"""제품 개선 기획안 자동 생성 모듈 (Challenge 요건).

실행:
    python src/product_plan.py [--input output/original/voc_classification.csv] [--mode original]

입력: classify.py 결과 (불만/기능 요청 VoC + topic/urgency/customer_type/regulation_context)
출력: output/<mode>/product_improvement_plan.md — 우선순위 상위 2개 기획안만 작성

우선순위 산식: priority_score = frequency_score + impact_score + urgency_score + regulation_score - effort_score
점수 산정 기준의 근거는 output/decisions.md 6장에도 동일하게 기록한다.
"""

import argparse
import re

import pandas as pd

import config

PRODUCT_VOC_TYPES = ["불만", "기능 요청"]

# 제품 개선 후보 클러스터. topics는 classify.py가 산출한 topic 값과 매칭한다.
# 어떤 클러스터의 topics에도 속하지 않는 "기타" topic 행만 keywords로 보완 매칭한다
# (이미 topic이 명확한 행을 키워드로 재매칭해 중복 집계하지 않기 위함).
CLUSTER_DEFINITIONS = [
    {
        "key": "cbam_form",
        "title": "CBAM 신고·인증서 제출 어시스턴트",
        "topics": ["CBAM 신고/인증서"],
        "keywords": ["CBAM", "세관", "인증서"],
        "effort_score": 1,  # 문서/템플릿/가이드 수준
        "effort_label": "문서/템플릿 수준 (신고 절차 가이드 + 반려 사례 체크리스트)",
    },
    {
        "key": "scope3_automation",
        "title": "협력사 Scope 3 데이터 일괄 수집 자동화",
        "topics": ["Scope 3/공급망 데이터"],
        "keywords": ["Scope 3", "협력사", "공급망"],
        "effort_score": 3,  # API/복잡한 연동/신규 모듈
        "effort_label": "신규 모듈 (대량 발송·자동 리마인드·협력사 응답 수집 파이프라인)",
    },
    {
        "key": "report_customization",
        "title": "보고서 커스터마이징·자동 생성",
        "topics": ["보고서/대시보드"],
        "keywords": ["보고서", "대시보드", "커스터마이징", "차트"],
        "effort_score": 2,  # 화면/리포트 개선
        "effort_label": "화면/리포트 개선 (템플릿 편집기 + 스케줄 발행)",
    },
    {
        "key": "calc_reliability",
        "title": "계산 로직 투명성·검증 강화",
        "topics": ["계산 로직/데이터 신뢰성", "검증/인증/감사"],
        "keywords": ["계산", "GWP", "차이", "검증"],
        "effort_score": 2,  # 화면/리포트 개선 (계산 근거 화면 + 문서화)
        "effort_label": "화면/리포트 개선 (계산 근거 상세 화면 + 방법론 문서화)",
    },
    {
        "key": "api_integration",
        "title": "API/ERP 연동 안정성 개선",
        "topics": ["플랫폼 오류/API/권한"],
        "keywords": ["API", "ERP", "연동", "로그인"],
        "effort_score": 3,  # API/복잡한 연동
        "effort_label": "API/복잡한 연동 (연동 모니터링 + 재시도/알림 로직)",
    },
    {
        "key": "faq_onboarding",
        "title": "FAQ/가이드 자동 추천 온보딩",
        "topics": [],  # voc_type/sub_intent 기반으로 별도 매칭
        "keywords": ["가이드", "온보딩", "교육"],
        "effort_score": 1,  # 문서/템플릿/FAQ 수준
        "effort_label": "문서/템플릿 수준 (FAQ 콘텐츠 + 문의 유형별 추천 로직)",
    },
]

HIGH_VALUE_CUSTOMER_TYPES = ["OEM", "1차 협력사"]
CORE_REGULATION_CONTEXTS = {"CBAM", "CSRD", "Scope3", "검증/인증"}
SECONDARY_REGULATION_CONTEXTS = {"ESG/공시", "PCF/LCA"}


def load_classified(input_path) -> pd.DataFrame:
    """classify.py가 생성한 분류 결과 CSV를 읽는다."""
    return pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8")


