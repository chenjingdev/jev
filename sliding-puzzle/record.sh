#!/bin/sh
# Record the demo: a chromeless Chrome window on the main display running the page's own
# demo mode (?demo=1&depth=14), captured with macOS screencapture at 30fps - the same
# recipe as bug-hunter/record.sh (CDP screencast frames were uneven there).
# The server must be up on :3459, started with SIF_CACHE=0 so every request is real.
#   sliding-puzzle/record.sh                  # writes $OUT/take.mov and $OUT/demo.mp4
#   DEPTH=16 SECONDS_TO_RECORD=60 TRIM_END=52 sliding-puzzle/record.sh
set -e
OUT=${OUT:-/tmp/sliding-puzzle-demo}; mkdir -p "$OUT"
open -na "Google Chrome" --args --app="http://127.0.0.1:3459/?demo=1&depth=${DEPTH:-14}" --window-size=1280,748 --window-position=200,120 \
  --force-dark-mode --user-data-dir="$OUT/chrome-profile" --no-first-run --no-default-browser-check
sleep 3
PID=$(pgrep -f "Google Chrome --app=http://127.0.0.1:3459" | head -1)
osascript -e "tell application \"System Events\" to tell (first process whose unix id is $PID) to set frontmost to true"
screencapture -x -v -V ${SECONDS_TO_RECORD:-50} -R 200,148,1280,720 "$OUT/take.mov"
osascript -e 'tell application "Google Chrome" to get title of front window' > "$OUT/title.txt" 2>/dev/null || true
kill "$PID"
cat "$OUT/title.txt" 2>/dev/null
ffmpeg -y -loglevel error -ss ${TRIM_START:-1.5} -to ${TRIM_END:-45} -i "$OUT/take.mov" \
  -vf "scale=1920:1080:flags=lanczos,format=yuv420p" -r 30 -c:v libx264 -preset slow -crf 18 -movflags +faststart "$OUT/demo.mp4"
echo "$OUT/demo.mp4"
