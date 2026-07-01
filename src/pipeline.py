"""VoC 분석 파이프라인의 핵심 오케스트레이션 로직.

`run_analysis()` 하나로 정제 → 분류 → 집계 → 인사이트 → 주간 리포트 → 제품 개선 기획안까지
전부 실행하고, 화면에 그리거나 파일로 내려줄 수 있는 결과를 dict로 반환한다.

이 모듈은 CLI(`src/run_pipeline.py`)와 Streamlit 앱(`app.py`) 양쪽에서 공유하는 단일 진입점이다.
분석 로직 자체는 여기서 새로 만들지 않고 clean/classify/aggregate/insight/product_plan/report를
그대로 호출한다 — app.py에는 분석 로직을 직접 작성하지 않는다.
"""

from pathlib import Path

import config
import clean
import classify
import aggregate
import insight
import product_plan
import report
import sheets_export


def check_dataset_label_consistency(output_dir: Path, dataset_label: str) -> None:
    """같은 output_dir이 서로 다른 dataset_label로 재사용되지 않도록 막는다.

    output/original vs output/augmented처럼 결과가 섞이면 안 되는 폴더에만 적용한다.
    Streamlit의 output/uploaded/처럼 매번 덮어써도 되는 폴더에는 호출하지 않는다.
    """
    marker = Path(output_dir) / ".dataset_label"
    if marker.exists():
        prev = marker.read_text(encoding="utf-8").strip()
        if prev != dataset_label:
            raise ValueError(
                f"'{output_dir}' 폴더는 이전에 dataset-label='{prev}'로 사용되었습니다. "
                f"'{dataset_label}' 데이터는 다른 출력 폴더를 사용하세요 "
                "(원본과 증강 데이터 결과를 같은 폴더에 섞지 않기 위한 안전장치)."
            )
    marker.write_text(dataset_label, encoding="utf-8")


def write_run_decisions_log(path: Path, dataset_label: str, input_path, default_year: int,
                             quality_summary: dict, summary: dict, proposals: list, week_label: str) -> None:
    """이번 실행에서 적용된 파라미터·결과를 output 폴더 내 decisions.md에 기록한다."""
    lines = [
        "# 실행 결정 로그",
        "",
        f"- dataset_label: {dataset_label}",
        f"- 입력 파일: {input_path}",
        f"- 리포트 기간(week_label): {week_label}",
        f"- 기본 연도(default_year, 연도 없는 날짜 표기에 적용): {default_year}",
        f"- 정제 전/후 행 수: {quality_summary['row_count_before']} -> {quality_summary['row_count_after']}",
        f"- High urgency 건수: {summary['cs_immediate_count']}",
        f"- 제품 개선 기획안 건수: {len(proposals)}",
    ]
    if proposals:
        lines.append("- 채택된 기획안:")
        for p in proposals:
            lines.append(f"  - {p['title']} (priority_score={p['scores']['priority_score']})")
    lines.append("")
    lines.append("> 분류 기준·우선순위 산정 기준의 전체 근거는 `output/decisions.md`를 참고한다.")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_analysis(input_path, output_dir, dataset_label: str = "original", default_year: int = None,
                  week_label: str = None, enforce_label_consistency: bool = False) -> dict:
    """VoC CSV 하나를 받아 전체 파이프라인을 실행하고 결과를 dict로 반환한다.

    Raises:
        FileNotFoundError: input_path가 존재하지 않을 때
        ValueError: 필수 컬럼이 누락되었거나(또는 enforce_label_consistency=True일 때
                    output_dir가 이전과 다른 dataset_label로 재사용된 경우)
    """
    if default_year is None:
        default_year = clean.DEFAULT_YEAR

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if enforce_label_consistency:
        check_dataset_label_consistency(output_dir, dataset_label)

    paths = config.build_paths(output_dir)

    # 1. load_voc
    raw_df = clean.load_voc(str(input_path))

    missing_columns = clean.check_required_columns(raw_df)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {', '.join(missing_columns)}")

    # 2. clean_voc
    clean_df, quality_summary = clean.clean_voc(raw_df, default_year=default_year)

    # 3. write_data_quality_log
    clean.write_data_quality_log(raw_df, clean_df, quality_summary, paths["quality_log_md"])
    clean_df.to_csv(paths["cleaned_csv"], index=False, encoding="utf-8")

    # 4. classify_voc
    classified_df = classify.classify_voc(clean_df)
    warnings = classify.run_special_validations(classified_df)

    # 5. voc_classification.csv 저장
    classified_df.to_csv(paths["classified_csv"], index=False, encoding="utf-8")

    # 6. build_summary_tables
    summary = aggregate.build_summary_tables(classified_df)
    summary["by_type"].to_csv(paths["summary_csv"], index=False, encoding="utf-8")

    # 7. generate_business_insights
    context_texts = insight.load_context_texts()
    insights = insight.generate_business_insights(classified_df, summary, context_texts)
    insight_report_md = insight.render_insight_report(insights)
    paths["insight_report_md"].write_text(insight_report_md, encoding="utf-8")

    proposals = product_plan.generate_product_proposals(classified_df)
    resolved_week_label = week_label or report.default_week_label(classified_df)

    # 8. generate_weekly_report (제품 개선 기획안을 참조하므로 먼저 계산해둔 proposals를 사용)
    report_context = report.build_report_context(
        dataset_label, quality_summary, classified_df, summary, insights, proposals, resolved_week_label
    )
    weekly_report_md = report.render_voc_report(report_context)
    paths["voc_report_md"].write_text(weekly_report_md, encoding="utf-8")

    # 9. generate_product_improvement_plan
    proposal_md = product_plan.render_proposal_doc(proposals)
    paths["proposal_md"].write_text(proposal_md, encoding="utf-8")

    # 10. decisions.md 작성 (이번 실행의 판단 근거를 output_dir에 기록)
    write_run_decisions_log(paths["run_decisions_md"], dataset_label, input_path, default_year,
                             quality_summary, summary, proposals, resolved_week_label)

    # 11. 구글시트용 TSV 내보내기 (자격증명 없이 항상 생성 — 시트에 바로 붙여넣기 가능)
    sheets_export_tsv = sheets_export.build_tsv(classified_df)
    paths["sheets_export_tsv"].write_text(sheets_export_tsv, encoding="utf-8")

    return {
        "output_dir": output_dir,
        "paths": paths,
        "dataset_label": dataset_label,
        "week_label": resolved_week_label,
        "warnings": warnings,
        "raw_df": raw_df,
        "clean_df": clean_df,
        "classified_df": classified_df,
        "quality_summary": quality_summary,
        "summary": summary,
        "insights": insights,
        "insight_report_md": insight_report_md,
        "proposals": proposals,
        "proposal_md": proposal_md,
        "weekly_report_md": weekly_report_md,
        "sheets_export_tsv": sheets_export_tsv,
    }


def push_to_sheets(result: dict, spreadsheet_id: str, credentials_path: str) -> dict:
    """run_analysis()가 이미 계산한 결과를 그대로 구글시트에 자동 기입한다 (선택 기능).

    CLI(run_pipeline.py)와 Streamlit(app.py)이 공유하는 얇은 래퍼 — 분석 결과를 다시 계산하지 않는다.

    Raises:
        sheets_export.SheetsExportError: gspread 미설치, 자격증명 누락/오류, API 오류 시.
    """
    return sheets_export.push_to_google_sheets(
        result["classified_df"], result["summary"], result["proposals"],
        spreadsheet_id, credentials_path,
    )
