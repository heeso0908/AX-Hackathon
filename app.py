"""Internal VoC operations dashboard built on the CarbonLink-inspired UI."""

from __future__ import annotations

import base64
import html
import io
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).parent / "src"))

import clean  # noqa: E402
import config  # noqa: E402
import pipeline  # noqa: E402
import sheets_export  # noqa: E402

HEADER_LOGO_PATH = Path(__file__).parent / "logo.svg"
FAVICON_PATH = Path(__file__).parent / "logo_mini.png"

# Streamlit/Markdown 함정: st.markdown(..., unsafe_allow_html=True)에 넘기는 문자열이
# Python 소스 들여쓰기를 그대로 가지고 있으면(4칸 이상 공백), CommonMark가 이를 "들여쓰기된
# 코드 블록"으로 인식해 HTML로 렌더링하지 않고 그대로 텍스트로 출력해버린다. 이 앱은 여러
# 함수에서 들여쓰기된 멀티라인 f-string으로 HTML을 만들기 때문에, st.markdown 자체를 감싸서
# unsafe_allow_html=True일 때 항상 공통 들여쓰기를 제거하도록 한 곳에서 고친다.
_original_st_markdown = st.markdown


def _dedented_markdown(body, *args, **kwargs):
    if kwargs.get("unsafe_allow_html") and isinstance(body, str):
        # 단순 dedent로는 부족하다: 이 파일의 HTML은 여러 f-string 조각을 이어붙여 만드는데,
        # 각 조각이 삼중인용부호 닫힘 직전에 "공백만 있는 줄"로 끝난다. CommonMark는 그런
        # 공백뿐인 줄을 blank line으로 보고 그 자리에서 HTML 블록을 끝내버리고, 바로 다음 줄이
        # 4칸 이상 들여쓰기돼 있으면 "들여쓰기된 코드 블록"으로 오인해 그대로 텍스트로 찍어버린다
        # (실제로 step 2~6 카드가 이렇게 코드 텍스트로 나온 원인). 줄 단위로 좌우 공백을 지우고
        # 빈 줄을 제거해 한 줄짜리 HTML로 합치면 이 오인식 자체가 발생할 여지가 없어진다.
        lines = [line.strip() for line in body.splitlines()]
        body = " ".join(line for line in lines if line)
    return _original_st_markdown(body, *args, **kwargs)


st.markdown = _dedented_markdown

