# L2-9 実践: Microsoft Agent Framework で主＋専門エージェントを協調させる（Magentic）

**マネージャー（主）エージェント**が、専門エージェント（調査担当・執筆担当）の中から**次に誰を呼ぶかをその都度決めて**タスクを委譲し、成果を統合する **Magentic** オーケストレーションのハンズオンです。`azure-ai-projects` ではなく **Microsoft Agent Framework**（`agent_framework`）を使います。

> 対応レクチャー：実践 `L2-9-3`
> 認証は**キーレス**（`az login` ＋ `AzureCliCredential`）。このコードは Foundry Agent Service にエージェントを登録しません（`FoundryChatClient` がモデルを直接呼ぶ）。後片付けで消すものはありません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 調査担当（社内規程を調べる関数ツール `lookup_policy` 付き）・執筆担当・マネージャーを作り、Magentic ワークフローを組み立てて、ストリーミングで進行を表示する。最後に調整ラウンドと委譲の回数を表示する |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`agent-framework-foundry`／`agent-framework-orchestrations` ほか） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- **`az login` 済み**（このコードは `AzureCliCredential` を使うので、`az login` のサインインだけで動きます）／ Python 3.11+
- モデルは **`gpt-5.4`**（L1-1 で講座共通のプロジェクトにデプロイ済み）。
- ⚠️ **Agent Framework は活発に進化中**です。クラス名・引数が変わることがあるので、動かないときは公式サンプルで最新の書き方を確かめてください：https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/orchestrations
  （このコードの動作確認：2026-09-24、`agent-framework-core` 1.19.0 ／ `-foundry` 1.13.1 ／ `-orchestrations` 1.2.0）

## 進め方（コピペで実行できます）

全部で8手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | `gpt-5.4` のデプロイがあるか確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 調べて書く仕事を頼む（調査担当 → 執筆担当） |
| 7 | 調べなくてよい仕事を頼む（マネージャーが担当を選び直す） |
| 8 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-9_multi_agent
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. `gpt-5.4` のデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧の Name 列に `gpt-5.4` があればOKです。`.env` に書くのは、この **Name 列（デプロイ名）** です。

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
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。Agent Framework は部品ごとにパッケージが分かれていて、Magentic は `agent-framework-orchestrations` に入っています。

### 5. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `FOUNDRY_PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`FOUNDRY_MODEL=gpt-5.4` は最初から入っています。
> ⚠️ このレッスンの変数名は `FOUNDRY_PROJECT_ENDPOINT` と `FOUNDRY_MODEL` です。前のレッスンの `.env` を写すと、名前が `PROJECT_ENDPOINT`／`MODEL_DEPLOYMENT` のままになって動きません。

### 6. 調べて書く仕事を頼む（調査担当 → 執筆担当）
```powershell
python main.py
```
引数なしで実行すると、「社内の経費精算のルールを調べて、新入社員向けの案内を3行で書いて。」と頼みます。1分ほどかかります。
```text
TASK> 社内の経費精算のルールを調べて、新入社員向けの案内を3行で書いて。  （モデル: gpt-5.4）

[manager] PLAN_CREATED

[manager] PROGRESS_LEDGER_UPDATED → 次の担当: researcher

--- researcher ---

[ツール] lookup_policy('経費精算') -> 申請は発生日から30日以内。領収書の画像を添付。1万円以上は上長の承認が必要。
- 申請期限は発生日から30日以内です。
- …

[manager] PROGRESS_LEDGER_UPDATED → 次の担当: writer

--- writer ---
経費精算は、発生日から30日以内に申請してください。
…

[manager] PROGRESS_LEDGER_UPDATED → 完了と判断（最終成果をまとめる）

--- 最終成果 ---
…

[まとめ] 調整ラウンド 3 回、委譲: researcher 1 回 / writer 1 回
```
- `[manager] PLAN_CREATED` は、マネージャーが最初の計画を立てた節目です。
- `PROGRESS_LEDGER_UPDATED` は、マネージャーが**進捗台帳**（終わったか・行き詰まっていないか・次は誰か）を更新した節目で、調整ラウンドごとに1回出ます。`→ 次の担当:` は、台帳でマネージャーが選んだ担当です（`main.py` が台帳から取り出して表示しています）。
- `[ツール]` の行は、調査担当が関数ツール `lookup_policy` を実際に呼んだ記録です。規程の文面（30日以内など）は、この関数が返したモックの値で、モデルが作った文ではありません。
- `--- researcher ---` などの本文は、各担当（モデル）が書いたものです。調査担当の報告に出てくる資料名（「経理FAQ」など）はモデルが想定したもので、このアプリには無い資料です。文面も、ラウンドの回数も、誰を何回呼ぶかも、実行のたびに変わることがあります。

