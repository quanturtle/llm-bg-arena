from boardgames.llm.catalog import parse_catalog

LISTING = {
    "data": [
        {
            "id": "openai/gpt-x",
            "name": "GPT X",
            "supported_parameters": ["verbosity", "reasoning", "tools"],
            "reasoning": {
                "mandatory": True,
                "supported_efforts": ["high", "none", "turbo", "minimal"],
                "default_effort": "high",
            },
            "top_provider": {"max_completion_tokens": 1000},
            "default_parameters": {"temperature": None},
        },
        {
            "id": "plain/model",
            "supported_parameters": ["temperature", "tools"],
            "reasoning": None,
            "default_parameters": {"temperature": 0.3},
        },
    ]
}


def test_catalog_keeps_known_efforts_least_first_and_marks_plain_models() -> None:
    models = parse_catalog(LISTING)
    reasoning = models["openai/gpt-x"].reasoning
    assert reasoning is not None
    assert (reasoning.is_mandatory, reasoning.efforts) == (True, ["minimal", "high"])
    assert models["openai/gpt-x"].max_output_tokens == 1000
    plain = models["plain/model"]
    assert (plain.reasoning, plain.default_temperature) == (None, 0.3)
    assert plain.name == "plain/model"
    return
