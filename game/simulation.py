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


@dataclass
class Effect:
    label: str
    source: Literal["policy", "foreign_event", "disaster"]
    sign: float  # +1 or -1
    indicators: list[str]
    peak_year_abs: int  # ゲーム内経過年(0起点)
    sigma: float
    scale: float = 1.0  # 追加スケール(impact_scaleや耐災害減衰など)

    def contribution_at(self, year: int, key: str) -> float:
        if key not in self.indicators:
            return 0.0
        ind = INDICATOR_BY_KEY[key]
        gauss = math.exp(-((year - self.peak_year_abs) ** 2) / (2 * self.sigma**2))
        return self.sign * self.scale * ind.impact_unit * gauss


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
    year_index: int = 0  # 0-origin, 0=開始年
    values: dict[str, float] = field(default_factory=dict)
    effects: list[Effect] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)
    status: str = "ongoing"  # ongoing | win | lose_border | lose_time

    @classmethod
    def new_game(cls, mode: ModeDef, model: str) -> "GameState":
        gs = cls(mode=mode, model=model, values=dict(mode.initial_values))
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

    def _add_impact(self, label: str, impact: dict, sign: float, source: str) -> None:
        duration = impact.get("duration", "medium")
        sigma = DURATION_SIGMA.get(duration, 2.5)
        peak_year = int(impact.get("peak_year", 1))
        indicators = [k for k in impact.get("target_indicators", []) if k in INDICATOR_BY_KEY]
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
        # 影響がほぼ消えたeffectは間引く(効果測定はpeak_year_absからの距離で十分小さいか判定)
        self.effects = [
            e for e in self.effects
            if abs(self.year_index - e.peak_year_abs) <= e.sigma * 4
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

        if self.year_index >= self.mode.duration_years:
            all_met = True
            for key, threshold in self.mode.victory_conditions.items():
                ind = INDICATOR_BY_KEY[key]
                val = self.values[key]
                met = val >= threshold if ind.higher_is_better else val <= threshold
                if not met:
                    all_met = False
                    break
            self.status = "win" if all_met else "lose_time"
            self.log.append(LogEntry(
                self.calendar_year, "gameover",
                "クリア!" if all_met else "ゲームオーバー(タイムアップ)",
                "30年が経過しました。",
            ))
            return

        # 期間途中でも目標値を全て満たしていれば早期クリア
        all_met = all(
            (self.values[k] >= t if INDICATOR_BY_KEY[k].higher_is_better else self.values[k] <= t)
            for k, t in self.mode.victory_conditions.items()
        )
        if all_met:
            self.status = "win"
            self.log.append(LogEntry(
                self.calendar_year, "gameover", "クリア!",
                f"{self.year_index}年で目標水準を達成しました。",
            ))


@dataclass
class _VectorEffect(Effect):
    """指標ごとに個別の基準値(impact_vector)を持つEffect。"""

    vector: dict[str, float] = field(default_factory=dict)

    def contribution_at(self, year: int, key: str) -> float:
        if key not in self.vector:
            return 0.0
        gauss = math.exp(-((year - self.peak_year_abs) ** 2) / (2 * self.sigma**2))
        return self.sign * self.scale * self.vector[key] * gauss
