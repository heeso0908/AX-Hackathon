"""구글시트 연동 (Challenge 도전 항목, 선택 기능).

Claude Code 터미널 환경에는 Cowork의 구글시트 커넥터가 없고, CLAUDE.md는 별도 API 키 사용을
원칙적으로 금지한다. 그래서 기본 실행은 자격증명 없이 그대로 동작하며(TSV 내보내기), 사용자가
본인 구글 서비스 계정 자격증명을 직접 제공했을 때만 실제 구글시트에 자동 기입한다.

- build_tsv(): 항상 호출됨. gspread를 import하지 않으므로 의존성/자격증명이 전혀 필요 없다.
- push_to_google_sheets(): opt-in. gspread/google-auth는 여기서만 지연 import하고,
  미설치·자격증명 누락 시 SheetsExportError로 원인을 명확히 안내한다.
"""

from pathlib import Path

SHEET_COLUMNS = ["id", "date_clean", "channel", "customer_type", "voc_type", "topic", "urgency", "content"]

CLASSIFICATION_WORKSHEET = "VoC 분류"
SUMMARY_WORKSHEET = "요약"


class SheetsExportError(Exception):
    """gspread 미설치, 자격증명 누락/오류, 구글시트 API 오류를 사용자에게 안내하기 위한 예외."""


def build_tsv(classified_df) -> str:
    """분류 결과를 구글시트에 그대로 붙여넣을 수 있는 탭 구분(TSV) 텍스트로 변환한다."""
    columns = [c for c in SHEET_COLUMNS if c in classified_df.columns]
    lines = ["\t".join(columns)]
    for _, row in classified_df[columns].iterrows():
        lines.append("\t".join(str(row[c]).replace("\t", " ").replace("\n", " ") for c in columns))
    return "\n".join(lines)


def _build_summary_rows(summary: dict, proposals: list) -> list:
    rows = [["지표", "값"]]
    for row in summary["by_type"].itertuples(index=False):
        rows.append([row.voc_type, str(row.count)])
    rows.append(["High urgency", str(summary["cs_immediate_count"])])
    rows.append(["제품팀 전달 후보", str(summary["product_candidate_count"])])
    rows.append(["", ""])
    rows.append(["제품 개선 기획안", "우선순위 점수"])
    for p in proposals:
        rows.append([p["title"], str(p["scores"]["priority_score"])])
    return rows


def push_to_google_sheets(classified_df, summary: dict, proposals: list,
                           spreadsheet_id: str, credentials_path: str) -> dict:
    """서비스 계정 자격증명으로 인증 후 지정된 스프레드시트에 분류 결과·요약을 자동 기입한다.

    Raises:
        SheetsExportError: gspread/google-auth 미설치, 자격증명 누락/오류, API 오류 시.
    """
    if not spreadsheet_id:
        raise SheetsExportError("spreadsheet_id가 필요합니다 (구글시트 URL의 /d/ 뒤 ID 값).")
    if not credentials_path or not Path(credentials_path).exists():
        raise SheetsExportError(
            f"서비스 계정 자격증명 JSON 파일을 찾을 수 없습니다: {credentials_path}. "
            "구글 클라우드 콘솔에서 서비스 계정 키를 발급하고 경로를 지정하세요 "
            "(--sheets-credentials 또는 GOOGLE_SHEETS_CREDENTIALS 환경변수)."
        )

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise SheetsExportError(
            "gspread/google-auth 패키지가 설치되어 있지 않습니다. "
            "구글시트 자동 기입 기능을 쓰려면 `pip install gspread google-auth`를 실행하세요. "
            "설치하지 않아도 sheets_export.tsv로 수동 붙여넣기는 가능합니다."
        ) from exc

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    try:
        credentials = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(spreadsheet_id)
    except Exception as exc:
        raise SheetsExportError(f"구글시트 인증/접속에 실패했습니다: {exc}") from exc

    def _write_worksheet(title: str, rows: list) -> None:
        try:
            worksheet = spreadsheet.worksheet(title)
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=title, rows=max(len(rows), 10), cols=max(len(rows[0]), 4))
        worksheet.update(rows)

    try:
        classification_rows = [SHEET_COLUMNS] + [
            [str(row[c]) for c in SHEET_COLUMNS] for _, row in classified_df[SHEET_COLUMNS].iterrows()
        ]
        _write_worksheet(CLASSIFICATION_WORKSHEET, classification_rows)
        _write_worksheet(SUMMARY_WORKSHEET, _build_summary_rows(summary, proposals))
    except Exception as exc:
        raise SheetsExportError(f"구글시트에 기입 중 오류가 발생했습니다: {exc}") from exc

    return {
        "spreadsheet_url": spreadsheet.url,
        "updated_worksheets": [CLASSIFICATION_WORKSHEET, SUMMARY_WORKSHEET],
    }