def _short_quote(content: str, max_len: int = 60) -> str:
    """content에서 첫 문장만 추려 짧게 인용한다 (| 문자는 표가 깨지지 않도록 치환)."""
    content = (content or "").strip()
    sentences = re.split(r"(?<=[.?!])\s+", content)
    quote = sentences[0] if sentences and sentences[0] else content
    if len(quote) > max_len:
        quote = quote[:max_len].rstrip() + "..."
    return quote.replace("|", "/")


def _match_cluster_vocs(df: pd.DataFrame, cluster: dict) -> pd.DataFrame:
    """클러스터 정의에 맞는 VoC 후보(불만/기능 요청)를 df에서 추려낸다."""
    pool = df[df["voc_type"].isin(PRODUCT_VOC_TYPES)]

    if cluster["key"] == "faq_onboarding":
        mask = pool["sub_intent"].fillna("").str.contains("가이드") | pool["content"].str.contains(
            "|".join(cluster["keywords"]), case=False, na=False
        )
        return pool[mask]

    mask_topic = pool["topic"].isin(cluster["topics"])
    text = pool["content"].fillna("") + " " + pool["keyword_hint"].fillna("")
    mask_keyword_fallback = (pool["topic"] == "기타") & text.str.contains(
        "|".join(cluster["keywords"]), case=False, na=False
    )
    return pool[mask_topic | mask_keyword_fallback]


def _frequency_score(n: int) -> int:
    if n == 1:
        return 1
    if 2 <= n <= 3:
        return 2
    return 3


def _impact_score(customer_types: list) -> int:
    s = set(customer_types)
    if s & set(HIGH_VALUE_CUSTOMER_TYPES):
        return 3
    if "2차 협력사" in s:
        return 2
    return 1


def _urgency_score(urgencies: list) -> int:
    s = set(urgencies)
    if "High" in s:
        return 3
    if "Medium" in s:
        return 2
    return 1


def _regulation_score(regulation_contexts: list) -> int:
    s = set(regulation_contexts)
    if s & CORE_REGULATION_CONTEXTS:
        return 3
    if s & SECONDARY_REGULATION_CONTEXTS:
        return 2
    return 1


def cluster_candidates(df: pd.DataFrame) -> list:
    """6개 클러스터 정의에 맞춰 VoC를 매칭한 후보 목록을 만든다 (점수 산정 이전 단계)."""
    candidates = []
    for cluster in CLUSTER_DEFINITIONS:
        vocs = _match_cluster_vocs(df, cluster)
        if vocs.empty:
            continue
        candidates.append({**cluster, "vocs": vocs})
    return candidates


def score_priority(candidate: dict) -> dict:
    """후보 클러스터에 빈도·임팩트·긴급도·규제연관성·구현난이도 점수를 계산해 추가한다."""
    vocs = candidate["vocs"]
    frequency_score = _frequency_score(len(vocs))
    impact_score = _impact_score(vocs["customer_type"].tolist())
    urgency_score = _urgency_score(vocs["urgency"].tolist())
    regulation_score = _regulation_score(vocs["regulation_context"].tolist())
    effort_score = candidate["effort_score"]

    priority_score = frequency_score + impact_score + urgency_score + regulation_score - effort_score

    return {
        **candidate,
        "frequency_score": frequency_score,
        "impact_score": impact_score,
        "urgency_score": urgency_score,
        "regulation_score": regulation_score,
        "effort_score": effort_score,
        "priority_score": priority_score,
    }


