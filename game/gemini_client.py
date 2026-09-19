"""Google Gemini との通信ラッパー。OpenAI/Claudeと同じインターフェースを提供する。

2026年6月にGoogleのデフォルトAPIとなった Interactions API
(`client.interactions.create`) を使い、JSON Schemaで構造化出力を強制する。
ストリーミングイベントの型名は変わりやすいので、途中経過の解釈に失敗した
場合は非ストリーミング呼び出しにフォールバックする。

【注意】このAPIはClaude Code側の学習データより新しいため、実際に動かして
初回にエラーが出た場合はエラーメッセージを添えて相談してほしい。
"""

from __future__ import annotations

import json
import os
import time
from typing import Iterator

from google import genai

from game.ai_common import AICallError, AIResult, StreamUpdate
from game.indicators import ModeDef
from game.prompts import (
    HISTORICAL_EVENT_SCHEMA,
    POLICY_EVAL_SCHEMA,
    build_historical_event_messages,
    build_policy_eval_messages,
)

RECOMMENDED_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]


def list_available_models() -> list[str]:
    return RECOMMENDED_MODELS


def _get_client() -> "genai.Client":
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise AICallError("GEMINI_API_KEYが設定されていません。サイドバーでAPIキーを入力してください。")
    return genai.Client(api_key=api_key)


def _response_format(schema: dict) -> dict:
    return {"type": "text", "mime_type": "application/json", "schema": schema}


def _extract_usage(usage) -> tuple[int | None, int | None]:
    if usage is None:
        return None, None
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    return input_tokens, output_tokens


def _fallback_sync_call(client, model: str, messages: list[dict], schema: dict):
    interaction = client.interactions.create(model=model, input=messages, response_format=_response_format(schema))
    input_tokens, output_tokens = _extract_usage(getattr(interaction, "usage", None))
    return interaction.output_text, input_tokens, output_tokens


def _stream_json(model: str, messages: list[dict], schema: dict) -> Iterator[StreamUpdate]:
    client = _get_client()
    start = time.perf_counter()
    accumulated = ""
    input_tokens: int | None = None
    output_tokens: int | None = None

    try:
        stream = client.interactions.create(
            model=model, input=messages, response_format=_response_format(schema), stream=True,
        )
        for event in stream:
            etype = getattr(event, "event_type", None) or getattr(event, "type", None)
            if etype == "step.delta":
                delta = getattr(event, "delta", None)
                if delta is not None and getattr(delta, "type", None) == "text":
                    accumulated += getattr(delta, "text", "")
                    yield StreamUpdate(partial_content=accumulated, elapsed_seconds=time.perf_counter() - start)
            elif etype == "interaction.completed":
                usage = getattr(event, "usage", None) or getattr(getattr(event, "interaction", None), "usage", None)
                input_tokens, output_tokens = _extract_usage(usage)
    except Exception as e:  # noqa: BLE001 - ストリーミング周りのSDK仕様変更に備えて広めに捕捉
        raise AICallError(f"Gemini呼び出しに失敗しました({model}): {e}") from e

    if not accumulated.strip():
        try:
            accumulated, input_tokens, output_tokens = _fallback_sync_call(client, model, messages, schema)
        except Exception as e:  # noqa: BLE001
            raise AICallError(f"Gemini呼び出しに失敗しました({model}): {e}") from e
        yield StreamUpdate(partial_content=accumulated, elapsed_seconds=time.perf_counter() - start)

    elapsed = time.perf_counter() - start
    try:
        data = json.loads(accumulated)
    except json.JSONDecodeError as e:
        raise AICallError(
            f"モデル({model})の出力がJSONとして解釈できませんでした: {e}\n---\n{accumulated}"
        ) from e

    result = AIResult(
        data=data, raw_content=accumulated, elapsed_seconds=elapsed, model=model, provider="gemini",
        input_tokens=input_tokens, output_tokens=output_tokens,
    )
    yield StreamUpdate(partial_content=accumulated, elapsed_seconds=elapsed, done=True, result=result)


def stream_policy_evaluation(
    model: str, mode: ModeDef, calendar_year: int, indicator_snapshot: dict[str, float], policy_text: str,
) -> Iterator[StreamUpdate]:
    messages = build_policy_eval_messages(mode, calendar_year, indicator_snapshot, policy_text)
    yield from _stream_json(model, messages, POLICY_EVAL_SCHEMA)


def stream_historical_event(
    model: str, mode: ModeDef, calendar_year: int, indicator_snapshot: dict[str, float],
    event_title: str, event_description: str,
) -> Iterator[StreamUpdate]:
    messages = build_historical_event_messages(
        mode, calendar_year, indicator_snapshot, event_title, event_description
    )
    yield from _stream_json(model, messages, HISTORICAL_EVENT_SCHEMA)
