# 갈래 수 한계 실험

`sif.decide()`(Jev Choice)가 선택지 수를 늘릴 때 어디서 무너지는지 잰 실험. 2026-09-17, `jev-1.13.0`.

## 설계

- 한국어 고객 문의 20개 카테고리 × 정답이 명확한 문장 4개 = 80문장
- 갈래 수 N ∈ {2, 3, 5, 8, 12, 20}, 앞에서 N개 카테고리를 뽑고 그 문장만 평가
- 조건: A 기본(이름+영어 설명), B 이름만, C 순서 섞기 3회, D 익명 키(A/B/C), E 재현 2회
- 모든 호출은 질문 1개짜리 단독 `decide`. 묶어 보내면 분포가 달라지므로.
- 1,600회 호출, 입력 1,022,276 + 출력 228,772 토큰, $0.05, 454초

## 결과 한 줄

20갈래까지 1,600건 전부 정답. 순서 섞기와 반복에서 선택이 바뀐 경우 0건.

- 1,564건은 정답 확률이 정확히 1.00
- 확률이 흔들린 건 N=20에서만, 최대 표준편차 0.015
- 설명을 뺀 B 조건만 약해짐. 최솟값 0.66(리뷰 작성 문의 → 사용법 질문)
- 의심이 생기면 거의 항상 "사용법 질문"이 2위로 등장
- 입력 토큰은 N=2에서 약 370, N=20에서 약 870. 갈래 수에 비례
- latency 중앙값 255ms, p95 446ms
- API는 확률을 소수 둘째 자리로 반올림해 돌려줌. 그 아래 차이는 볼 수 없음

이 데이터셋은 모델을 무너뜨리지 못했다. 한계를 보려면 경계가 애매한 문장이나 20개 넘는 갈래가 필요하다.

## 실행

```sh
uv run python experiments/branches/run.py --dry-run   # 호출 수·토큰 예상만
op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
  -- uv run python experiments/branches/run.py         # results.json에 이어하기
uv run python experiments/branches/report.py            # summary.md 재생성
```

## 주의: sif 캐시 키는 선택지 순서를 무시한다

`sif.cache.make_key`가 `sort_keys=True`로 직렬화하므로 선택지 순서만 다른 두 호출은 같은 캐시를 맞는다.
순서 효과를 재려면 `sif.configure(cache=False)`로 돌려야 한다. 요청 본문 자체는 순서를 유지해 API에 전달된다.
이 실험 결과 순서가 선택을 바꾸지 않았으므로 캐시 키는 그대로 둔다.
