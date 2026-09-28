"""369 게임.

규칙 문구는 DIGITS(박수를 치는 숫자)에서 만들고, 풀이기도 같은 숫자를 읽는다.
① 판정: 수 N 차례에 할 행동(수를 그대로 말한다 / 짝 / 짝짝 / 짝짝짝), 또는 보기 수 중 박수를 k번 치는 수.
② 변형: 같은 상황·보기에서 박수를 치는 숫자가 2, 5, 8인 규칙. 답이 달라지는 문항만 짝으로 쓴다.
③·④: 이 게임에는 수 선택이 없어 만들지 않는다.
"""
from .common import make_item

GAME = 'game369'
NAME = '369'
FACET = '규칙 판정'

STD, ALT = '369', '258'
ACTIONS = ['수를 그대로 말한다', '짝', '짝짝', '짝짝짝']
COUNT_Q = {0: '보기 중 박수를 치지 않고 수를 그대로 말해야 하는 수는?',
           1: '보기 중 박수를 정확히 한 번 쳐야 하는 수는?',
           2: '보기 중 박수를 정확히 두 번 쳐야 하는 수는?'}


def rules_text(digits):
    d = ', '.join(digits)
    return (f'여러 사람이 돌아가며 1부터 차례로 수를 하나씩 말한다. 말할 수에 숫자 {d} 중 하나라도 들어 있으면 '
            f'수를 말하지 않고, 수에 들어 있는 {d}의 개수만큼 "짝" 하고 손뼉을 친다. '
            f'{d} 중 어느 것도 들어 있지 않으면 수를 그대로 말한다.')


def claps(digits, n):
    return sum(c in digits for c in str(n))


def action(digits, n):
    return ACTIONS[claps(digits, n)]


def with_count(digits, nums, k):
    hs = [str(n) for n in nums if claps(digits, n) == k]
    return hs[0] if len(hs) == 1 else None


def pick_number(rng, want_change):
    while True:
        n = rng.randint(10, 999) if rng.random() < 0.4 else rng.randint(10, 99)
        if (action(STD, n) != action(ALT, n)) == want_change:
            return n


def pick_options(rng, k, want_change):
    while True:
        nums = rng.sample(range(10, 100), 4)
        a, b = with_count(STD, nums, k), with_count(ALT, nums, k)
        if a is None:
            continue
        if want_change and b is not None and b != a:
            return nums
        if not want_change and b == a:
            return nums


def generate(rng, per_stage):
    items = []
    std, alt = rules_text(STD), rules_text(ALT)
    k = 0
    for i in range(2 * per_stage):
        want_change = i % 5 != 4  # 다섯에 하나는 짝 없는 문항(두 규칙에서 답이 같다)
        if i % 2 == 0:
            n = pick_number(rng, want_change)
            sit, q, opts = f'앞사람까지 차례대로 했고, 이제 내 차례다. 순서상 내 수는 {n}이다.', '나는 어떻게 해야 하는가?', ACTIONS
            ans, twin = action(STD, n), action(ALT, n)
        else:
            c = rng.choice([0, 1, 2] if want_change else [0, 1])  # 두 자리에서 두 번은 두 규칙이 겹칠 수 없다
            nums = pick_options(rng, c, want_change)
            sit, q, opts = '아래 보기는 게임 중에 말할 차례가 올 수 있는 수들이다.', COUNT_Q[c], [str(x) for x in nums]
            ans, twin = with_count(STD, nums, c), with_count(ALT, nums, c)
        base = make_item(rng, GAME, '1-판정', i, {'규칙': std, '상황': sit}, q, opts, ans)
        items.append(base)
        if twin is not None and twin != ans:
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': alt, '상황': sit}, q, opts, twin,
                                   original=ans, twin_of=base['id'], order=base['options']))
            k += 1
    return items
