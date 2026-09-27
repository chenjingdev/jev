"""원카드 정답 계산기 손 검사."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import game_rng  # noqa: E402
from games import onecard as O  # noqa: E402


def c(t):
    return O.JOKER if t == '조커' else (t[1:], t[0])


def hand(t):
    return [c(x) for x in t.split()]


def test_playable_normal():
    # ♣3 위: ♥4 ♦6 ♥7 ♠5 는 무늬도 숫자도 다르다 → 없음. 색 규칙이면 검정인 ♠5.
    hd = hand('♥4 ♦6 ♥7 ♠5')
    assert O.only_playable(O.STANDARD, hd, c('♣3'), False, '없음') == '없음'
    assert O.only_playable(O.COLOR, hd, c('♣3'), False, '없음') == '♠5'


def test_rank_only():
    # ♣J 위 ♣9만 무늬가 같다. 숫자만 보는 규칙에서는 없음.
    hd = hand('♣9 ♦8 ♠Q ♥2 ♠K')
    assert O.only_playable(O.STANDARD, hd, c('♣J'), False, '없음') == '♣9'
    assert O.only_playable(O.RANK, hd, c('♣J'), False, '없음') == '없음'


def test_block():
    # ♠2 공격: ♥A는 더 세지만 무늬·숫자가 안 맞다 → 못 막음. 아무 공격 카드나 막는 규칙이면 ♥A.
    hd = hand('♥3 ♥A ♥5')
    assert O.only_playable(O.STANDARD, hd, c('♠2'), True, '없음') == '없음'
    assert O.only_playable(O.ANY, hd, c('♠2'), True, '없음') == '♥A'
    # ♠A 공격 위에 ♥2는 약해서 못 내고 조커만 된다
    assert O.only_playable(O.STANDARD, hand('♠6 조커 ♥2 ♥10'), c('♠A'), True, '없음') == '조커'


def test_stack():
    seq = hand('♣2 조커')
    assert O.stack_total(O.STANDARD, seq) == 7    # 2 + 5
    assert O.stack_total(O.SWAP_AMT, seq) == 8    # 3 + 5
    assert O.stack_total(O.STANDARD, hand('♥A ♦A ♠A 조커')) == 14


def test_spoil():
    # ♠K 위. ♠3을 내면 ♦A는 무늬·숫자 모두 안 맞다. ♦K를 내면 ♦A가 무늬로 맞는다.
    hd = hand('♥9 ♣9 ♠3 ♦K')
    assert O.spoil_answer(O.STANDARD, hd, c('♠K'), c('♦A')) == '♠3'
    # 숫자 규칙: 낼 수 있는 건 ♦K뿐이고, 그 위에 ♦A는 숫자가 달라 못 낸다
    assert O.spoil_answer(O.RANK, hd, c('♠K'), c('♦A')) == '♦K'
    # 조커를 내면 다음 사람은 공격을 받아 일반 카드 ♥7을 낼 수 없다
    assert O.spoil_answer(O.STANDARD, hand('조커 ♥K ♥2 ♦5 ♥6'), c('♠6'), c('♥7')) == '조커'


def test_twins_change_answer():
    items = O.generate(game_rng(20260927, O.GAME), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
