"""볼링 점수.

① 판정: 투구 기록이 주어질 때 (가) 특정 프레임 한 칸의 점수, (나) N프레임까지의 누적 점수, (다) 10프레임까지의 총점.
   보기는 흔한 실수(보너스 빠뜨림, 스트라이크 보너스를 한 번만 셈 등)로 만든다.
② 변형: 같은 기록을 "스트라이크 보너스는 다음 한 번의 투구", 또는 "스페어 보너스는 다음 두 번의 투구"로 계산한다.
   답이 바뀌는 경우만 쓴다.
"""
from .common import make_item

GAME = 'bowling'
NAME = '볼링 점수'
FACET = '규칙 판정'

STANDARD = (2, 1)     # (스트라이크 보너스 투구 수, 스페어 보너스 투구 수)
STRIKE1 = (1, 1)
SPARE2 = (2, 2)
KO_NUM = {1: '한', 2: '두'}


def rules_text(rule):
    s, p = rule
    return ('한 게임은 10프레임이다. 1~9프레임에서는 프레임마다 공을 최대 두 번 던진다. '
            '첫 투구에 핀 10개를 모두 쓰러뜨리면 스트라이크이고 그 프레임은 한 번으로 끝난다. '
            '두 번 던져 합이 10이면 스페어다. '
            f'스트라이크 프레임의 점수는 10에 그다음 {KO_NUM[s]} 번의 투구에서 쓰러뜨린 핀 수를 더한 값이다. '
            f'스페어 프레임의 점수는 10에 그다음 {KO_NUM[p]} 번의 투구에서 쓰러뜨린 핀 수를 더한 값이다. '
            '둘 다 아니면 그 프레임의 점수는 두 투구의 핀 수 합이다. 보너스로 더하는 투구는 뒤 프레임들의 투구를 순서대로 센다(10프레임의 추가 투구 포함). '
            '10프레임에서 스트라이크나 스페어가 나오면 공을 더 던져 10프레임에서만 최대 세 번 던지고, '
            '10프레임의 점수는 10프레임에서 쓰러뜨린 핀 수의 합이다. 누적 점수는 1프레임부터 그 프레임까지 점수의 합이다.')


NOTATION = '각 프레임의 투구를 쓰러뜨린 핀 수로 적는다. 예: "10"은 스트라이크 한 번, "7, 3"은 7개 뒤 3개(스페어), "4, 2"는 4개 뒤 2개.'


def frames_to_rolls(frames):
    return [r for f in frames for r in f]


def frame_scores(frames, rule):
    """프레임별 점수. 보너스 투구가 기록에 없으면 None."""
    s, p = rule
    rolls = frames_to_rolls(frames)
    out, pos = [], 0
    for fi, f in enumerate(frames):
        if fi == 9:
            out.append(sum(f))
            break
        if f[0] == 10:
            nb = s
        elif len(f) == 2 and sum(f) == 10:
            nb = p
        else:
            nb = 0
        after = pos + len(f)
        bonus = rolls[after:after + nb]
        out.append(sum(f) + sum(bonus) if len(bonus) == nb else None)
        pos = after
    return out


def cumulative(frames, rule, n):
    sc = frame_scores(frames, rule)[:n]
    assert None not in sc and len(sc) == n
    return sum(sc)


def naive_scores(frames):
    """흔한 실수: 보너스 없이 핀 수만 더한다."""
    return [sum(f) for f in frames]


def rand_frame(rng, tenth=False):
    kind = rng.random()
    if kind < 0.3:
        f = [10]
    elif kind < 0.6:
        a = rng.randint(0, 9)
        f = [a, 10 - a]
    else:
        a = rng.randint(0, 9)
        f = [a, rng.randint(0, 9 - a)]
    if tenth:
        if f[0] == 10:
            b = rng.choice([10, rng.randint(0, 9)])
            c = rng.randint(0, 10) if b == 10 else rng.randint(0, 10 - b)
            f = [10, b, c]
        elif sum(f) == 10:
            f = f + [rng.randint(0, 10)]
    return f


def frame_str(f):
    return ', '.join(str(x) for x in f)


def show(frames):
    return '\n'.join(f'{i + 1}프레임: {frame_str(f)}' for i, f in enumerate(frames))


def generate(rng, per_stage):
    items = []
    n_twin = 0

    def twin(base, rule, orig, correct):
        nonlocal n_twin
        items.append(make_item(rng, GAME, '2-변형', n_twin, dict(base['state'], 규칙=rules_text(rule)),
                               base['question'], base['options'], correct, original=orig, twin_of=base['id'],
                               order=base['options']))
        n_twin += 1

    seen = set()
    idx = tries = 0
    total_items = 2 * per_stage
    while idx < total_items:
        tries += 1
        assert tries < 200000
        kind = idx % 3  # 0: 한 프레임 점수, 1: N프레임까지 누적, 2: 10프레임 총점
        rule2 = STRIKE1 if idx % 2 == 0 else SPARE2
        if kind == 2:
            frames = [rand_frame(rng) for _ in range(9)] + [rand_frame(rng, tenth=True)]
            n = 10
            q = '10프레임까지의 총점은?'
        else:
            n = rng.randint(2, 6)
            # 보너스를 셀 수 있도록 뒤따르는 두 프레임까지 보여 준다
            frames = [rand_frame(rng) for _ in range(n + 2)]
            q = f'{n}프레임의 점수는?' if kind == 0 else f'{n}프레임까지의 누적 점수는?'
        key = (kind, n, str(frames))
        if key in seen:
            continue
        if kind == 0:
            a = frame_scores(frames, STANDARD)[n - 1]
            t = frame_scores(frames, rule2)[n - 1]
            mistakes = [sum(frames[n - 1]), frame_scores(frames, STRIKE1)[n - 1], frame_scores(frames, SPARE2)[n - 1]]
        else:
            a, t = cumulative(frames, STANDARD, n), cumulative(frames, rule2, n)
            mistakes = [sum(naive_scores(frames)[:n]), cumulative(frames, STRIKE1, n), cumulative(frames, SPARE2, n),
                        a + 10, cumulative(frames, STANDARD, n - 1)]
        if a is None or t is None:
            continue
        want_twin = idx % 4 != 3
        if want_twin != (a != t):
            continue
        # 한 프레임 문항은 스트라이크나 스페어 프레임을 묻는다
        if kind == 0 and sum(frames[n - 1]) < 10:
            continue
        opts = []
        for v in [a, t] + mistakes + [a - 1, a + 1]:
            if v is not None and v >= 0 and str(v) not in opts:
                opts.append(str(v))
        opts = opts[:5]
        if len(opts) < 4:
            continue
        seen.add(key)
        state = {'규칙': rules_text(STANDARD), '표기': NOTATION, '상황': show(frames)}
        base = make_item(rng, GAME, '1-판정', idx, state, q, opts, str(a))
        items.append(base)
        if a != t:
            twin(base, rule2, str(a), str(t))
        idx += 1
    return items
