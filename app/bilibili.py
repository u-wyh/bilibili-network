import json
import os
import re
import shutil
from copy import copy
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from imageio_ffmpeg import get_ffmpeg_exe
from yt_dlp import YoutubeDL
from yt_dlp.extractor.bilibili import BiliBiliBangumiIE
from yt_dlp.utils import DownloadError
from platform_support import APP_DATA, WINDOWS


NAV = "https://api.bilibili.com/x/web-interface/nav"
VIDEO_DETAILS = "https://api.bilibili.com/x/web-interface/view"
SEASON_DETAILS = "https://api.bilibili.com/pgc/view/web/season"
EPISODE_PLAYBACK = "https://api.bilibili.com/pgc/player/web/v2/playurl"
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
SESSION_COOKIES = {"SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid"}
BV_PATTERN = re.compile(r"BV[A-Za-z0-9]{10}")
EPISODE_PATTERN = re.compile(r"ep[1-9][0-9]{0,11}")


class AppError(Exception):
    pass


@dataclass(frozen=True)
class Episode:
    video_id: str
    part: int
    title: str


def video_reference(value):
    value = value.strip()
    if BV_PATTERN.fullmatch(value):
        return value, 1
    try:
        link = urlsplit(value)
    except ValueError:
        return None
    if link.scheme != "https" or link.netloc not in {"www.bilibili.com", "m.bilibili.com", "bilibili.com"}:
        return None
    episode = link.path.removeprefix("/bangumi/play/").rstrip("/")
    if link.path.startswith("/bangumi/play/") and EPISODE_PATTERN.fullmatch(episode):
        return episode, 1
    match = re.fullmatch(r"/video/(" + BV_PATTERN.pattern + r")/?", link.path)
    if not match:
        return None
    part = parse_qs(link.query).get("p", ["1"])[0]
    if not re.fullmatch(r"[0-9]{1,4}", part) or int(part) < 1:
        return None
    return match[1], int(part)


def video_url(video_id, part):
    if EPISODE_PATTERN.fullmatch(video_id) and part == 1:
        return f"https://www.bilibili.com/bangumi/play/{video_id}"
    if BV_PATTERN.fullmatch(video_id) and 1 <= part <= 9999:
        return f"https://www.bilibili.com/video/{video_id}/?p={part}"
    raise AppError("无法识别这个视频或分集。")


class BrowserSession:
    def __init__(self, cookies):
        self.cookies = CookieJar()
        for cookie in cookies:
            self.cookies.set_cookie(copy(cookie))
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, url):
        request = Request(url, headers={"User-Agent": AGENT, "Referer": "https://www.bilibili.com/"})
        with self.opener.open(request, timeout=12) as response:
            return json.load(response)

    def account_info(self):
        reply = self.request(NAV)
        data = reply.get("data") or {}
        if reply.get("code") != 0 or not data.get("isLogin") or not self.session_cookies():
            raise AppError("B 站登录已失效，请重新扫码登录。")
        vip = data.get("vip") or {}
        return {
            "name": data.get("uname") or "B 站账号",
            "vip": data.get("vipStatus", vip.get("status")) == 1,
        }

    def session_cookies(self):
        cookies = [
            copy(cookie) for cookie in self.cookies
            if cookie.name in SESSION_COOKIES
            and cookie.domain.lstrip(".") == "bilibili.com"
            and not cookie.is_expired()
        ]
        return cookies if any(cookie.name == "SESSDATA" for cookie in cookies) else []


