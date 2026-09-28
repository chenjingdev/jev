import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_format import build, spell, targets  # noqa: E402
from run_exam import make_job  # noqa: E402


def test_only_criteria_change():
    q, stmts = targets()[0]
    old, new = make_job(q, 0)['request'], build(q, stmts)['request']
    assert new['state'] == old['state']
    assert new['questions']['answer']['instructions'] == old['questions']['answer']['instructions']
    assert list(new['questions']['answer']['criteria']) == list(old['questions']['answer']['criteria'])


def test_spell_lists_included_and_excluded():
    stmts = [('ㄱ', '가'), ('ㄴ', '나'), ('ㄷ', '다')]
    assert spell('ㄱ, ㄷ', stmts) == '옳은 것: ㄱ. 가 / ㄷ. 다 || 옳지 않은 것: ㄴ. 나'
    assert spell('ㄱ, ㄴ, ㄷ', stmts).endswith('옳지 않은 것: 없음')
