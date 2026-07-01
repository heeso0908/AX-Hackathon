"""CarbonLink 주간 VoC 리포트(weekly_voc_report.md) 생성 모듈.

실행:
    python src/report.py [--mode original]

입력: clean/classify/aggregate/insight/product_plan 각 단계의 결과를 이 모듈이 직접 재실행해 조합한다
      (항상 최신 입력 CSV 기준으로 일관된 리포트를 만들기 위함).
출력: output/<mode>/weekly_voc_report.md

CS 담당자·제품팀·리더가 5분 안에 읽을 수 있도록 수치 중심으로 간결하게 작성한다.
"""

import argparse
import re

import pandas as pd

import config
import clean
import classify
import aggregate
import insight
import product_plan

INPUT_CSV_BY_MODE = {
    "original": config.DEFAULT_INPUT_CSV,
    "augmented": config.SYNTHETIC_INPUT_CSV,
}

# 유형 비중 요약에 쓸 표기 순서 (Executive Summary 문구 기준)
SUMMARY_TYPE_ORDER = ["불만", "기능 요청", "일반 문의", "칭찬"]

# CS 우선 대응 Queue의 topic별 권장 응대 방향
RESPONSE_GUIDE_BY_TOPIC = {
    "CBAM 신고/인증서": "CBAM 신고 절차·반려 사유를 1:1로 확인하고 필요 시 컨설팅팀 우선 확인 요청",
    "플랫폼 오류/API/권한": "장애 원인 확인 후 임시 해결 방법 안내, 엔지니어링팀에 즉시 공유",
    "검증/인증/감사": "인증 제출용 데이터 이슈 확인 후 대체 제출 방법 안내",
    "계산 로직/데이터 신뢰성": "계산 근거 자료를 개별 회신하고 데이터 신뢰성 담당자에게 케이스 전달",
}
DEFAULT_RESPONSE_GUIDE = "24시간 이내 개별 회신, 필요 시 전담 담당자 배정"

# 제품팀 전달 후보의 topic -> product_plan 클러스터 제목 매핑 (product_plan.py와 동기화)
TOPIC_TO_CLUSTER_TITLE = {
    topic: cluster["title"] for cluster in product_plan.CLUSTER_DEFINITIONS for topic in cluster["topics"]
}
DEFAULT_CLUSTER_NOTE = "제품 개선 과제 신규 후보로 등록 검토"


def _short_quote(content: str, max_len: int = 40) -> str:
    """content에서 첫 문장만 추려 표에 넣기 좋게 짧게 인용한다 (| 문자는 표가 깨지지 않도록 치환)."""
    content = (content or "").strip()
    sentences = re.split(r"(?<=[.?!])\s+", content)
    quote = sentences[0] if sentences and sentences[0] else content
    if len(quote) > max_len:
        quote = quote[:max_len].rstrip() + "..."
    return quote.replace("|", "/")


def default_week_label(classified_df: pd.DataFrame) -> str:
    """date_clean 최소~최대 값으로 리포트 기간 라벨을 자동 생성한다."""
    if "date_clean" not in classified_df.columns:
        return "기간 미확인"
    valid = classified_df["date_clean"][classified_df["date_clean"] != ""]
    if valid.empty:
        return "기간 미확인"
    return f"{valid.min()} ~ {valid.max()}"


def load_all_outputs(mode: str) -> dict:
    """해당 mode의 정제/분류/집계/인사이트/기획안 산출물을 모두 계산해 dict로 반환한다."""
    input_path = INPUT_CSV_BY_MODE[mode]
    raw_df = clean.load_voc(input_path)
    clean_df, quality_summary = clean.clean_voc(raw_df)
    classified_df = classify.classify_voc(clean_df)
    summary = aggregate.build_summary_tables(classified_df)
    context_texts = insight.load_context_texts()
    insights = insight.generate_business_insights(classified_df, summary, context_texts)
    proposals = product_plan.generate_product_proposals(classified_df)

    return build_report_context(mode, quality_summary, classified_df, summary, insights, proposals)


def build_report_context(mode: str, quality_summary: dict, classified_df: pd.DataFrame, summary: dict,
                          insights: list, proposals: list, week_label: str = None) -> dict:
    """run_pipeline.py처럼 이미 계산된 결과가 있을 때, 재계산 없이 리포트 컨텍스트를 구성한다."""
    return {
        "mode": mode,
        "quality_summary": quality_summary,
        "classified_df": classified_df,
        "summary": summary,
        "insights": insights,
        "proposals": proposals,
        "week_label": week_label or default_week_label(classified_df),
    }


