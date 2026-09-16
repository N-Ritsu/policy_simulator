"""Ollamaへ渡すプロンプトとJSON Schemaの組み立て。"""

from game.indicators import INDICATORS

INDICATOR_KEYS = [i.key for i in INDICATORS]

_INDICATOR_LIST_TEXT = "\n".join(f"- {i.key}: {i.label}({i.unit})" for i in INDICATORS)


POLICY_EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "positive_impacts": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "target_indicators": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "string", "enum": INDICATOR_KEYS},
                    },
                    "peak_year": {"type": "integer", "minimum": 0, "maximum": 29},
                    "duration": {"type": "string", "enum": ["short", "medium", "long"]},
                },
                "required": ["description", "target_indicators", "peak_year", "duration"],
            },
        },
        "negative_impacts": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "target_indicators": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "string", "enum": INDICATOR_KEYS},
                    },
                    "peak_year": {"type": "integer", "minimum": 0, "maximum": 29},
                    "duration": {"type": "string", "enum": ["short", "medium", "long"]},
                },
                "required": ["description", "target_indicators", "peak_year", "duration"],
            },
        },
    },
    "required": ["positive_impacts", "negative_impacts"],
}


HISTORICAL_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "event_occurs": {"type": "boolean"},
        "reason": {"type": "string"},
        "impact_scale": {"type": "integer", "minimum": 1, "maximum": 5},
    },
    "required": ["event_occurs", "reason", "impact_scale"],
}


def build_policy_eval_messages(
    mode_label: str, calendar_year: int, indicator_snapshot: dict[str, float], policy_text: str
) -> list[dict]:
    snapshot_text = "\n".join(f"- {k}: {v}" for k, v in indicator_snapshot.items())
    system = (
        "あなたは日本の政策シミュレーションゲームの審判役アシスタントです。\n"
        "ユーザーが入力した政策1つについて、今後30年間で社会に及ぼす影響を分析し、"
        "指定されたJSON Schemaに厳密に従って出力してください。\n"
        "良い影響を3つ、悪い影響を3つ、必ずそれぞれ挙げてください(現実の政策には副作用があります)。\n"
        "target_indicatorsは必ず以下のキーの中からのみ選んでください:\n"
        f"{_INDICATOR_LIST_TEXT}\n"
        "peak_yearは効果が最大になるまでの年数(0=即時, 29=30年後近く)。\n"
        "durationは効果の続く期間の目安(short=1-2年で収束, medium=数年, long=長期間持続)。"
    )
    user = (
        f"# モード\n{mode_label}\n\n"
        f"# 現在(西暦{calendar_year}年)の社会指標\n{snapshot_text}\n\n"
        f"# ユーザーが実行する政策\n{policy_text}\n\n"
        "この政策が今後30年間に社会指標へ与える影響を分析してください。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_historical_event_messages(
    mode_label: str,
    calendar_year: int,
    indicator_snapshot: dict[str, float],
    event_title: str,
    event_description: str,
) -> list[dict]:
    snapshot_text = "\n".join(f"- {k}: {v}" for k, v in indicator_snapshot.items())
    system = (
        "あなたは日本の政策シミュレーションゲームの審判役アシスタントです。\n"
        "このゲームでは、これまでのユーザーの政策によって史実とは異なる歴史が展開している"
        "可能性があります。与えられた諸外国の出来事が、現在の社会状況を踏まえたときに"
        "史実通り発生するかどうかを判定し、指定されたJSON Schemaに厳密に従って出力してください。\n"
        "reasonには判定理由を簡潔に述べてください。\n"
        "impact_scaleは1(微小)〜3(史実通りの規模)〜5(甚大)で、"
        "発生しない場合(event_occurs=false)でも一応の想定規模を入れてください。"
    )
    user = (
        f"# モード\n{mode_label}\n\n"
        f"# 現在(西暦{calendar_year}年)の社会指標\n{snapshot_text}\n\n"
        f"# 想定されている諸外国の出来事\n【{event_title}】\n{event_description}\n\n"
        "この出来事は史実通り発生しますか?"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
