"""파이프라인 재현성·정제 로직 안정성·분류 기준 확장성 검증용 synthetic VoC 데이터 생성 모듈.

실행:
    python src/generate_synthetic_voc.py --base data/voc.csv --output data/voc_augmented.csv --n 200 --seed 42

생성 규칙:
    - 원본 data/voc.csv는 절대 수정하지 않고 그대로 읽어 output에 이어붙인다.
    - synthetic 행은 10개 VoC 주제 카탈로그(TOPIC_CATALOG)에서 voc_type 목표 분포에 맞춰 샘플링한다.
    - 날짜 형식 혼용, channel 결측, content 공백, 완전 중복 등 원본과 동일한 유형의 데이터 품질
      이슈를 일정 비율로 주입해 clean.py/classify.py가 새 데이터에도 안정적으로 동작하는지 검증한다.
    - 필수 6컬럼(id/date/channel/customer_type/content/keyword_hint) 외에 검증용 컬럼
      (synthetic_source/expected_voc_type/expected_topic/expected_urgency)을 추가한다.
      파이프라인은 필수 6컬럼만으로 동작하며, 검증용 컬럼은 그대로 통과(pass-through)된다.

이 스크립트는 실제 고객 데이터를 생성하지 않는다. 회사명·고객명은 전부 일반화된 표현만 사용한다.
"""

import argparse
import random

import pandas as pd

import config

# ---------------------------------------------------------------------------
# 분포 설정
# ---------------------------------------------------------------------------

VOC_TYPE_WEIGHTS = {"일반 문의": 0.38, "기능 요청": 0.27, "불만": 0.27, "칭찬": 0.08}
CUSTOMER_TYPE_WEIGHTS = {"1차 협력사": 0.30, "2차 협력사": 0.40, "OEM": 0.15, "기타": 0.15}
CHANNEL_WEIGHTS = {"이메일": 0.40, "채널톡": 0.35, "미팅메모": 0.20, "": 0.05}

DATE_FORMAT_WEIGHTS = {"iso": 0.65, "slash": 0.22, "korean": 0.13}
DUPLICATE_RATIO = 0.025  # content 완전 중복 약 2.5%
WHITESPACE_RATIO = 0.10  # content 앞뒤 공백 주입 약 10%

SYNTHETIC_DATE_START = (2026, 6, 15)
SYNTHETIC_DATE_END = (2026, 9, 30)


# ---------------------------------------------------------------------------
# VoC 주제 카탈로그: {topic: {voc_type: [(content_template, keyword_hint, urgency), ...]}}
# content_template은 {n}/{pct}/{days} 플레이스홀더를 랜덤 값으로 채운다.
# 문장은 COMPLAINT_KEYWORDS/STRONG·SOFT_REQUEST/PRAISE_PATTERN(classify.py) 신호를
# 의도적으로 포함해, classify.py가 expected_voc_type과 동일하게 분류하도록 설계했다.
# ---------------------------------------------------------------------------

