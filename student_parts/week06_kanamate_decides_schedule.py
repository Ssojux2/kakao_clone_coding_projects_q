from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from fixed.external_people_store import normalize_external_member_names
from fixed.langchain_trace import extract_agent_events, extract_final_text
from fixed.llm import chat_model
from fixed.runtime_clock import current_app_date_iso
from fixed.schedule_decision import (
    CommonSlotCandidate,
    decide_final_slot_payload,
    find_common_available_slots_payload,
    normalize_date_bound,
)
from student_parts.week01_wake_up_nana import join_system_prompt
from student_parts.week02_structure_natural_language_requests import extract_schedule_request
from student_parts.week03_build_nanas_logbook import SavedScheduleListInput, personal_list_saved_schedules
from student_parts.week04_retrieve_nanas_memory import week04_prompt_parts, week04_tools
from student_parts.week05_load_kanas_past_conversations import (
    collect_member_schedules,
    extract_schedules_from_history,
    list_shared_schedules,
    load_conversation_messages,
    search_previous_conversations,
    week05_prompt_parts,
)


_NANA_SUBAGENT: Any | None = None
_KANA_SUBAGENT: Any | None = None
_SUPERVISOR_AGENT: Any | None = None


PERSONAL_SCHEDULE_LOOKUP_TERMS = ("조회", "보여", "알려", "뭐", "무엇", "있", "확인", "목록", "전체")
PERSONAL_SCHEDULE_MUTATION_TERMS = (
    "잡아",
    "추가",
    "저장",
    "등록",
    "만들",
    "생성",
    "수정",
    "변경",
    "삭제",
    "지워",
    "취소",
)


