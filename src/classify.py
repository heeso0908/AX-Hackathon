"""VoC 4유형(불만/기능 요청/칭찬/일반 문의) 규칙 기반 분류 모듈.

실행:
    python src/classify.py [--input output/<mode>/voc-cleaned.csv] [--mode original|augmented]

입력: clean.py가 생성한 정제 데이터 (content, keyword_hint, customer_type, channel 포함)
출력: output/<mode>/voc_classification.csv

분류 판단 근거(기준표·혼합 케이스 처리·urgency/customer_impact 산정식)는 output/decisions.md에
문서화되어 있다. 분류 규칙 자체(키워드 사전)는 이 파일에서만 정의하며, 새 CSV에도 동일 규칙이 재사용된다.
"""

import argparse
import re

import pandas as pd

import config

# ---------------------------------------------------------------------------
# 1. 키워드/패턴 사전 (분류 규칙의 단일 소스)
# ---------------------------------------------------------------------------

COMPLAINT_KEYWORDS = [
    "장애", "오류", "불편", "업무 차질", "마비", "반려", "위험합니다",
    "안 됩니다", "안됩니다", "안 됐", "안됐",
    "틀린", "틀립니다", "틀려",
    "누락", "끊깁니다", "끊겨", "끊김",
    "혼란", "제한적", "불가능", "막혔",
    "차이납니다", "차이가 납니다", "차이가 난다", "불일치",
]

# 위 키워드가 등장해도 바로 뒤에 이런 표현이 오면 "문제가 해소/개선된" 긍정 문맥으로 보고
# 불만·긴급 신호로 인정하지 않는다 (예: "오류가 많이 줄었습니다" -> 칭찬 문맥).
RESOLUTION_CONTEXT_WORDS = ["줄었", "줄어들었", "감소했", "해소되었", "개선되었", "해결되었", "좋아졌"]
RESOLUTION_WINDOW = 20

# 강한 요청 표현: 제공/추가/개선 등 명확한 액션 요청 동사 + 문맥(topic word) 없이도 요청 신호로 간주.
# "설명해주세요"/"알려주세요"처럼 단순 정보 확인 목적의 "해주세요"는 제외한다 (문의로 처리).
STRONG_REQUEST_REGEX = re.compile(
    r"(제공해\s*주(세요|시면)?|추가해\s*주(세요|시면)?|만들어\s*주(세요|시면)?|"
    r"지원해\s*주(세요|시면)?|해결해\s*주세요|수정해\s*주세요|개선해\s*주세요|"
    r"부탁드립니다|요청드립니다|요청합니다)"
)

# 약한(완곡한) 요청 표현: 기능/서비스 등 요청 대상 명사가 함께 있어야 요청으로 인정
SOFT_REQUEST_REGEX = re.compile(
    r"(좋겠습니다|좋겠어요|있으면 좋겠|가능한가요|해줄 수 있나요|해주실 수 있나요|"
    r"해 주실 수 있나요|필요합니다|필요해요)"
)
REQUEST_TOPIC_WORDS = ["기능", "가이드", "템플릿", "자동화", "대시보드", "연동", "커스터마이징", "지원", "서비스", "차트", "문서", "양식"]

PRAISE_PATTERN = re.compile(
    r"(감사합니다|감사드립니다|고맙습니다|만족스럽|만족합니다|좋았습니다|"
    r"훌륭|인상적|친절하게|도움이|편하게 쓰고|줄었|줄어들었|올라갔|"
    r"향상되었|개선되었|무사히|순조로웠습니다)"
)

INQUIRY_PATTERN = re.compile(
    r"(언제|어떻게|방법|기준|절차|가능한가요|알고 싶|궁금합니다|확인하고 싶|"
    r"무엇인가요|인가요\?|될까요|맞나요|해야 하나요|모르겠습니다)"
)

GUIDE_SUBTOPIC_WORDS = ["가이드", "문서", "방법론", "교육", "안내", "매뉴얼"]

