# Jev 오픈소스 복제본 카탈로그

조사일 2026-09-19. 출처는 각 저장소 README와 https://github.com/hellogumbo/awesome-jev . 수치는 각 저장소가 스스로 보고한 것이다.
"읽음"은 README를 읽었다는 뜻이고 코드는 보지 않았다. 항목별 상세(속도·성능·후기)는 `replicas-detail.md`.

## 읽음

| 이름 | 베이스 | 학습 | 병렬화 | 보고 수치 | 비고 |
|---|---|---|---|---|---|
| [system-one-open](https://github.com/mithalouni/system-one-open) | Gemma 4 E2B(attention LoRA), Gemma 3 270M | CE + Brier, temperature scaling. HF 92개 + 합성 | 슬롯 logit, 옵션 52개/패스 | TypeSafe eval 343쌍 76.7% (Jev 86.9%, 미학습 Qwen 7B 73.8%), H100 27질문 97ms, 이메일 74.6통/s | MIT. Modal 서빙. 가장 재현 가능한 학습 레시피 |
| [SemIf (구 openjev)](https://github.com/TheoLeeCJ/openjev) | Qwen3-0.6B Q8, MiniCPM5-2B Q4, Qwen3.5-4B Q4 | 없음 | suffix 재사용 | 102행 modal agreement 0.845 (Jev는 balanced accuracy 0.883, 지표 다름), 3090 단일 1.02s, 777판단 20/s | 가장 별 많은 독립 복제본. "모델·학습은 재현 안 함" 명시 |
| [NanoJev](https://github.com/TianyuCodings/NanoJev) | Qwen3-0.6B + decision heads | 3단계(init→헤드 워밍업→전체), distribution loss | 한 forward에 44 candidate path, 후보 2~255 동적 | 안전 77.84% test / 76.56% OOD, 미로 4×4 95% | 데이터 생성→학습→평가 파이프라인 전부 공개 |
| [jevfire](https://github.com/kikoncuo/jevfire) | Qwen3.8-27B-FP8 (vLLM), 브라우저는 Qwen3.5-0.8B WebLLM | 없음 | 공유 prefix + 필드별 접미, KV cache 재사용 | 28판단 497ms(제약 JSON 대비 10.3×), warm prefix 12필드 255ms, M4 Max 71ms/판단 | 확률은 "상대 선호이지 보정 확신도 아님" 명시 |
| [qwen-rlcd](https://github.com/shamazharikh/qwen-rlcd) | Qwen3.5-0.8B-Base (Gated DeltaNet 18 + attention 6) | 계획만. RLCD = proper scoring rule 보상 | prefix fork (`system_one/fork.py`) | fork vs 순차 오차 4.8e-5 | 하이브리드 모델에서 tree mask가 안 되는 이유와 대안이 문서화돼 있음 |
| [Verdict-open-jev](https://github.com/Heman10x-NGU/Verdict-open-jev) | ModernBERT-base 151M | CE + 1.0·Brier, L-BFGS temperature scaling(T=1.4265) | 인코더, 후보 슬롯 25(기권 1 포함) | Banking77 95.0%, Brier 0.0756, ECE 1.13%→보정 후 3.35%(악화), <35ms | 유일한 인코더 접근. 도메인 하나 |

## 안 읽음 (awesome-jev 기준 한 줄)

| 이름 | 한 줄 |
|---|---|
| [decider](https://github.com/Mapika/decider) | Qwen3.5-2B 파인튜닝, one-pass 보정 확률 |
| [reflex](https://github.com/kshetrajna12/reflex) | Qwen3.5 위 작은 판단 모델 |
| [jevlike](https://github.com/vinnylarouge/jevlike) | 텍스트 옵션 중 고르는 작은 모델 학습 |
| [system-one-gemma](https://github.com/akash-kamat/system-one-gemma) | Gemma 3 270M + scoring head |
| [jevbetter](https://github.com/olonotolu/jevbetter) | 가변 텍스트 옵션 위 attention scorer |
| [litjev](https://github.com/zhengxuyu/litjev) | 임의 Qwen을 판단 모델로 |
| [mini-jev](https://github.com/r-ms/mini-jev) | frozen Qwen3-4B logit |
| [jev-on-a-laptop](https://github.com/rorshopping/jev-on-a-laptop) | 1.5B~8B 스톡 모델 병렬 판단 연구 |
| [open-alternative-jev](https://github.com/ikermoel/open-alternative-jev) | HF + vLLM |
| [typesafe-local](https://github.com/aabolfazl/typesafe-local) | 로컬 LLM에 typed 질문 |
| [system-one](https://github.com/sgoedecke/system-one) | 배치 단일 토큰 선택, TypeSafe 호환 |
| [decisionbridge](https://github.com/grishahq/decisionbridge) | 기존 LLM용 판단 인터페이스 |
| [open-jev (daseinlabs)](https://github.com/daseinlabs/open-jev) | Gemma 3 4B, MLX |
| [jevmlx](https://github.com/bnsd55/jevmlx) | 임의 MLX 모델 병렬 제약 판단 |
| [jev-visual](https://github.com/hr98w/jev-visual) | Apple Silicon 시각 입력, 공유 컨텍스트 채점 |
| [openjev (razorback16)](https://github.com/razorback16/openjev) | DiffusionGemma 판단 서버 |
| [open-jev (JoshuaSP)](https://github.com/JoshuaSP/open-jev) | DiffusionGemma typed JSON |
| [openjev (zhihz)](https://github.com/zhihz/openjev) | 이중 언어 로컬 확률 판단 |
| [openvons](https://github.com/genai-craft/openvons) | 텍스트/이미지/음성 입력, 일본어 |
| [system-one-adapter-rust](https://github.com/codeitlikemiley/system-one-adapter-rust) | 공식 어댑터 Rust 포트 |

## 큐레이션 목록

- https://github.com/hellogumbo/awesome-jev
- https://github.com/ozers/jevsome-projects — 실제로 Jev를 호출하는 코드 줄까지 링크, 매일 갱신
- https://github.com/cobanov/awesome-jev , https://github.com/yibie/awesome-jev , https://github.com/devx-opensource/awesome-typesafe
