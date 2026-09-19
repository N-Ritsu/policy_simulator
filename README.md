# 政策シミュレーションゲーム(クラウドLLM比較プロトタイプ)

`設計資料/` の構想(バブル期モード・現代モード、50社会指標、AIによる政策影響評価・
史実イベント判定)の**モデル比較用プロトタイプ**。OpenAI(GPT) / Google(Gemini) /
Anthropic(Claude) を切り替えて、同じプロンプト・同じJSON Schemaでの出力傾向や
速度・コストを見比べられる。

## できること

- モード選択: バブル期モード(1988年開始) / 現代モード(2000年開始)、各30年間
- 開始時に約50個の社会指標(GDP・出生率・国民満足度・健康寿命など)を表示
- 自由記述の政策を入力 → AIに「良い影響3つ・悪い影響3つ」をJSON Schemaで出力させ、
  ガウス型の山として各指標に反映する。各影響は次の5項目を持つ:
  - `description` 影響の内容
  - `target_indicators` 影響を受ける指標(1〜3個)
  - `peak_year` 山のピーク(何年後か、正規分布の平均μ)
  - `duration` 山のばらつき(short / medium / long、σに相当)
  - `magnitude` 山そのものの大きさ(1:微小〜3:標準〜5:甚大)。山の面積(=指標が最終的に
    動く総量)が「指標ごとの基準量 × magnitude/3 × 全体倍率」になる。`duration`は山の
    広がりだけを決め、長く続くからといって総量は増えない
- 影響の6件に続けて、最後に `overall_review`(政策への総評)をAIに出力させ、
  1年進めたあとに画面上部へ表示する(ゲームログにも残る)
- 「良い影響」は指標が良い方向に動く効果として扱う。失業率・債務残高など
  「低いほど良い指標」では値が減る方向に、「悪い影響」では逆に動く
- 台本化された史実イベント(諸外国の出来事・自然災害)を年ごとに発生させ、
  諸外国の出来事は「史実通り発生するか / 影響度1〜5」をAIに判定させる。
  自然災害は史実通り必ず発生し、耐災害指数で被害を軽減する
- AIには、モードごとの舞台設定(時代背景・経済状況・国民の意識・技術水準・ゲームの目標)と
  「当時の感覚・当時の経済規模に対する比率で評価する」「後知恵で判断しない」という前提を
  システムプロンプトで与える(`game/indicators.py` の `scenario_context`)。
  同じ「1兆円の政策」でも、バブル期と2000年とでは規模感や国民の受け止め方が変わる
- クリア判定は**30年経過時点のみ**(途中で条件を満たしても即クリアにはならない)。
  30年後に全条件を満たせばクリア、未達ならゲームオーバー(未達の項目が表示される)。
  指標が破綻ラインを割る/超えた場合は、その時点でゲームオーバー
- クリア条件は複数指標の同時達成を要求する厳しめの設定。乱数プレイヤーによる
  シミュレーションで、全政策をクリア条件に集中させても勝率が1割前後になるよう調整している
- 直近のAI応答(生JSON・所要時間・入出力トークン数・tokens/sec)を画面に表示し、
  生成中は途中経過のJSONをリアルタイム表示する

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

APIキーは `.env` に書く(`.env.example` をコピーして編集)か、アプリ起動後にサイドバーの
パスワード欄へ入力する(入力分はセッション中のみ有効で、ファイルには保存されない)。

```bash
cp .env.example .env
```

```
OPENAI_API_KEY=...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
```

**`.env` は `.gitignore` 済み。誤って `git add -f` しないこと。** 比較したいプロバイダーの
キーだけ設定すればよい。

```bash
streamlit run app.py
```

## ディレクトリ構成

```
app.py                 Streamlit UI(プロバイダー選択・進捗可視化)
game/
  indicators.py        50社会指標の定義、モード別初期値・勝敗条件
  events.py            史実イベント(諸外国の出来事・自然災害)の台本データ
  prompts.py           プロバイダー非依存のプロンプトとJSON Schema
  ai_common.py          AIResult / StreamUpdate / AICallError(全プロバイダー共通の型)
  openai_client.py      OpenAI(Responses API)呼び出しラッパー
  gemini_client.py      Google Gemini(Interactions API)呼び出しラッパー
  anthropic_client.py   Claude(Messages API)呼び出しラッパー
  simulation.py         年次進行ロジック(効果の重ね合わせ・勝敗判定)
```

各プロバイダーのクライアントは同じインターフェース
(`list_available_models` / `stream_policy_evaluation` / `stream_historical_event`)を持つ。

JSON Schemaは3社の構造化出力すべてで通るよう、全オブジェクトに
`additionalProperties: false`・全項目 `required`・`minimum`/`maxItems` 等の制約なし、
に揃えている。値の範囲(peak_year 0〜29、magnitude 1〜5など)はdescriptionで伝え、
コード側(`simulation.py`)でclampしている。

## 既知の制約(プロトタイプゆえの簡略化)

- 史実イベントは各モード5件のみ台本化(サンプル)。増やす場合は `game/events.py` に追記
- 指標の初期値・勝敗条件のしきい値・`impact_unit` は仮置きの値。バランス調整は別途必要
- OpenAI(Responses API)・Gemini(Interactions API)は比較的新しいAPIで仕様変更が速い。
  ストリーミング解析に失敗した場合は非ストリーミングに自動フォールバックするが、
  エラーが出たら各 `*_client.py` の `_stream_json` を調整する
