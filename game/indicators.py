"""社会指標の定義。

50個の社会指標のメタデータ(表示名・カテゴリ・単位・単発効果の基準量・
取りうる範囲)と、モード別の初期値・勝利条件・敗北条件を持つ。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorDef:
    key: str
    label: str
    category: str
    unit: str
    impact_unit: float  # 1回の政策/イベント効果がピーク時に動かす基準量
    min_val: float
    max_val: float
    higher_is_better: bool = True


# (key, label, category, unit, impact_unit, min, max, higher_is_better)
_RAW_INDICATORS = [
    # --- 経済 (10) ---
    ("gdp", "GDP", "経済", "兆円", 8.0, 0, 2000),
    ("gdp_growth_rate", "GDP成長率", "経済", "%", 0.8, -15, 15),
    ("national_debt", "国の債務残高", "経済", "兆円", 15.0, 0, 5000, False),
    ("tax_revenue", "税収", "経済", "兆円", 3.0, 0, 300),
    ("unemployment_rate", "失業率", "経済", "%", 0.4, 0, 20, False),
    ("inflation_rate", "インフレ率", "経済", "%", 0.5, -10, 30, False),
    ("exchange_rate_index", "円為替指数", "経済", "pt", 3.0, 0, 200),
    ("stock_market_index", "株価指数", "経済", "pt", 5.0, 0, 500),
    ("corporate_profit_index", "企業収益指数", "経済", "pt", 3.0, 0, 200),
    ("trade_balance", "貿易収支", "経済", "兆円", 2.0, -50, 50),
    # --- 家計・財政 (6) ---
    ("household_savings", "家計残キャッシュ", "家計・財政", "兆円", 4.0, 0, 2000),
    ("household_debt", "家計負債", "家計・財政", "兆円", 4.0, 0, 1000, False),
    ("disposable_income", "可処分所得指数", "家計・財政", "pt", 2.5, 0, 200),
    ("poverty_rate", "相対的貧困率", "家計・財政", "%", 0.4, 0, 40, False),
    ("gini_coefficient", "ジニ係数", "家計・財政", "pt", 0.01, 0, 1, False),
    ("consumption_tax_rate", "消費税率", "家計・財政", "%", 0.5, 0, 30, False),
    # --- 人口動態 (6) ---
    ("birth_rate", "出生率(合計特殊出生率)", "人口動態", "", 0.03, 0.5, 4),
    ("population", "総人口", "人口動態", "百万人", 0.5, 50, 200),
    ("aging_rate", "高齢化率", "人口動態", "%", 0.3, 0, 60, False),
    ("working_age_ratio", "生産年齢人口比率", "人口動態", "%", 0.3, 30, 80),
    ("immigration_rate", "移民受入指数", "人口動態", "pt", 1.5, 0, 100),
    ("marriage_rate", "婚姻率", "人口動態", "‰", 0.1, 0, 15),
    # --- 健康 (5) ---
    ("healthy_life_expectancy", "健康寿命", "健康", "歳", 0.15, 50, 100),
    ("life_expectancy", "平均寿命", "健康", "歳", 0.1, 50, 100),
    ("healthcare_spending_ratio", "医療費対GDP比", "健康", "%", 0.2, 0, 30, False),
    ("obesity_rate", "肥満率", "健康", "%", 0.3, 0, 50, False),
    ("mental_health_index", "精神的健康指数", "健康", "pt", 2.0, 0, 100),
    # --- 社会・満足度 (6) ---
    ("national_satisfaction", "国民満足度指数", "社会・満足度", "pt", 3.0, 0, 100),
    ("trust_in_government", "政府信頼度指数", "社会・満足度", "pt", 3.0, 0, 100),
    ("crime_rate", "犯罪発生率", "社会・満足度", "件/10万人", 3.0, 0, 300, False),
    ("education_level_index", "教育水準指数", "社会・満足度", "pt", 2.0, 0, 100),
    ("work_life_balance_index", "ワークライフバランス指数", "社会・満足度", "pt", 2.5, 0, 100),
    ("social_mobility_index", "社会流動性指数", "社会・満足度", "pt", 2.0, 0, 100),
    # --- 技術・産業 (6) ---
    ("tech_competitiveness_index", "技術競争力指数", "技術・産業", "pt", 3.0, 0, 100),
    ("rd_spending_ratio", "研究開発費対GDP比", "技術・産業", "%", 0.2, 0, 10),
    ("patent_index", "特許出願指数", "技術・産業", "pt", 3.0, 0, 200),
    ("startup_rate", "起業率指数", "技術・産業", "pt", 2.5, 0, 100),
    ("digitalization_index", "デジタル化指数", "技術・産業", "pt", 3.0, 0, 100),
    ("energy_self_sufficiency", "エネルギー自給率", "技術・産業", "%", 1.5, 0, 100),
    # --- 環境・防災 (6) ---
    ("co2_emissions_index", "CO2排出指数", "環境・防災", "pt", 2.0, 0, 200, False),
    ("renewable_energy_ratio", "再生可能エネルギー比率", "環境・防災", "%", 1.5, 0, 100),
    ("disaster_resilience", "耐災害指数", "環境・防災", "pt", 2.5, 0, 100),
    ("forest_coverage_ratio", "森林被覆率", "環境・防災", "%", 0.5, 0, 100),
    ("air_quality_index", "大気質指数", "環境・防災", "pt", 1.5, 0, 100),
    ("food_self_sufficiency", "食料自給率", "環境・防災", "%", 1.0, 0, 100),
    # --- 国際 (5) ---
    ("diplomatic_influence", "外交影響力指数", "国際", "pt", 2.0, 0, 100),
    ("export_competitiveness", "輸出競争力指数", "国際", "pt", 2.5, 0, 100),
    ("foreign_reserve", "外貨準備高", "国際", "兆円", 3.0, 0, 300),
    ("defense_capability", "防衛力指数", "国際", "pt", 2.0, 0, 100),
    ("tourism_index", "観光指数", "国際", "pt", 3.0, 0, 100),
]

INDICATORS: list[IndicatorDef] = [IndicatorDef(*row) for row in _RAW_INDICATORS]
INDICATOR_BY_KEY: dict[str, IndicatorDef] = {i.key: i for i in INDICATORS}
CATEGORIES: list[str] = list(dict.fromkeys(i.category for i in INDICATORS))

assert len(INDICATORS) == 50, f"想定は50指標だが{len(INDICATORS)}個ある"


# ---------------------------------------------------------------------------
# モード定義: 初期値 / 勝利条件 / 敗北条件
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModeDef:
    key: str
    label: str
    description: str
    start_year: int  # 開始時の西暦
    duration_years: int
    initial_values: dict[str, float]
    victory_conditions: dict[str, float]  # 指標 >= (higher_is_better) / <= (逆) を満たすべき水準
    failure_conditions: dict[str, float]  # いずれか1つでも越えたら即ゲームオーバー


def _fill_defaults(overrides: dict[str, float]) -> dict[str, float]:
    """未指定の指標は範囲の中央値で埋める(プロトタイプ用の簡易処理)。"""
    values = {}
    for ind in INDICATORS:
        if ind.key in overrides:
            values[ind.key] = overrides[ind.key]
        else:
            values[ind.key] = round((ind.min_val + ind.max_val) / 2, 2)
    return values


BUBBLE_MODE = ModeDef(
    key="bubble",
    label="バブル期モード:バブル崩壊を防げ!",
    description=(
        "1988年、資産価格が高騰する好景気の絶頂。このまま崩壊させず、"
        "軟着陸させながら健全な成長へ導けるか。"
    ),
    start_year=1988,
    duration_years=30,
    initial_values=_fill_defaults({
        "gdp": 420, "gdp_growth_rate": 6.0, "national_debt": 200, "tax_revenue": 60,
        "unemployment_rate": 2.5, "inflation_rate": 2.5, "exchange_rate_index": 120,
        "stock_market_index": 380, "corporate_profit_index": 150, "trade_balance": 12,
        "household_savings": 900, "household_debt": 300, "disposable_income": 110,
        "poverty_rate": 12, "gini_coefficient": 0.30, "consumption_tax_rate": 3,
        "birth_rate": 1.66, "population": 122, "aging_rate": 11, "working_age_ratio": 69,
        "national_satisfaction": 68, "trust_in_government": 55,
        "tech_competitiveness_index": 78, "disaster_resilience": 40,
        "foreign_reserve": 90,
    }),
    victory_conditions={
        "gdp_growth_rate": 1.5,
        "unemployment_rate": 5.0,  # 以下であること(failure/higher_is_better=Falseなので下回ればOK)
        "national_debt": 600.0,   # 以下
        "national_satisfaction": 65.0,
    },
    failure_conditions={
        "gdp_growth_rate": -6.0,      # これを下回ったら破綻
        "unemployment_rate": 12.0,    # これを超えたら破綻
        "national_satisfaction": 15.0,  # これを下回ったら破綻
    },
)

MODERN_MODE = ModeDef(
    key="modern",
    label="現代モード:不況を跳ね除け、再び技術大国へ",
    description=(
        "2000年、長期停滞の入り口。失われた技術的優位を取り戻し、"
        "再び世界有数の技術大国として返り咲けるか。"
    ),
    start_year=2000,
    duration_years=30,
    initial_values=_fill_defaults({
        "gdp": 500, "gdp_growth_rate": 0.5, "national_debt": 650, "tax_revenue": 50,
        "unemployment_rate": 4.7, "inflation_rate": -0.5, "exchange_rate_index": 105,
        "stock_market_index": 140, "corporate_profit_index": 90, "trade_balance": 8,
        "household_savings": 1400, "household_debt": 350, "disposable_income": 95,
        "poverty_rate": 15, "gini_coefficient": 0.32, "consumption_tax_rate": 5,
        "birth_rate": 1.36, "population": 127, "aging_rate": 17, "working_age_ratio": 68,
        "national_satisfaction": 50, "trust_in_government": 40,
        "tech_competitiveness_index": 55, "digitalization_index": 35,
        "disaster_resilience": 55, "foreign_reserve": 350,
    }),
    victory_conditions={
        "tech_competitiveness_index": 80.0,
        "digitalization_index": 80.0,
        "gdp_growth_rate": 2.0,
        "national_satisfaction": 70.0,
    },
    failure_conditions={
        "gdp_growth_rate": -6.0,
        "unemployment_rate": 12.0,
        "national_satisfaction": 15.0,
    },
)

MODES: dict[str, ModeDef] = {m.key: m for m in (BUBBLE_MODE, MODERN_MODE)}
