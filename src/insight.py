"""분류·집계 결과를 CS팀/제품팀이 바로 액션을 정할 수 있는 비즈니스 인사이트로 변환하는 모듈.

실행:
    python src/insight.py [--input output/original/voc_classification.csv] [--mode original]

입력: classify.py 결과 + aggregate.build_summary_tables()의 집계 dict
출력: output/<mode>/insight-report.md

LLM API 없이 template-based로 동작한다: 각 인사이트 생성 함수는 수치 조건(건수·비율)을 만족할 때만
결과를 반환하고, context/company-info.md·context/industry-news.md에서 관련 문장을 찾아 인용해
탄소규제 맥락을 반영한다. 조건을 만족하지 않으면 해당 인사이트는 생성하지 않는다(과장 방지).
"""

import argparse
import re

import pandas as pd

import config
import aggregate

# 규제 변화 리스크 인사이트에서 다룰 regulation_context
REGULATION_RISK_CONTEXTS = ["CBAM", "CSRD", "Scope3"]

# 제품 개선 인사이트에서 topic별로 다르게 붙일 비즈니스 해석/권장 액션
TOPIC_BUSINESS_MEANING = {
    "플랫폼 오류/API/권한": (
        "로그인 장애·API 연동 끊김·권한 관리 등 플랫폼 안정성 이슈는 온보딩 초기 신뢰도와 "
        "일일 업무 연속성에 직접 영향을 준다.",
        "플랫폼 오류/API/권한 관련 건은 버그 트래커에 최우선순위로 등록하고, 재발률이 높은 API 연동 "
        "끊김 이슈는 원인 분석(ERP 연동 구조) 후 안정화 스프린트를 배정한다.",
    ),
    "보고서/대시보드": (
        "보고서 커스터마이징·자동화 요구가 반복되는 것은 이사회·감사 보고 주기(분기·연간)와 맞물려 "
        "실제 업무 흐름에서 구조적으로 반복 발생하는 니즈임을 시사한다.",
        "보고서 템플릿 커스터마이징 기능과 분기별 자동 생성 기능을 로드맵에 편성하고, 우선 커스터마이징 "
        "요구가 명확한 건(id043)을 파일럿으로 검증한다.",
    ),
    "Scope 3/공급망 데이터": (
        "협력사 수백 개의 Scope 3 데이터를 수동으로 입력해야 하는 구조는 데이터 신뢰성 저하와 "
        "CS 반복 문의의 근본 원인이 될 수 있다.",
        "협력사 데이터 일괄 요청·자동 수집 기능(대량 발송, 자동 리마인드)을 우선 검토하고, 200개 "
        "협력사 규모의 고객(id008)을 베타 대상으로 삼는다.",
    ),
    "계산 로직/데이터 신뢰성": (
        "동일 항목에서 카본링크 계산값과 외부 기관·경쟁사 산정값의 차이가 반복 제기되는 것은 "
        "계산 로직의 투명성·정확도에 대한 신뢰 이슈로 이어질 수 있다.",
        "계산 로직(GWP 기준치, Scope1/3 산정 방식)을 문서화해 공개하고, 외부 산정값과 차이가 20% "
        "이상인 건(id014, id033)은 원인을 역추적해 계산 엔진을 검증한다.",
    ),
}
DEFAULT_TOPIC_BUSINESS_MEANING = (
    "동일 topic에서 개선 요구가 반복되는 것은 개별 요청이 아니라 구조적 제품 갭일 가능성이 높다.",
    "해당 topic의 VoC를 모아 제품 백로그에 하나의 개선 과제로 등록하고 우선순위를 재평가한다.",
)


def load_classified(input_path) -> pd.DataFrame:
    """classify.py가 생성한 분류 결과 CSV를 읽는다."""
    return pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8")


def load_context_texts() -> dict:
    """context/company-info.md, context/industry-news.md 원문을 읽어 dict로 반환한다."""
    return {
        "company_info": config.COMPANY_INFO_MD.read_text(encoding="utf-8"),
        "industry_news": config.INDUSTRY_NEWS_MD.read_text(encoding="utf-8"),
    }


def _find_context_sentence(text: str, keyword: str) -> str:
    """context 원문에서 keyword가 포함된 줄을 찾아 마크다운 기호를 제거하고 반환한다.

    찾지 못하면 빈 문자열을 반환한다 (해당 문장을 인용하지 않고 건너뛴다).
    """
    if not text:
        return ""
    for line in text.splitlines():
        if keyword in line:
            cleaned = re.sub(r"^[\s\-\d.]+", "", line.strip())  # 리스트 번호("1. ", "- ") 제거
            cleaned = cleaned.replace("**", "")  # 볼드 마크업은 공백 없이 제거
            cleaned = re.sub(r"[|`>#]", " ", cleaned)  # 표/인용 기호는 공백으로 치환
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
            cleaned = re.sub(r"\s+:", ":", cleaned)  # "감지 :" -> "감지:"
            return cleaned
    return ""


