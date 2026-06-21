# KanaMate 주차별 멘토 가이드

멘토의 역할은 수강생이 주차별 과제를 구현해 커밋하면 해당 코드를 검토하고, 필요한 피드백을 제공한 뒤 최종 커밋 컨펌 여부를 판단하는 것입니다.  
리뷰할 때는 단순히 코드가 실행되는지만 보는 것이 아니라 **과제 의도 이해 → 기능 구현 → payload 확인 → trace 검증 → 다음 주차 연결성**까지 함께 확인합니다.

---

## 공통 컨펌 기준

| 기준 | 설명 |
|---|---|
| 동작한다 | 해당 주차에서 요구한 기능이 실제로 실행된다. |
| 설명할 수 있다 | 학생이 입력 → 처리 → 출력 흐름을 설명할 수 있다. |
| 검증했다 | JSON payload, trace, 앱 실행 결과 중 최소 하나 이상으로 결과를 확인했다. |
| 연결된다 | 이번 주차 결과가 다음 주차 또는 최종 시스템 흐름과 연결된다. |

멘토 리뷰의 직접 구현 범위는 각 `student_parts/weekXX_*.py` 파일 최상단 `[수강생 구현 가이드]`가 지정한 함수와 tool입니다. prompt, schema, helper, tool-list, agent builder, compatibility helper, `mcp_server/sqlite_mcp_server.py`의 MCP tool은 주차별 가이드에서 별도 구현 대상으로 지정하지 않는 한 학생이 다시 작성하는 대상이 아니라 연결 구조를 읽는 참고 코드로 봅니다.

현재 기준본은 Week 1~5가 각 주차별 **단일 LangChain agent**로 동작하고, Week 6에서만 supervisor가 Nana/Kana 하위 agent로 위임하는 구조입니다. Week 3 이후 저장 흐름은 SQLite에 바로 쓰기 전에 `StructuredRequest` 형태로 한 번 정리한 뒤 저장하는 것을 기준으로 리뷰합니다.

---

## 1주차: 나나를 깨우다

### 핵심 과제

`personal_create_schedule`, `personal_list_schedules`, `personal_delete_schedule`로 개인 일정을 생성·조회·삭제하는 CRUD Tool을 구현한다.

### 멘토가 꼭 봐야 할 것

| 확인 항목 | 멘토 체크 포인트 |
|---|---|
| 일정 생성 | `title`, `date`, `start_time`, `end_time`, `attendees`가 일정 payload에 제대로 들어가는지 확인한다. |
| 일정 저장 | 생성된 일정이 `PERSONAL_SCHEDULES` 같은 메모리 저장소에 누적되는지 확인한다. |
| 일정 조회 | 전체 조회와 날짜 조건 조회가 구분되어 동작하는지 확인한다. |
| 일정 삭제 | `schedule_id` 기준으로 정확한 일정이 삭제되는지 확인한다. |
| JSON 반환 | 생성은 `created_schedule`, 조회는 `schedules`, 삭제는 `deleted` 필드가 포함되는지 확인한다. |
| trace 확인 | 사용자의 요청에 대해 적절한 Tool이 호출되었는지 확인한다. |

### 자주 발생하는 오류

- 일정 payload는 만들었지만 저장소에 추가하지 않는 경우
- 삭제 함수가 동작해도 실제 목록이 바뀌지 않는 경우
- 반환값이 JSON 문자열 형식이 아니거나 필드가 누락되는 경우
- 새 대화 범위에서도 이전 대화의 임시 일정이 보이는 경우

### 멘토 피드백 방향

- 일정 생성 결과가 화면에는 보이지만 저장소에 남는지 다시 확인하도록 안내한다.
- 삭제 전후 목록을 비교해서 실제로 어떤 일정이 삭제됐는지 검증하도록 안내한다.
- Week 1 일정은 현재 대화 안에서만 유지되는 임시 메모리이며, Week 3 이후의 영구 저장과 다르다는 점을 짚어준다.

### 최종 컨펌 기준

- 일정 생성, 조회, 삭제가 모두 동작한다.
- 삭제 전후 목록 변화를 설명할 수 있다.
- 반환 JSON의 핵심 필드를 확인했다.
- trace에서 Tool 호출 흐름을 확인했다.
- 학습일지에 정상 입력, 실패 입력, 수정 내용이 정리되어 있다.

---

## 2주차: 자연어를 구조화된 요청으로 만든다

### 핵심 과제

