from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from fixed.app_store import AppSQLiteStore
from fixed.config import CONFIG
from fixed.external_mcp import call_external_tool_payload
from fixed.external_people_store import (
    external_schedule_summary,
    normalize_external_member_names,
    normalize_external_schedule_date_bounds,
)
from fixed.llm import chat_model
from fixed.mcp_client import (
    call_local_mcp_tool,
    call_local_mcp_tool_sync,
    load_local_mcp_tools,
    load_local_mcp_tools_sync,
)
from fixed.runtime_clock import current_app_date_iso
from fixed.session_scope import DEFAULT_SESSION_SCOPE, current_session_scope
from student_parts.week01_wake_up_nana import PERSONAL_SCHEDULES, join_system_prompt
from student_parts.week02_structure_natural_language_requests import StructuredRequest
from student_parts.week04_retrieve_nanas_memory import week04_prompt_parts, week04_tools


_WEEK05_AGENT: Any | None = None


# [수강생 구현 가이드]
#
# 목표
#   외부 SQLite/MCP 서버에 있는 Kana의 이전 대화와 공유 일정을 LangChain agent가 사용할 수 있게 감쌉니다.
#   학생이 직접 SQL을 작성하는 주차가 아니라, MCP tool을 호출하고 그 결과를 agent용 JSON으로 전달하는
#   wrapper tool을 만드는 주차입니다.
#
# 구현 위치와 사용할 코드
#   - 이 파일(student_parts/week05_load_kanas_past_conversations.py)의 @tool wrapper 함수들을 구현합니다.
#   - 실제 외부 SQLite/MCP tool 구현은 mcp_server/sqlite_mcp_server.py에 있으며, 학생은 이 파일을 직접 수정하지 않습니다.
#   - MCP 호출은 fixed/mcp_client.py의 call_local_mcp_tool_sync를 이 파일에서 별칭으로 둔
#     call_mcp_tool_sync(tool_name, args)를 사용합니다.
#   - load_conversation_messages는 fixed/external_mcp.py의 call_external_tool_payload(...)를 사용해
#     외부 tool payload를 dict로 받은 뒤 json_payload()로 감쌉니다.
#   - 멤버 이름/날짜 정규화와 요약은 fixed/external_people_store.py의
#     normalize_external_member_names(), normalize_external_schedule_date_bounds(),
#     external_schedule_summary()를 사용합니다.
#   - 내 일정 수집은 _personal_schedules_for_current_scope()에서 처리합니다. 이 helper는
#     fixed/app_store.py의 AppSQLiteStore(CONFIG.app_db_path).list_schedules(...)와
#     student_parts/week01_wake_up_nana.py의 PERSONAL_SCHEDULES 중 현재 대화 범위 row를 합칩니다.
#   - Week 3+ AppSQLiteStore는 개인/그룹 일정을 저장할 때 공유 일정 저장소에 자동 동기화할 수 있습니다.
#     이 파일의 create/list/delete_shared_schedule wrapper는 공유 저장소 row 자체를 직접 확인하거나 보정할 때 사용합니다.
#   - week05_tools()는 student_parts/week04_retrieve_nanas_memory.py의 week04_tools() 위에
#     Week 5 MCP wrapper tool들을 누적해 Week 5 단일 agent에 공개합니다.
#
# 구현 대상
#   1. search_previous_conversations
#      - query, member_names, limit를 받습니다.
#      - 이 파일의 call_mcp_tool_sync("search_previous_conversations", args)를 호출하고 결과 문자열을 그대로 반환합니다.
#      - 멤버 이름 정규화는 외부 SQLite store/MCP 경계에서 한 번만 처리하므로 wrapper에서 중복 변환하지 않습니다.
#
#   2. load_conversation_messages
#      - conversation_id로 외부 SQLite/MCP helper에서 이전 대화 메시지를 조회합니다.
#      - call_external_tool_payload("load_conversation_messages", {"conversation_id": conversation_id})를 사용합니다.
#      - 대화 메시지의 speaker/content/created_at 순서가 보존되도록 결과를 가공하지 않습니다.
#
#   3. extract_schedules_from_history
#      - member_names, date_from, date_to를 받습니다.
#      - call_mcp_tool_sync("extract_schedules_from_history", args)를 호출합니다.
#      - 날짜 형식 정리는 외부 SQLite store/MCP 경계에서 한 번만 처리합니다.
#      - 결과 rows는 member_name/title/date/start_time/end_time/notes 필드를 유지해야 합니다.
#
#   4. create_shared_schedule / delete_shared_schedule / list_shared_schedules
#      - 각각 call_mcp_tool_sync("create_shared_schedule" / "delete_shared_schedule" / "list_shared_schedules", args)를 호출합니다.
#      - 공유 일정 저장소 row를 생성/삭제/조회할 때 MCP tool 결과를 그대로 전달합니다.
#      - schedule_id 또는 source_conversation_id를 보존해야 나중에 수정/삭제 동기화가 가능합니다.
#      - 공유 저장소 자체를 확인할 때는 list_shared_schedules로 "나"를 포함한 등록 row를 조회합니다.
#      - 필터 없이 list_shared_schedules를 호출하면 외부 실습용 기본 공유 일정 row가 우선 반환될 수 있습니다.
#
#   5. collect_member_schedules
#      - 3주차 이후 저장된 내 일정은 앱 SQLite에서 읽고, 현재 대화의 임시 일정만 추가로 합칩니다.
#      - 외부 멤버 일정은 call_mcp_tool_sync("extract_schedules_from_history", args) 결과를 이 tool 안에서 읽습니다.
#      - 두 출처를 member_name/title/date/start_time/end_time/notes가 있는 rows 배열로 직접 합칩니다.
#      - schedule_summary도 함께 반환해 LLM이 바쁜 시간을 자연어로 설명할 수 있게 합니다.
#      - PERSONAL_SCHEDULES는 현재 대화 범위의 아직 DB에 없는 임시 일정만 합치고, SQLite에 이미 저장된 일정과 중복하지 않습니다.
#
# 책임 경계
#   mcp_server/sqlite_mcp_server.py의 @mcp.tool 구현은 학생 구현 대상이 아닙니다.
#   이 파일의 wrapper tool은 직접 SQL이나 중복 정규화 helper를 두지 않고 store/MCP helper의 결과 JSON을 전달합니다.
#   week05_tools()는 Week 1-4 도구에 외부 SQLite/MCP 일정 도구를 누적합니다.
#   외부 멤버 busy-time 조회와 공유 저장소 row 조회는 Week 5 범위지만, 여러 사람의 최종 회의 시간 선택은 Week 6 범위입니다.
#
# 검증 방법
#   ./run.sh --week5에서 외부 팀원 일정 조회 요청을 입력합니다.
#   trace에서 search_previous_conversations, load_conversation_messages, extract_schedules_from_history 중
#   어떤 tool이 어떤 순서로 호출됐는지 확인합니다.
#   collect_member_schedules 결과 rows에 "나"와 외부 멤버 일정이 같은 구조로 들어 있고,
#   list_shared_schedules 결과에 rows와 schedule_summary가 유지되는지도 확인합니다.
#
# 함수별 동작 설명
#   - _schedule_scope(schedule)
#     Week 1 임시 일정이 어느 대화 범위에 속하는지 읽습니다. session_id가 없으면 기본 scope로 처리합니다.
#
#   - _personal_schedules_for_current_scope()
#     Week 3 이후 SQLite에 저장된 내 일정과 현재 대화에만 남아 있는 Week 1 임시 일정을 합칩니다.
#     이미 SQLite에 저장된 일정과 임시 일정이 중복되지 않도록 schedule_id/id를 기준으로 한 번 걸러냅니다.
#
#   - json_payload(payload)
#     외부 MCP 결과나 내부 helper 결과 dict를 한글이 보존되는 JSON 문자열로 바꿉니다.
#
#   - SearchPreviousConversationsInput / LoadConversationMessagesInput / ExtractSchedulesFromHistoryInput
#     외부 이전 대화 검색, 대화 메시지 로드, 외부 대화에서 일정 추출 tool의 입력 스키마입니다.
#
#   - CreateSharedScheduleInput / DeleteSharedScheduleInput / ListSharedSchedulesInput
#     외부 공유 일정 저장소에 row를 생성, 삭제, 조회할 때 쓰는 입력 스키마입니다.
#
#   - CollectMemberSchedulesInput
#     내 일정과 외부 멤버 busy-time을 같은 rows 배열로 합치는 collect_member_schedules tool 입력 스키마입니다.
#
#   - _structured_request_from_schedule_row(row)
#     SQLite schedule row나 Week 1 임시 schedule row를 Week 2 StructuredRequest 모양으로 읽습니다.
#     뒤에서 내 일정 row를 외부 멤버 row와 같은 구조로 맞출 때 사용합니다.
#
#   - _collect_member_schedules(...)
#     내 일정과 외부 멤버 일정을 같은 member_name/title/date/start_time/end_time/notes row 구조로 합칩니다.
#     외부 멤버 이름과 날짜 범위는 fixed/external_people_store.py helper로 정규화합니다.
#
#   - search_previous_conversations(...)
#     외부 SQLite/MCP 서버에 저장된 과거 대화를 검색합니다. wrapper는 query/member_names/limit를 넘기고 결과 문자열을 그대로 반환합니다.
#
#   - load_conversation_messages(conversation_id)
#     검색으로 찾은 특정 외부 대화의 전체 메시지를 불러옵니다. speaker/content/created_at 순서를 보존합니다.
#
#   - extract_schedules_from_history(...)
#     외부 멤버의 이전 대화에서 일정 또는 바쁜 시간 row를 추출합니다.
#
#   - create_shared_schedule(...) / delete_shared_schedule(...) / list_shared_schedules(...)
#     공유 일정 저장소를 조작하거나 조회하는 MCP wrapper입니다. source_conversation_id와 schedule_id를 보존해 동기화 근거로 씁니다.
#
#   - collect_member_schedules(...)
#     내 일정과 외부 멤버 busy-time을 한 번에 모으는 Week 5 핵심 tool입니다.
#     Week 6의 공통 가능 시간 결정 tool이 이 rows를 busy_rows 근거로 사용합니다.
#
#   - week05_tools()
#     Week 4까지의 tool에 외부 대화/MCP/공유 일정 tool을 누적합니다.
#
#   - week05_system_prompt() / week05_prompt_parts()
#     개인 저장/RAG는 이전 주차 도구로, 외부 멤버 대화와 일정은 MCP wrapper로 처리하도록 agent 역할을 설명합니다.
#
#   - build_week05_agent() / build_week_agent()
#     Week 1~5 tool을 가진 agent를 한 번만 만들고 재사용합니다.


