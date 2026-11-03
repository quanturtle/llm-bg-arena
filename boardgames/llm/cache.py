"""Response cache around any ChatModel, for cheap reruns during development.

The key covers the model settings (including seed), every message and the tool,
so any prompt change misses. Cached replies cost nothing and are marked cached.
"""

import json
import os
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from boardgames.core import JsonObject, JsonValue, json_digest
from boardgames.llm.model import (
    ChatModel,
    Completion,
    Message,
    ModelSettings,
    ToolCall,
    ToolChoice,
    ToolSpec,
    Usage,
    messages_json,
    tool_choice_json,
    tools_json,
)


class ResponseStore(Protocol):
    def get(self, key: str) -> JsonObject | None:
        """The stored value, or None."""
        ...

    def put(self, key: str, value: JsonObject) -> None:
        """Store a value; storing the same key again overwrites it."""
        ...


class DirectoryResponseStore:
    """One JSON file per key under `root`, sharded by the first two key characters."""

    def __init__(self, root: Path) -> None:
        self._root = root
        return

    def get(self, key: str) -> JsonObject | None:
        """The stored object, or None when the file is missing or not a JSON object."""
        path = self._path(key)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def put(self, key: str, value: JsonObject) -> None:
        """Write through a temporary name, so a cut-off write leaves no file behind."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        os.replace(temporary, path)
        return

    def _path(self, key: str) -> Path:
        return self._root / key[:2] / f"{key}.json"


class CachedChatModel:
    def __init__(self, inner: ChatModel, store: ResponseStore) -> None:
        self._inner = inner
        self._store = store
        return

    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tools: Sequence[ToolSpec],
        tool_choice: ToolChoice,
    ) -> Completion:
        key = cache_key(messages, settings, tools, tool_choice)
        stored = self._store.get(key)
        cached = None if stored is None else completion_from_json(stored)
        if cached is not None:
            return replace(cached, cost_usd=0.0, is_cached=True)
        completion = await self._inner.complete(messages, settings, tools, tool_choice)
        self._store.put(key, completion_json(completion))
        return completion


def cache_key(
    messages: Sequence[Message],
    settings: ModelSettings,
    tools: Sequence[ToolSpec],
    tool_choice: ToolChoice,
) -> str:
    """Digest of everything that shapes the reply."""
    return json_digest(
        {
            "settings": settings.to_json(),
            "messages": messages_json(messages),
            "tools": tools_json(tools),
            "tool_choice": tool_choice_json(tool_choice) if tools else None,
        }
    )


def completion_json(completion: Completion) -> dict[str, JsonValue]:
    """Stored form of a completion."""
    return {
        "text": completion.text,
        "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in completion.tool_calls
        ],
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
        "cost_usd": completion.cost_usd,
        "reasoning": completion.reasoning,
    }


def completion_from_json(stored: JsonObject) -> Completion | None:
    """Completion from its stored form; a malformed entry gives None, a cache miss."""
    text = stored.get("text")
    calls = stored.get("tool_calls")
    prompt_tokens = stored.get("prompt_tokens")
    completion_tokens = stored.get("completion_tokens")
    reasoning = stored.get("reasoning")
    if not (
        isinstance(text, str)
        and isinstance(calls, list)
        and isinstance(prompt_tokens, int)
        and isinstance(completion_tokens, int)
        and (reasoning is None or isinstance(reasoning, str))
    ):
        return None
    tool_calls = [tool_call_from_json(call) for call in calls]
    if any(call is None for call in tool_calls):
        return None
    return Completion(
        text=text,
        tool_calls=tuple(call for call in tool_calls if call is not None),
        usage=Usage(prompt_tokens, completion_tokens),
        cost_usd=None,
        reasoning=reasoning,
    )


def tool_call_from_json(stored: JsonValue) -> ToolCall | None:
    """A tool call from its stored form, or None when malformed."""
    if not isinstance(stored, dict):
        return None
    call_id = stored.get("id")
    name = stored.get("name")
    arguments = stored.get("arguments")
    if not (
        isinstance(call_id, str)
        and isinstance(name, str)
        and isinstance(arguments, str)
    ):
        return None
    return ToolCall(call_id, name, arguments)
