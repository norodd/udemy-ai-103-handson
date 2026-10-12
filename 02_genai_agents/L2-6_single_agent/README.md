# L2-6 実践: 単一エージェントの作成と実行（Code Interpreter付き）

`PromptAgentDefinition`（model / instructions / tools）で組み込みツール **Code Interpreter** 付きのエージェントを定義し、会話に紐づけて多ターンで対話するハンズオンです。計算が必要な質問では、モデルが Code Interpreter を呼び、Python のコードを書いて実行させます。

> 対応レクチャー：実践 `L2-6-3`
>
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。会話とエージェントは `finally` で削除され、プロジェクトに残りません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | エージェントの作成・会話（複数ターン）・ツール呼び出しの表示・会話とエージェントの削除（`finally`） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- L1-1 でデプロイした `gpt-5.4` を使います（Code Interpreter に対応。無い場合は L1-1 の README 手順2でデプロイ）。
- `az login` 済み ／ Python 3.11+
- **新しいリソースは作りません**。推論を数回するだけです。ただし **Code Interpreter はトークン料金とは別に、セッション単位で課金**されます（Code Interpreter を呼んだ会話ごとに1セッション。むやみに実行し直さないのが節約になります）。

## 進め方（コピペで実行できます）

全部で8手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 使うデプロイを確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 既定の2問で実行する（Code Interpreter が呼ばれる） |
| 7 | 簡単な計算で実行する（たいていツールは呼ばれない） |
| 8 | 後片付けを確かめる |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-6_single_agent
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
`gpt-5.4` の行があればOKです。`.env` の `MODEL_DEPLOYMENT` に書くのは左の **name（デプロイ名）** です（モデルのカタログ名ではありません）。エージェントに持たせるツールとモデルには相性があり、Code Interpreter は `gpt-5.4` で使えます（公式のツール対応表）。

### 3. プロジェクトのエンドポイントを取得する
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name ai103-project `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
```
返ってきた URL（末尾が `/api/projects/ai103-project`）を、手順5で `.env` に貼ります。エージェントはプロジェクトに属するので、入口はリソースではなく**プロジェクトのエンドポイント**です。

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

### 6. 既定の2問で実行する（Code Interpreter が呼ばれる）
```powershell
python main.py
```
エージェントを作り、同じ会話で2問続けて聞き、最後に会話とエージェントを削除します。
```text
エージェント作成: name=single-tool-agent, version=1

あなた> 1 から 10000 までの素数の個数と合計を計算して。
[ツール] 1 件 code_interpreter_call
    | def is_prime(n):
    |     if n < 2:
    |         return False
AI> 1 から 10000 までの素数の個数は 1229個 です。その合計は 5,736,396 です。

あなた> その合計を個数で割ると？
[ツール] 1 件 code_interpreter_call
    | 5736396/1229
AI> 合計を個数で割ると 4667.53... です。

会話とエージェントを削除しました（残り: 0 件）
```
- `[ツール]` の行は、応答に入っていたツール呼び出しです。`code_interpreter_call` の下の `|` の行は、**モデルが書いて Code Interpreter に実行させた Python コード**の先頭です。
- 2問目は「その合計」としか言っていないのに、1問目の数字を使って計算しています。同じ会話（`conversation`）に紐づけて呼んでいるので、**会話の履歴はサーバー側が持っています**。
- 2問目は割り算1回で済むので、**ツールを呼ばずに答えることもあります**（`[ツール] 0 件`）。ツールを呼ぶかどうかは、ターンごとにモデルが決めます。1問目でモデルが書くコードも、実行のたびに変わります（`sympy` を使うこともあります）。
- 答えの文面は実行のたびに変わります。確かめるのは数字と `[ツール]` の行です。`version` は、同じ名前のエージェントが別に残っていると 1 以外になることがあります。

### 7. 簡単な計算で実行する（たいていツールは呼ばれない）
```powershell
python main.py "127 と 358 と 921 の合計は？" "それを3で割ると？"
```
引数を渡すと、その質問に差し替わります（`main.py` は編集しません）。
```text
あなた> 127 と 358 と 921 の合計は？
[ツール] 0 件
AI> 127 + 358 + 921 = 1406 です。
```
暗算で足りる計算では、たいていツールは呼ばれません（呼ばれる回もあります）。**ツールを持たせても、使うかどうかを決めるのはモデル**です（`tool_choice` の既定は `auto`）。instructions に「計算には Code Interpreter を使って」と書いてあってもこの結果で、**instructions は判断材料にすぎず、呼び出しを保証しません**。必ず使わせたいときは、`tool_choice` を `required` にして強制します（[Tool best practices](https://learn.microsoft.com/azure/foundry/agents/concepts/tool-best-practice)）。

### 8. 後片付けを確かめる
手順6・7の最後の行 `会話とエージェントを削除しました（残り: 0 件）` が、後片付けの確認です。`main.py` は `finally` で、会話（`conversations.delete`）と、作ったエージェントの版（`delete_version`）を削除し、同じ名前のエージェントが一覧に残っていないかを数えて表示します。途中でエラーが出ても `finally` は必ず走るので、エージェントや会話がプロジェクトに溜まりません。

## ポイント（試験の論点）
- 定義は **model / instructions / tools** の3点（`PromptAgentDefinition`）。実行のランタイムは Foundry 側が持ち、アプリは `agent_reference` で呼ぶだけ。
- **会話（conversation）が多ターンの記憶**。同じ `conversation.id` で呼べば、前の答えを前提にできる（アプリ側で履歴を積まない）。
- **ツールを選ぶのはモデル**。組み込みツール（Code Interpreter）は Foundry 側で実行される（関数ツールと違い、アプリが実行して結果を返す必要はない）。
- `azure-ai-projects` 2.x は **agents（名前と版）＋ conversations ＋ responses** の形。1.x の threads / runs とは別物。
- 作ったものは **`finally` で片付ける**（エージェントは課金されないが、溜まると管理が崩れる）。

## つまずき
| 症状 | 対処 |
|---|---|
| `DeploymentNotFound`（404） | `MODEL_DEPLOYMENT` が**デプロイ名**と一致しているか（手順2の name） |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| `[ツール] 0 件` で困る | 必ず使わせたいなら `tool_choice` を `required` に（instructions では保証されない） |
| ツールが使えない旨のエラー | モデルとツールの相性。公式のツール対応表で、そのモデルが Code Interpreter に対応しているか |
| `[ツール] 0 件` なのに数字が合っている | 暗算で済むとモデルが判断した（手順7）。誤りではない |

## 後片付け
- エージェントと会話は実行のたびに `finally` で削除されます（手順8）。削除が必要なリソースはありません。
- Code Interpreter のセッションは、Code Interpreter を呼んだ会話ごとに1つ作られ、既定で1時間有効・30分操作が無いと終わります。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。