# urgency 판단 키워드 (등장 순서 = 우선순위: High > Medium > Low)
URGENCY_HIGH_KEYWORDS = ["긴급", "마감", "반려", "업무 마비", "수출 계약", "위험합니다", "EU 세관", "오류", "안 됩니다", "안됩니다"]
# "감사"는 바로 "감사합니다/감사드립니다"(칭찬)와 동형어라 "내부/외부 감사", "감사법인" 등
# 감사(audit) 문맥의 구체적 구절만 사용해 오탐을 방지한다.
URGENCY_MEDIUM_KEYWORDS = ["비용", "감사법인", "내부 감사", "외부 감사", "감사에서", "인증", "검증", "차이", "연동 끊김", "끊깁니다", "끊겨"]

# customer_impact 가중치 (decisions.md에 동일 표 문서화)
CUSTOMER_TYPE_WEIGHT = {"OEM": 3, "1차 협력사": 3, "2차 협력사": 2, "기타": 1}
URGENCY_WEIGHT = {"High": 3, "Medium": 2, "Low": 1}
REPEAT_LABOR_KEYWORDS = ["일일이", "반복", "번거", "매번", "수작업", "수동으로"]

TOPIC_KEYWORDS = [
    ("CBAM 신고/인증서", ["CBAM", "신고기한", "신고마감", "세관", "조달"]),
    ("CSRD 보고/공시", ["CSRD", "TCFD", "이중중요성", "감사법인", "해석기준", "이중보고"]),
    ("Scope 3/공급망 데이터", ["Scope3", "협력사데이터", "협력사", "공급망", "탄소크레딧"]),
    ("PCF/LCA/탄소발자국", ["LCA", "PCF", "탄소발자국", "탄소내재량"]),
    ("검증/인증/감사", ["검증", "인증기관", "ISO14064", "인증"]),
    ("계산 로직/데이터 신뢰성", ["계산로직", "Scope1", "Scope2", "GWP", "IPCC", "배출량계산", "계산"]),
    ("보고서/대시보드", ["보고서", "대시보드", "차트", "이사회보고", "분기", "커스터마이징", "보고서자동화", "보고서품질"]),
    ("플랫폼 오류/API/권한", ["로그인", "플랫폼오류", "API", "ERP", "연동오류", "권한관리", "데이터내보내기", "모바일"]),
    ("감축 로드맵/컨설팅", ["감축로드맵", "컨설팅", "SBTi", "감축목표", "탄소중립", "탄소감축", "분석리포트"]),
]

REGULATION_KEYWORDS = [
    ("CBAM", ["CBAM"]),
    ("CSRD", ["CSRD", "TCFD"]),
    ("Scope3", ["Scope3", "Scope 3"]),
    ("Scope2", ["Scope2", "Scope 2"]),
    ("Scope1", ["Scope1", "Scope 1"]),
    ("PCF/LCA", ["PCF", "LCA"]),
    ("ESG/공시", ["ESG", "공시", "SBTi", "녹색채권", "ICMA", "이중중요성", "이중보고"]),
    ("검증/인증", ["검증", "인증", "ISO14064"]),
]


# ---------------------------------------------------------------------------
# 2. 개별 신호 판별 함수
# ---------------------------------------------------------------------------

def _contains_any(text: str, words) -> str:
    """words 중 text에 포함된 첫 번째 항목을 반환 (없으면 빈 문자열)."""
    for w in words:
        if w.lower() in text.lower():
            return w
    return ""


def _contains_any_guarded(text: str, words) -> str:
    """words 중 text에 포함되면서, 바로 뒤에 '해소/개선' 문맥이 없는 첫 항목을 반환한다.

    예: "오류가 많이 줄었습니다"는 오류를 부정적 신호로 카운트하지 않는다.
    """
    lowered = text.lower()
    for w in words:
        idx = lowered.find(w.lower())
        if idx == -1:
            continue
        window = lowered[idx : idx + RESOLUTION_WINDOW]
        if any(rw in window for rw in RESOLUTION_CONTEXT_WORDS):
            continue
        return w
    return ""


