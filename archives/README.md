# archives

용량이 크거나 파일 수가 많은 원자료를 묶은 것. 저장소 루트에서 풀면 원래 경로에 그대로 풀린다.

```sh
for f in archives/*.tar.gz; do tar xzf "$f"; done
```

| 파일 | 내용 |
|---|---|
| `csat-bench-results.tar.gz` | `csat/bench/results/*/<시스템>/`: 지식 벤치마크(2027 9월 모평) 호출별 기록 40,107개 |
| `gamebench-results.tar.gz` | `gamebench/results/*/<시스템>/`: 판단 벤치마크 호출별 기록과 로그 29,942개 |
| `gamebench-lang-results.tar.gz` | `gamebench/results/lang-en/`, `lang-ko-rerun/`: 언어 시험 호출별 기록 5,552개와 로그 13개 |
| `csat-all_subjects-results.tar.gz` | `csat/all_subjects/results/<모델>/`: 2026 수능 전과목 호출 기록 3,536개 |
| `csat-prompt_study-development.tar.gz` | `csat/prompt_study/development/<변형>/`: 지시문 비교 호출 기록 3,536개 |
| `chess-matches-full.tar.gz` | `chess/matches/*.json` 중 2MB 넘는 대국 통합 기록 15개(수별 Jev 확률 포함) |

채점 스크립트(`score.py`, `report.py`)는 풀린 폴더를 읽는다. 요약 결과(`report.json`, `scores.json`, PGN, 심판 결과)는 풀지 않아도 저장소에 있다.

체스·바둑의 판별 폴더(`chess/matches/<대국>/`, `go/matches/<대국>/`)는 통합 JSON의 `games`와 같은 내용이라 넣지 않았다.
