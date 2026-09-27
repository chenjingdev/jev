"""Create a local page listing every question Jev got wrong, with the scanned page and Jev's probabilities.

Contains question text and page scans, so it is for local viewing only (not for publishing).
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
JEV = 'jev-1.13.0'
OTHERS = {'gpt-5.6-luna': 'Luna', 'gpt-5.6-terra': 'Terra', 'gpt-5.6-sol': 'Sol'}


def english_page(number):
    # Same fallback as render_report.py for the reused English reading records.
    return 2 if number <= 20 else 3 if number <= 24 else 4 if number <= 28 else 5 if number <= 32 else 6 if number <= 36 else 7 if number <= 40 else 8


def main():
    dataset = json.loads((HERE / 'dataset.json').read_text())
    questions = {q['id']: q for q in dataset['questions']}
    rows = list(csv.DictReader(open(HERE / 'answers.csv')))
    others = {}
    for r in rows:
        if r['model'] in OTHERS:
            others.setdefault(r['id'], {})[OTHERS[r['model']]] = r['selected']
    items = []
    for r in rows:
        if r['model'] != JEV or r['correct'] != 'False':
            continue
        q = questions[r['id']]
        page = q.get('source_page') or (english_page(q['number']) if q['subject'] == 'english' else None)
        image = f"images/{q['subject']}/page-{page:02d}.jpg" if page else None
        if image and not (HERE / image).exists():
            # English reading pages were rendered by build_english_2026.py, not into images/.
            fallback = f"../sources/page-{page}.png"
            image = fallback if (HERE / fallback).exists() else None
        probs = {}
        try:
            res = json.loads(Path(r['result_path']).read_text())
            mapping = res['job']['choice_to_original']
            probs = {mapping[k]: v for k, v in res['job']['response']['probabilities'].items()}
        except (OSError, KeyError, TypeError, ValueError):
            pass
        items.append({
            'id': r['id'], 'subject': q['subject_name'], 'section': q['section'], 'number': q['number'],
            'selected': r['selected'], 'answer': r['answer'], 'points': r['points'],
            'visual': q['has_visual'], 'state': q['state'], 'options': q['options'],
            'probs': probs, 'others': others.get(r['id'], {}), 'image': image, 'page': page,
        })
    html = (HERE / 'wrong_template.html').read_text().replace(
        '__DATA__', json.dumps(items, ensure_ascii=False).replace('</', '<\\/'))
    (HERE / 'jev-wrong.html').write_text(html)
    print(HERE / 'jev-wrong.html', len(items))


if __name__ == '__main__':
    main()
