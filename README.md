# CarbonLink VoC Report Bot

## 1. 프로젝트 개요

**문제 상황**
리뉴어스랩(카본링크)의 CS팀은 이메일·채널톡·미팅메모로 산발적으로 들어오는 VoC를 수작업으로 엑셀에
정리하고 있어, 유형별 패턴을 파악하기 어렵고 비즈니스 의사결정에 활용하지 못하고 있다. CBAM 확정 시행
(2026-01)과 CSRD 적용 확대가 맞물리며 문의·불만이 급증하는 시점이라 이 문제는 더 커지고 있다.

**해결 목표**
VoC CSV 한 장이면 정제 → 분류 → 집계 → 인사이트 → 주간 리포트 → 제품 개선 기획안까지 자동으로 생성되는
재사용 가능한 파이프라인을 만든다. 새 CSV를 넣어도 동일 절차로 동일 품질의 결과물이 나와야 한다.

**최종 산출물** (`python src/run_pipeline.py` 한 번 실행 시 전부 생성)

- `output/<label>/weekly_voc_report.md` — CS·제품팀·리더가 읽는 종합 주간 리포트
- `output/<label>/product_improvement_plan.md` — 우선순위 상위 2건의 제품 개선 기획안
- `output/<label>/voc_classification.csv` — 4유형 분류 + topic·urgency·규제 맥락
- `output/<label>/data_quality_log.md` — 정제 전/후 데이터 품질 점검 로그
- `output/<label>/sheets_export.tsv` — 구글시트에 바로 붙여넣을 수 있는 내보내기 파일
- `output/decisions.md` — 분류 기준·우선순위 산정식 방법론 문서

## 2. Why This Output

VoC를 4유형으로 나누는 것 자체가 목적이 아니라, **누가 이 리포트를 읽고 무엇을 하는가**를 기준으로
섹션을 설계했다.

- **CS팀**: `weekly_voc_report.md`의 High urgency Queue로 오늘 당장 응대할 건을 바로 파악하고, FAQ 후보
  섹션으로 반복 문의를 지식베이스화한다. 신규 담당자는 이 두 섹션만 봐도 "무엇부터 처리해야 하는지"와
  "어떤 절차 문의가 자주 오는지"를 별도 온보딩 자료 없이 파악할 수 있다.
- **제품팀**: 제품팀 전달 후보 섹션과 `product_improvement_plan.md`의 우선순위 점수로, 반복되는
  불만·요청을 감(感)이 아니라 VoC 건수·고객 세그먼트·구현 난이도 기준으로 다음 스프린트에 올릴지
  판단할 수 있다.
- **리더/PM**: 비즈니스 인사이트 섹션이 CBAM/CSRD 같은 규제 변화 시점과 VoC 급증 패턴을 직접 연결해
  보여줘서, "왜 지금 이 문의가 늘었는가"를 규제 캘린더 없이도 파악하고 이탈 위험·세일즈 레퍼런스 같은
  리스크·기회를 조기에 포착할 수 있다.

## 3. Data Strategy

| 데이터셋 | 목적 | 산출물 |
|---|---|---|
| `voc.csv` | 과제 제공 데이터 기반 필수 분석 | `output/original/weekly_voc_report.md` |
| `voc_augmented.csv` | 실무 운영 규모 가정 검증 | `output/augmented/weekly_voc_report.md` |

> 제공된 voc.csv로 필수 리포트와 제품 개선 기획안을 생성했습니다. 추가 synthetic 데이터는 실제 인사이트
> 근거가 아니라, 새 CSV가 들어와도 동일 파이프라인이 재사용 가능한지 검증하기 위한 별도 테스트 용도로만
> 사용했습니다.

synthetic 데이터에는 검증용 컬럼(`expected_voc_type`/`expected_topic`/`expected_urgency`)을 별도로 심어
두어 실제 분류 결과와 정량 비교가 가능하며, 2026-07-01 실행 기준 정확도 100%를 확인했다
(`output/augmented/synthetic_data_note.md` 참고). 두 데이터셋의 결과물은 `output/original/`과
`output/augmented/`로 폴더가 완전히 분리되고, 같은 폴더를 다른 데이터셋으로 재사용하면 파이프라인이
즉시 에러를 낸다.

## 4. Pipeline

```
정제 → 분류 → 집계 → 인사이트 → 주간 리포트 → 제품 개선 기획안
(clean)  (classify)  (aggregate)  (insight)  (report)      (product_plan)
```

`src/run_pipeline.py`가 6단계를 순서대로 실행한다. 각 모듈은 `python src/<module>.py --mode <label>`로
개별 실행도 가능하다.

