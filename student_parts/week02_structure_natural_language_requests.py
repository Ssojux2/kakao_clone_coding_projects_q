from __future__ import annotations

import json
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.tools import tool
from pydantic import BaseModel, Field

from fixed.config import CONFIG
from fixed.llm import chat_model
from fixed.runtime_clock import current_app_date_iso
from student_parts.week01_wake_up_nana import join_system_prompt, week01_prompt_parts


RequestKind = Literal["personal_schedule", "group_schedule", "todo", "reminder", "unknown"]
_WEEK02_AGENT: Any | None = None


# [수강생 구현 가이드]
#
# 목표
#   사용자의 한국어 자연어 요청을 일정 앱이 읽을 수 있는 StructuredRequest로 바꿉니다.
#   Week 1은 이미 정해진 인자를 받아 일정을 만들었다면, Week 2는 "내일 오후 3시" 같은
#   자연어를 날짜/시간/종류/멤버 필드로 구조화하는 단계입니다. 구조화 결과는 아직 저장하지 않습니다.
#
# 구현 위치와 사용할 코드
#   - 이 파일(student_parts/week02_structure_natural_language_requests.py)의 StructuredRequest 스키마와
#     build_week02_agent(), extract_structured_request(), extract_schedule_request() 흐름을 확인합니다.
#   - build_week02_agent()는 langchain.agents.create_agent, fixed/llm.py의 chat_model(),
#     week02_system_prompt(), response_format=StructuredRequest를 사용해 Week 2 단일 agent를 만듭니다.
#   - extract_structured_request()는 Week 3 이상 tool에서 재사용되는 helper이며,
#     agent를 새로 만들지 않고 chat_model().with_structured_output(StructuredRequest, ...)를 호출합니다.
#   - extract_schedule_request()는 extract_structured_request() 결과를 base_date와 함께
#     ok/tool_name/structured_request JSON tool payload로 감쌉니다.
#   - week02_prompt_parts()는 student_parts/week01_wake_up_nana.py의 week01_prompt_parts() 위에
#     Week 2 구조화 지시를 추가합니다.
#
# 구현 대상
#   1. StructuredRequest 스키마
#      - kind/title/date/start_time/end_time/members/priority/reason/original_text 필드가
#        이후 Week 3 저장 payload의 기준이 됩니다.
#      - kind는 RequestKind Literal에 들어 있는 값만 허용합니다.
#
#   2. extract_structured_request / extract_schedule_request
#      - extract_structured_request는 nested agent를 만들지 않고 chat_model().with_structured_output(...)만 사용합니다.
#      - extract_schedule_request는 helper 결과를 JSON 문자열로 반환하는 tool wrapper입니다.
#      - LLM이 판단한 kind와 members를 임의 기본값으로 덮어쓰지 말고 그대로 보존합니다.
#
#   3. build_week02_agent
#      - LangChain agent에 response_format=StructuredRequest를 넘깁니다.
#      - Week 2 대화에서는 별도 tool 호출 없이 최종 structured_response를 바로 확인합니다.
#
# StructuredRequest 읽는 법
#   - kind: personal_schedule, group_schedule, todo, reminder, unknown 중 하나입니다.
#   - title/date/start_time/end_time: 일정 앱이 실제 저장이나 생성에 사용할 핵심 필드입니다.
#   - members: 참석자/관련 멤버 list입니다. 모르면 빈 list로 둡니다.
#   - priority/reason/original_text: 할 일 우선순위, 판단 근거, 원문 보존용 필드입니다.
#   - 모르는 값을 억지로 만들지 않는 것이 중요합니다. 확실하지 않으면 None 또는 빈 list가 안전합니다.
#   - date/start_time/end_time은 확실할 때만 YYYY-MM-DD, HH:MM 형식으로 채웁니다.
#
# 참고 코드
#   extract_schedule_request
#      - Week 3 이상에서 DB 저장 tool chain에 쓰는 재사용 helper입니다.
#      - query 문자열을 agent가 아닌 structured LLM 호출로 구조화한 뒤 JSON tool payload로 감쌉니다.
#
# 검증 방법
#   ./run.sh --week2로 실행한 뒤 "다음 주 화요일 오후 3시에 철수랑 회의 잡아줘" 같은 문장을 입력합니다.
#   최종 답변이 StructuredRequest class 형식의 structured_response로 나오는지 확인합니다.
#   Week 3에서는 trace에서 extract_schedule_request 이후 save_structured_request가 호출되는지 봅니다.
#
# 함수별 동작 설명
#   - StructuredRequest
#     Week 2 structured output의 중심 스키마입니다. LLM이 자연어에서 뽑은 요청 종류, 제목, 날짜, 시간,
#     멤버, 우선순위, 근거, 원문을 이 class 필드에 맞춰 반환합니다.
#
#   - _coerce_structured_request(value)
#     LangChain structured output 결과가 이미 StructuredRequest이면 그대로 쓰고, dict이면 Pydantic 검증을 거쳐
#     StructuredRequest로 바꿉니다. 예상한 형태가 아니면 오류를 내서 잘못된 LLM 응답을 조용히 통과시키지 않습니다.
#
#   - extract_structured_request(text)
#     agent loop를 새로 만들지 않고 chat_model().with_structured_output(...)만 사용해 자연어를 StructuredRequest로 변환합니다.
#     Week 3 이상에서 저장 직전 자연어를 구조화해야 할 때 재사용하는 핵심 helper입니다.
#
#   - extract_schedule_request(query)
#     LangChain tool로 노출되는 wrapper입니다. extract_structured_request(...) 결과에 ok/tool_name/base_date를 붙여
#     JSON 문자열로 반환하므로, 이후 저장 tool이 structured_request 필드를 그대로 받을 수 있습니다.
#
#   - week02_tools()
#     Week 2 대화 agent는 tool을 쓰지 않고 response_format으로 구조화 결과를 바로 반환하므로 빈 목록을 반환합니다.
#
#   - week02_system_prompt() / week02_prompt_parts()
#     Week 1 prompt 위에 "자연어를 StructuredRequest로만 출력한다"는 Week 2 지시를 누적합니다.
#
#   - build_week02_agent() / build_week_agent()
#     response_format=StructuredRequest가 설정된 agent를 만들고 재사용합니다. build_week_agent()는 실행기가 찾는 표준 entry point입니다.