call_mcp_tool = call_local_mcp_tool
call_mcp_tool_sync = call_local_mcp_tool_sync
load_langchain_mcp_tools = load_local_mcp_tools
load_langchain_mcp_tools_sync = load_local_mcp_tools_sync


def _schedule_scope(schedule: dict[str, Any]) -> str:
    return str(schedule.get("session_id") or DEFAULT_SESSION_SCOPE)


def _personal_schedules_for_current_scope() -> list[dict[str, Any]]:
    """SQLite 저장 일정과 현재 대화의 임시 일정만 group 조율 후보로 사용합니다."""

    # TODO: SQLite 저장 일정과 현재 대화의 임시 일정을 합쳐 반환하세요.
    ...


def json_payload(payload: dict[str, Any]) -> str:
    """도구 반환용 dict를 한글이 깨지지 않는 JSON 문자열로 변환합니다."""

    return json.dumps(payload, ensure_ascii=False)


class SearchPreviousConversationsInput(BaseModel):
    """외부 이전 대화 검색 입력입니다."""

    query: str
    member_names: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=50)


class LoadConversationMessagesInput(BaseModel):
    """외부 대화 메시지 조회 입력입니다."""

    conversation_id: str


class ExtractSchedulesFromHistoryInput(BaseModel):
    """외부 멤버 일정 추출 입력입니다."""

    member_names: list[str]
    date_from: str
    date_to: str