def video_episodes(bvid, session):
    if EPISODE_PATTERN.fullmatch(bvid):
        reply = session.request(SEASON_DETAILS + "?" + urlencode({"ep_id": bvid[2:]}))
        season = reply.get("result") or {}
        episodes = {}
        for group in [season, *(season.get("section") or [])]:
            for entry in group.get("episodes") or []:
                video_id = f'ep{entry.get("id")}'
                if EPISODE_PATTERN.fullmatch(video_id):
                    title = entry.get("long_title") or entry.get("title") or video_id
                    episodes.setdefault(video_id, Episode(video_id, 1, title))
        if reply.get("code") == 0 and bvid in episodes:
            return season.get("title") or bvid, list(episodes.values())
        raise AppError("B 站未返回这部番剧的选集，请检查播放页和登录状态。")
    reply = session.request(VIDEO_DETAILS + "?" + urlencode({"bvid": bvid}))
    data = reply.get("data") or {}
    if reply.get("code") != 0:
        raise AppError("B 站未返回选集，请检查当前视频和登录状态。")
    title = data.get("title") or bvid
    pages = [
        Episode(bvid, page["page"], page.get("part") or f'P{page["page"]}')
        for page in data.get("pages") or []
        if isinstance(page.get("page"), int) and page["page"] > 0
    ]
    if len(pages) > 1:
        return title, pages
    season = data.get("ugc_season") or {}
    collection = {}
    for section in season.get("sections") or []:
        for entry in section.get("episodes") or []:
            video = entry.get("bvid") or ""
            part = (entry.get("page") or {}).get("page") or 1
            if BV_PATTERN.fullmatch(video) and isinstance(part, int) and part > 0:
                collection.setdefault((video, part), Episode(video, part, entry.get("title") or video))
    if len(collection) > 1 and any(video == bvid for video, _ in collection):
        return season.get("title") or title, list(collection.values())
    return title, pages or [Episode(bvid, 1, title)]


class QuietLog:
    def debug(self, message):
        pass

    warning = error = debug


class BiliWebEpisodeIE(BiliBiliBangumiIE):
    IE_NAME = "bilibili:episode-web"

    def _real_extract(self, url):
        episode_id = self._match_id(url)
        headers = {"Referer": url}
        query = {"ep_id": episode_id}
        reply = self._download_json(EPISODE_PLAYBACK, episode_id, headers=headers,
                                    query={**query, "fnval": 12240})
        if reply.get("code") != 0:
            code = reply.get("code")
            raise AppError(f"B 站未向当前会话提供正片（播放接口代码 {code}）。请在官网确认该账号能完整播放本集。")
        result = reply.get("result") or {}
        video = result.get("video_info") or {}
        flag = (result.get("play_check") or {}).get("play_detail") or result.get("play_video_type")
        if video.get("is_drm") in (1, "1"):
            raise AppError("B 站为这集提供了受保护的播放流，请在 B 站播放页观看。")
        if video.get("is_preview") in (1, "1") or flag in ("PLAY_PREVIEW", "preview"):
            raise AppError("B 站只向当前会话提供试看片段。请在官网确认该账号能完整播放本集。")
        formats = self.extract_formats(video) if flag in (None, "PLAY_WHOLE", "whole") else []
        if not formats:
            raise AppError("B 站未向当前会话返回可保存的完整音视频流。请在官网确认当前账号可播放整集。")
        details = self._download_json(SEASON_DETAILS, episode_id, headers=headers, query=query, fatal=False) or {}
        season = details.get("result") or {}
        episode = next(
            (entry for group in [season, *(season.get("section") or [])]
             for entry in group.get("episodes") or [] if str(entry.get("id")) == episode_id),
            {},
        )
        series = season.get("title") or "B 站番剧"
        title = episode.get("long_title") or episode.get("title") or f"EP {episode_id}"
        return {
            "id": episode_id, "title": f"{series} · {title}", "formats": formats,
            "duration": (video.get("timelength") or 0) / 1000,
            "http_headers": headers,
        }


def ffmpeg_path():
    try:
        source = Path(get_ffmpeg_exe())
    except RuntimeError:
        raise AppError("找不到 FFmpeg，请检查桌面版依赖是否安装完成。") from None
    if source == Path("ffmpeg"):
        return None
    if not source.is_file():
        raise AppError("找不到 FFmpeg，请检查桌面版依赖是否安装完成。")
    executable = "ffmpeg.exe" if WINDOWS else "ffmpeg"
    if source.name.lower() == executable:
        return str(source)
    tools = APP_DATA / source.stem
    tools.mkdir(parents=True, exist_ok=True)
    target = tools / executable
    if not target.is_file():
        with TemporaryDirectory(dir=tools) as folder:
            staged = Path(folder) / target.name
            shutil.copy2(source, staged)
            try:
                staged.rename(target)
            except FileExistsError:
                pass
    return str(target)