class StructuredRequest(BaseModel):
    """LLM structured output으로 추출되는 2주차 요청 스키마입니다."""

    # TODO: kind 필드를 RequestKind 타입으로 정의하세요.
    # TODO: title/date/start_time/end_time 필드를 정의하세요.
    # TODO: members/priority/reason/original_text 필드를 정의하세요.
    ...


def _coerce_structured_request(value: Any) -> StructuredRequest:
    """LangChain structured output 결과를 StructuredRequest로 정규화합니다."""

    if isinstance(value, StructuredRequest):
        return value
    if isinstance(value, dict):
        return StructuredRequest.model_validate(value)
    raise RuntimeError("LLM structured output 결과에서 StructuredRequest를 찾지 못했습니다.")


def extract_structured_request(text: str) -> StructuredRequest:
    """agent를 새로 띄우지 않고 structured LLM 호출로 요청을 변환합니다."""

    # TODO: chat_model().with_structured_output(StructuredRequest, ...)로 자연어 요청을 구조화하세요.
    ...


@tool
def extract_schedule_request(query: str) -> str:
    """사용자 프롬프트를 일정 앱용 구조화 요청 JSON으로 변환합니다."""

    # TODO: extract_structured_request 결과를 base_date와 함께 JSON 문자열로 반환하세요.
    ...


def week02_tools() -> list[Any]:
    """Week 2 대화 agent는 tool 없이 structured_response를 직접 반환합니다."""

    return []


def week02_system_prompt() -> str:
    """2주차 단일 agent가 따르는 시스템 프롬프트입니다."""

    return join_system_prompt(week02_prompt_parts())


def week02_prompt_parts() -> list[str]:
    """2주차 structured output agent가 따르는 system prompt 조각입니다."""

    return [
        *week01_prompt_parts(),
        # TODO: Week 2 요청 구조화 agent system prompt를 자유롭게 추가하세요.
    ]


def build_week02_agent() -> object:
    """Week 2 대화에서 structured_response를 직접 반환하는 단일 LangChain agent를 만듭니다."""

    if not CONFIG.has_openai_key:
        raise RuntimeError("PROXY_TOKEN이 .env에 필요합니다.")
    global _WEEK02_AGENT
    if _WEEK02_AGENT is None:
        _WEEK02_AGENT = create_agent(
            model=chat_model(),
            tools=week02_tools(),
            response_format=StructuredRequest,
            system_prompt=week02_system_prompt(),
        )
    return _WEEK02_AGENT


def build_week_agent() -> object:
    """active-week registry가 호출하는 표준 Week agent builder입니다."""

    return build_week02_agent()