class CreateSharedScheduleInput(BaseModel):
    """공유 일정 생성 입력입니다."""

    member_name: str
    title: str
    date: str
    start_time: str
    end_time: str = "미정"
    notes: str | None = None
    source_conversation_id: str | None = None
    schedule_id: str | None = None


class DeleteSharedScheduleInput(BaseModel):
    """공유 일정 삭제 입력입니다."""

    schedule_id: str | None = None
    source_conversation_id: str | None = None


class ListSharedSchedulesInput(BaseModel):
    """공유 일정 조회 입력입니다."""

    member_names: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    source_conversation_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CollectMemberSchedulesInput(BaseModel):
    """내 일정과 외부 멤버 busy-time 수집 입력입니다."""

    member_names: list[str]
    date_from: str
    date_to: str


def _structured_request_from_schedule_row(row: dict[str, Any]) -> StructuredRequest:
    """앱 일정 row를 Week 2 StructuredRequest 기준으로 읽습니다."""

    return StructuredRequest(
        kind="personal_schedule",
        title=row.get("title"),
        date=row.get("date"),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        members=row.get("attendees") or row.get("members") or [],
        original_text=str(row.get("title") or ""),
    )


def _collect_member_schedules(
    *,
    member_names: list[str],
    date_from: str,
    date_to: str,
    personal_schedules: list[dict[str, Any]],
) -> dict[str, Any]:
    """내 일정과 외부 멤버 일정을 같은 row 구조로 합칩니다."""

    # TODO: 내 SQLite/임시 일정과 외부 MCP 일정 rows를 같은 구조로 합치세요.
    ...