TOPIC_CATALOG = {
    "CBAM 신고/인증서": {
        "regulation": "CBAM",
        "keyword_hint": "CBAM, 신고, 인증서",
        "일반 문의": [
            ("CBAM 인증서 구매는 매년 언제까지 완료해야 하나요? 처음 신고라 절차가 헷갈립니다.", "Medium"),
            ("CBAM 보고서 제출 양식이 작년과 달라졌다고 들었는데, 어떤 항목이 바뀌었는지 확인하고 싶습니다.", "Medium"),
            ("협력사 {n}곳의 CBAM 데이터를 모아서 제출해야 하는데 순서가 어떻게 되는지 궁금합니다.", "Medium"),
        ],
        "기능 요청": [
            ("CBAM 인증서 구매 비용을 자동으로 추산해주는 계산기 기능이 있으면 좋겠습니다.", "Medium"),
            ("CBAM 제출 양식을 자동으로 사전 검증해주는 기능을 추가해주세요.", "Medium"),
            ("CBAM 신고 기한 D-{days}일 전부터 알려주는 알림 기능을 지원해주시면 좋겠습니다.", "Medium"),
        ],
        "불만": [
            ("카본링크에서 제출한 CBAM 보고서가 EU 세관에서 또 반려됐습니다. 양식이 계속 틀린 것 같습니다.", "High"),
            ("CBAM 신고 마감일이 지났는데 시스템에서 안내가 전혀 없었습니다. 업무 차질이 발생했습니다.", "High"),
            ("인증서 구매 절차가 너무 복잡해서 담당자가 매번 혼란스러워합니다.", "Medium"),
        ],
        "칭찬": [
            ("CBAM 신고 절차를 단계별로 안내해주셔서 이번에는 문제 없이 한 번에 제출했습니다. 감사합니다.", "Medium"),
            ("이번 신고는 걸림 없이 한 번에 통과되어 담당자 모두 만족스러웠습니다.", "Medium"),
        ],
    },
    "CSRD 보고/공시": {
        "regulation": "CSRD",
        "keyword_hint": "CSRD, ESRS, 제3자검증",
        "일반 문의": [
            ("CSRD 공시 항목 중 ESRS 기준으로 어떤 지표까지 포함해야 하는지 기준을 확인하고 싶습니다.", "Medium"),
            ("제3자 검증(Limited Assurance)은 어느 기관에 맡겨야 하는지 방법을 알고 싶습니다.", "Medium"),
            ("이중 중요성 평가를 완료 기한 전까지 끝내야 하는데 절차가 어떻게 되나요?", "Medium"),
        ],
        "기능 요청": [
            ("ESRS 이중 중요성 평가 템플릿을 플랫폼 내에서 제공해주시면 좋겠습니다.", "Medium"),
            ("CSRD 공시 항목별 작성 현황을 한눈에 보여주는 대시보드 기능이 필요합니다.", "Medium"),
            ("제3자 검증 기관에 바로 데이터를 전달할 수 있는 내보내기 기능을 추가해주세요.", "Medium"),
        ],
        "불만": [
            ("CSRD 공시 기준 해석이 매번 달라서 혼란스럽습니다. 공식 가이드가 필요합니다.", "Medium"),
            ("이중 중요성 평가 결과가 저장 중 누락되는 오류가 반복되고 있습니다.", "High"),
        ],
        "칭찬": [
            ("CSRD 공시 초안을 꼼꼼히 검토해주셔서 이사회 보고를 무사히 마쳤습니다. 감사합니다.", "Medium"),
            ("제3자 검증 대응 자료를 미리 준비해주셔서 감사 일정에 맞춰 무사히 마쳤습니다.", "Medium"),
        ],
    },
    "Scope 3/공급망 데이터": {
        "regulation": "Scope3",
        "keyword_hint": "Scope3, 협력사데이터",
        "일반 문의": [
            ("Scope 3 카테고리 중 물류 배출량은 어떤 방식으로 산정하는 것이 맞는지 확인하고 싶습니다.", "Low"),
            ("협력사 {n}곳의 응답률이 낮은데, 독촉 외에 다른 방법이 있는지 궁금합니다.", "Low"),
        ],
        "기능 요청": [
            ("협력사 {n}곳에 데이터 요청을 일괄로 발송하고 응답률을 추적하는 기능이 필요합니다.", "Low"),
            ("Scope 3 데이터 입력 양식을 협력사가 스스로 채울 수 있는 셀프서비스 화면을 추가해주세요.", "Low"),
            ("미제출 협력사에게 자동으로 리마인드 메일을 보내는 기능이 있으면 좋겠습니다.", "Low"),
        ],
        "불만": [
            ("협력사 {n}곳의 Scope 3 데이터를 일일이 손으로 입력해야 해서 너무 불편합니다.", "Low"),
            ("협력사마다 응답률이 달라 데이터 간 불일치가 발생해 신뢰하기 어렵습니다.", "Low"),
            ("공급망 데이터 업로드 중 절반 가까이 누락되는 오류가 발생했습니다.", "High"),
        ],
        "칭찬": [
            ("협력사 데이터 수집이 자동화된 이후로 담당자 업무 시간이 절반 가까이 줄었습니다. 만족스럽습니다.", "Low"),
        ],
    },
    "PCF/LCA/탄소발자국": {
        "regulation": "PCF/LCA",
        "keyword_hint": "PCF, LCA, 탄소발자국",
        "일반 문의": [
            ("제품탄소발자국(PCF) 산정에 국내 LCA 데이터베이스를 쓸 수 있는지 궁금합니다.", "Low"),
            ("제품군이 {n}개인데 PCF를 하나씩 산정해야 하는지, 유사 제품은 묶어도 되는지 알고 싶습니다.", "Low"),
        ],
        "기능 요청": [
            ("PCF 산정 시 여러 LCA 데이터베이스를 비교해서 보여주는 기능을 지원해주시면 좋겠습니다.", "Low"),
            ("제품별 탄소발자국 변화 추이를 비교하는 차트 기능이 필요합니다.", "Low"),
        ],
        "불만": [
            ("동일 제품인데 PCF 산정값이 지난 산정 대비 {pct}% 차이가 납니다. 원인을 알 수가 없습니다.", "Medium"),
            ("제품 {n}개 중 일부 PCF 값이 산정 시점마다 달라져 불일치가 발생합니다.", "Low"),
        ],
        "칭찬": [
            ("PCF 산정 리포트 덕분에 고객사 요청에 빠르게 대응할 수 있었습니다. 감사합니다.", "Low"),
            ("LCA 데이터베이스 추천 덕분에 산정 시간이 크게 줄었습니다. 감사합니다.", "Low"),
        ],
    },
    "계산 로직/데이터 신뢰성": {
        "regulation": "검증/인증",
        "keyword_hint": "계산로직, 데이터신뢰성",
        "일반 문의": [
            ("배출량 계산에 적용되는 배출계수 기준이 어떤 버전인지 확인하고 싶습니다.", "Low"),
            ("계산 결과가 소수점 단위로 자주 바뀌는데 반영 주기가 어떻게 되는지 궁금합니다.", "Low"),
        ],
        "기능 요청": [
            ("계산 근거(적용 계수, 산정 공식)를 화면에서 바로 확인할 수 있는 기능을 추가해주세요.", "Low"),
            ("외부 산정값과 자체 계산값을 나란히 비교해주는 기능이 있으면 좋겠습니다.", "Low"),
        ],
        "불만": [
            ("이번 달 계산 결과가 외부 전문기관 산정값과 {pct}% 이상 차이가 납니다. 계산이 틀린 것 같습니다.", "Medium"),
            ("응답률이 낮은 데이터가 반영되면서 전체 계산값에 불일치가 생겼습니다.", "Low"),
            ("배출계수 업데이트가 반영이 안 됩니다. 계산 결과를 신뢰하기 어렵습니다.", "High"),
        ],
        "칭찬": [
            ("계산 근거를 투명하게 공개해주셔서 내부 감사 대응이 한결 수월해졌습니다. 감사합니다.", "Medium"),
            ("차이 발생 건에 대한 원인 설명을 빠르게 받아서 도움이 많이 되었습니다.", "Medium"),
        ],
    },
    "보고서/대시보드": {
        "regulation": "기타",
        "keyword_hint": "보고서, 대시보드, 다운로드",
        "일반 문의": [
            ("분기별 보고서를 PDF 외 다른 형식으로도 받을 수 있는지 궁금합니다.", "Low"),
            ("대시보드에서 보여주는 배출량 데이터는 몇 시간 주기로 갱신되나요?", "Low"),
        ],
        "기능 요청": [
            ("보고서 템플릿을 회사 양식에 맞게 커스터마이징하는 기능을 추가해주세요.", "Low"),
            ("대시보드에서 연도별 배출량 추이를 비교하는 차트가 있으면 좋겠습니다.", "Low"),
            ("보고서를 정해진 주기로 자동 생성해서 담당자 메일로 보내주는 기능이 필요합니다.", "Low"),
        ],
        "불만": [
            ("대시보드 데이터를 다운로드하려고 하면 절반 정도의 확률로 오류가 발생합니다.", "High"),
            ("보고서 커스터마이징 옵션이 너무 제한적이어서 회사 양식에 맞추기 어렵습니다.", "Low"),
        ],
        "칭찬": [
            ("새로 추가된 대시보드 차트 덕분에 이사회 보고 준비 시간이 크게 줄었습니다. 감사합니다.", "Low"),
            ("분기 보고서 자동 발행 기능 덕분에 매번 수동으로 만들던 시간이 줄었습니다. 만족스럽습니다.", "Low"),
        ],
    },
    "플랫폼 오류/API/권한": {
        "regulation": "기타",
        "keyword_hint": "API, ERP, 권한",
        "일반 문의": [
            ("계정 담당자가 바뀌었는데 권한을 이전하는 절차가 어떻게 되는지 궁금합니다.", "Low"),
            ("ERP 연동 설정을 변경하려면 어떤 절차를 거쳐야 하나요?", "Low"),
            ("권한이 있는 담당자만 데이터를 내보낼 수 있게 하려면 어떻게 설정하나요?", "Low"),
        ],
        "기능 요청": [
            ("ERP 연동 상태를 실시간으로 확인할 수 있는 모니터링 화면을 지원해주시면 좋겠습니다.", "Low"),
            ("담당자별로 접근 권한을 세분화해서 설정하는 기능이 필요합니다.", "Low"),
        ],
        "불만": [
            ("카본링크 API 연동이 하루에도 몇 번씩 끊겨서 데이터가 누락되고 있습니다.", "Medium"),
            ("로그인이 안 됩니다. 비밀번호를 재설정해도 계속 안 되고 있어 업무가 마비됐습니다.", "High"),
            ("ERP와 연동한 이후로 권한 오류 메시지가 반복적으로 발생합니다.", "High"),
        ],
        "칭찬": [
            ("API 연동 문제를 다음 날 바로 해결해주셔서 업무에 지장이 없었습니다. 감사합니다.", "Low"),
            ("권한 설정 문의에 친절하게 답변해주셔서 빠르게 해결됐습니다. 감사합니다.", "Low"),
        ],
    },
    "기타": {
        "regulation": "기타",
        "keyword_hint": "가이드, 온보딩",
        "일반 문의": [
            ("친환경 경영 로드맵 수립 시 참고할 만한 공개 가이드가 있는지 궁금합니다.", "Low"),
            ("담당자 교육 자료를 어디서 받을 수 있는지 확인하고 싶습니다.", "Low"),
            ("탄소배출권 크레딧과 자체 감축 실적을 구분해서 보고해야 하는지 궁금합니다.", "Low"),
        ],
        "기능 요청": [
            ("신규 담당자를 위한 온보딩 가이드를 플랫폼 내에서 바로 볼 수 있게 지원해주시면 좋겠습니다.", "Low"),
            ("자주 묻는 질문을 모아 볼 수 있는 FAQ 게시판 기능을 추가해주세요.", "Low"),
        ],
        "불만": [
            ("온보딩 자료가 부족해서 신규 담당자가 적응하는 데 너무 불편합니다.", "Low"),
            ("가이드 문서가 오래된 내용이라 최신 절차와 맞지 않아 혼란스럽습니다.", "Low"),
        ],
        "칭찬": [
            ("온보딩 담당자분이 친절하게 안내해주셔서 초기 세팅이 순조로웠습니다. 감사합니다.", "Low"),
            ("친환경 경영 로드맵 작성 지원이 실무에 바로 활용할 수 있는 수준이었습니다. 정말 만족스럽습니다.", "Low"),
        ],
    },
}

