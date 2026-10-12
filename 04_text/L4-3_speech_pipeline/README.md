# L4-3 実践: 音声パイプライン（STT → LLM → TTS）

①**STT**（音声 → テキスト）→ ②**LLM**（Responses API で答えを作る）→ ③**TTS**（テキスト → 音声）を1本につなぐハンズオンです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。Azure のリソースは新しく作りません（課金は音声の秒数・文字数・トークンの分だけです）。
>
> Codespaces にはマイクもスピーカーもありません。そこで、入力の音声は **TTS で作ったファイル** `input.wav` を使い、出力の音声は **ファイル** `output.wav` に書き出します。音が出ているかは、ファイルの長さ・サイズと、出力をもう一度 STT にかけた結果で確かめます（Codespaces のエディターで wav を開くと再生もできます）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | STT → LLM → TTS の一連の処理。`make-input` で入力の音声を作り、`stt` で任意の wav を文字起こしする |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- `az login` 済み ／ Python 3.11+
- デプロイ `gpt-5.4` があること（手順2で確かめます。無ければモデル選定のレッスン（L1-1）の README の手順2で作成）。
- **Azure Speech は、講座共通の Foundry リソースにそのまま入っています**。Speech 用のリソースを別に作る必要はありません。キーレスで呼ぶには**カスタムドメインのエンドポイント**が要ります（Foundry リソースには最初から付いています）。
- ロール：Speech の公式ページは **Cognitive Services Speech User**（または Speech Contributor）を案内していますが、Foundry の RBAC ページは Cognitive Services で始まるロールを付けないよう案内しており、公式の中で割れています。講座の収録環境では、Foundry User を持つアカウントでそのまま通りました。401 / 403 になったら、まず Foundry User が付いているかを確かめます（つまずき参照）。

## 進め方（コピペで実行できます）

全部で10手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | LLM に使うデプロイがあるか確かめる |
| 3 | Speech とプロジェクトの接続先を取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | TTS で入力の音声 `input.wav` を作る |
| 7 | パイプラインを実行する（STT → LLM → TTS） |
| 8 | 出力の `output.wav` を STT にかけて確かめる |
| 9 | わざと失敗させる（入力ファイルが無い／リージョンのエンドポイント） |
| 10 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 04_text/L4-3_speech_pipeline
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. LLM に使うデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧の Name の列に `gpt-5.4` があればOKです。STT と TTS はデプロイ不要です（Speech はモデルをデプロイせずに呼べます）。

### 3. Speech とプロジェクトの接続先を取得する
```powershell
az cognitiveservices account show --name $FOUNDRY --resource-group $RG --query "properties.endpoint" -o tsv
"https://$FOUNDRY.services.ai.azure.com/api/projects/ai103-project"
```
- 1行目の結果 `https://<リソース名>.cognitiveservices.azure.com/` が **Speech の接続先**（カスタムドメインのエンドポイント）です。
- 2行目は、リソース名から**プロジェクトの接続先**（LLM 用）を組み立てて表示します。
- **同じ Foundry リソースでも、Speech と LLM で宛先が違います**。手順5で `.env` に貼ります。