# ---------------------------------------------------------------------------
# 섹션별 렌더링
# ---------------------------------------------------------------------------

def _render_executive_summary(context: dict) -> str:
    summary = context["summary"]
    by_type = summary["by_type"].set_index("voc_type")
    total = summary["total_count"]

    type_line = " / ".join(
        f"{t} {int(by_type.loc[t, 'count'])}건({by_type.loc[t, 'pct']}%)" for t in SUMMARY_TYPE_ORDER
    )
    top_issues = "\n".join(f"  {i}. {ins['title']}" for i, ins in enumerate(context["insights"][:3], start=1))

    return (
        f"- 이번 주 총 VoC: {total}건\n"
        f"- 유형 비중: {type_line}\n"
        f"- High urgency 건수: {summary['cs_immediate_count']}건\n"
        f"- 제품팀 전달 필요 건수: {summary['product_candidate_count']}건\n"
        f"- 이번 주 핵심 이슈 3줄 요약:\n{top_issues}"
    )


def _render_data_quality_summary(quality_summary: dict) -> str:
    before = quality_summary["row_count_before"]
    after = quality_summary["row_count_after"]
    removed = before - after
    fmt_counts = quality_summary["date_format_counts"]
    mixed = fmt_counts.get("slash", 0) + fmt_counts.get("korean", 0)
    channel_missing = len(quality_summary["channel_missing_ids"])

    return (
        f"- 원본 행 수: {before}건\n"
        f"- 중복 제거: {removed}건 (content 완전 중복 → 최초 접수 건만 유지)\n"
        f"- 날짜 표준화: {mixed}건을 YYYY-MM-DD로 통일 (slash {fmt_counts.get('slash', 0)}건, "
        f"한글 표기 {fmt_counts.get('korean', 0)}건)\n"
        f"- 채널 결측 처리: {channel_missing}건 → '미기재'로 채움\n"
        f"- 분석 대상 최종 행 수: {after}건"
    )


def _render_data_overview(context: dict) -> str:
    quality_summary = context["quality_summary"]
    week_label = context.get("week_label") or default_week_label(context["classified_df"])
    before = quality_summary["row_count_before"]
    cleaning_summary = _render_data_quality_summary(quality_summary).splitlines()
    cleaning_lines = "; ".join(line.removeprefix("- ").strip() for line in cleaning_summary)
    return (
        f"- 분석 대상: data/voc.csv ({before}건)\n"
        f"- 분석 기간: {week_label}\n"
        f"- 데이터 정제 내용: {cleaning_lines}"
    )


def _render_classification_table(classified_df: pd.DataFrame) -> str:
    if "date_clean" in classified_df.columns:
        report_dates = classified_df["date_clean"]
    elif "date" in classified_df.columns:
        report_dates = classified_df["date"]
    else:
        report_dates = pd.Series([""] * len(classified_df))

    table_df = pd.DataFrame(
        {
            "id": classified_df["id"],
            "date": report_dates,
            "customer_type": classified_df["customer_type"],
            "content 요약 (30자)": classified_df["content"].apply(lambda value: _short_quote(value, max_len=30)),
            "분류 유형": classified_df["voc_type"],
        }
    )
    return table_df.to_markdown(index=False)


def _render_type_status(summary: dict) -> str:
    return summary["by_type"].rename(columns={"voc_type": "유형", "count": "건수", "pct": "비율(%)"}).to_markdown(
        index=False
    )


def _render_three_insights(insights: list) -> str:
    if not insights:
        return "이번 주 생성된 인사이트가 없습니다."

    blocks = []
    for index, ins in enumerate(insights[:3], start=1):
        blocks.append(
            f"### 인사이트 {index}\n"
            f"- **내용**: {ins['title']}\n"
            f"- **근거**: {ins['observation']}\n"
            f"- **비즈니스 의미**: {ins['business_meaning']}"
        )
    return "\n\n".join(blocks)


