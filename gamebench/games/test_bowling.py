"""볼링 점수 정답 계산기 손 검사."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import game_rng  # noqa: E402
from games import bowling as W  # noqa: E402


def test_strike_frame():
    f = [[9, 1], [1, 4], [3, 5], [10], [10], [8, 0]]
    assert W.frame_scores(f, W.STANDARD)[3] == 28     # 10 + 10 + 8
    assert W.frame_scores(f, W.STRIKE1)[3] == 20      # 10 + 10
    assert W.frame_scores(f, W.STANDARD)[0] == 11     # 스페어 10 + 1


def test_cumulative():
    f = [[10], [10], [9, 0], [3, 4]]
    # 1: 10+10+9=29, 2: 10+9+0=19, 3: 9 → 57
    assert W.cumulative(f, W.STANDARD, 3) == 57
    # 스트라이크 보너스 한 번: 1: 20, 2: 19, 3: 9 → 48
    assert W.cumulative(f, W.STRIKE1, 3) == 48


def test_spare_two():
    f = [[6, 4], [3, 5], [0, 0]]
    assert W.frame_scores(f, W.STANDARD)[0] == 13     # 10 + 3
    assert W.frame_scores(f, W.SPARE2)[0] == 18       # 10 + 3 + 5


def test_perfect_game():
    f = [[10]] * 9 + [[10, 10, 10]]
    assert W.cumulative(f, W.STANDARD, 10) == 300


def test_tenth_frame():
    f = [[0, 0]] * 8 + [[10], [7, 3, 5]]
    # 9프레임: 10 + 7 + 3 = 20, 10프레임: 15 → 35
    assert W.cumulative(f, W.STANDARD, 10) == 35
    assert W.cumulative(f, W.STRIKE1, 10) == 32       # 9프레임 17


def test_twins_change_answer():
    items = W.generate(game_rng(20260927, W.GAME), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