st.set_page_config(
    page_title="VoC 운영 콘솔",
    page_icon=str(FAVICON_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def load_logo_data_uri() -> str | None:
    """logo.svg를 base64 data URI로 인코딩한다. 파일이 없으면 None을 반환한다."""
    if not HEADER_LOGO_PATH.exists():
        return None
    b64 = base64.b64encode(HEADER_LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700;800&family=Noto+Sans+KR:wght@400;500;700;800&display=swap');

        :root {
            --primary-green: #10B69F;
            --deep-green: #087F6A;
            --mint-bg: #EEF9F6;
            --soft-green: #DDF4EE;
            --bg-main: #FFFFFF;
            --bg-card: #FFFFFF;
            --border-light: #E5E7EB;
            --text-main: #111827;
            --text-sub: #6B7280;
            --text-muted: #9CA3AF;
            --success: #10B69F;
            --warning: #F59E0B;
            --danger: #EF4444;
            --info: #2563EB;
        }

        html, body, [class*="css"] {
            font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
        }

        .stApp {
            background: #FFFFFF;
            color: var(--text-main);
        }

        .block-container {
            max-width: 1480px;
            padding-top: 0.75rem;
            padding-bottom: 4rem;
        }

        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.92);
            border-right: 1px solid var(--border-light);
        }

        .app-shell {
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        .top-header {
            display: flex;
            justify-content: flex-start;
            align-items: center;
            gap: 24px;
            background: #FFFFFF;
            border-bottom: 2px solid #17B3A2;
            padding: 12px 8px 18px;
        }

        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-icon {
            width: 48px;
            height: 48px;
            border-radius: 16px;
            background: linear-gradient(135deg, #16A34A 0%, #0F5132 100%);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            box-shadow: 0 14px 24px rgba(22, 163, 74, 0.22);
        }

        .brand-logo {
            height: 40px;
            width: auto;
            display: block;
        }

        .brand-title {
            font-size: 20px;
            font-weight: 800;
            color: #111827;
            line-height: 1.1;
        }

        .brand-subtitle {
            margin-top: 2px;
            color: #9CA3AF;
            font-size: 12px;
        }

        .hero {
            background: #FFFFFF;
            border: none;
            border-radius: 0;
            padding: 24px 0 8px;
            box-shadow: none;
        }

        .eyebrow {
            display: inline-block;
            color: #10B69F;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: -0.01em;
        }

        .hero-title {
            margin: 16px 0 0;
            font-size: 58px;
            line-height: 1.1;
            font-weight: 800;
            color: var(--text-main);
            letter-spacing: -0.04em;
        }

        .hero-title .green {
            color: var(--primary-green);
        }

        .hero-desc {
            margin-top: 18px;
            color: #6B7280;
            font-size: 20px;
            line-height: 1.55;
            max-width: 760px;
        }

        .hero-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 26px;
        }

        .hero-chip, .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 14px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }

        .hero-chip {
            background: #F4FBF9;
            border: 1px solid #DDF4EE;
            color: #0F8D77;
        }

        .preview-card, .dashboard-card, .metric-card, .step-card, .insight-card, .plan-card {
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
        }

        .preview-card {
            border-radius: 26px;
            padding: 24px;
            height: 100%;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        }

        .preview-card.alert {
            background: linear-gradient(180deg, #FFF6F6 0%, #FFF1F1 100%);
            border: 1px solid #FECACA;
            box-shadow: 0 12px 28px rgba(239, 68, 68, 0.08);
        }

        .preview-card.alert .preview-label {
            color: #B91C1C;
        }

        .preview-card.alert .preview-metric {
            color: #991B1B;
        }

        .preview-card.alert .preview-caption {
            color: #7F1D1D;
        }

        .preview-label {
            color: var(--text-sub);
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .preview-metric {
            margin-top: 8px;
            font-size: 36px;
            font-weight: 800;
            color: var(--text-main);
            line-height: 1.1;
        }

        .preview-caption {
            margin-top: 8px;
            color: var(--text-sub);
            font-size: 14px;
            line-height: 1.6;
        }

        .section-title {
            margin: 56px 0 10px;
            font-size: 34px;
            font-weight: 800;
            color: var(--text-main);
            letter-spacing: -0.03em;
        }

        .section-desc {
            color: var(--text-sub);
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 28px;
        }

        .metric-card {
            border-radius: 22px;
            padding: 22px;
            min-height: 170px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.04);
        }

        .metric-label {
            color: var(--text-sub);
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .metric-value {
            margin-top: 12px;
            font-size: 32px;
            line-height: 1.15;
            font-weight: 800;
            color: var(--text-main);
        }

        .metric-footnote {
            margin-top: 16px;
            display: inline-flex;
            align-items: center;
            padding: 6px 10px;
            border-radius: 999px;
            background: #ECFDF5;
            color: #166534;
            font-size: 12px;
            font-weight: 700;
        }

        .workflow-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 14px;
        }

        .step-card {
            border-radius: 22px;
            padding: 22px 18px;
            min-height: 164px;
        }

        .step-number {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: var(--primary-green);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 800;
            margin-bottom: 16px;
        }

        .step-title {
            color: var(--text-main);
            font-size: 17px;
            font-weight: 800;
        }

        .step-desc {
            margin-top: 8px;
            color: var(--text-sub);
            font-size: 14px;
            line-height: 1.65;
        }

        .dashboard-card {
            border-radius: 22px;
            padding: 20px 22px 16px;
            margin-bottom: 18px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.04);
        }

        .card-label {
            color: var(--text-sub);
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .card-title {
            margin-top: 6px;
            color: var(--text-main);
            font-size: 20px;
            font-weight: 800;
        }

        .card-subtitle {
            margin-top: 6px;
            color: var(--text-sub);
            font-size: 14px;
            line-height: 1.6;
        }

        .status-badge {
            background: #DCFCE7;
            color: #166534;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }

        .badge-complaint, .badge-high, .badge-danger {
            background: #FEE2E2;
            color: #991B1B;
        }

        .badge-request, .badge-info {
            background: #DBEAFE;
            color: #1D4ED8;
        }

        .badge-praise, .badge-low, .badge-success {
            background: #DCFCE7;
            color: #166534;
        }

        .badge-inquiry, .badge-neutral {
            background: #F3F4F6;
            color: #374151;
        }

        .badge-medium, .badge-warning {
            background: #FEF3C7;
            color: #92400E;
        }

        .insight-card {
            border-left: 4px solid var(--primary-green);
            border-radius: 4px 18px 18px 4px;
            padding: 20px 22px;
            margin-bottom: 14px;
        }

        .insight-title {
            color: var(--deep-green);
            font-size: 18px;
            font-weight: 800;
            margin: 0 0 10px;
        }

        .insight-card p {
            margin: 8px 0;
            color: #374151;
            font-size: 14px;
            line-height: 1.7;
        }

        .field-label {
            color: var(--primary-green);
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }

        .plan-card {
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 18px;
        }

        .plan-score-wrap {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }

        .plan-score-label {
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--text-sub);
        }

        .plan-score {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 62px;
            height: 42px;
            border-radius: 14px;
            background: #ECFDF5;
            border: 1px solid #86EFAC;
            color: var(--deep-green);
            font-size: 20px;
            font-weight: 800;
        }

        .score-chip {
            display: inline-flex;
            align-items: center;
            margin: 6px 6px 0 0;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid var(--border-light);
            background: #F8FAFC;
            color: #374151;
            font-size: 12px;
            font-weight: 700;
        }

        .table-caption {
            color: var(--text-sub);
            font-size: 13px;
            margin-bottom: 10px;
        }

        .footer-note {
            margin-top: 6px;
            padding: 18px 20px;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid var(--border-light);
            color: #4B5563;
            font-size: 13px;
            line-height: 1.7;
        }

        .html-table-wrap {
            overflow-x: auto;
            border: 1px solid var(--border-light);
            border-radius: 18px;
            background: #FFFFFF;
        }

        .html-table {
            width: 100%;
            border-collapse: collapse;
        }

        .html-table thead th {
            background: #F9FAFB;
            color: #374151;
            font-size: 14px;
            font-weight: 700;
            text-align: left;
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-light);
        }

        .html-table tbody td {
            color: #111827;
            font-size: 15px;
            line-height: 1.65;
            padding: 14px;
            border-bottom: 1px solid #F1F5F9;
            vertical-align: top;
        }

        .html-table tbody tr:last-child td {
            border-bottom: none;
        }

        .report-page-header {
            background: #FFFFFF;
            border: 1px solid var(--border-light);
            border-radius: 24px;
            padding: 24px 26px;
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
            margin-bottom: 24px;
        }

        .report-page-kicker {
            color: #10B69F;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }

        .report-page-title {
            margin-top: 8px;
            color: #111827;
            font-size: 30px;
            font-weight: 800;
            letter-spacing: -0.03em;
        }

        .report-page-desc {
            margin-top: 12px;
            color: #6B7280;
            font-size: 15px;
            line-height: 1.7;
        }

        .report-meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
        }

        .report-section-card {
            background: #FFFFFF;
            border: 1px solid var(--border-light);
            border-radius: 24px;
            padding: 24px;
            margin-bottom: 18px;
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
        }

        .report-section-card--summary {
            background: var(--mint-bg);
            border: 1px solid #86EFAC;
        }

        .report-section-card--summary .report-section-kicker,
        .report-section-card--summary .report-section-title {
            color: var(--deep-green);
        }

        .report-section-head {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }

        .report-section-kicker {
            color: var(--text-sub);
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .report-section-title {
            margin: 6px 0 0;
            color: #111827;
            font-size: 22px;
            font-weight: 800;
            letter-spacing: -0.02em;
        }

        .report-subhead {
            margin: 10px 0 12px;
            color: #0F766E;
            font-size: 16px;
            font-weight: 800;
        }

        .report-subheading {
            margin: 22px 0 12px;
            padding-top: 16px;
            border-top: 1px solid var(--border-light);
            color: var(--text-main);
            font-size: 17px;
            font-weight: 800;
        }

        .report-subheading:first-child {
            margin-top: 0;
            padding-top: 0;
            border-top: none;
        }

        .report-paragraph {
            margin: 0 0 12px;
            color: #374151;
            font-size: 15px;
            line-height: 1.75;
        }

        .report-list {
            margin: 0 0 10px 18px;
            padding: 0;
            color: #374151;
        }

        .report-list li {
            margin-bottom: 8px;
            line-height: 1.7;
        }

        .report-list.ordered {
            margin-left: 22px;
        }

        .report-section-body {
            margin-top: 4px;
        }

        .report-section-body .html-table-wrap {
            margin: 14px 0 18px;
        }

        .report-code-block {
            margin: 14px 0 18px;
            padding: 16px 18px;
            border-radius: 18px;
            border: 1px solid #E5E7EB;
            background: #F8FAFC;
            color: #111827;
            font-size: 14px;
            line-height: 1.7;
            overflow-x: auto;
            white-space: pre-wrap;
        }

        .sidebar-header-title {
            margin: 4px 0 0;
            color: var(--text-main);
            font-size: 30px;
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.2;
        }

        .sidebar-menu-label {
            margin: 18px 0 10px;
            color: var(--text-muted);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        section[data-testid="stSidebar"] .stButton > button {
            width: 100%;
            justify-content: flex-start;
            border-radius: 16px;
            padding: 0.9rem 1rem;
            box-shadow: none;
            border: 1px solid transparent;
            background: transparent;
            color: #4B5563;
            font-weight: 700;
        }

        section[data-testid="stSidebar"] .stButton > button:hover {
            background: #F3F4F6;
            color: #111827;
            border: 1px solid transparent;
            box-shadow: none;
        }

        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: #EAF8F1;
            color: #059669;
            border: 1px solid #D1FAE5;
            box-shadow: none;
        }

        section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background: #E3F5EB;
            color: #047857;
            border: 1px solid #C7F3DB;
            box-shadow: none;
        }

        .stButton > button, .stDownloadButton > button {
            background: var(--primary-green);
            color: white;
            border: none;
            border-radius: 999px;
            padding: 0.78rem 1.35rem;
            font-weight: 700;
            box-shadow: 0 10px 20px rgba(22, 163, 74, 0.18);
        }

        .stButton > button:hover, .stDownloadButton > button:hover {
            background: #15803D;
            color: white;
            border: none;
        }

        div[data-baseweb="tab-list"] {
            gap: 8px;
        }

        button[data-baseweb="tab"] {
            border-radius: 999px;
            padding: 10px 18px;
        }

        @media (max-width: 1100px) {
            .workflow-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .hero-title {
                font-size: 38px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


TYPE_BADGE_CLASS = {
    "불만": "badge-complaint",
    "기능 요청": "badge-request",
    "칭찬": "badge-praise",
    "일반 문의": "badge-inquiry",
}

URGENCY_BADGE_CLASS = {"High": "badge-high", "Medium": "badge-medium", "Low": "badge-low"}


class TrustedHtml(str):
    """직접 생성한 신뢰된 HTML 조각(배지 등) 표시용 마커.

    render_html_table_html은 기본적으로 모든 셀 값을 escape하지만, 이 타입으로
    감싼 값만은 이미 안전하게 생성된 HTML이므로 escape 없이 그대로 삽입한다.
    """


def type_badge(voc_type: str) -> str:
    # voc_type은 classify.py가 고정된 값(불만/기능 요청/칭찬/일반 문의)만 반환하므로
    # VoC 원문이 그대로 흘러들어올 수 없다 — 신뢰된 HTML로 취급한다.
    badge_class = TYPE_BADGE_CLASS.get(voc_type, "badge-neutral")
    return TrustedHtml(f'<span class="badge {badge_class}">{html.escape(str(voc_type))}</span>')


def urgency_badge(urgency: str) -> str:
    # urgency도 classify.py가 고정된 값(High/Medium/Low)만 반환한다.
    badge_class = URGENCY_BADGE_CLASS.get(urgency, "badge-neutral")
    return TrustedHtml(f'<span class="badge {badge_class}">{html.escape(str(urgency))}</span>')


def render_html_table(headers: list[str], rows: list[list[str]]) -> None:
    st.markdown(render_html_table_html(headers, rows), unsafe_allow_html=True)


def _escape_cell(value) -> str:
    # TrustedHtml로 감싼 값(배지 등 직접 생성한 HTML)만 예외적으로 escape하지 않는다.
    # 그 외에는 VoC 원문(사용자 입력)이 그대로 담길 수 있으므로 항상 escape한다.
    if isinstance(value, TrustedHtml):
        return value
    return html.escape(str(value))


def render_html_table_html(headers: list[str], rows: list[list[str]]) -> str:
    header_html = "".join(f"<th>{_escape_cell(header)}</th>" for header in headers)
    body_html = ""
    for row in rows:
        cells = "".join(f"<td>{_escape_cell(cell)}</td>" for cell in row)
        body_html += f"<tr>{cells}</tr>"

    return (
        f"""
        <div class="html-table-wrap">
            <table class="html-table">
                <thead><tr>{header_html}</tr></thead>
                <tbody>{body_html}</tbody>
            </table>
        </div>
        """
    )


def render_block_gap(height: int = 28) -> None:
    st.markdown(f"<div style='height: {height}px;'></div>", unsafe_allow_html=True)


def set_selected_menu(menu_name: str) -> None:
    st.session_state.selected_menu = menu_name


def format_inline_markdown(text: str) -> str:
    # VoC 원문이 섞여 들어올 수 있는 리포트 본문이므로 먼저 escape한 뒤,
    # 그 위에 마크다운 강조 문법만 안전하게 HTML로 치환한다.
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def parse_markdown_table(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    if len(lines) < 2:
        return None
    header = [cell.strip() for cell in lines[0].strip().strip("|").split("|")]
    divider_line = lines[1].strip()
    if "|" not in divider_line or "-" not in divider_line:
        return None
    rows = []
    for line in lines[2:]:
        if "|" not in line:
            continue
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return header, rows


def split_markdown_sections(markdown_text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = "리포트"
    current_lines: list[str] = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = line[3:].strip()
            current_lines = []
        elif line.startswith("# "):
            current_title = line[2:].strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))
    return sections


def report_meta_chips(title: str, lines: list[str]) -> str:
    chips: list[str] = []
    normalized = title.lower()

    if any(keyword in normalized for keyword in ["executive", "요약"]):
        chips.append('<span class="score-chip">요약</span>')
    if "분류표" in title:
        chips.append('<span class="score-chip">원문 기준</span>')
    if "인사이트" in title:
        chips.append('<span class="score-chip">의사결정 참고</span>')
    if "기획안" in title:
        chips.append('<span class="score-chip">제품 검토</span>')
    if "queue" in normalized or "즉시 대응" in title:
        chips.append('<span class="score-chip">CS 우선 확인</span>')
    if "faq" in normalized or "가이드" in title:
        chips.append('<span class="score-chip">문서화 후보</span>')
    if "appendix" in normalized or "부록" in title:
        chips.append('<span class="score-chip">참고 자료</span>')
    return "".join(chips)


def render_report_section_body_html(lines: list[str]) -> str:
    html_blocks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if line.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            escaped_code = html.escape("\n".join(code_lines))
            html_blocks.append(f'<pre class="report-code-block"><code>{escaped_code}</code></pre>')
            i += 1
            continue

        if line.startswith("### "):
            html_blocks.append(f'<div class="report-subheading">{format_inline_markdown(line[4:].strip())}</div>')
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            table_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            parsed = parse_markdown_table(table_lines)
            if parsed:
                headers, rows = parsed
                html_blocks.append(render_html_table_html(headers, rows))
            continue

        if line.startswith("- "):
            bullet_lines = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                bullet_lines.append(format_inline_markdown(lines[i].strip()[2:]))
                i += 1
            bullet_html = "".join(f"<li>{item}</li>" for item in bullet_lines)
            html_blocks.append(f'<ul class="report-list">{bullet_html}</ul>')
            continue

        if line[:2].isdigit() and ". " in line:
            ordered_lines = []
            while i < len(lines) and lines[i].strip() and lines[i].strip()[0].isdigit() and ". " in lines[i]:
                ordered_lines.append(format_inline_markdown(lines[i].strip().split(". ", 1)[1]))
                i += 1
            ordered_html = "".join(f"<li>{item}</li>" for item in ordered_lines)
            html_blocks.append(f'<ol class="report-list ordered">{ordered_html}</ol>')
            continue

        if line.startswith("**") and line.endswith("**"):
            html_blocks.append(f'<div class="report-subhead">{format_inline_markdown(line.strip("*"))}</div>')
            i += 1
            continue

        html_blocks.append(f'<p class="report-paragraph">{format_inline_markdown(line)}</p>')
        i += 1
    return "".join(html_blocks)


def render_styled_report(markdown_text: str) -> None:
    sections = split_markdown_sections(markdown_text)
    if not sections:
        return

    page_title, _ = sections[0]
    body_sections = sections[1:] if len(sections) > 1 and sections[0][0] == page_title else sections
    st.markdown(
        f"""
        <div class="report-page-header">
            <div class="report-page-kicker">주간 운영 리포트</div>
            <div class="report-page-title">{page_title}</div>
            <div class="report-page-desc">CS 대응 우선순위와 제품팀 전달 포인트를 같은 흐름으로 검토할 수 있도록 정리한 운영 보고서입니다.</div>
            <div class="report-meta-row">
                <span class="score-chip">리포트 본문 {len(body_sections)}개 섹션</span>
                <span class="score-chip">내부 검토용</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for index, (title, lines) in enumerate(body_sections):
        section_body_html = render_report_section_body_html(lines)
        is_summary = "executive" in title.lower()
        card_class = "report-section-card report-section-card--summary" if is_summary else "report-section-card"
        st.markdown(
            f"""
            <div class="{card_class}">
                <div class="report-section-head">
                    <div>
                        <div class="report-section-kicker">리포트 섹션 {index + 1}</div>
                        <div class="report-section-title">{title}</div>
                    </div>
                    <div>{report_meta_chips(title, lines)}</div>
                </div>
                <div class="report-section-body">{section_body_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if index < len(body_sections) - 1:
            render_block_gap(18)


@st.cache_data(show_spinner="기본 VoC 데이터를 분석 중입니다.")
def load_original_analysis() -> dict:
    return pipeline.run_analysis(
        input_path=config.DEFAULT_INPUT_CSV,
        output_dir=config.ORIGINAL_OUTPUT_DIR,
        dataset_label="original",
        default_year=2026,
        enforce_label_consistency=False,
    )


@st.cache_data(show_spinner="업로드한 CSV를 분석 중입니다.")
def run_uploaded_analysis(file_bytes: bytes, filename: str) -> dict:
    temp_path = config.UPLOADED_OUTPUT_DIR / f"_upload_{filename}"
    config.UPLOADED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(file_bytes)
    return pipeline.run_analysis(
        input_path=temp_path,
        output_dir=config.UPLOADED_OUTPUT_DIR,
        dataset_label="uploaded",
        default_year=2026,
        enforce_label_consistency=False,
    )


def count_by_type(summary: dict, voc_type: str) -> int:
    by_type = summary["by_type"].set_index("voc_type")
    return int(by_type.loc[voc_type, "count"]) if voc_type in by_type.index else 0


def metric_card(label: str, value: str | int, footnote: str) -> str:
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-footnote">{footnote}</div>
    </div>
    """


def render_metrics(result: dict) -> None:
    summary = result["summary"]
    quality = result["quality_summary"]
    cards = [
        ("즉시 대응 큐", f"{summary['cs_immediate_count']:,}", "CS 에스컬레이션 우선 확인"),
        ("이탈 위험", f"{summary['churn_risk_count']:,}", "불만/긴급도 기반 추적 필요"),
        ("제품 백로그 후보", f"{summary['product_candidate_count']:,}", "제품팀 검토 대상"),
        ("FAQ 전환 후보", f"{summary['faq_candidate_count']:,}", "반복 문의 문서화 가능"),
        ("총 유입 VoC", f"{quality['row_count_before']:,}", f"정제 후 {quality['row_count_after']:,}건 유지"),
        ("불만", f"{count_by_type(summary, '불만'):,}", "CS 원인 분류 필요"),
        ("기능 요청", f"{count_by_type(summary, '기능 요청'):,}", "백로그 매핑 필요"),
        ("중복 제거", f"{len(quality['duplicates_removed']):,}", "콘텐츠 중복 기준 정리"),
    ]

    for row_start in range(0, len(cards), 4):
        cols = st.columns(4)
        for col, (label, value, footnote) in zip(cols, cards[row_start:row_start + 4]):
            with col:
                st.markdown(metric_card(label, value, footnote), unsafe_allow_html=True)
        if row_start + 4 < len(cards):
            st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)


def render_workflow() -> None:
    steps = [
        ("1", "원문 수집", "채널별 문의 원문과 고객군 메타데이터를 불러옵니다."),
        ("2", "품질 점검", "날짜 표준화, 중복 제거, 결측 검증으로 운영 가능한 상태를 만듭니다."),
        ("3", "CS 분류", "불만, 기능 요청, 칭찬, 일반 문의로 1차 트리아지를 수행합니다."),
        ("4", "이슈 집계", "토픽, 긴급도, 고객군 기준으로 반복 패턴을 묶습니다."),
        ("5", "운영 인사이트", "즉시 대응 건과 제품 전달 이슈를 분리해 정리합니다."),
        ("6", "후속 액션", "CS 리포트와 제품 백로그 문서를 생성합니다."),
    ]
    html = ['<div class="workflow-grid">']
    for number, title, desc in steps:
        html.append(
            f"""
            <div class="step-card">
                <div class="step-number">{number}</div>
                <div class="step-title">{title}</div>
                <div class="step-desc">{desc}</div>
            </div>
            """
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_dashboard_overview(result: dict) -> None:
    summary = result["summary"]
    high_risk = summary["high_risk_vocs"].copy()
    if not high_risk.empty:
        high_risk_rows = []
        for _, row in high_risk.iterrows():
            high_risk_rows.append(
                [
                    str(row["id"]),
                    str(row["topic"]),
                    str(row["customer_type"]),
                    type_badge(str(row["voc_type"])),
                    urgency_badge(str(row["urgency"])),
                    str(row["content"]),
                ]
            )
    else:
        high_risk_rows = []

    left = st.container()
    with left:
        st.markdown(
            """
            <div class="dashboard-card">
                <div class="card-label">유입 현황</div>
                <div class="card-title">유형별 유입 현황</div>
                <div class="card-subtitle">이번 주에 어떤 유형의 문의가 많이 들어왔는지 CS팀 기준으로 먼저 봅니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.bar_chart(summary["by_type"].set_index("voc_type")["count"], color="#16A34A")
        render_block_gap()

        st.markdown(
            """
            <div class="dashboard-card">
                <div class="card-label">즉시 대응</div>
                <div class="card-title">즉시 대응 필요 건</div>
                <div class="card-subtitle">High urgency 또는 계약/이탈 리스크가 큰 건을 CS팀이 먼저 확인할 수 있게 정리했습니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if high_risk_rows:
            render_html_table(["ID", "주제", "고객군", "유형", "긴급도", "원문"], high_risk_rows)
        else:
            st.info("즉시 대응 대상이 없습니다.")
        render_block_gap()

    bottom_left, bottom_right = st.columns(2)
    with bottom_left:
        st.markdown(
            """
            <div class="dashboard-card">
                <div class="card-label">반복 이슈</div>
                <div class="card-title">반복 토픽 Top 5</div>
                <div class="card-subtitle">CS와 제품팀이 함께 봐야 할 반복 이슈를 빠르게 확인합니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.bar_chart(summary["top_topics"].set_index("topic")["count"], color="#0F5132")
        render_block_gap()

    with bottom_right:
        st.markdown(
            """
            <div class="dashboard-card">
                <div class="card-label">입력 품질</div>
                <div class="card-title">입력 품질 체크</div>
                <div class="card-subtitle">분류 전에 먼저 막아야 할 입력 이슈를 운영 관점으로 요약했습니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        quality = result["quality_summary"]
        quality_df = pd.DataFrame(
            [
                {"항목": "중복 제거", "건수": len(quality["duplicates_removed"])},
                {"항목": "채널 누락", "건수": len(quality["channel_missing_ids"])},
                {"항목": "날짜 파싱 실패", "건수": len(quality["date_parse_failed_ids"])},
                {"항목": "키워드 누락", "건수": len(quality["keyword_hint_missing_ids"])},
            ]
        )
        st.dataframe(quality_df, width="stretch", hide_index=True)
        render_block_gap()


def render_insights(result: dict) -> None:
    st.markdown(
        """
        <div class="dashboard-card">
            <div class="card-label">운영 메모</div>
            <div class="card-title">CS / 제품팀 공통 인사이트</div>
            <div class="card-subtitle">어떤 이슈를 CS가 당장 대응하고, 어떤 이슈를 제품팀으로 넘길지 기준이 되는 메모입니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for index, insight_item in enumerate(result["insights"], start=1):
        # insight 문구는 VoC 원문 인용을 포함할 수 있으므로 렌더링 전에 escape한다.
        title = html.escape(str(insight_item["title"]))
        observation = html.escape(str(insight_item["observation"]))
        business_meaning = html.escape(str(insight_item["business_meaning"]))
        recommended_action = html.escape(str(insight_item["recommended_action"]))
        st.markdown(
            f"""
            <div class="insight-card">
                <div class="insight-title">{index}. {title}</div>
                <p><span class="field-label">핵심 내용</span><br>{observation}</p>
                <p><span class="field-label">업무 의미</span><br>{business_meaning}</p>
                <p><span class="field-label">권장 액션</span><br>{recommended_action}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_proposals(result: dict) -> None:
    st.markdown(
        """
        <div class="dashboard-card">
            <div class="card-label">제품 백로그</div>
            <div class="card-title">제품팀 전달 후보</div>
            <div class="card-subtitle">반복 VoC를 기능/운영 개선 백로그로 묶고 우선순위 점수로 정렬했습니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for index, proposal in enumerate(result["proposals"], start=1):
        scores = proposal["scores"]
        chips = "".join(
            [
                f'<span class="score-chip">빈도 {scores["frequency_score"]}</span>',
                f'<span class="score-chip">영향도 {scores["impact_score"]}</span>',
                f'<span class="score-chip">긴급도 {scores["urgency_score"]}</span>',
                f'<span class="score-chip">규제 연관성 {scores["regulation_score"]}</span>',
                f'<span class="score-chip">구현 난이도 {scores["effort_score"]}</span>',
            ]
        )
        # render_html_table_html이 내부적으로 escape하므로 여기서는 원본 값만 전달한다
        # (이중 escape 방지).
        evidence_table_html = render_html_table_html(
            ["ID", "고객군", "유형", "긴급도", "원문"],
            [
                [
                    str(row["id"]),
                    str(row["customer_type"]),
                    str(row["voc_type"]),
                    str(row["urgency"]),
                    str(row["quote"]),
                ]
                for row in proposal["evidence_rows"]
            ],
        )
        st.markdown(
            f"""
            <div class="plan-card">
                <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">
                    <div>
                        <div class="card-label">기획안 {index}</div>
                        <div class="card-title">{proposal['title']}</div>
                    </div>
                    <div class="plan-score-wrap">
                        <div class="plan-score-label">Score</div>
                        <div class="plan-score">{scores['priority_score']}</div>
                    </div>
                </div>
                <div style="margin-top:10px;">{chips}</div>
                <p style="margin-top:16px;"><span class="field-label">문제 정의</span><br>{proposal['problem_definition']}</p>
                <p><span class="field-label">핵심 기능</span><br>{proposal['content']['key_feature']}</p>
                <p><span class="field-label">자동화 방식</span><br>{proposal['content']['automation']}</p>
                <p><span class="field-label">1차 범위</span><br>{proposal['content']['mvp_v1']}</p>
                <div class="field-label" style="margin-top:16px;">근거 VoC</div>
                {evidence_table_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_block_gap(18)


def render_overview_tab(result: dict) -> None:
    st.markdown('<div class="section-title">운영 요약</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="section-desc">분석 기간 <b>{result["week_label"]}</b> · 기준 데이터 <code>data/voc.csv</code></div>',
        unsafe_allow_html=True,
    )
    render_dashboard_overview(result)


def render_basic_tab(result: dict) -> None:
    qs = result["quality_summary"]
    st.markdown('<div class="section-title">분류 결과 상세</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="dashboard-card">
            <div class="card-label">분류 기준 요약</div>
            <div class="card-title">실무 판단 기준</div>
            <div class="card-subtitle">불만 → 기능 요청 → 칭찬 → 일반 문의 순으로 우선 판정하고, 긴급도는 마감·반려·오류 같은 직접 신호를 우선 반영합니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="table-caption">
        원본 {qs['row_count_before']:,}건에서 중복 {len(qs['duplicates_removed']):,}건을 정리했고,
        채널 누락 {len(qs['channel_missing_ids']):,}건, 키워드 누락 {len(qs['keyword_hint_missing_ids']):,}건을 기록했습니다.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.dataframe(result["summary"]["by_type"], width="stretch", hide_index=True)
    render_block_gap()

    classified_df = result["classified_df"].copy()
    filter_cols = st.columns([1, 1, 1, 1.5])
    with filter_cols[0]:
        type_filter = st.multiselect("유형", sorted(classified_df["voc_type"].dropna().unique()), key="type_filter")
    with filter_cols[1]:
        topic_filter = st.multiselect("토픽", sorted(classified_df["topic"].dropna().unique()), key="topic_filter")
    with filter_cols[2]:
        urgency_filter = st.multiselect("긴급도", ["High", "Medium", "Low"], key="urgency_filter")
    with filter_cols[3]:
        search_term = st.text_input("원문 검색", key="search_term")

    if type_filter:
        classified_df = classified_df[classified_df["voc_type"].isin(type_filter)]
    if topic_filter:
        classified_df = classified_df[classified_df["topic"].isin(topic_filter)]
    if urgency_filter:
        classified_df = classified_df[classified_df["urgency"].isin(urgency_filter)]
    if search_term:
        classified_df = classified_df[classified_df["content"].str.contains(search_term, case=False, na=False)]

    display_df = classified_df[
        ["id", "date_clean", "customer_type", "channel", "topic", "voc_type", "urgency", "content"]
    ].rename(
        columns={
            "id": "ID",
            "date_clean": "날짜",
            "customer_type": "고객군",
            "channel": "채널",
            "topic": "토픽",
            "voc_type": "유형",
            "urgency": "긴급도",
            "content": "원문",
        }
    )
    st.caption(f"{len(display_df):,}건 표시 중 / 전체 {len(result['classified_df']):,}건")
    st.dataframe(display_df, width="stretch", hide_index=True)
    render_block_gap()

    render_insights(result)


def render_pipeline_tab(result: dict) -> None:
    st.markdown('<div class="section-title">운영 리포트</div>', unsafe_allow_html=True)
    st.code(
        "CSV 입력 → 정제(clean) → 분류(classify) → 집계(aggregate) → 인사이트(insight) → 리포트(report) → 개선안(product_plan)",
        language="text",
    )
    render_block_gap(18)
    render_styled_report(result["weekly_report_md"])
    render_block_gap()
    st.download_button(
        "주간 리포트 .md 다운로드",
        data=result["weekly_report_md"],
        file_name="weekly_voc_report.md",
        mime="text/markdown",
        key="download_weekly_report_md",
    )


def render_proposal_tab(result: dict) -> None:
    st.markdown('<div class="section-title">제품팀 전달안</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-desc">각 카드 우측 상단의 <b>Score</b>는 우선순위 점수입니다. '
        '<code>priority_score = 빈도 + 영향도 + 긴급도 + 규제 연관성 - 구현 난이도</code> 산식으로 계산하며, '
        '값이 높을수록 다음 스프린트에 먼저 올릴 후보입니다. 각 항목의 세부 배점 기준은 '
        '<code>output/decisions.md</code> 6장을 참고하세요.</div>',
        unsafe_allow_html=True,
    )
    render_block_gap(10)
    render_proposals(result)
    render_block_gap(4)
    st.download_button(
        "제품 개선안 .md 다운로드",
        data=result["proposal_md"],
        file_name="product_improvement_plan.md",
        mime="text/markdown",
        key="download_product_plan_md",
    )
    render_block_gap(48)
    st.markdown(
        """
        <div class="dashboard-card">
            <div class="card-label">구글시트 내보내기</div>
            <div class="card-title">TSV 내보내기</div>
            <div class="card-subtitle">구글시트 셀에 바로 입력할 수 있는 탭 구분 텍스트입니다. 복사 버튼으로 전체를 클립보드에 담을 수 있습니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    tsv_text = result.get("sheets_export_tsv")
    if tsv_text is None:
        tsv_text = sheets_export.build_tsv(result["classified_df"])
    copy_markup = html.escape(tsv_text)
    components.html(
        f"""
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:14px 0 12px;">
            <button id="copy-tsv-btn" style="
                border:none;
                border-radius:999px;
                padding:10px 16px;
                background:#10B69F;
                color:#fff;
                font-weight:700;
                cursor:pointer;
                box-shadow:0 10px 20px rgba(22,163,74,0.18);
            ">TSV 복사</button>
            <span id="copy-tsv-status" style="color:#6B7280;font-size:13px;">버튼을 누르면 클립보드에 복사됩니다.</span>
        </div>
        <textarea id="tsv-source" readonly style="
            width:100%;
            height:260px;
            resize:vertical;
            border:1px solid #E5E7EB;
            border-radius:18px;
            padding:14px 16px;
            font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
            font-size:12px;
            line-height:1.6;
            box-sizing:border-box;
            background:#F8FAFC;
        ">{copy_markup}</textarea>
        <script>
        const button = document.getElementById('copy-tsv-btn');
        const source = document.getElementById('tsv-source');
        const status = document.getElementById('copy-tsv-status');
        button.addEventListener('click', async () => {{
            try {{
                await navigator.clipboard.writeText(source.value);
                status.textContent = 'TSV가 복사되었습니다.';
                button.textContent = '복사 완료';
            }} catch (err) {{
                source.focus();
                source.select();
                status.textContent = '클립보드가 막혀 있어 텍스트를 선택했습니다.';
                button.textContent = '수동 복사';
            }}
        }});
        </script>
        """,
        height=380,
    )


def render_upload_tab(original_result: dict) -> None:
    st.markdown('<div class="section-title">신규 VoC 업로드 분석</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-desc">필수 컬럼은 <code>id, date, channel, customer_type, content, keyword_hint</code>입니다.</div>',
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader("VoC CSV 파일 선택", type=["csv"], key="voc_uploader")

    if uploaded_file is None:
        st.info("CSV를 업로드하면 동일한 파이프라인으로 즉시 분석합니다.")
        return

    raw_bytes = uploaded_file.getvalue()
    try:
        preview_df = pd.read_csv(io.BytesIO(raw_bytes), dtype=str, keep_default_na=False, encoding="utf-8")
        missing_cols = clean.check_required_columns(preview_df)
    except Exception as exc:
        st.error(f"CSV를 읽을 수 없습니다: {exc}")
        return

    if missing_cols:
        st.error(f"필수 컬럼이 누락되었습니다: {', '.join(missing_cols)}")
        return

    st.success(f"필수 컬럼 확인 완료. 총 {len(preview_df):,}건을 분석합니다.")
    try:
        uploaded_result = run_uploaded_analysis(raw_bytes, uploaded_file.name)
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        return

    render_metrics(uploaded_result)

    compare_df = pd.DataFrame(
        [
            {"지표": "총 VoC", "기본 데이터": original_result["quality_summary"]["row_count_before"], "업로드 데이터": uploaded_result["quality_summary"]["row_count_before"]},
            {"지표": "정제 후", "기본 데이터": original_result["quality_summary"]["row_count_after"], "업로드 데이터": uploaded_result["quality_summary"]["row_count_after"]},
            {"지표": "불만", "기본 데이터": count_by_type(original_result["summary"], "불만"), "업로드 데이터": count_by_type(uploaded_result["summary"], "불만")},
            {"지표": "기능 요청", "기본 데이터": count_by_type(original_result["summary"], "기능 요청"), "업로드 데이터": count_by_type(uploaded_result["summary"], "기능 요청")},
            {"지표": "칭찬", "기본 데이터": count_by_type(original_result["summary"], "칭찬"), "업로드 데이터": count_by_type(uploaded_result["summary"], "칭찬")},
            {"지표": "일반 문의", "기본 데이터": count_by_type(original_result["summary"], "일반 문의"), "업로드 데이터": count_by_type(uploaded_result["summary"], "일반 문의")},
            {"지표": "High urgency", "기본 데이터": original_result["summary"]["cs_immediate_count"], "업로드 데이터": uploaded_result["summary"]["cs_immediate_count"]},
            {"지표": "제품 후보", "기본 데이터": original_result["summary"]["product_candidate_count"], "업로드 데이터": uploaded_result["summary"]["product_candidate_count"]},
        ]
    )
    st.dataframe(compare_df, width="stretch", hide_index=True)
    render_block_gap()

    uploaded_display = uploaded_result["classified_df"][
        ["id", "date_clean", "customer_type", "topic", "voc_type", "urgency", "content"]
    ].rename(
        columns={
            "id": "ID",
            "date_clean": "날짜",
            "customer_type": "고객군",
            "topic": "토픽",
            "voc_type": "유형",
            "urgency": "긴급도",
            "content": "원문",
        }
    )
    st.dataframe(uploaded_display, width="stretch", hide_index=True)
    render_block_gap()

    quality_log_path = uploaded_result["paths"]["quality_log_md"]
    if quality_log_path.exists():
        st.markdown(
            """
            <div class="dashboard-card">
                <div class="card-label">업로드 품질 점검</div>
                <div class="card-title">이번 업로드의 정제 로그</div>
                <div class="card-subtitle">업로드한 CSV에서 발견된 형식 혼용, 중복, 결측 처리 내역만 확인합니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_styled_report(quality_log_path.read_text(encoding="utf-8"))
        render_block_gap()

    dl_cols = st.columns(3)
    with dl_cols[0]:
        st.download_button(
            "분류 결과 CSV",
            data=uploaded_result["classified_df"].to_csv(index=False).encode("utf-8"),
            file_name="voc_classification_uploaded.csv",
            mime="text/csv",
        )
    with dl_cols[1]:
        st.download_button(
            "주간 리포트 .md",
            data=uploaded_result["weekly_report_md"],
            file_name="weekly_voc_report_uploaded.md",
            mime="text/markdown",
        )
    with dl_cols[2]:
        st.download_button(
            "제품 개선안 .md",
            data=uploaded_result["proposal_md"],
            file_name="product_improvement_plan_uploaded.md",
            mime="text/markdown",
        )


def render_decisions_tab(result: dict) -> None:
    st.markdown('<div class="section-title">품질 로그와 검증</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-desc">데이터 정제 로그, 분류 기준, 필수 검증 결과를 같은 카드형 문서 레이아웃으로 확인합니다.</div>',
        unsafe_allow_html=True,
    )

    classified_df = result["classified_df"]
    has_001 = "001" in classified_df["id"].values
    has_031 = "031" in classified_df["id"].values
    duplicate_ok = has_001 and not has_031
    row_043 = classified_df[classified_df["id"] == "043"]
    sample_043_ok = not row_043.empty and row_043.iloc[0]["voc_type"] == "불만"

    validation_cards = st.columns(2)
    with validation_cards[0]:
        duplicate_score_class = "plan-score" if duplicate_ok else "plan-score"
        duplicate_score_style = "" if duplicate_ok else ' style="background:#FEF2F2;border-color:#FECACA;color:#B91C1C;"'
        st.markdown(
            f"""
            <div class="plan-card">
                <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">
                    <div>
                        <div class="card-label">중복 검증</div>
                        <div class="card-title">샘플 001 / 031 확인</div>
                    </div>
                    <div class="{duplicate_score_class}"{duplicate_score_style}>{"정상" if duplicate_ok else "확인"}</div>
                </div>
                <p style="margin-top:16px;"><span class="field-label">검증 기준</span><br>중복 샘플에서 <code>id 001</code>은 남고 <code>id 031</code>은 제거되어야 합니다.</p>
                <p><span class="field-label">현재 결과</span><br>{"중복 제거 로직이 정상 동작했습니다." if duplicate_ok else "중복 처리 결과를 다시 확인해야 합니다."}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with validation_cards[1]:
        sample_043_style = "" if sample_043_ok else ' style="background:#FEF2F2;border-color:#FECACA;color:#B91C1C;"'
        st.markdown(
            f"""
            <div class="plan-card">
                <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">
                    <div>
                        <div class="card-label">분류 검증</div>
                        <div class="card-title">샘플 id 043 확인</div>
                    </div>
                    <div class="plan-score"{sample_043_style}>{"정상" if sample_043_ok else "확인"}</div>
                </div>
                <p style="margin-top:16px;"><span class="field-label">검증 기준</span><br><code>id 043</code>은 혼합 케이스 규칙에 따라 <b>불만</b>으로 분류되어야 합니다.</p>
                <p><span class="field-label">현재 결과</span><br>{"검증 샘플 id 043은 불만으로 정상 분류되었습니다." if sample_043_ok else "검증 샘플 id 043 분류를 다시 확인해야 합니다."}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_block_gap()

    quality_log_path = result["paths"]["quality_log_md"]
    if quality_log_path.exists():
        st.markdown(
            """
            <div class="dashboard-card">
                <div class="card-label">품질 로그</div>
                <div class="card-title">데이터 품질 점검 로그</div>
                <div class="card-subtitle">업로드 원본 기준의 정제 이슈, 처리 방식, 실무 권장사항을 카드형 문서로 확인합니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_styled_report(quality_log_path.read_text(encoding="utf-8"))
        render_block_gap()

    if config.CLASSIFICATION_DECISIONS_MD.exists():
        st.markdown(
            """
            <div class="dashboard-card">
                <div class="card-label">분류 기준</div>
                <div class="card-title">분류 및 판단 기준 문서</div>
                <div class="card-subtitle">유형 분류, 혼합 케이스 처리, 긴급도 산정, 제품 우선순위 기준을 같은 보고서 스타일로 확인합니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_styled_report(config.CLASSIFICATION_DECISIONS_MD.read_text(encoding="utf-8"))


inject_css()
original = load_original_analysis()

st.sidebar.markdown('<div class="sidebar-header-title">VoC 운영</div>', unsafe_allow_html=True)
st.sidebar.caption("내부 CS팀 · 제품팀 운영 화면")
menu_options = [
    "운영 요약",
    "분류 결과",
    "운영 리포트",
    "제품팀 전달안",
    "신규 업로드",
]
if "selected_menu" not in st.session_state:
    st.session_state.selected_menu = "운영 요약"

st.sidebar.markdown('<div class="sidebar-menu-label">메뉴</div>', unsafe_allow_html=True)
for menu_name in menu_options:
    button_type = "primary" if st.session_state.selected_menu == menu_name else "secondary"
    st.sidebar.button(
        menu_name,
        key=f"menu_{menu_name}",
        type=button_type,
        on_click=set_selected_menu,
        args=(menu_name,),
    )

selected_menu = st.session_state.selected_menu

logo_data_uri = load_logo_data_uri()
brand_mark_html = (
    f'<img class="brand-logo" src="{logo_data_uri}" alt="CarbonLink" />'
    if logo_data_uri
    else '<div class="brand-title">VoC 운영 콘솔</div>'
)

st.markdown('<div class="app-shell">', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="top-header">
        <div class="brand-wrap">
            {brand_mark_html}
            <div>
                <div class="brand-subtitle">CarbonLink VoC 운영 콘솔</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

hero_left, hero_right = st.columns([1.35, 0.65])
top_summary_card_class = "preview-card alert" if original["summary"]["cs_immediate_count"] > 0 else "preview-card"
with hero_left:
    st.markdown(
        """
        <div class="hero">
            <div class="eyebrow">CarbonLink 운영 대시보드</div>
            <div class="hero-title">VoC 운영 현황,<br><span class="green">정확하고 간편하게</span></div>
            <div class="hero-desc">
                CS 큐, 반복 이슈, 데이터 품질, 주간 리포트
            </div>
            <div class="hero-actions">
                <span class="hero-chip">즉시 대응 큐</span>
                <span class="hero-chip">이탈 위험 추적</span>
                <span class="hero-chip">제품 전달 후보</span>
                <span class="hero-chip">주간 리포트</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hero_right:
    st.markdown(
        f"""
        <div class="{top_summary_card_class}" style="margin-top:120px;">
            <div class="preview-label">즉시 대응</div>
            <div class="preview-metric">{original['summary']['cs_immediate_count']:,}건</div>
            <div class="preview-caption">
                분석 기간 <b>{original['week_label']}</b><br>
                총 유입 <b>{original['summary']['total_count']}</b>건 · 제품팀 전달 후보 <b>{original['summary']['product_candidate_count']}</b>건 · 이탈 위험 <b>{original['summary']['churn_risk_count']}</b>건
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if selected_menu == "운영 요약":
    st.markdown('<div class="section-title">운영 지표</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-desc">운영 우선순위 기준 지표</div>',
        unsafe_allow_html=True,
    )
    render_metrics(original)

    st.markdown('<div class="section-title">운영 흐름</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-desc">CS 접수부터 제품팀 전달안 정리까지의 처리 흐름</div>',
        unsafe_allow_html=True,
    )
    render_workflow()

    render_overview_tab(original)
elif selected_menu == "분류 결과":
    render_basic_tab(original)
elif selected_menu == "운영 리포트":
    render_pipeline_tab(original)
elif selected_menu == "제품팀 전달안":
    render_proposal_tab(original)
elif selected_menu == "신규 업로드":
    render_upload_tab(original)

st.markdown(
    """
    <div class="footer-note">
        CS 대응, 제품팀 전달 후보, 업로드 분석, 주간 리포트 확인용 화면입니다.
    </div>
    </div>
    """,
    unsafe_allow_html=True,
)
