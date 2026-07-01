"""VoC 분류 결과 집계 모듈.

실행:
    python src/aggregate.py [--input output/original/voc_classification.csv] [--mode original]

입력: classify.py가 생성한 voc_classification.csv
출력: output/<mode>/voc-summary.csv (유형별 건수·비율)

`build_summary_tables(df)`가 반환하는 dict는 report.py(주간 리포트)와 product_plan.py
(기획안 근거 VoC 추출)에서 그대로 재사용한다. 모든 표는 pandas DataFrame이며
`.to_markdown()`으로 바로 마크다운 표로 변환할 수 있다 (requirements.txt의 tabulate 사용).
"""

import argparse

import pandas as pd

import config

# 제품팀 전달 대상으로 볼 topic (제품/기능/데이터 신뢰성과 직결되는 영역).
# CBAM/CSRD 신고 절차 관련 문의(topic="CBAM 신고/인증서" 등)는 컨설팅·가이드 영역이라 제외하고,
# 카본링크 "제품" 자체의 기능·데이터·계산 신뢰도에 관한 topic만 포함한다.
PRODUCT_RELATED_TOPICS = [
    "계산 로직/데이터 신뢰성",
    "검증/인증/감사",
    "보고서/대시보드",
    "플랫폼 오류/API/권한",
    "Scope 3/공급망 데이터",
]

# 이탈 위험 신호를 매길 고가치 고객 세그먼트
HIGH_VALUE_CUSTOMER_TYPES = ["OEM", "1차 협력사"]

# 규제 변화 감지 신호를 추적할 regulation_context
REGULATION_TREND_CONTEXTS = ["CBAM", "CSRD", "Scope3"]


def load_classified(input_path) -> pd.DataFrame:
    """classify.py가 생성한 분류 결과 CSV를 읽는다."""
    return pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8")


def _count_table(series: pd.Series, value_col: str, order: list = None) -> pd.DataFrame:
    """value_counts를 [value_col, count, pct] 형태의 마크다운 친화적 DataFrame으로 변환한다."""
    counts = series.value_counts()
    if order:
        counts = counts.reindex(order).fillna(0).astype(int)
    total = int(counts.sum())
    out = counts.reset_index()
    out.columns = [value_col, "count"]
    out["pct"] = (out["count"] / total * 100).round(1) if total else 0.0
    return out


def aggregate_by_type(df: pd.DataFrame) -> pd.DataFrame:
    """voc_type별 건수·비율을 집계한다 (필수 집계 2)."""
    return _count_table(df["voc_type"], "voc_type", order=config.VOC_TYPES)


def aggregate_by_channel(df: pd.DataFrame) -> pd.DataFrame:
    """channel별 건수를 집계한다 (필수 집계 3)."""
    return _count_table(df["channel"], "channel")


def aggregate_by_customer_type(df: pd.DataFrame) -> pd.DataFrame:
    """customer_type별 건수를 집계한다 (필수 집계 4)."""
    return _count_table(df["customer_type"], "customer_type", order=config.CUSTOMER_TYPES)


def aggregate_by_topic(df: pd.DataFrame) -> pd.DataFrame:
    """topic별 건수를 집계한다 (필수 집계 5)."""
    return _count_table(df["topic"], "topic")


def aggregate_by_regulation_context(df: pd.DataFrame) -> pd.DataFrame:
    """regulation_context별 건수를 집계한다 (필수 집계 6)."""
    return _count_table(df["regulation_context"], "regulation_context")


def aggregate_by_urgency(df: pd.DataFrame) -> pd.DataFrame:
    """urgency별 건수를 집계한다 (필수 집계 7)."""
    return _count_table(df["urgency"], "urgency", order=["High", "Medium", "Low"])


def aggregate_by_week(df: pd.DataFrame) -> pd.DataFrame:
    """week 컬럼 기준 주간 건수를 집계한다 (Standard 주간 리포트용)."""
    if "week" not in df.columns:
        return pd.DataFrame(columns=["week", "count"])
    counts = df["week"].value_counts().sort_index()
    out = counts.reset_index()
    out.columns = ["week", "count"]
    return out


def crosstab_type_topic(df: pd.DataFrame) -> pd.DataFrame:
    """voc_type x topic 교차표를 생성한다 (필수 집계 8)."""
    ct = pd.crosstab(df["voc_type"], df["topic"])
    return ct.reindex(config.VOC_TYPES).fillna(0).astype(int).reset_index()


def crosstab_customer_urgency(df: pd.DataFrame) -> pd.DataFrame:
    """customer_type x urgency 교차표를 생성한다 (필수 집계 9)."""
    ct = pd.crosstab(df["customer_type"], df["urgency"])
    ordered_cols = [c for c in ["High", "Medium", "Low"] if c in ct.columns]
    return ct.reindex(config.CUSTOMER_TYPES).fillna(0).astype(int)[ordered_cols].reset_index()


# ---------------------------------------------------------------------------
# 실무형 지표
# ---------------------------------------------------------------------------