# [수강생 구현 가이드]
#
# 목표
#   Week 6은 "모든 기능을 한 agent가 직접 처리"하지 않고 supervisor가 Nana/Kana 하위 agent로 위임하게 만듭니다.
#   Nana는 개인 일정/저장/RAG를 맡고, Kana는 외부 대화/멤버 일정/그룹 시간 결정을 맡습니다.
#   supervisor가 직접 볼 수 있는 tool은 nana_agent와 kana_agent 두 개뿐입니다.
#
# 구현 위치와 사용할 코드
#   - 이 파일(student_parts/week06_kanamate_decides_schedule.py)의 Week 6 전용 tool과 sub-agent wrapper를 구현합니다.
#   - 공통 가능 시간 검증/최종 선택 payload 생성은 fixed/schedule_decision.py의
#     find_common_available_slots_payload(), decide_final_slot_payload(), normalize_date_bound()를 사용합니다.
#   - Nana 하위 agent 도구는 student_parts/week04_retrieve_nanas_memory.py의 week04_tools()를 그대로 사용합니다.
#   - Kana 하위 agent 도구는 이 파일의 kana_tools()에서 구성하며, Week 2 extract_schedule_request와
#     Week 5 wrapper tool(search_previous_conversations, extract_schedules_from_history,
#     collect_member_schedules 등), find_common_available_slots, decide_final_slot을 포함합니다.
#   - supervisor가 볼 수 있는 도구는 supervisor_tools()의 nana_agent, kana_agent 두 개뿐입니다.
#   - nana_agent()/kana_agent()/build_langchain_supervisor_agent()는 create_agent(...)로 각각 필요한 agent를 만들고 재사용합니다.
#   - trace 정리는 fixed/langchain_trace.py의 extract_agent_events(), extract_final_text()를 사용합니다.
#
# 구현 대상
#   1. find_common_available_slots / decide_final_slot
#      - find_common_available_slots는 busy-time row를 Python 룰이나 nested LLM으로 훑지 않고,
#        Kana agent가 tool description을 읽고 직접 고른 candidate_slots payload를 검증/기록합니다.
#      - date_from/date_to에 ISO datetime이 들어오면 normalize_date_bound()로 날짜 부분만 사용합니다.
#      - busy_rows가 None이면 collect_member_schedules를 호출해 내 일정과 외부 멤버 busy-time을 모읍니다.
#      - decide_final_slot도 nested LLM을 만들지 않고 Kana agent가 넘긴 final_slot, selected_index,
#        needs_agent_selection, reason payload를 그대로 course repo JSON 계약에 맞춰 기록합니다.
#      - 반환 JSON은 course repo 기준 top-level final_slot, reason, candidates를 반드시 포함합니다.
#      - 후보 판단을 수행한 경우 members, busy_rows, candidate_slots도 함께 남겨 근거를 확인할 수 있게 합니다.
#      - selected_index나 selected_slot이 없으면 final_slot을 자동으로 고르지 말고 needs_agent_selection=True 상태를 유지합니다.
#
#   2. nana_agent
#      - supervisor가 넘긴 query로 Nana 하위 agent를 이 tool 안에서 만들거나 재사용해 실행합니다.
#      - 단순 개인 일정 조회는 _direct_personal_schedule_lookup(...)으로 SQLite를 직접 조회해
#        deterministic_schedule_lookup mode JSON을 반환할 수 있습니다.
#      - 하위 agent 결과에서 answer, trace, inner_tool_names를 뽑아 JSON 문자열로 반환합니다.
#      - 개인 일정 생성/조회/수정/삭제, todo/reminder 저장, 개인 참고자료와 앱 대화 RAG는 Nana 담당입니다.
#
#   3. kana_agent
#      - supervisor가 넘긴 query로 Kana 하위 agent를 이 tool 안에서 만들거나 재사용해 실행합니다.
#      - 하위 trace를 훑어 decide_final_slot 결과를 final_slot_payload로 끌어올립니다.
#      - answer, trace, inner_tool_names, final_slot_payload, final_decision_payload를 JSON으로 반환합니다.
#      - 외부 멤버 일정 조회, 공유 일정 row 조회, 공통 가능 시간 후보 검증과 최종 시간 결정은 Kana 담당입니다.
#
# 중요한 구조
#   Week 6 파일은 Week 1-5 구현을 다시 작성하지 않습니다.
#   이전 주차 tool을 import하고 kana_tools(), supervisor_tools()에서 역할별로 조립합니다.
#   prompt 함수와 직접 일정 조회 helper는 구현 대상이 아니라 agent 역할과 데이터 흐름을 이해하는 참고 코드입니다.
#   find_common_available_slots/decide_final_slot의 실제 겹침 검증과 payload 정리는 fixed/schedule_decision.py가 맡습니다.
#
# Compatibility helper
#   propose_group_schedule은 기존 흐름을 위해 유지합니다.
#   현재 supervisor/kana_tools() 경로의 핵심 구현 대상은 find_common_available_slots,
#   decide_final_slot, nana_agent, kana_agent입니다.
#
# 검증 방법
#   ./run.sh --week6으로 앱을 실행합니다.
#   supervisor trace에서 nana_agent 또는 kana_agent 중 무엇이 선택됐는지 확인합니다.
#   그룹 일정 요청에서는 하위 trace에 search_previous_conversations, extract_schedules_from_history,
#   decide_final_slot이 이어지고 final_slot_payload가 최종 답변과 일치하는지 확인합니다.
#   개인 일정 단순 조회에서는 deterministic_schedule_lookup mode와 personal_list_saved_schedules 호출을 확인합니다.
#
# 함수별 동작 설명
#   - week06_system_prompt() / week06_prompt_parts()
#     supervisor agent의 system prompt를 만듭니다. supervisor는 직접 업무를 처리하지 않고 nana_agent 또는 kana_agent로 위임합니다.
#
#   - nana_prompt_parts() / kana_prompt_parts()
#     하위 에이전트별 역할 prompt를 만듭니다. Nana는 개인 일정/저장/RAG, Kana는 외부 멤버 일정/공통 시간 결정을 담당합니다.
#
#   - nana_system_prompt() / kana_system_prompt() / supervisor_system_prompt()
#     prompt 조각을 join_system_prompt(...)로 합쳐 실제 create_agent(...)에 넘길 system prompt 문자열을 만듭니다.
#
#   - _tool_call_names(events)
#     trace event 목록에서 tool_call 이벤트의 tool_name만 뽑아 UI와 테스트가 호출 순서를 쉽게 확인하게 합니다.
#
#   - extract_langchain_trace(result)
#     supervisor 실행 결과를 events, 선택된 하위 agent, 내부 tool 이름, 최종 시간 payload가 포함된 trace dict로 정리합니다.
#
#   - tool_name(tool_object)
#     LangChain tool 객체와 일반 함수 객체에서 이름을 안전하게 읽습니다. agent_tool_names(...)에서 사용합니다.
#
#   - _compact_query(query) / _is_direct_personal_schedule_lookup(query)
#     단순 개인 일정 조회인지 빠르게 판별합니다. 조회 요청이면 하위 LLM을 거치기 전에 deterministic lookup으로 처리할 수 있습니다.
#
#   - _date_from_query(query)
#     "오늘", "내일", "2026-06-21", "6월 21일" 같은 표현을 SQLite date_from/date_to 필터에 쓸 ISO 날짜로 바꿉니다.
#
#   - _format_korean_date(...) / _format_schedule_time(...) / _format_schedule_line(...)
#     SQLite 일정 row를 사용자에게 읽기 좋은 한국어 일정 문장으로 바꿉니다.
#
#   - _answer_from_saved_schedule_rows(...)
#     personal_list_saved_schedules 결과 rows를 단순 일정 조회 답변 문장으로 바꿉니다.
#
#   - _direct_personal_schedule_lookup(query)
#     개인 일정 조회로 확실하면 personal_list_saved_schedules를 직접 invoke하고, answer와 trace를 포함한 JSON payload를 만듭니다.
#
#   - FindCommonAvailableSlotsInput / DecideFinalSlotInput
#     Kana agent가 공통 가능 시간 후보와 최종 선택을 tool argument로 넘길 때 쓰는 Pydantic 입력 스키마입니다.
#
#   - ProposeGroupScheduleInput / AgentQueryInput
#     기존 호환용 그룹 일정 제안 tool과 supervisor가 하위 agent에 query를 넘기는 wrapper tool의 입력 스키마입니다.
#
#   - find_common_available_slots_dict(...)
#     멤버 이름과 날짜 범위를 정규화하고, busy_rows가 없으면 collect_member_schedules를 호출해 수집합니다.
#     실제 후보 검증 payload 생성은 fixed/schedule_decision.py의 find_common_available_slots_payload(...)가 맡습니다.
#
#   - find_common_available_slots(...)
#     Kana agent가 직접 고른 candidate_slots가 busy_rows와 겹치지 않는지 검증하고 JSON 문자열로 반환하는 tool입니다.
#
#   - decide_final_slot(...)
#     Kana agent가 직접 고른 selected_index/final_slot/reason을 course repo 계약에 맞는 최종 payload로 기록합니다.
#
#   - kana_tools() / supervisor_tools() / agent_tool_names(agent_name)
#     Kana 하위 agent와 supervisor가 볼 수 있는 tool 목록을 역할별로 조립하고 이름 목록을 제공합니다.
#
#   - propose_group_schedule(...)
#     이전 실습 흐름과의 호환을 위해 남겨 둔 그룹 일정 최종 제안 helper입니다. 현재 핵심 경로는 decide_final_slot입니다.
#
#   - nana_agent(query)
#     supervisor가 개인 업무를 위임할 때 호출하는 tool입니다. 단순 조회는 deterministic lookup으로 처리하고,
#     그 외 요청은 Week 4 tool을 가진 Nana 하위 agent를 실행합니다.
#
#   - kana_agent(query)
#     supervisor가 외부 멤버/그룹 조율 업무를 위임할 때 호출하는 tool입니다. Kana 하위 agent trace에서
#     final_slot_payload와 final_decision_payload를 끌어올려 supervisor가 최종 답변에 사용할 수 있게 합니다.
#
#   - build_langchain_supervisor_agent() / build_week_agent()
#     supervisor agent를 한 번만 만들고 재사용합니다. build_week_agent()는 실행기가 호출하는 표준 entry point입니다.