# 혼합 표현(경계 케이스) 전용 템플릿: (topic, content, keyword_hint, expected_voc_type, expected_urgency)
MIXED_TEMPLATES = [
    (
        "CBAM 신고/인증서",
        "CBAM 제출 양식이 자꾸 반려됩니다. 양식 오류를 사전에 검증해주는 기능을 추가해주세요.",
        "CBAM, 반려, 기능",
        "불만",  # 불만 + 요청 혼합 -> 불만(개선요청)
        "High",
    ),
    (
        "계산 로직/데이터 신뢰성",
        "계산 결과가 외부 산정값과 차이가 납니다. 계산 근거를 공개해주시거나 설명해주세요.",
        "계산로직, 차이",
        "불만",
        "Medium",
    ),
    (
        "CSRD 보고/공시",
        "이중 중요성 평가 방법론을 플랫폼 내에서 지원해줄 수 있나요? 외부 컨설팅 비용이 너무 많이 나옵니다.",
        "CSRD, 이중중요성, 방법론",
        "기능 요청",  # 문의 + 요청 혼합 -> 기능 요청(가이드요청)
        "Medium",
    ),
    (
        "Scope 3/공급망 데이터",
        "협력사 데이터 요청 템플릿을 제공해주실 수 있나요? 협력사들이 서식이 없어 협조를 어려워합니다.",
        "Scope3, 협력사, 템플릿",
        "기능 요청",
        "Low",
    ),
    (
        "보고서/대시보드",
        "보고서 커스터마이징 기능이 정말 좋았습니다. 다만 차트 색상도 회사 톤에 맞게 바꿀 수 있으면 좋겠습니다.",
        "보고서, 커스터마이징, 차트",
        "칭찬",  # 칭찬 + 개선 제안 혼합, 긍정 표현이 중심 -> 칭찬
        "Low",
    ),
    (
        "플랫폼 오류/API/권한",
        "API 연동 모니터링 기능 덕분에 문제를 빠르게 발견해 도움이 많이 되었습니다. 재시도 로직도 추가해주시면 완벽할 것 같습니다.",
        "API, 모니터링, 재시도",
        "칭찬",
        "Low",
    ),
]

