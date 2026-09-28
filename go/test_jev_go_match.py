import json
import pytest
from gnugo import GnuGo, shortlist
import jev_go_match as m


def test_shortlist_margin_and_cap():
    rows = [{'move': 'E5', 'value': 10.0}, {'move': 'D4', 'value': 9.0}, {'move': 'F6', 'value': 8.5},
            {'move': 'C3', 'value': 8.1}, {'move': 'A1', 'value': 1.0}]
    assert shortlist(rows, 2.0) == ['E5', 'D4', 'F6']
    assert shortlist(rows, 0.5) == ['E5']
    assert shortlist([], 2.0) == []


def test_ranked_moves_puts_base_first_and_is_seeded():
    with GnuGo(level=1) as e:
        base1, rows1 = e.ranked_moves('black')
        base2, rows2 = e.ranked_moves('black')
        assert base1 == base2 and rows1 == rows2
        assert rows1[0]['move'] == base1 and rows1[0]['rank'] == 1
        assert len({r['move'] for r in rows1}) == len(rows1)
        assert 'I' not in ''.join(r['move'][0] for r in rows1)


def test_request_hides_engine_information():
    with GnuGo(level=1) as e:
        e.play('black', 'E5')
        req = m.make_request(e, 'white', ['D4', 'F6'], 7, 2, 'E5')
    text = json.dumps(req)
    for banned in ('value', 'rank', 'base', 'genmove', 'top_moves'):
        assert banned not in text
    assert req['state']['stones'] == {'E5': 'black'}
    assert set(req['questions']['move']['criteria']) == {'D4', 'F6'}
    assert req['state']['side_to_move'] == 'white'


def test_result_for_rejects_draw():
    assert m.result_for('W+7.5') == ('white', 7.5)
    assert m.result_for('B+0.5') == ('black', 0.5)
    with pytest.raises(ValueError):
        m.result_for('0')


def test_confidence_gate_keeps_jev_answer(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, timeout=None): pass
        def close(self): pass

    def fake_ask(client, request, base):
        options = list(request['questions']['move']['criteria'])
        other = next(o for o in options if o != base)
        calls.append(other)
        return {'base_move': base, 'selected_move': other, 'intervention': True, 'enabled': True,
                'latency_ms': 1.0, 'confidence': 0.1, 'candidates': [], 'request': request,
                'response': {'model': 'x', 'answers': {}, 'usage': {'input_tokens': 1, 'output_tokens': 1}}}
    monkeypatch.setattr(m, 'TypeSafeClient', FakeClient)
    monkeypatch.setattr(m, 'ask_jev', fake_ask)
    payload = m.run(tmp_path / 'gate', level=1, seed=3, selector='jev', min_confidence=0.4)
    decisions = [mv['jev'] for g in payload['games'] for mv in g['moves'] if mv.get('jev')]
    assert decisions and all(d['gated'] and not d['intervention'] for d in decisions)
    assert all(d['selected_move'] == d['base_move'] and d['jev_move'] != d['base_move'] for d in decisions)
    assert payload['summary']['gated'] == len(decisions) == payload['summary']['jev_disagreed']
    for g in payload['games']:
        assert g['winner'] in ('black', 'white')


def test_replay_reproduces_engine_moves():
    """Replaying the move list with the same queries at every ply reproduces genmove. (Position
    alone is not always enough: GNU Go's persistent caches make rare positions history-dependent,
    which is why counterfactual_replay mimics the match's query sequence.)"""
    with GnuGo(level=1, seed=99) as a:
        color = 'black'
        moves = []
        for _ in range(30):
            base, _rows = a.ranked_moves(color)
            if base == 'PASS':
                break
            a.play(color, base)
            moves.append((color, base))
            color = 'white' if color == 'black' else 'black'
    with GnuGo(level=1, seed=99) as b:
        for col, mv in moves:
            assert b.ranked_moves(col)[0] == mv
            b.play(col, mv)


def test_ranked_moves_only_lists_legal_alternatives():
    with GnuGo(level=1) as e:
        # Build a ko: black E5 D4 F4 E3 (E4 empty), white D5 F5 E6 ... simpler: replay a known ko sequence.
        for color, v in [('black', 'D5'), ('white', 'E5'), ('black', 'E4'), ('white', 'F4'), ('black', 'E6'),
                         ('white', 'F6'), ('black', 'F5'), ('white', 'G5')]:
            e.play(color, v)
        # white just took at G5? Not necessarily a ko; whatever the position, every listed move must be legal.
        for color in ('black', 'white'):
            base, rows = e.ranked_moves(color)
            for r in rows:
                assert e.is_legal(color, r['move']), r
