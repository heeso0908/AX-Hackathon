"""VoC 분류·인사이트 파이프라인 CLI. 이 스크립트 하나로 전체 파이프라인이 완주된다.

실행 예:
    python src/run_pipeline.py --input data/voc.csv --output output/original --dataset-label original --default-year 2026

옵션:
    --input          입력 VoC CSV 경로
    --output         산출물을 저장할 폴더 (없으면 dataset-label에 따라 output/original 또는 output/augmented)
    --default-year    연도 표기가 없는 날짜(예: "5월 4일")에 적용할 기본 연도
    --week-label      리포트 제목에 표시할 주차명. 생략하면 데이터의 최소~최대 날짜로 자동 생성
    --dataset-label   original | augmented — 원본/증강 데이터를 구분하는 라벨

실제 파이프라인 단계(정제→분류→집계→인사이트→리포트→기획안)는 `src/pipeline.py`의
`run_analysis()`에 있다. 이 스크립트는 CLI 인자 처리와 에러 메시지·터미널 출력만 담당하는
얇은 래퍼이며, Streamlit 앱(`app.py`)도 동일한 `run_analysis()`를 공유한다.

원본(--dataset-label original)과 증강(--dataset-label augmented) 데이터의 결과는 서로 다른
--output 폴더에 저장되어야 하며, 같은 폴더를 다른 라벨로 재사용하면 즉시 에러를 낸다.
"""

import argparse
import os
from pathlib import Path

import config
import clean
import pipeline
import sheets_export


def run(args: argparse.Namespace) -> dict:
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = config.AUGMENTED_OUTPUT_DIR if args.dataset_label == "augmented" else config.ORIGINAL_OUTPUT_DIR

    try:
        result = pipeline.run_analysis(
            input_path=args.input,
            output_dir=output_dir,
            dataset_label=args.dataset_label,
            default_year=args.default_year,
            week_label=args.week_label,
            enforce_label_consistency=True,
        )
    except FileNotFoundError as e:
        raise SystemExit(f"[run_pipeline] 오류: {e}")
    except ValueError as e:
        raise SystemExit(f"[run_pipeline] 오류: {e}")

    result["sheets_push_result"] = None
    if args.push_sheets:
        try:
            result["sheets_push_result"] = pipeline.push_to_sheets(
                result, args.sheet_id, args.sheets_credentials
            )
        except sheets_export.SheetsExportError as e:
            raise SystemExit(f"[run_pipeline] 오류: {e}")

    return result


def print_summary(args: argparse.Namespace, result: dict) -> None:
    quality_summary = result["quality_summary"]
    summary = result["summary"]
    generated_files = [str(p) for key, p in result["paths"].items()]

    print("\n[run_pipeline] 실행 완료")
    print(f"- 입력 데이터셋 라벨: {args.dataset_label}")
    print(f"- 정제 전 행 수: {quality_summary['row_count_before']}")
    print(f"- 정제 후 행 수: {quality_summary['row_count_after']}")
    print("- 생성 파일 목록:")
    for f in generated_files:
        print(f"    {f}")
    print(f"- High urgency 건수: {summary['cs_immediate_count']}")
    print(f"- 제품 개선 기획안 건수: {len(result['proposals'])}")
    if result.get("sheets_push_result"):
        print(f"- 구글시트 자동 기입 완료: {result['sheets_push_result']['spreadsheet_url']}")
    else:
        print(f"- 구글시트 붙여넣기용 TSV 생성됨: {result['paths']['sheets_export_tsv']} "
              "(--push-sheets로 실제 시트에 자동 기입 가능)")
    for w in result["warnings"]:
        print(f"[run_pipeline][WARNING] {w}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VoC 분류·인사이트 파이프라인 (전체 자동 실행)")
    parser.add_argument("--input", default=str(config.DEFAULT_INPUT_CSV), help="입력 VoC CSV 경로")
    parser.add_argument(
        "--output", default=None,
        help="산출물 저장 폴더 (생략 시 dataset-label에 따라 output/original 또는 output/augmented)",
    )
    parser.add_argument(
        "--default-year", type=int, default=clean.DEFAULT_YEAR,
        help="연도 표기가 없는 날짜에 적용할 기본 연도 (기본값 2026)",
    )
    parser.add_argument(
        "--week-label", default=None,
        help="리포트 제목에 표시할 주차명 (생략 시 데이터의 최소~최대 날짜로 자동 생성)",
    )
    parser.add_argument(
        "--dataset-label", default="original", choices=["original", "augmented"],
        help="original(제공된 voc.csv) 또는 augmented(synthetic 검증용)",
    )
    parser.add_argument(
        "--push-sheets", action="store_true",
        help="분석 결과를 실제 구글시트에 자동 기입한다 (선택 기능, gspread/google-auth와 "
             "서비스 계정 자격증명 필요). 생략하면 sheets_export.tsv 파일만 생성한다.",
    )
    parser.add_argument(
        "--sheet-id", default=None,
        help="--push-sheets 사용 시 대상 구글시트 spreadsheet ID (시트 URL의 /d/ 뒤 값)",
    )
    parser.add_argument(
        "--sheets-credentials", default=os.environ.get("GOOGLE_SHEETS_CREDENTIALS"),
        help="--push-sheets 사용 시 구글 서비스 계정 자격증명 JSON 경로 "
             "(기본값: GOOGLE_SHEETS_CREDENTIALS 환경변수)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(args)
    print_summary(args, result)


if __name__ == "__main__":
    main()