Week 2 단일 agent가 tool 호출 없이 자연어 요청을 `StructuredRequest` schema에 맞는 structured output으로 반환하게 한다. `extract_schedule_request`는 Week 3 이후 저장 tool chain에서 재사용되는 helper tool로 본다.

### 멘토가 꼭 봐야 할 것

| 확인 항목 | 멘토 체크 포인트 |
|---|---|
| Schema 정의 | `kind`, `title`, `date`, `start_time`, `end_time`, `members`, `priority`, `reason`, `original_text`가 적절히 정의되어 있는지 확인한다. |
| 요청 분류 | 개인 일정, 그룹 일정, 할 일, 알림, `unknown` 분류가 합리적인지 확인한다. |
| 날짜·시간 처리 | 날짜는 `YYYY-MM-DD`, 시간은 `HH:MM` 형식으로 정리되는지 확인한다. |
| 애매한 요청 처리 | 확실하지 않은 값이 억지로 채워지지 않고 `None` 또는 빈 배열로 처리되는지 확인한다. |
| Pydantic 검증 | LLM 출력이 schema 검증을 통과하는지 확인한다. |
| 단일 agent 실행 | `build_week02_agent()`가 `response_format=StructuredRequest`를 사용하고, Week 2 대화 agent에는 별도 tool이 없는지 확인한다. |
| 3주차 연결성 | 구조화 결과가 Week 3 `save_structured_request` 저장 payload로 활용 가능한지 확인한다. |

### 자주 발생하는 오류

- 모든 요청을 일정으로만 분류하는 경우
- 상대 날짜를 잘못 계산하는 경우
- 멤버 정보를 문자열 하나로 처리하는 경우
- LLM이 생성한 텍스트만 사용하고 schema 검증을 하지 않는 경우
- 애매한 요청을 무리하게 실행 가능한 요청으로 분류하는 경우
- Week 3 이상에서 재사용되는 `extract_schedule_request`가 중첩 Week 2 agent를 새로 띄우도록 구현하는 경우

### 멘토 피드백 방향

- 요청이 일정인지, 할 일인지, 알림인지 먼저 분류 기준을 다시 확인하도록 안내한다.
- 확실하지 않은 필드는 억지로 채우기보다 `None` 처리하는 것이 안전하다고 안내한다.
- 구조화 결과가 `kind`, `title`, `date`, `start_time`, `end_time`, `members`를 갖춘 저장 payload인지 확인하도록 유도한다.
- Week 3 이상에서 쓰는 `extract_structured_request()`는 agent가 아니라 `chat_model().with_structured_output(...)` 직접 호출 경로라는 점을 짚어준다.

### 최종 컨펌 기준

- 자연어 요청이 적절한 `kind`로 분류된다.
- 날짜, 시간, 제목, 멤버, 우선순위가 schema에 맞게 추출된다.
- 애매한 요청을 안전하게 처리한다.
- structured output이 Pydantic 모델 검증을 통과한다.
- 여러 예시 입력에 대한 결과 비교가 학습일지에 정리되어 있다.

---

## 3주차: 나나의 기록장을 만들다

### 핵심 과제

`save_structured_request`, `list_saved_requests`, `get_saved_request`, `personal_list_saved_schedules`, `personal_update_saved_schedule`, `personal_delete_saved_schedules`로 구조화된 요청을 SQLite에 저장하고, 저장된 요청과 일정을 조회·수정·삭제한다.

### 멘토가 꼭 봐야 할 것

| 확인 항목 | 멘토 체크 포인트 |
|---|---|
| 요청 저장 | structured payload가 SQLite에 저장되는지 확인한다. |
| 저장 전 구조화 | raw 자연어, `extract_schedule_request` 전체 payload, 이미 정리된 dict가 모두 `StructuredRequest` 기준 payload로 정리된 뒤 저장되는지 확인한다. |
| Request Log | 원본 요청, 요청 종류, 실행 상태, 저장 데이터가 추적 가능한지 확인한다. |
| 저장 위치 분리 | `kind`에 따라 일정, 할 일, 알림 데이터가 적절히 나뉘어 저장되는지 확인한다. |
| 조건 조회 | `kind`, 날짜 범위, request id 기준으로 조회가 가능한지 확인한다. |
| 일정 삭제 | 일정 ID, 날짜, 제목, 시간 조건으로 삭제 대상이 정확히 선택되는지 확인한다. |
| DB 검증 | DB row와 Tool 반환 결과가 일치하는지 확인한다. |

