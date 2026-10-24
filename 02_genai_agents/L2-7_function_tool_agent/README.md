# L2-7 実践: 自作関数をエージェントに登録する（Function Tool）

自作の関数（在庫照会）を `FunctionTool` でスキーマ宣言してエージェント定義に登録し、`function_call → アプリが実行 → function_call_output → 最終回答` のループを自分のコードで回すハンズオンです。関数を実行するのは**アプリ側**で、モデルではありません。

> 対応レクチャー：実践 `L2-7-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。会話とエージェントは `finally` で削除され、プロジェクトに残りません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 自作関数 `get_inventory`（在庫はモック）、`FunctionTool` のスキーマ宣言、`function_call` が出なくなるまで回すループ、後片付け（`finally`） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- `az login` 済み ／ Python 3.11+
- エージェントに関数ツール（Functions）を持たせるので、**モデルは `gpt-4.1-mini`** を使います。Foundry Agent Service の「Tool support by region and model」（エージェントに持たせるツールの対応表）で、`gpt-4.1-mini` は Functions が Yes、`gpt-5.4` 系は No です。リージョンでも可否が分かれるので、講座の `japaneast` で使います。デプロイが無ければ手順2で作ります（デプロイ自体は無料。課金は使ったトークン分だけ）。

## 進め方（コピペで実行できます）

全部で9手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | `gpt-4.1-mini` のデプロイを確かめる（無ければ作る） |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 在庫を聞く（関数が1回呼ばれる） |
| 7 | 2つの商品を比べる（関数が2回呼ばれる） |
| 8 | 存在しない商品を聞く（エラーをモデルに返す） |
| 9 | 後片付けを確かめる |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-7_function_tool_agent
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. `gpt-4.1-mini` のデプロイを確かめる（無ければ作る）
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧に `gpt-4.1-mini` があればOKです。無ければ、次のコマンドでデプロイします（`gpt-4.1-mini  Succeeded` が出ればOK）。
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

### 3. プロジェクトのエンドポイントを取得する
```powershell
$result = az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name ai103-project `
  -o json | ConvertFrom-Json

$result.properties.endpoints.'AI Foundry API'
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
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-4.1-mini` は最初から入っています。
> ⚠️ 前のレッスンの `.env` を丸ごと写すと、`MODEL_DEPLOYMENT` が `gpt-5.4` のままになることがあります。

### 6. 在庫を聞く（関数が1回呼ばれる）
```powershell
python main.py
```
引数なしで実行すると、「商品 X1 の在庫はいくつ？」と聞きます。
```text
USER> 商品 X1 の在庫はいくつ？
[応答1] function_call 1 件
[ツール要求] get_inventory({'product_code': 'X1'})
[実行] get_inventory -> {'product_code': 'X1', 'stock': 3}
[応答2] function_call 0 件
AI> 商品コード X1 の在庫は3個あります。
会話とエージェントを削除しました（残り: 0 件）
```
- `[ツール要求]` は、モデルが返した「この関数をこの引数で呼びたい」という依頼（`function_call`）です。**モデルは関数を実行しません**。
- `[実行]` は、アプリ（`main.py`）が自分の関数を実行した結果です。この結果を `function_call_output` として返すと、モデルが最終回答を書きます。
- 在庫の数 3 は、アプリの関数が返した値です。`[実行]` の行があるので、モデルが推測で答えたのではないことが画面で分かります。
- `[応答2] function_call 0 件` で、もう呼びたい関数が無いのでループを抜けます。答えの文面は実行のたびに変わることがあります。

### 7. 2つの商品を比べる（関数が2回呼ばれる）
```powershell
python main.py "商品 X1 と M27 の在庫を比べて。"
```
```text
[応答1] function_call 2 件
[ツール要求] get_inventory({'product_code': 'X1'})
[実行] get_inventory -> {'product_code': 'X1', 'stock': 3}
[ツール要求] get_inventory({'product_code': 'M27'})
[実行] get_inventory -> {'product_code': 'M27', 'stock': 12}
[応答2] function_call 0 件
AI> 商品コードX1の在庫は3個、M27の在庫は12個です。在庫はM27の方が多いです。
```
同じ関数を、商品ごとに2回呼びました。1つの応答に2件まとめて並ぶ（並列の呼び出し）ことも、1件ずつ2往復になることもあります（モデルと、要求の `parallel_tool_calls` の設定で変わる）。どちらでも、`main.py` は `function_call` が出なくなるまでループするので最後まで答えます。「M27 の方が多い」という比較は、2つの結果を受け取ったモデルが書いたものです。

