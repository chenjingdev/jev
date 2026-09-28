"""윷놀이 정답 계산기 손 검사."""
import random

from games import yut as g


def test_outer_path():
    assert g.dest(0, 1, 'standard') == 1          # 판 밖에서 도 → 1번
    assert g.dest(3, 3, 'standard') == 6          # 3에서 걸 → 6
    assert g.dest(4, 2, 'standard') == 6          # 5번을 지나가기만 하면 바깥 길


def test_shortcuts():
    assert g.dest(5, 3, 'standard') == 23         # 5→21→22→23
    assert g.dest(5, 3, 'noshort') == 8
    assert g.dest(10, 4, 'standard') == 24        # 10→26→27→23→24
    assert g.dest(22, 5, 'standard') == g.OUT     # 23·24·25·20 네 칸뿐이라 다섯 칸이면 난다


def test_home():
    assert g.dest(17, 3, 'standard') == 20        # 18·19·20 딱 맞게 도착하면 20번에 선다
    assert g.dest(17, 3, 'arrive') == g.OUT       # 도착만으로 나는 규칙
    assert g.dest(18, 3, 'standard') == g.OUT     # 지나치면 난다
    assert g.dest(20, 1, 'standard') == g.OUT     # 20번에 선 말은 무엇이 나와도 난다


def test_capture_one_piece():
    mine = {'가': 14, '나': 5}
    theirs = {9, 17, 25}
    # 모: 가는 19, 나는 5→21→22→23→24→25로 25번의 상대 말을 잡는다.
    assert not g.captures(mine, theirs, '가', '모', 'standard')
    assert g.captures(mine, theirs, '나', '모', 'standard')
    # 지름길이 없으면 나는 10번으로 가 못 잡는다.
    assert not g.captures(mine, theirs, '나', '모', 'noshort')


def test_order_matters():
    # 3번 말에 개 먼저면 5번에 멈춘 뒤 걸로 지름길 23번. 걸 먼저면 6→8.
    assert g.two_step(3, '개', '걸', {23}, 'standard')
    assert not g.two_step(3, '걸', '개', {23}, 'standard')
    assert g.two_step(3, '걸', '개', {6}, 'standard')   # 첫 번째로 멈춘 칸에서도 잡는다


def test_twins_change_answer():
    items = g.generate(random.Random(7), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