def week06_system_prompt() -> str:
    """6주차 supervisor agent가 따르는 시스템 프롬프트입니다."""

    return supervisor_system_prompt()


def week06_prompt_parts() -> list[str]:
    """1~6주차 supervisor system prompt 조각을 누적합니다."""

    return [
        *week05_prompt_parts(),
        # TODO: Week 6 supervisor agent system prompt를 작성하세요.
    ]


def nana_prompt_parts() -> list[str]:
    """Week 6 Nana 하위 에이전트 전용 system prompt 조각입니다."""

    return [
        *week04_prompt_parts(),
        # TODO: Week 6 Nana 하위 에이전트 전용 system prompt를 작성하세요.
    ]


def kana_prompt_parts() -> list[str]:
    """Week 6 Kana 하위 에이전트 전용 system prompt 조각입니다."""

    return [
        # TODO: Week 6 Kana 하위 에이전트 전용 system prompt를 작성하세요.
    ]


def nana_system_prompt() -> str:
    return join_system_prompt(nana_prompt_parts())


def kana_system_prompt() -> str:
    return join_system_prompt(kana_prompt_parts())


def supervisor_system_prompt() -> str:
    return join_system_prompt(
        [
            *week06_prompt_parts(),
            # TODO: supervisor 실행 역할에 필요한 최종 system prompt를 작성하세요.
        ]
    )


