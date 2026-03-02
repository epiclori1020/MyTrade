"""JSON Repair wrapper for malformed LLM outputs.

When messages.parse() returns parsed_output=None, the raw text content
may contain almost-valid JSON that can be repaired and validated against
the Pydantic schema.

Uses the json_repair library (pip install json-repair).
"""

import logging

import json_repair as jr
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def extract_raw_text(response) -> str | None:
    """Extract text content from Anthropic ParsedMessage response.

    Iterates over response.content and finds the TextBlock
    (block.type == "text"). Returns block.text, or None if no
    text block found.
    """
    if not hasattr(response, "content") or not response.content:
        return None

    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", None)

    return None


def try_repair_json(raw_text: str, schema: type[BaseModel]) -> BaseModel | None:
    """Attempt to repair malformed JSON and validate against Pydantic schema.

    Returns:
        Pydantic model instance if repair + validation succeeds, None otherwise.
    """
    if not raw_text or not raw_text.strip():
        return None

    try:
        repaired = jr.repair_json(raw_text)
        if not repaired:
            return None
        return schema.model_validate_json(repaired)
    except ValidationError as exc:
        logger.debug("JSON repair: repaired JSON failed schema validation: %s", exc)
        return None
    except Exception as exc:
        logger.debug("JSON repair: unexpected error: %s", exc)
        return None
