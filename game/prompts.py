"""AIへ渡すプロンプトとJSON Schemaの組み立て(プロバイダー非依存)。

スキーマはOpenAI(strict)・Claude・Geminiの構造化出力すべてで通る形に揃えている:
全オブジェクトに additionalProperties: false、全プロパティを required、
minimum/maximum/minItems などの制約は使わない(範囲はdescriptionで伝え、
コード側でclampする)。
"""

from game.indicators import INDICATORS, ModeDef

INDICATOR_KEYS = [i.key for i in INDICATORS]

_INDICATOR_LIST_TEXT = "\n".join(
    f"- {i.key}: {i.label}({i.unit})" + ("" if i.higher_is_better else " 【低いほど良い指標】")
    for i in INDICATORS
)


def _impact_item_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "この影響の内容(1文)"},
            "target_indicators": {
                "type": "array",
                "items": {"type": "string", "enum": INDICATOR_KEYS},
                "description": "影響を受ける指標。1〜3個",
            },
            "peak_year": {
                "type": "integer",
                "description": "効果が最大になるまでの年数。0=即時、29=30年後近く",
            },
            "duration": {
                "type": "string",
                "enum": ["short", "medium", "long"],
                "description": "効果のばらつき。short=1-2年で収束、medium=数年、long=長期間持続",
            },
            "magnitude": {
                "type": "integer",
                "description": "効果の大きさ(山そのものの大きさ=指標を最終的にどれだけ動かすか)。1=微小、2=小、3=標準、4=大、5=甚大",
            },
        },
        "required": ["description", "target_indicators", "peak_year", "duration", "magnitude"],
        "additionalProperties": False,
    }


POLICY_EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "positive_impacts": {
            "type": "array",
            "items": _impact_item_schema(),
            "description": "指標が良い方向に動く効果。ちょうど3件",
        },
        "negative_impacts": {
            "type": "array",
            "items": _impact_item_schema(),
            "description": "指標が悪い方向に動く効果(副作用)。ちょうど3件",
        },
        "overall_review": {
            "type": "string",
            "description": "ユーザーに提示する、この政策全体への総評(日本語で2〜3文)。最後に書く",
        },
    },
    "required": ["positive_impacts", "negative_impacts", "overall_review"],
    "additionalProperties": False,
}


HISTORICAL_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "event_occurs": {"type": "boolean", "description": "この出来事が発生するか(回避できた場合はfalse)"},
        "reason": {"type": "string", "description": "判定理由(簡潔に)"},
        "impact_scale": {
            "type": "integer",
            "description": "影響度。1=微小、3=史実通り、5=甚大",
        },
    },
    "required": ["event_occurs", "reason", "impact_scale"],
    "additionalProperties": False,
}


_ERA_PRINCIPLES = (
    "# 評価にあたっての前提(必ず守ること)\n"
    "- すべての判断は、上の舞台設定の時代における社会・経済・制度・技術水準・国際環境・"
    "国民の価値観を前提に行ってください。今日の常識や現在の感覚で判断してはいけません。"
    "同じ政策・同じ金額でも、当時の経済規模や財政状況、世論や国民の受け止め方は今とは異なります。\n"
    "- 金額や規模は、その時点の指標(GDP、税収、国の債務残高、家計残キャッシュなど)に対する"
    "比率で評価してください(例: 1兆円がGDPや税収の何%にあたるか)。\n"
    "- 史実の結果を知っている前提(後知恵)で評価せず、その時点の状況と政策内容から"
    "合理的に予想される因果で評価してください。諸外国の動向や自然災害などの大きな外的出来事は"
    "ゲーム側で別途扱うので、ここで勝手に織り込まないでください。"
)


def _premise_block(mode: ModeDef) -> str:
    return f"# 舞台設定(このゲームの前提条件)\n【モード】{mode.label}\n{mode.scenario_context}\n\n{_ERA_PRINCIPLES}\n\n"