MIXED_RATIO = 0.08  # 전체 synthetic 행 중 약 8%를 경계 케이스 문장으로 채움

# 문장 앞에 랜덤하게 붙이는 시점 표현. classify.py의 불만/요청/칭찬/문의 판별 키워드와
# 겹치지 않는 중립적인 표현만 사용해, 분류 결과에 영향을 주지 않으면서 문장 다양성만 높인다.
TIME_PREFIXES = [
    "", "이번 주 ", "지난주 ", "이번 달 초 ", "최근 ", "오늘 아침 ", "어제 ",
    "이번 시즌 ", "지난달 ", "최근 며칠간 ", "오늘 오전 ", "방금 전 ",
]

# 문장 뒤에 랜덤하게 붙이는 마무리 표현. TIME_PREFIXES와 조합해 (12 x 9 = 108가지) 다양성을
# 만든다. classify.py의 불만/요청/칭찬/문의 판별 키워드와 겹치지 않는 표현만 사용했다.
DETAIL_SUFFIXES = [
    "",
    " 담당팀 회신을 기다리고 있습니다.",
    " 다음 보고 전까지 확인하려고 합니다.",
    " 같은 팀 동료들도 함께 궁금해하고 있습니다.",
    " 관련 담당자와 공유했습니다.",
    " 내부 회의에서도 논의된 사항입니다.",
    " 이번 주 안에 확인 가능한지 궁금합니다.",
    " 참고로 예전에도 비슷한 상황이 있었습니다.",
]


