"""Five ways to push `sif.decide` past the point where it answered perfectly.

The branch-count experiment (`experiments/branches`) got 1,600/1,600 on twenty
categories with unambiguous sentences. This dataset keeps the same domain -
Korean customer support, Korean category name + one English line - and varies
five things instead:

1. width      - 80 categories, nested N in {20, 40, 60, 80}, 2 clear sentences each
2. neighbors  - eight families of four categories a single word apart
3. ambiguous  - sentences that straddle two categories, with a human expectation
4. length     - one clear inquiry buried in unrelated Korean policy text
5. traps      - one clear answer, misleading surface cues

Categories 1-20 are the branch experiment's twenty, verbatim and in order, so
`categories_for(20)` is that dataset's option list and every N nests.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Mapping, Sequence

# ------------------------------------------------------------------ constants

#: One instruction for axes 1, 2, 3 and 5, identical to the branch experiment.
INSTRUCTIONS = "Classify this Korean customer support message into exactly one category."

#: Axis 4 has to say the inquiry is buried somewhere in the state.
LONG_INSTRUCTIONS = (
    "Classify the customer inquiry contained in the text into exactly one category."
)

#: Axis 1 branch counts; each takes the first N categories. Past 80 the extra
#: branches are out-of-domain distractors: no sentence of the dataset belongs to
#: them, so the gold answer always stays inside the first eighty. 255 is the
#: documented maximum number of Choice options.
N_VALUES: tuple[int, ...] = (20, 40, 60, 80, 150, 255)

#: Categories that carry evaluation sentences; the rest are distractors.
REAL_CATEGORIES = 80

#: Axis 3 repeats the same call this many times with the cache off.
AMBIGUOUS_REPEATS = 3

#: Axis 4 state sizes in tokens (the state text alone, not the whole request).
LENGTH_TIERS: tuple[int, ...] = (1000, 4000, 12000, 24000)

#: Where the inquiry sits inside the filler; only the top tier gets all three.
POSITIONS: tuple[str, ...] = ("front", "middle", "end")

#: If the top tier is rejected (the 32k state ceiling is unconfirmed), retry here.
LENGTH_FALLBACK_TIER = 16000

#: Input-token model fitted on the 1,600 real `usage.input_tokens` of
#: experiments/branches/results.json (mean absolute error 4.0 tokens, max 25.9).
TOKEN_BASE = 259.376
TOKEN_PER_KOREAN_CHAR = 1.2282
TOKEN_PER_OTHER_CHAR = 0.2845


@dataclass(frozen=True)
class Category:
    """A branch: the Korean label the model returns, its gloss and its family."""

    name: str
    description: str
    family: str


@dataclass(frozen=True)
class Sample:
    """One message with its single correct category."""

    id: str
    text: str
    gold: str


@dataclass(frozen=True)
class Ambiguous:
    """A message that spans two categories, with the split a human would give."""

    id: str
    text: str
    expected: Mapping[str, float]


@dataclass(frozen=True)
class Trap:
    """A message with one correct answer and a misleading surface cue."""

    id: str
    kind: str
    text: str
    gold: str


# ----------------------------------------------------------------- categories

#: Positions 1-20 are the branch experiment's categories, byte for byte.
CATEGORIES: tuple[Category, ...] = (
    Category("환불", "Customer wants money back for an item or service already paid for or received.", "refund"),
    Category("취소 요청", "Customer wants an order or a booking cancelled before it ships or starts.", "order"),
    Category("배송 지연", "Customer complains that the package is late or past its promised date.", "delivery"),
    Category("배송지 변경", "Customer wants the delivery address or recipient of an order changed.", "delivery"),
    Category("배송 조회", "Customer asks where the package is now or how to track it.", "delivery"),
    Category("제품 불량", "Customer reports the item arrived broken, damaged or not working.", "product"),
    Category("사이즈 교환", "Customer wants to swap the item for a different size of the same product.", "product"),
    Category("재고 문의", "Customer asks whether an item is in stock or when it will be restocked.", "product"),
    Category("결제 오류", "Customer reports a failed, duplicated or wrongly charged payment.", "payment"),
    Category("쿠폰/할인", "Customer asks about coupons, promo codes, points or discount conditions.", "promo"),
    Category("회원 탈퇴", "Customer wants to close or delete their membership account.", "account"),
    Category("비밀번호 재설정", "Customer cannot sign in and needs a password reset or account unlock.", "account"),
    Category("영수증/세금계산서", "Customer asks for a receipt, tax invoice or other proof-of-purchase document.", "record"),
    Category("리뷰 작성 문의", "Customer asks how to write, edit or delete a product review.", "record"),
    Category("칭찬", "Customer thanks the company or praises the product, packaging or staff.", "misc"),
    Category("욕설/불만 표출", "Customer vents anger or insults without asking for any specific action.", "misc"),
    Category("대량 구매 문의", "Customer asks about buying a large quantity or placing a corporate order.", "misc"),
    Category("제휴 제안", "Another business proposes a partnership, sponsorship or reselling deal.", "misc"),
    Category("사용법 질문", "Customer asks how to use, clean, install or operate the product.", "product"),
    Category("기타 잡담", "Off-topic small talk unrelated to any support request.", "misc"),
    # --- 21-40: the closest neighbours of the first twenty
    Category("환불 지연", "A refund was already approved or promised but the money has not arrived yet.", "refund"),
    Category("오배송", "A different item, a wrong option or somebody else's order was delivered.", "delivery"),
    Category("반품 접수", "Customer wants to send an item back and asks for the return to be registered.", "refund"),
    Category("부분 배송", "Only part of one order arrived and the remaining items are still missing.", "delivery"),
    Category("결제 수단 변경", "Customer wants to pay for an existing order with a different card or method.", "payment"),
    Category("로그인 오류", "Signing in fails with an error although the password itself is known to be right.", "account"),
    Category("색상/옵션 변경", "Customer wants a different colour or option of the same product, not a different size.", "product"),
    Category("적립금 문의", "Customer asks about reward points earned, missing or about to expire.", "promo"),
    Category("반품 정책 문의", "Customer asks what the return rules and deadlines are without returning anything yet.", "policy"),
    Category("고객센터 연결 요청", "Customer asks to reach a human agent, or for the call centre's number and hours.", "misc"),
    Category("부분 환불", "Customer wants money back for only some items or only part of the amount.", "refund"),
    Category("배송비 문의", "Customer asks how much shipping costs or when shipping is free.", "delivery"),
    Category("환불 수단 변경", "Customer wants the refund paid to a different card, bank account or method.", "refund"),
    Category("해외 배송 문의", "Customer asks about shipping abroad, customs duties or overseas delivery time.", "delivery"),
    Category("정기결제 해지", "Customer wants a subscription's recurring charge stopped from renewing.", "payment"),
    Category("개인정보 변경", "Customer wants the phone number, email or name saved on the account changed.", "account"),
    Category("구성품 누락", "A part or accessory listed as box contents is missing from a delivered item.", "product"),
    Category("이벤트 응모 문의", "Customer asks how to enter an event or draw, or when winners are announced.", "promo"),
    Category("교환 정책 문의", "Customer asks what the exchange rules and deadlines are without requesting one.", "policy"),
    Category("앱 오류 신고", "Customer reports the app or web site crashing, freezing or showing an error.", "misc"),
    # --- 41-60
    Category("반품 배송비 문의", "Customer asks who pays the return shipping fee and how much it is.", "refund"),
    Category("택배사 변경 요청", "Customer asks for the order to be handed to a different courier company.", "delivery"),
    Category("주문 수량 변경", "Customer wants the ordered quantity of an existing order raised or lowered.", "order"),
    Category("새벽배송 요청", "Customer asks for dawn or same-day delivery instead of standard delivery.", "delivery"),
    Category("무이자 할부 문의", "Customer asks about instalment plans or interest-free months on a card payment.", "payment"),
    Category("회원가입 문의", "Customer asks how to sign up or why creating an account is being rejected.", "account"),
    Category("상품 스펙 문의", "Customer asks about a product's measurements, material, weight or specification.", "product"),
    Category("멤버십 등급 문의", "Customer asks how membership tiers are decided and what each tier gives.", "promo"),
    Category("보증/AS 정책 문의", "Customer asks about the warranty period or how paid repairs are charged.", "policy"),
    Category("매장 정보 문의", "Customer asks for an offline store's address, opening hours or parking.", "misc"),
    Category("취소 수수료 문의", "Customer asks how large the cancellation penalty is before deciding.", "order"),
    Category("부재중 재배송 요청", "Delivery failed because nobody was home and the customer asks for another attempt.", "delivery"),
    Category("주문 내역 확인", "Customer asks what a particular order contained or what its order number is.", "order"),
    Category("배송 일정 지정 요청", "Customer asks for delivery on a specific future date or time window.", "delivery"),
    Category("가상계좌 입금 확인", "Customer paid by bank transfer and asks whether the deposit has registered.", "payment"),
    Category("휴면 계정 해제", "An account went dormant from disuse and the customer wants it reactivated.", "account"),
    Category("정품 확인 요청", "Customer asks whether the item is genuine or how to verify authenticity.", "product"),
    Category("가격 인하 보상 문의", "The price dropped after purchase and the customer asks for the difference back.", "promo"),
    Category("환불 정책 문의", "Customer asks what the refund rules and timelines are without requesting one.", "policy"),
    Category("채용 문의", "A job seeker asks about hiring, open positions or an application.", "misc"),
    # --- 61-80
    Category("반품 회수 일정 문의", "Customer asks when the courier will collect the item that is being returned.", "refund"),
    Category("배송 기사 불만", "Customer complains about the delivery driver's behaviour or how the parcel was left.", "delivery"),
    Category("취소 상태 확인", "Customer already cancelled and asks whether the cancellation went through.", "order"),
    Category("방문 수령 문의", "Customer asks to pick the order up in person at a store or warehouse.", "delivery"),
    Category("해외 결제 수수료 문의", "Customer asks about foreign-currency charges or overseas card fees.", "payment"),
    Category("계정 정지 문의", "The account was suspended or restricted and the customer asks why.", "account"),
    Category("호환성 문의", "Customer asks whether the product works with another device, model or part.", "product"),
    Category("사은품 문의", "Customer asks about a free promotional gift attached to a purchase.", "promo"),
    Category("개인정보 처리방침 문의", "Customer asks how personal data is kept, shared or destroyed by the company.", "policy"),
    Category("구매 이력 확인", "Customer asks for a list of past purchases over some period of time.", "record"),
    Category("예약 일정 변경", "Customer wants a booked visit, installation or appointment moved to another time.", "order"),
    Category("배송 완료 오표시", "Tracking says delivered but the customer never received the parcel.", "delivery"),
    Category("결제 승인 취소 확인", "Customer asks whether a card authorisation was voided and when it disappears.", "payment"),
    Category("마케팅 수신 설정 변경", "Customer wants marketing texts, emails or push notifications turned on or off.", "account"),
    Category("유통기한 문의", "Customer asks about the expiry date, manufacture date or shelf life.", "product"),
    Category("친구 초대 리워드 문의", "Customer asks about the referral reward for inviting a friend.", "promo"),
    Category("이용약관 문의", "Customer asks what a clause of the terms of service means.", "policy"),
    Category("상담 이력 확인", "Customer asks for the record or outcome of an earlier support conversation.", "record"),
    Category("미성년자 구매 정책 문의", "Customer asks about the rules for purchases by minors or guardian consent.", "policy"),
    Category("분실/파손 배송 사고 접수", "Customer reports the parcel lost in transit or crushed by the courier.", "delivery"),
)

#: 175 branches from other support domains. They never hold the right answer;
#: they are there so N can reach 150 and 255 without inventing e-commerce
#: categories that would make a sentence genuinely ambiguous.
DISTRACTORS: tuple[Category, ...] = (
    # --- 은행 (25)
    Category("계좌 개설 문의", "Customer asks how to open a new bank account.", "bank"),
    Category("체크카드 재발급", "Customer asks for a replacement debit card.", "bank"),
    Category("이체 한도 상향", "Customer wants a higher bank transfer limit.", "bank"),
    Category("대출 상담 요청", "Customer asks for a loan consultation.", "bank"),
    Category("대출 상환 문의", "Customer asks how to repay a loan early.", "bank"),
    Category("예금 금리 문의", "Customer asks about deposit interest rates.", "bank"),
    Category("적금 만기 문의", "Customer asks when a savings plan matures.", "bank"),
    Category("인터넷뱅킹 이체 오류", "An online banking transfer fails with an error.", "bank"),
    Category("공동인증서 갱신", "Customer asks to renew a digital banking certificate.", "bank"),
    Category("통장 분실 신고", "Customer reports a lost bankbook.", "bank"),
    Category("카드 분실 신고", "Customer reports a lost credit card.", "bank"),
    Category("신용카드 한도 문의", "Customer asks about a credit card spending limit.", "bank"),
    Category("외화 환전 문의", "Customer asks about exchanging foreign currency.", "bank"),
    Category("해외 송금 문의", "Customer asks how to wire money abroad.", "bank"),
    Category("자동이체 등록", "Customer wants to set up an automatic bank transfer.", "bank"),
    Category("자동이체 해지", "Customer wants an automatic bank transfer stopped.", "bank"),
    Category("잔액 증명서 발급", "Customer asks for a bank balance certificate.", "bank"),
    Category("금융거래 확인서 발급", "Customer asks for a bank transaction statement.", "bank"),
    Category("보이스피싱 신고", "Customer reports a voice phishing attempt.", "bank"),
    Category("계좌 지급정지 요청", "Customer asks to freeze a bank account.", "bank"),
    Category("마이너스 통장 문의", "Customer asks about an overdraft account.", "bank"),
    Category("청약통장 문의", "Customer asks about a housing subscription account.", "bank"),
    Category("펀드 가입 문의", "Customer asks about buying an investment fund.", "bank"),
    Category("ATM 입출금 오류", "An ATM deposit or withdrawal did not complete.", "bank"),
    Category("은행 영업점 대기 문의", "Customer asks about branch opening times and queues.", "bank"),
    # --- 병원 (25)
    Category("진료 예약 문의", "Patient asks how to book a doctor's appointment.", "hospital"),
    Category("진료 예약 취소", "Patient wants to cancel a booked medical appointment.", "hospital"),
    Category("검사 결과 문의", "Patient asks when medical test results are ready.", "hospital"),
    Category("진단서 발급", "Patient asks for a medical certificate.", "hospital"),
    Category("처방전 재발급", "Patient asks for a reissued prescription.", "hospital"),
    Category("입원 수속 문의", "Patient asks about hospital admission paperwork.", "hospital"),
    Category("퇴원 수속 문의", "Patient asks about hospital discharge paperwork.", "hospital"),
    Category("병원비 수납 문의", "Patient asks how to pay a hospital bill.", "hospital"),
    Category("실손보험 청구 서류", "Patient asks for papers needed for a medical insurance claim.", "hospital"),
    Category("예방접종 일정 문의", "Patient asks about a vaccination schedule.", "hospital"),
    Category("건강검진 예약", "Patient asks to book a health screening.", "hospital"),
    Category("응급실 이용 문의", "Patient asks how the emergency room works.", "hospital"),
    Category("담당 의사 변경", "Patient wants a different attending doctor.", "hospital"),
    Category("약 복용법 문의", "Patient asks how to take a prescribed medicine.", "hospital"),
    Category("진료과 안내 문의", "Patient asks which hospital department to visit.", "hospital"),
    Category("수술 일정 문의", "Patient asks about the date of a scheduled operation.", "hospital"),
    Category("의무기록 사본 신청", "Patient asks for a copy of their medical records.", "hospital"),
    Category("물리치료 예약", "Patient asks to book physiotherapy.", "hospital"),
    Category("병실 배정 문의", "Patient asks about ward or room assignment.", "hospital"),
    Category("면회 시간 문의", "Visitor asks about hospital visiting hours.", "hospital"),
    Category("병원 주차 등록 문의", "Patient asks about registering a car at the hospital.", "hospital"),
    Category("진료비 영수증 재발급", "Patient asks for a reissued medical receipt.", "hospital"),
    Category("예방접종 증명서 발급", "Patient asks for a vaccination certificate.", "hospital"),
    Category("건강보험 적용 문의", "Patient asks whether health insurance covers a treatment.", "hospital"),
    Category("원격 진료 문의", "Patient asks about a remote medical consultation.", "hospital"),
    # --- 통신사 (25)
    Category("요금제 변경", "Subscriber wants to change their mobile price plan.", "telecom"),
    Category("데이터 추가 신청", "Subscriber wants to buy extra mobile data.", "telecom"),
    Category("통신 요금 청구 문의", "Subscriber asks about the monthly phone bill.", "telecom"),
    Category("통화 품질 불량 신고", "Subscriber reports poor call quality.", "telecom"),
    Category("인터넷 속도 저하 신고", "Subscriber reports slow home internet.", "telecom"),
    Category("인터넷 설치 예약", "Subscriber asks to book an internet installation.", "telecom"),
    Category("번호 이동 문의", "Subscriber asks about porting a number to another carrier.", "telecom"),
    Category("유심 재발급", "Subscriber asks for a replacement SIM card.", "telecom"),
    Category("휴대폰 분실 정지", "Subscriber asks to suspend a lost phone line.", "telecom"),
    Category("로밍 요금 문의", "Subscriber asks about international roaming charges.", "telecom"),
    Category("결합 할인 문의", "Subscriber asks about bundled service discounts.", "telecom"),
    Category("약정 기간 문의", "Subscriber asks when the contract term ends.", "telecom"),
    Category("통신 위약금 문의", "Subscriber asks about early termination charges on a line.", "telecom"),
    Category("통신 해지 요청", "Subscriber wants to terminate a phone line.", "telecom"),
    Category("단말기 할부금 문의", "Subscriber asks about handset instalment payments.", "telecom"),
    Category("소액결제 차단 요청", "Subscriber asks to block carrier billing.", "telecom"),
    Category("스팸 문자 차단 문의", "Subscriber asks how to block spam text messages.", "telecom"),
    Category("명의 변경 신청", "Subscriber wants a line transferred to another person's name.", "telecom"),
    Category("부가서비스 해지", "Subscriber wants a telecom add-on service cancelled.", "telecom"),
    Category("IPTV 채널 문의", "Subscriber asks about IPTV channel line-ups.", "telecom"),
    Category("공유기 설정 문의", "Subscriber asks how to configure a home router.", "telecom"),
    Category("통신 장애 접수", "Subscriber reports a network outage in their area.", "telecom"),
    Category("요금 미납 안내 문의", "Subscriber asks about an unpaid telecom bill notice.", "telecom"),
    Category("자급제 단말 개통", "Subscriber asks to activate a self-bought handset.", "telecom"),
    Category("청소년 요금제 문의", "Subscriber asks about youth mobile plans.", "telecom"),
    # --- SaaS (25)
    Category("라이선스 수량 변경", "Admin wants to change the number of software seats.", "saas"),
    Category("조직 계정 권한 설정", "Admin asks how to set workspace permissions.", "saas"),
    Category("SSO 연동 문의", "Admin asks about single sign-on integration.", "saas"),
    Category("API 키 발급", "Developer asks how to issue an API key.", "saas"),
    Category("API 사용량 한도 문의", "Developer asks about API rate limits.", "saas"),
    Category("웹훅 설정 문의", "Developer asks how to configure a webhook.", "saas"),
    Category("데이터 내보내기 요청", "Customer asks to export their workspace data.", "saas"),
    Category("데이터 이관 문의", "Customer asks about migrating data from another tool.", "saas"),
    Category("백업 복구 요청", "Customer asks to restore data from a backup.", "saas"),
    Category("서비스 장애 공지 문의", "Customer asks about a reported service outage.", "saas"),
    Category("무료 체험 연장", "Customer asks to extend a free trial.", "saas"),
    Category("요금제 업그레이드", "Customer asks to move to a higher subscription tier.", "saas"),
    Category("좌석 초대 오류", "Admin reports that inviting a teammate fails.", "saas"),
    Category("감사 로그 열람", "Admin asks for audit log access.", "saas"),
    Category("보안 인증 문서 요청", "Customer asks for security compliance documents.", "saas"),
    Category("온프레미스 설치 문의", "Customer asks about a self-hosted installation.", "saas"),
    Category("버전 업데이트 일정", "Customer asks when the next software release ships.", "saas"),
    Category("기능 요청 접수", "Customer suggests a new product feature.", "saas"),
    Category("버그 재현 정보 제공", "Customer supplies steps that reproduce a software bug.", "saas"),
    Category("연동 앱 오류", "Customer reports a third-party integration failing.", "saas"),
    Category("사용자 교육 요청", "Customer asks for onboarding training for their team.", "saas"),
    Category("계약서 검토 요청", "Customer asks for a contract review before signing.", "saas"),
    Category("소프트웨어 견적서 요청", "Customer asks for a written software quotation.", "saas"),
    Category("개발자 문서 오류 신고", "Developer reports a mistake in the documentation.", "saas"),
    Category("구독 계약 해지 절차", "Customer asks how to terminate a software subscription contract.", "saas"),
    # --- 공공기관 (25)
    Category("주민등록등본 발급", "Citizen asks how to get a residence certificate.", "public"),
    Category("인감증명서 발급", "Citizen asks about a registered seal certificate.", "public"),
    Category("전입신고 문의", "Citizen asks how to report a change of address.", "public"),
    Category("여권 발급 문의", "Citizen asks about passport issuance.", "public"),
    Category("운전면허 갱신", "Driver asks about renewing a driving licence.", "public"),
    Category("자동차 등록 문의", "Citizen asks about registering a vehicle.", "public"),
    Category("과태료 이의신청", "Citizen objects to an administrative fine.", "public"),
    Category("세금 납부 문의", "Citizen asks how to pay a tax bill.", "public"),
    Category("지방세 감면 문의", "Citizen asks about local tax reductions.", "public"),
    Category("국민연금 가입 문의", "Citizen asks about national pension enrolment.", "public"),
    Category("건강보험료 문의", "Citizen asks about health insurance premiums.", "public"),
    Category("실업급여 신청", "Citizen asks how to claim unemployment benefit.", "public"),
    Category("출생신고 문의", "Citizen asks how to register a birth.", "public"),
    Category("혼인신고 문의", "Citizen asks how to register a marriage.", "public"),
    Category("병역 관련 문의", "Citizen asks about military service administration.", "public"),
    Category("쓰레기 배출 문의", "Resident asks about waste disposal rules.", "public"),
    Category("불법 주정차 신고", "Resident reports illegally parked cars.", "public"),
    Category("도로 보수 요청", "Resident asks for a road to be repaired.", "public"),
    Category("가로등 고장 신고", "Resident reports a broken street light.", "public"),
    Category("소음 민원 접수", "Resident files a noise complaint about a neighbour.", "public"),
    Category("복지 지원금 문의", "Citizen asks about welfare payments.", "public"),
    Category("어린이집 입소 문의", "Parent asks about daycare admission.", "public"),
    Category("공공 도서관 이용 문의", "Resident asks about using the public library.", "public"),
    Category("민원 처리 기간 문의", "Citizen asks how long a civil petition takes.", "public"),
    Category("증명서 수수료 문의", "Citizen asks about fees for issuing official certificates.", "public"),
    # --- 항공/여행 (20)
    Category("항공권 예약 변경", "Traveller wants to change a flight booking.", "travel"),
    Category("항공권 환불 규정", "Traveller asks about airline ticket refund rules.", "travel"),
    Category("수하물 규정 문의", "Traveller asks about baggage allowance.", "travel"),
    Category("좌석 지정 문의", "Traveller asks about choosing an aircraft seat.", "travel"),
    Category("마일리지 적립 문의", "Traveller asks about frequent flyer miles.", "travel"),
    Category("결항 보상 문의", "Traveller asks about compensation for a cancelled flight.", "travel"),
    Category("기내식 요청", "Traveller asks for a special in-flight meal.", "travel"),
    Category("탑승 수속 문의", "Traveller asks about airport check-in.", "travel"),
    Category("여권 정보 수정", "Traveller asks to correct passport details on a booking.", "travel"),
    Category("호텔 예약 변경", "Guest wants to change a hotel reservation.", "travel"),
    Category("호텔 취소 수수료", "Guest asks about hotel cancellation fees.", "travel"),
    Category("렌터카 예약 문의", "Traveller asks about renting a car.", "travel"),
    Category("여행자 보험 문의", "Traveller asks about travel insurance.", "travel"),
    Category("비자 발급 문의", "Traveller asks about visa issuance.", "travel"),
    Category("공항 라운지 이용", "Traveller asks about airport lounge access.", "travel"),
    Category("반려동물 동반 탑승", "Traveller asks about flying with a pet.", "travel"),
    Category("유아 동반 좌석 문의", "Traveller asks about seating with an infant.", "travel"),
    Category("경유 시간 문의", "Traveller asks about a layover connection.", "travel"),
    Category("패키지 여행 일정 문의", "Traveller asks about a package tour itinerary.", "travel"),
    Category("여행 취소 위약금", "Traveller asks about tour cancellation penalties.", "travel"),
    # --- 보험 (15)
    Category("보험 가입 상담", "Customer asks about taking out an insurance policy.", "insurance"),
    Category("보험료 납입 문의", "Policyholder asks about paying insurance premiums.", "insurance"),
    Category("보험금 청구 절차", "Policyholder asks how to file an insurance claim.", "insurance"),
    Category("보험금 지급 지연", "Policyholder asks why an insurance payout is late.", "insurance"),
    Category("보험 해지 환급금", "Policyholder asks about the surrender value of a policy.", "insurance"),
    Category("자동차 보험 갱신", "Driver asks about renewing car insurance.", "insurance"),
    Category("보험 사고 접수", "Policyholder reports an accident to the insurer.", "insurance"),
    Category("보장 범위 문의", "Policyholder asks what the policy covers.", "insurance"),
    Category("실손 청구 서류 문의", "Policyholder asks which documents a claim needs.", "insurance"),
    Category("수익자 변경", "Policyholder wants to change the policy beneficiary.", "insurance"),
    Category("보험 증권 재발급", "Policyholder asks for a reissued policy document.", "insurance"),
    Category("할인 특약 문의", "Policyholder asks about discount riders on a policy.", "insurance"),
    Category("보험 나이 문의", "Policyholder asks how insurance age is counted.", "insurance"),
    Category("중도 인출 문의", "Policyholder asks about partial withdrawal from a policy.", "insurance"),
    Category("보험 계약 대출", "Policyholder asks about borrowing against a policy.", "insurance"),
    # --- 교육 (15)
    Category("수강 신청 문의", "Student asks how to register for a course.", "education"),
    Category("수강 취소 환불", "Student asks about withdrawing from a course.", "education"),
    Category("강의 일정 문의", "Student asks about class times.", "education"),
    Category("교재 구입 문의", "Student asks where to buy the course textbook.", "education"),
    Category("출석 인정 문의", "Student asks about attendance credit.", "education"),
    Category("성적 이의신청", "Student disputes a grade.", "education"),
    Category("수료증 발급", "Student asks for a course completion certificate.", "education"),
    Category("강사 변경 문의", "Student asks about a change of instructor.", "education"),
    Category("온라인 강의 접속 오류", "Student cannot access an online lecture.", "education"),
    Category("학원비 분할 납부", "Student asks to pay tuition in instalments.", "education"),
    Category("자격증 시험 접수", "Student asks how to apply for a certification exam.", "education"),
    Category("모의고사 일정 문의", "Student asks about mock exam dates.", "education"),
    Category("학습 상담 예약", "Student asks to book a study consultation.", "education"),
    Category("수업 보강 요청", "Student asks for a make-up class.", "education"),
    Category("국비 지원 문의", "Student asks about government-funded tuition support.", "education"),
)

#: The full option pool: eighty answerable categories, then the distractors.
ALL_CATEGORIES: tuple[Category, ...] = CATEGORIES + DISTRACTORS

CATEGORY_NAMES: tuple[str, ...] = tuple(c.name for c in ALL_CATEGORIES)
BY_NAME: dict[str, Category] = {c.name: c for c in ALL_CATEGORIES}


# ------------------------------------------------------- axis 1: width (x160)

#: Two sentences per category whose answer stays clear even against all eighty.
WIDTH_MESSAGES: dict[str, tuple[str, str]] = {
    "환불": (
        "구매한 정수기 필터 세트 전액 환불해 주세요. 결제 취소 요청드립니다.",
        "주문한 상품값을 전부 돌려받고 싶습니다. 환불 요청드립니다.",
    ),
    "취소 요청": (
        "방금 넣은 주문 아직 출고 전이면 취소해 주세요.",
        "주문번호 40217 건 주문 취소 부탁드립니다.",
    ),
    "배송 지연": (
        "도착 예정일이 사흘이나 지났는데 아직도 물건이 안 왔습니다. 너무 늦네요.",
        "주문한 지 열흘째인데 아직 출고도 안 됐습니다. 왜 이렇게 늦나요?",
    ),
    "배송지 변경": (
        "이사를 해서 받는 주소를 새 집으로 바꿔 주세요.",
        "배송지에 동호수가 빠졌습니다. 302동 1104호로 수정 부탁드립니다.",
    ),
    "배송 조회": (
        "지금 택배가 어디쯤 왔는지 현재 위치를 알려주세요.",
        "운송장 번호랑 택배사를 알려주시겠어요?",
    ),
    "제품 불량": (
        "받은 커피머신 전원이 아예 안 들어오고 물이 샙니다. 불량 같아요.",
        "구매한 스탠드 조명이 켜자마자 꺼집니다. 제품 자체가 고장인 것 같습니다.",
    ),
    "사이즈 교환": (
        "주문한 셔츠가 작아서 한 치수 큰 것으로 교환하고 싶습니다.",
        "운동화를 265mm로 받았는데 270mm로 바꿔 주세요.",
    ),
    "재고 문의": (
        "품절된 그 텀블러 언제 재입고되나요?",
        "이 모델 블랙 색상 재고가 아직 남아 있는지 확인해 주세요.",
    ),
    "결제 오류": (
        "카드 결제가 두 번 승인됐습니다. 중복 결제된 것 같아요.",
        "결제 진행 중에 오류 코드가 뜨면서 결제창이 그냥 닫혔습니다.",
    ),
    "쿠폰/할인": (
        "생일 쿠폰이 장바구니에서 적용이 안 되는데 사용 조건이 어떻게 되나요?",
        "지금 진행 중인 할인 행사에 이 상품도 포함되는지 궁금합니다.",
    ),
    "회원 탈퇴": (
        "회원 탈퇴하려고 하는데 어디에서 신청하나요?",
        "계정을 완전히 삭제하고 서비스 이용을 그만두고 싶습니다.",
    ),
    "비밀번호 재설정": (
        "비밀번호를 잊어버렸습니다. 재설정하는 방법을 알려주세요.",
        "비밀번호 재설정 메일이 오지 않습니다. 다시 보내 주세요.",
    ),
    "영수증/세금계산서": (
        "지난달 구매 건 전자세금계산서를 발행해 주세요.",
        "현금영수증을 사업자 번호로 다시 발행해 주실 수 있나요?",
    ),
    "리뷰 작성 문의": (
        "구매 후기를 쓰려는데 사진은 몇 장까지 올릴 수 있나요?",
        "제가 올린 리뷰를 수정하려면 어느 메뉴로 들어가야 하나요?",
    ),
    "칭찬": (
        "포장이 정말 꼼꼼해서 감동했습니다. 잘 쓰겠습니다.",
        "상담사분이 너무 친절하게 안내해 주셔서 기분 좋았어요. 감사합니다.",
    ),
    "욕설/불만 표출": (
        "이런 엉망인 회사는 처음 봅니다. 진짜 최악이네요.",
        "일 처리를 이따위로 하니까 욕먹는 겁니다. 어이가 없습니다.",
    ),
    "대량 구매 문의": (
        "회사 창립기념품으로 300개 대량 구매하려는데 가능할까요?",
        "학교 행사용으로 200세트 단체 주문 견적을 받고 싶습니다.",
    ),
    "제휴 제안": (
        "저희는 마케팅 대행사인데 협업 제휴를 제안드리려 연락드립니다.",
        "유통 총판 계약 관련해 제휴 미팅을 요청드립니다.",
    ),
    "사용법 질문": (
        "이 블렌더 세척은 어떻게 하는 건가요? 사용 방법을 알려주세요.",
        "앱에서 기기를 와이파이에 연결하는 방법을 알려주세요.",
    ),
    "기타 잡담": (
        "오늘 서울 날씨 진짜 덥네요. 다들 더위 조심하세요.",
        "점심 뭐 드셨어요? 저는 김치찌개 먹었습니다.",
    ),
    "환불 지연": (
        "환불 승인됐다는 문자를 받은 지 열흘인데 아직 입금이 안 됐습니다.",
        "반품 완료 처리된 지 2주가 지났는데 환불금이 아직도 안 들어옵니다. 언제 들어오나요?",
    ),
    "오배송": (
        "주문한 건 청소기인데 전혀 다른 프라이팬이 왔습니다.",
        "다른 사람 이름이 적힌 상자가 배송됐습니다. 제 주문과 다른 물건이에요.",
    ),
    "반품 접수": (
        "구매한 원피스 반품 접수해 주세요. 상자에 다시 넣어 두었습니다.",
        "이 상품 반품 신청합니다. 회수 요청 접수 부탁드립니다.",
    ),
    "부분 배송": (
        "세 개 주문했는데 한 개만 도착했습니다. 나머지 두 개는 언제 오나요?",
        "한 주문에서 티셔츠만 오고 바지는 안 왔습니다.",
    ),
    "결제 수단 변경": (
        "이미 넣은 주문의 결제 수단을 다른 카드로 바꾸고 싶습니다.",
        "무통장 입금으로 주문했는데 카드 결제로 변경할 수 있을까요?",
    ),
    "로그인 오류": (
        "비밀번호는 맞는데 로그인하면 계속 오류 메시지가 뜹니다.",
        "아이디랑 비밀번호를 정확히 입력해도 로그인 화면에서 넘어가지 않습니다.",
    ),
    "색상/옵션 변경": (
        "같은 제품 화이트 색상으로 바꿔서 받고 싶습니다. 사이즈는 그대로요.",
        "옵션을 기본형으로 골랐는데 고급형으로 변경하고 싶습니다.",
    ),
    "적립금 문의": (
        "구매 확정했는데 적립금이 아직 안 들어왔습니다. 언제 쌓이나요?",
        "제 적립금이 이번 달에 소멸되는지 확인해 주세요.",
    ),
    "반품 정책 문의": (
        "반품은 수령 후 며칠까지 가능한지 규정이 궁금합니다. 아직 반품할 건 아니에요.",
        "개봉한 상품도 반품이 되는지 정책만 먼저 알고 싶습니다.",
    ),
    "고객센터 연결 요청": (
        "상담원과 직접 통화하고 싶습니다. 전화 연결 부탁드립니다.",
        "고객센터 전화번호랑 상담 가능한 시간이 어떻게 되나요?",
    ),
    "부분 환불": (
        "세 벌 중 한 벌만 반품했으니 그 한 벌 값만 환불해 주세요.",
        "주문 금액 중 배송비를 뺀 상품값만 부분 환불 가능할까요?",
    ),
    "배송비 문의": (
        "얼마 이상 사면 배송비가 무료인가요?",
        "제주도로 보내면 추가 배송비가 얼마나 붙나요?",
    ),
    "환불 수단 변경": (
        "카드 취소 말고 제 계좌로 환불금을 받고 싶습니다.",
        "환불을 다른 카드로 받을 수 있게 변경해 주세요.",
    ),
    "해외 배송 문의": (
        "미국으로도 배송이 되나요? 관세는 누가 부담하나요?",
        "해외 배송으로 보내면 며칠 정도 걸리는지 궁금합니다.",
    ),
    "정기결제 해지": (
        "매달 자동으로 빠져나가는 정기구독 결제를 해지해 주세요.",
        "다음 달부터 구독료가 청구되지 않게 정기결제를 중단하고 싶습니다.",
    ),
    "개인정보 변경": (
        "회원정보에 등록된 휴대폰 번호를 새 번호로 바꾸고 싶습니다.",
        "가입할 때 쓴 이메일 주소를 회사 메일로 변경해 주세요.",
    ),
    "구성품 누락": (
        "박스에 들어 있어야 할 전용 충전기가 빠져 있습니다.",
        "설명서에 적힌 여분 필터 두 개가 상자에 없었습니다.",
    ),
    "이벤트 응모 문의": (
        "이번 추첨 이벤트는 어떻게 응모하는 건가요?",
        "지난주 이벤트 당첨자 발표는 언제 하나요?",
    ),
    "교환 정책 문의": (
        "교환은 수령 후 며칠 안에 신청해야 하는지 규정을 알고 싶습니다.",
        "한 번 교환한 상품을 또 교환할 수 있는지 정책이 궁금합니다.",
    ),
    "앱 오류 신고": (
        "앱이 결제 화면에서 계속 튕깁니다. 오류 신고드립니다.",
        "홈페이지 장바구니 페이지가 흰 화면만 나오고 안 열립니다.",
    ),
    "반품 배송비 문의": (
        "단순 변심으로 반품하면 반품 배송비는 얼마인가요?",
        "반품할 때 택배비는 제가 내는 건가요, 회사가 부담하나요?",
    ),
    "택배사 변경 요청": (
        "지금 지정된 택배사 말고 다른 택배사로 보내 주실 수 있나요?",
        "이 지역은 우체국 택배로만 잘 오니 택배사를 바꿔 주세요.",
    ),
    "주문 수량 변경": (
        "두 개 주문했는데 세 개로 수량을 늘려 주세요.",
        "수량을 다섯 개에서 두 개로 줄여서 주문을 변경하고 싶습니다.",
    ),
    "새벽배송 요청": (
        "일반 배송 말고 새벽배송으로 받을 수 있을까요?",
        "오늘 주문하면 내일 새벽에 도착하는 배송으로 보내 주세요.",
    ),
    "무이자 할부 문의": (
        "이 카드로 결제하면 몇 개월 무이자 할부가 되나요?",
        "할부로 결제하고 싶은데 최대 몇 개월까지 나눠 낼 수 있나요?",
    ),
    "회원가입 문의": (
        "회원가입을 하려는데 인증번호가 오지 않아 가입이 안 됩니다.",
        "가입은 꼭 휴대폰 인증을 해야 하나요? 가입 절차를 알려주세요.",
    ),
    "상품 스펙 문의": (
        "이 책상 가로 세로 높이 치수가 정확히 어떻게 되나요?",
        "이 가방 겉감 소재가 가죽인지 인조가죽인지 알려주세요.",
    ),
    "멤버십 등급 문의": (
        "멤버십 등급은 어떤 기준으로 올라가나요?",
        "골드 등급이 되면 어떤 혜택을 받을 수 있는지 알려주세요.",
    ),
    "보증/AS 정책 문의": (
        "이 제품 무상 보증 기간이 몇 년인가요?",
        "보증 기간이 지나면 수리비는 어떻게 청구되는지 알고 싶습니다.",
    ),
    "매장 정보 문의": (
        "강남점 영업시간이랑 주차 가능 여부를 알려주세요.",
        "직접 가서 보고 싶은데 오프라인 매장 주소가 어디인가요?",
    ),
    "취소 수수료 문의": (
        "지금 취소하면 위약금이 얼마나 나오나요? 금액만 먼저 알고 싶습니다.",
        "출고 후 취소하면 수수료가 붙는지, 얼마인지 궁금합니다.",
    ),
    "부재중 재배송 요청": (
        "어제 부재중이라 못 받았습니다. 오늘 다시 배송해 주세요.",
        "집에 아무도 없어서 반송될 것 같은데 재배송 요청드립니다.",
    ),
    "주문 내역 확인": (
        "지난주에 제가 무엇을 주문했는지 주문 내역을 알려주세요.",
        "제 주문번호를 잊어버렸습니다. 확인해 주실 수 있나요?",
    ),
    "배송 일정 지정 요청": (
        "다음 주 화요일 오후에 받고 싶은데 그날로 배송 날짜를 지정할 수 있나요?",
        "휴가 중이라 25일 이후에 도착하도록 배송일을 맞춰 주세요.",
    ),
    "가상계좌 입금 확인": (
        "가상계좌로 입금했는데 입금 확인이 됐는지 알려주세요.",
        "무통장 입금을 어제 저녁에 했는데 아직 입금 확인 처리가 안 됐습니다.",
    ),
    "휴면 계정 해제": (
        "오래 안 썼더니 휴면 계정이 됐습니다. 해제해 주세요.",
        "휴면 상태인 아이디를 다시 쓰려면 어떻게 해야 하나요?",
    ),
    "정품 확인 요청": (
        "여기서 파는 제품이 정품이 맞는지 확인하고 싶습니다.",
        "시리얼 번호로 정품 여부를 조회할 수 있나요?",
    ),
    "가격 인하 보상 문의": (
        "산 지 사흘 만에 가격이 내렸는데 차액 보상이 되나요?",
        "구매 후 할인 행사가 시작됐습니다. 가격 인하 차액을 받을 수 있는지 문의드립니다.",
    ),
    "환불 정책 문의": (
        "환불은 보통 며칠 안에 처리되는지 규정만 알고 싶습니다. 신청할 건 아니에요.",
        "어떤 경우에 환불이 안 되는지 환불 규정을 알려주세요.",
    ),
    "채용 문의": (
        "채용 공고를 보고 연락드립니다. 지원 절차가 궁금합니다.",
        "지금 채용 중인 직무가 있는지 알고 싶습니다.",
    ),
    "반품 회수 일정 문의": (
        "반품 접수는 했는데 회수 기사님이 언제 오시나요?",
        "반품 회수가 오늘 예정이었는데 아직 안 오셨습니다. 일정 확인해 주세요.",
    ),
    "배송 기사 불만": (
        "택배 기사님이 초인종도 안 누르고 물건을 문 앞에 던져두고 갔습니다.",
        "배송 기사분이 전화로 반말하며 짜증을 내셨습니다. 항의드립니다.",
    ),
    "취소 상태 확인": (
        "어제 주문 취소를 눌렀는데 취소가 정상 처리됐는지 확인해 주세요.",
        "취소 신청한 건이 아직 처리 중으로 보입니다. 취소된 게 맞나요?",
    ),
    "방문 수령 문의": (
        "택배 말고 매장에 직접 가서 받아 갈 수 있나요?",
        "물류창고에 방문해서 수령하고 싶은데 가능한지 문의드립니다.",
    ),
    "해외 결제 수수료 문의": (
        "해외 카드로 결제하면 수수료가 따로 붙나요?",
        "달러로 결제되면 환전 수수료는 얼마나 나오는지 궁금합니다.",
    ),
    "계정 정지 문의": (
        "제 계정이 갑자기 정지됐습니다. 이유를 알려주세요.",
        "이용 제한 상태라고 뜨는데 왜 제한된 건지 확인 부탁드립니다.",
    ),
    "호환성 문의": (
        "이 충전기가 제 노트북 모델에도 호환되나요?",
        "구형 본체에 이 부품을 끼워도 맞는지 알려주세요.",
    ),
    "사은품 문의": (
        "이번 행사 사은품은 어떤 조건으로 받을 수 있나요?",
        "사은품도 같이 발송되는지, 언제 받을 수 있는지 궁금합니다.",
    ),
    "개인정보 처리방침 문의": (
        "제 개인정보가 어디까지 제3자에게 제공되는지 알고 싶습니다.",
        "수집한 개인정보를 회사가 몇 년 동안 보관하는지 방침이 궁금합니다.",
    ),
    "구매 이력 확인": (
        "작년 한 해 동안 제가 구매한 내역 전체를 뽑아 주실 수 있나요?",
        "예전에 산 제품 목록을 기간별로 확인하고 싶습니다.",
    ),
    "예약 일정 변경": (
        "설치 기사님 방문 날짜를 다음 주 금요일로 변경하고 싶습니다.",
        "예약한 상담 시간을 오후 3시로 옮길 수 있을까요?",
    ),
    "배송 완료 오표시": (
        "배송 완료로 떴는데 문 앞에도 경비실에도 물건이 없습니다.",
        "받은 적이 없는데 배송이 완료됐다고 표시돼 있습니다.",
    ),
    "결제 승인 취소 확인": (
        "주문 취소했는데 카드 승인 취소는 언제 반영되나요?",
        "결제 취소됐다는데 카드 내역에 아직 승인 건이 남아 있습니다. 확인해 주세요.",
    ),
    "마케팅 수신 설정 변경": (
        "광고 문자가 너무 자주 옵니다. 수신 거부로 바꿔 주세요.",
        "앱 푸시 알림만 끄고 이메일은 계속 받고 싶습니다.",
    ),
    "유통기한 문의": (
        "이 제품 유통기한이 언제까지인가요?",
        "지금 발송되는 상품의 제조일자가 어떻게 되는지 알고 싶습니다.",
    ),
    "친구 초대 리워드 문의": (
        "친구 초대 코드를 입력하면 저도 혜택을 받나요?",
        "친구를 초대했는데 초대 리워드가 들어오지 않았습니다.",
    ),
    "이용약관 문의": (
        "이용약관 제12조에 적힌 책임 범위가 무슨 뜻인지 설명해 주세요.",
        "약관이 최근에 바뀌었다는데 어떤 조항이 달라졌나요?",
    ),
    "상담 이력 확인": (
        "지난주에 상담한 내용이 어떻게 처리됐는지 이력을 확인해 주세요.",
        "제가 이전에 문의한 건의 상담 기록을 다시 볼 수 있나요?",
    ),
    "미성년자 구매 정책 문의": (
        "중학생 아이가 결제한 건인데 미성년자 구매는 규정이 어떻게 되나요?",
        "만 19세 미만도 보호자 동의 없이 구매할 수 있나요?",
    ),
    "분실/파손 배송 사고 접수": (
        "배송 중에 상자가 완전히 찌그러져서 내용물이 망가졌습니다. 사고 접수해 주세요.",
        "택배가 배송 중 분실됐다고 합니다. 처리 부탁드립니다.",
    ),
}


# ---------------------------------------------------- axis 2: neighbours (x96)

#: Eight families, four categories each, told apart by a single word.
NEIGHBOR_FAMILIES: tuple[tuple[str, tuple[str, str, str, str]], ...] = (
    ("delivery", ("배송 지연", "배송 조회", "배송지 변경", "배송비 문의")),
    ("refund", ("환불", "환불 지연", "부분 환불", "환불 수단 변경")),
    ("account", ("회원 탈퇴", "비밀번호 재설정", "로그인 오류", "휴면 계정 해제")),
    ("payment", ("결제 오류", "결제 수단 변경", "정기결제 해지", "가상계좌 입금 확인")),
    ("product", ("제품 불량", "사이즈 교환", "색상/옵션 변경", "구성품 누락")),
    ("promo", ("쿠폰/할인", "적립금 문의", "이벤트 응모 문의", "멤버십 등급 문의")),
    ("policy", ("반품 정책 문의", "교환 정책 문의", "환불 정책 문의", "보증/AS 정책 문의")),
    ("order", ("취소 요청", "취소 수수료 문의", "취소 상태 확인", "주문 수량 변경")),
)

#: Three minimal sentences per family member.
NEIGHBOR_MESSAGES: dict[str, tuple[str, str, str]] = {
    "배송 지연": (
        "배송이 왜 이렇게 늦나요?",
        "배송 예정일보다 늦어지고 있어요.",
        "주문한 게 아직도 안 왔어요. 너무 늦습니다.",
    ),
    "배송 조회": (
        "배송 지금 어디쯤 왔나요?",
        "배송 조회 좀 해 주세요.",
        "운송장 번호 알려주세요.",
    ),
    "배송지 변경": (
        "배송지 바꿔 주세요.",
        "배송 주소를 수정하고 싶어요.",
        "받는 주소 변경 가능한가요?",
    ),
    "배송비 문의": (
        "배송비 얼마인가요?",
        "배송비 무료 기준이 어떻게 되나요?",
        "배송비가 추가로 붙나요?",
    ),
    "환불": (
        "환불해 주세요.",
        "환불 요청합니다.",
        "결제한 거 환불받고 싶어요.",
    ),
    "환불 지연": (
        "환불 언제 들어와요?",
        "환불이 아직도 안 들어왔어요.",
        "환불 처리가 왜 이렇게 늦나요?",
    ),
    "부분 환불": (
        "한 개만 환불해 주세요.",
        "일부 금액만 환불 가능한가요?",
        "두 개 중 하나만 환불받고 싶어요.",
    ),
    "환불 수단 변경": (
        "환불 계좌 바꾸고 싶어요.",
        "환불을 다른 카드로 받을 수 있나요?",
        "환불받을 수단을 변경해 주세요.",
    ),
    "회원 탈퇴": (
        "탈퇴하고 싶어요.",
        "계정 삭제해 주세요.",
        "회원 탈퇴 어떻게 하나요?",
    ),
    "비밀번호 재설정": (
        "비밀번호를 잊어버렸어요.",
        "비밀번호 재설정해 주세요.",
        "비밀번호 새로 바꾸고 싶어요.",
    ),
    "로그인 오류": (
        "비밀번호 맞는데 로그인이 안 돼요.",
        "로그인하면 오류가 떠요.",
        "로그인 화면에서 계속 튕겨요.",
    ),
    "휴면 계정 해제": (
        "휴면 계정 풀어 주세요.",
        "오래 안 써서 휴면으로 바뀌었어요.",
        "휴면 상태 해제하려면 어떻게 하나요?",
    ),
    "결제 오류": (
        "결제가 두 번 됐어요.",
        "결제하다가 오류가 났어요.",
        "카드 승인이 계속 실패해요.",
    ),
    "결제 수단 변경": (
        "결제 수단 바꿔 주세요.",
        "다른 카드로 결제하고 싶어요.",
        "카드 대신 계좌이체로 변경할게요.",
    ),
    "정기결제 해지": (
        "정기결제 해지해 주세요.",
        "매달 나가는 구독 결제 끊고 싶어요.",
        "자동결제 중단해 주세요.",
    ),
    "가상계좌 입금 확인": (
        "가상계좌로 입금했어요. 확인해 주세요.",
        "무통장 입금 확인됐나요?",
        "입금했는데 아직 확인이 안 됐어요.",
    ),
    "제품 불량": (
        "받은 제품이 고장 났어요.",
        "작동이 아예 안 돼요.",
        "전원이 안 켜집니다. 불량이에요.",
    ),
    "사이즈 교환": (
        "사이즈 교환하고 싶어요.",
        "한 치수 큰 걸로 바꿔 주세요.",
        "작아서 큰 사이즈로 교환돼요?",
    ),
    "색상/옵션 변경": (
        "색상 다른 걸로 바꿔 주세요.",
        "같은 제품 검정색으로 변경하고 싶어요.",
        "옵션을 다른 걸로 바꿀 수 있나요?",
    ),
    "구성품 누락": (
        "구성품 하나가 안 왔어요.",
        "박스에 충전기가 없어요.",
        "설명서에 있는 부속품이 빠졌어요.",
    ),
    "쿠폰/할인": (
        "쿠폰이 적용이 안 돼요.",
        "할인 코드 어디에 넣나요?",
        "이 상품도 할인되나요?",
    ),
    "적립금 문의": (
        "적립금이 안 들어왔어요.",
        "적립금 언제 소멸되나요?",
        "적립금 얼마나 쌓였나요?",
    ),
    "이벤트 응모 문의": (
        "이벤트 어떻게 응모해요?",
        "이벤트 당첨자 발표 언제예요?",
        "이 이벤트 아직 응모 가능한가요?",
    ),
    "멤버십 등급 문의": (
        "제 멤버십 등급이 뭔가요?",
        "등급은 어떻게 올라가요?",
        "골드 등급 혜택이 뭔가요?",
    ),
    "반품 정책 문의": (
        "반품 규정이 어떻게 되나요?",
        "반품은 며칠까지 되나요?",
        "개봉해도 반품 되나요?",
    ),
    "교환 정책 문의": (
        "교환 규정이 어떻게 되나요?",
        "교환은 며칠까지 되나요?",
        "교환은 몇 번까지 되나요?",
    ),
    "환불 정책 문의": (
        "환불 규정이 어떻게 되나요?",
        "환불은 며칠 걸리나요?",
        "어떤 경우에 환불이 안 되나요?",
    ),
    "보증/AS 정책 문의": (
        "보증 기간이 얼마인가요?",
        "무상 AS 규정이 어떻게 되나요?",
        "보증 기간 지나면 수리비 나오나요?",
    ),
    "취소 요청": (
        "주문 취소해 주세요.",
        "이 건 취소할게요.",
        "출고 전이면 취소 부탁드려요.",
    ),
    "취소 수수료 문의": (
        "취소하면 수수료 있나요?",
        "취소 위약금이 얼마인가요?",
        "지금 취소하면 얼마 떼나요?",
    ),
    "취소 상태 확인": (
        "취소 처리됐나요?",
        "어제 취소했는데 확인해 주세요.",
        "취소 상태가 아직 처리 중이에요.",
    ),
    "주문 수량 변경": (
        "수량을 두 개로 바꿔 주세요.",
        "한 개 더 추가할 수 있나요?",
        "세 개에서 한 개로 줄이고 싶어요.",
    ),
}


# --------------------------------------------------- axis 3: ambiguous (x40)

#: Sentences that straddle two of the first twenty categories, with the split a
#: human annotator would write down before seeing the model's answer.
AMBIGUOUS: tuple[Ambiguous, ...] = (
    Ambiguous("amb00", "받은 제품이 불량인데 그냥 환불해 주세요.", {"제품 불량": 0.5, "환불": 0.5}),
    Ambiguous("amb01", "주문한 지 오래됐는데 아직도 안 와서요, 그냥 취소하고 환불받고 싶어요.", {"취소 요청": 0.5, "환불": 0.5}),
    Ambiguous("amb02", "배송이 너무 늦어서요. 지금 어디쯤 왔는지 알려주세요.", {"배송 지연": 0.5, "배송 조회": 0.5}),
    Ambiguous("amb03", "사이즈가 안 맞는데 교환이 안 되면 환불받고 싶습니다.", {"사이즈 교환": 0.7, "환불": 0.3}),
    Ambiguous("amb04", "결제가 두 번 됐어요. 한 번은 취소하고 돈 돌려주세요.", {"결제 오류": 0.7, "환불": 0.3}),
    Ambiguous("amb05", "비밀번호도 안 되고 로그인도 안 되니 그냥 탈퇴할까 합니다.", {"비밀번호 재설정": 0.5, "회원 탈퇴": 0.5}),
    Ambiguous("amb06", "배송이 이렇게 늦는 게 말이 됩니까? 진짜 화납니다.", {"배송 지연": 0.5, "욕설/불만 표출": 0.5}),
    Ambiguous("amb07", "직원분 친절해서 좋았어요. 오늘 날씨도 좋고 기분 좋네요.", {"칭찬": 0.7, "기타 잡담": 0.3}),
    Ambiguous("amb08", "설명서대로 했는데 작동이 안 됩니다. 제가 잘못 쓰는 건가요?", {"사용법 질문": 0.5, "제품 불량": 0.5}),
    Ambiguous("amb09", "품절이라고 뜨는데 언제쯤 받아볼 수 있을까요?", {"재고 문의": 0.7, "배송 지연": 0.3}),
    Ambiguous("amb10", "쿠폰을 적용했는데 결제 금액이 이상하게 더 나왔습니다.", {"쿠폰/할인": 0.5, "결제 오류": 0.5}),
    Ambiguous("amb11", "세금계산서에 적힌 금액이 실제 결제 금액과 다릅니다.", {"영수증/세금계산서": 0.5, "결제 오류": 0.5}),
    Ambiguous("amb12", "리뷰에 사진을 올리려는데 앱에서 어떻게 하는 건지 모르겠어요.", {"리뷰 작성 문의": 0.7, "사용법 질문": 0.3}),
    Ambiguous("amb13", "주소를 잘못 적었는데 수정이 안 되면 주문을 취소해 주세요.", {"배송지 변경": 0.7, "취소 요청": 0.3}),
    Ambiguous("amb14", "200개를 한 번에 사려는데 재고가 그만큼 있나요?", {"대량 구매 문의": 0.5, "재고 문의": 0.5}),
    Ambiguous("amb15", "저희 회사에서 단체로 500개를 구매하면서 장기 공급 계약도 논의하고 싶습니다.", {"대량 구매 문의": 0.5, "제휴 제안": 0.5}),
    Ambiguous("amb16", "택배 상자가 찌그러져서 안에 있던 그릇이 깨졌습니다. 새로 보내주시거나 환불해 주세요.", {"제품 불량": 0.5, "환불": 0.5}),
    Ambiguous("amb17", "취소하려고 했는데 이미 출발했다고 하네요. 그럼 받고 나서 환불하면 되나요?", {"취소 요청": 0.5, "환불": 0.5}),
    Ambiguous("amb18", "운동화가 작아요. 큰 사이즈로 바꿔주시고, 없으면 그냥 돌려보낼게요.", {"사이즈 교환": 0.7, "환불": 0.3}),
    Ambiguous("amb19", "비밀번호를 다섯 번이나 틀려서 계정이 잠겼습니다. 이럴 거면 탈퇴하는 게 나을까요?", {"비밀번호 재설정": 0.7, "회원 탈퇴": 0.3}),
    Ambiguous("amb20", "이 제품 쓰는 법도 모르겠고, 애초에 제대로 만든 게 맞나 싶네요.", {"사용법 질문": 0.5, "욕설/불만 표출": 0.5}),
    Ambiguous("amb21", "포장은 훌륭했는데 배송이 하루 늦었어요.", {"칭찬": 0.5, "배송 지연": 0.5}),
    Ambiguous("amb22", "할인 쿠폰 받으려고 리뷰를 썼는데 쿠폰이 안 들어왔어요.", {"쿠폰/할인": 0.7, "리뷰 작성 문의": 0.3}),
    Ambiguous("amb23", "제품이 불량이라 반품했습니다. 세금계산서는 어떻게 되나요?", {"영수증/세금계산서": 0.7, "제품 불량": 0.3}),
    Ambiguous("amb24", "탈퇴하면 지금까지 산 내역이랑 영수증도 다 사라지나요?", {"회원 탈퇴": 0.7, "영수증/세금계산서": 0.3}),
    Ambiguous("amb25", "재고가 없으면 그냥 주문 취소해 주세요.", {"재고 문의": 0.5, "취소 요청": 0.5}),
    Ambiguous("amb26", "배송지를 바꾸고 싶은데, 지금 물건이 어디까지 갔는지부터 알려주세요.", {"배송지 변경": 0.5, "배송 조회": 0.5}),
    Ambiguous("amb27", "결제가 실패했는데 돈은 빠져나갔습니다. 돌려주세요.", {"결제 오류": 0.5, "환불": 0.5}),
    Ambiguous("amb28", "이 제품 협찬받아서 써보고 리뷰를 올리고 싶은데 가능한가요?", {"제휴 제안": 0.7, "리뷰 작성 문의": 0.3}),
    Ambiguous("amb29", "친절하게 응대해 주셔서 감사하지만 배송 문제는 여전히 해결이 안 됐습니다.", {"칭찬": 0.5, "배송 지연": 0.5}),
    Ambiguous("amb30", "기계에서 소리가 이상하게 나는데 원래 이런 건가요?", {"제품 불량": 0.5, "사용법 질문": 0.5}),
    Ambiguous("amb31", "300개 주문하려는데 할인은 얼마나 되나요?", {"대량 구매 문의": 0.7, "쿠폰/할인": 0.3}),
    Ambiguous("amb32", "주문한 물건이 안 와서 짜증나는데 그냥 취소할게요.", {"취소 요청": 0.5, "배송 지연": 0.5}),
    Ambiguous("amb33", "탈퇴했다가 다시 가입하면 기존 적립 내역은 유지되나요?", {"회원 탈퇴": 0.7, "쿠폰/할인": 0.3}),
    Ambiguous("amb34", "이 제품 사용법 영상이 리뷰에 올라와 있던데 그 영상 어디서 볼 수 있나요?", {"사용법 질문": 0.5, "리뷰 작성 문의": 0.5}),
    Ambiguous("amb35", "물건은 안 오고 문의해도 답이 없고, 진짜 이런 회사 처음입니다.", {"욕설/불만 표출": 0.5, "배송 지연": 0.5}),
    Ambiguous("amb36", "제품에 하자가 있어서 새 걸로 교환받고 싶습니다.", {"제품 불량": 0.7, "사이즈 교환": 0.3}),
    Ambiguous("amb37", "카드 결제 취소하고 다시 결제하려는데 쿠폰이 이미 사용됨으로 뜹니다.", {"쿠폰/할인": 0.5, "결제 오류": 0.5}),
    Ambiguous("amb38", "오늘 도착한다고 했는데 아직 출발도 안 했네요. 이럴 거면 취소가 낫겠어요.", {"배송 지연": 0.7, "취소 요청": 0.3}),
    Ambiguous("amb39", "택배 아저씨가 경비실에 맡겼다는데 경비실에는 없대요.", {"배송 조회": 0.7, "배송 지연": 0.3}),
)


# ------------------------------------------------------- axis 5: traps (x50)

#: One correct answer, a surface cue pointing elsewhere. Every gold sits in the
#: first twenty so the same sentence can be judged against 20 and against 80.
TRAPS: tuple[Trap, ...] = (
    Trap("tr-neg-0", "부정", "환불은 이미 됐고요, 배송지만 바꿔 주세요.", "배송지 변경"),
    Trap("tr-neg-1", "부정", "취소하려는 건 아니고, 배송이 지금 어디쯤인지만 알려주세요.", "배송 조회"),
    Trap("tr-neg-2", "부정", "불량은 아닙니다. 사이즈만 한 치수 큰 걸로 바꿔 주세요.", "사이즈 교환"),
    Trap("tr-neg-3", "부정", "할인 쿠폰 얘기가 아니라, 결제가 두 번 승인된 게 문제입니다.", "결제 오류"),
    Trap("tr-neg-4", "부정", "탈퇴하려는 게 아니라 비밀번호를 재설정하고 싶은 겁니다.", "비밀번호 재설정"),
    Trap("tr-neg-5", "부정", "제품은 아주 만족합니다. 다만 세금계산서 발행만 부탁드려요.", "영수증/세금계산서"),
    Trap("tr-neg-6", "부정", "환불도 교환도 필요 없습니다. 이 제품 세척 방법만 알려주세요.", "사용법 질문"),
    Trap("tr-neg-7", "부정", "배송이 늦어서 화가 난 건 아니고요, 그냥 주문을 취소하고 싶습니다.", "취소 요청"),
    Trap("tr-neg-8", "부정", "리뷰를 쓰려는 건 아닙니다. 이 모델 재입고 일정만 알려주세요.", "재고 문의"),
    Trap("tr-neg-9", "부정", "제휴 제안 아니고요, 회사에서 300개 단체로 구매하려고 문의드립니다.", "대량 구매 문의"),
    Trap("tr-quo-0", "인용", "친구는 환불하라는데 저는 사이즈 교환을 원합니다.", "사이즈 교환"),
    Trap("tr-quo-1", "인용", "남편이 그냥 취소하라고 하는데, 저는 배송지만 회사로 바꾸고 싶어요.", "배송지 변경"),
    Trap("tr-quo-2", "인용", "블로그에서는 이 제품이 불량이 많다던데, 저는 사용 방법만 알고 싶습니다.", "사용법 질문"),
    Trap("tr-quo-3", "인용", "상담사분은 재고가 없다고 하셨는데, 언제 재입고되는지 알려주세요.", "재고 문의"),
    Trap("tr-quo-4", "인용", "앞선 후기에는 배송이 늦다고 적혀 있던데, 제 건 지금 어디쯤 왔나요?", "배송 조회"),
    Trap("tr-quo-5", "인용", "동료가 탈퇴했다고 하더라고요. 저는 비밀번호만 새로 바꾸고 싶습니다.", "비밀번호 재설정"),
    Trap("tr-quo-6", "인용", "어머니는 환불받으라고 하시는데, 저는 결제가 두 번 된 것부터 확인하고 싶어요.", "결제 오류"),
    Trap("tr-quo-7", "인용", "회사 경리팀에서 영수증이 필요하다고 합니다. 세금계산서 발행 부탁드립니다.", "영수증/세금계산서"),
    Trap("tr-quo-8", "인용", "판매자분이 쿠폰을 쓰라고 하셨는데, 그 쿠폰 사용 조건이 어떻게 되나요?", "쿠폰/할인"),
    Trap("tr-quo-9", "인용", "지인이 여기 제품 별로라고 했는데 저는 아주 만족했습니다. 감사합니다.", "칭찬"),
    Trap("tr-hyp-0", "가정", "만약 300개를 한 번에 주문하면 단가가 달라지나요? 아직 확정은 아닙니다.", "대량 구매 문의"),
    Trap("tr-hyp-1", "가정", "혹시 재입고되면 알림을 받을 수 있나요? 지금 당장 사려는 건 아닙니다.", "재고 문의"),
    Trap("tr-hyp-2", "가정", "만약 제가 회사 주소로 받고 싶으면 지금이라도 배송지를 바꿀 수 있나요?", "배송지 변경"),
    Trap("tr-hyp-3", "가정", "혹시 지금 취소하면 바로 처리되나요? 아직 출고 전인 것 같은데 취소해 주세요.", "취소 요청"),
    Trap("tr-hyp-4", "가정", "만약 비밀번호를 세 번 이상 틀리면 계정이 잠기나요? 지금 재설정하려고 합니다.", "비밀번호 재설정"),
    Trap("tr-hyp-5", "가정", "혹시 이 블렌더를 뜨거운 재료에도 써도 되나요? 사용 방법이 궁금합니다.", "사용법 질문"),
    Trap("tr-hyp-6", "가정", "만약 제가 사업자로 구매하면 세금계산서 발행이 가능한가요?", "영수증/세금계산서"),
    Trap("tr-hyp-7", "가정", "혹시 리뷰를 수정하면 적립금이 취소되나요? 일단 리뷰 수정 방법부터 알려주세요.", "리뷰 작성 문의"),
    Trap("tr-hyp-8", "가정", "혹시 지금 제 택배가 어디쯤 왔는지 볼 수 있나요? 송장 번호를 잃어버렸습니다.", "배송 조회"),
    Trap("tr-hyp-9", "가정", "만약 다음 주에 할인 행사가 시작되면 이 상품도 할인 대상인가요?", "쿠폰/할인"),
    Trap("tr-emo-0", "감정", "진짜 너무 화가 나는데, 그냥 송장번호만 알려주세요.", "배송 조회"),
    Trap("tr-emo-1", "감정", "어이가 없어서 말이 안 나옵니다. 아무튼 주문 취소해 주세요.", "취소 요청"),
    Trap("tr-emo-2", "감정", "이런 경우가 어디 있습니까. 배송지를 다시 제대로 수정해 주세요.", "배송지 변경"),
    Trap("tr-emo-3", "감정", "정말 실망했습니다. 그래도 사이즈만 큰 걸로 교환해 주시면 됩니다.", "사이즈 교환"),
    Trap("tr-emo-4", "감정", "몇 번을 말해야 합니까? 결제가 두 번 승인된 것 좀 확인해 주세요.", "결제 오류"),
    Trap("tr-emo-5", "감정", "너무 짜증나는데 일단 비밀번호 재설정 메일부터 다시 보내 주세요.", "비밀번호 재설정"),
    Trap("tr-emo-6", "감정", "화가 머리끝까지 납니다. 세금계산서나 빨리 발행해 주세요.", "영수증/세금계산서"),
    Trap("tr-emo-7", "감정", "진짜 최악입니다. 그냥 전액 환불해 주세요.", "환불"),
    Trap("tr-emo-8", "감정", "속이 터집니다. 이 제품 필터 교체 방법이나 알려주세요.", "사용법 질문"),
    Trap("tr-emo-9", "감정", "어처구니가 없네요. 아무튼 이 모델 재고 있는지만 확인해 주세요.", "재고 문의"),
    Trap("tr-mix-0", "영어이모지", "Hi, 제 order 아직 안 왔는데 tracking number 좀 알려주세요 🙏", "배송 조회"),
    Trap("tr-mix-1", "영어이모지", "Please cancel my order 🙏 아직 출고 전입니다.", "취소 요청"),
    Trap("tr-mix-2", "영어이모지", "사이즈가 too small 해서 L size로 exchange 하고 싶어요 😅", "사이즈 교환"),
    Trap("tr-mix-3", "영어이모지", "Payment가 두 번 charge 됐어요 😱 확인 부탁드립니다.", "결제 오류"),
    Trap("tr-mix-4", "영어이모지", "I forgot my password 😭 재설정 링크 좀 보내 주세요.", "비밀번호 재설정"),
    Trap("tr-mix-5", "영어이모지", "Address 변경하고 싶어요! 새 주소로 update 부탁드립니다 🏠", "배송지 변경"),
    Trap("tr-mix-6", "영어이모지", "Refund please 🙇 결제한 금액 전액 돌려받고 싶습니다.", "환불"),
    Trap("tr-mix-7", "영어이모지", "Thank you so much 😊 포장도 배송도 완벽했어요!", "칭찬"),
    Trap("tr-mix-8", "영어이모지", "This item is broken 💔 받자마자 전원이 안 들어옵니다.", "제품 불량"),
    Trap("tr-mix-9", "영어이모지", "Tax invoice 발행 가능한가요? 사업자 번호로 부탁드립니다 📄", "영수증/세금계산서"),
)


# ------------------------------------------------------ axis 4: length (x20)

#: The first message of each of the twenty original categories, copied verbatim
#: from experiments/branches/dataset.py - every one of them was answered
#: correctly there, so a wrong answer here is the filler's doing.
LONG_MESSAGES: tuple[tuple[str, str], ...] = (
    ("환불", "지난주에 받은 원피스를 반품했는데 환불금이 아직 입금되지 않았습니다. 언제 들어오나요?"),
    ("취소 요청", "오늘 오전에 넣은 주문, 아직 출고 전이면 취소해 주세요."),
    ("배송 지연", "주문한 지 일주일이 지났는데 아직도 상품이 오지 않았습니다."),
    ("배송지 변경", "이사를 해서 받는 주소를 바꾸고 싶습니다. 출고 전이면 변경 가능할까요?"),
    ("배송 조회", "지금 제 택배가 어디쯤 와 있는지 위치를 조회해 주실 수 있나요?"),
    ("제품 불량", "받은 커피머신에서 물이 새고 전원이 아예 들어오지 않습니다."),
    ("사이즈 교환", "주문한 셔츠가 조금 작아요. 한 사이즈 큰 것으로 교환하고 싶습니다."),
    ("재고 문의", "품절된 그 텀블러는 언제 재입고되나요?"),
    ("결제 오류", "결제가 두 번 승인됐다고 문자가 왔어요. 중복 결제된 것 같습니다."),
    ("쿠폰/할인", "생일 쿠폰이 장바구니에서 적용되지 않는데 사용 조건이 어떻게 되나요?"),
    ("회원 탈퇴", "회원 탈퇴를 하고 싶은데 어디에서 신청하나요?"),
    ("비밀번호 재설정", "비밀번호를 잊어버려서 로그인이 안 됩니다. 재설정 방법을 알려주세요."),
    ("영수증/세금계산서", "지난달 구매 건의 세금계산서를 발행해 주세요."),
    ("리뷰 작성 문의", "구매 후기를 쓰려는데 사진은 몇 장까지 올릴 수 있나요?"),
    ("칭찬", "포장이 정말 꼼꼼해서 감동했어요. 잘 쓰겠습니다. 감사합니다."),
    ("욕설/불만 표출", "이런 엉망인 회사는 처음 봅니다. 진짜 최악이네요."),
    ("대량 구매 문의", "회사 창립기념품으로 300개 정도 대량 구매하려는데 가능한가요?"),
    ("제휴 제안", "저희는 마케팅 대행사인데 협업 제안을 드리고 싶어 연락드립니다."),
    ("사용법 질문", "이 블렌더를 처음 쓰는데 세척은 어떻게 하는 건가요?"),
    ("기타 잡담", "오늘 서울 날씨 진짜 덥네요. 다들 더위 조심하세요."),
)


# ------------------------------------------------------------ filler language

_SUBJECTS: tuple[str, ...] = (
    "회사", "판매자", "이용자", "회원", "구매자", "운영자", "배송 대행사", "결제 대행사",
    "고객센터", "제휴사", "수탁자", "통신판매중개자",
)

_TOPICS: tuple[str, ...] = (
    "전자상거래 표준약관", "개인정보 처리방침", "주문 취소 절차", "반품 회수 절차",
    "교환 판정 기준", "포인트 적립 기준", "쿠폰 사용 조건", "배송 예정일 산정 기준",
    "청약철회 기간", "분쟁 조정 절차", "서비스 이용 계약", "회원 등급 산정 기준",
    "전자금융거래 기록", "고지 의무", "미성년자 결제 확인 절차", "재화의 하자 판정 기준",
    "손해배상 범위", "약관 변경 고지 방법", "휴면 회원 전환 기준", "통신판매중개 책임 범위",
    "이용 제한 조치", "개인정보 파기 절차", "제3자 제공 항목", "위탁 처리 업무",
    "전자우편 수신 동의", "결제 승인 취소 처리", "배송 사고 처리 기준", "정기결제 갱신 조건",
    "수수료 산정 방식", "환불 처리 기한", "재고 정보 표시 기준", "가격 표시 원칙",
)

_CONDITIONS: tuple[str, ...] = (
    "천재지변 등 불가항력이 발생한 경우", "관계 법령이 개정된 경우", "정기 점검이 예정된 경우",
    "결제 정보가 일치하지 않는 경우", "재화의 공급이 중단된 경우", "이용자의 요청이 접수된 경우",
    "제휴 계약이 종료된 경우", "시스템 장애가 확인된 경우", "전산 기록이 보존되어 있는 경우",
    "감독 기관의 요청이 있는 경우", "계약 해지 사유가 발생한 경우", "판매 조건이 변경된 경우",
)

_CLAUSES: tuple[str, ...] = (
    "{subject}{subject_j_neun} {condition} {topic}{topic_j_eul} 변경할 수 있으며, 변경된 내용은 적용일 {days}일 전에 공지합니다.",
    "{topic}{topic_j_eun} 관계 법령과 본 약관이 정하는 바에 따르며, 세부 기준은 서비스 화면에 게시합니다.",
    "{condition} {subject}{subject_j_neun} {topic}{topic_j_eui} 적용을 일시적으로 제한할 수 있습니다.",
    "{subject}{subject_j_neun} {topic}{topic_j_eul} 처리할 때 제{article}항에서 정한 절차를 준수하여야 합니다.",
    "{topic}{topic_j_gwa} 관련한 기록은 {years}년간 보관되며, 보관 기간이 지나면 지체 없이 파기됩니다.",
    "본 조에서 정하지 아니한 {topic}{topic_j_e} 관한 사항은 전자상거래 등에서의 소비자보호에 관한 법률을 따릅니다.",
    "{condition} {topic}{topic_j_eui} 처리 기한은 영업일 기준 {days}일로 산정합니다.",
    "{subject}{subject_j_gwa} 이용자 사이에 분쟁이 발생한 경우 {topic}{topic_j_e} 따라 협의하여 해결합니다.",
    "공지 제{article}호에 따라 {month}월 {day}일부터 {topic}{topic_j_i} 일부 조정됩니다.",
    "{topic}{topic_j_eui} 적용 대상과 예외 사유는 부속 문서 별표 {article}에 따로 정합니다.",
    "{subject}{subject_j_neun} {topic}{topic_j_eul} 이유로 이용자에게 불이익한 조치를 하지 아니합니다.",
    "{topic}{topic_j_e} 대한 안내는 서비스 내 공지사항과 전자우편으로 함께 제공됩니다.",
    "{condition} {subject}{subject_j_neun} {topic}{topic_j_eul} 재검토하고 그 결과를 {days}일 이내에 기록합니다.",
    "{topic}{topic_j_eun} 제{article}장 총칙의 정의를 그대로 사용하며 별도의 해석을 두지 아니합니다.",
    "{subject}{subject_j_neun} {topic}{topic_j_e} 관하여 필요한 자료를 {years}년 단위로 갱신합니다.",
    "{topic}{topic_j_eul} 위반한 사실이 확인되면 {subject}{subject_j_neun} 제{article}항에 따른 조치를 취합니다.",
    "{condition} {topic}{topic_j_eun} 적용이 유예되며 유예 기간은 최대 {days}일을 넘지 아니합니다.",
    "{subject}{subject_j_neun} {topic}{topic_j_eul} 위하여 필요한 범위에서만 개인정보를 수집합니다.",
)

_HEADINGS: tuple[str, ...] = (
    "제{article}조 ({topic})",
    "[공지] {topic} 안내",
    "FAQ {article}. {topic}",
    "부칙 {article}. {topic}",
)


def _has_batchim(word: str) -> bool:
    """True when the last Hangul syllable ends in a consonant."""
    last = word[-1]
    if "가" <= last <= "힣":
        return (ord(last) - 0xAC00) % 28 != 0
    return True


def _forms(word: str) -> dict[str, str]:
    """The particles that follow `word`, so the filler stays grammatical."""
    batchim = _has_batchim(word)
    rieul = word[-1] != "" and "가" <= word[-1] <= "힣" and (ord(word[-1]) - 0xAC00) % 28 == 8
    return {
        "j_eun": "은" if batchim else "는",
        "j_neun": "은" if batchim else "는",
        "j_eul": "을" if batchim else "를",
        "j_i": "이" if batchim else "가",
        "j_gwa": "과" if batchim else "와",
        "j_eui": "의",
        "j_e": "에",
        "j_wa_gwan": "과" if batchim else "와",
        "j_ro": "로" if (not batchim or rieul) else "으로",
    }


def _slots(subject: str, topic: str, condition: str, rng: random.Random) -> dict[str, str]:
    out: dict[str, str] = {
        "subject": subject,
        "topic": topic,
        "condition": condition,
        "days": str(rng.choice((3, 5, 7, 10, 14, 15, 30, 60, 90))),
        "years": str(rng.choice((1, 2, 3, 5, 10))),
        "article": str(rng.randint(1, 48)),
        "month": str(rng.randint(1, 12)),
        "day": str(rng.randint(1, 28)),
    }
    for key, value in _forms(subject).items():
        out[f"subject_{key}"] = value
    for key, value in _forms(topic).items():
        out[f"topic_{key}"] = value
    return out


def text_tokens(text: str) -> float:
    """Input tokens contributed by `text` alone, without the request overhead."""
    korean = sum(1 for char in text if "가" <= char <= "힣" or "ㄱ" <= char <= "ㆎ")
    return korean * TOKEN_PER_KOREAN_CHAR + (len(text) - korean) * TOKEN_PER_OTHER_CHAR


def estimate_tokens(state: str, criteria: Mapping[str, str | None], instructions: str) -> float:
    """Input-token estimate for one call; used by --dry-run and the filler.

    The payload is spelled the same way the fit was made: the instructions, the
    state and the criteria as JSON, so the punctuation is counted too.
    """
    payload = instructions + state + json.dumps(dict(criteria), ensure_ascii=False)
    return TOKEN_BASE + text_tokens(payload)


def filler_paragraphs(seed: int, target_tokens: float) -> list[str]:
    """Policy-style Korean paragraphs, no two sentences alike, up to a token budget.

    The text is deliberately declarative: terms of service, notices and answer-side
    FAQ lines. Nothing in it is phrased as a customer asking for something, so the
    only inquiry in an axis-4 state is the one planted there.
    """
    rng = random.Random(seed)
    used: set[str] = set()
    paragraphs: list[str] = []
    total = 0.0
    article = 1
    while total < target_tokens:
        heading_template = _HEADINGS[rng.randrange(len(_HEADINGS))]
        topic = _TOPICS[rng.randrange(len(_TOPICS))]
        heading = heading_template.format(article=article, topic=topic)
        article += 1
        sentences: list[str] = []
        for _ in range(rng.randint(3, 6)):
            sentence = ""
            for _attempt in range(30):
                index = rng.randrange(len(_CLAUSES))
                subject = _SUBJECTS[rng.randrange(len(_SUBJECTS))]
                clause_topic = _TOPICS[rng.randrange(len(_TOPICS))]
                condition = _CONDITIONS[rng.randrange(len(_CONDITIONS))]
                sentence = _CLAUSES[index].format_map(
                    _slots(subject, clause_topic, condition, rng)
                )
                if sentence not in used:
                    break
            used.add(sentence)
            sentences.append(sentence)
        paragraph = heading + "\n" + " ".join(sentences)
        paragraphs.append(paragraph)
        total += text_tokens(paragraph) + 2 * TOKEN_PER_OTHER_CHAR
    return paragraphs


def long_state(index: int, inquiry: str, target_tokens: int, position: str) -> str:
    """Filler of about `target_tokens` tokens with `inquiry` planted in it."""
    if position not in POSITIONS:
        raise ValueError(f"unknown position {position!r}")
    body = target_tokens - text_tokens(inquiry)
    paragraphs = filler_paragraphs(seed=1000 + index, target_tokens=body)
    count = len(paragraphs)
    if position == "front":
        cut = max(1, round(count * 0.05))
    elif position == "middle":
        cut = count // 2
    else:
        cut = max(count - 1, min(count, round(count * 0.95)))
    planted = paragraphs[:cut] + ["고객 문의 접수 내용: " + inquiry] + paragraphs[cut:]
    return "\n\n".join(planted)


# ----------------------------------------------------------- option builders


def categories_for(n: int) -> list[Category]:
    """The first `n` options: the answerable eighty first, then distractors."""
    if n < 2 or n > len(ALL_CATEGORIES):
        raise ValueError(f"n must be between 2 and {len(ALL_CATEGORIES)}, got {n}")
    return list(ALL_CATEGORIES[:n])


def options_for(n: int) -> dict[str, str | None]:
    """Criteria for the first `n` categories: Korean name -> English line."""
    return {c.name: c.description for c in categories_for(n)}


def family_options(members: Sequence[str]) -> dict[str, str | None]:
    """Criteria for one neighbour family: four sibling categories only."""
    return {name: BY_NAME[name].description for name in members}


def width_samples(n: int) -> list[Sample]:
    """The two sentences of each answerable category among the first `n`.

    Past `REAL_CATEGORIES` the extra options are distractors with no sentences,
    so N=150 and N=255 evaluate the same 160 sentences as N=80.
    """
    samples: list[Sample] = []
    for index, category in enumerate(categories_for(min(n, REAL_CATEGORIES))):
        for position, text in enumerate(WIDTH_MESSAGES[category.name]):
            samples.append(Sample(id=f"w{index:02d}-{position}", text=text, gold=category.name))
    return samples


def neighbor_samples() -> list[tuple[str, Sample]]:
    """(family key, sample) for every neighbour sentence."""
    out: list[tuple[str, Sample]] = []
    for family, members in NEIGHBOR_FAMILIES:
        for position, name in enumerate(members):
            for index, text in enumerate(NEIGHBOR_MESSAGES[name]):
                out.append((family, Sample(id=f"{family}-{position}-{index}", text=text, gold=name)))
    return out


def long_samples() -> list[Sample]:
    """The twenty planted inquiries, in category order."""
    return [
        Sample(id=f"L{index:02d}", text=text, gold=gold)
        for index, (gold, text) in enumerate(LONG_MESSAGES)
    ]


# ------------------------------------------------------------------ self check


def validate() -> list[str]:
    """Structural checks over the dataset; returns a list of problems."""
    problems: list[str] = []
    if len(CATEGORIES) != REAL_CATEGORIES:
        problems.append(f"expected {REAL_CATEGORIES} categories, found {len(CATEGORIES)}")
    if len(DISTRACTORS) != 175:
        problems.append(f"expected 175 distractors, found {len(DISTRACTORS)}")
    if len(ALL_CATEGORIES) != max(N_VALUES):
        problems.append(f"expected {max(N_VALUES)} options, found {len(ALL_CATEGORIES)}")
    if len(set(CATEGORY_NAMES)) != len(CATEGORY_NAMES):
        seen: set[str] = set()
        dupes = sorted({n for n in CATEGORY_NAMES if n in seen or seen.add(n)})  # type: ignore[func-returns-value]
        problems.append(f"duplicate category names: {dupes}")
    for distractor in DISTRACTORS:
        if distractor.name in WIDTH_MESSAGES:
            problems.append(f"distractor {distractor.name} must not carry sentences")
    for category in CATEGORIES:
        messages = WIDTH_MESSAGES.get(category.name)
        if messages is None or len(messages) != 2:
            problems.append(f"{category.name}: needs exactly 2 width sentences")
    extra = set(WIDTH_MESSAGES) - set(CATEGORY_NAMES)
    if extra:
        problems.append(f"width sentences for unknown categories: {sorted(extra)}")
    texts = [text for pair in WIDTH_MESSAGES.values() for text in pair]
    if len(set(texts)) != len(texts):
        problems.append("duplicate width sentences")
    if len(NEIGHBOR_FAMILIES) != 8:
        problems.append(f"expected 8 neighbour families, found {len(NEIGHBOR_FAMILIES)}")
    for family, members in NEIGHBOR_FAMILIES:
        if len(members) != 4:
            problems.append(f"family {family}: needs exactly 4 members")
        for name in members:
            if name not in BY_NAME:
                problems.append(f"family {family}: unknown category {name}")
            elif len(NEIGHBOR_MESSAGES.get(name, ())) != 3:
                problems.append(f"{name}: needs exactly 3 neighbour sentences")
    if len(AMBIGUOUS) != 40:
        problems.append(f"expected 40 ambiguous sentences, found {len(AMBIGUOUS)}")
    first20 = set(CATEGORY_NAMES[:20])
    for item in AMBIGUOUS:
        if len(item.expected) != 2:
            problems.append(f"{item.id}: expected exactly 2 categories")
        if abs(sum(item.expected.values()) - 1.0) > 1e-9:
            problems.append(f"{item.id}: expected weights must sum to 1.0")
        for name in item.expected:
            if name not in first20:
                problems.append(f"{item.id}: {name} is not one of the first twenty")
    if len(TRAPS) != 50:
        problems.append(f"expected 50 traps, found {len(TRAPS)}")
    kinds: dict[str, int] = {}
    for trap in TRAPS:
        kinds[trap.kind] = kinds.get(trap.kind, 0) + 1
        if trap.gold not in first20:
            problems.append(f"{trap.id}: gold {trap.gold} is not one of the first twenty")
    for kind, count in kinds.items():
        if count != 10:
            problems.append(f"trap kind {kind}: {count} sentences, expected 10")
    if len(LONG_MESSAGES) != 20:
        problems.append(f"expected 20 long-state messages, found {len(LONG_MESSAGES)}")
    for gold, _ in LONG_MESSAGES:
        if gold not in first20:
            problems.append(f"long message gold {gold} is not one of the first twenty")
    return problems
