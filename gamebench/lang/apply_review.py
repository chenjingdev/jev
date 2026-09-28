"""검토 지적 반영. lang/PROTOCOL.md 6번.

translation/review/<game>.json의 지적 중 must-fix·should-fix(대안 번역이 있는 것)는 반영하고, note는
translation/decisions.json의 accept_notes에 사유와 함께 적은 것만 반영한다. reject에 적은 지적은 사유와 함께
반영하지 않는다. 모든 지적과 처리 결과를 translation/review.json에 남긴다. 번역표(en/<game>.json)를 고친다.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = HERE / 'translation'


def main():
    decisions = json.loads((T / 'decisions.json').read_text())
    reject, accept_notes = decisions.get('reject', {}), decisions.get('accept_notes', {})
    log = []
    for path in sorted((T / 'review').glob('*.json')):
        review = json.loads(path.read_text())
        game = review['game']
        table_path = T / 'en' / f'{game}.json'
        table = json.loads(table_path.read_text())
        for issue in review['issues']:
            key = f"{game}|{issue['ko']}"
            entry = {'game': game, **{k: issue.get(k) for k in ('severity', 'type', 'ko', 'en', 'suggested_en', 'explanation')}}
            if issue['ko'] not in table:
                raise SystemExit(f'{key}: not in translation table')
            if table[issue['ko']] != issue['en'] and table[issue['ko']] != issue.get('suggested_en'):
                raise SystemExit(f'{key}: translation changed since review')
            if key in reject:
                entry.update(decision='not applied', reason=reject[key])
            elif issue.get('suggested_en') is None:
                entry.update(decision='not applied', reason='no replacement proposed')
            elif issue['severity'] in ('must-fix', 'should-fix'):
                table[issue['ko']] = issue['suggested_en']
                entry.update(decision='applied', reason=f"reviewer {issue['severity']}")
            elif key in accept_notes:
                table[issue['ko']] = issue['suggested_en']
                entry.update(decision='applied', reason=accept_notes[key])
            else:
                entry.update(decision='not applied', reason='note; reviewer said no change needed')
            log.append(entry)
        table_path.write_text(json.dumps(table, ensure_ascii=False, indent=1) + '\n')
    (T / 'review.json').write_text(json.dumps(log, ensure_ascii=False, indent=1) + '\n')
    applied = sum(e['decision'] == 'applied' for e in log)
    print(f'{len(log)} issues, {applied} applied, {len(log) - applied} not applied -> {T / "review.json"}')


if __name__ == '__main__':
    main()