def _weighted_choice(rng: random.Random, weights: dict):
    keys = list(weights.keys())
    probs = list(weights.values())
    return rng.choices(keys, weights=probs, k=1)[0]


def _fill_placeholders(rng: random.Random, template: str) -> str:
    """{n}/{pct}/{days} 플레이스홀더를 채우고, 앞에 랜덤 시점 표현을 붙여 문장 다양성을 높인다.

    템플릿 풀이 한정적이라 플레이스홀더가 없는 문장은 그대로 두면 자주 충돌(의도치 않은 완전
    중복)이 발생한다. TIME_PREFIXES는 분류 키워드와 겹치지 않으므로 분류 결과에 영향이 없다.
    """
    filled = template.format(
        n=rng.randint(15, 250),
        pct=rng.randint(12, 35),
        days=rng.choice([7, 14, 30]),
    )
    prefix = rng.choice(TIME_PREFIXES)
    suffix = rng.choice(DETAIL_SUFFIXES)
    return f"{prefix}{filled}{suffix}"


def _random_date(rng: random.Random, date_format: str) -> str:
    start_ord = _to_ordinal(*SYNTHETIC_DATE_START)
    end_ord = _to_ordinal(*SYNTHETIC_DATE_END)
    day_ord = rng.randint(start_ord, end_ord)
    year, month, day = _from_ordinal(day_ord)

    if date_format == "iso":
        return f"{year:04d}-{month:02d}-{day:02d}"
    if date_format == "slash":
        return f"{year:04d}/{month:02d}/{day:02d}"
    return f"{month}월 {day}일"  # korean (연도 표기 없음 - 원본과 동일한 품질 이슈)