def _context_prefix(context_line: str, source: str) -> str:
    """context 인용문을 '(source: 문장) ' 형태로 감싼다. 인용문이 없으면 빈 문자열."""
    return f"({source}: {context_line}) " if context_line else ""


def _short_quote(content: str, max_len: int = 50) -> str:
    """content에서 첫 문장만 추려 짧게 인용한다 (| 문자는 표가 깨지지 않도록 치환)."""
    content = (content or "").strip()
    sentences = re.split(r"(?<=[.?!])\s+", content)
    quote = sentences[0] if sentences and sentences[0] else content
    if len(quote) > max_len:
        quote = quote[:max_len].rstrip() + "..."
    return quote.replace("|", "/")


def _cite(df_subset: pd.DataFrame, k: int = 3) -> list:
    """df_subset 상위 k건을 [{id, quote}] 리스트로 변환한다."""
    cites = []
    for _, row in df_subset.head(k).iterrows():
        cites.append({"id": row["id"], "quote": _short_quote(row.get("content", ""))})
    return cites


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


# ---------------------------------------------------------------------------
# 인사이트 1: 규제 대응 리스크
# ---------------------------------------------------------------------------

def _insight_regulatory_risk(df: pd.DataFrame, summary: dict, context_texts: dict) -> dict:
    total = summary["total_count"]
    reg_df = df[df["regulation_context"].isin(REGULATION_RISK_CONTEXTS)]
    if len(reg_df) < 3:
        return None

    urgent_reg = reg_df[reg_df["urgency"].isin(["High", "Medium"])]
    by_reg_counts = reg_df["regulation_context"].value_counts()
    top_context = by_reg_counts.index[0]
    top_context_count = int(by_reg_counts.iloc[0])

    news = context_texts.get("industry_news", "")
    context_line = (
        _find_context_sentence(news, "본격 과금 시작")
        or _find_context_sentence(news, "확정 시행")
        or _find_context_sentence(news, top_context)
    )

    priority_cites = pd.concat([urgent_reg, reg_df]).drop_duplicates(subset="id")

    return {
        "title": f"{top_context} 관련 문의·불만 집중, 확정 시행 리스크 구간 진입",
        "observation": (
            f"CBAM/CSRD/Scope3 규제 관련 VoC가 전체 {total}건 중 {len(reg_df)}건"
            f"({_pct(len(reg_df), total)}%)이며, 그중 '{top_context}' 맥락이 {top_context_count}건으로 가장 많다."
        ),
        "evidence": (
            f"규제 관련 VoC {len(reg_df)}건 중 urgency Medium 이상이 {len(urgent_reg)}건"
            f"({_pct(len(urgent_reg), len(reg_df))}%). 대표 사례: id010(EU 세관 반려), id045(신고 마감 초과)."
        ),
        "business_meaning": (
            _context_prefix(context_line, "산업 동향")
            + "규제 확정 시행 시점과 맞물려 신고 절차·인증서·제출 양식 관련 혼란이 CS 부담과 "
            "계약 리스크(반려, 마감 지연)로 이어질 수 있다."
        ),
        "recommended_action": (
            f"'{top_context}' 신고 절차/제출 양식에 대한 표준 가이드를 우선 제작하고, EU 세관 반려·마감 "
            "초과처럼 계약 리스크로 직결되는 건은 컨설팅팀이 개별 대응 SLA를 적용한다."
        ),
        "related_vocs": _cite(priority_cites, 3),
    }


# ---------------------------------------------------------------------------
# 인사이트 2: 제품 개선
# ---------------------------------------------------------------------------

def _insight_product_improvement(df: pd.DataFrame, summary: dict, context_texts: dict) -> dict:
    total = summary["total_count"]
    candidates = summary["product_candidate_vocs"]
    if len(candidates) < 3:
        return None

    topic_counts = candidates["topic"].value_counts()
    top_topic = topic_counts.index[0]
    top_topic_count = int(topic_counts.iloc[0])
    business_meaning, recommended_action = TOPIC_BUSINESS_MEANING.get(top_topic, DEFAULT_TOPIC_BUSINESS_MEANING)

    return {
        "title": f"제품 개선 신호 집중: '{top_topic}'",
        "observation": (
            f"불만·기능 요청 중 제품/기능/데이터 신뢰성과 직결되는 VoC가 {len(candidates)}건"
            f"({_pct(len(candidates), total)}%)이며, '{top_topic}' 주제가 {top_topic_count}건으로 가장 많다."
        ),
        "evidence": (
            f"'{top_topic}' 관련 {top_topic_count}건이 불만·기능 요청 후보 {len(candidates)}건 중 "
            f"{_pct(top_topic_count, len(candidates))}%를 차지한다."
        ),
        "business_meaning": business_meaning,
        "recommended_action": recommended_action,
        "related_vocs": _cite(candidates[candidates["topic"] == top_topic], 3),
    }


