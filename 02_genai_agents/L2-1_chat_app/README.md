# L2-1 実践: 履歴つき・ストリーミング表示の CLI チャットアプリ

Microsoft Foundry のプロジェクトに接続し、**Responses API** で多ターン対話する最小の CLI チャットです。会話履歴を自前の配列で保持し、`stream=True` で逐次表示し、システムメッセージは `instructions` で毎ターン効かせます。

> 対応レクチャー：実践 `L2-1-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 履歴つき・ストリーミング表示の CLI チャット本体 |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- L1-1 でデプロイした `gpt-5.4` を使います（無い場合は、L1-1 の README 手順2でデプロイするか、`gpt-5.4-nano` に読み替え）。
- `az login` 済み ／ Python 3.11+
- **新しいリソースは作りません**。推論を数回するだけです（数円程度）。

## 進め方（コピペで実行できます）

全部で7手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 使うデプロイを確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | チャットを起動して、続けて質問する（履歴が効くことを確かめる） |
| 7 | 存在しないデプロイ名で起動して、エラー時の動きを確かめる |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-1_chat_app
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. 使うデプロイを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
`gpt-5.4` の行があればOKです。`.env` の `MODEL_DEPLOYMENT` に書くのは左の **name（デプロイ名）** です（モデルのカタログ名ではありません）。

### 3. プロジェクトのエンドポイントを取得する
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name ai103-project `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
```
返ってきた URL（末尾が `/api/projects/ai103-project`）を、手順5で `.env` に貼ります。

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
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` は最初から入っています。
> ⚠️ このレッスンのキー名は `PROJECT_ENDPOINT` と `MODEL_DEPLOYMENT` です。前のレッスンの `.env` を丸ごと写さず、値だけを移してください。

### 6. チャットを起動して、続けて質問する
```powershell
python main.py
```
`あなた>` のプロンプトが出たら、次の2つを順に入力します。2つ目は「それ」としか言っていないのに、1つ目の話題を踏まえて答えれば、**会話履歴が効いています**。
```text
Microsoft Foundry を2行で説明して
それを使うと何が楽になる？3行で
```
応答は、届いた断片から順に表示されます（ストリーミング）。`exit` で終了します。

### 7. 存在しないデプロイ名で起動して、エラー時の動きを確かめる
```powershell
$env:MODEL_DEPLOYMENT = "no-such-deployment"
python main.py
```
何か入力すると `[エラー]`（404 `DeploymentNotFound`）が表示され、**プログラムは落ちずに**次の入力を待ちます。失敗した発言は履歴から取り除かれています。`exit` で終了したら、環境変数を消しておきます。
```powershell
Remove-Item Env:MODEL_DEPLOYMENT
```
> 環境変数は `.env` より優先されます（`python-dotenv` は既定で、すでにある環境変数を上書きしません）。

## ポイント（試験の論点）
- **会話履歴は自前で配列管理**（`history` に `user`/`assistant` を積んでいく）。Responses API にはサーバー側で履歴を持つ方法（`previous_response_id` や Conversations）もあるが、このコードは毎ターン履歴をまるごと送る方式。
- システムメッセージは履歴に入れず、毎ターン `instructions` で渡す。`system` の直後に `type` を付けない `user` メッセージを置くと **400** になる（2026-09 実測）。
- `stream=True` にすると `response.output_text.delta` イベントが逐次届き、`response.completed` で終わる。途中で失敗したときは `response.failed` / `error` イベントが届くので、それも見る。最初のトークンまでの時間（TTFT）が体感で短くなる。

## つまずきポイント
| 症状 | 対処 |
|---|---|
| `DeploymentNotFound`（404） | `MODEL_DEPLOYMENT` が**デプロイ名**と一致しているか（手順2の name）。環境変数 `MODEL_DEPLOYMENT` が残っていないか（手順7の後片付け） |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| `400 Invalid value: ''` | `input` の先頭に `system` を置き、その直後に `type` なしの `user` を置いている。`instructions=` を使う |

## 後片付け
- 推論を数回するだけ（数円程度）。削除が必要なリソースはありません。