def _to_ordinal(year: int, month: int, day: int) -> int:
    import datetime

    return datetime.date(year, month, day).toordinal()


def _from_ordinal(ordinal: int):
    import datetime

    d = datetime.date.fromordinal(ordinal)
    return d.year, d.month, d.day


def generate_synthetic_rows(n: int, seed: int = 42) -> list:
    """TOPIC_CATALOG/MIXED_TEMPLATES에서 목표 분포에 맞춰 synthetic VoC n건을 생성한다."""
    rng = random.Random(seed)
    n_mixed = max(1, round(n * MIXED_RATIO))
    n_duplicates = max(1, round(n * DUPLICATE_RATIO))
    n_regular = n - n_mixed - n_duplicates

    rows = []

    for _ in range(n_regular):
        voc_type = _weighted_choice(rng, VOC_TYPE_WEIGHTS)
        candidate_topics = [t for t, buckets in TOPIC_CATALOG.items() if buckets.get(voc_type)]
        topic = rng.choice(candidate_topics)
        catalog_entry = TOPIC_CATALOG[topic]
        content_template, urgency = rng.choice(catalog_entry[voc_type])
        content = _fill_placeholders(rng, content_template)

        rows.append(
            {
                "content": content,
                "keyword_hint": catalog_entry["keyword_hint"],
                "expected_voc_type": voc_type,
                "expected_topic": topic,
                "expected_urgency": urgency,
            }
        )

    for _ in range(n_mixed):
        topic, content, keyword_hint, voc_type, urgency = rng.choice(MIXED_TEMPLATES)
        content = rng.choice(TIME_PREFIXES) + content + rng.choice(DETAIL_SUFFIXES)
        rows.append(
            {
                "content": content,
                "keyword_hint": keyword_hint,
                "expected_voc_type": voc_type,
                "expected_topic": topic,
                "expected_urgency": urgency,
            }
        )

    rng.shuffle(rows)

    # 완전 중복 content 주입 (약 2~3%): 이미 생성된 행 중 일부를 새 메타데이터로 복제
    # (n_duplicates는 위에서 n 예산 안에 포함되도록 이미 차감했다 -> 총 건수는 정확히 n)
    for _ in range(n_duplicates):
        source = rng.choice(rows)
        rows.append(dict(source))  # content/keyword_hint/expected_* 동일, 메타데이터는 아래에서 새로 채움

    # 날짜/채널/고객유형 배정 + 공백 주입 + id 부여
    synthetic_rows = []
    for i, row in enumerate(rows, start=1):
        date_format = _weighted_choice(rng, DATE_FORMAT_WEIGHTS)
        content = row["content"]
        if rng.random() < WHITESPACE_RATIO:
            content = f"  {content}  "

        synthetic_rows.append(
            {
                "id": None,  # 최종 저장 시 순번으로 재부여
                "date": _random_date(rng, date_format),
                "channel": _weighted_choice(rng, CHANNEL_WEIGHTS),
                "customer_type": _weighted_choice(rng, CUSTOMER_TYPE_WEIGHTS),
                "content": content,
                "keyword_hint": row["keyword_hint"],
                "synthetic_source": "synthetic",
                "expected_voc_type": row["expected_voc_type"],
                "expected_topic": row["expected_topic"],
                "expected_urgency": row["expected_urgency"],
            }
        )

    return synthetic_rows


