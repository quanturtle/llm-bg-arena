"""Response cache around any ChatModel, for cheap reruns during development.

The key covers the model settings (including seed), every message and the tool,
so any prompt change misses. Cached replies cost nothing and are marked cached.
"""

import json
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
        path = self._path(key)
        if not path.exists():
            return None
        value: JsonObject = json.loads(path.read_text(encoding="utf-8"))
        return value

    def put(self, key: str, value: JsonObject) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
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
        if stored is not None:
            return replace(completion_from_json(stored), cost_usd=0.0, is_cached=True)
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


def completion_from_json(stored: JsonObject) -> Completion:
    """Completion from its stored form."""
    text = stored["text"]
    calls = stored["tool_calls"]
    prompt_tokens = stored["prompt_tokens"]
    completion_tokens = stored["completion_tokens"]
    reasoning = stored.get("reasoning")
    if not (
        isinstance(text, str)
        and isinstance(calls, list)
        and isinstance(prompt_tokens, int)
        and isinstance(completion_tokens, int)
        and (reasoning is None or isinstance(reasoning, str))
    ):
        raise TypeError(f"malformed cached completion: {stored!r}")
    return Completion(
        text=text,
        tool_calls=tuple(tool_call_from_json(call) for call in calls),
        usage=Usage(prompt_tokens, completion_tokens),
        cost_usd=None,
        reasoning=reasoning,
    )


def tool_call_from_json(stored: JsonValue) -> ToolCall:
    """A tool call from its stored form."""
    if not isinstance(stored, dict):
        raise TypeError(f"malformed cached tool call: {stored!r}")
    call_id, name, arguments = stored["id"], stored["name"], stored["arguments"]
    if not (
        isinstance(call_id, str)
        and isinstance(name, str)
        and isinstance(arguments, str)
    ):
        raise TypeError(f"malformed cached tool call: {stored!r}")
    return ToolCall(call_id, name, arguments)