`save_structured_request`는 저장 전 `normalize_structured_request_payload()`를 거쳐야 합니다. 멘토는 SQLite에 들어간 `raw_json`이 `extract_schedule_request`의 outer payload가 아니라 내부 `structured_request` 기준으로 저장되는지 확인합니다.

### 자주 발생하는 오류

- 요청은 저장되지만 실제 일정 데이터와 연결되지 않는 경우
- 저장 전 구조화를 생략해 `ok`, `tool_name`, `structured_request` 같은 wrapper 필드가 SQLite 원본 row로 들어가는 경우
- 자연어 문자열을 그대로 SQLite에 넣으려다 schema 검증 없이 저장하는 경우
- 모든 요청을 하나의 테이블에만 저장하는 경우
- 필터 조회가 전체 조회처럼 동작하는 경우
- 삭제 조건이 너무 넓어 여러 일정이 한꺼번에 삭제되는 경우
- 삭제 결과 payload에 `deleted_count`, `filters`, `deleted` 정보가 부족한 경우

### 멘토 피드백 방향

- 요청 기록과 실제 저장 데이터가 어떤 ID로 연결되는지 확인하도록 안내한다.
- 저장 도구가 입력을 바로 DB에 넣는 것이 아니라 `StructuredRequest.model_validate(...)` 가능한 형태로 정리한 뒤 저장해야 함을 안내한다.
- `kind`별로 저장 위치가 달라져야 하는 이유를 코드에서 확인하게 한다.
- 삭제 전에는 삭제 후보를 확인하고, 삭제 후에는 row 변화를 비교하도록 안내한다.

### 최종 컨펌 기준

- structured request가 SQLite에 저장된다.
- 저장 직전 payload가 `StructuredRequest` 기준으로 정리되고 검증된다.
- 저장된 요청을 조건별로 조회할 수 있다.
- request id로 단건 조회가 가능하다.
- 저장된 일정 삭제가 정확히 동작한다.
- DB row와 반환 payload가 일치한다.
- 학습일지에 저장 row 예시와 삭제 전후 비교가 포함되어 있다.

---

## 4주차: 나나가 기억을 찾아오다

### 핵심 과제

`add_personal_reference`, `search_personal_references`, `search_saved_requests`, `search_conversation_messages`로 개인 참고자료, 저장된 요청, 앱 채팅 메시지를 구분 검색해 RAG 근거 payload를 만든다.

### 멘토가 꼭 봐야 할 것

| 확인 항목 | 멘토 체크 포인트 |
|---|---|
| 참고자료 저장 | 제목, 내용, 태그가 포함된 개인 참고자료가 저장되는지 확인한다. |
| 참고자료 검색 | 질문과 관련 있는 reference hit가 반환되는지 확인한다. |
| 저장 요청 검색 | SQLite에 저장된 요청 또는 일정이 검색 가능한지 확인한다. |
| 대화 메시지 검색 | 일반 채팅 발화 검색은 `search_conversation_messages`의 top-level `rows`를 사용하는지 확인한다. |
| 검색 결과 구분 | ChromaDB reference hit와 SQLite saved request hit의 차이를 이해했는지 확인한다. |
| Payload 계약 | `search_personal_references`는 top-level `hits`, `search_saved_requests`와 `search_conversation_messages`는 top-level `rows`를 반환하는지 확인한다. |
| 검색 실험 | 검색어, limit, 조건을 바꿨을 때 결과가 달라지는지 확인한다. |

`search_nana_memory`는 compatibility helper로 남겨 두는 통합 검색이며, 핵심 TODO 구현 대상은 아니다. 일반 채팅 발화 검색은 저장 요청 검색과 구분해 `search_conversation_messages`를 사용해야 한다.

### 자주 발생하는 오류

- 참고자료만 검색되고 저장 일정 검색이 빠지는 경우
- 일반 채팅 발화를 `search_saved_requests`로 찾으려는 경우
- 검색 결과는 있지만 context에 반영되지 않는 경우
- 출처 정보나 title이 빠져 답변 근거로 쓰기 어려운 경우
- 검색 결과가 없을 때 빈 응답을 제대로 처리하지 못하는 경우
- 참고자료 검색과 일정 검색을 구분하지 못하는 경우

### 멘토 피드백 방향

- 검색 결과가 실제 답변 context에 포함되는지 확인하도록 안내한다.
- reference hit와 saved request hit는 출처가 다르므로 구분해서 정리하도록 안내한다.
- course repo 기준 RAG tool은 `search_personal_references`, `search_saved_requests`라는 점을 안내한다.
- 검색 결과가 없거나 관련도가 낮을 때의 응답도 고려하도록 피드백한다.