def _problem_definition(candidate: dict) -> str:
    """근거 VoC 패턴을 바탕으로 3~5문장의 문제 정의 문단을 만든다."""
    vocs = candidate["vocs"]
    n = len(vocs)
    customer_types = vocs["customer_type"].value_counts()
    top_customer = customer_types.index[0]
    top_customer_count = int(customer_types.iloc[0])
    high_urgency_n = int((vocs["urgency"] == "High").sum())

    lead = {
        "cbam_form": (
            f"CBAM 신고 기한·인증서 구매 절차·EU 세관 제출 양식에 대한 문의·불만이 {n}건 반복적으로 접수되고 있다."
        ),
        "scope3_automation": (
            f"Scope 3(공급망) 탄소 데이터를 협력사로부터 수집하는 과정에서 수작업 의존도가 높아 불만·기능 "
            f"요청이 {n}건 발생하고 있다."
        ),
        "report_customization": (
            f"보고서 형식·대시보드 시각화·자동 생성 관련 요구가 {n}건 접수되었다."
        ),
        "calc_reliability": (
            f"카본링크의 탄소 배출량 계산 결과가 외부 산정값·경쟁사 플랫폼과 다르다는 지적이 {n}건 확인된다."
        ),
        "api_integration": (
            f"플랫폼 로그인·API/ERP 연동 오류로 업무가 중단되는 사례가 {n}건 접수되었다."
        ),
        "faq_onboarding": (
            f"절차·방법·가이드를 묻는 반복적인 정보 확인형 요청이 {n}건 확인된다."
        ),
    }[candidate["key"]]

    body = (
        f"{top_customer} 고객군에서 {top_customer_count}건으로 가장 많이 발생했고, 이 중 urgency High가 "
        f"{high_urgency_n}건이다. "
    )

    detail = {
        "cbam_form": (
            "특히 신고 기한을 처음 겪는 고객의 정보 확인성 문의(id001)부터, 실제 제출한 보고서가 EU 세관에서 "
            "반려된 사례(id010), 협력사 협조 문제로 데이터 확보 자체가 막힌 사례(id023), 마감을 이미 넘겨 수출 "
            "계약이 위험한 사례(id045)까지 위험도가 점진적으로 심각해지는 패턴을 보인다."
        ),
        "scope3_automation": (
            "협력사가 200개에 달하는 고객은 데이터를 일일이 손으로 입력해야 해 시간이 크게 소요되고(id008), "
            "계산 카테고리가 복잡해 가이드가 필요하거나(id005) 일괄 발송 기능이 없어 번거롭다는 지적(id018)이 "
            "이어진다."
        ),
        "report_customization": (
            "이사회·감사 보고에 쓸 트렌드 차트(id029), 고정 템플릿을 벗어난 자사 양식 커스터마이징(id043), "
            "분기별 반복 작업의 자동화(id037) 요구가 공통적으로 나타난다."
        ),
        "calc_reliability": (
            "외부 전문기관 산정값과 20% 차이(id014), 경쟁사 플랫폼과 30% 이상 차이(id033), IPCC 최신 기준 "
            "미반영으로 보이는 계산 오류(id019) 등 계산 로직의 투명성 부족이 반복 지적되고, 계산 근거와 "
            "함께 다뤄야 할 인증기관 제출용 데이터 내보내기 실패 사례(id027)도 같은 맥락에서 발생하고 있다."
        ),
        "api_integration": (
            "로그인 장애로 업무가 마비된 사례(id003), ERP 연동이 하루 수차례 끊겨 데이터가 누락되는 사례(id026), "
            "모바일 환경에서 데이터 확인이 안 되는 사례(id038)가 함께 발생한다."
        ),
        "faq_onboarding": (
            "CBAM 인증서 구매 절차 가이드 요청(id006), CSRD 이중 중요성 평가 방법론 지원 요청(id013)처럼 "
            "동일한 절차성 질문이 형태만 바뀌어 반복된다."
        ),
    }[candidate["key"]]

    return f"{lead} {body}{detail}"


