set -e
cd ${OUT:-/tmp/bug-hunter-demo}
python3 - <<'PY'
import json, os
st = json.load(open("frames/stamps.json")); t0 = st[0]
os.makedirs("out", exist_ok=True)
for f in os.listdir("out"): os.remove(os.path.join("out", f))
fps = 30; total = st[-1]-t0; k = 0; i = 0; t = 0.0
while t <= total:
    while i+1 < len(st) and st[i+1]-t0 <= t: i += 1
    k += 1; os.link(f"frames/f{i+1:05d}.jpg", f"out/o{k:05d}.jpg"); t += 1/fps
print(k, "frames")
PY
ffmpeg -y -loglevel error -framerate 30 -i out/o%05d.jpg -vf "scale=1920:1080:flags=lanczos,format=yuv420p" -c:v libx264 -preset slow -crf 18 -movflags +faststart demo.mp4
ls -la demo.mp4