def detect_complaint(text: str) -> str:
    return _contains_any_guarded(text, COMPLAINT_KEYWORDS)


def detect_request(text: str) -> tuple:
    """(request 신호 여부, 매칭된 표현)을 반환한다."""
    m = STRONG_REQUEST_REGEX.search(text)
    if m:
        return True, m.group(0)
    m = SOFT_REQUEST_REGEX.search(text)
    if m and any(w in text for w in REQUEST_TOPIC_WORDS):
        return True, m.group(0)
    return False, ""


def detect_praise(text: str) -> str:
    m = PRAISE_PATTERN.search(text)
    return m.group(0) if m else ""


def detect_inquiry(text: str) -> str:
    m = INQUIRY_PATTERN.search(text)
    if m:
        return m.group(0)
    return "?" if text.strip().endswith("?") else ""


def classify_topic(text: str) -> str:
    for topic, words in TOPIC_KEYWORDS:
        if any(w.lower() in text.lower() for w in words):
            return topic
    return "기타"


def classify_regulation_context(text: str) -> str:
    for reg, words in REGULATION_KEYWORDS:
        if any(w.lower() in text.lower() for w in words):
            return reg
    return "기타"


def classify_urgency(text: str) -> tuple:
    hit = _contains_any_guarded(text, URGENCY_HIGH_KEYWORDS)
    if hit:
        return "High", hit
    hit = _contains_any_guarded(text, URGENCY_MEDIUM_KEYWORDS)
    if hit:
        return "Medium", hit
    return "Low", ""


def classify_customer_impact(customer_type: str, urgency: str, text: str) -> str:
    weight = CUSTOMER_TYPE_WEIGHT.get(customer_type, 1) + URGENCY_WEIGHT.get(urgency, 1)
    if any(w in text for w in REPEAT_LABOR_KEYWORDS):
        weight += 1

    if weight >= 6:
        return "High"
    if weight >= 4:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# 3. 행 단위 분류
# ---------------------------------------------------------------------------

def classify_row(content: str, keyword_hint: str, customer_type: str, channel: str) -> dict:
    """단일 VoC 한 건을 분류하여 추가 컬럼 dict를 반환한다."""
    text = f"{content} {keyword_hint}"

    complaint_hit = detect_complaint(text)
    request_signal, request_hit = detect_request(text)
    praise_hit = detect_praise(text)
    inquiry_hit = detect_inquiry(text)

    reason_parts = []

    if complaint_hit:
        voc_type = "불만"
        if request_signal:
            sub_intent = "개선요청"
            reason_parts.append(f"불만 표현('{complaint_hit}')과 개선 요청 표현('{request_hit}')이 함께 나타나 불만(개선요청)으로 분류")
        else:
            sub_intent = ""
            reason_parts.append(f"불만 표현('{complaint_hit}')이 확인되어 불만으로 분류")

    elif praise_hit and request_signal:
        # 칭찬 + 개선 제안 혼합: 표현 강도를 비교해 중심 신호를 판단
        praise_count = len(PRAISE_PATTERN.findall(text))
        request_count = 1  # 이미 request_signal=True 이므로 최소 1
        if praise_count >= request_count:
            voc_type, sub_intent = "칭찬", ""
            reason_parts.append(f"긍정 표현('{praise_hit}')이 중심이 되어 칭찬으로 분류 (개선 제안은 부수적)")
        else:
            voc_type, sub_intent = "기능 요청", "개선제안"
            reason_parts.append(f"개선 제안 표현('{request_hit}')이 중심이 되어 기능 요청(개선제안)으로 분류")

    elif request_signal:
        voc_type = "기능 요청"
        if inquiry_hit:
            if any(w in text for w in GUIDE_SUBTOPIC_WORDS):
                sub_intent = "가이드요청"
            else:
                sub_intent = "기능요청"
            reason_parts.append(f"정보 확인('{inquiry_hit}')과 요청 표현('{request_hit}')이 함께 나타나 기능 요청({sub_intent})으로 분류")
        else:
            sub_intent = ""
            reason_parts.append(f"요청 표현('{request_hit}')이 확인되어 기능 요청으로 분류")

    elif praise_hit:
        voc_type, sub_intent = "칭찬", ""
        reason_parts.append(f"긍정 표현('{praise_hit}')이 확인되어 칭찬으로 분류")

    else:
        voc_type, sub_intent = "일반 문의", ""
        if inquiry_hit:
            reason_parts.append(f"정보 확인 표현('{inquiry_hit}')이 확인되어 일반 문의로 분류")
        else:
            reason_parts.append("불만/기능 요청/칭찬 신호가 없어 기본값인 일반 문의로 분류")

    topic = classify_topic(text)
    regulation_context = classify_regulation_context(text)
    urgency, urgency_hit = classify_urgency(text)
    customer_impact = classify_customer_impact(customer_type, urgency, text)

    if urgency_hit:
        reason_parts.append(f"urgency는 '{urgency_hit}' 표현에 따라 {urgency}로 판단")
    else:
        reason_parts.append(f"urgency는 별다른 긴급 신호가 없어 {urgency}로 판단")

    return {
        "voc_type": voc_type,
        "sub_intent": sub_intent,
        "topic": topic,
        "regulation_context": regulation_context,
        "urgency": urgency,
        "customer_impact": customer_impact,
        "classification_reason": ". ".join(reason_parts) + f" (customer_type={customer_type}, channel={channel} 반영)",
    }


