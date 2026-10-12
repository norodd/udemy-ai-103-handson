# L4-4 実践: Voice Live で会話できる音声エージェント

Foundry エージェントに **Voice Live の設定**（声・話し終わりの検出・ノイズ抑制）を持たせて作り、**Voice Live** 経由でそのエージェントと**声で1往復**するハンズオンです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。**エージェント経由の Voice Live はキー認証に対応していない**ので、Entra ID が必須です。Azure のリソースは新しく作りません（作るのはエージェントだけで、手順10で消します）。
>
> Codespaces にはマイクもスピーカーもありません。そこで、**マイクの代わりに音声ファイル `input.wav` を少しずつ送り**、エージェントの声は**ファイル `reply.wav` に保存**します。声が返ってきたことは、文字起こしとファイルの長さ・サイズで確かめます（Codespaces のエディターで wav を開くと再生もできます）。マイクとスピーカーがある自分の PC なら、Foundry ポータルのエージェントの Playground で声の会話を試せます。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `create_agent_with_voicelive.py` | Voice Live 設定つきのエージェントを作る（`delete` で消す） |
| `voice_live_agent.py` | Voice Live でエージェントに接続し、声で1往復する。`make-input` で入力の音声を作る |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-voicelive` の非同期接続には `aiohttp` が必要） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- `az login` 済み ／ Python 3.11+
- デプロイ `gpt-5.4` があること（手順2で確かめます。無ければモデル選定のレッスン（L1-1）の README の手順2で作成）。
- Voice Live は、講座共通の Foundry リソースにそのまま入っています（リソースのリージョンが Voice Live のエージェント連携に対応している必要があります。講座の `japaneast` は対応）。キーレスで呼ぶには**カスタムドメインのエンドポイント**が要ります（Foundry リソースには最初から付いています）。
- ロール：エージェントの作成も、エージェント経由の Voice Live への接続も、公式のエージェント版クイックスタートの前提は **Foundry User** です（講座の収録環境でも Foundry User だけで通りました）。モデルに直接つなぐ版のクイックスタートは **Cognitive Services User** を案内しているので、401 / 403 になったら Foundry リソースにこちらも付けてください（つまずき参照）。

## 進め方（コピペで実行できます）

全部で10手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | エージェントに使うデプロイがあるか確かめる |
| 3 | Voice Live とプロジェクトの接続先を取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | Voice Live 設定つきのエージェントを作る |
| 7 | TTS で入力の音声 `input.wav` を作る |
| 8 | Voice Live でエージェントと声で1往復する |
| 9 | わざと失敗させる（存在しないエージェント名） |
| 10 | 後片付け（エージェントと音声ファイルを消す） |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 04_text/L4-4_voice_live
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. エージェントに使うデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧の Name の列に `gpt-5.4` があればOKです。音声モデルのデプロイは要りません（Voice Live は音声の認識・合成をサービス側でまとめて持っています）。

### 3. Voice Live とプロジェクトの接続先を取得する
```powershell
az cognitiveservices account show --name $FOUNDRY --resource-group $RG --query "properties.endpoint" -o tsv
"https://$FOUNDRY.services.ai.azure.com/api/projects/ai103-project"
```
- 1行目の結果 `https://<リソース名>.cognitiveservices.azure.com/` が **Voice Live の接続先**です。**ホスト名の先頭がリソース名**になっているのが、カスタムドメインのエンドポイントの目印です（`japaneast.api.cognitive.microsoft.com` のようなリージョン名のエンドポイントでは、キーレスで接続できません）。
- 2行目は、同じリソース名にプロジェクトのパス（`/api/projects/…`）を付けた**プロジェクトの接続先**（エージェントを作る側）を組み立てて表示します。
- **同じ Foundry リソースでも、Voice Live とプロジェクトで宛先が違います**。手順5で `.env` に貼ります。

### 4. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 5. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順3の2行目の結果、`VOICELIVE_ENDPOINT=` に1行目の結果を貼って保存します。`PROJECT_NAME=ai103-project`・`AGENT_NAME=ai103-voice-agent`・`MODEL_DEPLOYMENT_NAME=gpt-5.4` は最初から入っています。

### 6. Voice Live 設定つきのエージェントを作る
```powershell
python create_agent_with_voicelive.py
```
```text
Agent created: ai103-voice-agent (version 1)
  モデル: gpt-5.4 ／ Voice Live 設定: 422 字 → metadata 1 個に分割
```
エージェントの定義（モデルと指示）に、Voice Live の設定（声・話し終わりの検出・ノイズ抑制）を **metadata** として付けて作ります。metadata の値は1つ 512 字までなので、長い設定は分割して入れる作りにしてあります（今回の設定は1個に収まります）。定義が前回とまったく同じなら、もう一度実行しても版の番号は増えません。

### 7. TTS で入力の音声 `input.wav` を作る
```powershell
python voice_live_agent.py make-input
```
```text
入力の音声を作りました: input.wav（4.0 秒・189,644 バイト）
```
質問の文（「おすすめの休日の過ごし方を一つ教えてください。」）を Azure Speech の TTS で読み上げて、`input.wav` に保存します。マイクの代わりです。Voice Live の PCM16 の既定（24kHz・16bit・モノラル）に合わせて作ります。別の質問にしたいときは `python voice_live_agent.py make-input "質問の文"` とします。

