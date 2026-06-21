from __future__ import annotations

import json
from typing import Any


def todo_payload(
    *,
    week: int,
    tool_name: str,
    message: str,
    received: dict[str, Any] | None = None,
    **expected_payload: Any,
) -> dict[str, Any]:
    """Return an executable placeholder payload for student implementation tasks."""

    return {
        "ok": False,
        "student_todo": True,
        "week": week,
        "tool_name": tool_name,
        "message": message,
        "received": received or {},
        **expected_payload,
    }


def todo_json(
    *,
    week: int,
    tool_name: str,
    message: str,
    received: dict[str, Any] | None = None,
    **expected_payload: Any,
) -> str:
    """Serialize a student TODO payload for LangChain tool results."""

    return json.dumps(
        todo_payload(
            week=week,
            tool_name=tool_name,
            message=message,
            received=received,
            **expected_payload,
        ),
        ensure_ascii=False,
    )
