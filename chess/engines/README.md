# Local chess engines

Sunfish is isolated from the repository's main Python environment because the `sunfish==2026.1` package pins `chess==1.9.4`, while this project uses `chess==1.11.2`.

```sh
uv venv chess/.venv-sunfish --python 3.14
uv pip install --python chess/.venv-sunfish/bin/python sunfish==2026.1
printf 'uci\nisready\nquit\n' | chess/.venv-sunfish/bin/sunfish-uci
```

The virtual environment contains its own `.gitignore` and is not committed. The installed UCI engine is `chess/.venv-sunfish/bin/sunfish-uci`.

Run the initial paired-color smoke match:

```sh
.venv/bin/python chess/engine_match.py \
  --nodes-a 1000 --nodes-b 300 --games 2 \
  --output chess/matches/sunfish-smoke
```

The match runner records per-move engine identity, UCI and SAN moves, elapsed time, reported depth/nodes/score, result, termination reason, final FEN, PGN, and match points.