### 8. Voice Live でエージェントと声で1往復する
```powershell
python voice_live_agent.py
```
```text
[1] session.updated … 接続・認証・エージェント指定が通った
[2] speech_started … 話し始めを検出
[3] speech_stopped … 話し終わりを検出（ここで応答が始まる）
    あなた（文字起こし）: おすすめの休日の過ごし方を一つ教えてください。
  → 音声を送り終えました（60 回に分けて送信）
    エージェント（声の文字起こし）: 朝に近所をゆっくり散歩して、…（2文以内）
[4] response.done … 1往復が完了
返事の音声を保存しました: reply.wav（14.0 秒・670,844 バイト）
受け取った声の断片（response.audio.delta）: 29 個
```
- `[1]`〜`[4]` の番号は、**コードが主な知らせに付けた見出し**で、サービスが送るイベントの順番そのものではありません（接続の直後には `session.created` が届き、`response.created` なども届いていますが、表示していません）。
- `[1]` の **`session.updated`** は、こちらが送った `session.update` にサービスが応えた知らせで、接続・認証・エージェントの指定・セッション設定が通った目印です。これが届いてから音声を送り始めます。
- `input.wav` を 0.1 秒ずつ送り、最後に2秒の無音を足します。**話し始め `[2]` と話し終わり `[3]` は、サービス側の検出（VAD）が判断します**。コードは「ここで答えて」とは指示していません。
- 「あなた」はサービスが入力の声を文字にしたもの、「エージェント」は返事の声を文字にしたものです（返事の文面は実行のたびに変わります）。
- 返事の声は細かい断片（`response.audio.delta`）で届きます。それをつないで `reply.wav` に保存しています。

### 9. わざと失敗させる（存在しないエージェント名）
```powershell
$env:AGENT_NAME = "no-such-agent"
python voice_live_agent.py
Remove-Item Env:AGENT_NAME
```
```text
[エラーイベント] Agent no-such-agent not found.
受け取った声の断片（response.audio.delta）: 0 個
```
エージェント名を間違えても、**接続そのものは開き**、そのあと **`error` イベント**として届きます（例外にはなりません）。`session.updated` は返らないので、声も返りません。シェルの環境変数（`$env:…`）は `.env` より優先されるので、確かめたら `Remove-Item` で消して `.env` の値に戻します。

### 10. 後片付け（エージェントと音声ファイルを消す）
```powershell
python create_agent_with_voicelive.py delete
Remove-Item input.wav, reply.wav
```
```text
Agent deleted: ai103-voice-agent（同じ名前の残り: 0 件）
```
エージェントは残しておくだけでは課金されませんが、使い終わったら消しておきます。`gpt-5.4` のデプロイは後のレッスンでも使うので、残しておきます。

## 注意点（試験の論点）
- **エージェント経由の Voice Live はキー認証に対応していない**。Entra ID（`DefaultAzureCredential` など）で接続する。
- **エージェントの指定は `connect()` のキーワード引数** `agent_name=` と `project_name=`（必要なら `agent_version=`・`conversation_id=`。版を省くと最新の版が使われる）。
- **声・話し終わりの検出（VAD）・ノイズ抑制は、エージェントの metadata に Voice Live 設定として持たせられる**。クライアントは「どのエージェントか」を指定するだけでよい。
- **話し終わりの検出の種類**：Azure の意味で判定する種類を使うなら、日本語を含む多言語は `azure_semantic_vad_multilingual`（multilingual の付かない `azure_semantic_vad` は英語向け）。話し終わりの判定モデルも `semantic_detection_v1_multilingual` を使う。
- **接続できたかの目印は `session.updated`**。名前の間違いなどは、接続のあとに `error` イベントで届く。
- **このコードの入出力の音声は、PCM16 の既定（24kHz・16bit・モノラル）**。入力は G.711（`g711_ulaw`／`g711_alaw`）、出力は `pcm16_16000hz` などほかの形式も選べる。声は `response.audio.delta` の断片で届く。
- `api_version="2026-01-01-preview"` は、公式のエージェント版クイックスタートのサンプルと同じ版です。Voice Live は API の版の更新が速いので、版を明示して書きます。

## つまずき
- **401 / 403**：多くはロールが足りない。`az login` 済みか、エンドポイントがカスタムドメイン（先頭がリソース名）かを確かめ、それでも出るなら Foundry リソースに **Cognitive Services User** を付けて、反映まで数分待つ。
- **`[エラーイベント] Agent … not found.`**：`AGENT_NAME` が違うか、手順6を実行していない（手順9）。
- **`ConnectionError`（WebSocket の接続に失敗、400）**：`VOICELIVE_ENDPOINT` がリージョン名のエンドポイント（`https://japaneast.api.cognitive.microsoft.com/` など）になっている。カスタムドメインにする。
- **`[4] response.done` まで行かない**：入力の音声が無音でないか確かめる（手順7で作り直す）。
- **`ImportError`（aiohttp 関連）**：`azure-ai-voicelive` の非同期接続には `aiohttp` が必要。`requirements.txt` どおりに入っているか確かめる。
- **設定を変えたのに戻らない**：シェルの環境変数が `.env` より優先されている。`Remove-Item Env:<変数名>` で消す。