### 7. 調べなくてよい仕事を頼む（マネージャーが担当を選び直す）
```powershell
python main.py "社内の問い合わせにAIを使うときの注意点を、初心者向けに3行でまとめて。"
```
```text
[manager] PROGRESS_LEDGER_UPDATED → 次の担当: writer

--- writer ---
…

[まとめ] 調整ラウンド 2 回、委譲: writer 1 回
```
コードは同じなのに、今度は調査担当を呼ばずに執筆担当だけで終わることがあります（講座の試走では毎回そうなりました）。**誰をどの順に呼ぶかはコードで固定しておらず、マネージャーが仕事の中身と各担当の `description` を見て決めます**。これが Magentic の特徴です。モデルの判断なので、調査担当を呼ぶ回があっても誤りではありません。

### 8. 後片付け
- このコードは Foundry Agent Service にエージェントを登録しません（`FoundryChatClient` はプロジェクトのエンドポイントからモデルを直接呼ぶだけ）。ポータルの「エージェント」一覧にも増えません。消すものはありません（なお、モデルの応答の記録は Responses API の既定で一定期間サービス側に保存されます）。
- `gpt-5.4` のデプロイは後続のレッスンでも使うので残します。デプロイ自体は課金されません（Standard 系は使ったトークン分だけ）。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。

## ポイント（試験の論点）
- **Magentic**：マネージャー（主）が計画を立て、進捗台帳で状況を判断しながら、**次の担当を動的に選ぶ**。行き詰まったら計画を立て直す（`REPLANNED`）。担当の順番が決まっている仕事は Sequential、並列に同じ問いを投げるなら Concurrent、会話の中で担当を渡すなら Handoff、と使い分けます。
- **`description` は担当を選ぶ手がかり**、`instructions` はその担当自身への指示。マネージャーが見るのは `description` です。
- **専門エージェントに道具（ツール）を分けて持たせる**：このサンプルでは調査担当だけが `lookup_policy` を持ちます。関数はアプリ（この Python プロセス）の中で実行されるので、Foundry Agent Service のツール対応表（L2-7。サービスに登録するエージェント向け）で Functions が No のモデルでも、ここでは関数ツールが使えます。
- `max_round_count`（調整ラウンドの上限。達すると最終成果の代わりに打ち切りのメッセージが出る）で、終わらない協調を止めます。`max_stall_count` は、前に進まないラウンドが何回続いたら**計画を立て直す**（`REPLANNED`）かで、止める設定ではありません。
- マネージャーも毎ラウンドモデルを呼ぶので、エージェント1つで済む仕事より、トークンと時間がかかります。

## つまずき
| 症状 | 対処 |
|---|---|
| `ModuleNotFoundError` | `requirements.txt` の全パッケージ（特に `agent-framework-orchestrations`）を入れたか |
| `KeyError: 'FOUNDRY_PROJECT_ENDPOINT'` | `.env` の作成と変数名（手順5）を確認 |
| `DeploymentNotFound`（404） | `FOUNDRY_MODEL` が手順2の Name 列のデプロイ名と一致しているか |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| `AttributeError: run_stream` | 旧い書き方です。現行は `workflow.run(task, stream=True)` |
| ラウンドが上限（8回）まで回る・同じ担当が何度も呼ばれる | 頼む仕事を具体的にする（行数・対象を書く）。講座の試走では、`gpt-4.1-mini` にするとラウンドが増えた（8回） |
| 400 `No tool call found for function call output` | 講座の試走で、ツールを持つ調査担当が2回目に呼ばれたときに出たことがあります。もう一度実行するか、頼む仕事の対象を具体的にしてください（規程の名前が分かると1回で調べ終わる） |

## 後片付け
手順8のとおりです。削除するリソースはありません。