# ---------------------------------------------------------------------------
# 인사이트 3: CS 운영
# ---------------------------------------------------------------------------

def _insight_cs_operations(df: pd.DataFrame, summary: dict, context_texts: dict) -> dict:
    total = summary["total_count"]
    faq = summary["faq_candidate_vocs"]
    if len(faq) < 3:
        return None

    top_topic = faq["topic"].value_counts().index[0]
    top_topic_count = int(faq["topic"].value_counts().iloc[0])

    company_info = context_texts.get("company_info", "")
    context_line = _find_context_sentence(company_info, "처음 경험")

    return {
        "title": "단순 정보 확인형 문의의 FAQ/가이드 전환 여지",
        "observation": (
            f"전체 VoC {total}건 중 {len(faq)}건({_pct(len(faq), total)}%)이 단순 정보 확인형 문의(일반 문의 "
            f"또는 가이드 요청)이며, '{top_topic}' 주제가 {top_topic_count}건으로 가장 많다."
        ),
        "evidence": (
            f"FAQ/가이드화 후보 {len(faq)}건 중 '{top_topic}' 관련 {top_topic_count}건"
            f"({_pct(top_topic_count, len(faq))}%)이 반복되는 절차성 질문이다."
        ),
        "business_meaning": (
            _context_prefix(context_line, "회사 컨텍스트")
            + "반복되는 절차 문의를 지식베이스로 전환하면 신규 CS 담당자의 도메인 학습 부담과 "
            "1건당 응대 시간을 함께 줄일 수 있다."
        ),
        "recommended_action": (
            f"'{top_topic}' 주제를 포함한 상위 문의 패턴을 카본링크 헬프센터 FAQ로 우선 전환하고, "
            "반복 빈도가 높은 항목은 챗봇/자동 응답 초안을 마련한다."
        ),
        "related_vocs": _cite(faq[faq["topic"] == top_topic], 3),
    }


# ---------------------------------------------------------------------------
# 인사이트 4: 이탈 위험
# ---------------------------------------------------------------------------

def _insight_churn_risk(df: pd.DataFrame, summary: dict, context_texts: dict) -> dict:
    high_risk = summary["high_risk_vocs"]
    if high_risk.empty:
        return None

    complaint_total = int(
        summary["by_type"].loc[summary["by_type"]["voc_type"] == "불만", "count"].sum()
    )
    company_info = context_texts.get("company_info", "")
    context_line = _find_context_sentence(company_info, "이탈 위험")

    return {
        "title": "OEM/1차 협력사의 고긴급도 불만 - 이탈 위험 신호",
        "observation": (
            f"불만 {complaint_total}건 중 OEM/1차 협력사에서 발생한 urgency High 건이 {len(high_risk)}건 "
            f"확인된다."
        ),
        "evidence": (
            "id "
            + ", ".join(high_risk["id"].tolist())
            + " — EU 세관 반려·인증 데이터 내보내기 실패·신고 마감 초과 등 계약·업무 리스크로 직결되는 사례."
        ),
        "business_meaning": (
            _context_prefix(context_line, "회사 컨텍스트")
            + "고가치 협력사의 고긴급도 불만은 처리 지연 시 계약 갱신율(NRR) 저하나 이탈로 이어질 수 있는 "
            "선행 신호다."
        ),
        "recommended_action": (
            "해당 건은 SLA 24시간 이내 전담 대응을 적용하고, 처리 완료 후 CSM이 후속 만족도 체크를 진행해 "
            "이탈 신호를 조기에 해소한다."
        ),
        "related_vocs": _cite(high_risk, 3),
    }


# ---------------------------------------------------------------------------
# 인사이트 5: 고객 성공/마케팅
# ---------------------------------------------------------------------------

