"""지뢰찾기 정답 계산기 검사. 기대값은 규칙 문구대로 손으로 추론했다."""
from build import game_rng
from games import minesweeper as ms


def test_counts():
    mines = {(1, 0), (1, 2)}               # B1, B3
    assert ms.count(mines, 3, 3, 0, 1, 8) == 2   # A2: 대각선 B1, B3
    assert ms.count(mines, 3, 3, 0, 1, 4) == 0   # A2의 4방향: A1, A3, B2
    assert ms.count(mines, 3, 3, 1, 1, 4) == 2   # B2의 좌우


def test_safe_eight_vs_four():
    # A: 1 1 ?
    # B: ? ? ?
    nums = {(0, 0): 1, (0, 1): 1}
    # 8방향: A1의 1은 B1·B2 중 하나 → A2의 1도 그걸로 채워져 A3·B3은 안전
    assert ms.safe_cells(2, 3, nums, 8) == {(0, 2), (1, 2)}
    # 4방향: A1의 1은 B1(지뢰 확정), A2의 1은 A3·B2 중 하나, B3은 아무 숫자와도 안 닿음 → 확실히 안전한 칸 없음
    assert ms.safe_cells(2, 3, nums, 4) == set()


def test_zero_and_inconsistent():
    # 2×2, A1=0: 8방향이면 나머지 셋 안전, 4방향이면 B2는 닿지 않아 모른다
    assert ms.safe_cells(2, 2, {(0, 0): 0}, 8) == {(0, 1), (1, 0), (1, 1)}
    assert ms.safe_cells(2, 2, {(0, 0): 0}, 4) == {(0, 1), (1, 0)}
    # 1×2, A1=2: 이웃 닫힌 칸이 하나뿐 → 가능한 배치 없음
    assert ms.safe_cells(1, 2, {(0, 0): 2}, 8) is None


def test_generated_example_by_hand():
    # A: ? ? ? 0 / B: ? 3 1 ? / C: 2 ? ? 1 / D: 1 ? ? ? / E: ? ? ? ? / F: ? ? 1 ?
    # C1=2는 B1·C2·D2 중 둘, D1=1은 C2·D2·E1·E2 중 하나 → C2·D2가 둘 다 지뢰일 수 없으니 B1 지뢰,
    # C2·D2 중 하나 → E1·E2 안전
    nums = {(0, 3): 0, (1, 1): 3, (1, 2): 1, (2, 0): 2, (2, 3): 1, (3, 0): 1, (5, 2): 1}
    safe = ms.safe_cells(6, 4, nums, 8)
    assert (4, 0) in safe and (4, 1) in safe and (2, 1) not in safe


def test_twins_differ_only_in_rule():
    items = ms.generate(game_rng(20260927, ms.GAME), 10)
    by_id = {x['id']: x for x in items}
    for x in items:
        assert not any(w in x['state']['규칙'] for w in ('원래', '변형', '바뀐'))
        if x['stage'] == '2-변형':
            t = by_id[x['twin_of']]
            assert x['state']['판'] == t['state']['판'] and x['state']['규칙'] != t['state']['규칙']
            assert x['answer'] != x['original_answer'] == t['answer']
