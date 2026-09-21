#!/bin/sh
# Record a game: a chromeless Chrome window on the main display in recording mode
# (?clean=1, fast speed, fixed seed), captured with macOS screencapture at 30fps. Records for
# SECONDS_TO_RECORD (generous), then trims to the game's real end (TRIM_END, or found from the
# server log, so start the server with its output in SERVER_LOG) and cuts three files: the whole game (full.mp4), a
# time-lapse (demo.mp4) and the last minute in real time (ending.mp4). Server must be up on :3462.
#
#   op run --env-file=.env.tpl -- npm start > /tmp/jev-2048-server.log 2>&1 &
#   SECONDS_TO_RECORD=360 SEED=1001 SPEEDUP=3 ./record.sh
#   QUERY="clean=1&speed=fast&replay=seed-1001" SECONDS_TO_RECORD=400 TRIM_END=382 SPEEDUP=6 ./record.sh
#
# Same recipe as bug-hunter/record.sh; the CDP screencast route (tetris/record.mjs) drops
# frames unevenly and looks jerky, so it is not used here.
set -e
OUT=${OUT:-/tmp/jev-2048-demo}; mkdir -p "$OUT"
SEED=${SEED:-1001}
SERVER_LOG=${SERVER_LOG:-/tmp/jev-2048-server.log}
# QUERY overrides the page: e.g. QUERY="clean=1&speed=fast&replay=seed-1001" plays a saved game
# (public/replays/) without calling Jev; then pass TRIM_END yourself, there are no server moves.
QUERY=${QUERY:-"clean=1&speed=fast&seed=$SEED"}
W=1440; H=900; X=200; Y=120
open -na "Google Chrome" --args --app="http://localhost:3462/?$QUERY" \
  --window-size=$W,$((H + 28)) --window-position=$X,$Y \
  --user-data-dir="$OUT/chrome-profile" --no-first-run --no-default-browser-check
sleep 2.5
PID=$(pgrep -f "Google Chrome --app=" | head -1)
osascript -e "tell application \"System Events\" to tell (first process whose unix id is $PID) to set frontmost to true"
python3 -c 'import time; print(time.time())' > "$OUT/start.txt"
# screencapture stalls silently (empty file, never returns) if the display sleeps mid-capture,
# so keep it awake for the take
caffeinate -d -t $(( ${SECONDS_TO_RECORD:-240} + 30 )) &
screencapture -x -v -V ${SECONDS_TO_RECORD:-240} -R $X,$((Y + 28)),$W,$H "$OUT/take.mov"
kill "$PID"
# where the game ended: the server logs a timestamp per move; the last one + 3s is the end
END=${TRIM_END:-$(python3 - "$OUT/start.txt" "$SERVER_LOG" <<'PY'
import sys, re, subprocess
# seconds from capture start to the last move logged by the server
start = float(open(sys.argv[1]).read())
log = subprocess.run(["tail", "-n", "3000", sys.argv[2]], capture_output=True, text=True).stdout
ts = [float(m.group(1)) for m in re.finditer(r"^t=(\d+\.\d+) move#", log, re.M)]
last = max((t for t in ts if t > start), default=None)
print(f"{last - start + 3:.1f}" if last else "")
PY
)}
TO=${END:+-to $END}
# whole game
ffmpeg -y -loglevel error -ss ${TRIM_START:-1.5} $TO -i "$OUT/take.mov" \
  -vf "scale=1920:1200:flags=lanczos,format=yuv420p" -r 30 -c:v libx264 -preset slow -crf 18 -movflags +faststart "$OUT/full.mp4"
# time-lapse: every frame kept, played SPEEDUP× faster. Every slide in it is a real Jev answer.
ffmpeg -y -loglevel error -i "$OUT/full.mp4" \
  -vf "setpts=PTS/${SPEEDUP:-3}" -r 30 -an -c:v libx264 -preset slow -crf 18 -movflags +faststart "$OUT/demo.mp4"
# the last minute in real time, where the arrows are readable
ffmpeg -y -loglevel error -sseof -60 -i "$OUT/full.mp4" -c copy -movflags +faststart "$OUT/ending.mp4"
echo "$OUT/full.mp4"
echo "$OUT/demo.mp4"
echo "$OUT/ending.mp4"
