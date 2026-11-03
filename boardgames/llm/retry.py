"""Retry with exponential backoff around any ChatModel, for transient API failures.

API retries are counted apart from illegal-move retries, which the agent handles.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace

from boardgames.llm.model import (
    ChatModel,
    Completion,
    Message,
    ModelSettings,
    ModelUnavailableError,
    ToolChoice,
    ToolSpec,
    TransientModelError,
)

type Sleep = Callable[[float], Awaitable[None]]


class RetryingChatModel:
    """Retries TransientModelError up to `max_attempts` calls, waiting 1s, 2s, 4s..."""

    def __init__(
        self,
        inner: ChatModel,
        *,
        max_attempts: int = 4,
        base_delay_seconds: float = 1.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._inner = inner
        self._max_attempts = max_attempts
        self._base_delay = base_delay_seconds
        self._sleep = sleep
        return

    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tools: Sequence[ToolSpec],
        tool_choice: ToolChoice,
    ) -> Completion:
        failures: list[str] = []
        for attempt in range(self._max_attempts):
            try:
                completion = await self._inner.complete(
                    messages, settings, tools, tool_choice
                )
            except TransientModelError as error:
                failures.append(str(error))
                if attempt + 1 < self._max_attempts:
                    await self._sleep(self._base_delay * 2**attempt)
                continue
            return replace(completion, api_retries=completion.api_retries + attempt)
        raise ModelUnavailableError(
            f"{settings.model} failed {self._max_attempts} times; last: {failures[-1]}"
        )
