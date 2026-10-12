# L2-10 実践: 高リスク操作の前に人間承認を挟む（deterministic HITL）

エージェントに**低リスク（読み取り）**と**高リスク（削除）**の関数ツールを持たせ、高リスクの関数は**アプリ側のコードが必ず**人間の承認を求めます。承認するかどうかをモデルに判断させない、これが deterministic HITL（決定論的な Human-in-the-loop）です。

> 対応レクチャー：実践 `L2-10-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。会話とエージェントは `finally` で削除され、プロジェクトに残りません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | `get_record`（低リスク・自動実行）／`delete_record`（高リスク・承認必須）を持つエージェント。承認ゲートと後片付け（`finally`） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- `az login` 済み ／ Python 3.11+
- エージェントに関数ツール（Functions）を持たせるので、**モデルは `gpt-4.1-mini`** を使います。Foundry Agent Service の「Tool support by region and model」（エージェントに持たせるツールの対応表）で、`gpt-4.1-mini` は Functions が Yes、`gpt-5.4` 系は No です。リージョンでも可否が分かれるので、講座の `japaneast`（Function は yes）で使います。無ければ手順2でデプロイします（デプロイ自体は無料。課金は使ったトークン分だけ）。

## 進め方（コピペで実行できます）

全部で9手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | `gpt-4.1-mini` をデプロイする（あれば再利用） |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 削除を依頼して、**承認する**（`y`） |
| 7 | もう一度削除を依頼して、**拒否する**（`n`） |
| 8 | 読み取りを依頼する（承認なしで自動実行） |
| 9 | 後片付けを確かめる |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-10_hitl
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. `gpt-4.1-mini` をデプロイする（あれば再利用）
```powershell
az cognitiveservices account deployment create `
  --name $FOUNDRY `
  --resource-group $RG `
  --deployment-name gpt-4.1-mini `
  --model-name gpt-4.1-mini `
  --model-version 2025-04-14 `
  --model-format OpenAI `
  --sku-name GlobalStandard `
  --sku-capacity 10 `
  --query "{name:name, state:properties.provisioningState}" -o table
```
`gpt-4.1-mini  Succeeded` が出ればOKです。すでに同じ名前のデプロイがあるときも、同じ設定なら `Succeeded` が返ります（後続のレッスンでも使うので、消さずに残します）。
> 関数ツールをエージェントに持たせるときは、**モデル（とリージョン）がそのツールに対応しているか**を公式の対応表で先に確かめます。表で No のモデルは、動いたとしても前提にしません。

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
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-4.1-mini` は最初から入っています。
> ⚠️ このレッスンのキー名は `PROJECT_ENDPOINT` と `MODEL_DEPLOYMENT` です。前のレッスンの `.env` を丸ごと写すと、`MODEL_DEPLOYMENT` が `gpt-5.4` のままになります。

### 6. 削除を依頼して、承認する（`y`）
```powershell
python main.py
```
引数なしで実行すると、「レコード 1002 を削除して。」と依頼します。モデルが削除の関数を呼びたいと返すと、**実行する前に**承認のプロンプトで止まります。`y` と入力して Enter を押します。
```text
USER> レコード 1002 を削除して。
[ツール要求] delete_record({'record_id': '1002'})
[承認] delete_record({'record_id': '1002'}) を実行しますか？ (y/N): y
[実行] delete_record -> {'deleted': '1002'}
AI> レコード 1002 を削除しました。

DB の中身: {'1001': '山田'}
会話とエージェントを削除しました（残り: 0 件）
```
- `[ツール要求]` は、モデルが返した「この関数をこの引数で呼びたい」という依頼です。**モデルは関数を実行しません**。実行するのはアプリ（`main.py`）です。
- `DB の中身` から 1002 が消えています。データベースはインメモリの辞書なので、次に実行すると元（1001・1002）に戻ります。

### 7. もう一度削除を依頼して、拒否する（`n`）
```powershell
python main.py
```
今度は承認のプロンプトで `n` と入力して Enter を押します（`y` 以外は、空の Enter も含めてすべて拒否です）。
```text
[承認] delete_record({'record_id': '1002'}) を実行しますか？ (y/N): n
[拒否] delete_record は実行しませんでした
AI> レコード1002の削除は承認されていないため実行できません。