@tool(args_schema=SearchPreviousConversationsInput)
def search_previous_conversations(
    query: str,
    member_names: list[str] | None = None,
    limit: int = 5,
) -> str:
    """외부 SQLite 데이터베이스에 저장된 이전 대화를 검색합니다. query에는 LLM이 고른 짧은 핵심 명사나 구를 넣습니다."""

    # TODO: call_mcp_tool_sync("search_previous_conversations", args)를 호출하고 결과 문자열을 반환하세요.
    ...


@tool(args_schema=LoadConversationMessagesInput)
def load_conversation_messages(conversation_id: str) -> str:
    """외부 SQLite 데이터베이스에서 특정 이전 대화의 모든 메시지를 불러옵니다."""

    # TODO: call_external_tool_payload("load_conversation_messages", {"conversation_id": ...}) 결과를 JSON으로 반환하세요.
    ...


@tool(args_schema=ExtractSchedulesFromHistoryInput)
def extract_schedules_from_history(member_names: list[str], date_from: str, date_to: str) -> str:
    """외부 SQLite 이전 대화에서 멤버별 일정을 추출합니다."""

    # TODO: call_mcp_tool_sync("extract_schedules_from_history", args)를 호출해 외부 멤버 busy-time rows를 반환하세요.
    ...


@tool(args_schema=CreateSharedScheduleInput)
def create_shared_schedule(
    member_name: str,
    title: str,
    date: str,
    start_time: str,
    end_time: str = "미정",
    notes: str | None = None,
    source_conversation_id: str | None = None,
    schedule_id: str | None = None,
) -> str:
    """외부 MCP 공유 일정 저장소에 일정을 등록하거나 갱신합니다."""

    # TODO: call_mcp_tool_sync("create_shared_schedule", args)로 공유 일정 row를 생성/갱신하세요.
    ...


@tool(args_schema=DeleteSharedScheduleInput)
def delete_shared_schedule(
    schedule_id: str | None = None,
    source_conversation_id: str | None = None,
) -> str:
    """외부 MCP 공유 일정 저장소에서 일정을 삭제합니다."""

    # TODO: call_mcp_tool_sync("delete_shared_schedule", args)로 공유 일정을 삭제하세요.
    ...


@tool(args_schema=ListSharedSchedulesInput)
def list_shared_schedules(
    member_names: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source_conversation_id: str | None = None,
    limit: int = 50,
) -> str:
    """외부 MCP 공유 일정 저장소에 등록된 일정을 조회합니다. 필터가 없으면 기본 공유 일정을 반환합니다."""

    # TODO: call_mcp_tool_sync("list_shared_schedules", args)로 공유 일정 저장소 rows를 조회하세요.
    ...


@tool(args_schema=CollectMemberSchedulesInput)
def collect_member_schedules(member_names: list[str], date_from: str, date_to: str) -> str:
    """내 일정과 다른 사람들의 일정을 MCP SQLite 기록에서 모읍니다."""

    # TODO: 내 일정과 외부 멤버 busy-time rows를 모아 JSON 문자열로 반환하세요.
    ...


def week05_tools() -> list[Any]:
    """4주차까지의 도구에 외부 SQLite/MCP 일정 도구를 누적한 목록입니다."""

    return [
        *week04_tools(),
        search_previous_conversations,
        load_conversation_messages,
        extract_schedules_from_history,
        create_shared_schedule,
        delete_shared_schedule,
        list_shared_schedules,
        collect_member_schedules,
    ]


def week05_system_prompt() -> str:
    """5주차 단일 agent가 따르는 시스템 프롬프트입니다."""

    return join_system_prompt(week05_prompt_parts())


