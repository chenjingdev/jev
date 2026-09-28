"""Thin GTP wrapper around GNU Go for the 9x9 selector experiment.

GNU Go is deterministic, but its answer depends on the position AND on its query history
(persistent reading caches): replaying a game's moves with `play` alone reproduces genmove in
most positions, not all. A faithful replay must issue the same queries the original run did
(see counterfactual_replay.branch). The startup --seed does not change genmove; it only
perturbs the ordering of near-equal alternatives in top_moves.
"""
from __future__ import annotations
import subprocess

COLS = 'ABCDEFGHJKLMNOPQRST'  # GTP skips the letter I


class GnuGo:
    def __init__(self, level=1, boardsize=9, komi=7.5, seed=1, binary='gnugo'):
        self.level, self.boardsize, self.komi, self.seed = level, boardsize, komi, seed
        self.proc = subprocess.Popen(
            [binary, '--mode', 'gtp', '--boardsize', str(boardsize), '--komi', str(komi),
             '--chinese-rules', '--capture-all-dead', '--never-resign', '--level', str(level), '--seed', str(seed)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def cmd(self, text):
        self.proc.stdin.write(text + '\n')
        self.proc.stdin.flush()
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if line == '':
                raise RuntimeError(f'GnuGo exited during: {text}')
            if line == '\n' and lines:
                break
            if line.strip():
                lines.append(line.rstrip('\n'))
        reply = ' '.join(lines)
        if not reply.startswith('='):
            raise RuntimeError(f'GTP error for {text!r}: {reply}')
        return reply[1:].strip()

    def close(self):
        try:
            self.cmd('quit')
        except Exception:
            pass
        self.proc.terminate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- game state -----------------------------------------------------
    def play(self, color, vertex):
        self.cmd(f'play {color} {vertex}')

    def stones(self, color):
        out = self.cmd(f'list_stones {color}')
        return sorted(out.split()) if out else []

    def captures(self, color):
        return int(self.cmd(f'captures {color}'))

    def final_score(self):
        return self.cmd('final_score')

    def showboard(self):
        return self.cmd('showboard')

    def is_legal(self, color, vertex):
        return self.cmd(f'is_legal {color} {vertex}') == '1'

    # --- engine queries ---------------------------------------------------
    def ranked_moves(self, color):
        """Engine's own move plus its valued alternatives.

        Returns (base, rows): base is what reg_genmove would play ('PASS' possible); rows are
        [{'move', 'value', 'rank'}] with the base first. top_moves may omit or reorder the
        genmove choice (genmove applies extra filters), so the base is inserted at rank 1
        carrying the top value; the selector never sees values or ranks anyway.
        Deterministic given the same position and the same query history (see module docstring).
        """
        base = self.cmd(f'reg_genmove {color}').upper()
        raw = self.cmd(f'top_moves_{color}').split()
        rows = [{'move': raw[i].upper(), 'value': float(raw[i + 1])} for i in range(0, len(raw), 2)]
        if base == 'PASS' or base == 'RESIGN':
            return 'PASS', []
        # top_moves can list a move genmove would never play (e.g. a ko retake); drop illegal ones.
        rows = [r for r in rows if r['move'] == base or self.is_legal(color, r['move'])]
        top_value = rows[0]['value'] if rows else 0.0
        rows = [r for r in rows if r['move'] != base]
        rows.insert(0, {'move': base, 'value': top_value})
        for i, r in enumerate(rows, 1):
            r['rank'] = i
        return base, rows


def shortlist(rows, margin, limit=3):
    if not rows:
        return []
    best = rows[0]['value']
    return [r['move'] for r in rows if best - r['value'] <= margin][:limit]
