"""포커 족보 정답 계산기 손 검사. 기대값은 규칙 문구에서 손으로 따졌다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import game_rng  # noqa: E402
from games import poker_hands as P  # noqa: E402

R = {r: i for i, r in enumerate(P.RANKS)}


def h(text):
    return [(R[c[1:]], c[0]) for c in text.split()]


FH_OVER_FL = P.swapped('풀하우스', '플러시')


def test_categories():
    assert P.category(h('♠5 ♠6 ♠7 ♠8 ♠9'), P.STANDARD) == '스트레이트 플러시'
    assert P.category(h('♠10 ♥J ♦Q ♣K ♠A'), P.STANDARD) == '스트레이트'
    # A-2-3-4-5는 이어진 것이 아니다 → 하이카드
    assert P.category(h('♠A ♥2 ♦3 ♣4 ♠5'), P.STANDARD) == '하이카드'
    assert P.category(h('♣3 ♥3 ♦3 ♣Q ♦Q'), P.STANDARD) == '풀하우스'
    assert P.category(h('♣3 ♥3 ♦Q ♣Q ♦K'), P.STANDARD) == '투페어'


def test_winner_full_house_vs_flush():
    hands = [h('♣3 ♥3 ♦3 ♣Q ♦Q'), h('♥4 ♥5 ♥7 ♥8 ♥9')]
    assert P.winner(hands, P.STANDARD) == 0          # 풀하우스 > 플러시
    assert P.winner(hands, FH_OVER_FL) == 1          # 플러시가 더 높은 순서


def test_weakest_of_three():
    hands = [h('♠2 ♠5 ♥9 ♦J ♣K'), h('♥7 ♦7 ♠8 ♣8 ♥Q'), h('♣6 ♦6 ♥A ♠3 ♦4')]
    # 하이카드 < 원페어 < 투페어
    assert P.winner(hands, P.STANDARD, weakest=True) == 0
    assert P.winner(hands, P.STANDARD) == 1


def test_best_discard():
    hand, new = h('♠5 ♠6 ♠7 ♥8 ♠9'), h('♠4')[0]
    # ♥8을 버리면 ♠4 5 6 7 9 플러시, ♠9를 버리면 4~8 스트레이트. 플러시가 더 높다.
    assert P.best_discards(hand, new, P.STANDARD) == [h('♥8')[0]]
    # 스트레이트가 플러시보다 높은 순서에서는 ♠9를 버린다
    assert P.best_discards(hand, new, P.swapped('플러시', '스트레이트')) == [h('♠9')[0]]


def test_twins_change_answer():
    items = P.generate(game_rng(20260927, P.GAME), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
    assert not any(w in x['state']['규칙'] for x in items for w in ('원래', '변형', '바뀐'))
