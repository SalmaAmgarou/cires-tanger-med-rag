"""Understand step — GPT-4o-mini detects intent, language, and rewrites the query.

Fast (~300ms) and cheap (~$0.0003 per turn).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import openai

from backend.ai.schemas import ConversationState, UnderstandResult
from backend.core.config import settings

logger = logging.getLogger(__name__)

_UNDERSTAND_PROMPT = (Path(__file__).parent / "prompts" / "understand.txt").read_text(encoding="utf-8")

_UNDERSTAND_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "understand_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "greeting",
                        "question",
                        "follow_up",
                        "clarification",
                        "off_topic",
                        "human_request",
                    ],
                },
                "language": {"type": "string", "enum": ["fr", "en"]},
                "search_query": {"type": "string"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["intent", "language", "search_query", "confidence", "reasoning"],
            "additionalProperties": False,
        },
    },
}


async def understand(
    user_message: str,
    state: ConversationState,
    recent_messages: list[dict[str, str]],
) -> tuple[UnderstandResult, int]:
    """Detect intent + language and rewrite the query for retrieval.

    Args:
        user_message: latest user message.
        state: accumulated conversation state.
        recent_messages: last 6-8 messages, [{"role": ..., "content": ...}].
    """
    t0 = time.time()

    state_json = state.model_dump_json(indent=2)
    history_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in recent_messages[-6:]
    )

    user_prompt = (
        f"Current conversation state:\n{state_json}\n\n"
        f"Recent conversation:\n{history_text or '(no prior turns)'}\n\n"
        f"New user message: {user_message}"
    )

    oai = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        completion = await oai.chat.completions.create(
            model=settings.understand_model,
            messages=[
                {"role": "system", "content": _UNDERSTAND_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=_UNDERSTAND_SCHEMA,
            temperature=0.1,
            max_tokens=settings.understand_max_tokens,
        )
        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        result = UnderstandResult(**parsed)
    except Exception as e:
        logger.error("Understand step failed: %s", e)
        # Fallback: use raw message as query, guess language
        is_french = any(c in user_message for c in "àâäçéèêëîïôœùûüÿ") or any(
            w in user_message.lower() for w in (" le ", " la ", " les ", " des ", " du ", " quel ", " comment ", " bonjour")
        )
        result = UnderstandResult(
            intent="question",
            language="fr" if is_french else "en",
            search_query=user_message,
            confidence=0.3,
            reasoning=f"Understand fallback after error: {e}",
        )

    duration_ms = int((time.time() - t0) * 1000)
    return result, duration_ms


def update_state(state: ConversationState, understood: UnderstandResult) -> ConversationState:
    """Merge understanding into the conversation state."""
    if understood.language:
        state.language = understood.language
    if understood.intent in ("question", "follow_up", "clarification"):
        state.pending_question = ""
    return state
