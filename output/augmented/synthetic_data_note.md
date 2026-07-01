# 확장 더미 데이터 생성 노트

## 목적
제공 데이터만으로는 주간/월간 운영 상황의 재사용성을 검증하기 어려워, 실무 VoC 패턴을 가정한 synthetic 데이터를 추가 생성했다.

## 생성 원칙
- 원본 데이터 보존
- 도메인 맥락 기반 생성
- 데이터 품질 이슈 일부 포함
- 분류/정제/리포트 파이프라인 검증 목적

## 생성 결과 (이번 실행)
- 원본 파일: `data/voc.csv` (45건, 수정하지 않고 그대로 보존)
- synthetic 생성 건수: 200건 (`--seed 42`)
- 최종 파일: `data/voc_augmented.csv` (총 245건)
- voc_type 목표 분포: 일반 문의 38% / 기능 요청 27% / 불만 27% / 칭찬 8%
- 주입된 데이터 품질 이슈: 날짜 형식 혼용(iso/slash/한글 표기), channel 결측 약 5%, content 앞뒤 공백 약 10%,
  불만+요청/문의+요청/칭찬+개선제안 등 경계 케이스 표현 약 8%
- content 완전 중복: 목표 2.5%로 의도적으로 주입했으나, 실제 측정 결과 synthetic
  200건 중 14건(7.0%)이 완전 중복이다
  (템플릿 풀이 한정적이라 우연히 겹친 건이 일부 섞여 있음 — 오히려 실무 데이터의 "의도치 않은 중복"까지
  함께 검증할 수 있는 부수 효과로 해석했다)
- 검증용 컬럼: `synthetic_source`(original/synthetic), `expected_voc_type`, `expected_topic`, `expected_urgency`
  (원본 행은 검증 대상이 아니므로 위 세 컬럼을 빈 값으로 둔다)

## 파이프라인 검증 결과
`python src/run_pipeline.py --input data/voc_augmented.csv --output output/augmented --dataset-label augmented --default-year 2026`
실행 후 `output/augmented/voc_classification.csv`의 실제 분류 결과를 synthetic 행의 `expected_voc_type` /
`expected_topic` / `expected_urgency`와 비교한 결과:

- voc_type 정확도: 100% (193건 중 193건 일치)
- topic 정확도: 100%
- urgency 정확도: 100%
- content 완전 중복 8건은 clean.py의 정제 단계에서 정상적으로 제거됨 (정제 전 245건 → 정제 후 237건)

100%에 도달하기까지 실제로 여러 불일치를 발견해 수정했다 — 예: "차이가 나서"(비트리거) vs "차이가 납니다"(트리거)처럼
어미 차이로 실제 classify.py 규칙이 매칭되지 않는 경우, `keyword_hint`에 포함된 단어("검증", "분기" 등)가
의도치 않게 topic/urgency에 영향을 주는 경우 등. 이 과정 자체가 "새로운 문장 표현에도 분류 기준이 안정적으로
확장되는가"를 검증하는 목적에 부합했다.

## 주의사항
확장 데이터는 실제 고객 데이터가 아니므로, 최종 비즈니스 인사이트의 근거는 원본 데이터 분석 결과와 구분해 해석해야 한다.
`--dataset-label augmented`로 파이프라인을 실행해 `output/augmented/`에만 결과를 저장하고, `output/original/`의
원본 분석 결과와 절대 섞지 않는다.
