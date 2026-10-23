#!/bin/sh
set -e

echo "ffmpegfyMe container smoke check"

FFMPEG_VERSION="$(ffmpeg -version 2>&1 | head -n 1)"
FFPROBE_VERSION="$(ffprobe -version 2>&1 | head -n 1)"

echo "ffmpeg version: ${FFMPEG_VERSION}"
echo "ffprobe version: ${FFPROBE_VERSION}"

echo "${FFMPEG_VERSION}" | grep -q "5.1.9" || { echo "FAIL: unexpected ffmpeg version"; exit 1; }
echo "${FFPROBE_VERSION}" | grep -q "5.1.9" || { echo "FAIL: unexpected ffprobe version"; exit 1; }

PKG_VERSION="$(dpkg-query -W -f='${Version}' ffmpeg)"
if [ "${PKG_VERSION}" != "7:5.1.9-0+deb12u1" ]; then
    echo "FAIL: ffmpeg package version ${PKG_VERSION} != 7:5.1.9-0+deb12u1"
    exit 1
fi

for dir in /app/in /app/out /app/progress; do
    if [ -d "$dir" ]; then
        echo "OK: mounted runtime path ${dir} exists"
    else
        echo "FAIL: missing mounted runtime path ${dir}"
        exit 1
    fi
done

echo "SMOKE CHECK PASSED"
