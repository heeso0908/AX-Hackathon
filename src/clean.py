"""VoC CSV 데이터 정제 모듈.

실행:
    python src/clean.py [--input data/voc.csv]

정제 규칙:
    1. id -> 문자열 3자리로 표준화 (예: "1" -> "001")
    2. date -> date_clean 컬럼에 YYYY-MM-DD로 표준화 (연도 없는 표기는 기본 연도 적용)
    3. channel 결측 -> "미기재"
    4. customer_type 결측 -> "기타"
    5. content 앞뒤 공백 제거
    6. keyword_hint 앞뒤 공백 제거
    7. content 완전 중복 행 -> 첫 번째 행만 유지, 나머지는 제거 로그에 기록
    8. 추가 컬럼: date_clean, week, is_duplicate_removed, data_quality_flags

원본 컬럼(date 등)은 그대로 보존하며, 정제 결과는 별도 컬럼으로 추가한다.
`load_voc` / `normalize_date` / `clean_voc`는 새로운 CSV에도 그대로 재사용 가능하도록
경로·연도 등을 파라미터로 받는다.
"""

import argparse
import re
from collections import Counter
from datetime import datetime

import pandas as pd

import config

# --- 날짜 형식 패턴 ---
DATE_PATTERNS = {
    "iso": re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"),
    "slash": re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$"),
    "korean": re.compile(r"^(\d{1,2})월\s*(\d{1,2})일$"),
}

DEFAULT_YEAR = 2026

CHANNEL_MISSING_FILL = "미기재"
CUSTOMER_TYPE_MISSING_FILL = "기타"


def load_voc(input_path: str) -> pd.DataFrame:
    """VoC CSV를 문자열 그대로(값 변형 없이) 읽는다."""
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]
    return df


def detect_date_format(value: str) -> str:
    """날짜 문자열의 형식을 분류한다: iso / slash / korean / unknown."""
    value = (value or "").strip()
    for fmt, pattern in DATE_PATTERNS.items():
        if pattern.match(value):
            return fmt
    return "unknown"


