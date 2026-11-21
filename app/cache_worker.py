import json
import subprocess
import sys
from http.cookiejar import Cookie
from pathlib import Path

from bilibili import AppError, BrowserSession, Episode, download, video_episodes
from platform_support import WINDOWS


def run_worker(request, session, notify):
    cookies = []
    if session:
        for cookie in session.session_cookies():
            fields = vars(cookie).copy()
            fields["rest"] = fields.pop("_rest")
            cookies.append(fields)
    request["cookies"] = cookies
    python = Path(sys.executable).with_name("python.exe") if WINDOWS else Path(sys.executable)
    command = [str(python), "-B", "-X", "utf8", str(Path(__file__).resolve())]
    result = None
    error = None
    # Pass the browser session directly to this worker over a private pipe.
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as worker:
        worker.stdin.write(json.dumps(request))
        worker.stdin.close()
        for line in worker.stdout:
            try:
                event, *values = json.loads(line)
            except ValueError:
                continue
            if event == "result":
                result = values
            elif event == "error":
                error = values[0]
            else:
                notify(event, values)
        status = worker.wait()
    if error:
        raise AppError(error)
    if status or result is None:
        raise AppError("缓存服务未能完成操作，请重试。")
    return result


def cache_video(bvid, part, quality, folder, session, progress, on_title):
    def notify(event, values):
        if event == "title":
            on_title(values[0])
        elif event == "progress":
            progress(*values)

    path, saved = run_worker({
        "action": "download", "bvid": bvid, "part": part, "quality": quality,
        "folder": str(folder), "account": session is not None,
    }, session, notify)
    return Path(path), saved


def load_video_episodes(bvid, session):
    title, episodes = run_worker({"action": "episodes", "bvid": bvid}, session, lambda *_: None)
    return title, [Episode(*episode) for episode in episodes]


def verify_account(session):
    account, = run_worker({"action": "account"}, session, lambda *_: None)
    return account


def serve():
    def emit(*event):
        print(json.dumps(event), flush=True)

    try:
        request = json.load(sys.stdin)
        session = BrowserSession(Cookie(**fields) for fields in request["cookies"])
        if request["action"] == "account":
            emit("result", session.account_info())
            return
        if request["action"] == "episodes":
            title, episodes = video_episodes(request["bvid"], session)
            emit("result", title, [(ep.video_id, ep.part, ep.title) for ep in episodes])
            return
        if request["action"] != "download":
            raise AppError("无法识别缓存操作。")
        path, saved = download(
            request["bvid"], request["part"], request["quality"], Path(request["folder"]),
            session if request["account"] else None,
            lambda *values: emit("progress", *values), lambda title: emit("title", title),
        )
        emit("result", str(path), saved)
    except AppError as exc:
        emit("error", str(exc))
    except Exception:
        emit("error", "操作失败。请检查网络连接和保存目录。")


if __name__ == "__main__":
    serve()
