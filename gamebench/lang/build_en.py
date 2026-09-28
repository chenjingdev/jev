"""언어 시험 영어본 만들기. lang/PROTOCOL.md 2절.

strings: set/ko.jsonl에서 게임별로 번역할 문자열(한글이 든 것)을 뽑아 translation/strings/<game>.json에 쓴다.
apply:   translation/en/<game>.json(원문 → 번역)을 적용해 set/en.jsonl을 만들고 기계 검사를 한다.
         검사를 모두 통과할 때만 파일을 쓴다. 정답 파일은 읽지 않는다.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
KO = HERE / 'set' / 'ko.jsonl'
EN = HERE / 'set' / 'en.jsonl'
STRINGS = HERE / 'translation' / 'strings'
TRANS = HERE / 'translation' / 'en'
KEYS = {'규칙': 'rules', '상황': 'situation', '표기': 'notation', '판': 'board', '덱': 'deck'}
HANGUL = re.compile('[가-힣ㄱ-ㅎㅏ-ㅣ]')
NUMBER = re.compile(r'\d+(?:\.\d+)?')
COORD = re.compile(r'(?<![A-Za-z])[A-Z]\d{1,2}(?!\d)')


def load(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def fields(item):
    """(자리 이름, 문자열) 목록. 규칙을 먼저 두어 번역자가 용어 정의를 먼저 보게 한다."""
    out = [(f'state.{k}', v) for k, v in item['state'].items()]
    out.append(('question', item['question']))
    out += [(f'option.{n}', o) for n, o in enumerate(item['options'], 1)]
    return out


def cmd_strings():
    items = load(KO)
    STRINGS.mkdir(parents=True, exist_ok=True)
    games = {}
    for it in items:
        g = games.setdefault(it['game'], {'game': it['game'], 'game_name': it['game_name'], 'strings': {}})
        for where, s in fields(it):
            if HANGUL.search(s):
                g['strings'].setdefault(s, set()).add(where.split('.')[0] if where.startswith('option') else where)
    for g in games.values():
        order = sorted(g['strings'].items(), key=lambda kv: (0 if 'state.규칙' in kv[1] else 1))
        g['strings'] = [{'ko': s, 'where': sorted(w)} for s, w in order]
        (STRINGS / f"{g['game']}.json").write_text(json.dumps(g, ensure_ascii=False, indent=1))
    print(len(games), 'games,', sum(len(g['strings']) for g in games.values()), 'strings ->', STRINGS)


def check_pair(ko, en):
    errs = []
    if HANGUL.search(en):
        errs.append('hangul left')
    if Counter(NUMBER.findall(ko)) != Counter(NUMBER.findall(en)):
        errs.append(f'numbers {sorted(NUMBER.findall(ko))} != {sorted(NUMBER.findall(en))}')
    if Counter(COORD.findall(ko)) != Counter(COORD.findall(en)):
        errs.append(f'coords {sorted(COORD.findall(ko))} != {sorted(COORD.findall(en))}')
    if ko.count('\n') != en.count('\n'):
        errs.append(f'newlines {ko.count(chr(10))} != {en.count(chr(10))}')
    return errs


def translate(s, table):
    return table[s] if HANGUL.search(s) else s


def cmd_apply(allow_number_changes):
    items = load(KO)
    problems, out = [], []
    allowed = set(allow_number_changes)
    for it in items:
        path = TRANS / f"{it['game']}.json"
        table = json.loads(path.read_text()) if path.exists() else {}
        for where, s in fields(it):
            if HANGUL.search(s):
                if s not in table:
                    problems.append((it['id'], where, 'missing translation', s[:60]))
                    continue
                for e in check_pair(s, table[s]):
                    if e.startswith('numbers') and s in allowed:
                        continue
                    problems.append((it['id'], where, e, s[:60]))
        if any(p[0] == it['id'] and p[2] == 'missing translation' for p in problems):
            continue
        opts = [translate(o, table) for o in it['options']]
        if len(set(opts)) != len(opts):
            problems.append((it['id'], 'options', 'options collide after translation', ' | '.join(opts)[:120]))
        out.append({**it, 'state': {KEYS[k]: translate(v, table) for k, v in it['state'].items()},
                    'question': translate(it['question'], table), 'options': opts, 'lang': 'en'})
    if problems:
        for p in problems:
            print(*p, sep=' | ')
        print(len(problems), 'problems; set/en.jsonl not written')
        sys.exit(1)
    EN.write_text(''.join(json.dumps(it, ensure_ascii=False) + '\n' for it in out))
    manifest = {'ko.jsonl': hashlib.sha256(KO.read_bytes()).hexdigest(),
                'en.jsonl': hashlib.sha256(EN.read_bytes()).hexdigest(), 'items': len(out)}
    (HERE / 'set' / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(len(out), 'items ->', EN, manifest)


def cmd_check(games):
    """번역자용: 맡은 게임의 번역표만 검사한다(빠진 문자열, 기계 검사, 보기 충돌)."""
    bad = 0
    for game in games:
        todo = json.loads((STRINGS / f'{game}.json').read_text())['strings']
        path = TRANS / f'{game}.json'
        table = json.loads(path.read_text()) if path.exists() else {}
        for s in todo:
            if s['ko'] not in table:
                print(game, 'missing:', s['ko'][:60]); bad += 1
                continue
            for e in check_pair(s['ko'], table[s['ko']]):
                print(game, e, '|', s['ko'][:60]); bad += 1
        extra = set(table) - {s['ko'] for s in todo}
        for s in extra:
            print(game, 'not in strings file:', s[:60]); bad += 1
        for it in load(KO):
            if it['game'] == game and all(o in table or not HANGUL.search(o) for o in it['options']):
                opts = [translate(o, table) for o in it['options']]
                if len(set(opts)) != len(opts):
                    print(game, 'options collide:', ' | '.join(opts)[:120]); bad += 1
    print('ok' if not bad else f'{bad} problems')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['strings', 'check', 'apply'])
    ap.add_argument('--games', nargs='*', default=[])
    ap.add_argument('--allow-number-change', nargs='*', default=[],
                    help='숫자 검사를 건너뛸 원문 (예: "두" → "2"처럼 말로 쓴 수를 숫자로 옮긴 경우). review.json에 사유를 적는다')
    a = ap.parse_args()
    if a.cmd == 'strings':
        cmd_strings()
    elif a.cmd == 'check':
        cmd_check(a.games)
    else:
        cmd_apply(a.allow_number_change)


if __name__ == '__main__':
    main()
