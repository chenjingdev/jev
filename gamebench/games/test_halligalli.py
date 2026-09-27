"""할리갈리 정답 계산기 손 검사."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import game_rng  # noqa: E402
from games import halligalli as H  # noqa: E402


def test_ring_five():
    # 딸기 3 + 딸기 2 = 5
    assert H.should_ring([('딸기', 3), ('바나나', 4), ('딸기', 2)], 5) == '예'
    assert H.which_fruit([('딸기', 3), ('바나나', 4), ('딸기', 2)], 5) == '딸기'


def test_no_ring_six():
    # 라임 4 + 라임 2 = 6, 바나나 3 → 다섯인 과일 없음
    assert H.should_ring([('라임', 4), ('라임', 2), ('바나나', 3)], 5) == '아니오'
    assert H.which_fruit([('라임', 4), ('라임', 2), ('바나나', 3)], 5) == H.NONE


def test_four_rule():
    cards = [('바나나', 5), ('딸기', 2), ('딸기', 4)]  # 바나나 5, 딸기 6
    assert H.should_ring(cards, 5) == '예'
    assert H.should_ring(cards, 4) == '아니오'
    assert H.which_fruit([('자두', 1), ('자두', 3), ('라임', 5)], 4) == '자두'


def test_new_card_covers_old():
    # 나의 바나나 3이 가려진다. 바나나 5를 펼치면 바나나 5 → 종. 바나나 2는 3이 가려져 바나나 2뿐.
    cards = [('라임', 4), ('라임', 2), ('바나나', 3)]
    assert H.hit_fruits(H.after_play(cards, 2, ('바나나', 5)), 5) == ['바나나']
    assert H.hit_fruits(H.after_play(cards, 2, ('바나나', 2)), 5) == []


def test_twins_change_answer():
    items = H.generate(game_rng(20260927, H.GAME), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