def _cluster_content(key: str) -> dict:
    """클러스터별 개선 제안/기대 효과/MVP 범위 등 정성적 서술 콘텐츠를 반환한다."""
    content = {
        "cbam_form": {
            "key_feature": "VoC에서 확인된 이슈(신고 기한, 인증서 구매, EU 세관 제출 양식)를 단계별 체크리스트로 제공하는 'CBAM 신고 어시스턴트'",
            "ux": "신고 마감일 D-30/D-7 알림 배너 + 제출 양식 미리보기/자체 검증 화면",
            "automation": "제출 전 필수 항목(탄소내재량, 인증서 번호 등) 자동 검증 후 EU 세관 반려 가능성이 높은 항목을 사전 경고",
            "cs_ops": "반려·마감 초과 등 urgency High 건은 어시스턴트에서 즉시 컨설팅팀 티켓으로 에스컬레이션",
            "effect_cs": "반복되는 신고 기한·절차 문의가 줄어 컨설팅팀이 고위험 건(반려·마감 초과)에 집중할 수 있다.",
            "effect_product": "CBAM 관련 VoC 재발생률과 반려 건수를 제품 지표로 추적할 수 있게 된다.",
            "effect_customer": "처음 신고하는 협력사도 셀프서비스로 절차를 확인해 실수를 줄일 수 있다.",
            "effect_business": "EU 세관 반려·마감 초과로 인한 고객 이탈·계약 리스크를 사전에 줄인다.",
            "mvp_v1": "신고 기한 알림 + 제출 전 필수 항목 자동 검증 (id001, id010, id045 패턴 대응)",
            "mvp_excluded": "협력사 협조 문제(id023) 해결을 위한 자동 공문 발송 기능은 2차 범위로 미룬다.",
            "mvp_success": "CBAM 관련 문의·불만 VoC 건수 및 EU 세관 반려 재발 건수 감소",
        },
        "scope3_automation": {
            "key_feature": "협력사 데이터 요청을 대량으로 발송하고 응답 현황을 추적하는 '협력사 데이터 수집 자동화'",
            "ux": "협력사 목록 업로드 → 일괄 요청 발송 → 응답 현황 대시보드(제출/미제출/리마인드 필요)",
            "automation": "미제출 협력사에게 정해진 주기로 자동 리마인드 발송, 계산이 복잡한 카테고리(예: 카테고리 15 투자)는 입력 가이드 툴팁 제공",
            "cs_ops": "3회 리마인드 후에도 미제출인 협력사는 CS가 직접 개입하도록 알림",
            "effect_cs": "협력사 데이터 독촉 업무가 자동화되어 반복 문의 대응 시간이 줄어든다.",
            "effect_product": "데이터 수집 완료율을 신규 제품 지표로 확보할 수 있다.",
            "effect_customer": "협력사가 200개 이상인 고객도 일일이 손으로 입력하지 않고 진행 현황을 한눈에 관리할 수 있다.",
            "effect_business": "Scope 3 데이터 확보 속도가 빨라져 CSRD·CBAM 대응 리드타임이 줄어든다.",
            "mvp_v1": "일괄 요청 발송 + 제출 현황 대시보드 (id008, id018 패턴 대응)",
            "mvp_excluded": "카테고리 15(투자) 등 복잡 계산 가이드 콘텐츠(id005)는 FAQ 클러스터와 별도로 진행한다.",
            "mvp_success": "협력사 평균 데이터 제출 소요 시간 및 관련 VoC 재발생 건수",
        },
        "report_customization": {
            "key_feature": "보고서 템플릿 편집기 + 정기 보고서 자동 발행 스케줄러",
            "ux": "섹션 추가/삭제/순서 변경이 가능한 템플릿 편집 화면, 연도별 배출량 추세 차트 위젯",
            "automation": "분기/연간 주기로 지정된 템플릿을 자동 생성해 담당자 메일로 발송",
            "cs_ops": "커스터마이징 요청 중 표준 템플릿으로 해결되지 않는 예외 건은 CS가 요구사항을 수집해 제품팀에 전달",
            "effect_cs": "반복되는 '수동 편집 요청' 문의가 줄어 CS 리소스를 다른 이슈에 배분할 수 있다.",
            "effect_product": "템플릿 사용 패턴 데이터를 확보해 다음 커스터마이징 우선순위를 데이터 기반으로 정할 수 있다.",
            "effect_customer": "이사회·감사 보고 주기에 맞춰 원하는 형식의 보고서를 직접 만들고 자동으로 받을 수 있다.",
            "effect_business": "보고서 커스터마이징이 계약 갱신·업셀 포인트로 활용될 수 있다.",
            "mvp_v1": "템플릿 섹션 편집 기능 + 연도별 추세 차트 위젯 (id043, id029 패턴 대응)",
            "mvp_excluded": "분기별 자동 발행 스케줄러(id037)는 템플릿 편집기 안정화 이후 2차로 진행한다.",
            "mvp_success": "보고서 커스터마이징/차트 관련 VoC 건수 감소, 템플릿 재사용률",
        },
        "calc_reliability": {
            "key_feature": "계산 근거를 항목별로 펼쳐볼 수 있는 '계산 상세 보기' 화면 + ISO 14064 등 인증기관 제출용 표준 포맷 내보내기 + 방법론 공개 문서",
            "ux": "배출량 결과 옆에 '계산 근거 보기' 버튼 → 산정 공식, 적용 배출계수(GWP), 기준 연도 표시. 데이터 내보내기 화면에 '인증 제출용 포맷' 옵션 추가",
            "automation": "외부 산정값과 자체 계산값 차이가 지정 임계치(예: 15%) 이상이면 자동으로 검토 티켓 생성. ISO 14064 등 인증기관이 요구하는 표준 포맷의 내보내기 템플릿을 사전 정의해 내보내기 실패를 방지",
            "cs_ops": "차이 검토 티켓은 데이터 신뢰성 전담 담당자가 원인(계수 버전, 입력 오류 등)을 회신",
            "effect_cs": "'계산이 틀린 것 같다', '인증 제출용 내보내기가 안 된다'는 문의에 근거 화면·표준 포맷을 바로 안내할 수 있어 응대 시간이 줄어든다.",
            "effect_product": "계산 로직·내보내기 신뢰도 이슈를 정량적으로 추적(차이 발생 건수·내보내기 실패 건수·해소 시간)할 수 있다.",
            "effect_customer": "계산 결과를 신뢰할 수 있는 근거를 스스로 확인하고, 인증 기관 제출용 데이터를 바로 내보낼 수 있다.",
            "effect_business": "계산·검증 신뢰성은 제품의 핵심 신뢰 지표이므로, 이슈를 방치하면 이탈로 직결될 수 있는 리스크를 선제 관리한다.",
            "mvp_v1": "계산 상세 보기 화면 + IPCC 최신 GWP 기준 반영 + ISO 14064 표준 포맷 내보내기 지원 (id019, id027 패턴 대응)",
            "mvp_excluded": "외부 산정값 자동 비교 연동(제3자 API)은 2차 범위로 미룬다.",
            "mvp_success": "계산 차이·내보내기 실패 관련 VoC 건수, 관련 건의 평균 해소 시간",
        },
        "api_integration": {
            "key_feature": "API/ERP 연동 상태를 실시간으로 보여주는 '연동 모니터링' 화면과 자동 재시도 로직",
            "ux": "연동 상태(정상/끊김/재시도 중) 배지 + 최근 끊김 이력 타임라인",
            "automation": "연동 끊김 감지 시 자동 재시도 후, 반복 실패하면 담당자에게 즉시 알림 발송",
            "cs_ops": "일 3회 이상 끊김이 발생한 계정은 CS가 선제적으로 연락해 원인을 안내",
            "effect_cs": "'연동이 끊겼다'는 문의를 고객이 제기하기 전에 선제 대응할 수 있다.",
            "effect_product": "연동 안정성(가동률, 평균 재시도 성공률)을 제품 신뢰성 지표로 관리할 수 있다.",
            "effect_customer": "데이터 누락 없이 ERP와의 연동을 안심하고 사용할 수 있다.",
            "effect_business": "플랫폼 안정성 이슈로 인한 초기 온보딩 이탈을 줄인다.",
            "mvp_v1": "연동 상태 모니터링 화면 + 자동 재시도 로직 (id026 패턴 대응)",
            "mvp_excluded": "모바일 앱(id038)은 별도 로드맵 항목으로 분리한다.",
            "mvp_success": "연동 오류 관련 VoC 건수, 끊김 발생 후 평균 복구 시간",
        },
        "faq_onboarding": {
            "key_feature": "문의 내용을 분석해 관련 가이드/FAQ를 자동으로 추천하는 '스마트 헬프' 기능",
            "ux": "문의 작성 화면에서 키워드 입력 시 관련 가이드 문서를 실시간 추천",
            "automation": "반복 빈도가 높은 절차성 문의(신고 기한, 방법론 등)를 자동으로 FAQ 후보로 수집",
            "cs_ops": "추천 가이드로 해결되지 않은 경우에만 CS 상담으로 연결해 1차 응대를 자동화",
            "effect_cs": "신규 CS 담당자도 스마트 헬프 추천을 참고해 온보딩 기간을 줄일 수 있다.",
            "effect_product": "어떤 가이드가 자주 추천/클릭되는지 데이터를 쌓아 콘텐츠 우선순위를 정할 수 있다.",
            "effect_customer": "규제 대응을 처음 접하는 실무자도 빠르게 필요한 정보를 찾을 수 있다.",
            "effect_business": "CS 응대 시간을 줄여 동일 인력으로 더 많은 고객을 지원할 수 있다.",
            "mvp_v1": "상위 문의 패턴 기반 FAQ 추천 로직 (id006, id013 패턴 대응)",
            "mvp_excluded": "자연어 기반 자동 답변 생성(챗봇)은 2차 범위로 미룬다.",
            "mvp_success": "FAQ 추천 클릭률, 추천 후 CS 상담 전환율(낮을수록 목표 달성)",
        },
    }
    return content[key]