def get_top_topics(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """건수가 많은 상위 n개 topic을 반환한다."""
    return aggregate_by_topic(df).head(n)


def get_high_risk_vocs(df: pd.DataFrame) -> pd.DataFrame:
    """이탈 위험 신호: 불만 + urgency=High + OEM/1차 협력사."""
    mask = (
        (df["voc_type"] == "불만")
        & (df["urgency"] == "High")
        & (df["customer_type"].isin(HIGH_VALUE_CUSTOMER_TYPES))
    )
    return df[mask].copy()


def get_product_candidate_vocs(df: pd.DataFrame) -> pd.DataFrame:
    """제품팀 전달 후보: 불만/기능 요청 + 제품·기능·데이터 신뢰성 관련 topic."""
    mask = df["voc_type"].isin(["불만", "기능 요청"]) & df["topic"].isin(PRODUCT_RELATED_TOPICS)
    return df[mask].copy()


def get_faq_candidate_vocs(df: pd.DataFrame) -> pd.DataFrame:
    """FAQ/가이드화 후보: 일반 문의 전체 + sub_intent에 '가이드'가 포함된 건."""
    mask = (df["voc_type"] == "일반 문의") | df["sub_intent"].fillna("").str.contains("가이드")
    return df[mask].copy()


def get_churn_risk_count(df: pd.DataFrame) -> int:
    """이탈 위험 신호 건수 (get_high_risk_vocs의 건수만 필요할 때 사용)."""
    return len(get_high_risk_vocs(df))


def get_cs_immediate_vocs(df: pd.DataFrame) -> pd.DataFrame:
    """CS 즉시 대응 필요: urgency == High 전체."""
    return df[df["urgency"] == "High"].copy()


def get_regulation_trend(df: pd.DataFrame) -> pd.DataFrame:
    """규제 변화 감지 신호: CBAM/CSRD/Scope3 관련 불만·문의를 주차별로 집계하고,
    직전 주 대비 증가 여부(increasing)를 표시한다.
    """
    mask = df["voc_type"].isin(["불만", "일반 문의"]) & df["regulation_context"].isin(REGULATION_TREND_CONTEXTS)
    subset = df[mask]
    if subset.empty or "week" not in subset.columns:
        return pd.DataFrame(columns=["week", "regulation_context", "count", "increasing"])

    weekly = (
        subset.groupby(["week", "regulation_context"]).size().reset_index(name="count").sort_values(["regulation_context", "week"])
    )
    weekly["increasing"] = weekly.groupby("regulation_context")["count"].diff().fillna(0) > 0
    return weekly.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 종합
# ---------------------------------------------------------------------------

def build_summary_tables(df: pd.DataFrame) -> dict:
    """모든 집계·실무형 지표를 dict로 모아 반환한다 (report.py / product_plan.py 공용).

    key는 두 그룹으로 나뉜다:
    - 표(DataFrame): by_type, by_channel, by_customer_type, by_topic,
      by_regulation_context, by_urgency, by_week, crosstab_type_topic,
      crosstab_customer_urgency, top_topics, regulation_trend
    - VoC 원본 서브셋(DataFrame): high_risk_vocs, product_candidate_vocs,
      faq_candidate_vocs, cs_immediate_vocs
    - 스칼라 지표(int): total_count, cs_immediate_count, product_candidate_count,
      faq_candidate_count, churn_risk_count
    """
    high_risk = get_high_risk_vocs(df)
    product_candidates = get_product_candidate_vocs(df)
    faq_candidates = get_faq_candidate_vocs(df)
    cs_immediate = get_cs_immediate_vocs(df)

    return {
        "total_count": len(df),
        "by_type": aggregate_by_type(df),
        "by_channel": aggregate_by_channel(df),
        "by_customer_type": aggregate_by_customer_type(df),
        "by_topic": aggregate_by_topic(df),
        "by_regulation_context": aggregate_by_regulation_context(df),
        "by_urgency": aggregate_by_urgency(df),
        "by_week": aggregate_by_week(df),
        "crosstab_type_topic": crosstab_type_topic(df),
        "crosstab_customer_urgency": crosstab_customer_urgency(df),
        "top_topics": get_top_topics(df),
        "regulation_trend": get_regulation_trend(df),
        "high_risk_vocs": high_risk,
        "product_candidate_vocs": product_candidates,
        "faq_candidate_vocs": faq_candidates,
        "cs_immediate_vocs": cs_immediate,
        "cs_immediate_count": len(cs_immediate),
        "product_candidate_count": len(product_candidates),
        "faq_candidate_count": len(faq_candidates),
        "churn_risk_count": len(high_risk),
    }


def aggregate_voc(df: pd.DataFrame) -> dict:
    """build_summary_tables의 별칭 (run_pipeline.py 등 다른 모듈과의 호출 규약 유지)."""
    return build_summary_tables(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="VoC 분류 결과 집계")
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
    summary = build_summary_tables(df)
    summary["by_type"].to_csv(paths["summary_csv"], index=False, encoding="utf-8")

    print(f"[aggregate] total={summary['total_count']}, "
          f"cs_immediate={summary['cs_immediate_count']}, "
          f"product_candidates={summary['product_candidate_count']}, "
          f"faq_candidates={summary['faq_candidate_count']}, "
          f"churn_risk={summary['churn_risk_count']}")
    print(f"[aggregate] summary csv: {paths['summary_csv']}")


if __name__ == "__main__":
    main()
