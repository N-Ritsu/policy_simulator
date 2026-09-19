"""OpenAI(GPT)との通信ラッパー。Gemini/Claudeと同じインターフェースを提供する。

Responses API (`client.responses.create`) を使い、JSON Schemaで構造化出力を
強制する。ストリーミングイベントの型名は変わりやすいので、途中経過の解釈に
失敗した場合は非ストリーミング呼び出しにフォールバックする。

【注意】このAPI(Responses API)は2026年時点の公式ドキュメントを確認して実装
しているが、Claude Code側の学習データより新しいため、実際に動かして初回に
エラーが出た場合はエラーメッセージを添えて相談してほしい。
"""

from __future__ import annotations

import json
import os
import time
from typing import Iterator

from openai import OpenAI

from game.ai_common import AICallError, AIResult, StreamUpdate
from game.indicators import ModeDef
from game.prompts import (
    HISTORICAL_EVENT_SCHEMA,
    POLICY_EVAL_SCHEMA,
    build_historical_event_messages,
    build_policy_eval_messages,
)

# 2026年時点でAPI経由での利用が確認できているモデルの目安(価格帯で選べるように)
RECOMMENDED_MODELS = [
    "gpt-5.6-terra",
    "gpt-5.1",
    "gpt-5.6-luna",
    "gpt-5-nano",
    "gpt-5.5",
]


def list_available_models() -> list[str]:
    return RECOMMENDED_MODELS


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise AICallError("OPENAI_API_KEYが設定されていません。サイドバーでAPIキーを入力してください。")
    return OpenAI(api_key=api_key)


def _text_format(schema: dict, schema_name: str) -> dict:
    return {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}}


def _extract_usage(usage) -> tuple[int | None, int | None]:
    if usage is None:
        return None, None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    return input_tokens, output_tokens


def _fallback_sync_call(client: OpenAI, model: str, messages: list[dict], schema: dict, schema_name: str):
    response = client.responses.create(model=model, input=messages, text=_text_format(schema, schema_name))
    input_tokens, output_tokens = _extract_usage(getattr(response, "usage", None))
    return response.output_text, input_tokens, output_tokens


def _stream_json(model: str, messages: list[dict], schema: dict, schema_name: str) -> Iterator[StreamUpdate]:
    client = _get_client()
    start = time.perf_counter()
    accumulated = ""
    input_tokens: int | None = None
    output_tokens: int | None = None

    try:
        stream = client.responses.create(
            model=model, input=messages, text=_text_format(schema, schema_name), stream=True,
        )
        for event in stream:
            etype = getattr(event, "type", None)
            if etype == "response.output_text.delta":
                accumulated += getattr(event, "delta", "")
                yield StreamUpdate(partial_content=accumulated, elapsed_seconds=time.perf_counter() - start)
            elif etype == "response.completed":
                input_tokens, output_tokens = _extract_usage(getattr(event.response, "usage", None))
    except Exception as e:  # noqa: BLE001 - ストリーミング周りのSDK仕様変更に備えて広めに捕捉
        raise AICallError(f"OpenAI呼び出しに失敗しました({model}): {e}") from e

    if not accumulated.strip():
        # ストリーミングイベントの解釈に失敗した場合の保険として非ストリーミングで取り直す
        try:
            accumulated, input_tokens, output_tokens = _fallback_sync_call(client, model, messages, schema, schema_name)
        except Exception as e:  # noqa: BLE001
            raise AICallError(f"OpenAI呼び出しに失敗しました({model}): {e}") from e
        yield StreamUpdate(partial_content=accumulated, elapsed_seconds=time.perf_counter() - start)

    elapsed = time.perf_counter() - start
    try:
        data = json.loads(accumulated)
    except json.JSONDecodeError as e:
        raise AICallError(
            f"モデル({model})の出力がJSONとして解釈できませんでした: {e}\n---\n{accumulated}"
        ) from e

    result = AIResult(
        data=data, raw_content=accumulated, elapsed_seconds=elapsed, model=model, provider="openai",
        input_tokens=input_tokens, output_tokens=output_tokens,
    )
    yield StreamUpdate(partial_content=accumulated, elapsed_seconds=elapsed, done=True, result=result)


def stream_policy_evaluation(
    model: str, mode: ModeDef, calendar_year: int, indicator_snapshot: dict[str, float], policy_text: str,
) -> Iterator[StreamUpdate]:
    messages = build_policy_eval_messages(mode, calendar_year, indicator_snapshot, policy_text)
    yield from _stream_json(model, messages, POLICY_EVAL_SCHEMA, "policy_evaluation")


def stream_historical_event(
    model: str, mode: ModeDef, calendar_year: int, indicator_snapshot: dict[str, float],
    event_title: str, event_description: str,
) -> Iterator[StreamUpdate]:
    messages = build_historical_event_messages(
        mode, calendar_year, indicator_snapshot, event_title, event_description
    )
    yield from _stream_json(model, messages, HISTORICAL_EVENT_SCHEMA, "historical_event")