### 4. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
./.venv/bin/Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 5. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `SPEECH_ENDPOINT=` に手順3の1行目の結果、`PROJECT_ENDPOINT=` に2行目の結果を貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` は最初から入っています。

### 6. TTS で入力の音声 `input.wav` を作る
```powershell
python main.py make-input
```
```text
[準備] input.wav を作りました（5.1 秒・16000 Hz・163,246 バイト）
```
質問の文（「キーを使わずにアジュールへ接続する方法を教えてください。」）を TTS で読み上げて、`input.wav` に保存します。マイクの代わりです。別の質問にしたいときは `python main.py make-input "質問の文"` とします。秒数やバイト数は、声や文で少し変わります。

### 7. パイプラインを実行する（STT → LLM → TTS）
```powershell
python main.py
```
```text
[入力] input.wav（5.1 秒・16000 Hz・163,246 バイト）
① STT: キーを使わずにAzureへ接続する方法を教えてください。
② LLM（gpt-5.4）: Azureへはキーの代わりに Microsoft Entra ID を使って認証し、…（2文以内）
③ TTS: output.wav に書き出しました（22.1 秒・16000 Hz・708,846 バイト）
```
- ① は `input.wav` の音声を文字にした結果です。
- ② はその文字に LLM が答えたものです（実行のたびに文面は変わります）。読み上げる前提なので、instructions で「記号や箇条書きを使わず、2文以内」と頼んでいます。
- ③ は②の答えを読み上げた音声のファイルです。秒数とバイト数で、音声ができたことを確かめます。

### 8. 出力の `output.wav` を STT にかけて確かめる
```powershell
python main.py stt output.wav
```
```text
[STT] output.wav: Azureへは、キーの代わりにMicrosoft entra IDを使って認証し、…一般的です。
```
TTS で作った音声を STT で文字に戻すと、②の答えとほぼ同じ文が返ります（英字の大文字・小文字や句読点は少し変わることがあります）。**このサンプルの `recognize_once()` は、最初の1文（無音で区切られるまで）だけを認識します**。2文目以降も文字にしたいときは、連続認識（`start_continuous_recognition()`）を使います。

### 9. わざと失敗させる
入力ファイルが無い場合：
```powershell
$env:INPUT_WAV = "no-such.wav"
python main.py
Remove-Item Env:INPUT_WAV
```
```text
[エラー] FileNotFoundError: no-such.wav が見つかりません（先に make-input で作る）
```
リージョンのエンドポイント（カスタムドメインではない）を指定した場合：
```powershell
$env:SPEECH_ENDPOINT = "https://japaneast.api.cognitive.microsoft.com/"
python main.py
Remove-Item Env:SPEECH_ENDPOINT
```
```text
[エラー] RuntimeError: STT 失敗: Canceled WebSocket upgrade failed: Bad request (400). …
```
キーレス（`token_credential`）で呼ぶときは、**カスタムドメインのエンドポイントが前提**です。リージョン名のエンドポイントでは接続が拒否されます。シェルの環境変数（`$env:…`）は `.env` より優先されるので、確かめたら `Remove-Item` で消して `.env` の値に戻します。

### 10. 後片付け
このレッスンでは Azure のリソースを作っていないので、削除するものはありません。`gpt-5.4` のデプロイは後のレッスンでも使うので、残しておきます。作った音声ファイルは消しておきます。
```powershell
Remove-Item input.wav, output.wav
```

## 注意点（試験の論点）
- **キーレスの Speech SDK**：`SpeechConfig(token_credential=<資格情報>, endpoint=<カスタムドメイン>)`。STT（`SpeechRecognizer`）も TTS（`SpeechSynthesizer`）も同じ書き方です。キー認証なら `SpeechConfig(subscription=<キー>, region=<リージョン>)` です。
- **リソース ID ＋トークン（`aad#<リソースID>#<トークン>`）**：`token_credential` に対応していない場面（REST や一部の SDK 呼び出し）で使う書き方です。このサンプルでは使いません。
- **カスタムドメインは後から変更できない**：キーレスの前提なので、リソースを作るときに付けます。
- **`recognize_once()` は1発話だけ**（無音で区切られるか、最長約30秒）。長い音声や会議の文字起こしは連続認識やバッチ文字起こしを使います。
- 音声の入出力は `AudioConfig(filename=…)`／`AudioOutputConfig(filename=…)` でファイルにも、既定のマイク・スピーカーにもできます。

## つまずき
- **401 / 403**：401 はトークンや接続先（カスタムドメインか・`az login`）、403 はロールの不足を疑う。まず **Foundry User** が付いているかを確かめ、それでも通らなければ **Cognitive Services Speech User** を付けて、反映まで数分待つ。
- **STT が 400（WebSocket upgrade failed）**：`SPEECH_ENDPOINT` がリージョン名のエンドポイントになっている（手順9）。
- **NoMatch**：音声を聞き取れなかった。`input.wav` が無音でないか、言語（`ja-JP`）が合っているかを確かめる。
- **LLM が 404 DeploymentNotFound**：`MODEL_DEPLOYMENT` はカタログ名ではなく「デプロイ名」。
- **設定を変えたのに戻らない**：シェルの環境変数が `.env` より優先されている。`Remove-Item Env:<変数名>` で消す。