def _tool_call_names(events: list[dict[str, Any]]) -> list[str]:
    return [event["tool_name"] for event in events if event.get("event") == "tool_call" and event.get("tool_name")]


def extract_langchain_trace(result: dict[str, Any]) -> dict[str, Any]:
    """Week 6 supervisor 실행 결과를 UI trace payload로 변환합니다."""

    events = extract_agent_events(result)
    inner_tool_names: list[str] = []
    final_slot_payload: dict[str, Any] | None = None
    final_decision_payload: dict[str, Any] | None = None
    selected_agent: str | None = None

    for event in events:
        if event.get("event") == "tool_call" and event.get("tool_name") in {"nana_agent", "kana_agent"}:
            selected_agent = event["tool_name"]
        content = event.get("content")
        if isinstance(content, dict):
            inner_tool_names.extend(content.get("inner_tool_names") or [])
            if content.get("final_slot_payload"):
                final_slot_payload = content["final_slot_payload"]
            elif "final_slot" in content:
                final_slot_payload = content
            if content.get("final_decision_payload"):
                final_decision_payload = content["final_decision_payload"]

    return {
        "events": events,
        "supervisor_selected_agent": selected_agent,
        "inner_tool_names": inner_tool_names,
        "final_slot_payload": final_slot_payload,
        "final_decision_payload": final_decision_payload,
    }


def tool_name(tool_object: Any) -> str:
    return getattr(tool_object, "name", getattr(tool_object, "__name__", str(tool_object)))


def _compact_query(query: str) -> str:
    return re.sub(r"\s+", "", query or "")


def _is_direct_personal_schedule_lookup(query: str) -> bool:
    """Week 6 개인 일정 단순 조회는 SQLite를 직접 보게 해 답변 흔들림을 줄입니다."""

    compact = _compact_query(query)
    if "일정" not in compact:
        return False
    if any(term in compact for term in PERSONAL_SCHEDULE_MUTATION_TERMS):
        return False
    if not any(term in compact for term in PERSONAL_SCHEDULE_LOOKUP_TERMS):
        return False
    return any(term in compact for term in ("내", "나", "저장된", "전체", "오늘", "내일", "모레"))


def _date_from_query(query: str) -> tuple[str | None, str | None]:
    """자주 쓰는 한국어 날짜 표현을 SQLite date filter로 바꿉니다."""

    text = query or ""
    base_date = date.fromisoformat(current_app_date_iso())
    if "오늘" in text:
        return base_date.isoformat(), "오늘"
    if "내일" in text:
        return (base_date + timedelta(days=1)).isoformat(), "내일"
    if "모레" in text:
        return (base_date + timedelta(days=2)).isoformat(), "모레"

    iso_match = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", text)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        return date(year, month, day).isoformat(), None

    korean_match = re.search(r"(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일", text)
    if korean_match:
        year_text, month_text, day_text = korean_match.groups()
        year = int(year_text) if year_text else base_date.year
        return date(year, int(month_text), int(day_text)).isoformat(), None

    return None, None


def _format_korean_date(iso_date: str | None) -> str:
    if not iso_date:
        return "날짜 미정"
    try:
        parsed = date.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일"


def _format_schedule_time(row: dict[str, Any]) -> str:
    start_time = row.get("start_time")
    end_time = row.get("end_time")
    if start_time and end_time:
        return f"{start_time}-{end_time}"
    if start_time:
        return str(start_time)
    return "시간 미정"


def _format_schedule_line(row: dict[str, Any]) -> str:
    title = row.get("title") or "제목 없음"
    return f"{_format_korean_date(row.get('date'))} {_format_schedule_time(row)} '{title}'"