def download(bvid, part, quality, destination, login, progress, on_title=None):
    url = video_url(bvid, part)
    is_episode = bool(EPISODE_PATTERN.fullmatch(bvid))
    height = int(quality) if quality != "auto" else None
    tag = f"{height}p" if height else ("auto-account" if login else "auto-guest")
    stem = bvid if is_episode else f"{bvid}_p{part}"
    target = destination / f"{stem}_{tag}.mp4"
    if target.exists():
        return target, False
    cookies = []
    if login:
        progress(0, "正在确认 B 站缓存账号…")
        login.account_info()
        cookies = login.session_cookies()
        if not cookies:
            raise AppError("B 站登录已失效，请重新扫码登录。")

    constraint = f"[height={height}]" if height else ""
    title_reported = False

    def on_progress(info):
        nonlocal title_reported
        if on_title and not title_reported:
            title = (info.get("info_dict") or {}).get("title")
            if title:
                on_title(title)
                title_reported = True
        if info["status"] == "downloading":
            total = info.get("total_bytes") or info.get("total_bytes_estimate")
            if total:
                progress(min(100, 100 * info.get("downloaded_bytes", 0) / total), "正在下载当前媒体流…")
        elif info["status"] == "finished":
            progress(100, "当前媒体流已下载，等待下一条流或合并…")

    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".bilibili-app-", dir=destination) as folder:
        staged = Path(folder) / "video.mp4"
        logger = QuietLog()
        options = {
            "outtmpl": str(staged).replace("%", "%%"),
            "format": f"bv[ext=mp4]{constraint}+ba[ext=m4a]/b[ext=mp4]{constraint}",
            "format_sort": ["res", "vcodec:h264"],
            "merge_output_format": "mp4",
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 2,
            "extractor_retries": 2,
            "ffmpeg_location": ffmpeg_path(),
            "logger": logger,
            "progress_hooks": [on_progress],
        }
        with YoutubeDL(options) as ydl:
            extractor = None
            if is_episode:
                extractor = BiliWebEpisodeIE()
                ydl.add_info_extractor(extractor)
            for cookie in cookies:
                ydl.cookiejar.set_cookie(cookie)
            try:
                progress(0, "正在读取 B 站提供的完整正片和可用画质…" if is_episode else "正在读取视频和可用画质…")
                ydl.extract_info(url, download=True, ie_key=extractor.ie_key() if extractor else None)
            except DownloadError as exc:
                issue = str(exc).lower()
                if "drm" in issue:
                    raise AppError("B 站提供的是受保护的播放流，请在 B 站播放页观看。") from None
                if "geo-restricted" in issue or "not available from your location" in issue:
                    raise AppError("B 站没有在当前地区提供这个视频。") from None
                if "premium members" in issue or "login required" in issue or "log in" in issue:
                    message = ("B 站未向已验证账号提供正片，请确认这个视频在官网能完整播放。"
                               if login else "请先用顶部「登录 B 站」登录缓存账号。")
                    raise AppError(message) from None
                if "requested format is not available" in issue:
                    raise AppError("B 站没有向当前会话提供这个画质，请选择自动或其他画质。") from None
                if any(token in issue for token in ("http error 403", "http error 412", "http error 429")):
                    raise AppError("B 站拒绝了本次下载请求。请在官网确认该集可播放后再试。") from None
                if any(token in issue for token in ("timed out", "connection", "unable to download")):
                    raise AppError("缓存请求未完成。请检查 B 站媒体连接，稍后重试。") from None
                raise AppError("B 站信息读取或音视频合并失败，请尝试其他画质。") from None
        if not staged.is_file() or not staged.stat().st_size:
            raise AppError("未生成有效的 MP4 文件。")
        try:
            if WINDOWS:
                staged.rename(target)
            else:
                os.link(staged, target)
        except FileExistsError:
            return target, False
    return target, True
