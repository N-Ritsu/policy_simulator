"""Claude (Anthropic API) との通信ラッパー。OpenAI/Geminiと同じインターフェースを提供する。

Messages APIのストリーミング + 構造化出力(output_config.format)を使う。
Claude Opus 5 は安全分類器で応答が拒否されることがあるため、拒否時に別モデルへ
サーバー側で再実行させる fallbacks="default" を有効にしている(他モデルでは不要)。
"""

from __future__ import annotations

import json
import os
import time
from typing import Iterator

import anthropic

from game.ai_common import AICallError, AIResult, StreamUpdate
from game.indicators import ModeDef
from game.prompts import (
    HISTORICAL_EVENT_SCHEMA,
    POLICY_EVAL_SCHEMA,
    build_historical_event_messages,
    build_policy_eval_messages,
)

RECOMMENDED_MODELS = [
    "claude-sonnet-5",
    "claude-haiku-4-5",
    "claude-opus-5",
]

MAX_TOKENS = 16000
FALLBACK_MODELS = {"claude-opus-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# output_config.effort に対応しているモデル(Haiku 4.5 は指定するとエラーになる)
EFFORT_MODELS = {"claude-opus-5", "claude-sonnet-5"}


def list_available_models() -> list[str]:
    return RECOMMENDED_MODELS


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AICallError("ANTHROPIC_API_KEYが設定されていません。.envに書くかサイドバーでAPIキーを入力してください。")
    return anthropic.Anthropic(api_key=api_key)


def _output_config(schema: dict, model: str) -> dict:
    config: dict = {"format": {"type": "json_schema", "schema": schema}}
    if model in EFFORT_MODELS:
        config["effort"] = "medium"
    return config


def _open_stream(client: anthropic.Anthropic, model: str, messages: list[dict], schema: dict):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    chat = [m for m in messages if m["role"] != "system"]
    params = dict(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=chat,
        output_config=_output_config(schema, model),
    )
    if model in FALLBACK_MODELS:
        return client.beta.messages.stream(betas=[FALLBACK_BETA], fallbacks="default", **params)
    return client.messages.stream(**params)


def _stream_json(model: str, messages: list[dict], schema: dict) -> Iterator[StreamUpdate]:
    client = _get_client()
    start = time.perf_counter()
    accumulated = ""

    try:
        with _open_stream(client, model, messages, schema) as stream:
            for piece in stream.text_stream:
                accumulated += piece
                yield StreamUpdate(partial_content=accumulated, elapsed_seconds=time.perf_counter() - start)
            final = stream.get_final_message()
    except anthropic.APIError as e:
        raise AICallError(f"Claude呼び出しに失敗しました({model}): {e}") from e

    if final.stop_reason == "refusal":
        raise AICallError(
            f"Claude({model})が応答を拒否しました: {getattr(final, 'stop_details', None)}"
        )
    if final.stop_reason == "max_tokens":
        raise AICallError(f"Claude({model})の出力が上限({MAX_TOKENS}トークン)に達して途中で打ち切られました。")

    text = "".join(block.text for block in final.content if block.type == "text")
    elapsed = time.perf_counter() - start
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise AICallError(
            f"モデル({model})の出力がJSONとして解釈できませんでした: {e}\n---\n{text}"
        ) from e

    result = AIResult(
        data=data, raw_content=text, elapsed_seconds=elapsed, model=model, provider="anthropic",
        input_tokens=final.usage.input_tokens, output_tokens=final.usage.output_tokens,
    )
    yield StreamUpdate(partial_content=text, elapsed_seconds=elapsed, done=True, result=result)


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