def _render_topic_regulation(summary: dict) -> str:
    top_topics = summary["top_topics"].rename(columns={"topic": "topic", "count": "건수", "pct": "비율(%)"})
    reg = summary["by_regulation_context"].head(5).rename(
        columns={"regulation_context": "regulation_context", "count": "건수", "pct": "비율(%)"}
    )
    return (
        "**주요 topic (상위 5개)**\n\n"
        + top_topics.to_markdown(index=False)
        + "\n\n**규제 Context (상위 5개)**\n\n"
        + reg.to_markdown(index=False)
    )


def _render_cs_queue(summary: dict) -> str:
    cs_vocs = summary["cs_immediate_vocs"]
    if cs_vocs.empty:
        return "이번 주 urgency High 건이 없습니다."

    header = "| id | date_clean | customer_type | topic | urgency | content 요약 | 권장 응대 방향 |\n|---|---|---|---|---|---|---|"
    rows = []
    for _, row in cs_vocs.iterrows():
        guide = RESPONSE_GUIDE_BY_TOPIC.get(row["topic"], DEFAULT_RESPONSE_GUIDE)
        rows.append(
            f"| {row['id']} | {row['date_clean']} | {row['customer_type']} | {row['topic']} | "
            f"{row['urgency']} | {_short_quote(row['content'])} | {guide} |"
        )
    return header + "\n" + "\n".join(rows)


def _render_product_candidates(summary: dict) -> str:
    candidates = summary["product_candidate_vocs"]
    if candidates.empty:
        return "이번 주 제품팀 전달 후보가 없습니다."

    header = "| id | topic | voc_type | customer_type | 근거 | 제품팀 검토 포인트 |\n|---|---|---|---|---|---|"
    rows = []
    for _, row in candidates.iterrows():
        review_point = TOPIC_TO_CLUSTER_TITLE.get(row["topic"], DEFAULT_CLUSTER_NOTE)
        rows.append(
            f"| {row['id']} | {row['topic']} | {row['voc_type']} | {row['customer_type']} | "
            f"{_short_quote(row['content'])} | {review_point} |"
        )
    return header + "\n" + "\n".join(rows)


def _render_faq_candidates(summary: dict) -> str:
    faq = summary["faq_candidate_vocs"]
    if faq.empty:
        return "이번 주 FAQ/가이드 후보가 없습니다."

    header = "| topic | 관련 VoC 수 | 고객 질문 | 추천 콘텐츠 |\n|---|---|---|---|"
    rows = []
    grouped = faq.groupby("topic").size().sort_values(ascending=False)
    for topic, count in grouped.items():
        example = faq[faq["topic"] == topic].iloc[0]
        rows.append(
            f"| {topic} | {count} | {_short_quote(example['content'])} | '{topic}' 절차 안내 FAQ/가이드 |"
        )
    return header + "\n" + "\n".join(rows)


def _render_decision_log_summary() -> str:
    return (
        "- 분류 우선순위는 `불만 → 기능 요청 → 칭찬 → 일반 문의` 순으로 적용한다.\n"
        "- 혼합 케이스는 이탈 위험이 큰 신호를 우선 반영하고, 보조 의도는 `sub_intent`로 남긴다.\n"
        "- 긴급도는 마감·반려·업무 마비·오류 같은 문면 신호 중심으로 판단한다.\n"
        "- 고객 영향도는 고객군, 긴급도, 반복 업무 표현을 함께 반영한다.\n"
        "- 자세한 기준·근거는 `output/decisions.md`를 참고한다."
    )


def _render_business_insights(insights: list) -> str:
    if not insights:
        return "이번 주 생성된 인사이트가 없습니다."

    blocks = []
    for i, ins in enumerate(insights, start=1):
        blocks.append(
            f"**{i}. {ins['title']}**\n"
            f"- {ins['observation']}\n"
            f"- 비즈니스 의미: {ins['business_meaning']}\n"
            f"- 권장 액션: {ins['recommended_action']}"
        )
    return "\n\n".join(blocks)