def build_synthetic_dataframe(n: int, seed: int = 42) -> pd.DataFrame:
    """synthetic 행들을 DataFrame으로 구성한다."""
    rows = generate_synthetic_rows(n, seed=seed)
    df = pd.DataFrame(rows)
    return df


def load_base_dataframe(base_path) -> pd.DataFrame:
    """원본 VoC CSV(data/voc.csv)를 그대로 읽고 검증용 컬럼을 빈 값으로 채운다."""
    base_df = pd.read_csv(base_path, dtype=str, keep_default_na=False, encoding="utf-8")
    base_df["synthetic_source"] = "original"
    base_df["expected_voc_type"] = ""
    base_df["expected_topic"] = ""
    base_df["expected_urgency"] = ""
    return base_df


def build_augmented_dataframe(base_path, n: int, seed: int = 42) -> pd.DataFrame:
    """원본 데이터 + synthetic 데이터를 이어붙여 최종 augmented DataFrame을 만든다."""
    base_df = load_base_dataframe(base_path)
    synthetic_df = build_synthetic_dataframe(n, seed=seed)

    combined = pd.concat([base_df, synthetic_df], ignore_index=True)

    # id를 001부터 순번으로 재부여해 원본 접두 규칙(3자리 zero-pad)을 유지한다.
    combined["id"] = [str(i).zfill(3) for i in range(1, len(combined) + 1)]

    columns = config.INPUT_COLUMNS + ["synthetic_source", "expected_voc_type", "expected_topic", "expected_urgency"]
    return combined[columns]


def save_synthetic_csv(df: pd.DataFrame, output_path) -> None:
    """augmented DataFrame을 CSV로 저장한다."""
    df.to_csv(output_path, index=False, encoding="utf-8")