DB の中身: {'1001': '山田', '1002': '佐藤'}
```
拒否したときも、アプリは「拒否された」という結果（`denied_by_human`）をモデルに返します。だからモデルは、拒否を踏まえて説明できます。1002 は残っています。
> モデルは説明を言い換えることがあります（撮影では「権限の関係でできません」と、理由がずれた）。確かめるのは文面ではなく、`[拒否]` の行と DB の中身です。理由を正確に伝えさせたいときは、返す結果に `"message": "人が承認しなかったため実行していません"` のような説明を文として入れます。

### 8. 読み取りを依頼する（承認なしで自動実行）
```powershell
python main.py "レコード 1001 を見せて。"
```
```text
[ツール要求] get_record({'record_id': '1001'})
[自動実行] get_record -> {'record_id': '1001', 'name': '山田'}
AI> レコード1001の名前は「山田」です。
```
読み取りは低リスクなので、承認を挟まずに実行します。**リスクに応じて、人間の関与の度合い（oversight）を切り替える**のがこのサンプルの設計です。

### 9. 後片付けを確かめる
手順6〜8の最後の行 `会話とエージェントを削除しました（残り: 0 件）` が確認です。`main.py` は `finally` で会話とエージェントの版を削除し、同じ名前のエージェントが残っていないかを数えて表示します。`gpt-4.1-mini` のデプロイは後続のレッスンでも使うので残します。

## ポイント（試験の論点）
- **deterministic HITL**：高リスクで不可逆な操作は、モデルではなく**オーケストレーター（アプリ）のコード**で承認を強制する。instructions で「削除の前には確認して」と書くだけでは決定論的ではない。
- **モデルは関数を実行しない**。`function_call`（依頼）を返すだけで、実行してその結果（`function_call_output`）を返すのはアプリ。だからその間に承認を挟める。
- **拒否も結果として返す**（`denied_by_human`）。モデルは拒否を踏まえて応答できる。
- ⚠️ **このサンプルは「HIGH_RISK に入っている関数だけ承認」**なので、新しい危険な関数を足して `HIGH_RISK` への登録を忘れると、承認なしで実行されます（fail-open）。本番では逆に、**承認なしでよい関数の許可リストを持ち、それ以外はすべて承認に回す**（既定で拒否）形にするほうが安全です。
- 承認の実装の代表的なものは3つ：アプリ側のロジック（このサンプル）／Agent Framework の tool approval／MCP ツールの `require_approval`。

## つまずき
| 症状 | 対処 |
|---|---|
| 承認プロンプトが出ない | モデルが `delete_record` ではなく `get_record` を選んでいないか（依頼文を「削除して」など明確に）。`HIGH_RISK` の名前と関数名が一致しているか |
| `DeploymentNotFound`（404） | `.env` の `MODEL_DEPLOYMENT` が手順2のデプロイ名 `gpt-4.1-mini` と一致しているか |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| `PROJECT_ENDPOINT が未設定です` | `.env` の作成・値の入力を確認 |
| 往復が5回で止まる | `MAX_TURNS = 5`（無限ループ防止）。長い往復が必要なら値を増やす |
| 承認に時間をかけたら失敗した | エージェントの1回の実行（run）は、作成から10分で期限切れになる（Learn の function calling。関数1つの実行時間ではなく、承認待ちを含む経過時間）。関数の結果は10分以内に返す。人の判断に時間がかかる設計では、承認待ちを別の仕組みで持つ |

## 後片付け
- エージェントと会話は実行のたびに `finally` で削除されます（手順9）。データベースはインメモリなので後片付け不要です。
- `gpt-4.1-mini` のデプロイは後続のレッスン（L2-7・L2-9 など）でも使うので残します。デプロイ自体は課金されません（Standard 系は使ったトークン分だけ）。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。
