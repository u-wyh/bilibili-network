import os
import sqlite3
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import quote, urlencode

from PySide6.QtCore import QCoreApplication, QDateTime, QEvent, QLockFile, QSettings, QSignalBlocker, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QStackedWidget, QTabWidget,
    QVBoxLayout, QWidget,
)

from bilibili import AppError, BrowserSession, SESSION_COOKIES, video_reference, video_url
from account_session import AccountStore
from cache_library import CacheLibrary
from cache_worker import cache_video as download, load_video_episodes, verify_account
from platform_support import APP_DATA, WINDOWS, downloads_folder

if WINDOWS:
    from PySide6.QtWebView import QWebView, QWebViewLoadingInfo, QtWebView


HOME = "https://www.bilibili.com/"
LOGIN = "https://passport.bilibili.com/login?" + urlencode({"gourl": HOME})
QUALITY = {"自动 · 最高可用": "auto", "1080p": "1080", "720p": "720", "480p": "480", "360p": "360"}
PREVIEW_LINKS = """
(() => {
  if (window.biliCacheNavigation) return;
  window.biliCacheNavigation = true;
  const isBilibili = value => {
    try {
      const url = new URL(value, location.href);
      return url.protocol === 'https:' &&
        (url.hostname === 'bilibili.com' || url.hostname.endsWith('.bilibili.com'));
    } catch (_) { return false; }
  };
  const open = window.open.bind(window);
  window.open = (url, ...options) => {
    if (!url || !isBilibili(url)) return open(url, ...options);
    location.assign(url);
    return window;
  };
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[target="_blank"][href]');
    if (link && isBilibili(link.href)) link.target = '_self';
  }, true);
  document.addEventListener('submit', event => {
    const form = event.target;
    if (form.target === '_blank' && isBilibili(form.action)) form.target = '_self';
  }, true);
})();
"""


def site_url(url):
    host = url.host()
    return url.scheme() == "https" and not url.userInfo() and url.port() in (-1, 443) and (
        host in {"bilibili.com", "b23.tv"} or host.endswith(".bilibili.com")
    )


class BiliPage(QWebEnginePage):
    video_clicked = Signal(str)
    playback_requested = Signal(QUrl)
    blocked = Signal()

    def __init__(self, profile, parent):
        super().__init__(profile, parent)
        self.click_download = False
        self.navigation_rejected = False
        self.newWindowRequested.connect(self.open_requested_window)

    def handle_video_click(self, url):
        if not video_reference(url.toString()):
            return False
        if self.click_download:
            self.video_clicked.emit(url.toString())
        else:
            self.playback_requested.emit(url)
        return True

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if not is_main_frame or url.toString() == "about:blank":
            return True
        if not site_url(url):
            self.navigation_rejected = True
            self.blocked.emit()
            return False
        if navigation_type == self.NavigationType.NavigationTypeLinkClicked:
            self.navigation_rejected = self.handle_video_click(url)
            return not self.navigation_rejected
        self.navigation_rejected = False
        return True

    def open_requested_window(self, request):
        url = request.requestedUrl()
        user_initiated = request.isUserInitiated()
        if not user_initiated and url.host() != "search.bilibili.com":
            return
        if not site_url(url):
            self.blocked.emit()
        elif not (user_initiated and self.handle_video_click(url)):
            QTimer.singleShot(0, lambda: self.setUrl(url))