def build_policy_eval_messages(
    mode: ModeDef, calendar_year: int, indicator_snapshot: dict[str, float], policy_text: str
) -> list[dict]:
    snapshot_text = "\n".join(f"- {k}: {v}" for k, v in indicator_snapshot.items())
    system = (
        "あなたは日本の政策シミュレーションゲームの審判役アシスタントです。\n"
        "このゲームは、プレイヤーが日本の政策担当者となり、30年間にわたり毎年政策を実行していく"
        "歴史シミュレーションです。\n\n"
        f"{_premise_block(mode)}"
        "# 出力ルール\n"
        "ユーザーが入力した政策1つについて、今後30年間で社会に及ぼす影響を分析し、"
        "指定されたJSON Schemaに厳密に従って出力してください。\n"
        "良い影響(positive_impacts)を3つ、悪い影響(negative_impacts)を3つ、"
        "必ずそれぞれ挙げてください(現実の政策には副作用があります)。\n"
        "- positive_impacts は指標が「良い方向」に動く効果、negative_impacts は「悪い方向」に動く効果です。"
        "(例: 失業率が下がる=positive、国の債務残高が増える=negative。"
        "【低いほど良い指標】は値が下がるほど良い指標です)\n"
        "- target_indicators は影響を受ける指標を1〜3個、以下のキーの中からのみ選んでください:\n"
        f"{_INDICATOR_LIST_TEXT}\n"
        "- peak_year は効果が最大になるまでの年数(0=即時, 29=30年後近く)。\n"
        "- duration は効果が続く期間のばらつき(short=1-2年で収束, medium=数年, long=長期間持続)。\n"
        "- magnitude は効果の大きさ(山そのものの大きさ)を1〜5の整数で。1=微小, 2=小, 3=標準的, 4=大, 5=甚大。"
        "peak_yearやdurationとは独立に、「その効果が最終的に指標をどれだけ動かすか」の総量だけで判断し、"
        "効果が長く続く(long)からといって大きくしないでください。"
        "政策の規模が小さければ全体に低め、大規模なら高めにしてください。\n"
        "- overall_review は最後に出力する、プレイヤーに見せる総評です。上の6つの影響を踏まえて、"
        "この政策の狙い・主な効果と副作用・総合的な見立てを日本語で2〜3文にまとめてください。"
        "指標は英字のキーではなく日本語名で書いてください。"
    )
    user = (
        f"# 現在(西暦{calendar_year}年)の社会指標\n{snapshot_text}\n\n"
        f"# ユーザーが実行する政策\n{policy_text}\n\n"
        "この政策が今後30年間に社会指標へ与える影響を分析してください。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_historical_event_messages(
    mode: ModeDef,
    calendar_year: int,
    indicator_snapshot: dict[str, float],
    event_title: str,
    event_description: str,
) -> list[dict]:
    snapshot_text = "\n".join(f"- {k}: {v}" for k, v in indicator_snapshot.items())
    system = (
        "あなたは日本の政策シミュレーションゲームの審判役アシスタントです。\n"
        "このゲームは、プレイヤーが日本の政策担当者となり、30年間にわたり毎年政策を実行していく"
        "歴史シミュレーションです。これまでのプレイヤーの政策によって史実とは異なる歴史が"
        "展開している可能性があります。\n\n"
        f"{_premise_block(mode)}"
        "# 出力ルール\n"
        "与えられた諸外国の出来事が、現在の社会状況を踏まえたときに"
        "史実通り発生するかどうかを判定し、指定されたJSON Schemaに厳密に従って出力してください。\n"
        "reasonには判定理由を簡潔に述べてください。\n"
        "impact_scaleは1(微小)〜3(史実通りの規模)〜5(甚大)の整数で、"
        "発生しない場合(event_occurs=false)でも一応の想定規模を入れてください。"
    )
    user = (
        f"# 現在(西暦{calendar_year}年)の社会指標\n{snapshot_text}\n\n"
        f"# 想定されている諸外国の出来事\n【{event_title}】\n{event_description}\n\n"
        "この出来事は史実通り発生しますか?"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
