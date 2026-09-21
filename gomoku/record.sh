#!/bin/sh
# Record the demo: a chromeless Chrome window on the main display running the
# page's demo mode (?demo=1: the engine bot plays black, Jev plays white),
# captured with macOS screencapture at 30fps - the bug-hunter recipe.
# The server must be up on :3460.
set -e
OUT=${OUT:-/tmp/gomoku-demo}; mkdir -p "$OUT"; rm -f "$OUT/take.mov"
open -na "Google Chrome" --args --app="http://localhost:3460/?demo=1" --window-size=1280,748 --window-position=200,120 \
  --user-data-dir="$OUT/chrome-profile" --no-first-run --no-default-browser-check
sleep 2.5
PID=$(pgrep -f "Google Chrome --app=http://localhost:3460" | head -1)
# keep the window in front for the whole take - other windows on this Mac may pop up meanwhile
( while kill -0 "$PID" 2>/dev/null; do
    osascript -e "with timeout of 2 seconds" -e "tell application \"System Events\" to tell (first process whose unix id is $PID) to set frontmost to true" -e "end timeout" &
    sleep 1
  done ) >/dev/null 2>&1 &
FRONT=$!
screencapture -x -v -V ${SECONDS_TO_RECORD:-70} -R 200,148,1280,720 "$OUT/take.mov"
kill "$PID"; kill "$FRONT" 2>/dev/null || true
ffmpeg -y -loglevel error -ss ${TRIM_START:-1.5} -to ${TRIM_END:-61.5} -i "$OUT/take.mov" \
  -vf "scale=1920:1080:flags=lanczos,format=yuv420p" -r 30 -c:v libx264 -preset slow -crf 18 -movflags +faststart "$OUT/demo.mp4"
echo "$OUT/demo.mp4"
