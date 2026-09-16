"""Ollamaとの通信ラッパー。

構造化出力(JSON Schema指定)でpolicy_evaluation / historical_eventの2種類を
問い合わせる。モデルごとの応答傾向・速度・スキーマ遵守率を比較しやすいように、
生レスポンス文字列と所要時間もあわせて返す。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import ollama

from game.prompts import (
    HISTORICAL_EVENT_SCHEMA,
    POLICY_EVAL_SCHEMA,
    build_historical_event_messages,
    build_policy_eval_messages,
)


class OllamaCallError(RuntimeError):
    pass


@dataclass
class AIResult:
    data: dict[str, Any]
    raw_content: str
    elapsed_seconds: float
    model: str


def list_available_models() -> list[str]:
    try:
        res = ollama.list()
    except Exception as e:  # noqa: BLE001 - Ollama未起動などをまとめて捕捉
        raise OllamaCallError(
            "Ollamaサーバーに接続できませんでした。`ollama serve` が起動しているか確認してください。"
            f" (詳細: {e})"
        ) from e
    models = getattr(res, "models", None) or res.get("models", [])
    names = []
    for m in models:
        name = getattr(m, "model", None) or (m.get("model") if isinstance(m, dict) else None)
        if name:
            names.append(name)
    return names


def _chat_json(model: str, messages: list[dict], schema: dict) -> AIResult:
    start = time.perf_counter()
    try:
        response = ollama.chat(
            model=model,
            messages=messages,
            format=schema,
            options={"temperature": 0.7},
        )
    except Exception as e:  # noqa: BLE001
        raise OllamaCallError(f"モデル呼び出しに失敗しました({model}): {e}") from e
    elapsed = time.perf_counter() - start

    content = response["message"]["content"] if isinstance(response, dict) else response.message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise OllamaCallError(
            f"モデル({model})の出力がJSONとして解釈できませんでした: {e}\n---\n{content}"
        ) from e

    return AIResult(data=data, raw_content=content, elapsed_seconds=elapsed, model=model)


def evaluate_policy(
    model: str,
    mode_label: str,
    calendar_year: int,
    indicator_snapshot: dict[str, float],
    policy_text: str,
) -> AIResult:
    messages = build_policy_eval_messages(mode_label, calendar_year, indicator_snapshot, policy_text)
    return _chat_json(model, messages, POLICY_EVAL_SCHEMA)


def evaluate_historical_event(
    model: str,
    mode_label: str,
    calendar_year: int,
    indicator_snapshot: dict[str, float],
    event_title: str,
    event_description: str,
) -> AIResult:
    messages = build_historical_event_messages(
        mode_label, calendar_year, indicator_snapshot, event_title, event_description
    )
    return _chat_json(model, messages, HISTORICAL_EVENT_SCHEMA)
