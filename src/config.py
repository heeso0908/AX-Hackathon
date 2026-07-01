"""프로젝트 전역 경로·상수 설정.

모든 산출물(output/*)의 경로는 이 파일에서만 정의한다.
run_pipeline.py 및 각 단계 모듈은 이 config를 통해 경로를 참조한다.

output/original/  -> data/voc.csv(제공된 원본 데이터) 분석 결과. 메인 산출물.
output/augmented/ -> generate_synthetic_voc.py로 만든 synthetic CSV 분석 결과.
                      파이프라인 재현성 검증용이며 원본 분석 결과와 절대 섞지 않는다.
"""

from pathlib import Path

# 프로젝트 루트 (src/ 의 부모 디렉터리)
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
CONTEXT_DIR = BASE_DIR / "context"
OUTPUT_DIR = BASE_DIR / "output"
ORIGINAL_OUTPUT_DIR = OUTPUT_DIR / "original"
AUGMENTED_OUTPUT_DIR = OUTPUT_DIR / "augmented"
# Streamlit 앱(app.py)에서 사용자가 CSV를 업로드했을 때만 쓰는 폴더. 매 업로드마다 덮어쓰며,
# output/original(제공된 voc.csv 분석)과는 절대 섞지 않는다.
UPLOADED_OUTPUT_DIR = OUTPUT_DIR / "uploaded"

# 입력
DEFAULT_INPUT_CSV = DATA_DIR / "voc.csv"
# generate_synthetic_voc.py의 기본 출력 경로 (파이프라인 재현성 검증용, 원본과 분리)
SYNTHETIC_INPUT_CSV = DATA_DIR / "voc_augmented.csv"

# 컨텍스트 문서
COMPANY_INFO_MD = CONTEXT_DIR / "company-info.md"
INDUSTRY_NEWS_MD = CONTEXT_DIR / "industry-news.md"

# 분류 방법론 문서 (원본/synthetic 공통, output/ 바로 아래에 위치)
CLASSIFICATION_DECISIONS_MD = OUTPUT_DIR / "decisions.md"

# 원본 CSV 컬럼 정의
INPUT_COLUMNS = ["id", "date", "channel", "customer_type", "content", "keyword_hint"]

# 분류 유형 (4종, 고정 순서)
VOC_TYPES = ["불만", "기능 요청", "칭찬", "일반 문의"]

# 고객 유형 (design-conversation.md v2 기준)
CUSTOMER_TYPES = ["1차 협력사", "2차 협력사", "OEM", "기타"]


def get_output_dir(mode: str = "original") -> Path:
    """mode('original' | 'augmented')에 해당하는 산출물 디렉터리를 반환한다."""
    if mode not in ("original", "augmented"):
        raise ValueError(f"알 수 없는 output mode: {mode}")
    return ORIGINAL_OUTPUT_DIR if mode == "original" else AUGMENTED_OUTPUT_DIR


def ensure_output_dirs() -> None:
    """output/, output/original/, output/augmented/, output/uploaded/ 디렉터리를 모두 생성한다."""
    ORIGINAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    AUGMENTED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_paths(output_dir) -> dict:
    """임의의 output_dir(Path|str) 기준으로 단계별 산출물 경로 dict를 반환한다.

    run_pipeline.py의 --output처럼 output/original, output/augmented가 아닌
    임의의 폴더를 산출물 위치로 쓸 때 사용한다.
    """
    out_dir = Path(output_dir)
    return {
        "cleaned_csv": out_dir / "voc-cleaned.csv",
        "classified_csv": out_dir / "voc_classification.csv",
        "quality_log_md": out_dir / "data_quality_log.md",
        "summary_csv": out_dir / "voc-summary.csv",
        "insight_report_md": out_dir / "insight-report.md",
        "proposal_md": out_dir / "product_improvement_plan.md",
        "voc_report_md": out_dir / "weekly_voc_report.md",
        "run_decisions_md": out_dir / "decisions.md",
        "sheets_export_tsv": out_dir / "sheets_export.tsv",
    }


def output_paths(mode: str = "original") -> dict:
    """단계별 산출물 경로 dict를 반환한다 (mode에 따라 original/augmented 하위)."""
    return build_paths(get_output_dir(mode))
