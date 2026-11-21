Bilibili Cache / B 站浏览与缓存
https://github.com/u-wyh/bilibili-network

Windows x64
Extract the entire archive and double-click Bilibili-Download.exe.
Python is included. The public bundle installs Qt and FFmpeg from their
upstream packages on first launch. An offline build can include them.
Playback inside the app uses the Microsoft Edge WebView2 Runtime.
https://developer.microsoft.com/microsoft-edge/webview2/

Linux x64
Extract the archive on a Linux desktop, then run:
  bash ./Bilibili-Download.sh
Python 3.10+ with the venv module is required. The first launch installs Python
dependencies into a user-owned environment. The Linux archive includes a pip
bootstrap for distributions where ensurepip is unavailable. For playback use the app's system-browser
button. Saving a login across restarts requires an unlocked Secret Service
keyring. The Ubuntu virtual-machine download script is also included.

Both platforms
The app uses the Bilibili account you sign into inside the app. Bilibili
determines the available video streams and quality. Video files are saved
locally, by default in the Downloads/bilibili-network directory.
Only app runtime files are included. Login data and existing videos stay
in the user profile.

Windows bundle components
CPython: https://www.python.org/
Qt for Python: https://www.qt.io/qt-for-python
yt-dlp: https://github.com/yt-dlp/yt-dlp
FFmpeg via imageio-ffmpeg: https://github.com/imageio/imageio-ffmpeg
Package license and metadata files are included with the components.