def _answer_from_saved_schedule_rows(
    rows: list[dict[str, Any]],
    *,
    date_filter: str | None,
    date_label: str | None,
) -> str:
    if date_filter:
        label = f"{date_label} " if date_label else ""
        date_text = _format_korean_date(date_filter)
        if not rows:
            return f"{label}{date_text}에는 저장된 일정이 없습니다."
        schedule_text = ", ".join(
            f"{_format_schedule_time(row)}에 '{row.get('title') or '제목 없음'}'" for row in rows
        )
        return f"{label}{date_text}에는 {schedule_text} 일정이 있습니다."

    if not rows:
        return "현재 저장된 전체 일정이 없습니다."
    lines = ["현재 저장된 일정은 다음과 같습니다."]
    lines.extend(f"- {_format_schedule_line(row)}" for row in rows)
    return "\n".join(lines)


def _direct_personal_schedule_lookup(query: str) -> dict[str, Any] | None:
    if not _is_direct_personal_schedule_lookup(query):
        return None

    date_filter, date_label = _date_from_query(query)
    lookup_input = SavedScheduleListInput(
        limit=50,
        kind="personal_schedule",
        date_from=date_filter,
        date_to=date_filter,
    )
    args = lookup_input.model_dump()
    payload = json.loads(personal_list_saved_schedules.invoke(args))
    answer = _answer_from_saved_schedule_rows(
        payload.get("schedules") or [],
        date_filter=date_filter,
        date_label=date_label,
    )
    trace = [
        {
            "event": "tool_call",
            "tool_name": "personal_list_saved_schedules",
            "arguments": args,
            "id": "week06_direct_personal_schedule_lookup",
        },
        {
            "event": "tool_result",
            "tool_name": "personal_list_saved_schedules",
            "content": payload,
            "id": "week06_direct_personal_schedule_lookup",
        },
    ]
    return {
        "ok": True,
        "selected_agent": "nana_agent",
        "answer": answer,
        "trace": trace,
        "inner_tool_names": ["personal_list_saved_schedules"],
        "mode": "deterministic_schedule_lookup",
    }


FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION = (
    "수집된 멤버 일정에서 LLM agent가 직접 고른 공통 가능 시간 후보를 검증하고 기록합니다. "
    "이 Python tool은 후보를 계산하거나 nested LLM을 호출하지 않습니다. Kana agent는 먼저 "
    "collect_member_schedules 또는 extract_schedules_from_history 결과의 busy_rows를 읽고, "
    "업무 시간과 요청 날짜 범위 안에서 어떤 busy row와도 overlap/겹치면 안 되는 candidate_slots를 직접 채웁니다. "
    "candidate_slots 각 항목은 date(YYYY-MM-DD), start_time(HH:MM), end_time(HH:MM), "
    "duration_minutes, reason을 포함합니다. busy_rows도 가능하면 앞선 tool output에서 복사해 넣습니다. "
    "이 tool은 date_from/date_to, workday_start/workday_end, duration_minutes, busy_rows와 비교해 "
    "명백히 범위를 벗어나거나 겹치는 후보를 제거한 뒤 candidate_slots payload를 반환합니다. "
    "사용자가 회의 시간을 잡아달라고 했다면 이 결과로 답변하지 말고, 검증된 candidate_slots 중 하나를 골라 "
    "decide_final_slot을 이어서 호출해야 합니다."
)


DECIDE_FINAL_SLOT_DESCRIPTION = (
    "candidate_slots 중 LLM agent가 직접 선택한 최종 회의 시간 payload를 기록합니다. "
    "이 Python tool은 최종 시간을 자동 선택하거나 nested LLM을 호출하지 않습니다. Kana agent는 "
    "find_common_available_slots 결과의 candidate_slots를 읽고 selected_index 또는 selected_slot과 "
    "final_slot('YYYY-MM-DD HH:MM-HH:MM'), needs_agent_selection, reason을 직접 채웁니다. "
    "근거 trace를 위해 find_common_available_slots 결과의 busy_rows, member_names, date_from, date_to도 함께 복사합니다. "
    "후보가 있지만 아직 고르지 않았다면 final_slot은 null, needs_agent_selection은 true로 둡니다. "
    "needs_agent_selection이 false이면 사용자에게 다시 고르라고 묻지 말고 확정된 final_slot으로 답합니다. "
    "최종 답변은 반드시 이 tool이 반환한 final_slot, reason, candidates, candidate_slots를 근거로 작성합니다."
)