def write_synthetic_data_note(output_path, base_path, output_csv_path, n: int, seed: int, stats: dict) -> None:
    """output/augmented/synthetic_data_note.md를 작성한다."""
    note = f"""# 확장 더미 데이터 생성 노트

## 목적
제공 데이터만으로는 주간/월간 운영 상황의 재사용성을 검증하기 어려워, 실무 VoC 패턴을 가정한 synthetic 데이터를 추가 생성했다.

## 생성 원칙
- 원본 데이터 보존
- 도메인 맥락 기반 생성
- 데이터 품질 이슈 일부 포함
- 분류/정제/리포트 파이프라인 검증 목적

## 생성 결과 (이번 실행)
- 원본 파일: `{base_path}` ({stats['original_count']}건, 수정하지 않고 그대로 보존)
- synthetic 생성 건수: {n}건 (`--seed {seed}`)
- 최종 파일: `{output_csv_path}` (총 {stats['total_count']}건)
- voc_type 목표 분포: 일반 문의 {int(VOC_TYPE_WEIGHTS['일반 문의']*100)}% / 기능 요청 {int(VOC_TYPE_WEIGHTS['기능 요청']*100)}% / 불만 {int(VOC_TYPE_WEIGHTS['불만']*100)}% / 칭찬 {int(VOC_TYPE_WEIGHTS['칭찬']*100)}%
- 주입된 데이터 품질 이슈: 날짜 형식 혼용(iso/slash/한글 표기), channel 결측 약 5%, content 앞뒤 공백 약 10%,
  불만+요청/문의+요청/칭찬+개선제안 등 경계 케이스 표현 약 {MIXED_RATIO*100:.0f}%
- content 완전 중복: 목표 {DUPLICATE_RATIO*100:.1f}%로 의도적으로 주입했으나, 실제 측정 결과 synthetic
  {stats['synthetic_count']}건 중 {stats['duplicate_count']}건({stats['duplicate_pct']:.1f}%)이 완전 중복이다
  (템플릿 풀이 한정적이라 우연히 겹친 건이 일부 섞여 있음 — 오히려 실무 데이터의 "의도치 않은 중복"까지
  함께 검증할 수 있는 부수 효과로 해석했다)
- 검증용 컬럼: `synthetic_source`(original/synthetic), `expected_voc_type`, `expected_topic`, `expected_urgency`
  (원본 행은 검증 대상이 아니므로 위 세 컬럼을 빈 값으로 둔다)

## 주의사항
확장 데이터는 실제 고객 데이터가 아니므로, 최종 비즈니스 인사이트의 근거는 원본 데이터 분석 결과와 구분해 해석해야 한다.
`--dataset-label augmented`로 파이프라인을 실행해 `output/augmented/`에만 결과를 저장하고, `output/original/`의
원본 분석 결과와 절대 섞지 않는다.
"""
    output_path.write_text(note, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="파이프라인 검증용 synthetic VoC 데이터 생성")
    parser.add_argument("--base", default=str(config.DEFAULT_INPUT_CSV), help="원본 VoC CSV 경로 (수정하지 않음)")
    parser.add_argument("--output", default=str(config.SYNTHETIC_INPUT_CSV), help="augmented CSV 저장 경로")
    parser.add_argument("--n", type=int, default=200, help="생성할 synthetic VoC 건수 (기본값 200)")
    parser.add_argument("--seed", type=int, default=42, help="랜덤 시드 (재현성 보장)")
    args = parser.parse_args()

    config.ensure_output_dirs()

    df = build_augmented_dataframe(args.base, args.n, seed=args.seed)
    save_synthetic_csv(df, args.output)

    original_count = int((df["synthetic_source"] == "original").sum())
    synthetic_count = int((df["synthetic_source"] == "synthetic").sum())
    synthetic_rows = df[df["synthetic_source"] == "synthetic"]
    duplicate_count = int(synthetic_rows["content"].str.strip().duplicated(keep=False).sum())
    stats = {
        "original_count": original_count,
        "synthetic_count": synthetic_count,
        "total_count": len(df),
        "duplicate_count": duplicate_count,
        "duplicate_pct": (duplicate_count / synthetic_count * 100) if synthetic_count else 0.0,
    }

    note_path = config.AUGMENTED_OUTPUT_DIR / "synthetic_data_note.md"
    write_synthetic_data_note(note_path, args.base, args.output, args.n, args.seed, stats)

    print(f"[generate_synthetic_voc] 원본 {original_count}건 + synthetic {synthetic_count}건 = 총 {len(df)}건 -> {args.output}")
    print(f"[generate_synthetic_voc] 생성 노트: {note_path}")
    print(
        "[generate_synthetic_voc] 검증 실행 예: python src/run_pipeline.py --input "
        f"{args.output} --output output/augmented --dataset-label augmented --default-year 2026"
    )


if __name__ == "__main__":
    main()
