---
description: Generate CarbonLink weekly VoC report and product improvement plan
argument-hint: [csv_path] [output_dir] [dataset_label]
---

아래 작업을 순서대로 수행해라.

1. 입력 CSV 경로를 확인한다.
   - `$ARGUMENTS`의 첫 번째 값을 사용한다.
   - 기본값: `data/voc.csv`
2. output 경로를 확인한다.
   - `$ARGUMENTS`의 두 번째 값을 사용한다.
   - 기본값: `output/original`
3. dataset_label을 확인한다.
   - `$ARGUMENTS`의 세 번째 값을 사용한다 (`original` 또는 `augmented`).
   - 기본값: `original`
4. Python 파이프라인을 실행한다.
   - `python src/run_pipeline.py --input [csv_path] --output [output_dir] --dataset-label [dataset_label] --default-year 2026`
   - 구글시트 자동 기입까지 원하면(선택, 서비스 계정 필요) `--push-sheets --sheet-id [spreadsheet_id] --sheets-credentials [json_path]`를 추가한다.
5. 생성된 파일을 확인한다 (`[output_dir]` 하위).
   - `voc_classification.csv`
   - `weekly_voc_report.md`
   - `product_improvement_plan.md`
   - `data_quality_log.md`
   - `decisions.md`
   - `sheets_export.tsv` (구글시트에 바로 붙여넣기용, 자격증명 없이도 항상 생성됨)
6. `weekly_voc_report.md`와 `product_improvement_plan.md`의 내용을 요약해 사용자에게 알려준다.
   - 유형별 건수·비율, High urgency 건수, 제품팀 전달 필요 건수
   - 핵심 인사이트 3개 이상
   - 제품 개선 기획안 제목과 우선순위 점수
7. 오류 발생 시 어느 단계(1~6)에서 실패했는지 설명하고 수정안을 제안한다.
   - 입력 CSV가 없으면: 경로를 다시 확인하거나 `data/voc.csv`를 사용하도록 안내
   - 필수 컬럼(`id,date,channel,customer_type,content,keyword_hint`)이 누락되면: 어떤 컬럼이 없는지 알려주고 CSV 수정을 요청
   - `[output_dir]`을 이전에 다른 `dataset_label`로 이미 사용한 경우(원본/증강 혼재 방지 에러): 다른 `output_dir`을 쓰도록 안내

## 사용 예시

```
/voc-report data/voc.csv output/original original
/voc-report data/voc_augmented.csv output/augmented augmented
```

인자를 생략하면 기본값(`data/voc.csv`, `output/original`, `original`)으로 실행된다:

```
/voc-report
```

## 주의

- **원본(original)과 증강(augmented) 결과가 섞이지 않도록 경로를 명확히 안내한다.** 항상 서로 다른
  `output_dir`을 사용해야 하며(예: `output/original` vs `output/augmented`), 같은 폴더를 다른
  `dataset_label`로 재실행하면 파이프라인이 에러를 낸다 — 이는 의도된 안전장치이므로 에러 메시지를
  그대로 사용자에게 전달하고 다른 `output_dir`을 제안한다.
- `output/decisions.md`(분류·우선순위 산정 기준 방법론 문서)는 매 실행마다 덮어쓰지 않는다.
  실행별 요약은 `[output_dir]/decisions.md`에만 기록된다.