def week05_prompt_parts() -> list[str]:
    """1~5주차 system prompt 조각을 누적합니다."""

    return [
        *week04_prompt_parts(),
        "너는 Kanana의 Week 5 Kana history agent다. "
        f"현재 날짜는 앱 시작 시 OS에서 읽은 {current_app_date_iso()}이다. "
        "개인 일정/저장/RAG 요청은 Week 3 이후 SQLite 저장 도구를 기준으로 처리한다. "
        "새 일정, 할 일, 알림 생성은 extract_schedule_request로 구조화한 뒤 "
        "structured_request를 바로 save_structured_request에 전달한다. "
        "personal_create_schedule은 Week 1-2 임시 메모리용이므로 Week 5에서 새 일정 저장에 사용하지 않는다. "
        "일정 목록이나 기간 조회는 personal_list_saved_schedules로 앱 SQLite row를 확인하고, "
        "특정 날짜나 기간 조회는 personal_list_saved_schedules의 date_from/date_to를 YYYY-MM-DD로 채운다. "
        "personal_list_schedules는 Week 5의 단순 조회에 사용하지 않는다. "
        "사용자가 구체적인 날짜와 시간을 말하며 미팅/회의를 잡아줘, 등록해줘, 추가해줘라고 요청하면 "
        "참석자가 있어도 외부 일정 조율이 아니라 앱 DB 일정 저장 요청이다. "
        "이 경우 extract_schedule_request로 구조화한 뒤 structured_request를 save_structured_request에 전달해 저장한다. "
        "kind가 group_schedule이면 personal_create_schedule을 거치지 말고 구조화 결과를 그대로 저장한다. "
        "사용자가 '내가 했던 대화 목록', '이전 채팅', '방금 다른 대화에서 말한 내용'처럼 "
        "내 앱의 일반 채팅 발화에서 답을 찾으라고 하면 search_conversation_messages의 context와 hits를 근거로 답한다. "
        "search_conversation_messages는 SQLite 대화 목록을 대화 1개당 1개 청크로 ChromaDB에 lazy sync한 뒤 검색하는 agentic RAG tool이다. "
        "search_saved_requests는 일정/할 일/알림 구조화 기록 전용이며 일반 채팅 메시지 검색용이 아니다. "
        "검색 tool의 query는 코드에서 토큰화하지 않으므로, 질문 전체가 아니라 네가 직접 고른 짧은 핵심 검색 문자열을 넣는다. "
        "사용자가 직전 질문에 이어 '지난 대화 검색해서 찾아줘'처럼 말하면 직전 질문의 대상 명사를 query로 삼는다. "
        "예를 들어 '내가 가지고 있는 양의 색은 뭐야?' 다음 검색 요청은 search_conversation_messages(query='양')처럼 호출한다. "
        "일반 채팅 발화 검색 결과가 비어 있으면 search_saved_requests로 넘어가지 말고, 같은 search_conversation_messages에 더 짧은 핵심어로 다시 검색한다. "
        "외부 멤버의 이전 대화나 일정 추출이 필요하면 search_previous_conversations, "
        "load_conversation_messages, extract_schedules_from_history를 사용한다. "
        "사용자가 '외부 공유 데이터', '공유 일정 확인', '공유 일정 보여줘'처럼 공유 저장소 row를 묻는 경우 "
        "되묻지 말고 list_shared_schedules를 사용한다. 날짜/멤버가 없으면 tool의 기본 공유 일정 조회 결과를 답한다. "
        "공유 일정 저장소에 등록된 row 자체를 확인해야 하면 list_shared_schedules를 사용한다. "
        "내 일정과 외부 멤버 일정을 함께 모아야 하면 collect_member_schedules를 사용한다. "
        "이때 내 이전 일정은 Week 3 이후 SQLite에 저장된 row를 기준으로 본다. "
        "내 일정이 공유 저장소에도 보여야 할 때는 create_shared_schedule/delete_shared_schedule을 사용한다. "
        "Week 5에서는 여러 사람의 공통 가능 시간을 최종 결정하는 payload만 만들지 않고, "
        "이미 날짜와 시간이 정해진 일정 등록은 저장 도구로 처리한다. "
        "도구 결과에 없는 일정이나 시간을 만들지 않는다."
    ]


def build_week05_agent() -> object:
    """Week 1-5 누적 tool 목록을 노출하는 단일 LangChain agent를 만듭니다."""

    if not CONFIG.has_openai_key:
        raise RuntimeError("PROXY_TOKEN이 .env에 필요합니다.")
    global _WEEK05_AGENT
    if _WEEK05_AGENT is None:
        _WEEK05_AGENT = create_agent(
            model=chat_model(),
            tools=week05_tools(),
            system_prompt=week05_system_prompt(),
        )
    return _WEEK05_AGENT


def build_week_agent() -> object:
    """active-week registry가 호출하는 표준 Week agent builder입니다."""

    return build_week05_agent()
