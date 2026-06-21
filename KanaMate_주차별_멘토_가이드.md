# KanaMate Week 1 멘토 가이드

이 문서는 Kanana Schedule Agent Week 1 main 브랜치 기준 멘토 가이드입니다. Week 1-6 전체 멘토 가이드는 `week_1_to_6f` 브랜치에 보존되어 있습니다.

## 수업 목표

Week 1의 목표는 LangChain tool의 입출력 구조를 이해하고, 현재 대화 안에서만 유지되는 임시 개인 일정 CRUD를 직접 구현하는 것입니다.

학생 구현 파일은 `student_parts/week01_wake_up_nana.py` 하나입니다.

## 구현 대상

- `personal_create_schedule`
- `personal_list_schedules`
- `personal_delete_schedule`

세 tool은 모두 JSON 문자열을 반환해야 합니다. 학생이 trace에서 결과를 읽을 수 있도록 top-level key를 안정적으로 유지하는 것이 중요합니다.

## 멘토 진행 흐름

1. `README.md`와 `PROJECT_OVERVIEW.md`를 보고 실행 흐름을 확인합니다.
2. `./run.sh --install` 또는 `./run.sh`로 Week 1 앱을 실행합니다.
3. 학생에게 일정 생성, 조회, 삭제 프롬프트를 입력하게 합니다.
4. 상세 trace에서 호출된 tool 이름과 입력 payload를 함께 확인합니다.
5. `student_parts/week01_wake_up_nana.py`의 TODO 영역을 구현합니다.
6. 같은 프롬프트를 다시 실행해 결과 JSON이 바뀌었는지 확인합니다.

## 확인 포인트

| 항목 | 기대 |
| --- | --- |
| 생성 | `created_schedule`에 제목, 날짜, 시간, 참석자, ID가 담깁니다. |
| 조회 | `schedules`가 현재 대화에서 생성한 일정 목록을 반환합니다. |
| 삭제 | `deleted`가 실제 삭제 여부를 나타내고, 삭제 후 조회 결과가 갱신됩니다. |
| 오류 처리 | 없는 ID 삭제처럼 실패 가능한 요청도 JSON으로 설명합니다. |

## 흔한 피드백

- tool이 Python dict를 그대로 반환하지 않고 JSON 문자열을 반환하는지 확인합니다.
- 같은 대화 안에서 생성한 일정이 조회와 삭제에 이어지는지 확인합니다.
- 입력값을 무시하고 고정 응답을 반환하지 않는지 trace로 확인합니다.
- 구현 대상 밖의 `fixed/` 코드는 먼저 수정하지 않도록 안내합니다.
