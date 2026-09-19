"""ゲーム進行のコアロジック。

政策効果・史実イベント効果は「ガウス関数型の一時的な増減インパルス」として
effectsリストに積み上げ、毎年その総和を各指標に加算していく方式で計算する。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from game.events import ScriptedEvent, events_for_year
from game.indicators import INDICATOR_BY_KEY, ModeDef

DURATION_SIGMA = {"short": 1.0, "medium": 2.5, "long": 5.0}

# magnitude(1〜5)が基準値のとき、山の大きさ(面積=指標が最終的に動く総量)が
# 指標ごとの impact_unit × EFFECT_TOTAL_MULTIPLIER になる
MAGNITUDE_BASELINE = 3
# 山の総量の全体倍率(ゲームバランス調整用)
EFFECT_TOTAL_MULTIPLIER = 2.0


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _mountain_weight(year: int, peak_year: int, sigma: float) -> float:
    """面積が1になるよう規格化したガウス関数(全年の合計≒1)。

    σで割ることで、durationが長いだけで総影響量が増えないようにする。
    """
    gauss = math.exp(-((year - peak_year) ** 2) / (2 * sigma**2))
    return gauss / (sigma * math.sqrt(2 * math.pi))


@dataclass
class Effect:
    label: str
    source: Literal["policy", "foreign_event", "disaster"]
    sign: float  # +1=良い方向 / -1=悪い方向(政策効果)
    indicators: list[str]
    peak_year_abs: int  # ゲーム内経過年(0起点)
    sigma: float
    scale: float = 1.0  # 山の大きさ倍率(policyならmagnitude/3、災害なら耐災害減衰など)

    def contribution_at(self, year: int, key: str) -> float:
        if key not in self.indicators:
            return 0.0
        ind = INDICATOR_BY_KEY[key]
        # 「良い方向」の動きは、低いほど良い指標(失業率・債務残高など)では値の減少になる
        direction = 1.0 if ind.higher_is_better else -1.0
        return (
            self.sign * direction * self.scale * EFFECT_TOTAL_MULTIPLIER
            * ind.impact_unit * _mountain_weight(year, self.peak_year_abs, self.sigma)
        )


@dataclass
class LogEntry:
    calendar_year: int
    kind: str
    title: str
    detail: str


@dataclass
class GameState:
    mode: ModeDef
    model: str
    provider: str  # "openai" | "gemini" | "anthropic"
    year_index: int = 0  # 0-origin, 0=開始年
    values: dict[str, float] = field(default_factory=dict)
    effects: list[Effect] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)
    status: str = "ongoing"  # ongoing | win | lose_border | lose_time

    @classmethod
    def new_game(cls, mode: ModeDef, model: str, provider: str) -> "GameState":
        gs = cls(mode=mode, model=model, provider=provider, values=dict(mode.initial_values))
        gs.log.append(
            LogEntry(mode.start_year, "start", "ゲーム開始", mode.description)
        )
        return gs

    @property
    def calendar_year(self) -> int:
        return self.mode.start_year + self.year_index

    def snapshot(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in self.values.items()}

    # --- 効果の登録 -------------------------------------------------

    def add_policy_effects(self, policy_label: str, evaluation: dict) -> None:
        for impact in evaluation.get("positive_impacts", []):
            self._add_impact(policy_label, impact, sign=+1.0, source="policy")
        for impact in evaluation.get("negative_impacts", []):
            self._add_impact(policy_label, impact, sign=-1.0, source="policy")
        review = str(evaluation.get("overall_review", "")).strip()
        if review:
            self.log.append(LogEntry(self.calendar_year, "policy", f"政策: {policy_label}", review))

    def latest_policy_log(self) -> "LogEntry | None":
        return next((e for e in reversed(self.log) if e.kind == "policy"), None)

    def _add_impact(self, label: str, impact: dict, sign: float, source: str) -> None:
        duration = impact.get("duration", "medium")
        sigma = DURATION_SIGMA.get(duration, 2.5)
        peak_year = _clamp_int(impact.get("peak_year"), 0, 29, default=1)
        magnitude = _clamp_int(impact.get("magnitude"), 1, 5, default=MAGNITUDE_BASELINE)
        indicators = [k for k in impact.get("target_indicators", []) if k in INDICATOR_BY_KEY][:3]
        if not indicators:
            return
        self.effects.append(
            Effect(
                label=f"{label}: {impact.get('description', '')}",
                source=source,  # type: ignore[arg-type]
                sign=sign,
                indicators=indicators,
                peak_year_abs=self.year_index + peak_year,
                sigma=sigma,
                scale=magnitude / MAGNITUDE_BASELINE,
            )
        )

    def add_foreign_event_effect(self, event: ScriptedEvent, occurs: bool, impact_scale: int) -> None:
        if not occurs:
            self.log.append(
                LogEntry(self.calendar_year, "foreign_event_avoided",
                          event.title, "この世界線では発生しなかった。")
            )
            return
        scale = impact_scale / 3.0
        self.effects.append(
            _VectorEffect(
                label=event.title,
                source="foreign_event",
                sign=1.0,
                indicators=list(event.impact_vector.keys()),
                peak_year_abs=self.year_index + 1,
                sigma=1.5,
                scale=scale,
                vector=event.impact_vector,
            )
        )
        self.log.append(
            LogEntry(self.calendar_year, "foreign_event", event.title,
                      f"発生(影響度{impact_scale}/5): {event.description}")
        )

    def add_disaster_effect(self, event: ScriptedEvent) -> None:
        resilience = self.values.get("disaster_resilience", 50.0)
        dampen = max(0.0, 1.0 - (resilience / 100.0) * 0.8)
        self.effects.append(
            _VectorEffect(
                label=event.title,
                source="disaster",
                sign=1.0,
                indicators=list(event.impact_vector.keys()),
                peak_year_abs=self.year_index,
                sigma=1.2,
                scale=dampen,
                vector=event.impact_vector,
            )
        )
        self.log.append(
            LogEntry(self.calendar_year, "disaster", event.title,
                      f"発生(耐災害指数{resilience:.0f}により被害{dampen*100:.0f}%に軽減): "
                      f"{event.description}")
        )

    def pending_events(self) -> list[ScriptedEvent]:
        return events_for_year(self.mode.key, self.calendar_year)

    # --- 年次進行 -----------------------------------------------------

    def advance_year(self) -> None:
        deltas = {k: 0.0 for k in self.values}
        for effect in self.effects:
            for key in effect.indicators:
                deltas[key] = deltas.get(key, 0.0) + effect.contribution_at(self.year_index, key)

        for key, delta in deltas.items():
            ind = INDICATOR_BY_KEY[key]
            new_val = self.values[key] + delta
            self.values[key] = min(max(new_val, ind.min_val), ind.max_val)

        self.year_index += 1
        # ピークから4σ以上過ぎて影響がほぼ消えたeffectだけ間引く(未来のピークは残す)
        self.effects = [
            e for e in self.effects
            if self.year_index - e.peak_year_abs <= e.sigma * 4
        ]

        self._check_end_conditions()

    def _check_end_conditions(self) -> None:
        if self.status != "ongoing":
            return

        for key, threshold in self.mode.failure_conditions.items():
            ind = INDICATOR_BY_KEY[key]
            val = self.values[key]
            breached = val < threshold if ind.higher_is_better else val > threshold
            if breached:
                self.status = "lose_border"
                self.log.append(LogEntry(
                    self.calendar_year, "gameover",
                    "ゲームオーバー",
                    f"{ind.label}が{val:.1f}となり、破綻ライン({threshold})を超えました。",
                ))
                return

        # クリア判定は期間終了時(30年経過時点)のみ。途中で条件を満たしても即クリアにはならない
        if self.year_index >= self.mode.duration_years:
            unmet = []
            for key, threshold in self.mode.victory_conditions.items():
                ind = INDICATOR_BY_KEY[key]
                val = self.values[key]
                met = val >= threshold if ind.higher_is_better else val <= threshold
                if not met:
                    op = "以上" if ind.higher_is_better else "以下"
                    unmet.append(f"{ind.label}(目標{threshold}{op}/現在{val:.1f})")
            self.status = "lose_time" if unmet else "win"
            self.log.append(LogEntry(
                self.calendar_year, "gameover",
                "ゲームオーバー(タイムアップ)" if unmet else "クリア!",
                ("30年が経過しましたが、未達成の目標があります: " + "、".join(unmet)) if unmet
                else "30年が経過し、すべての目標水準を達成しました。",
            ))


@dataclass
class _VectorEffect(Effect):
    """指標ごとに個別の基準値(impact_vector)を持つEffect。"""

    vector: dict[str, float] = field(default_factory=dict)

    def contribution_at(self, year: int, key: str) -> float:
        if key not in self.vector:
            return 0.0
        # impact_vectorは「その出来事が指標を最終的に動かす総量」として扱う
        return self.sign * self.scale * self.vector[key] * _mountain_weight(
            year, self.peak_year_abs, self.sigma
        )
