# 데이터 품질 점검 로그

> 대상 파일: `data/voc.csv` | 점검 일시: 파이프라인 실행 시점 자동 생성

## 1. 요약

- 총 행 수 (정제 전): 45
- 총 행 수 (정제 후): 44
- 총 컬럼 수: 6 (`id, date, channel, customer_type, content, keyword_hint`)
- 분석 기간 (정제 후 date_clean 기준): 2026-05-02 ~ 2026-06-14
- 중복 제거 전/후 행 수: 45건 → 44건 (1건 제거)

## 2. 발견된 이슈

| 이슈 | 건수 | 처리 방식 |
|---|---:|---|
| 필수 컬럼 누락 | 0 | 없음 |
| 날짜 형식 혼용 (slash/korean) | 16 | 정규식 기반 형식 판별 후 date_clean 컬럼에 YYYY-MM-DD로 통일 |
| channel 결측 | 2 | '미기재'로 채움 (해당 id: 032, 035) |
| customer_type 결측 | 0 | '기타'로 채움 (해당 id: 없음) |
| content 결측 | 0 | 없음 |
| keyword_hint 결측 | 0 | 없음 |
| id 중복 | 0 | 없음 |
| 날짜 파싱 실패 | 0 | 없음 |
| content 완전 중복 | 1 | 첫 번째 행(kept_id)만 유지, 나머지 제거 |

## 3. 상세 내역

- **날짜 형식 혼용**:
  - iso: 29건
  - korean: 6건
  - slash: 10건
  - 처리: 연도 표기가 없는 `M월 D일` 형식은 기본 연도(2026)를 적용해 `date_clean`에 정규화했다.

- **채널 결측**: 2건 (id: 032, 035)
  - 처리: 임의 채널로 추정하지 않고 '미기재'로 명시적으로 표시했다.

- **중복 행**:
  - id 031 제거 (id 001과 content 완전 일치)

- **기타**:
  - 필수 컬럼(`id, date, channel, customer_type, content, keyword_hint`) 누락: 없음
  - customer_type 결측 0건 (id: 없음) → '기타'로 채움
  - content 결측: 없음
  - keyword_hint 결측: 없음
  - id 중복: 없음

- **data_quality_flags 발생 건수**:
  - duplicate_content_removed: 1건
  - channel_missing: 2건

- **customer_type 값 분포 (정제 전)**:
  - 1차 협력사: 11건
  - 기타: 23건
  - 2차 협력사: 5건
  - OEM: 6건

## 4. 실무 적용 시 권장사항

- CS 담당자가 CSV 업로드 전 확인해야 할 항목:
  - `date` 컬럼은 가능하면 `YYYY-MM-DD` 단일 형식으로 입력 (연도 누락 표기 금지)
  - `channel`, `customer_type`은 필수 입력 항목으로 지정 (빈 값 제출 방지)
  - 동일 문의를 여러 채널로 재접수한 경우 원본 접수 id를 함께 기재하면 중복 판정 정확도가 올라감

- 다음 버전에서 자동 검증하면 좋은 항목:
  - CSV 업로드 시점에 날짜 형식·필수 컬럼을 즉시 검증하고 오류 행을 즉시 반려하는 업로드 단계 검증기
  - `data_quality_flags`가 2개 이상 붙은 행을 CS 대시보드에서 우선 검수 대상으로 자동 표시
  - content 완전 일치가 아닌 유사도 기반 중복 탐지(예: 90% 이상 유사) 도입 검토
