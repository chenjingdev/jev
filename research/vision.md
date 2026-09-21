# 시각 입력 전용 Jev 같은 것

조사일 2026-09-19. Jev 자체는 `state`가 문자열·매핑·리스트뿐이라 이미지를 못 받는다(`experiments/vision` 참고: 글자로 철자하면 names/rgb/hex는 읽지만 base64는 우연 수준).
그래서 "시각 정보에 최적화된 Jev"는 전부 오픈소스 쪽에 있고, 지금까지 찾은 것은 둘이다.

## openvons.vision — https://github.com/genai-craft/openvons (스타 7, 일본)

가장 Jev스럽게 시각을 다룬 것. 정리 문서 `docs/vision_summary.md`가 본체다.

**구조**: Qwen3-VL-2B의 **시각 인코더만** 떼어 얼리고(407M) 그 위에 **2.5만 파라미터짜리 head**만 학습. 이미지를 한 번 임베딩하면 질문 몇 개든 head만 돌린다.
변형으로 "2B VLM 얼림 + 210만 파라미터 head"도 있다.

**속도** (RTX PRO 6000, bf16, 이미지 1장 4문항)
| 구성 | 파라미터 | VRAM | 4문항 응답 |
|---|---:|---:|---:|
| 시각 인코더 + head | 407M | 1.5 GB | 8.8 ms |
| 2B VLM 얼림 + head | 2.13B | 4.8 GB | 32 ms |
| Qwen3-VL-2B zero-shot | 2.13B | 4.8 GB | 81 ms |
| Qwen3.8-27B zero-shot | 27.4B | 52.1 GB | 314 ms |

27B 대비 VRAM 1/34, 속도 36배. 폰 데모에서는 이미지 임베딩 260~290 ms, 9문항 답변 11 ms.

**정확도**
| 과제 | 27B zero-shot | 인코더 + head | 참고 |
|---|---:|---:|---|
| FairFace 나이 9구간 | 0.522 | 0.597 | 지도학습 ResNet34 0.595 |
| FairFace 성별 | 0.941 | 0.946 | ResNet34 0.945 |
| PA-100K 보행자 방향 | 0.831 | 0.827 | |
| PA-100K 소지품 | 0.599 | 0.834 | |
| PA-100K 연령 3구간 macro F1 | 0.491 | 0.590 | 클래스 가중치 필수 |

보정: 학습한 구성은 전부 ECE 0.008~0.035. zero-shot 소형 모델은 ECE 0.37~0.60 (확신 0.35짜리 예측이 0.7%만 맞음).

**저자 요점 5개**
1. 27B zero-shot은 407M + 2.5만 파라미터로 대체된다.
2. 학습 안 한 소형 모델은 **순서 척도(나이 등)에서 붕괴**한다(0.01~0.03). head만 학습하면 0.6. 차이는 "보이느냐"가 아니라 "답하는 법".
3. 전부 학습할 필요 없다. 성별·방향은 zero-shot으로 충분, 소지품·나이는 학습 필수.
4. 질문 추가 비용은 거의 0. 이미지 한 번 읽으면 4문항이든 16문항이든 같다.
5. head만 학습이라 특징 한 번 뽑아 두면 **재학습이 수 초**.

**한계** (저자 명시): 공개 데이터셋 결과이고 실제 카메라(화각·조명·가림)는 미검증. 온디바이스 추론 미구현. 프레임을 동영상으로 묶어 넣으면 토큰이 간벌될 수 있음.

## jev-visual — https://github.com/hr98w/jev-visual (스타 109, Apple Silicon)

Qwen3.5-0.8B-4bit VLM을 MLX로 돌려 이미지 하나에 질문 여러 개(1~64문항, 2~26선택지). `image + context → shared prefill → fork cache → batch question suffixes`.
학습·보정 없음. 확률은 상대 선호이지 정확도 추정이 아니라고 명시. 데모는 분류 공장, Breakout, 카메라 제스처.

**속도**: M4 16GB에서 64판단 독립 채점 37.30 s → 공유 채점 2.40 s. 정확도 평가는 없다("스케일링 실험이지 Jev 비교가 아님").

**솔직한 실패담**: Breakout에서 0.8B가 공을 따라가거나 좌/우를 고르는 걸 못 해서 공을 키우고 패들을 넓히고 속도를 늦춰야 했다. 우리 `tetris/`에서 겪은 것과 같은 종류의 한계.

## 둘의 차이와 시사점

| | openvons.vision | jev-visual |
|---|---|---|
| 백본 | 시각 인코더만 (407M) | 소형 VLM 통째 (0.8B) |
| 학습 | head 2.5만 파라미터 | 없음 |
| 질문 | 학습 때 정한 속성 고정 | 런타임에 자유 |
| 보정 | ECE ≤ 0.035 | 없음 |
| 속도 | 8.8 ms/4문항 (GPU) | 2.4 s/64판단 (M4) |

핵심 갈림길은 **질문을 런타임에 바꿀 수 있느냐**다. openvons는 Jev의 "아무 질문이나" 성질을 포기하고 질문을 고정한 대신 CNN급 정확도와 보정, 8.8 ms를 얻었다. jev-visual은 자유도를 지켰지만 품질 측정도 보정도 없다.
Jev의 "런타임 질문 + 보정된 확률"을 시각에서 그대로 재현한 것은 아직 없다. 텍스트 Jev의 보정을 시각으로 옮기려면 VLM에 CE + Brier로 head를 붙이는 system-one-open 식 레시피가 필요한데 그걸 한 저장소는 못 찾았다.

## 우리와의 연결

- `eye/`가 화면을 격자로 줄여 Jev에 글자로 주는 방식이라면, openvons 식으로 SigLIP/Qwen-VL 인코더 + 작은 head를 로컬에 두고 "input 칸이 어디냐" 같은 고정 질문만 8 ms에 답하게 하는 구성이 가능하다. 학습 데이터는 `experiments/vision`의 grid 생성기를 그대로 쓸 수 있다.
- 다음에 볼 것: openvons `docs/benchmark.md`와 `experiments/*.json`(재현 로그), `openvons/vision/train_vision.py`(head 학습 코드), jev-visual `adapters.py`(MLX에서 KV/순환 상태 재사용).

## 출처
- https://github.com/genai-craft/openvons , https://github.com/genai-craft/openvons/blob/main/docs/vision_summary.md
- https://github.com/hr98w/jev-visual