def _insight_customer_success(df: pd.DataFrame, summary: dict, context_texts: dict) -> dict:
    total = summary["total_count"]
    praise = df[df["voc_type"] == "칭찬"]
    if len(praise) < 3:
        return None

    company_info = context_texts.get("company_info", "")
    context_line = _find_context_sentence(company_info, "영업 레퍼런스")

    # 정량적 성과(수치·업무 시간 절감 등)가 언급된 칭찬 VoC를 우선 인용 대상으로 삼는다.
    quantified = praise[praise["content"].str.contains(r"\d+%|절반|줄었", regex=True, na=False)]
    cite_source = quantified if not quantified.empty else praise

    return {
        "title": "칭찬 VoC 중 세일즈 레퍼런스 활용 가능 소재",
        "observation": (
            f"칭찬 VoC {len(praise)}건({_pct(len(praise), total)}%) 중 온보딩 응대, 업무 자동화, 보고서 "
            f"품질 개선 등 정량적 성과가 언급된 사례가 {len(quantified)}건 확인된다."
        ),
        "evidence": (
            "id " + ", ".join(cite_source.head(3)["id"].tolist())
            + " — 업무 시간 절감·오류 감소·배출량 감소 파악 등 구체적 수치가 포함된 후기."
        ),
        "business_meaning": (
            _context_prefix(context_line, "회사 컨텍스트")
            + "정량적 성과가 포함된 칭찬 후기는 별도 인터뷰 없이도 세일즈 케이스 스터디·마케팅 콘텐츠의 "
            "1차 소재로 바로 활용할 수 있다."
        ),
        "recommended_action": (
            "위 사례를 고객 동의 하에 케이스 스터디로 재구성해 세일즈/마케팅팀에 전달하고, 레퍼런스 콜이 "
            "가능한 고객인지 CSM이 확인한다."
        ),
        "related_vocs": _cite(cite_source, 3),
    }


INSIGHT_GENERATORS = [
    _insight_regulatory_risk,
    _insight_product_improvement,
    _insight_cs_operations,
    _insight_churn_risk,
    _insight_customer_success,
]


def generate_business_insights(df: pd.DataFrame, summary_tables: dict, context_texts: dict) -> list:
    """5종 인사이트 생성기를 실행해, 조건을 만족하는 인사이트만 dict 리스트로 반환한다."""
    insights = []
    for generator in INSIGHT_GENERATORS:
        result = generator(df, summary_tables, context_texts)
        if result:
            insights.append(result)
    return insights


def generate_insights(df: pd.DataFrame, min_count: int = 3) -> list:
    """standalone 실행 편의용 래퍼: 집계·context를 자체적으로 준비해 인사이트를 생성한다."""
    summary_tables = aggregate.build_summary_tables(df)
    context_texts = load_context_texts()
    return generate_business_insights(df, summary_tables, context_texts)


def render_insight_report(insights: list) -> str:
    """인사이트 목록을 insight-report.md 본문 문자열로 렌더링한다."""
    if not insights:
        return "# CSRD·CBAM 맥락 VoC 인사이트\n\n생성된 인사이트가 없습니다 (데이터 조건 미충족).\n"

    lines = ["# CSRD·CBAM 맥락 VoC 인사이트\n"]
    for i, insight in enumerate(insights, start=1):
        quotes = ", ".join(f"id {c['id']}(\"{c['quote']}\")" for c in insight["related_vocs"])
        lines.append(f"## Insight {i}. {insight['title']}\n")
        lines.append(f"- 관찰: {insight['observation']}")
        lines.append(f"- 근거 데이터: {insight['evidence']}")
        lines.append(f"- 비즈니스 의미: {insight['business_meaning']}")
        lines.append(f"- 권장 액션: {insight['recommended_action']}")
        lines.append(f"- 관련 VoC 예시: {quotes}\n")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="CSRD·CBAM 맥락 인사이트 생성")
    parser.add_argument("--input", default=None, help="분류 결과 CSV 경로 (기본값: output/<mode>/voc_classification.csv)")
    parser.add_argument(
        "--mode", default="original", choices=["original", "augmented"],
        help="산출물 저장 위치: original(제공된 voc.csv) 또는 augmented(synthetic 검증용)",
    )
    args = parser.parse_args()

    config.ensure_output_dirs()
    paths = config.output_paths(args.mode)
    input_path = args.input or paths["classified_csv"]

    df = load_classified(input_path)
    summary_tables = aggregate.build_summary_tables(df)
    context_texts = load_context_texts()

    insights = generate_business_insights(df, summary_tables, context_texts)
    report_md = render_insight_report(insights)
    paths["insight_report_md"].write_text(report_md, encoding="utf-8")

    print(f"[insight] {len(insights)}개 인사이트 생성 -> {paths['insight_report_md']}")


if __name__ == "__main__":
    main()