### 최종 컨펌 기준

- 개인 참고자료를 저장하고 검색할 수 있다.
- SQLite에 저장된 요청 또는 일정도 검색할 수 있다.
- `hits`와 `rows` payload가 답변 근거로 사용된다.
- 저장 요청 검색과 일반 채팅 메시지 검색의 출처 차이를 설명할 수 있다.
- 검색 결과에 출처 또는 근거가 포함된다.
- 검색 조건 변경 실험을 수행했다.
- 학습일지에 검색 실패 사례와 개선 방향이 정리되어 있다.

---

## 5주차: 카나가 지난대화를 불러오다

### 핵심 과제

`search_previous_conversations`, `load_conversation_messages`, `extract_schedules_from_history`, `create_shared_schedule`, `delete_shared_schedule`, `list_shared_schedules`, `collect_member_schedules`로 외부 대화 기록과 공유 일정 저장소를 MCP wrapper tool로 다룬다.

### 멘토가 꼭 봐야 할 것

| 확인 항목 | 멘토 체크 포인트 |
|---|---|
| 외부 대화 검색 | 검색어, 멤버 이름, limit 조건으로 이전 대화가 검색되는지 확인한다. |
| Tool interface | 외부 DB를 직접 수정하거나 직접 조회하지 않고 Tool interface로 접근하는지 확인한다. |
| 메시지 로드 | conversation id 기준으로 메시지가 시간순으로 로드되는지 확인한다. |
| 일정 추출 | 날짜, 시간, 멤버, 가능 여부 표현이 추출되는지 확인한다. |
| 멤버 alias | A/B/C 같은 alias가 실제 멤버 이름으로 변환되는지 확인한다. |
| 일정 통합 | 내 일정과 외부 멤버 일정이 함께 정리되는지 확인한다. |
| 공유 일정 저장소 | `create_shared_schedule`, `delete_shared_schedule`, `list_shared_schedules`가 MCP tool interface로 동작하는지 확인한다. |
| trace 확인 | 대화 검색, 메시지 로드, 일정 추출 Tool 호출 순서가 trace에 남는지 확인한다. |

`mcp_server/sqlite_mcp_server.py`의 `@mcp.tool` 구현은 학생 구현 대상이 아니며, Week 5 wrapper tool이 호출하는 기준 구현으로 유지한다.
Week 5 agent는 Week 1~5 누적 tool을 한 agent에 공개하는 단일 agent입니다. 외부 SQLite에 직접 SQL을 날리지 않고 `call_mcp_tool_sync(...)` 또는 `call_external_tool_payload(...)` wrapper 경로를 쓰는지 확인합니다.

### 자주 발생하는 오류

- 외부 DB를 Tool이 아니라 직접 조회하도록 구현하는 경우
- conversation id 없이 메시지 로드를 시도하는 경우
- 검색된 대화와 일정 후보 추출 결과가 연결되지 않는 경우
- 멤버별 일정은 추출했지만 내 개인 일정과 합치지 않는 경우
- 공유 일정 저장소 row를 확인해야 하는 상황에서 `list_shared_schedules`를 누락하는 경우
- 날짜 범위 조건이 일정 추출에 반영되지 않는 경우

### 멘토 피드백 방향

- 외부 데이터는 직접 건드리지 않고 Tool interface로 조회해야 한다고 안내한다.
- 검색 결과의 conversation id가 다음 메시지 로드 단계로 전달되는지 확인하도록 유도한다.
- 그룹 일정 조율을 위해서는 외부 멤버 일정뿐 아니라 내 일정도 함께 모아야 함을 짚어준다.

### 최종 컨펌 기준

- 외부 대화 검색이 동작한다.
- conversation id로 메시지를 불러올 수 있다.
- 메시지에서 날짜, 시간, 참석자, 가능 여부를 추출할 수 있다.
- 멤버별 일정 정보가 정리된다.
- 내 일정과 외부 멤버 일정이 함께 rows 형태로 수집된다.
- 공유 일정 생성, 삭제, 조회 wrapper가 MCP tool 결과를 그대로 보존한다.
- trace에서 MCP/외부 Tool 호출 흐름을 확인할 수 있다.

---

## 6주차: 카나메이트가 약속을 결정하다

### 핵심 과제