## 5. 실행 방법

원본 데이터 분석:
```bash
pip install -r requirements.txt
python src/run_pipeline.py --input data/voc.csv --output output/original --dataset-label original --default-year 2026
```

확장 데이터 생성:
```bash
python src/generate_synthetic_voc.py --base data/voc.csv --output data/voc_augmented.csv --n 200 --seed 42
```

확장 데이터 검증:
```bash
python src/run_pipeline.py --input data/voc_augmented.csv --output output/augmented --dataset-label augmented --default-year 2026
```

옵션 요약: `--input`(입력 CSV) · `--output`(저장 폴더) · `--default-year`(연도 없는 날짜의 기본 연도,
기본 2026) · `--week-label`(리포트 제목 주차명, 생략 시 데이터 기간으로 자동 생성) ·
`--dataset-label`(`original`|`augmented`). 입력 파일이 없거나 필수 컬럼이 누락되면 트레이스백 없이
원인을 바로 알려주고 종료한다.

**터미널 출력 예시** (원본 데이터 분석 실행 시)

```
[run_pipeline] 실행 완료
- 입력 데이터셋 라벨: original
- 정제 전 행 수: 45
- 정제 후 행 수: 44
- 생성 파일 목록:
    output/original/voc-cleaned.csv
    output/original/voc_classification.csv
    output/original/data_quality_log.md
    output/original/voc-summary.csv
    output/original/insight-report.md
    output/original/product_improvement_plan.md
    output/original/weekly_voc_report.md
    output/original/decisions.md
    output/original/sheets_export.tsv
- High urgency 건수: 6
- 제품 개선 기획안 건수: 2
- 구글시트 붙여넣기용 TSV 생성됨: output/original/sheets_export.tsv (--push-sheets로 실제 시트에 자동 기입 가능)
```

확장 데이터(`voc_augmented.csv`, 245건)로 실행하면 동일한 8개 파일이 `output/augmented/`에 생성되고,
`정제 후 행 수: 237`(완전 중복 8건 제거) / `High urgency 건수: 31` / `제품 개선 기획안 건수: 2`로 출력된다
— 별도 분기 없이 같은 `run_pipeline.py`가 두 데이터셋 모두 끝까지 완주한다.

**생성 파일 목록** (`output/<label>/`, label = `original` 또는 `augmented`)

| 파일 | original | augmented |
|---|---|---|
| `voc-cleaned.csv` | ✅ | ✅ |
| `voc_classification.csv` | ✅ | ✅ |
| `data_quality_log.md` | ✅ | ✅ |
| `voc-summary.csv` | ✅ | ✅ |
| `insight-report.md` | ✅ | ✅ |
| `product_improvement_plan.md` | ✅ | ✅ |
| `weekly_voc_report.md` | ✅ | ✅ |
| `decisions.md` (실행 로그) | ✅ | ✅ |
| `sheets_export.tsv` | ✅ | ✅ |
| `synthetic_data_note.md` | — | ✅ (synthetic 생성 시에만) |

## 6. Streamlit 대시보드

```bash
streamlit run app.py
```

`app.py`는 분석 로직을 직접 담지 않는다 — `src/pipeline.py`의 `run_analysis()`를 호출해 정제·분류·집계·
인사이트·리포트·기획안 결과를 받아 화면에 그리기만 한다 (CLI `run_pipeline.py`도 동일한 `run_analysis()`를
공유한다). CarbonLink 스타일 가이드(`design.md`)에 따라 화이트 배경 + 그린 포인트 컬러의 카드형 SaaS UI로
구성했다.

- **Hero + 상태 배지**: Basic Ready / Standard Pipeline / Challenge Plan / CSV Upload
- **요약 지표 카드**: 총 VoC · 정제 후 VoC · 불만 · 기능 요청 · 칭찬 · 일반 문의 · High urgency · 제품팀 전달 후보
- **Overview / Basic Report / Standard Pipeline / Challenge Plan / Upload CSV / Decisions & Quality** 6개 탭
- **Upload CSV 탭**: 새 CSV를 올리면 필수 컬럼을 즉시 검증하고, 동일 파이프라인으로 분석해
  `output/uploaded/`에 저장한다 (`output/original/`의 메인 산출물과 절대 섞지 않음). 원본과의 지표
  비교표와 결과 다운로드(CSV/MD)를 제공한다.

## 7. Claude Code Slash Command

```
/voc-report data/voc.csv output/original original
/voc-report data/voc_augmented.csv output/augmented augmented
```