class BiliView(QWebEngineView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # The desktop site has a wide layout. Keep its navigation visible beside the queue.
        zoom = min(1.0, max(0.65, self.width() / 1240))
        if abs(self.zoomFactor() - zoom) > 0.01:
            self.setZoomFactor(zoom)


@dataclass(frozen=True)
class Job:
    bvid: str
    part: int
    quality: str
    folder: Path
    account: bool

    @property
    def title(self):
        quality = f"{self.quality}p" if self.quality != "auto" else "自动画质"
        return f"{self.bvid} · P{self.part} · {quality}"


class App(QMainWindow):
    progress_changed = Signal(int, str)
    title_ready = Signal(str)
    job_finished = Signal(object, str)
    episodes_ready = Signal(object, object, str)
    account_ready = Signal(int, object, str)

    def __init__(self, session_path=None):
        super().__init__()
        self.setWindowTitle("B 站浏览与缓存")
        self.resize(1360, 850)
        self.setMinimumSize(880, 620)
        self.cookies = {}
        self.account_store = AccountStore(session_path or APP_DATA / "cache-session.dpapi")
        self.restoring_login = False
        self.selected_video = None
        self.account_generation = 0
        self.pending = deque()
        self.scheduled = set()
        self.active = None
        self.preferences = QSettings("bilibili-network", "desktop")
        self.folder = Path(self.preferences.value("cacheFolder", str(downloads_folder() / "bilibili-network")))
        self.library = CacheLibrary(APP_DATA / "cache.sqlite3")
        self.fetching_episodes = False

        self.profile = QWebEngineProfile(self)
        self.profile.setHttpAcceptLanguage("zh-CN,zh;q=0.9,en;q=0.7")
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.add_cookie)
        self.cookie_store.cookieRemoved.connect(self.remove_cookie)
        self.view = BiliView(self)
        self.page = BiliPage(self.profile, self.view)
        self.view.setPage(self.page)
        self.page.video_clicked.connect(self.select_and_enqueue)
        self.page.playback_requested.connect(self.show_preview)
        self.page.blocked.connect(lambda: self.notice.setText("浏览窗口用于打开 B 站页面。"))
        self.view.urlChanged.connect(self.browser_url_changed)
        self.view.loadFinished.connect(self.page_loaded)
        self.progress_changed.connect(self.update_progress)
        self.title_ready.connect(self.update_title)
        self.job_finished.connect(self.finish_job)
        self.episodes_ready.connect(self.choose_episodes)
        self.account_ready.connect(self.show_account)
        self.build_ui()
        self.refresh_library()
        self.preview = None
        self.restore_login()

    def build_ui(self):
        center = QWidget()
        self.setCentralWidget(center)
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(objectName="header")
        bar = QHBoxLayout(header)
        bar.setContentsMargins(18, 12, 18, 12)
        bar.setSpacing(8)
        brand = QLabel("B 站浏览与缓存", objectName="brand")
        bar.addWidget(brand)
        for text, action in (("后退", self.go_back), ("刷新", self.reload),
                             ("首页", lambda: self.open_page(QUrl(HOME)))):
            button = QPushButton(text)
            button.clicked.connect(action)
            bar.addWidget(button)
        self.address = QLineEdit()
        self.address.setPlaceholderText("搜索 B 站，或输入 BV 号 / 链接")
        self.address.returnPressed.connect(self.navigate)
        bar.addWidget(self.address, stretch=1)
        go = QPushButton("搜索 / 打开")
        go.clicked.connect(self.navigate)
        bar.addWidget(go)
        self.login_button = QPushButton("登录 B 站")
        self.login_button.clicked.connect(self.check_or_login)
        bar.addWidget(self.login_button)
        self.logout_button = QPushButton("退出缓存账号")
        self.logout_button.setVisible(False)
        self.logout_button.clicked.connect(self.logout)
        bar.addWidget(self.logout_button)
        layout.addWidget(header)

        work_area = QFrame()
        row = QHBoxLayout(work_area)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.web_area = QStackedWidget()
        self.web_area.addWidget(self.view)
        row.addWidget(self.web_area, stretch=1)
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(320)
        controls = QVBoxLayout(sidebar)
        controls.setContentsMargins(15, 18, 15, 16)
        controls.setSpacing(9)
        controls.addWidget(QLabel("视频缓存", objectName="sectionTitle"))
        self.auto_click = QCheckBox("点击卡片直接缓存")
        self.auto_click.toggled.connect(self.toggle_click_download)
        self.notice = QLabel("先打开视频观看，想留存时再缓存。", wordWrap=True, objectName="muted")
        controls.addWidget(self.notice)
        self.selection_label = QLabel("请先选中一个视频或具体分集。", wordWrap=True, objectName="muted")
        controls.addWidget(self.selection_label)
        self.current_button = QPushButton("缓存当前视频", objectName="primary")
        self.current_button.setEnabled(False)
        self.current_button.clicked.connect(lambda: self.with_video_url(self.enqueue))
        controls.addWidget(self.current_button)
        self.episodes_button = QPushButton("选集缓存…")
        self.episodes_button.setEnabled(False)
        self.episodes_button.clicked.connect(lambda: self.with_video_url(self.load_episodes))
        controls.addWidget(self.episodes_button)
        self.web_player_button = QPushButton("用系统浏览器观看")
        self.web_player_button.setEnabled(False)
        self.web_player_button.clicked.connect(lambda: self.with_video_url(self.open_system_video))
        controls.addWidget(self.web_player_button)
        controls.addWidget(self.auto_click)

        options = QHBoxLayout()
        options.addWidget(QLabel("画质"))
        self.quality = QComboBox()
        self.quality.addItems(list(QUALITY))
        options.addWidget(self.quality, stretch=1)
        controls.addLayout(options)
        self.folder_label = QLabel(str(self.folder), wordWrap=True, objectName="muted")
        controls.addWidget(self.folder_label)
        folder_buttons = QHBoxLayout()
        for text, action in (("更改保存位置", self.choose_folder), ("打开文件夹", self.open_folder)):
            button = QPushButton(text)
            button.clicked.connect(action)
            folder_buttons.addWidget(button, stretch=1)
        controls.addLayout(folder_buttons)
        self.tabs = QTabWidget()
        queue_page = QWidget()
        queue_controls = QVBoxLayout(queue_page)
        queue_controls.setContentsMargins(0, 8, 0, 0)
        self.items = QListWidget()
        self.items.setWordWrap(True)
        self.items.itemDoubleClicked.connect(self.open_video)
        queue_controls.addWidget(self.items, stretch=1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        queue_controls.addWidget(self.progress)
        self.tabs.addTab(queue_page, "缓存队列")

        library_page = QWidget()
        library_controls = QVBoxLayout(library_page)
        library_controls.setContentsMargins(0, 8, 0, 0)
        self.cached_items = QListWidget()
        self.cached_items.setWordWrap(True)
        self.cached_items.itemDoubleClicked.connect(self.open_video)
        self.cached_items.currentItemChanged.connect(self.update_cache_actions)
        library_controls.addWidget(self.cached_items, stretch=1)
        library_buttons = QHBoxLayout()
        self.play_cached_button = QPushButton("播放")
        self.play_cached_button.clicked.connect(lambda: self.open_video(self.cached_items.currentItem()))
        self.delete_cached_button = QPushButton("删除缓存", objectName="danger")
        self.delete_cached_button.clicked.connect(self.delete_cached)
        library_buttons.addWidget(self.play_cached_button, stretch=1)
        library_buttons.addWidget(self.delete_cached_button, stretch=1)
        library_controls.addLayout(library_buttons)
        self.tabs.addTab(library_page, "本地缓存")
        controls.addWidget(self.tabs, stretch=1)
        self.status = QLabel("当前没有缓存任务。", wordWrap=True, objectName="muted")
        controls.addWidget(self.status)
        row.addWidget(sidebar)
        layout.addWidget(work_area, stretch=1)

    def navigate(self):
        value = self.address.text().strip()
        if not value:
            return
        reference = video_reference(value)
        if reference and not value.startswith("https://"):
            value = video_url(*reference)
        elif not QUrl(value).scheme():
            if value.startswith(("bilibili.com/", "www.bilibili.com/", "b23.tv/")):
                value = "https://" + value
            else:
                value = "https://search.bilibili.com/all?" + urlencode({"keyword": value}, quote_via=quote)
        url = QUrl(value)
        if site_url(url):
            self.open_page(url)
        else:
            self.notice.setText("请输入 B 站链接、BV 号或搜索词。")

    def open_page(self, url):
        if video_reference(url.toString()):
            self.show_preview(url)
        else:
            self.show_browser()
            self.view.setUrl(url)

    def show_browser(self):
        if self.preview:
            self.preview.setUrl(QUrl("about:blank"))
        self.web_area.setCurrentWidget(self.view)
        self.url_changed(self.view.url())

    def show_preview(self, url):
        if not WINDOWS:
            if url.isLocalFile():
                QDesktopServices.openUrl(url)
            else:
                self.view.setUrl(url)
            return
        if self.preview is None:
            self.preview = QWebView()
            self.preview_container = QWidget.createWindowContainer(self.preview)
            self.web_area.addWidget(self.preview_container)
            self.preview.urlChanged.connect(self.preview_url_changed)
            self.preview.loadingChanged.connect(self.preview_loaded)
        self.web_area.setCurrentWidget(self.preview_container)
        self.url_changed(url)
        self.preview.setUrl(url)

    def preview_url_changed(self, url):
        if self.web_area.currentWidget() is not self.view and url.toString() != "about:blank":
            self.url_changed(url)

    def browser_url_changed(self, url):
        if self.web_area.currentWidget() is self.view:
            self.url_changed(url)

    def preview_loaded(self, info):
        if info.status() == QWebViewLoadingInfo.LoadStatus.Succeeded and site_url(info.url()):
            self.preview.runJavaScript(PREVIEW_LINKS, lambda _: None)

    def go_back(self):
        if self.web_area.currentWidget() is self.view:
            self.view.back()
        else:
            self.show_browser()

    def reload(self):
        if self.web_area.currentWidget() is self.view:
            self.view.reload()
        else:
            self.preview.reload()

    def with_video_url(self, action):
        selected = self.selected_video
        if not selected:
            self.status.setText("请先打开视频，或点击卡片选中一个具体分集。")
            return

        if self.web_area.currentWidget() is self.view:
            action(video_url(*selected))
            return

        preview = self.preview
        handled = False
        self.status.setText("正在识别当前视频…")

        def finish(url=None):
            nonlocal handled
            if handled:
                return
            handled = True
            if self.web_area.currentWidget() is self.view or self.selected_video != selected:
                self.status.setText("播放页已切换，请在当前分集重新点击。")
                return
            reference = video_reference(url) if isinstance(url, str) else None
            if reference:
                self.set_video_selection(reference)
            action(video_url(*(reference or selected)))

        QTimer.singleShot(1500, finish)
        preview.runJavaScript("location.href", finish)

    def url_changed(self, url):
        self.address.setText(url.toString())
        self.set_video_selection(video_reference(url.toString()))

    def set_video_selection(self, reference):
        self.selected_video = reference
        if reference:
            video_id, part = reference
            label = video_id if video_id.startswith("ep") else f"{video_id} · P{part}"
            if not WINDOWS:
                label += "\n预览无法播放时，可用系统浏览器观看。"
            self.selection_label.setText(f"当前选中：{label}")
        else:
            self.selection_label.setText("请先选中一个视频或具体分集。")
        self.current_button.setEnabled(reference is not None)
        self.web_player_button.setEnabled(reference is not None)
        self.episodes_button.setEnabled(reference is not None and not self.fetching_episodes)

    @Slot(str)
    def select_and_enqueue(self, url):
        reference = video_reference(url)
        if reference:
            self.set_video_selection(reference)
            self.queue_video(*reference)

    def open_system_video(self, url):
        opened = QDesktopServices.openUrl(QUrl(url))
        self.status.setText("已在系统浏览器打开当前分集。" if opened else "系统浏览器未能打开当前分集。")

    def page_loaded(self, success):
        if (self.web_area.currentWidget() is self.view and not success
                and not self.page.navigation_rejected and not self.view.url().isEmpty()):
            self.notice.setText("页面未能加载。请检查网络后点击刷新。")

    def toggle_click_download(self, enabled):
        self.page.click_download = enabled
        self.notice.setText("点 B 站视频卡片，视频会加入缓存队列。" if enabled else
                            "先打开视频观看，想留存时再缓存。")

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存位置", str(self.folder))
        if path:
            self.folder = Path(path)
            self.preferences.setValue("cacheFolder", path)
            self.folder_label.setText(str(self.folder))

    def open_folder(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))
        except OSError:
            self.status.setText("无法打开保存目录。")

    def open_video(self, item):
        path = item.data(Qt.ItemDataRole.UserRole) if item else None
        if path and Path(path).is_file():
            self.show_preview(QUrl.fromLocalFile(path))
        elif path:
            self.status.setText("缓存文件已不存在。")
            self.refresh_library()

    def refresh_library(self):
        self.cached_items.clear()
        for path, title in self.library.entries():
            try:
                size = path.stat().st_size / (1024 * 1024)
            except OSError:
                continue
            item = QListWidgetItem(f"{title}\n{size:.1f} MiB")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.cached_items.addItem(item)
        self.update_cache_actions()

    def update_cache_actions(self):
        enabled = self.cached_items.currentItem() is not None
        self.play_cached_button.setEnabled(enabled)
        self.delete_cached_button.setEnabled(enabled)

    def delete_cached(self):
        item = self.cached_items.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        choice = QMessageBox.question(
            self, "删除本地缓存", f"从电脑删除这个缓存文件？\n{Path(path).name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        if self.preview and self.preview.url().isLocalFile() and Path(self.preview.url().toLocalFile()) == Path(path):
            self.show_browser()
            QTimer.singleShot(400, lambda: self.remove_cached_file(path))
        else:
            self.remove_cached_file(path)

    def remove_cached_file(self, path):
        try:
            self.library.remove(path)
            for i in range(self.items.count()):
                item = self.items.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == path:
                    item.setData(Qt.ItemDataRole.UserRole, None)
                    item.setText(item.text().split("\n", 1)[0] + "\n本地缓存已删除")
            self.refresh_library()
            self.status.setText("本地缓存已删除。")
        except (OSError, sqlite3.Error):
            self.status.setText("删除失败。请关闭正在播放该文件的播放器后重试。")

    def load_episodes(self, url):
        reference = video_reference(url)
        if reference is None or self.fetching_episodes:
            return
        self.fetching_episodes = True
        self.episodes_button.setEnabled(False)
        self.status.setText("正在读取 B 站的选集…")
        session = BrowserSession(tuple(self.cookies.values()))

        def run():
            try:
                title, episodes = load_video_episodes(reference[0], session)
                self.episodes_ready.emit(reference, episodes, title)
            except AppError as exc:
                self.episodes_ready.emit(reference, None, str(exc))
            except Exception:
                self.episodes_ready.emit(reference, None, "暂时无法读取选集，请检查网络后重试。")

        threading.Thread(target=run, daemon=True).start()

    @Slot(object, object, str)
    def choose_episodes(self, current, episodes, title):
        self.fetching_episodes = False
        self.episodes_button.setEnabled(self.current_button.isEnabled())
        if not episodes:
            self.status.setText(title)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("选集缓存")
        dialog.resize(560, 500)
        layout = QVBoxLayout(dialog)
        heading = QLabel(title, wordWrap=True, objectName="sectionTitle")
        layout.addWidget(heading)
        current_index = next((i for i, item in enumerate(episodes)
                              if (item.video_id, item.part) == current), 0)
        range_controls = QHBoxLayout()
        layout.addLayout(range_controls)
        range_controls.addWidget(QLabel("列表序号"))
        start_number = QSpinBox()
        start_number.setAccessibleName("起始序号")
        start_number.setRange(1, len(episodes))
        start_number.setValue(current_index + 1)
        range_controls.addWidget(start_number)
        range_controls.addWidget(QLabel("到"))
        end_number = QSpinBox()
        end_number.setAccessibleName("结束序号")
        end_number.setRange(current_index + 1, len(episodes))
        end_number.setValue(current_index + 1)
        start_number.valueChanged.connect(end_number.setMinimum)
        range_controls.addWidget(end_number)
        choose_range = QPushButton("选择这段")
        choose_range.setDefault(True)
        range_controls.addWidget(choose_range)
        range_controls.addStretch(1)

        items = QListWidget()
        layout.addWidget(items, stretch=1)
        for i, episode in enumerate(episodes):
            item = QListWidgetItem(f"{i + 1}. {episode.title}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if i == current_index else Qt.CheckState.Unchecked)
            items.addItem(item)
        items.scrollToItem(items.item(current_index))

        actions = QHBoxLayout()
        layout.addLayout(actions)

        def update_count():
            count = sum(items.item(i).checkState() == Qt.CheckState.Checked for i in range(items.count()))
            selected_count.setText(f"已选 {count} / {len(episodes)} 集")
            accept.setEnabled(count > 0)

        def select_range(start, stop):
            with QSignalBlocker(items):
                for i in range(items.count()):
                    items.item(i).setCheckState(Qt.CheckState.Checked if start <= i < stop else Qt.CheckState.Unchecked)
            update_count()
            if start < stop:
                items.scrollToItem(items.item(start))

        choose_range.clicked.connect(lambda: select_range(start_number.value() - 1, end_number.value()))
        for label, start, stop in (("全选", 0, len(episodes)),
                                   ("从当前集开始", current_index, len(episodes)), ("清空", 0, 0)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, first=start, last=stop: select_range(first, last))
            actions.addWidget(button)
        actions.addStretch(1)
        selected_count = QLabel(objectName="muted")
        actions.addWidget(selected_count)
        accept = QPushButton("缓存所选", objectName="primary")
        accept.setAutoDefault(False)
        accept.clicked.connect(dialog.accept)
        actions.addWidget(accept)
        items.itemChanged.connect(update_count)
        update_count()
        end_number.setFocus()
        end_number.selectAll()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for i, episode in enumerate(episodes):
                if items.item(i).checkState() == Qt.CheckState.Checked:
                    self.queue_video(episode.video_id, episode.part, episode.title)
        elif not self.active:
            self.status.setText("已关闭选集。")

    def add_cookie(self, network_cookie):
        name = bytes(network_cookie.name()).decode("ascii", errors="ignore")
        domain = network_cookie.domain().lower()
        if domain.lstrip(".") != "bilibili.com" or name not in SESSION_COOKIES:
            return
        expiry = None if network_cookie.isSessionCookie() else network_cookie.expirationDate().toSecsSinceEpoch()
        path = network_cookie.path() or "/"
        flags = {"HttpOnly": None} if network_cookie.isHttpOnly() else {}
        cookie = Cookie(0, name, bytes(network_cookie.value()).decode("latin-1"), None, False,
                        domain, True, domain.startswith("."), path, True, network_cookie.isSecure(),
                        expiry, expiry is None, None, None, flags, False)
        key = name, domain, path
        previous = self.cookies.get(key)
        if previous and vars(previous) == vars(cookie):
            return
        self.cookies[key] = cookie
        if name == "SESSDATA":
            self.update_login_status()
        self.save_login()

    def remove_cookie(self, network_cookie):
        name = bytes(network_cookie.name()).decode("ascii", errors="ignore")
        key = name, network_cookie.domain().lower(), network_cookie.path() or "/"
        if self.cookies.pop(key, None) is not None:
            if name == "SESSDATA":
                self.update_login_status()
            self.save_login()

    def restore_login(self):
        try:
            records = self.account_store.load()
        except OSError:
            records = []
            self.status.setText("无法读取已保留的登录，请重新登录。" if WINDOWS else
                                "无法读取系统密钥环。请解锁桌面密钥环后重开应用，或扫码临时登录。")
        except ValueError:
            records = []
            self.status.setText("无法读取已保留的登录，请重新登录。")
        self.restoring_login = True
        pending = False
        for record in records:
            if (record["name"] not in SESSION_COOKIES or record["domain"].lstrip(".") != "bilibili.com"
                    or record["expires"] is not None and record["expires"] <= time.time()):
                continue
            cookie = QNetworkCookie(record["name"].encode("ascii"), record["value"].encode("latin-1"))
            cookie.setDomain(record["domain"])
            cookie.setPath(record["path"])
            cookie.setSecure(record["secure"])
            cookie.setHttpOnly(record["http_only"])
            if record["expires"] is not None:
                cookie.setExpirationDate(QDateTime.fromSecsSinceEpoch(record["expires"]))
            self.add_cookie(cookie)
            self.cookie_store.setCookie(cookie, QUrl(HOME))
            pending = True
        if pending:
            QTimer.singleShot(550, self.finish_restoring_login)
        else:
            self.finish_restoring_login()

    def finish_restoring_login(self):
        self.restoring_login = False
        self.view.setUrl(QUrl(HOME))

    def save_login(self):
        if self.restoring_login:
            return
        try:
            cookies = BrowserSession(self.cookies.values()).session_cookies()
            if not cookies:
                self.account_store.clear()
                return
            records = [{
                "name": cookie.name, "value": cookie.value, "domain": cookie.domain, "path": cookie.path,
                "secure": cookie.secure, "expires": cookie.expires,
                "http_only": cookie.has_nonstandard_attr("HttpOnly"),
            } for cookie in cookies]
            self.account_store.save(records)
        except OSError:
            self.status.setText("当前登录仍可使用，但这次未能保留到下次启动。" if WINDOWS else
                                "当前登录可用。请解锁桌面密钥环并重新扫码，以保留登录。")

    def logged_in(self):
        return any(cookie.name == "SESSDATA" and not cookie.is_expired() for cookie in self.cookies.values())

    def update_login_status(self):
        self.account_generation += 1
        generation = self.account_generation
        self.login_button.setEnabled(True)
        has_session = self.logged_in()
        self.logout_button.setVisible(has_session)
        if not has_session:
            self.login_button.setText("登录 B 站")
            self.login_button.setToolTip("登录后，缓存使用当前账号的权限。")
            return
        self.login_button.setText("正在验证账号…")
        self.login_button.setEnabled(False)
        session = BrowserSession(tuple(self.cookies.values()))

        def run():
            try:
                account = verify_account(session)
                self.account_ready.emit(generation, account, "")
            except AppError as exc:
                self.account_ready.emit(generation, None, str(exc))
            except Exception:
                self.account_ready.emit(generation, None, "暂时无法验证 B 站账号，请重试。")

        threading.Thread(target=run, daemon=True).start()

    @Slot(int, object, str)
    def show_account(self, generation, account, message):
        if generation != self.account_generation:
            return
        self.login_button.setEnabled(True)
        self.login_button.setText(
            ("大会员已验证" if account["vip"] else "普通账号已验证") if account else "重新登录 B 站"
        )
        self.login_button.setToolTip(account["name"] + "，点击重新验证" if account else message)
        if not account:
            self.status.setText(message)

    def check_or_login(self):
        if not self.logged_in() or self.login_button.text() == "重新登录 B 站":
            self.open_page(QUrl(LOGIN))
        else:
            self.update_login_status()

    def logout(self):
        choice = QMessageBox.question(
            self, "退出缓存账号", "清除这台电脑中保留的缓存账号登录？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self.account_store.clear()
        except OSError:
            self.status.setText("无法清除保留的登录，请稍后重试。")
            return
        self.cookie_store.deleteAllCookies()
        self.cookies.clear()
        self.update_login_status()
        self.open_page(QUrl(HOME))
        self.status.setText("已清除本地保存的缓存账号登录。")

    @Slot(str)
    def enqueue(self, url):
        reference = video_reference(url)
        if reference is not None:
            self.queue_video(*reference)

    def queue_video(self, bvid, part, title=None):
        job = Job(bvid, part, QUALITY[self.quality.currentText()], self.folder, self.logged_in())
        if job in self.scheduled:
            self.status.setText("该视频已在队列中。")
            return
        item = QListWidgetItem(f"{title or job.title}\n等待缓存")
        if title:
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
        self.items.addItem(item)
        self.pending.append((job, item))
        self.scheduled.add(job)
        self.items.scrollToItem(item)
        self.tabs.setCurrentIndex(0)
        self.start_next()

    def start_next(self):
        if self.active or not self.pending:
            return
        job, item = self.pending.popleft()
        self.active = job, item
        self.progress.setValue(0)
        item.setText(f"{item.data(Qt.ItemDataRole.UserRole + 1) or job.title}\n正在处理")
        self.status.setText(f"{job.title}，正在检查可用画质…")
        login = BrowserSession(tuple(self.cookies.values())) if job.account else None

        def run():
            def progress(percent, status):
                self.progress_changed.emit(int(percent), status)

            try:
                target, saved = download(job.bvid, job.part, job.quality, job.folder, login, progress,
                                         self.title_ready.emit)
                self.job_finished.emit(str(target), "已缓存" if saved else "已有缓存")
            except AppError as exc:
                self.job_finished.emit(None, str(exc))
            except Exception:
                self.job_finished.emit(None, "下载失败。请检查网络连接和保存目录。")

        threading.Thread(target=run, daemon=True).start()

    @Slot(int, str)
    def update_progress(self, percent, message):
        self.progress.setValue(percent)
        self.status.setText(message)

    @Slot(str)
    def update_title(self, title):
        _, item = self.active
        item.setData(Qt.ItemDataRole.UserRole + 1, title)
        item.setText(f"{title}\n正在下载")

    @Slot(object, str)
    def finish_job(self, path, message):
        job, item = self.active
        title = item.data(Qt.ItemDataRole.UserRole + 1) or job.title
        if path:
            item.setData(Qt.ItemDataRole.UserRole, path)
            try:
                item.setData(Qt.ItemDataRole.UserRole, str(self.library.add(path, title)))
                self.refresh_library()
            except (OSError, sqlite3.Error):
                message += "，缓存列表更新失败。"
        item.setText(f"{title}\n{message}")
        self.progress.setValue(100 if path else 0)
        self.status.setText(message)
        self.scheduled.discard(job)
        self.active = None
        self.start_next()

    def closeEvent(self, event):
        if self.active:
            self.status.setText("队列仍在处理，请等下载结束后再关闭。")
            event.ignore()
        else:
            if self.preview:
                self.preview_container.close()
            event.accept()


if __name__ == "__main__":
    if WINDOWS:
        os.environ.setdefault("QT_WEBVIEW_PLUGIN", "webview2")
        os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(APP_DATA / "preview-browser"))
    application = QApplication(sys.argv)
    application.setWindowIcon(QIcon(str(Path(__file__).with_name("icon.png"))))
    if WINDOWS:
        QtWebView.initialize()
    application.setStyleSheet(Path(__file__).with_name("style.qss").read_text(encoding="utf-8"))
    APP_DATA.mkdir(parents=True, exist_ok=True)
    profile_lock = QLockFile(str(APP_DATA / "cache-browser.lock"))
    profile_lock.setStaleLockTime(0)
    if not profile_lock.tryLock(0):
        QMessageBox.information(None, "B 站浏览与缓存", "应用已经打开，请切换到现有窗口。")
        sys.exit(0)
    window = App()
    window.show()
    status = application.exec()
    window.page.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    window.profile.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    profile_lock.unlock()
    sys.exit(status)