### 8. 存在しない商品を聞く（エラーをモデルに返す）
```powershell
python main.py "商品 Z9 の在庫は？"
```
```text
[ツール要求] get_inventory({'product_code': 'Z9'})
[実行] get_inventory -> {'error': 'unknown product_code: Z9'}
AI> 申し訳ありませんが、商品コードZ9の在庫情報は見つかりませんでした。…
```
関数は例外で止まらず、`{"error": ...}` を**結果としてモデルに返します**。モデルはそれを読んで「見つからない」と説明できます。モデルが関数を呼ばずに聞き返すこともあります。

### 9. 後片付けを確かめる
手順6・8の最後の行 `会話とエージェントを削除しました（残り: 0 件）` が確認です（手順7も、最後まで待てば同じ行が出ます）。`main.py` は `finally` で会話とエージェントの版を削除し、同じ名前のエージェントが残っていないかを数えて表示します。`gpt-4.1-mini` のデプロイは後続のレッスンでも使うので残します。

## ポイント（試験の論点）
- **`FunctionTool` はスキーマの宣言**で、関数の実体ではありません。モデルは宣言（名前・説明・引数の形）だけを見て、呼ぶかどうかと引数を決めます。**実行するのはアプリ**です（組み込みツールの Code Interpreter や File Search は Foundry 側で実行される、という対比）。
- ループは `function_call`（依頼）→ アプリが実行 → `call_id` を付けた `function_call_output` を返す → 最終回答。`call_id` で、どの依頼への結果かを対応づけます。
- **エラーも結果として返す**と、モデルが状況を説明したり聞き直したりできます。
- `strict=True`・`required`・`additionalProperties: False` で、引数の形をスキーマに合わせます。ただし公式（Structured outputs）では、**並列の関数呼び出しでは strict の保証が効かない**とされています（必ず守らせたいなら `parallel_tool_calls` を false）。だからアプリ側でも引数を確かめます。
- 呼ぶかどうかはモデルが決めます。instructions に「ツールで調べて」と書いても、呼ぶことは保証されません。必ず呼ばせたいときは、要求の `tool_choice` で指定します。このループで `required` を使うなら**最初の要求だけ**に付けます（結果を返したあとの要求にも付けると、また関数を呼ぶことになり、最終回答が出ません）。
- 関数ツールが動かないときは、まず**モデル（とリージョン）がツール対応表で Functions に対応しているか**を確かめます。
- エージェントの1回の実行（run）は、**作成から10分で期限切れ**です。10分は関数1つの処理時間ではなく、やり取り全体の経過時間です。時間のかかる処理は、先に状態だけ返して別に確かめます。

## つまずき
| 症状 | 対処 |
|---|---|
| `[応答1] function_call 0 件` で、`[実行]` が出ないまま答える | 質問に商品コードが入っているか。instructions と `description` を具体的にする。必ず呼ばせたいなら `tool_choice` |
| `DeploymentNotFound`（404） | `.env` の `MODEL_DEPLOYMENT` が手順2の一覧のデプロイ名と一致しているか |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| `PROJECT_ENDPOINT が未設定です` | `.env` の作成・値の入力を確認 |
| 最終回答が出ない | `function_call_output` を `call_id` 付きで返したか。続けて別の関数を呼びたがっていないか（このサンプルは `function_call` が無くなるまで、最大 `MAX_TURNS = 5` 回まわす） |
| 関数が動かない・エラーになる | モデルがツール対応表で Functions に対応しているか（`gpt-5.4` 系は No） |

## 後片付け
- エージェントと会話は実行のたびに `finally` で削除されます（手順9）。在庫はモックの辞書なので後片付け不要です。
- `gpt-4.1-mini` のデプロイは後続のレッスンでも使うので残します。デプロイ自体は課金されません（Standard 系は使ったトークン分だけ）。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。
