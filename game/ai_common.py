"""AIバックエンド(OpenAI / Gemini / Claude)共通の型とエラー。

どのプロバイダーを使っても同じインターフェース(AIResult / StreamUpdate)で
扱えるようにし、app.py側は呼び出し先を意識せず同じrender_stream()で描画できる
ようにする。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AICallError(RuntimeError):
    """モデル呼び出し・APIキー未設定・JSON解釈失敗などをまとめて表す。"""


@dataclass
class AIResult:
    data: dict[str, Any]
    raw_content: str
    elapsed_seconds: float
    model: str
    provider: str  # "openai" | "gemini" | "anthropic"
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def tokens_per_second(self) -> float | None:
        if not self.output_tokens or not self.elapsed_seconds:
            return None
        return self.output_tokens / self.elapsed_seconds


@dataclass
class StreamUpdate:
    partial_content: str
    elapsed_seconds: float
    done: bool = False
    result: AIResult | None = None
