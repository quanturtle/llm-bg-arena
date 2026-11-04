"""Which revision of the prompt templates a match was played with.

PROMPT_VERSION names the text a model sees apart from the game's own content:
the message layout, the answer instructions, the tool definitions and the retry
feedback. Game text (rules, observations, why a move is illegal) is not part of
it. Bump the version by hand when the templates change and pin the new
fingerprint in PROMPT_FINGERPRINTS. `prompt_fingerprint` hashes the templates
rendered for a fixed example request, and a test fails when they change without
a new version.
"""

from functools import cache

from boardgames.agents.base import DecisionRequest
from boardgames.core import (
    Decision,
    Event,
    FlatActionSpace,
    JsonValue,
    Observation,
    PlayerId,
    json_digest,
)
from boardgames.llm.model import Completion, Usage, tools_json
from boardgames.llm.parsing import (
    Rejected,
    parse_reply,
    parse_text,
    parse_tool_arguments,
)
from boardgames.llm.prompting import (
    TOOL_NAME,
    OutputMode,
    PromptSettings,
    build_prompt,
    retry_messages,
    submit_tool,
)
from boardgames.llm.tools import NO_TOOL_NUDGE, game_tools

PROMPT_VERSION = 1
# each version's fingerprint; a new version adds a line, old ones stay for reference
PROMPT_FINGERPRINTS = {1: "a44ddfb1f9b6"}
OUTPUT_MODES: tuple[OutputMode, ...] = ("tool", "text", "tools")


class ExampleActions:
    """Placeholder notation for the example request: an action is its own text."""

    def format_action(self, action: str) -> str:
        return action

    def parse_action(self, text: str) -> str:
        return text

    def describe_action(self, observation: Observation, action: str) -> str:
        return f"{{description of {action}}}"


@cache
def prompt_fingerprint() -> str:
    """Short hash of the prompt templates rendered for the example request."""
    return json_digest(rendered_templates())[:12]


def rendered_templates() -> dict[str, JsonValue]:
    """Every template a model can see, filled with placeholders instead of game text."""
    request = example_request()
    rendered: dict[str, JsonValue] = {}
    for mode in OUTPUT_MODES:
        prompt = build_prompt(request, "{notes}", PromptSettings(output_mode=mode))
        rendered[f"{mode} messages"] = [m.content for m in prompt.messages]
    patterns = build_prompt(request, "{notes}", PromptSettings(listing_limit=1))
    rendered["pattern listing"] = [m.content for m in patterns.messages]
    tools_mode = PromptSettings(output_mode="tools")
    rendered["tools"] = tools_json((submit_tool(1500), *game_tools(tools_mode)))
    rendered["retry"] = [m.content for m in retry_messages((), "{reply}", "{feedback}")]
    rendered["no tool nudge"] = NO_TOOL_NUDGE
    rendered["format feedback"] = format_feedback()
    return rendered


def example_request() -> DecisionRequest[str]:
    """A decision with two actions and one event, every game text a placeholder."""
    player = PlayerId(0)
    return DecisionRequest(
        game_id="{game}",
        decision=Decision(player, "{kind}", "{decision}"),
        observation=Observation(player, {}),
        observation_text="{state}",
        actions=FlatActionSpace(["{action 1}", "{action 2}"], str),
        recent_events=(Event("{kind}", "{event}"),),
        rules="{rules}",
        action_text=ExampleActions(),
    )


def format_feedback() -> list[JsonValue]:
    """The fixed feedback for replies whose answer cannot be read."""
    text_reply = Completion(
        text="{reply without an answer}\n{second line}",
        tool_calls=(),
        usage=Usage(0, 0),
        cost_usd=None,
    )
    rejections = [
        parse_tool_arguments("{"),
        parse_tool_arguments("[]"),
        parse_tool_arguments("{}"),
        parse_text("Final Answer:"),
        parse_text(text_reply.text),
        parse_reply(text_reply, TOOL_NAME),
    ]
    return [r.feedback for r in rejections if isinstance(r, Rejected)]
