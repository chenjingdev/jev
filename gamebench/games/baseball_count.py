"""야구 볼카운트.

① 판정: 한 타석의 투구 결과가 순서대로 주어질 때 타석이 어떻게 되었는가(볼넷 / 삼진 / 타격으로 끝남 / 진행 중이면 볼카운트).
② 변형: "볼 세 개면 볼넷", "파울도 언제나 스트라이크로 센다(세 번째 스트라이크면 삼진)". 같은 기록에서 답이 바뀌는 경우만 쓴다.
   두 규칙 모두에서 타석이 마지막 공보다 먼저 끝나지 않는 기록만 쓴다(끝난 뒤에 공을 더 던지는 모순이 없도록).
"""
from .common import make_item

GAME = 'baseball_count'
NAME = '야구 볼카운트'
FACET = '규칙 판정'

STANDARD = {'balls': 4, 'foul': 'protect'}
BALL3 = {'balls': 3, 'foul': 'protect'}
FOUL_K = {'balls': 4, 'foul': 'strike'}

PITCHES = ['볼', '스트라이크', '헛스윙', '파울', '땅볼 아웃', '안타']
W = [34, 22, 14, 22, 4, 4]
WALK, K = '볼넷', '삼진'
INPLAY = '공을 쳐서 타석이 끝남'


def rules_text(rule):
    nb = {4: '네', 3: '세'}[rule['balls']]
    foul = ('파울은 스트라이크가 0개나 1개일 때만 스트라이크 하나로 세고, 스트라이크가 2개일 때는 카운트가 바뀌지 않는다.'
            if rule['foul'] == 'protect' else '파울은 언제나 스트라이크 하나로 센다.')
    return ('한 타석은 볼카운트 0볼 0스트라이크에서 시작한다. 투구 결과는 볼, 스트라이크, 헛스윙, 파울, 땅볼 아웃, 안타 중 하나다. '
            f'볼은 볼 하나다. 스트라이크와 헛스윙은 스트라이크 하나다. {foul} '
            f'볼이 {nb} 개가 되면 볼넷으로 타석이 끝나고, 스트라이크가 세 개가 되면 삼진으로 타석이 끝난다. '
            '땅볼 아웃이나 안타가 나오면 공을 쳐서 타석이 끝난 것이다.')


def count_str(b, s):
    return f'진행 중: {b}볼 {s}스트라이크'


def play(seq, rule):
    """(결과, 끝난 투구 번호). 진행 중이면 번호는 None."""
    b = s = 0
    for i, p in enumerate(seq):
        if p == '볼':
            b += 1
        elif p in ('스트라이크', '헛스윙'):
            s += 1
        elif p == '파울':
            if rule['foul'] == 'strike' or s < 2:
                s += 1
        else:
            return INPLAY, i
        if b >= rule['balls']:
            return WALK, i
        if s >= 3:
            return K, i
    return count_str(b, s), None


def result(seq, rule):
    return play(seq, rule)[0]


def consistent(seq, rule):
    """타석이 마지막 공보다 먼저 끝나지 않는다."""
    _, end = play(seq, rule)
    return end is None or end == len(seq) - 1


def generate(rng, per_stage):
    items = []
    n_twin = 0
    q = '이 투구들이 끝난 뒤 타석은 어떻게 되었는가?'
    seen = set()
    idx = tries = 0
    while idx < 2 * per_stage:
        tries += 1
        assert tries < 200000
        seq = rng.choices(PITCHES, W, k=rng.randint(3, 9))
        key = tuple(seq)
        rule2 = BALL3 if idx % 2 == 0 else FOUL_K
        if key in seen or not consistent(seq, STANDARD):
            continue
        a = result(seq, STANDARD)
        want_twin = idx % 4 != 3
        t = result(seq, rule2) if consistent(seq, rule2) else None
        has_twin = t is not None and t != a
        if want_twin != has_twin:
            continue
        if not want_twin and a == INPLAY and idx % 8 != 7:
            continue  # 타격으로 끝나는 기록은 조금만
        seen.add(key)
        # 보기: 두 규칙의 답, 끝나는 세 결과, 비슷한 볼카운트 몇 개
        b = seq.count('볼')
        s_all = sum(p in ('스트라이크', '헛스윙', '파울') for p in seq)
        near = [count_str(min(b, 3), min(s_all, 2)), count_str(max(b - 1, 0), 2), count_str(min(b, 3), 1),
                count_str(3, 2), count_str(2, 2)]
        opts = []
        for v in [a] + ([t] if has_twin else []) + [WALK, K, INPLAY] + near:
            if v not in opts:
                opts.append(v)
        opts = opts[:7]
        state = {'규칙': rules_text(STANDARD), '상황': '투구 결과(순서대로): ' + ', '.join(seq)}
        base = make_item(rng, GAME, '1-판정', idx, state, q, opts, a)
        items.append(base)
        if has_twin:
            items.append(make_item(rng, GAME, '2-변형', n_twin, dict(state, 규칙=rules_text(rule2)), q, base['options'], t,
                                   original=a, twin_of=base['id'], order=base['options']))
            n_twin += 1
        idx += 1
    return items
