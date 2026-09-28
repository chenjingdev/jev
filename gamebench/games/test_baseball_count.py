"""야구 볼카운트 정답 계산기 손 검사."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import game_rng  # noqa: E402
from games import baseball_count as Y  # noqa: E402


def s(t):
    return t.split()


def test_foul_protect():
    # 헛스윙(1S) 파울(2S) 파울(그대로) → 0볼 2스트라이크
    assert Y.result(s('헛스윙 파울 파울'), Y.STANDARD) == '진행 중: 0볼 2스트라이크'
    assert Y.result(s('헛스윙 파울 파울'), Y.FOUL_K) == Y.K


def test_walk():
    assert Y.result(s('볼 볼 볼 볼'), Y.STANDARD) == Y.WALK
    assert Y.result(s('볼 볼 볼'), Y.STANDARD) == '진행 중: 3볼 0스트라이크'
    assert Y.result(s('볼 볼 볼'), Y.BALL3) == Y.WALK


def test_strikeout():
    assert Y.result(s('헛스윙 볼 스트라이크 헛스윙'), Y.STANDARD) == Y.K


def test_full_count():
    # 볼 스트라이크 파울(2S) 볼 파울(그대로) 볼 → 3볼 2스트라이크
    assert Y.result(s('볼 스트라이크 파울 볼 파울 볼'), Y.STANDARD) == '진행 중: 3볼 2스트라이크'


def test_in_play():
    assert Y.result(['볼', '볼', '땅볼 아웃'], Y.STANDARD) == Y.INPLAY
    # 파울 규칙이 바뀌면 두 번째 파울 뒤 공은 던져지지 않았어야 한다
    assert not Y.consistent(s('스트라이크 파울 파울 볼'), Y.FOUL_K)


def test_twins_change_answer():
    items = Y.generate(game_rng(20260927, Y.GAME), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