def normalize_date(value, default_year: int = DEFAULT_YEAR) -> str:
    """날짜 문자열을 YYYY-MM-DD로 표준화한다.

    지원 형식: YYYY-MM-DD / YYYY/MM/DD / M월 D일 (연도 없으면 default_year 사용)
    파싱에 실패하면 빈 문자열("")을 반환한다 (호출부에서 data_quality_flags에 기록).
    """
    value = (value or "").strip()
    fmt = detect_date_format(value)

    try:
        if fmt == "iso":
            dt = datetime.strptime(value, "%Y-%m-%d")
        elif fmt == "slash":
            dt = datetime.strptime(value, "%Y/%m/%d")
        elif fmt == "korean":
            m = DATE_PATTERNS["korean"].match(value)
            month, day = int(m.group(1)), int(m.group(2))
            dt = datetime(default_year, month, day)
        else:
            return ""
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _iso_week_label(date_clean: str) -> str:
    """YYYY-MM-DD 문자열을 'YYYY-Www' 주차 레이블로 변환한다. 빈 값이면 빈 문자열."""
    if not date_clean:
        return ""
    dt = datetime.strptime(date_clean, "%Y-%m-%d")
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _append_flag(flags: list, flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def check_required_columns(df: pd.DataFrame) -> list:
    """필수 컬럼(config.INPUT_COLUMNS) 중 누락된 컬럼명 목록을 반환한다."""
    return [c for c in config.INPUT_COLUMNS if c not in df.columns]


def clean_voc(df: pd.DataFrame, default_year: int = DEFAULT_YEAR) -> tuple:
    """정제 규칙 1~8을 적용하고 (정제된 DataFrame, 품질 요약 dict)를 반환한다."""
    clean = df.copy()

    # 0. 필수 컬럼 존재 여부 (누락 시에도 정제는 계속 진행하되 로그에 남긴다)
    missing_columns = check_required_columns(clean)

    # 정제 전 상태 기준 통계 (원본 컬럼 기준)
    date_format_counts = dict(Counter(clean["date"].apply(detect_date_format)))
    customer_type_dist_before = dict(
        Counter(clean["customer_type"].apply(lambda v: v.strip() if v.strip() else "(결측)"))
    )

    row_flags = [[] for _ in range(len(clean))]

    # 1. id 표준화
    clean["id"] = clean["id"].astype(str).str.strip().str.zfill(3)

    # id 중복 여부 탐지 (표준화 이후 값 기준, 제거하지 않고 플래그만 남김)
    duplicate_id_mask = clean["id"].duplicated(keep=False)
    duplicate_id_values = sorted(clean.loc[duplicate_id_mask, "id"].unique().tolist())
    for i in clean.index[duplicate_id_mask]:
        _append_flag(row_flags[i], "id_duplicate")

    # content 결측 탐지 (공백 제거 전 원본 기준, +flag)
    content_missing_ids = []
    for i, v in enumerate(clean["content"]):
        if not (v or "").strip():
            _append_flag(row_flags[i], "content_missing")
            content_missing_ids.append(clean.at[i, "id"])

    # keyword_hint 결측 탐지 (공백 제거 전 원본 기준, +flag)
    keyword_hint_missing_ids = []
    for i, v in enumerate(clean["keyword_hint"]):
        if not (v or "").strip():
            _append_flag(row_flags[i], "keyword_hint_missing")
            keyword_hint_missing_ids.append(clean.at[i, "id"])

    # 3. channel 결측 처리 (+flag)
    channel_missing_ids = []
    for i, v in enumerate(clean["channel"]):
        if not (v or "").strip():
            _append_flag(row_flags[i], "channel_missing")
            channel_missing_ids.append(clean.at[i, "id"])
    clean["channel"] = clean["channel"].apply(lambda v: v.strip() if (v or "").strip() else CHANNEL_MISSING_FILL)

    # 4. customer_type 결측 처리 (+flag)
    customer_type_missing_ids = []
    for i, v in enumerate(clean["customer_type"]):
        if not (v or "").strip():
            _append_flag(row_flags[i], "customer_type_missing")
            customer_type_missing_ids.append(clean.at[i, "id"])
    clean["customer_type"] = clean["customer_type"].apply(
        lambda v: v.strip() if (v or "").strip() else CUSTOMER_TYPE_MISSING_FILL
    )

    # 5. content / 6. keyword_hint 공백 제거
    clean["content"] = clean["content"].apply(lambda v: (v or "").strip())
    clean["keyword_hint"] = clean["keyword_hint"].apply(lambda v: (v or "").strip())

    # 2. date_clean 표준화 (+flag on failure)
    date_clean_values = []
    date_parse_failed_ids = []
    for i, raw_value in enumerate(clean["date"]):
        normalized = normalize_date(raw_value, default_year=default_year)
        if not normalized:
            _append_flag(row_flags[i], "date_parse_failed")
            date_parse_failed_ids.append(clean.at[i, "id"])
        date_clean_values.append(normalized)
    clean["date_clean"] = date_clean_values

    # week 컬럼
    clean["week"] = clean["date_clean"].apply(_iso_week_label)

    # 7. content 완전 중복 -> 첫 번째 행만 유지
    # content가 빈 값("")인 행들은 서로 다른 문의일 수 있으므로 중복 판정에서 제외한다.
    # (빈 값 기준으로 매칭하면 서로 무관한 결측 행들이 "중복"으로 오인되어 삭제되는 문제가 있었음)
    duplicate_mask = clean.duplicated(subset=["content"], keep="first") & (clean["content"] != "")
    duplicates_removed = []
    for i in clean.index[duplicate_mask]:
        _append_flag(row_flags[i], "duplicate_content_removed")
        first_idx = clean[clean["content"] == clean.at[i, "content"]].index[0]
        duplicates_removed.append(
            {
                "removed_id": clean.at[i, "id"],
                "kept_id": clean.at[first_idx, "id"],
                "content": clean.at[i, "content"],
            }
        )

    clean["is_duplicate_removed"] = duplicate_mask
    clean["data_quality_flags"] = [";".join(flags) for flags in row_flags]

    row_count_before = len(clean)
    clean = clean[~duplicate_mask].reset_index(drop=True)
    row_count_after = len(clean)

    quality_summary = {
        "row_count_before": row_count_before,
        "row_count_after": row_count_after,
        "missing_columns": missing_columns,
        "date_format_counts": date_format_counts,
        "customer_type_distribution_before": customer_type_dist_before,
        "channel_missing_ids": channel_missing_ids,
        "customer_type_missing_ids": customer_type_missing_ids,
        "content_missing_ids": content_missing_ids,
        "keyword_hint_missing_ids": keyword_hint_missing_ids,
        "duplicate_id_values": duplicate_id_values,
        "date_parse_failed_ids": date_parse_failed_ids,
        "duplicates_removed": duplicates_removed,
        "flag_counts": dict(Counter(f for flags in row_flags for f in flags)),
    }

    return clean, quality_summary


def write_data_quality_log(raw_df: pd.DataFrame, clean_df: pd.DataFrame, quality_summary: dict, output_path) -> None:
    """정제 전/후 상태를 비교하는 data_quality_log.md를 output_path에 작성한다."""
    row_before = quality_summary["row_count_before"]
    row_after = quality_summary["row_count_after"]

    valid_dates = clean_df["date_clean"][clean_df["date_clean"] != ""]
    period_start = valid_dates.min() if not valid_dates.empty else "N/A"
    period_end = valid_dates.max() if not valid_dates.empty else "N/A"

    fmt_counts = quality_summary["date_format_counts"]
    mixed_date_count = fmt_counts.get("slash", 0) + fmt_counts.get("korean", 0)

    issue_rows = [
        (
            "필수 컬럼 누락",
            len(quality_summary["missing_columns"]),
            "없음" if not quality_summary["missing_columns"] else f"누락 컬럼: {', '.join(quality_summary['missing_columns'])} — 파이프라인 중단 검토 필요",
        ),
        (
            "날짜 형식 혼용 (slash/korean)",
            mixed_date_count,
            "정규식 기반 형식 판별 후 date_clean 컬럼에 YYYY-MM-DD로 통일",
        ),
        (
            "channel 결측",
            len(quality_summary["channel_missing_ids"]),
            f"최빈 채널 대체 없이 '{CHANNEL_MISSING_FILL}'로 명시, 별도 카테고리 유지 (해당 id: {', '.join(quality_summary['channel_missing_ids']) or '없음'})",
        ),
        (
            "customer_type 결측",
            len(quality_summary["customer_type_missing_ids"]),
            f"'{CUSTOMER_TYPE_MISSING_FILL}'로 채움 (해당 id: {', '.join(quality_summary['customer_type_missing_ids']) or '없음'})",
        ),
        (
            "content 결측",
            len(quality_summary["content_missing_ids"]),
            "없음" if not quality_summary["content_missing_ids"] else f"data_quality_flags에 'content_missing' 기록, 수동 확인 필요 (해당 id: {', '.join(quality_summary['content_missing_ids'])})",
        ),
        (
            "keyword_hint 결측",
            len(quality_summary["keyword_hint_missing_ids"]),
            "없음" if not quality_summary["keyword_hint_missing_ids"] else f"data_quality_flags에 'keyword_hint_missing' 기록 (해당 id: {', '.join(quality_summary['keyword_hint_missing_ids'])})",
        ),
        (
            "id 중복",
            len(quality_summary["duplicate_id_values"]),
            "없음" if not quality_summary["duplicate_id_values"] else f"data_quality_flags에 'id_duplicate' 기록, 수동 확인 필요 (해당 id: {', '.join(quality_summary['duplicate_id_values'])})",
        ),
        (
            "날짜 파싱 실패",
            len(quality_summary["date_parse_failed_ids"]),
            "없음" if not quality_summary["date_parse_failed_ids"] else f"date_quality_flags에 'date_parse_failed' 기록, date_clean은 빈 값 유지 (해당 id: {', '.join(quality_summary['date_parse_failed_ids'])})",
        ),
        (
            "content 완전 중복",
            len(quality_summary["duplicates_removed"]),
            "첫 번째 행(kept_id)만 유지, 나머지 제거"
            if quality_summary["duplicates_removed"]
            else "없음",
        ),
    ]
    issue_table = "\n".join(f"| {name} | {count} | {action} |" for name, count, action in issue_rows)

    fmt_detail_lines = "\n".join(f"  - {fmt}: {cnt}건" for fmt, cnt in fmt_counts.items())
    ct_dist_lines = "\n".join(
        f"  - {name}: {cnt}건" for name, cnt in quality_summary["customer_type_distribution_before"].items()
    )

    dup_detail = "없음"
    if quality_summary["duplicates_removed"]:
        lines = [
            f"  - id {d['removed_id']} 제거 (id {d['kept_id']}과 content 완전 일치)"
            for d in quality_summary["duplicates_removed"]
        ]
        dup_detail = "\n".join(lines)

    flag_summary_lines = "\n".join(
        f"  - {flag}: {cnt}건" for flag, cnt in quality_summary["flag_counts"].items()
    ) or "  - 없음"

    missing_columns_line = (
        "없음" if not quality_summary["missing_columns"] else ", ".join(quality_summary["missing_columns"])
    )
    content_missing_line = (
        "없음" if not quality_summary["content_missing_ids"] else ', '.join(quality_summary["content_missing_ids"])
    )
    keyword_hint_missing_line = (
        "없음" if not quality_summary["keyword_hint_missing_ids"] else ', '.join(quality_summary["keyword_hint_missing_ids"])
    )
    duplicate_id_line = (
        "없음" if not quality_summary["duplicate_id_values"] else ', '.join(quality_summary["duplicate_id_values"])
    )

    log_md = f"""# 데이터 품질 점검 로그

> 대상 파일: `data/voc.csv` | 점검 일시: 파이프라인 실행 시점 자동 생성

## 1. 요약

- 총 행 수 (정제 전): {row_before}
- 총 행 수 (정제 후): {row_after}
- 총 컬럼 수: {len(raw_df.columns)} (`{', '.join(config.INPUT_COLUMNS)}`)
- 분석 기간 (정제 후 date_clean 기준): {period_start} ~ {period_end}
- 중복 제거 전/후 행 수: {row_before}건 → {row_after}건 ({row_before - row_after}건 제거)

## 2. 발견된 이슈

| 이슈 | 건수 | 처리 방식 |
|---|---:|---|
{issue_table}

## 3. 상세 내역

- **날짜 형식 혼용**:
{fmt_detail_lines}
  - 처리: 연도 표기가 없는 `M월 D일` 형식은 기본 연도(2026)를 적용해 `date_clean`에 정규화했다.

- **채널 결측**: {len(quality_summary['channel_missing_ids'])}건 (id: {', '.join(quality_summary['channel_missing_ids']) or '없음'})
  - 처리: 최빈 채널로 대체하지 않고 '{CHANNEL_MISSING_FILL}'로 명시해 별도 카테고리로 유지했다.

- **중복 행**:
{dup_detail}

- **기타**:
  - 필수 컬럼(`{', '.join(config.INPUT_COLUMNS)}`) 누락: {missing_columns_line}
  - customer_type 결측 {len(quality_summary['customer_type_missing_ids'])}건 (id: {', '.join(quality_summary['customer_type_missing_ids']) or '없음'}) → '{CUSTOMER_TYPE_MISSING_FILL}'로 채움
  - content 결측: {content_missing_line}
  - keyword_hint 결측: {keyword_hint_missing_line}
  - id 중복: {duplicate_id_line}

- **data_quality_flags 발생 건수**:
{flag_summary_lines}

- **customer_type 값 분포 (정제 전)**:
{ct_dist_lines}

## 4. 실무 적용 시 권장사항

- CS 담당자가 CSV 업로드 전 확인해야 할 항목:
  - `date` 컬럼은 가능하면 `YYYY-MM-DD` 단일 형식으로 입력 (연도 누락 표기 금지)
  - `channel`, `customer_type`은 필수 입력 항목으로 지정 (빈 값 제출 방지)
  - 동일 문의를 여러 채널로 재접수한 경우 원본 접수 id를 함께 기재하면 중복 판정 정확도가 올라감

- 다음 버전에서 자동 검증하면 좋은 항목:
  - CSV 업로드 시점에 날짜 형식·필수 컬럼을 즉시 검증하고 오류 행을 즉시 반려하는 업로드 단계 검증기
  - `data_quality_flags`가 2개 이상 붙은 행을 CS 대시보드에서 우선 검수 대상으로 자동 표시
  - content 완전 일치가 아닌 유사도 기반 중복 탐지(예: 90% 이상 유사) 도입 검토
"""

    output_path = str(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(log_md)


def main() -> None:
    parser = argparse.ArgumentParser(description="VoC CSV 데이터 정제")
    parser.add_argument("--input", default=str(config.DEFAULT_INPUT_CSV), help="정제할 VoC CSV 경로")
    parser.add_argument(
        "--mode", default="original", choices=["original", "augmented"],
        help="산출물 저장 위치: original(제공된 voc.csv) 또는 augmented(synthetic 검증용)",
    )
    args = parser.parse_args()

    config.ensure_output_dirs()
    paths = config.output_paths(args.mode)

    raw_df = load_voc(args.input)
    clean_df, quality_summary = clean_voc(raw_df)

    write_data_quality_log(raw_df, clean_df, quality_summary, paths["quality_log_md"])
    clean_df.to_csv(paths["cleaned_csv"], index=False, encoding="utf-8")

    print(f"[clean] {quality_summary['row_count_before']} -> {quality_summary['row_count_after']} rows")
    print(f"[clean] log: {paths['quality_log_md']}")
    print(f"[clean] cleaned csv: {paths['cleaned_csv']}")


if __name__ == "__main__":
    main()