`find_common_available_slots`, `decide_final_slot`, `nana_agent`, `kana_agent`를 구현해 supervisor가 요청에 맞는 agent로 위임하고 최종 일정 후보를 결정하도록 한다.

### 멘토가 꼭 봐야 할 것

| 확인 항목 | 멘토 체크 포인트 |
|---|---|
| 역할 분리 | Nana는 개인 일정/RAG, Kana는 그룹 일정 조율을 담당하는지 확인한다. |
| Tool 노출 | Nana는 Week 4 개인 도구, Kana는 `kana_tools()`, supervisor는 `supervisor_tools()`의 위임 도구만 볼 수 있는지 확인한다. |
| Routing | 개인 요청은 Nana, 그룹 일정 요청은 Kana로 위임되는지 확인한다. |
| 일정 수집 | 그룹 요청에서 멤버 일정 수집이 먼저 이루어지는지 확인한다. |
| 후보 비교 | busy-time rows를 바탕으로 가능한 시간을 판단하는지 확인한다. |
| 후보 검증 | `find_common_available_slots`가 Kana agent가 고른 `candidate_slots`를 검증하고 근거 rows를 보존하는지 확인한다. |
| 최종 제안 | `decide_final_slot`이 `final_slot`, 이유, 후보 목록을 payload로 반환하는지 확인한다. |
| trace 검증 | supervisor trace와 sub-agent trace에서 호출 흐름을 확인한다. |
| 최종 시나리오 확인 | 앱 실행과 trace로 최종 scenario 흐름이 깨지지 않았는지 확인한다. |

`propose_group_schedule`은 compatibility helper로 남겨 기능을 유지하지만 핵심 TODO 구현 대상은 아니다. `week06_system_prompt()`는 supervisor prompt이며, Nana/Kana sub-agent는 각각 `nana_system_prompt()`, `kana_system_prompt()`를 사용한다.

### 자주 발생하는 오류

- supervisor가 Nana/Kana에게 위임하지 않고 직접 모든 Tool을 호출하는 경우
- Nana와 Kana의 Tool 목록이 섞이는 경우
- supervisor prompt를 sub-agent가 그대로 공유한다고 가정해 역할별 지시가 충돌하는 경우
- 그룹 일정 요청인데 개인 일정 Tool만 호출되는 경우
- `find_common_available_slots` 없이 바로 임의의 시간을 제안하는 경우
- 최종 제안에 `final_slot`, `reason`, `candidates`가 없거나 근거가 부족한 경우
- trace에서 어떤 agent가 선택되었는지 확인할 수 없는 경우

### 멘토 피드백 방향

- supervisor는 직접 모든 일을 처리하는 역할이 아니라 적절한 agent에게 위임하는 역할임을 안내한다.
- Nana와 Kana의 책임을 다시 나누고, 각 agent가 사용할 Tool 목록을 점검하도록 유도한다.
- supervisor prompt와 sub-agent 전용 prompt가 분리되어 있음을 확인하도록 안내한다.
- 최종 일정 제안은 후보 비교와 근거가 있어야 하며, 왜 그 시간이 선택됐는지 payload에 남겨야 한다고 안내한다.

### 최종 컨펌 기준

- Nana/Kana 역할이 명확히 분리되어 있다.
- supervisor가 요청 유형에 따라 적절한 agent를 선택한다.
- 그룹 일정 요청에서 멤버 일정 수집 → 후보 비교 → 최종 제안 흐름이 이어진다.
- `find_common_available_slots`와 `decide_final_slot`이 busy rows와 candidate payload를 근거로 이어진다.
- 최종 payload에 `final_slot`, `reason`, `candidates`가 포함된다.
- trace에서 agent와 Tool 호출 흐름을 확인할 수 있다.
- 앱 실행과 상세 trace로 최종 통합 흐름을 확인했다.
- 학습일지에 전체 프로젝트 오류 유형과 개선점이 정리되어 있다.

---

## 멘토 리뷰 코멘트 템플릿

### 컨펌할 때

```text
[컨펌]
이번 주차 핵심 요구사항을 충족했습니다.

확인한 내용:
- 핵심 TODO 구현 완료
- 주요 입력 예시에 대한 payload 확인 완료
- trace에서 기대 Tool/Agent 호출 확인
- 앱 실행 또는 수동 검증 결과 확인
- 학습일지에 구현 과정과 오류 수정 내용 정리

최종 커밋 컨펌합니다.
```

### 수정 요청할 때