인자를 생략하면 `data/voc.csv output/original original` 기본값으로 실행된다 (`.claude/commands/voc-report.md`).

## 8. 구글시트 연동 (선택)

Claude Code 터미널 환경에는 Cowork의 구글시트 커넥터가 없고, `CLAUDE.md`는 별도 API 키 사용을 원칙적으로
금지한다. 그래서 두 단계로 구현했다 (설계 근거는 `output/decisions.md` 7장 참고).

- **기본(항상 실행, 자격증명 불필요)**: 매 실행마다 `output/<label>/sheets_export.tsv`가 생성된다.
  구글시트에서 전체 선택 후 붙여넣기만 하면 분류 결과 표가 그대로 채워진다.
- **선택(opt-in, 서비스 계정 필요)**: 본인의 구글 서비스 계정 자격증명(JSON)과 spreadsheet ID가 있으면
  실제 시트에 "VoC 분류"·"요약" 두 워크시트를 자동으로 채운다.

```bash
pip install gspread google-auth   # 자동 기입을 쓸 때만 필요
python src/run_pipeline.py --input data/voc.csv --output output/original --dataset-label original \
  --push-sheets --sheet-id <spreadsheet_id> --sheets-credentials <service_account.json>
```

Streamlit의 **Challenge Plan** 탭에서도 동일 기능을 UI로 제공한다 (TSV 다운로드는 항상 가능, 자동 기입은
Spreadsheet ID와 서비스 계정 JSON을 업로드하면 실행). gspread 미설치나 자격증명 누락 시에는 트레이스백
없이 원인과 해결 방법을 바로 안내한다 (`src/sheets_export.py`의 `SheetsExportError`).

