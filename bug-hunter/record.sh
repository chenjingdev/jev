#!/bin/sh
# Record the demo: a chromeless Chrome window on the main display running the
# page's own demo mode (?demo=1), captured with macOS screencapture at 30fps.
# The watch server must be up on :3458 (SIF_CACHE=0 so the counters are real)
# with demo.py in its clean state.
set -e
OUT=${OUT:-/tmp/bug-hunter-demo}; mkdir -p "$OUT"
open -na "Google Chrome" --args --app="http://localhost:3458/?demo=1" --window-size=1280,748 --window-position=200,120 \
  --user-data-dir="$OUT/chrome-profile" --no-first-run --no-default-browser-check
sleep 2.5
PID=$(pgrep -f "Google Chrome --app=" | head -1)
osascript -e "tell application \"System Events\" to tell (first process whose unix id is $PID) to set frontmost to true"
screencapture -x -v -V ${SECONDS_TO_RECORD:-46} -R 200,148,1280,720 "$OUT/take.mov"
kill "$PID"
ffmpeg -y -loglevel error -ss ${TRIM_START:-2.0} -to ${TRIM_END:-39.5} -i "$OUT/take.mov" \
  -vf "scale=1920:1080:flags=lanczos,format=yuv420p" -r 30 -c:v libx264 -preset slow -crf 18 -movflags +faststart "$OUT/demo.mp4"
echo "$OUT/demo.mp4"
