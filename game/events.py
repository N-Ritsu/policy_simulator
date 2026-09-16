"""史実イベントの台本データ。

foreign: 諸外国の出来事。AIに「(この世界線で)史実通り発生するか」「影響度(1-5)」を
         判定させ、その結果でimpact_vector(基準影響度=3のときの想定値)をスケールする。
disaster: 自然災害。史実通り必ず発生する前提とし、耐災害指数(disaster_resilience)で
          減衰させたうえで機械的に適用する(AI判定は行わない)。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScriptedEvent:
    calendar_year: int
    kind: str  # "foreign" | "disaster"
    title: str
    description: str
    impact_vector: dict[str, float]  # 基準影響度(=3 or 災害ならそのまま)での各指標への増減量


BUBBLE_EVENTS: list[ScriptedEvent] = [
    ScriptedEvent(
        1990, "foreign", "資産価格急落の連鎖(米国発)",
        "米国の金融引き締めと資産市場の調整が波及し、世界的に株式・不動産価格が動揺する。",
        {"stock_market_index": -25, "corporate_profit_index": -10, "exchange_rate_index": -5},
    ),
    ScriptedEvent(
        1991, "foreign", "湾岸戦争",
        "中東情勢の緊迫化により原油価格が高騰、貿易収支とインフレに影響が及ぶ。",
        {"trade_balance": -4, "inflation_rate": 1.2},
    ),
    ScriptedEvent(
        1995, "disaster", "阪神・淡路大震災",
        "都市直下型の大地震が関西圏を襲い、産業インフラに甚大な被害が出る。",
        {"gdp": -12, "stock_market_index": -15, "national_satisfaction": -8},
    ),
    ScriptedEvent(
        1997, "foreign", "アジア通貨危機",
        "タイ・韓国など近隣諸国の通貨が暴落し、地域経済とサプライチェーンが混乱する。",
        {"trade_balance": -5, "exchange_rate_index": -8, "stock_market_index": -10},
    ),
    ScriptedEvent(
        2001, "foreign", "米同時多発テロ・世界同時株安",
        "国際情勢の急変により世界的にリスク回避が強まり、株式市場と観光需要が落ち込む。",
        {"stock_market_index": -12, "tourism_index": -10},
    ),
]

MODERN_EVENTS: list[ScriptedEvent] = [
    ScriptedEvent(
        2001, "foreign", "ITバブル崩壊",
        "米国発の情報技術関連株の急落が波及し、輸出型企業の収益が悪化する。",
        {"stock_market_index": -15, "corporate_profit_index": -8, "export_competitiveness": -5},
    ),
    ScriptedEvent(
        2008, "foreign", "世界金融危機(リーマン・ショック)",
        "米国発の金融危機が世界経済を直撃し、輸出と雇用に深刻な打撃を与える。",
        {"gdp": -18, "unemployment_rate": 2.5, "stock_market_index": -30, "trade_balance": -8},
    ),
    ScriptedEvent(
        2011, "disaster", "東日本大震災・原発事故",
        "東北地方太平洋沖地震と津波、それに伴う原発事故が発生し、電力・産業基盤に甚大な被害。",
        {"gdp": -15, "energy_self_sufficiency": -10, "national_satisfaction": -10,
         "trust_in_government": -8},
    ),
    ScriptedEvent(
        2020, "foreign", "世界的感染症の拡大(COVID-19)",
        "世界的なパンデミックにより人の往来が止まり、観光・外食・医療体制に強い負荷がかかる。",
        {"tourism_index": -25, "gdp": -10, "healthcare_spending_ratio": 2.0,
         "mental_health_index": -8},
    ),
    ScriptedEvent(
        2022, "foreign", "国際情勢緊迫化とエネルギー価格高騰",
        "地政学的な緊張の高まりでエネルギー・食料価格が世界的に高騰する。",
        {"inflation_rate": 2.0, "energy_self_sufficiency": -5, "food_self_sufficiency": -3},
    ),
]


EVENTS_BY_MODE: dict[str, list[ScriptedEvent]] = {
    "bubble": BUBBLE_EVENTS,
    "modern": MODERN_EVENTS,
}


def events_for_year(mode_key: str, calendar_year: int) -> list[ScriptedEvent]:
    return [e for e in EVENTS_BY_MODE.get(mode_key, []) if e.calendar_year == calendar_year]