**실제 검증 완료(2026-07-01)**: 본인 구글 서비스 계정으로 `--push-sheets`를 실행해 data/voc.csv(44건)를
실제 구글시트에 자동 기입했다 —
[검증용 시트 바로가기](https://docs.google.com/spreadsheets/d/1UCScYu-07BgVmSh9zzOkyQqxn_COF_tsMZuvRFsdLsU).
"VoC 분류" 탭에 44건 분류 결과, "요약" 탭에 유형별 건수와 제품 개선 기획안 우선순위가 정상적으로
채워진 것을 확인했다.

## 9. Output Files

| 파일 | 설명 |
|---|---|
| `voc_classification.csv` | 불만/기능 요청/칭찬/일반 문의 4유형 분류 결과 + topic, urgency, regulation_context, sub_intent 등 |
| `weekly_voc_report.md` | Executive Summary부터 다음 액션까지 11개 섹션으로 구성된 종합 주간 리포트 |
| `product_improvement_plan.md` | 우선순위 상위 2건의 제품 개선 기획안 (문제 정의/근거 VoC/개선 제안/우선순위/MVP 범위) |
| `data_quality_log.md` | 원본 행 수, 날짜 형식 혼용·결측·중복 등 정제 전/후 데이터 품질 비교 |
| `decisions.md` (각 output 폴더 내) | 해당 실행(run)의 파라미터·결과 로그 (`--default-year`, 행 수, 채택된 기획안 등) |
| `output/decisions.md` (공통, 1개) | 분류 기준·혼합 케이스 처리·우선순위 산정식 등 방법론 전체 문서 |
| `sheets_export.tsv` | 구글시트에 바로 붙여넣을 수 있는 탭 구분 내보내기 파일 (자격증명 불필요) |
| `synthetic_data_note.md` (`output/augmented/`만) | synthetic 데이터 생성 원칙과 분류 정확도 검증 결과 |

## 10. Classification Rules

불만/기능 요청/칭찬/일반 문의는 우선순위 **불만 → 기능 요청 → 칭찬 → 일반 문의** 순으로 판단한다.
불만 신호가 있으면 다른 신호가 섞여 있어도 불만이 최우선이며, 나머지 맥락은 `sub_intent`에 남긴다.

| 유형 | 판단 신호 |
|------|-----------|
| 불만 | 장애·오류·불편·마비·반려·안 됩니다·틀린·누락·끊김·제한적 등 명확한 부정 신호 |
| 기능 요청 | 제공해주세요/추가해주세요/지원해주세요 등 명확한 액션 요청 동사(+ 기능·가이드·템플릿 등 대상 명사) |
| 칭찬 | 감사합니다/만족스럽/좋았습니다/친절하게 등 긍정 표현이 중심 |
| 일반 문의 | 위 신호가 없는 정보 확인형 질문 (기본값) |

불만+요청은 `불만(개선요청)`, 문의+요청은 `기능 요청(가이드요청/기능요청)`으로 승격하는 등 혼합 케이스
처리 기준과 urgency/customer_impact 산정식은 `output/decisions.md` 2~4장에 근거와 함께 기록했다.

## 11. Product Priority Scoring

```
priority_score = frequency_score + impact_score + urgency_score + regulation_score - effort_score
```

- **frequency**: 관련 VoC 1건=1점, 2~3건=2점, 4건 이상=3점
- **impact**: OEM/1차 협력사 포함=3점, 2차 협력사 포함=2점, 기타 중심=1점
- **urgency**: High 포함=3점, Medium 포함=2점, Low만 있음=1점
- **regulation**: CBAM/CSRD/Scope3/검증 직접 관련=3점, ESG/PCF/LCA 관련=2점, 일반 플랫폼 기능=1점
- **effort**: 문서/템플릿/FAQ 수준=1점, 화면/리포트 개선=2점, API/복잡한 연동/신규 모듈=3점 (클러스터
  성격에 따라 고정 배정 — 구현 난이도는 데이터로 산출할 수 없기 때문)

6개 클러스터(CBAM 신고, Scope3 자동화, 보고서 커스터마이징, 계산 로직/검증, API 연동, FAQ/온보딩)를 이
기준으로 채점해 상위 2건만 기획안으로 작성한다. 클러스터 정의와 동점 처리 규칙은 `output/decisions.md`
6장 참고.

## 12. Basic/Standard/Challenge 충족 여부

| 요구사항 | 구현 내용 | 산출물 |
|---|---|---|
| 4유형 분류표 + 경계 케이스 처리 (Basic) | 키워드 우선순위 규칙 + 혼합 케이스 sub_intent 태깅 | `src/classify.py`, `voc_classification.csv`, `decisions.md` 2~3장 |
| 건수·비율 집계 (Basic) | 유형/채널/고객군/topic/urgency 등 9종 집계 + 5종 실무 지표 | `src/aggregate.py`, `voc-summary.csv` |
| 탄소규제 인사이트 3개 이상 (Basic) | company-info.md·industry-news.md 인용 template 기반 생성 (5개) | `src/insight.py`, `insight-report.md` |
| 파이프라인 재현성 (Standard) | `--input`/`--output`/`--dataset-label`로 새 CSV 즉시 재실행, 예외 처리 3종 | `src/run_pipeline.py` |
| 주간 리포트 설계 (Standard) | Executive Summary~다음 액션까지 11개 섹션, 5분 내 스캔 가능 | `src/report.py`, `weekly_voc_report.md` |
| 제품 개선 기획안 (Challenge) | 6개 클러스터 우선순위 채점 후 상위 2건 작성 | `src/product_plan.py`, `product_improvement_plan.md` |
| 우선순위 설계 (Challenge) | frequency+impact+urgency+regulation-effort 산식 직접 설계 | `decisions.md` 6장 |
| 구글시트 자동 기입 연동 (Challenge) | 기본 TSV 내보내기(자격증명 불필요) + opt-in gspread 자동 기입 | `src/sheets_export.py`, `sheets_export.tsv`, `decisions.md` 7장 |
| Skill(/명령) 패키징 (Challenge) | `/voc-report`로 정제~기획안까지 전체 파이프라인 재현 | `.claude/commands/voc-report.md` |
| Streamlit 대시보드 (권장) | CarbonLink 스타일 UI + 6개 탭 + CSV 업로드 즉시 분석 | `app.py`, `src/pipeline.py` |

## 13. 한계와 개선 방향

- 현재는 rule-based classification이라 문맥을 완전히 이해하지 못한다. 개발 중에도 "설명해주세요"(정보
  확인)를 기능 요청으로 오인하거나 "오류가 줄었습니다"(칭찬)를 불만으로 잘못 인식하는 사례를 발견해
  가드 로직으로 수정한 바 있다.
- 실제 운영 시에는 CS 담당자의 피드백을 반영해 키워드 사전을 주기적으로 업데이트하는 프로세스가 필요하다.
- LLM API를 연동하면 `classification_reason`과 인사이트 문구의 품질을 한 단계 끌어올릴 수 있다 (현재는
  키워드 매칭 근거만 문장으로 조립).
- 구글시트 연동은 opt-in(사용자 서비스 계정) 방식으로 구현했다(8장). Slack/CRM 연동까지 붙이면 리포트
  생성 후 배포를 완전히 자동화할 수 있다 (현재 범위 밖).
- synthetic 데이터는 파이프라인 검증 목적이며, 실제 비즈니스 판단은 원본 데이터 결과와 구분해서 해석해야
  한다.