class FindCommonAvailableSlotsInput(BaseModel):
    member_names: list[str] = Field(description="공통 가능 시간을 찾아야 하는 외부 멤버 이름 목록")
    date_from: str = Field(description="조회 시작 날짜. ISO datetime이면 날짜 부분만 사용")
    date_to: str = Field(description="조회 종료 날짜. ISO datetime이면 날짜 부분만 사용")
    duration_minutes: int = Field(default=60, ge=30, le=480, description="회의 길이(분)")
    workday_start: str = Field(default="09:00", description="허용 업무 시간 시작 HH:MM")
    workday_end: str = Field(default="18:00", description="허용 업무 시간 종료 HH:MM")
    limit: int = Field(default=5, ge=1, le=20, description="최대 후보 수")
    busy_rows: list[dict[str, Any]] | None = Field(
        default=None,
        description="앞선 일정 조회 tool output에서 복사한 busy_rows. 후보는 이 row들과 overlap/겹치면 안 됩니다.",
    )
    candidate_slots: list[CommonSlotCandidate] = Field(
        default_factory=list,
        description=(
            "LLM agent가 직접 고른 후보 목록. 각 항목은 date, start_time, end_time, "
            "duration_minutes, reason을 포함하고 busy_rows와 겹치면 안 됩니다."
        ),
    )
    llm_reason: str | None = Field(default=None, description="LLM agent가 후보 목록을 고른 전체 이유")


class DecideFinalSlotInput(BaseModel):
    candidate_slots: list[Any] = Field(default_factory=list, description="find_common_available_slots 결과의 후보 목록")
    selected_slot: Any | None = Field(default=None, description="LLM agent가 직접 고른 후보 객체")
    selected_index: int | None = Field(default=None, description="LLM agent가 직접 고른 candidate_slots index")
    final_slot: str | None = Field(
        default=None,
        description="최종 확정 시간 텍스트. 형식은 'YYYY-MM-DD HH:MM-HH:MM'. 미확정이면 null",
    )
    needs_agent_selection: bool | None = Field(
        default=None,
        description="후보 선택이 더 필요하면 true, final_slot을 확정했으면 false",
    )
    member_names: list[str] | None = Field(default=None, description="회의 대상 멤버 목록")
    date_from: str | None = Field(default=None, description="요청 날짜 범위 시작")
    date_to: str | None = Field(default=None, description="요청 날짜 범위 종료")
    duration_minutes: int = Field(default=60, description="회의 길이(분)")
    reason: str | None = Field(default=None, description="최종 선택 또는 보류에 대한 사용자-facing 설명")
    busy_rows: list[dict[str, Any]] | None = Field(default=None, description="최종 결정 근거로 남길 busy_rows")


class ProposeGroupScheduleInput(BaseModel):
    """기존 호환용 그룹 일정 제안 입력입니다."""

    title: str
    member_names: list[str]
    candidate_slots: list[CommonSlotCandidate] = Field(default_factory=list)
    selected_slot: CommonSlotCandidate | None = None
    reason: str | None = None


class AgentQueryInput(BaseModel):
    """하위 에이전트 위임 입력입니다."""

    query: str


def find_common_available_slots_dict(
    member_names: list[str],
    date_from: str,
    date_to: str,
    duration_minutes: int = 60,
    workday_start: str = "09:00",
    workday_end: str = "18:00",
    limit: int = 5,
    busy_rows: list[dict[str, Any]] | None = None,
    candidate_slots: list[dict[str, Any]] | None = None,
    llm_reason: str | None = None,
) -> dict[str, Any]:
    """멤버별 busy-time rows와 LLM이 고른 후보 payload를 검증 결과로 바꿉니다."""

    # TODO: busy_rows를 수집하고 Kana agent가 고른 candidate_slots를 검증 payload로 바꾸세요.
    ...


