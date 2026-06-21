# Kanana 프로젝트 구조 안내

이 문서는 학생들이 프로젝트를 처음 열었을 때 전체 흐름을 빠르게 파악하기 위한 지도입니다. 실행 방법은 [README.md](README.md)를 기준으로 보고, 이 문서는 "어느 파일이 어떤 역할을 하는지"를 이해하는 데 집중합니다.

## 30초 요약

| 경로 | 역할 |
| --- | --- |
| `app.py` | Gradio 채팅 UI와 상세 trace 화면을 구성합니다. |
| `student_parts/` | 학생이 주차별 핵심 tool 함수를 구현하는 폴더입니다. |
| `fixed/` | 설정, 런타임, 저장소, trace, LLM 연결 등 기준 코드입니다. |
| `mcp_server/` | Week 5에서 사용하는 외부 SQLite MCP 서버 기준 구현입니다. |
| `static/` | UI 스타일과 Kanana 브랜드 이미지입니다. |
| `run.sh` | 설치와 앱 실행을 담당하는 runner입니다. |

## 전체 실행 흐름

1. 사용자가 `./run.sh --weekN`으로 앱을 실행합니다.
2. `app.py`가 Gradio UI를 띄우고 `fixed/agent_runtime.py`가 사용자 메시지를 저장합니다.
3. `fixed/week_agent_registry.py`가 `KANANA_ACTIVE_WEEK`에 맞는 `student_parts/weekXX_*.py`의 `build_week_agent()`를 호출합니다.
4. 선택된 agent가 prompt와 tool 목록을 보고 필요한 tool을 호출합니다.
5. tool call/result는 상세 탭의 trace JSON으로 표시됩니다.

초기 배포 상태에서 학생 구현 대상 tool은 실제 정답 로직 대신 `student_todo: true` JSON을 반환합니다. 학생은 trace에서 입력값과 기대 payload 키를 확인하며 함수 본문을 하나씩 완성합니다.

## 주차별 학습 흐름

| 주차 | 파일 | 핵심 개념 | 구현 포인트 |
| --- | --- | --- | --- |
| Week 1 | `student_parts/week01_wake_up_nana.py` | LangChain tool 기초 | 현재 대화 전용 개인 일정 생성/조회/삭제 |
| Week 2 | `student_parts/week02_structure_natural_language_requests.py` | Structured output | 자연어 요청을 `StructuredRequest`로 구조화 |
| Week 3 | `student_parts/week03_build_nanas_logbook.py` | SQLite persistence | 구조화 요청 저장, 조회, 수정, 삭제 |
| Week 4 | `student_parts/week04_retrieve_nanas_memory.py` | Agentic RAG | 참고자료, 저장 요청, 앱 대화 검색 출처 구분 |
| Week 5 | `student_parts/week05_load_kanas_past_conversations.py` | MCP tool 연결 | 외부 대화/MCP tool wrapper 구현 |
| Week 6 | `student_parts/week06_kanamate_decides_schedule.py` | Supervisor / sub-agent | Nana/Kana 역할 분리와 최종 일정 결정 |

주차가 올라갈수록 앞 주차의 결과를 재사용합니다. 예를 들어 Week 3은 Week 2의 구조화 결과를 저장하고, Week 6은 Week 4/5 도구를 Nana/Kana 하위 agent에 나누어 제공합니다.

## 추천 탐색 순서

1. [README.md](README.md)로 실행 방법과 `.env` 설정을 확인합니다.
2. `student_parts/week01_wake_up_nana.py`부터 열어 `[수강생 구현 가이드]`를 읽습니다.
3. `week01_tools()`가 어떤 tool을 agent에 공개하는지 확인합니다.
4. `./run.sh --week1`로 앱을 실행하고 샘플 요청을 입력합니다.
5. 상세 trace에서 `student_todo: true`, `tool_name`, `received` 값을 확인합니다.
6. 해당 함수 본문을 구현한 뒤 다시 실행해 trace 결과가 어떻게 바뀌는지 비교합니다.

## 자주 쓰는 명령

```bash
./run.sh --install
```

처음 의존성을 설치하고 Week 1 앱을 실행합니다.

```bash
./run.sh --week4
```

특정 주차 agent로 앱을 실행합니다.

```bash
./run.sh --help
```

runner에서 지원하는 옵션을 확인합니다.

## 읽는 팁

- 학생 구현 범위는 각 `student_parts/weekXX_*.py` 파일 상단의 `[수강생 구현 가이드]`가 기준입니다.
- `fixed/`와 `mcp_server/`는 기준 구현을 이해하기 위한 참고 코드이며, 수업에서 별도 지시가 없으면 수정하지 않습니다.
- 앱 화면에서 어떤 tool이 호출됐는지 궁금하면 상세 탭의 trace를 확인하세요.
