"""Korean customer-support messages, one clear category each.

Twenty categories, four sentences apiece. The category order is the branch order:
``categories_for(n)`` takes the first ``n``, and the confusable ones (refund,
cancellation, delivery delay, address change, tracking) sit in the first five so
even ``n=2`` asks a real question.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from string import ascii_uppercase
from typing import Sequence

#: Branch counts under test.
N_VALUES: tuple[int, ...] = (2, 3, 5, 8, 12, 20)

#: One instruction string for every condition, so presentation is the only variable.
INSTRUCTIONS = "Classify this Korean customer support message into exactly one category."

#: Presentation conditions. C and D rewrite how the options are shown, never the message.
CONDITIONS: tuple[str, ...] = ("A", "B", "C", "D", "E")

#: Shuffle seeds for condition C and repeat count for condition E.
C_SEEDS: tuple[int, ...] = (1, 2, 3)
E_REPEATS = 2


@dataclass(frozen=True)
class Category:
    """A branch: the Korean label the model picks and its English gloss."""

    name: str
    description: str


@dataclass(frozen=True)
class Sample:
    """One message with its single correct category."""

    id: str
    text: str
    gold: str


CATEGORIES: tuple[Category, ...] = (
    Category("환불", "Customer wants money back for an item or service already paid for or received."),
    Category("취소 요청", "Customer wants an order or a booking cancelled before it ships or starts."),
    Category("배송 지연", "Customer complains that the package is late or past its promised date."),
    Category("배송지 변경", "Customer wants the delivery address or recipient of an order changed."),
    Category("배송 조회", "Customer asks where the package is now or how to track it."),
    Category("제품 불량", "Customer reports the item arrived broken, damaged or not working."),
    Category("사이즈 교환", "Customer wants to swap the item for a different size of the same product."),
    Category("재고 문의", "Customer asks whether an item is in stock or when it will be restocked."),
    Category("결제 오류", "Customer reports a failed, duplicated or wrongly charged payment."),
    Category("쿠폰/할인", "Customer asks about coupons, promo codes, points or discount conditions."),
    Category("회원 탈퇴", "Customer wants to close or delete their membership account."),
    Category("비밀번호 재설정", "Customer cannot sign in and needs a password reset or account unlock."),
    Category("영수증/세금계산서", "Customer asks for a receipt, tax invoice or other proof-of-purchase document."),
    Category("리뷰 작성 문의", "Customer asks how to write, edit or delete a product review."),
    Category("칭찬", "Customer thanks the company or praises the product, packaging or staff."),
    Category("욕설/불만 표출", "Customer vents anger or insults without asking for any specific action."),
    Category("대량 구매 문의", "Customer asks about buying a large quantity or placing a corporate order."),
    Category("제휴 제안", "Another business proposes a partnership, sponsorship or reselling deal."),
    Category("사용법 질문", "Customer asks how to use, clean, install or operate the product."),
    Category("기타 잡담", "Off-topic small talk unrelated to any support request."),
)

MESSAGES: dict[str, tuple[str, ...]] = {
    "환불": (
        "지난주에 받은 원피스를 반품했는데 환불금이 아직 입금되지 않았습니다. 언제 들어오나요?",
        "받아본 제품이 마음에 들지 않아 반품하고 결제한 금액을 돌려받고 싶습니다.",
        "이미 결제한 정기구독 요금을 환불받고 싶어요. 환불 절차를 알려주세요.",
        "카드로 결제한 금액 환불 요청합니다. 계좌로 돌려받을 수 있나요?",
    ),
    "취소 요청": (
        "오늘 오전에 넣은 주문, 아직 출고 전이면 취소해 주세요.",
        "주문번호 20913 건 주문 취소 부탁드립니다.",
        "예약해 둔 설치 기사 방문 일정을 취소하고 싶습니다.",
        "아직 배송이 시작되지 않았다면 이 주문 취소 처리해 주세요.",
    ),
    "배송 지연": (
        "주문한 지 일주일이 지났는데 아직도 상품이 오지 않았습니다.",
        "도착 예정일이 이틀이나 지났는데 물건이 안 왔어요. 왜 이렇게 늦나요?",
        "명절 전에 받을 수 있다고 했는데 아직 출고도 안 됐네요. 너무 늦습니다.",
        "배송이 계속 늦어지고 있는데 예정보다 얼마나 더 기다려야 하나요?",
    ),
    "배송지 변경": (
        "이사를 해서 받는 주소를 바꾸고 싶습니다. 출고 전이면 변경 가능할까요?",
        "주문할 때 입력한 배송지가 예전 집 주소예요. 새 주소로 수정해 주세요.",
        "받는 사람을 제 회사 주소와 이름으로 바꿔서 보내 주실 수 있나요?",
        "배송지에 동호수를 빠뜨렸습니다. 101동 1502호로 수정 부탁드립니다.",
    ),
    "배송 조회": (
        "지금 제 택배가 어디쯤 와 있는지 위치를 조회해 주실 수 있나요?",
        "운송장 번호를 알려주시면 제가 직접 조회해 보겠습니다.",
        "택배사와 운송장 번호는 어디에서 확인할 수 있나요?",
        "어제 발송 문자를 받았는데 현재 배송 상태가 어떤지 확인 부탁드립니다.",
    ),
    "제품 불량": (
        "받은 커피머신에서 물이 새고 전원이 아예 들어오지 않습니다.",
        "택배 상자를 열어보니 유리컵 두 개가 깨져 있었어요.",
        "구매한 스탠드 조명이 켜자마자 꺼집니다. 불량인 것 같아요.",
        "의자 다리 한쪽에 금이 가 있고 심하게 흔들립니다. 불량품 같습니다.",
    ),
    "사이즈 교환": (
        "주문한 셔츠가 조금 작아요. 한 사이즈 큰 것으로 교환하고 싶습니다.",
        "신발을 275mm로 받았는데 265mm로 바꿔 주실 수 있을까요?",
        "같은 제품 라지 사이즈로 교환이 가능한지 문의드립니다.",
        "치마 길이가 너무 길어서 한 치수 작은 것으로 교환 요청드립니다.",
    ),
    "재고 문의": (
        "품절된 그 텀블러는 언제 재입고되나요?",
        "매장에 M 사이즈 재고가 남아 있는지 확인해 주실 수 있나요?",
        "이 모델 재고가 몇 개나 남아 있는지 알고 싶습니다.",
        "다음 주에 다시 판매가 시작되는지, 재입고 알림을 받을 수 있는지 궁금합니다.",
    ),
    "결제 오류": (
        "결제가 두 번 승인됐다고 문자가 왔어요. 중복 결제된 것 같습니다.",
        "카드 승인이 계속 실패하는데 결제가 안 되는 이유가 뭔가요?",
        "청구된 결제 금액이 주문 금액보다 만 원 더 많게 잡혔습니다.",
        "결제 진행 중에 오류 코드가 뜨면서 결제창이 그냥 닫혔습니다.",
    ),
    "쿠폰/할인": (
        "생일 쿠폰이 장바구니에서 적용되지 않는데 사용 조건이 어떻게 되나요?",
        "지금 진행 중인 할인 행사에 이 상품도 포함되나요?",
        "적립금과 할인 쿠폰을 같이 사용할 수 있는지 궁금합니다.",
        "신규 가입 할인 코드는 어디에 입력하는 건가요?",
    ),
    "회원 탈퇴": (
        "회원 탈퇴를 하고 싶은데 어디에서 신청하나요?",
        "계정을 완전히 삭제하고 제 개인정보도 지워 주세요.",
        "더 이상 서비스를 이용하지 않으려고 합니다. 탈퇴 처리 부탁드립니다.",
        "앱 계정 탈퇴 절차를 처음부터 안내해 주세요.",
    ),
    "비밀번호 재설정": (
        "비밀번호를 잊어버려서 로그인이 안 됩니다. 재설정 방법을 알려주세요.",
        "비밀번호 재설정 메일이 오지 않습니다. 다시 보내 주세요.",
        "계정이 잠겼다고 나오는데 비밀번호를 새로 설정하고 싶어요.",
        "로그인 비밀번호를 바꾸려면 어떤 메뉴로 들어가야 하나요?",
    ),
    "영수증/세금계산서": (
        "지난달 구매 건의 세금계산서를 발행해 주세요.",
        "현금영수증을 사업자 번호로 다시 발행해 주실 수 있을까요?",
        "회사 경비 처리를 해야 해서 구매 영수증 사본이 필요합니다.",
        "전자세금계산서를 제 이메일로 보내 주실 수 있나요?",
    ),
    "리뷰 작성 문의": (
        "구매 후기를 쓰려는데 사진은 몇 장까지 올릴 수 있나요?",
        "제가 쓴 리뷰를 수정하려면 어느 메뉴로 들어가야 하나요?",
        "실수로 올린 리뷰를 삭제하고 싶은데 방법을 알려주세요.",
        "리뷰는 배송 완료 후 며칠까지 작성할 수 있나요?",
    ),
    "칭찬": (
        "포장이 정말 꼼꼼해서 감동했어요. 잘 쓰겠습니다. 감사합니다.",
        "상담사분이 너무 친절하게 안내해 주셔서 기분이 좋았습니다.",
        "제품 품질이 기대 이상이에요. 주변에도 잘 추천하고 있습니다.",
        "빠르게 처리해 주셔서 감사합니다. 덕분에 잘 마무리됐어요.",
    ),
    "욕설/불만 표출": (
        "이런 엉망인 회사는 처음 봅니다. 진짜 최악이네요.",
        "일 처리를 이따위로 하니까 욕을 먹는 겁니다. 어이가 없네요.",
        "장난하나요? 이딴 식으로 장사한다는 게 말이 됩니까.",
        "정말 짜증나고 화가 납니다. 다시는 여기 안 옵니다.",
    ),
    "대량 구매 문의": (
        "회사 창립기념품으로 300개 정도 대량 구매하려는데 가능한가요?",
        "기업 단체 주문으로 500개 견적을 받고 싶습니다.",
        "학교 행사용으로 200세트 대량 구매가 가능한지 문의드립니다.",
        "도매로 한 번에 1,000개 주문하면 납기가 얼마나 걸리나요?",
    ),
    "제휴 제안": (
        "저희는 마케팅 대행사인데 협업 제안을 드리고 싶어 연락드립니다.",
        "인플루언서로 활동 중이며 제품 협찬 제휴를 제안드립니다.",
        "저희 플랫폼에 입점 제휴를 논의하고 싶습니다. 담당자 연결 부탁드립니다.",
        "유통 총판 계약 관련해서 제휴 미팅을 요청드립니다.",
    ),
    "사용법 질문": (
        "이 블렌더를 처음 쓰는데 세척은 어떻게 하는 건가요?",
        "앱에서 기기를 와이파이에 연결하는 방법을 알려주세요.",
        "필터는 얼마나 자주 교체해야 하는지 사용 방법이 궁금합니다.",
        "전자레인지에 돌려도 되는 용기인가요? 사용 방법을 알려주세요.",
    ),
    "기타 잡담": (
        "오늘 서울 날씨 진짜 덥네요. 다들 더위 조심하세요.",
        "점심은 뭐 드셨어요? 저는 김치찌개 먹었습니다.",
        "주말에 비 온다던데 다음 주에는 좀 개었으면 좋겠네요.",
        "요즘 볼 만한 드라마 있나요? 재밌는 거 추천 좀 해 주세요.",
    ),
}


def categories_for(n: int) -> list[Category]:
    """The first `n` categories, in the defined order."""
    if n < 2 or n > len(CATEGORIES):
        raise ValueError(f"n must be between 2 and {len(CATEGORIES)}, got {n}")
    return list(CATEGORIES[:n])


def samples_for(n: int) -> list[Sample]:
    """Every message whose gold category is one of the first `n`."""
    samples: list[Sample] = []
    for index, category in enumerate(categories_for(n)):
        for position, text in enumerate(MESSAGES[category.name]):
            samples.append(Sample(id=f"{index:02d}-{position}", text=text, gold=category.name))
    return samples


def _labels(n: int) -> list[str]:
    """Anonymous labels A, B, C ... for condition D."""
    if n > len(ascii_uppercase):
        raise ValueError("more branches than letters")
    return list(ascii_uppercase[:n])


def build_options(n: int, condition: str, seed: int | None = None) -> tuple[dict[str, str | None], dict[str, str]]:
    """The criteria mapping sent to the API, plus label -> gold-category lookup.

    A: Korean name + English description, defined order.
    B: Korean name only, no description.
    C: like A, with the options shuffled by `seed`.
    D: anonymous keys A, B, C ... whose description carries the Korean name.
    E: identical to A (the repeats differ only in that the cache is off).
    """
    categories = categories_for(n)
    if condition in ("A", "E"):
        return {c.name: c.description for c in categories}, {c.name: c.name for c in categories}
    if condition == "B":
        return {c.name: None for c in categories}, {c.name: c.name for c in categories}
    if condition == "C":
        if seed is None:
            raise ValueError("condition C needs a seed")
        shuffled = list(categories)
        random.Random(seed * 1000 + n).shuffle(shuffled)
        return {c.name: c.description for c in shuffled}, {c.name: c.name for c in shuffled}
    if condition == "D":
        labels = _labels(n)
        criteria = {
            label: f"{category.name} - {category.description}"
            for label, category in zip(labels, categories)
        }
        return criteria, dict(zip(labels, (c.name for c in categories)))
    raise ValueError(f"unknown condition {condition!r}")


def sample_counts() -> dict[int, int]:
    """Messages evaluated at each branch count."""
    return {n: len(samples_for(n)) for n in N_VALUES}


def all_category_names() -> Sequence[str]:
    return [c.name for c in CATEGORIES]
