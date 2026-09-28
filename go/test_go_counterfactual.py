import json
from pathlib import Path
import counterfactual_replay as cf
import jev_go_match as m


def test_identity_with_random_control(tmp_path):
    """Sum of per-decision deltas within a game equals actual minus plain result (deterministic engine)."""
    op = ['E5', 'C3', 'G7', 'C7']
    payload = m.run(tmp_path / 'op-000', level=1, seed=5, selector='random', opening=op)
    plain = m.run(tmp_path / 'plain', level=1, seed=5, selector='none', opening=op)
    jobs = cf.collect_jobs(tmp_path)
    assert jobs
    rows = [cf.job(j) for j in jobs]
    hybrid = payload['engine_a']['name']
    for g, pg in zip(payload['games'], plain['games']):
        hybrid_color = 'black' if g['black'] == hybrid else 'white'
        actual = 1.0 if g['winner'] == hybrid_color else 0.0
        plain_outcome = 1.0 if pg['winner'] == hybrid_color else 0.0
        total = sum(r['delta'] for r in rows if r['game'] == g['game'])
        assert total == actual - plain_outcome
    s = cf.summarize(rows)
    assert s['all_disagreements']['n'] == len(rows)
