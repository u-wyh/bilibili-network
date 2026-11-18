#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
用法：./download-bilibili.sh [-p 分P] [-o 输出目录] <BV号或B站视频链接>
  -p, --part N       分 P 编号，默认 1
  -o, --output DIR   输出目录，默认 ~/Downloads/bilibili-network
  -h, --help         显示帮助
支持 bilibili.com/video/BV… 和能跳转到该页面的 b23.tv 短链接。
下载匿名可用的 360p MP4。忽略链接中的 p 参数，请用 --part 指定分 P。
EOF
}

fail() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

part=1
output_dir="$HOME/Downloads/bilibili-network"
video=
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -p|--part)
      (($# >= 2)) || fail "$1 需要分 P 编号。"
      part=$2
      shift
      ;;
    -o|--output)
      (($# >= 2)) && [[ -n $2 ]] || fail "$1 需要输出目录。"
      output_dir=$2
      shift
      ;;
    -*) fail "未知参数 $1。请运行 --help 查看用法。" ;;
    *)
      [[ -z $video ]] || fail '一次只能下载一个视频的一个分 P。'
      video=$1
      ;;
  esac
  shift
done

[[ -n $video ]] || fail '请提供 BV 号或 B 站视频链接。'
[[ $part =~ ^0*([1-9][0-9]*)$ ]] || fail '分 P 编号必须是正整数。'
part=${BASH_REMATCH[1]}

if [[ $video =~ ^https?://b23\.tv/[[:alnum:]]+([/?#].*)?$ ]]; then
  command -v curl >/dev/null || fail '解析 b23.tv 短链接需要 curl，请运行 sudo apt install curl。'
  # 只读取短链返回的 Location，再按下方规则验证目标。
  video=$(curl -q -fsS --max-time 15 --output /dev/null --write-out '%{redirect_url}' -- "$video") ||
    fail '无法解析 b23.tv 短链接，请检查网络或改用视频页链接。'
  [[ -n $video ]] || fail '短链接未返回跳转地址，请使用视频页链接。'
fi

bv_pattern='BV[[:alnum:]]{10}'
if [[ $video =~ ^$bv_pattern$ ]]; then
  bvid=$video
elif [[ $video =~ ^https?://((www|m)\.)?bilibili\.com/video/($bv_pattern)/?([?#].*)?$ ]]; then
  bvid=${BASH_REMATCH[3]}
else
  fail '无法识别视频。请提供 BV 号或 bilibili.com/video/BV… 链接。'
fi

[[ $output_dir == /* ]] || output_dir="$PWD/$output_dir"
filename="${bvid}_p${part}.mp4"
target="$output_dir/$filename"
[[ ! -e $target && ! -L $target ]] || fail "目标文件已存在：$target。请选择其他输出目录。"

tools_dir="$HOME/.local/share/bilibili-network"
yt_dlp=$(command -v yt-dlp || true)
yt_dlp=${yt_dlp:-"$tools_dir/venv/bin/yt-dlp"}
[[ -x $yt_dlp ]] || fail '缺少 yt-dlp。请按 README 安装，或将可执行文件加入 PATH。'
ffmpeg=$(command -v ffmpeg || true)
ffmpeg=${ffmpeg:-"$tools_dir/bin/ffmpeg"}
[[ -x $ffmpeg ]] || fail '缺少 FFmpeg，请运行 sudo apt install ffmpeg 或按 README 准备静态构建。'

mkdir -p -- "$output_dir" || fail "无法创建输出目录：$output_dir"
staging=$(mktemp -d -- "$output_dir/.bilibili-download.XXXXXX") || fail "无法在输出目录创建临时目录：$output_dir"
trap 'rm -r -- "$staging"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

url="https://www.bilibili.com/video/$bvid/?p=$part"
formats='30015[height=360]+30216/bv[height=360][ext=mp4]+ba[ext=m4a]/b[height=360][ext=mp4]'
if ! "$yt_dlp" --ignore-config --no-playlist --newline \
  --socket-timeout 20 --retries 2 --ffmpeg-location "$ffmpeg" \
  -f "$formats" --merge-output-format mp4 \
  -P "$staging" -o "$filename" -- "$url"; then
  fail "$bvid P$part 下载或合并失败。请查看上方日志，确认分 P 存在、匿名可用 360p，且网络正常。"
fi

[[ -s $staging/$filename ]] || fail 'yt-dlp 未生成有效的 MP4 输出文件。'
mv -nT -- "$staging/$filename" "$target" || fail "无法保存成品：$target"
[[ ! -e $staging/$filename ]] || fail "目标文件已存在：$target。请选择其他输出目录。"
printf '下载完成：%s\n' "$target"
