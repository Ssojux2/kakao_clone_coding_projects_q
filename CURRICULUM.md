# Kanana 주차별 커리큘럼

이 문서는 Kanana Schedule Agent 수업에서 다루는 Week별 미션을 정리한 운영안입니다. 학생 직접 구현 범위는 각 `student_parts/weekXX_*.py` 파일 최상단의 `[수강생 구현 가이드]`가 지정한 함수와 tool 본문입니다.

## 운영 기준

- 수업은 앱 실행, 채팅 입력, 상세 trace 확인, 함수 구현, 재실행 순서로 진행합니다.
- 초기 배포 상태의 구현 대상 함수는 `student_todo: true` JSON을 반환합니다.
- 학생은 `received` 입력값과 기대 payload 키를 trace에서 확인한 뒤 실제 구현으로 바꿉니다.
- prompt, schema, tool-list, agent builder, MCP server 기준 구현은 연결 구조를 읽는 참고 코드입니다.

## Week 1 · 개인 일정 CRUD tool

파일: `student_parts/week01_wake_up_nana.py`

미션은 `personal_create_schedule`, `personal_list_schedules`, `personal_delete_schedule`을 구현하는 것입니다. 현재 대화 범위의 임시 메모리인 `PERSONAL_SCHEDULES`를 사용하고, tool 결과는 JSON 문자열로 반환합니다.

확인 포인트는 상세 trace에서 세 tool 중 어떤 tool이 호출됐는지, `created_schedule`, `schedules`, `deleted` payload가 기대한 모양으로 바뀌었는지 보는 것입니다.

## Week 2 · 자연어 요청 구조화

파일: `student_parts/week02_structure_natural_language_requests.py`

미션은 한국어 자연어 요청을 `StructuredRequest` schema로 변환하는 것입니다. `extract_structured_request`는 nested agent를 만들지 않고 structured output 경로를 사용하고, `extract_schedule_request`는 이후 주차에서 재사용할 JSON tool payload를 만듭니다.

확인 포인트는 `kind`, `title`, `date`, `start_time`, `members`, `original_text`가 원문 의도를 보존하는지입니다.

## Week 3 · SQLite 기록장

파일: `student_parts/week03_build_nanas_logbook.py`

미션은 Week 2의 구조화 결과를 SQLite에 저장하고, 저장된 요청과 일정을 조회/수정/삭제하는 것입니다. `@tool(args_schema=...)`가 입력 검증을 담당하므로 tool 본문은 검증된 인자를 저장소 호출용 dict로 정리하는 데 집중합니다.

확인 포인트는 저장 요청에서 `extract_schedule_request` 이후 `save_structured_request`가 호출되는지, 조회/수정/삭제 요청에서 먼저 후보 row를 확인한 뒤 ID나 필터를 사용하는지입니다.

## Week 4 · Nana memory와 RAG

파일: `student_parts/week04_retrieve_nanas_memory.py`

미션은 개인 참고자료, SQLite 저장 요청, 앱 대화 발화 검색을 다른 tool로 분리하는 것입니다. `add_personal_reference`, `search_personal_references`, `search_saved_requests`, `search_conversation_messages`가 핵심 구현 대상입니다.

확인 포인트는 질문 성격에 따라 `hits` 또는 `rows` payload가 맞는 출처에서 만들어지는지, 일반 대화 검색이 현재 대화를 과거 검색처럼 섞지 않는지입니다.

## Week 5 · 외부 대화와 MCP wrapper

파일: `student_parts/week05_load_kanas_past_conversations.py`

미션은 외부 SQLite/MCP tool을 LangChain agent가 사용할 수 있게 wrapper로 감싸는 것입니다. 직접 SQL을 다시 작성하지 않고 `call_mcp_tool_sync(...)` 또는 `call_external_tool_payload(...)` 결과를 agent용 JSON으로 전달합니다.

확인 포인트는 외부 대화 검색, 메시지 로드, 일정 추출, 공유 일정 조회/생성/삭제, 멤버 일정 수집 결과가 모두 trace에 남는지입니다.

## Week 6 · Supervisor와 하위 agent

파일: `student_parts/week06_kanamate_decides_schedule.py`

미션은 supervisor가 개인 업무는 `nana_agent`, 외부 멤버 일정 조율은 `kana_agent`로 위임하게 만드는 것입니다. `find_common_available_slots`와 `decide_final_slot`은 Kana agent가 고른 후보와 최종 선택을 course payload로 기록합니다.

확인 포인트는 supervisor trace에서 선택된 하위 agent가 보이는지, Kana 흐름에서 후보 검증과 최종 선택 payload가 이어지는지입니다.

## 진행 템플릿

1. 이번 주차 파일의 `[수강생 구현 가이드]`를 읽습니다.
2. 앱을 해당 주차로 실행합니다.
3. 샘플 프롬프트를 입력하고 상세 trace의 `student_todo` payload를 봅니다.
4. 구현 대상 함수 본문만 수정합니다.
5. 다시 실행해 trace payload가 실제 결과로 바뀌었는지 확인합니다.

## 멘토 확인 기준

- 구현 대상 함수가 가이드의 책임 범위 안에서 완성됐는지 확인합니다.
- tool 결과 JSON이 prompt와 다음 주차에서 기대하는 top-level 키를 유지하는지 확인합니다.
- trace에서 LLM이 고른 tool과 tool result가 설명 가능한지 확인합니다.
- 학생이 직접 실행한 프롬프트와 관찰한 trace를 바탕으로 구현 과정을 설명할 수 있는지 확인합니다.
