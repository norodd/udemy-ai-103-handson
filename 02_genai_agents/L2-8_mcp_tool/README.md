# L2-8 実践: リモート MCP サーバーのツールをエージェントに接続する

**GitHub の MCP サーバー**（リモート）を `MCPTool` でエージェントに宣言し、ツールを呼ぶ前に**承認フロー**（`mcp_approval_request` → `mcp_approval_response`）を自分のコードで挟むハンズオンです。GitHub への認証情報（PAT）はコードにも `.env` にも書かず、Foundry プロジェクトの**接続**に持たせます。

> 対応レクチャー：実践 `L2-8-3`
> Foundry への認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。会話とエージェントは `finally` で削除され、プロジェクトに残りません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 接続の確認、`MCPTool` の宣言（許可リスト `get_me`・承認は毎回）、承認要求を `y`/`N` で処理する流れ、後片付け（`finally`） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- `az login` 済み ／ Python 3.11+
- モデルは `gpt-5.4` を使います。Foundry Agent Service の「Tool support by region and model」（エージェントに持たせるツールの対応表）で、`gpt-5.4` は **MCP が Yes** です（関数ツールの Functions は No なので、L2-7 とは使えるモデルが違います）。講座の `japaneast` も MCP が yes です。
- GitHub のアカウント。
- 接続を作るには、プロジェクトに **Foundry Project Manager** 以上のロールが要ります（公式の MCP ツールのページの前提）。

## 🔴 事前準備（コードの前に、自分で行う）
**A. GitHub の Personal access token（PAT）を作る**
- GitHub → Settings → Developer settings → Personal access tokens で作ります。公式のサンプルは Tokens (classic) で「公開リポジトリの読み取り」程度の権限です。このハンズオンで呼ぶのは自分のユーザー情報を返す `get_me` だけなので、**権限は最小に、有効期限は短く**します。
- トークンは作成した画面でしか表示されません。次の B で貼るまで控えておきます。

**B. Foundry ポータルでプロジェクトの接続を作る**
- ai.azure.com で `ai103-project` を開き、**ビルド → ツール → ツールを接続 → カスタム → モデル コンテキスト プロトコル (MCP)** と進みます。
- 名前 `github-mcp`、エンドポイント `https://api.githubcopilot.com/mcp`、認証は**キーベース**、資格情報の名前 `Authorization`、値 `Bearer <PAT>`（`Bearer` の後ろに半角スペース）。
- 作った接続の種類は、コードからは `RemoteTool`、認証の形式は Custom keys に見えます。
- ⚠️ 接続に入れたキーは、そのプロジェクトにアクセスできる人なら中身を見られます（公式の注記）。共有してよい資格情報だけを入れます。

## 進め方（コピペで実行できます）

全部で8手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | `gpt-5.4` のデプロイを確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 実行して、ツールの呼び出しを承認する（`y`） |
| 7 | もう一度実行して、今度は拒否する（`N`） |
| 8 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-8_mcp_tool
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. `gpt-5.4` のデプロイを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧に `gpt-5.4` があればOKです（L1-1 で作成済み）。

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
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 5. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` と `MCP_CONNECTION_NAME=github-mcp` は最初から入っています（事前準備 B で別の名前にしたときは、その名前に直します）。PAT はどこにも書きません。

### 6. 実行して、ツールの呼び出しを承認する（`y`）
```powershell
python main.py
```
承認を聞かれたら `y` を入力して Enter を押します。
```text
接続: github-mcp（種類: RemoteTool）
エージェント作成: name=mcp-agent, version=1, model=gpt-5.4

