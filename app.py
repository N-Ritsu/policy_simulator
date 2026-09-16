"""政策シミュレーションゲーム - Ollamaプロトタイプ (Streamlit)

`streamlit run app.py` で起動。ローカルのOllamaサーバーと通信し、
選択したモデルで政策の影響評価・史実イベント判定を行う。
"""

from __future__ import annotations

import streamlit as st

from game.indicators import CATEGORIES, INDICATOR_BY_KEY, MODES
from game.ollama_client import OllamaCallError, evaluate_historical_event, evaluate_policy, list_available_models
from game.simulation import GameState

st.set_page_config(page_title="政策シミュレーションゲーム(Ollamaプロトタイプ)", layout="wide")


# --- セッション状態の初期化 ------------------------------------------------

if "game" not in st.session_state:
    st.session_state.game = None
if "last_ai_calls" not in st.session_state:
    st.session_state.last_ai_calls = []


def start_new_game(mode_key: str, model: str) -> None:
    st.session_state.game = GameState.new_game(MODES[mode_key], model)
    st.session_state.last_ai_calls = []


# --- サイドバー -------------------------------------------------------------

with st.sidebar:
    st.header("設定")

    try:
        available_models = list_available_models()
    except OllamaCallError as e:
        available_models = []
        st.error(str(e))

    if not available_models:
        st.warning(
            "Ollamaのモデルが見つかりません。`ollama serve` を起動し、"
            "`ollama pull <モデル名>` でモデルを取得してください。"
        )

    model = st.selectbox("比較したいOllamaモデル", available_models) if available_models else None

    mode_key = st.selectbox(
        "モード",
        options=list(MODES.keys()),
        format_func=lambda k: MODES[k].label,
    )

    if st.button("新しいゲームを開始", disabled=model is None, type="primary"):
        start_new_game(mode_key, model)
        st.rerun()

    st.divider()
    st.caption(
        "このプロトタイプはOllamaで動くモデルの出力傾向・速度を比較するための"
        "簡易版です。政策効果はガウス型インパルスとして各指標に加算されます。"
    )


game: GameState | None = st.session_state.game

if game is None:
    st.title("政策シミュレーションゲーム")
    st.write("左のサイドバーでモードとOllamaモデルを選び、「新しいゲームを開始」を押してください。")
    st.stop()


# --- ヘッダー ----------------------------------------------------------------

st.title(game.mode.label)
col_a, col_b, col_c = st.columns(3)
col_a.metric("西暦", f"{game.calendar_year}年")
col_b.metric("経過年数", f"{game.year_index} / {game.mode.duration_years}年")
col_c.metric("使用モデル", game.model)

if game.status != "ongoing":
    if game.status == "win":
        st.success("🎉 クリア!目標の社会指標水準を達成しました。")
    elif game.status == "lose_border":
        st.error("💥 ゲームオーバー:社会指標が破綻ラインを超えました。")
    else:
        st.error("⏱ ゲームオーバー:30年経過しても目標水準に届きませんでした。")


# --- 指標表示 ----------------------------------------------------------------

st.subheader("現在の社会指標")
snapshot = game.snapshot()
for category in CATEGORIES:
    keys = [k for k, ind in INDICATOR_BY_KEY.items() if ind.category == category]
    with st.expander(category, expanded=(category in ("経済", "社会・満足度"))):
        cols = st.columns(4)
        for i, key in enumerate(keys):
            ind = INDICATOR_BY_KEY[key]
            cols[i % 4].metric(f"{ind.label}", f"{snapshot[key]:.2f}{ind.unit}")

st.subheader("勝利条件 / 敗北条件")
col1, col2 = st.columns(2)
with col1:
    st.markdown("**勝利条件(すべて満たす)**")
    for k, t in game.mode.victory_conditions.items():
        ind = INDICATOR_BY_KEY[k]
        cur = snapshot[k]
        op = "≥" if ind.higher_is_better else "≤"
        ok = cur >= t if ind.higher_is_better else cur <= t
        st.write(("✅ " if ok else "▫️ ") + f"{ind.label} {op} {t} (現在 {cur:.1f})")
with col2:
    st.markdown("**敗北条件(いずれか1つで即終了)**")
    for k, t in game.mode.failure_conditions.items():
        ind = INDICATOR_BY_KEY[k]
        cur = snapshot[k]
        op = "<" if ind.higher_is_better else ">"
        st.write(f"⚠️ {ind.label} {op} {t} (現在 {cur:.1f})")


# --- 政策入力 ----------------------------------------------------------------

if game.status == "ongoing":
    st.subheader("政策を実行して1年進める")

    pending = game.pending_events()
    if pending:
        st.info(
            "今年は史実イベントの発生年です: "
            + ", ".join(f"「{e.title}」({'諸外国' if e.kind == 'foreign' else '自然災害'})" for e in pending)
        )

    policy_text = st.text_area(
        "政策内容を自由に記述してください(例: 保育所を大量増設し、女性の就労を促進する)",
        height=100,
    )

    if st.button("この政策を実行 → 1年進める", type="primary", disabled=not policy_text.strip()):
        ai_calls_this_turn = []
        try:
            with st.spinner("AIが政策の影響を分析中..."):
                policy_result = evaluate_policy(
                    game.model, game.mode.label, game.calendar_year, snapshot, policy_text
                )
            game.add_policy_effects(policy_text, policy_result.data)
            ai_calls_this_turn.append(("政策評価", policy_result))

            for event in pending:
                if event.kind == "foreign":
                    with st.spinner(f"AIが史実イベント「{event.title}」を判定中..."):
                        event_result = evaluate_historical_event(
                            game.model, game.mode.label, game.calendar_year, snapshot,
                            event.title, event.description,
                        )
                    game.add_foreign_event_effect(
                        event,
                        occurs=bool(event_result.data.get("event_occurs", True)),
                        impact_scale=int(event_result.data.get("impact_scale", 3)),
                    )
                    ai_calls_this_turn.append((f"史実イベント判定: {event.title}", event_result))
                else:  # disaster
                    game.add_disaster_effect(event)

            game.advance_year()
            st.session_state.last_ai_calls = ai_calls_this_turn
            st.rerun()
        except OllamaCallError as e:
            st.error(str(e))

# --- 直近のAI応答(モデル比較用の生データ) -----------------------------------

if st.session_state.last_ai_calls:
    with st.expander("直近のAI応答(モデル比較用・生データ)", expanded=False):
        for title, result in st.session_state.last_ai_calls:
            st.markdown(f"**{title}**  応答時間: {result.elapsed_seconds:.2f}秒  モデル: {result.model}")
            st.json(result.data)

# --- ログ --------------------------------------------------------------------

with st.expander("これまでの出来事ログ", expanded=False):
    for entry in reversed(game.log):
        st.write(f"**{entry.calendar_year}年** [{entry.kind}] {entry.title} — {entry.detail}")
