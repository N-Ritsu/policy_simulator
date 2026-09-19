"""政策シミュレーションゲーム - クラウドLLM比較プロトタイプ (Streamlit)

`streamlit run app.py` で起動。OpenAI(GPT) / Google(Gemini) / Anthropic(Claude)
のいずれかを選び、選択したモデルで政策の影響評価・史実イベント判定を行う。
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from game import anthropic_client, gemini_client, openai_client
from game.ai_common import AICallError, AIResult
from game.indicators import CATEGORIES, INDICATOR_BY_KEY, MODES
from game.simulation import GameState

# .env があれば読み込む(無くてもエラーにはならない)。既存のos.environは上書きしない。
load_dotenv()

st.set_page_config(page_title="政策シミュレーションゲーム(LLM比較版)", layout="wide")

# プロバイダーごとに list_available_models / stream_policy_evaluation /
# stream_historical_event という共通インターフェースを持つモジュールを登録する。
PROVIDERS = {
    "openai": {"label": "OpenAI(GPT)", "module": openai_client, "key_env": "OPENAI_API_KEY"},
    "gemini": {"label": "Google(Gemini)", "module": gemini_client, "key_env": "GEMINI_API_KEY"},
    "anthropic": {"label": "Anthropic(Claude)", "module": anthropic_client, "key_env": "ANTHROPIC_API_KEY"},
}


# --- セッション状態の初期化 ------------------------------------------------

if "game" not in st.session_state:
    st.session_state.game = None
if "last_ai_calls" not in st.session_state:
    st.session_state.last_ai_calls = []


def start_new_game(mode_key: str, provider_key: str, model: str) -> None:
    st.session_state.game = GameState.new_game(MODES[mode_key], model, provider=provider_key)
    st.session_state.last_ai_calls = []


def render_stream(generator, label: str) -> AIResult:
    """ストリームを逐次描画しながら消費し、最終的なAIResultを返す。

    生成中の部分的なJSON・経過時間・文字数をリアルタイム表示することで、
    「今どこまで生成が進んでいるか」を可視化する。完了時には出力トークン数から
    tokens/secを算出して表示する(プロバイダー間で比較しやすいよう統一の指標)。
    """
    st.markdown(f"**{label}**")
    text_ph = st.empty()
    stat_ph = st.empty()
    result: AIResult | None = None
    for update in generator:
        text_ph.code(update.partial_content or "(生成待ち…)", language="json")
        if update.done and update.result is not None:
            result = update.result
            tps = f"{result.tokens_per_second:.1f} tok/s" if result.tokens_per_second else "計測不可"
            stat_ph.caption(
                f"✅ 完了 — 所要 {result.elapsed_seconds:.1f}秒 / "
                f"入力 {result.input_tokens or '?'} / 出力 {result.output_tokens or '?'} トークン / 速度 {tps}"
            )
        else:
            stat_ph.caption(f"⏳ 生成中… {update.elapsed_seconds:.1f}秒経過 / {len(update.partial_content)}文字")
    if result is None:
        raise AICallError(f"{label}: モデルから最終応答を受け取れませんでした。")
    return result


# --- サイドバー -------------------------------------------------------------

with st.sidebar:
    st.header("設定")

    provider_key = st.selectbox(
        "プロバイダー",
        options=list(PROVIDERS.keys()),
        format_func=lambda k: PROVIDERS[k]["label"],
    )
    provider_info = PROVIDERS[provider_key]

    key_env = provider_info["key_env"]
    if os.environ.get(key_env):
        st.caption(f"✅ {key_env} を .env / 環境変数から読み込み済み")
    entered_key = st.text_input(
        f"{key_env}(.env設定済みなら空欄でOK)", type="password",
        help="ここに入力すると、このセッション中だけ上書きされます(保存されません)。",
    )
    if entered_key:
        os.environ[key_env] = entered_key
    key_ready = bool(os.environ.get(key_env))
    if not key_ready:
        st.warning(f"{key_env} が未設定です。.envに書くか、上の欄にAPIキーを入力してください。")

    model = st.selectbox("モデル", provider_info["module"].list_available_models())

    mode_key = st.selectbox(
        "モード",
        options=list(MODES.keys()),
        format_func=lambda k: MODES[k].label,
    )

    if st.button("新しいゲームを開始", disabled=not key_ready, type="primary"):
        start_new_game(mode_key, provider_key, model)
        st.rerun()

    st.divider()
    st.caption(
        "OpenAI(GPT) / Google(Gemini) / Anthropic(Claude) の出力傾向・速度・コストを"
        "比較するための簡易版です。政策効果はガウス型インパルスとして各指標に加算されます。"
    )


game: GameState | None = st.session_state.game

if game is None:
    st.title("政策シミュレーションゲーム")
    st.write("左のサイドバーでプロバイダー・モデル・モードを選び、「新しいゲームを開始」を押してください。")
    st.stop()


# --- ヘッダー ----------------------------------------------------------------

st.title(game.mode.label)
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("西暦", f"{game.calendar_year}年")
col_b.metric("経過年数", f"{game.year_index} / {game.mode.duration_years}年")
col_c.metric("プロバイダー", PROVIDERS[game.provider]["label"])
col_d.metric("使用モデル", game.model)

if game.status != "ongoing":
    end_detail = game.log[-1].detail
    if game.status == "win":
        st.success(f"🎉 クリア!{end_detail}")
    elif game.status == "lose_border":
        st.error(f"💥 ゲームオーバー:{end_detail}")
    else:
        st.error(f"⏱ ゲームオーバー:{end_detail}")

latest_policy = game.latest_policy_log()
if latest_policy:
    st.info(f"**{latest_policy.calendar_year}年の{latest_policy.title}**\n\n総評: {latest_policy.detail}")


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
    st.markdown(f"**クリア条件({game.mode.duration_years}年経過時点で、すべて満たす)**")
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
        game_module = PROVIDERS[game.provider]["module"]

        progress_area = st.container()
        try:
            with progress_area:
                policy_result = render_stream(
                    game_module.stream_policy_evaluation(
                        game.model, game.mode, game.calendar_year, snapshot, policy_text,
                    ),
                    "政策の影響を分析中",
                )
            game.add_policy_effects(policy_text, policy_result.data)
            ai_calls_this_turn.append(("政策評価", policy_result))

            for event in pending:
                if event.kind == "foreign":
                    with progress_area:
                        event_result = render_stream(
                            game_module.stream_historical_event(
                                game.model, game.mode, game.calendar_year, snapshot,
                                event.title, event.description,
                            ),
                            f"史実イベント判定: {event.title}",
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
        except AICallError as e:
            st.error(str(e))

# --- 直近のAI応答(モデル比較用の生データ) -----------------------------------

if st.session_state.last_ai_calls:
    with st.expander("直近のAI応答(モデル比較用・生データ)", expanded=False):
        for title, result in st.session_state.last_ai_calls:
            tps = f"{result.tokens_per_second:.1f} tok/s" if result.tokens_per_second else "?"
            st.markdown(
                f"**{title}**  プロバイダー: {result.provider}  モデル: {result.model}  "
                f"所要: {result.elapsed_seconds:.2f}秒  "
                f"入力: {result.input_tokens or '?'} / 出力: {result.output_tokens or '?'} トークン  速度: {tps}"
            )
            st.json(result.data)

# --- ログ --------------------------------------------------------------------

with st.expander("これまでの出来事ログ", expanded=False):
    for entry in reversed(game.log):
        st.write(f"**{entry.calendar_year}年** [{entry.kind}] {entry.title} — {entry.detail}")
