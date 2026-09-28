"""게임 모듈 공통 계약. PROTOCOL.md "게임 모듈 계약" 절.

게임 모듈(games/<name>.py)은 다음을 정의한다.
  GAME: str            # 짧은 영문 id (예: 'rps')
  NAME: str            # 한국어 이름
  FACET: str           # 판단 능력 분류
  def generate(rng: random.Random, per_stage: int) -> list[dict]

generate가 돌려주는 문항(dict):
  id        '<GAME>:<stage>:<번호>'
  game, stage
  state     {'규칙': str, '상황': str, ...}   # 모델이 보는 모든 사실. 정답 힌트 금지
  question  str                               # 문항별 질문 (instructions로 들어간다)
  options   list[str]                         # 2~16개, 서로 다름
  answer    int                               # 1부터. 규칙상 정답이 정확히 하나
  original_answer int (② 변형만)              # 같은 상황을 원래 규칙으로 풀었을 때의 답. answer와 달라야 한다
  twin_of   str (② 변형만)                    # 짝이 되는 원래 규칙 문항 id. 상황·보기가 같다

정답 위치는 make_item이 보기를 섞어 정한다. 단계 이름은 STAGES 중 하나.
"""
import random

STAGES = ('1-판정', '2-변형', '3-한수', '4-앞보기')
MAX_OPTIONS = 16


def make_item(rng: random.Random, game, stage, index, state, question, options, correct, original=None,
              twin_of=None, order=None):
    """보기를 섞고 정답 번호를 붙인다. correct/original은 보기 문자열.
    order를 주면 그 순서를 그대로 쓴다(② 변형이 짝 문항과 같은 보기 순서를 쓰도록)."""
    assert len(set(options)) == len(options), options
    assert 2 <= len(options) <= MAX_OPTIONS, len(options)
    assert correct in options
    opts = list(order) if order is not None else rng.sample(options, len(options))
    assert sorted(opts) == sorted(options)
    item = {'id': f'{game}:{stage}:{index:03d}', 'game': game, 'stage': stage, 'state': state,
            'question': question, 'options': opts, 'answer': opts.index(correct) + 1}
    if original is not None:
        assert original != correct, (game, stage, index, 'twin must change the answer')
        item['original_answer'] = opts.index(original) + 1
        item['twin_of'] = twin_of
    return item