def build_proposal(candidate: dict) -> dict:
    """후보 클러스터를 '문제 정의/근거 VoC/개선 제안/기대 효과/우선순위/MVP 범위' 기획안으로 변환한다."""
    vocs = candidate["vocs"].copy()
    content = _cluster_content(candidate["key"])

    evidence_rows = [
        {
            "id": row["id"],
            "customer_type": row["customer_type"],
            "voc_type": row["voc_type"],
            "urgency": row["urgency"],
            "quote": _short_quote(row["content"]),
        }
        for _, row in vocs.sort_values("urgency", key=lambda s: s.map({"High": 0, "Medium": 1, "Low": 2})).iterrows()
    ]

    return {
        "title": candidate["title"],
        "problem_definition": _problem_definition(candidate),
        "evidence_rows": evidence_rows,
        "content": content,
        "scores": {
            "frequency_score": candidate["frequency_score"],
            "frequency_note": f"{len(vocs)}건",
            "impact_score": candidate["impact_score"],
            "impact_note": ", ".join(sorted(vocs["customer_type"].unique())),
            "urgency_score": candidate["urgency_score"],
            "urgency_note": ", ".join(sorted(vocs["urgency"].unique())),
            "regulation_score": candidate["regulation_score"],
            "regulation_note": ", ".join(sorted(vocs["regulation_context"].unique())),
            "effort_score": candidate["effort_score"],
            "effort_note": candidate["effort_label"],
            "priority_score": candidate["priority_score"],
        },
    }


