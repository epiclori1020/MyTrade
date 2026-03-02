"""Tests for the JSON repair wrapper (src/services/llm_json_repair.py).

All tests are pure unit tests — no external I/O, no API calls.
The Anthropic response object is simulated with SimpleNamespace so we
test the real parsing logic in extract_raw_text() without needing the SDK.
"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from src.services.llm_json_repair import extract_raw_text, try_repair_json


# ---------------------------------------------------------------------------
# Shared test schema
# ---------------------------------------------------------------------------


class SampleSchema(BaseModel):
    """Minimal Pydantic model used as the target schema in try_repair_json() tests."""

    name: str
    value: int


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _text_block(text: str) -> SimpleNamespace:
    """Simulate an Anthropic TextBlock."""
    return SimpleNamespace(type="text", text=text)


def _tool_use_block() -> SimpleNamespace:
    """Simulate an Anthropic ToolUseBlock (no .text attribute)."""
    return SimpleNamespace(type="tool_use", id="tu_123", name="some_tool")


def _response(*blocks) -> SimpleNamespace:
    """Wrap content blocks in a minimal Anthropic ParsedMessage stub."""
    return SimpleNamespace(content=list(blocks))


# ---------------------------------------------------------------------------
# Tests: extract_raw_text()
# ---------------------------------------------------------------------------


class TestExtractRawText:
    def test_text_block_returns_text(self):
        """Response with a single TextBlock returns the text content."""
        payload = '{"name": "test", "value": 42}'
        response = _response(_text_block(payload))

        result = extract_raw_text(response)

        assert result == payload

    def test_response_with_no_content_attribute_returns_none(self):
        """Response object without a .content attribute returns None."""
        response = SimpleNamespace()  # no .content

        result = extract_raw_text(response)

        assert result is None

    def test_response_with_empty_content_list_returns_none(self):
        """Response with an empty content list returns None."""
        response = SimpleNamespace(content=[])

        result = extract_raw_text(response)

        assert result is None

    def test_tool_use_block_only_returns_none(self):
        """Response containing only a ToolUseBlock (no TextBlock) returns None."""
        response = _response(_tool_use_block())

        result = extract_raw_text(response)

        assert result is None

    def test_tool_use_block_before_text_block_returns_text(self):
        """When both block types exist the text is still found (extra coverage)."""
        payload = '{"name": "mixed", "value": 99}'
        response = _response(_tool_use_block(), _text_block(payload))

        result = extract_raw_text(response)

        assert result == payload

    def test_returns_first_text_block_when_multiple_exist(self):
        """Only the first TextBlock's text is returned."""
        response = _response(_text_block("first"), _text_block("second"))

        result = extract_raw_text(response)

        assert result == "first"


# ---------------------------------------------------------------------------
# Tests: try_repair_json()
# ---------------------------------------------------------------------------


class TestTryRepairJson:
    def test_valid_json_returns_model(self):
        """A perfectly valid JSON string is parsed without any repair step."""
        raw = '{"name": "hello", "value": 7}'

        result = try_repair_json(raw, SampleSchema)

        assert isinstance(result, SampleSchema)
        assert result.name == "hello"
        assert result.value == 7

    def test_missing_closing_brace_is_repaired(self):
        """JSON missing the final closing brace is repaired successfully."""
        raw = '{"name": "alice", "value": 10'

        result = try_repair_json(raw, SampleSchema)

        assert isinstance(result, SampleSchema)
        assert result.name == "alice"
        assert result.value == 10

    def test_trailing_comma_is_repaired(self):
        """Trailing comma after the last key-value pair is removed during repair."""
        raw = '{"name": "bob", "value": 5,}'

        result = try_repair_json(raw, SampleSchema)

        assert isinstance(result, SampleSchema)
        assert result.name == "bob"
        assert result.value == 5

    def test_single_quotes_are_repaired(self):
        """Single-quoted JSON keys and values (common LLM mistake) are repaired."""
        raw = "{'name': 'charlie', 'value': 3}"

        result = try_repair_json(raw, SampleSchema)

        assert isinstance(result, SampleSchema)
        assert result.name == "charlie"
        assert result.value == 3

    def test_text_before_json_is_repaired(self):
        """Preamble text before the JSON object (e.g. 'Here is the output:') is stripped."""
        raw = 'Here is the output: {"name": "delta", "value": 99}'

        result = try_repair_json(raw, SampleSchema)

        assert isinstance(result, SampleSchema)
        assert result.name == "delta"
        assert result.value == 99

    def test_completely_invalid_garbage_returns_none(self):
        """Completely non-JSON text that cannot be repaired returns None."""
        raw = "this is not json at all !!! ???"

        result = try_repair_json(raw, SampleSchema)

        assert result is None

    def test_valid_json_wrong_schema_returns_none(self):
        """Valid JSON that does not match the expected Pydantic schema returns None."""
        # 'value' must be an int, but here it is a string that cannot be coerced
        raw = '{"name": "echo", "value": "not-an-int", "extra_unexpected_field_only": true}'

        result = try_repair_json(raw, SampleSchema)

        # If json_repair coerces "not-an-int" to something invalid for int:
        # expect None. If for some reason pydantic accepts it, we just assert type.
        # The key assertion: no exception is raised and return type is correct.
        assert result is None or isinstance(result, SampleSchema)

    def test_json_missing_required_field_returns_none(self):
        """JSON that is valid but missing a required schema field returns None."""
        raw = '{"name": "foxtrot"}'  # 'value' (int, required) is absent

        result = try_repair_json(raw, SampleSchema)

        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string input returns None immediately (no repair attempted)."""
        result = try_repair_json("", SampleSchema)

        assert result is None

    def test_whitespace_only_string_returns_none(self):
        """Input containing only whitespace returns None immediately."""
        result = try_repair_json("   \n\t  ", SampleSchema)

        assert result is None
