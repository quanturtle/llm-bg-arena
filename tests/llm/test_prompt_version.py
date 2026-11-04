from boardgames.llm.prompt_version import (
    PROMPT_FINGERPRINTS,
    PROMPT_VERSION,
    prompt_fingerprint,
)


def test_the_prompt_version_pins_the_template_fingerprint() -> None:
    """Changed templates need a new version and its pinned fingerprint."""
    assert PROMPT_FINGERPRINTS[PROMPT_VERSION] == prompt_fingerprint()
    return