# ---------------------------------------------------------------------------
# 4. DataFrame 단위 분류 + 특수 검증
# ---------------------------------------------------------------------------

def classify_voc(df: pd.DataFrame) -> pd.DataFrame:
    """정제된 VoC DataFrame에 분류 컬럼을 추가한 결과를 반환한다."""
    result = df.copy()

    classified = result.apply(
        lambda row: classify_row(
            row.get("content", ""),
            row.get("keyword_hint", ""),
            row.get("customer_type", ""),
            row.get("channel", ""),
        ),
        axis=1,
        result_type="expand",
    )
    result = pd.concat([result, classified], axis=1)
    return result


def run_special_validations(df: pd.DataFrame) -> list:
    """요구된 특수 검증(id 043 불만, id 001/031 중복 제거)을 확인한다."""
    warnings = []

    row_043 = df[df["id"] == "043"]
    if row_043.empty:
        warnings.append("id 043 데이터가 존재하지 않음 (검증 불가)")
    elif row_043.iloc[0]["voc_type"] != "불만":
        warnings.append(f"id 043이 '불만'이 아닌 '{row_043.iloc[0]['voc_type']}'로 분류됨")

    if "031" in df["id"].values:
        warnings.append("id 031이 중복 제거되지 않고 남아있음 (clean.py 정제 결과를 입력으로 사용했는지 확인 필요)")
    if "001" not in df["id"].values:
        warnings.append("id 001이 존재하지 않음 (중복 제거 시 최초 접수 건이 잘못 삭제되었을 가능성)")

    return warnings


# ---------------------------------------------------------------------------
# 5. 실행부
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="VoC 4유형 규칙 기반 분류")
    parser.add_argument("--input", default=None, help="정제된 VoC CSV 경로 (기본값: output/<mode>/voc-cleaned.csv)")
    parser.add_argument(
        "--mode", default="original", choices=["original", "augmented"],
        help="산출물 저장 위치: original(제공된 voc.csv) 또는 augmented(synthetic 검증용)",
    )
    args = parser.parse_args()

    config.ensure_output_dirs()
    paths = config.output_paths(args.mode)
    input_path = args.input or paths["cleaned_csv"]

    df = pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8")
    classified = classify_voc(df)

    warnings = run_special_validations(classified)
    for w in warnings:
        print(f"[classify][WARNING] {w}")

    classified.to_csv(paths["classified_csv"], index=False, encoding="utf-8")

    print(f"[classify] {len(classified)}건 분류 완료 -> {paths['classified_csv']}")
    print(classified["voc_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