def generate_product_proposals(df: pd.DataFrame, top_n: int = 2) -> list:
    """제품 개선 기획안 목록(우선순위 상위 top_n)을 생성한다."""
    scored = [score_priority(c) for c in cluster_candidates(df)]
    # 동점 시 빈도가 높은 클러스터, 그다음 규제 연관성이 높은 클러스터를 우선한다.
    scored.sort(key=lambda c: (c["priority_score"], len(c["vocs"]), c["regulation_score"]), reverse=True)
    return [build_proposal(c) for c in scored[:top_n]]


def render_proposal_doc(proposals: list) -> str:
    """기획안 목록을 product_improvement_plan.md 본문 문자열로 렌더링한다."""
    lines = ["# 제품 개선 기획안\n"]
    lines.append("## 우선순위 판단 기준\n")
    lines.append("- 빈도: 관련 VoC 건수 (1건=1점, 2~3건=2점, 4건 이상=3점)")
    lines.append("- 임팩트: OEM/1차 협력사 포함=3점, 2차 협력사 포함=2점, 기타 중심=1점")
    lines.append("- 긴급도: urgency High 포함=3점, Medium 포함=2점, Low만 있음=1점")
    lines.append("- 규제 연관성: CBAM/CSRD/Scope3/검증 직접 관련=3점, ESG/PCF/LCA 관련=2점, 일반 플랫폼 기능=1점")
    lines.append("- 구현 난이도: 문서/템플릿/FAQ 수준=1점, 화면/리포트 개선=2점, API/복잡한 연동/신규 모듈=3점")
    lines.append("- 최종 점수 산식: `priority_score = frequency_score + impact_score + urgency_score + regulation_score - effort_score`\n")
    lines.append("---\n")

    for i, proposal in enumerate(proposals, start=1):
        c = proposal["content"]
        s = proposal["scores"]

        lines.append(f"## 기획안 {i}. {proposal['title']}\n")
        lines.append("### 1. 문제 정의")
        lines.append(proposal["problem_definition"] + "\n")

        lines.append("### 2. 근거 VoC")
        lines.append("| id | 고객 유형 | 유형 | 긴급도 | VoC 인용 |")
        lines.append("|---|---|---|---|---|")
        for row in proposal["evidence_rows"]:
            lines.append(
                f"| {row['id']} | {row['customer_type']} | {row['voc_type']} | {row['urgency']} | {row['quote']} |"
            )
        lines.append("")

        lines.append("### 3. 개선 제안")
        lines.append(f"- 핵심 기능: {c['key_feature']}")
        lines.append(f"- 화면/UX: {c['ux']}")
        lines.append(f"- 자동화 로직: {c['automation']}")
        lines.append(f"- CS 운영 연계: {c['cs_ops']}\n")

        lines.append("### 4. 기대 효과")
        lines.append(f"- CS팀: {c['effect_cs']}")
        lines.append(f"- 제품팀: {c['effect_product']}")
        lines.append(f"- 고객: {c['effect_customer']}")
        lines.append(f"- 비즈니스: {c['effect_business']}\n")

        lines.append("### 5. 우선순위")
        lines.append(f"- Frequency: {s['frequency_score']} ({s['frequency_note']})")
        lines.append(f"- Impact: {s['impact_score']} ({s['impact_note']})")
        lines.append(f"- Urgency: {s['urgency_score']} ({s['urgency_note']})")
        lines.append(f"- Regulation: {s['regulation_score']} ({s['regulation_note']})")
        lines.append(f"- Effort: {s['effort_score']} ({s['effort_note']})")
        lines.append(f"- Total Score: {s['priority_score']}")
        lines.append(
            "- 판단 근거: 빈도·임팩트·긴급도·규제연관성 대비 구현 난이도가 상대적으로 낮아 "
            "우선순위 상위로 산정되었다.\n"
        )

        lines.append("### 6. MVP 범위")
        lines.append(f"- 1차 구현: {c['mvp_v1']}")
        lines.append(f"- 제외 범위: {c['mvp_excluded']}")
        lines.append(f"- 성공 지표: {c['mvp_success']}\n")

        lines.append("---\n")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="제품 개선 기획안 생성")
    parser.add_argument("--input", default=None, help="분류 결과 CSV 경로 (기본값: output/<mode>/voc_classification.csv)")
    parser.add_argument(
        "--mode", default="original", choices=["original", "augmented"],
        help="산출물 저장 위치: original(제공된 voc.csv) 또는 augmented(synthetic 검증용)",
    )
    parser.add_argument("--top-n", type=int, default=2, help="작성할 기획안 개수 (기본값 2)")
    args = parser.parse_args()

    config.ensure_output_dirs()
    paths = config.output_paths(args.mode)
    input_path = args.input or paths["classified_csv"]

    df = load_classified(input_path)
    proposals = generate_product_proposals(df, top_n=args.top_n)
    doc_md = render_proposal_doc(proposals)
    paths["proposal_md"].write_text(doc_md, encoding="utf-8")

    print(f"[product_plan] {len(proposals)}건 기획안 생성 -> {paths['proposal_md']}")
    for p in proposals:
        print(f"  - {p['title']} (score={p['scores']['priority_score']})")


if __name__ == "__main__":
    main()