USER> 私の GitHub のユーザー名は？
[応答1] mcp_list_tools 1 件 / mcp_approval_request 1 件
[ツール一覧] server=github 1 件: get_me
[承認要求] server=github tool=get_me arguments={}
このMCPツール呼び出しを承認しますか？ (y/N): y
[応答2] mcp_call 1 件 / message 1 件
[MCP 呼び出し] tool=get_me 結果 388 文字
AI> あなたの GitHub ユーザー名は <あなたのユーザー名> です。
会話とエージェントを削除しました（残り: 0 件）
```
- `接続: … RemoteTool` は、接続の**名前と種類だけ**を確かめた行です。PAT の値は取り出していません。
- `[ツール一覧]` は、エージェントが MCP サーバーから取り寄せたツールの一覧です。`allowed_tools=["get_me"]` で許可リストを絞っているので、1件だけが並びます。
- `[承認要求]` は「このツールをこの引数で呼びたい」という依頼です。`require_approval="always"` なので、**まだ呼ばれていません**。
- `y` で承認を返すと、Foundry が接続の資格情報を付けて GitHub の MCP サーバーの `get_me` を呼び、`[MCP 呼び出し]` の行が出ます。ツールの一覧は承認の前に取り寄せ済みで、承認で止めているのはツールの実行です。答えのユーザー名は、そのツールの結果から来ています。結果の文字数や答えの文面は実行ごとに変わります。

### 7. もう一度実行して、今度は拒否する（`N`）
```powershell
python main.py
```
承認を聞かれたら `N`（または何も入れずに Enter）を押します。
```text
[承認要求] server=github tool=get_me arguments={}
このMCPツール呼び出しを承認しますか？ (y/N): N
[応答2] message 1 件
AI> GitHub 連携の承認が必要です。承認いただければ、あなたの GitHub ユーザー名を確認できます。
会話とエージェントを削除しました（残り: 0 件）
```
`[応答2]` に `mcp_call` が無く、ツールは呼ばれていません。答えの文面は実行のたびに大きく変わります。確かめるのは文面ではなく、**`mcp_call` が無いこと**です。

### 8. 後片付け
- 手順6・7の最後の行 `会話とエージェントを削除しました（残り: 0 件）` が、エージェントと会話が残っていないことの確認です。
- 講座を終えたら、GitHub で **PAT を失効**（Revoke）します。接続 `github-mcp` は、ほかのレッスンでは使わないので、ポータルの ビルド → ツール から削除してかまいません。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。

## ポイント（試験の論点）
- **MCP サーバーへの認証は、プロジェクトの接続に持たせる**（`project_connection_id`）。コードや `.env` に PAT を書かない。Foundry への認証（キーレス）とは別の話です。
- **`require_approval`**：`always` なら、呼ぶ前に必ず `mcp_approval_request` が返ります。承認は `mcp_approval_response`（`approve` と `approval_request_id`）で、`previous_response_id` を付けて返します。書き込みや変更をするツールには承認を求めるのが公式のベストプラクティスです。
- **`allowed_tools`** で、MCP サーバーが公開するツールのうち使ってよいものを許可リストで絞ります（最小権限）。
- MCP サーバーが返すツールの説明や結果は、**信頼できない入力**として扱います（間接プロンプトインジェクションの経路になりうる）。
- ツールが使えるかは、**モデルとリージョンの両方**で決まります（ツール対応表）。MCP は `gpt-5.4` で Yes、関数ツールは No、と種類ごとに違います。
- 非ストリーミングの MCP ツール呼び出しは、100 秒でタイムアウトします（公式の既知の制限）。

## つまずき
| 症状 | 対処 |
|---|---|
| `[エラー] ResourceNotFoundError`（接続の確認の行） | `MCP_CONNECTION_NAME` が事前準備 B の接続名と一致しているか |
| 最初の応答か承認後の呼び出しで、`[エラー]` や `[MCP 呼び出し] … エラー`、`401`/`Unauthorized` が出る | PAT の失効・権限不足、または接続の値が `Bearer <PAT>` の形になっていない。接続の値を作り直す（ツールの一覧は承認の前に取り寄せるので、認証のエラーが最初の応答で出ることもある） |
| `[応答1]` に `mcp_approval_request` が無く、ツールを使わずに答える | `require_approval` が `always` か。質問が GitHub の情報を必要としていない可能性。質問を変える。`MODEL_DEPLOYMENT` が MCP 対応のモデルか（ツール対応表） |
| `DeploymentNotFound`（404） | `.env` の `MODEL_DEPLOYMENT` が手順2の一覧のデプロイ名と一致しているか |
| `401`/`403`（エージェントの作成で） | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| 接続を作れない | プロジェクトに **Foundry Project Manager** 以上のロールがあるか |

## 後片付け
- エージェントと会話は実行のたびに `finally` で削除されます（手順8）。
- **PAT を GitHub 側で失効**（Revoke）します。接続 `github-mcp` は削除してかまいません。