```text
[수정 요청]
전체 방향은 맞지만 아래 항목 수정이 필요합니다.

수정 필요:
1. [파일/함수명]에서 [문제 내용]
2. [payload 필드명]이 누락되었거나 기대 구조와 다릅니다.
3. [테스트 입력]에서 기대 결과와 다른 결과가 나옵니다.

확인할 것:
- 반환 JSON을 열어 핵심 필드를 확인해 주세요.
- trace에서 실제 선택된 Tool/Agent를 확인해 주세요.
- 수정 후 같은 입력으로 다시 실행하고 결과를 학습일지에 추가해 주세요.
```

### 설명 보완이 필요할 때

```text
[보완 피드백]
구현 방향은 맞습니다. 다만 이번 주차의 핵심 데이터 흐름을 더 명확히 정리할 필요가 있습니다.

보완할 내용:
- 이 Tool이 어떤 입력을 받아 어떤 payload를 반환하는지 설명해 주세요.
- 다음 주차 기능과 연결되는 필드가 무엇인지 정리해 주세요.
- 실패한 입력 사례 1개와 그 원인을 학습일지에 추가해 주세요.
```

---

## 주차별 연결 포인트

| 연결 구간 | 멘토가 확인할 점 |
|---|---|
| 1주차 → 2주차 | Week 1 일정 필드(title/date/time/attendees)가 Week 2 구조화 schema의 어떤 필드와 대응되는가? |
| 2주차 → 3주차 | `StructuredRequest` 결과가 저장 전 정규화 payload로 쓰이고, `save_structured_request`가 SQLite 저장 전에 이를 검증하는가? |
| 3주차 → 4주차 | 저장된 요청과 일정이 검색 가능한 형태로 남는가? |
| 4주차 → 5주차 | 개인 참고자료 검색과 외부 대화 검색의 데이터 출처 차이를 이해했는가? |
| 5주차 → 6주차 | 멤버별 일정 rows가 그룹 일정 결정 입력으로 충분한가? |
| 6주차 최종 | supervisor, Nana, Kana의 역할이 trace로 설명 가능한가? |

---

# Agent 구현 원칙

1. 첫째, Agent는 답변하는 챗봇도 명령을 그대로 실행하는 스크립트도 아니라, 요청의 의도를 먼저 분류·해석하고 필요한 정보를 구조화한 뒤 적절한 Tool이나 하위 역할에 위임하는 "의사결정 흐름"으로 구현되어야 한다. 이는 단순히 LLM에 도구 몇 개를 붙이는 것이 아니라 자율성·기억·도구 사용이라는 세 축 위에서 사용자가 신뢰하고 실제 작업을 맡길 수 있는 구조를 만드는 것이며, 2025년의 효과적인 AI 에이전트는 자율성, 기억, 도구 사용이라는 세 가지 핵심 역량을 갖추고 사용자가 신뢰하고 실제 작업을 완수할 수 있도록 설계되어야 한다는 현재의 설계 합의와 일치합니다.

2. 둘째, Agent는 불확실한 값을 억지로 추측해 실행하지 않고, 내부 추측 대신 개인 기억·저장된 기록·외부 대화 같은 실제 데이터 출처에 근거(grounding)를 두며, 정보가 부족하면 "확인 필요" 상태로 남기거나 사용자에게 되묻는 방식으로 동작해야 한다. 맥락 전파를 통해 풍부한 도구 사용과 근거 확보가 가능해지고, 가드레일과 평가 파이프라인이 처음 설계 단계부터 내장되어야 신뢰할 수 있는 실행이 보장된다는 점에서 이 원칙은 현 시대 에이전트 설계의 핵심으로 자리 잡고 있습니다.

3. 셋째, 단일 Agent로 시작하되 복잡도가 임계점을 넘으면 supervisor가 요청 성격을 판단해 전문화된 하위 Agent에게 위임하는 역할 분리 구조로 확장하고, 각 단계의 근거와 선택 이유를 trace로 남겨 검증 가능하게 만들어야 한다. 현재 업계의 핵심 경쟁 지점은 가장 똑똑한 단일 에이전트가 아니라 효율적이고 안전하며 확장 가능하게 협업하는 전문화된 에이전트 네트워크를 오케스트레이션하는 능력으로 이동했으며, 실제로 권장되는 접근은 ReAct와 적절한 도구를 갖춘 단일 에이전트로 시작해 명확한 병목이 드러날 때만 멀티 에이전트 구조로 이동하는 것입니다.