def _render_next_actions(context: dict) -> str:
    summary = context["summary"]
    proposals = context["proposals"]
    insights = context["insights"]

    top_proposal = proposals[0]["title"] if proposals else "제품 개선 기획안 검토"
    top_score = proposals[0]["scores"]["priority_score"] if proposals else "-"

    success_insight = next((i for i in insights if "세일즈" in i["title"] or "레퍼런스" in i["title"]), None)
    content_basis = (
        f"'{success_insight['title']}' 인사이트 기반 케이스 스터디 제작"
        if success_insight
        else "칭찬 VoC 케이스 스터디 소재 검토"
    )

    header = "| 담당 | 액션 | 우선순위 | 근거 |\n|---|---|---|---|"
    rows = [
        f"| CS | High urgency {summary['cs_immediate_count']}건 24시간 내 개별 회신 | High | urgency High = 이탈·계약 리스크 직결 |",
        f"| Product | '{top_proposal}' 기획안 검토 (score={top_score}) | High | 근거 VoC {summary['product_candidate_count']}건, 우선순위 산정 기준은 decisions.md 참고 |",
        f"| Content/Marketing | {content_basis} | Medium | 칭찬 VoC {int(summary['by_type'].set_index('voc_type').loc['칭찬', 'count'])}건 중 세일즈 레퍼런스 소재 확인 |",
    ]
    return header + "\n" + "\n".join(rows)


def _render_appendix(mode: str) -> str:
    return (
        "**분류 기준 요약** (자세한 기준·근거는 `output/decisions.md` 참고)\n"
        "- 불만: 장애·오류·불편·마비·반려 등 명확한 부정 신호\n"
        "- 기능 요청: 기능 추가·가이드·템플릿·자동화 등 제공 요청 신호\n"
        "- 칭찬: 감사·만족·품질 향상 등 긍정 신호\n"
        "- 일반 문의: 위 신호가 없는 정보 확인형 질문 (기본값)\n\n"
        "**자동화 실행 명령어**\n"
        "```bash\n"
        f"python src/run_pipeline.py --input data/voc.csv --output output/{mode} --dataset-label {mode} --default-year 2026\n"
        "# 단계별 실행 (동일한 폴더 규칙을 --mode로 참조)\n"
        f"python src/clean.py --mode {mode}\n"
        f"python src/classify.py --mode {mode}\n"
        f"python src/aggregate.py --mode {mode}\n"
        f"python src/insight.py --mode {mode}\n"
        f"python src/product_plan.py --mode {mode}\n"
        f"python src/report.py --mode {mode}\n"
        "```"
    )


def render_voc_report(context: dict) -> str:
    """output/template.md 형식에 맞춰 최종 weekly_voc_report.md 본문을 렌더링한다."""
    summary = context["summary"]
    quality_summary = context["quality_summary"]

    week_label = context.get("week_label") or default_week_label(context["classified_df"])

    sections = [
        f"# CarbonLink 주간 VoC 리포트 ({week_label})\n",
        "## 1. Executive Summary\n" + _render_executive_summary(context),
        "## 2. 데이터 개요\n" + _render_data_overview(context),
        "## 3. VoC 유형별 분류표\n" + _render_classification_table(context["classified_df"]),
        "## 4. 유형별 건수·비율 요약\n" + _render_type_status(summary),
        "## 5. 탄소규제 맥락 인사이트 3개\n" + _render_three_insights(context["insights"]),
        "## 6. 의사결정 로그 요약\n" + _render_decision_log_summary(),
        "## 7. 주요 Topic 및 규제 Context\n" + _render_topic_regulation(summary),
        "## 8. CS 우선 대응 Queue\n" + _render_cs_queue(summary),
        "## 9. 제품팀 전달 후보\n" + _render_product_candidates(summary),
        "## 10. FAQ/가이드 콘텐츠 후보\n" + _render_faq_candidates(summary),
        "## 11. 비즈니스 인사이트\n" + _render_business_insights(context["insights"]),
        "## 12. 다음 액션\n" + _render_next_actions(context),
        "## 13. Appendix\n" + _render_appendix(context["mode"]),
    ]
    return "\n\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="CarbonLink 주간 VoC 리포트 생성")
    parser.add_argument(
        "--mode", default="original", choices=["original", "augmented"],
        help="렌더링할 산출물 위치: original(제공된 voc.csv) 또는 augmented(synthetic 검증용)",
    )
    args = parser.parse_args()

    config.ensure_output_dirs()
    paths = config.output_paths(args.mode)

    context = load_all_outputs(args.mode)
    report_md = render_voc_report(context)
    paths["voc_report_md"].write_text(report_md, encoding="utf-8")

    print(f"[report] weekly report: {paths['voc_report_md']}")


if __name__ == "__main__":
    main()
