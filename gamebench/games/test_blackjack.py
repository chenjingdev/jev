"""블랙잭 정답 계산기 손 검사."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import game_rng  # noqa: E402
from games import blackjack as B  # noqa: E402


def test_totals():
    assert B.total_str(['A', '4', '7'], B.STANDARD) == '12'     # 11로 세면 22 > 21
    assert B.total_str(['A', '4', '7'], B.BUST23) == '22'       # 22 <= 23
    assert B.total_str(['Q', 'A', '6'], B.STANDARD) == '17'
    assert B.total_str(['5', 'A', 'Q', '6'], B.STANDARD) == B.BUST   # 22
    assert B.total_str(['A', 'A', '9'], B.STANDARD) == '21'     # 11 + 1 + 9


def test_outcome():
    # 플레이어 17, 딜러 22 → 21 기준 딜러 버스트, 23 기준 딜러 22가 이긴다
    assert B.outcome(['7', '7', '3'], ['4', '4', '4', '4', '6'], B.STANDARD) == '플레이어 승'
    assert B.outcome(['7', '7', '3'], ['4', '4', '4', '4', '6'], B.BUST23) == '딜러 승'
    assert B.outcome(['8', 'K'], ['9', '9'], B.STANDARD) == '무승부'
    assert B.outcome(['K', '6', '9'], ['K', '6', '9'], B.STANDARD) == '딜러 승'   # 플레이어 버스트가 먼저


def test_dealer_draws():
    # 8, 8 = 16: 17 기준이면 5를 더 받아 21, 16 기준이면 멈춘다
    assert B.total_str(B.dealer_play(['8', '8'], ['5', 'Q'], B.STANDARD), B.STANDARD) == '21'
    assert B.total_str(B.dealer_play(['8', '8'], ['5', 'Q'], B.STAND16), B.STAND16) == '16'
    # A, 6 = 17 (A를 11로) → 멈춘다
    assert B.dealer_play(['A', '6'], ['5'], B.STANDARD) == ['A', '6']


def test_ev_decisions():
    # 소프트 13(A, 2)은 한 장을 받아도 버스트하지 않고 합이 13 아래로 내려가지 않는다 → 받는다
    assert B.decision(['A', '2'], '10', B.STANDARD)[0] == '카드를 받는다'
    # 20은 A가 아니면 모두 버스트 → 멈춘다
    assert B.decision(['10', '10'], '6', B.STANDARD)[0] == '멈춘다'
    # 딜러가 A 한 장이면 받는 최종 분포 확률 합은 1
    assert abs(sum(q for _, q in B.dealer_dist(1, True, B.STANDARD)) - 1) < 1e-12


def test_twins_change_answer():
    items = B.generate(game_rng(20260927, B.GAME), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