@tool(description=FIND_COMMON_AVAILABLE_SLOTS_DESCRIPTION, args_schema=FindCommonAvailableSlotsInput)
def find_common_available_slots(
    member_names: list[str],
    date_from: str,
    date_to: str,
    duration_minutes: int = 60,
    workday_start: str = "09:00",
    workday_end: str = "18:00",
    limit: int = 5,
    busy_rows: list[dict[str, Any]] | None = None,
    candidate_slots: list[Any] | None = None,
    llm_reason: str | None = None,
) -> str:
    """수집된 멤버 일정에서 LLM이 직접 고른 공통 가능 후보 시간을 검증합니다."""

    # TODO: busy_rows와 candidate_slots를 검증하고 top-level final_slot/reason/candidates를 포함해 반환하세요.
    ...


@tool(description=DECIDE_FINAL_SLOT_DESCRIPTION, args_schema=DecideFinalSlotInput)
def decide_final_slot(
    candidate_slots: list[Any] | None = None,
    selected_slot: Any | None = None,
    selected_index: int | None = None,
    final_slot: str | None = None,
    needs_agent_selection: bool | None = None,
    member_names: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    duration_minutes: int = 60,
    reason: str | None = None,
    busy_rows: list[dict[str, Any]] | None = None,
) -> str:
    """LLM이 직접 고른 후보/최종 시간을 course repo payload로 기록합니다."""

    # TODO: Kana agent가 고른 selected_index/final_slot을 decide_final_slot_payload(...) 계약에 맞춰 기록하세요.
    ...


def kana_tools() -> list[Any]:
    return [
        extract_schedule_request,
        search_previous_conversations,
        load_conversation_messages,
        extract_schedules_from_history,
        list_shared_schedules,
        collect_member_schedules,
        find_common_available_slots,
        decide_final_slot,
    ]


def supervisor_tools() -> list[Any]:
    return [nana_agent, kana_agent]


def agent_tool_names(agent_name: str) -> list[str]:
    if agent_name == "nana_agent":
        return [tool_name(item) for item in week04_tools()]
    if agent_name == "kana_agent":
        return [tool_name(item) for item in kana_tools()]
    if agent_name == "supervisor":
        return [tool_name(item) for item in supervisor_tools()]
    return []


@tool(args_schema=ProposeGroupScheduleInput)
def propose_group_schedule(
    title: str,
    member_names: list[str],
    candidate_slots: list[Any] | None = None,
    selected_slot: Any | None = None,
    reason: str | None = None,
) -> str:
    """Kana가 고른 후보 시간으로 최종 그룹 일정 결정 페이로드를 만듭니다."""

    slots = [slot.model_dump() if hasattr(slot, "model_dump") else slot for slot in candidate_slots or []]
    selected = selected_slot.model_dump() if hasattr(selected_slot, "model_dump") else selected_slot
    payload = {
        "title": title,
        "members": normalize_external_member_names(member_names),
        "selected_slot": selected,
        "status": "confirmed" if selected else "needs_manual_review",
        "reason": reason,
        "candidate_slots": slots,
    }
    return json.dumps({"ok": True, "tool_name": "propose_group_schedule", "final_decision": payload}, ensure_ascii=False)


@tool(args_schema=AgentQueryInput)
def nana_agent(query: str) -> str:
    """개인 일정과 개인 RAG 작업을 프롬프트 기반 Nana 하위 에이전트에게 위임합니다."""

    # TODO: Week 4 도구를 가진 Nana 하위 agent를 실행하고 answer/trace/inner_tool_names를 반환하세요.
    ...


@tool(args_schema=AgentQueryInput)
def kana_agent(query: str) -> str:
    """그룹 일정 종합 작업을 프롬프트 기반 Kana 하위 에이전트에게 위임합니다."""

    # TODO: Kana 하위 agent를 실행하고 trace에서 final_slot_payload/final_decision_payload를 끌어올리세요.
    ...


def build_langchain_supervisor_agent() -> object:
    """nana_agent와 kana_agent 위임 도구만 노출하는 LangChain v1 슈퍼바이저입니다."""

    global _SUPERVISOR_AGENT
    if _SUPERVISOR_AGENT is None:
        _SUPERVISOR_AGENT = create_agent(
            model=chat_model(),
            tools=supervisor_tools(),
            system_prompt=supervisor_system_prompt(),
        )
    return _SUPERVISOR_AGENT


def build_week_agent() -> object:
    """active-week registry가 호출하는 표준 Week agent builder입니다."""

    return build_langchain_supervisor_agent()
