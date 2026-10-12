# L2-11 実践: エージェントにトレースを仕込み、失敗を分析する

エージェントに **OpenTelemetry のトレース**を仕込み、**わざと存在しない商品コード（`ZZ9`）を聞いて**ツールに error を返させます。そのうえで、プロジェクトに接続した **Application Insights** のトレースを KQL で読み、「どの span で・何が起きたか」を突き止めるハンズオンです。

> 対応レクチャー：実践 `L2-11-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | Application Insights への送信を設定（`configure_azure_monitor`）→ GenAI 計測を有効化（`AIProjectInstrumentor`）→ 関数ツール `get_inventory` を持つエージェントを作り、質問する。`get_inventory` は `@trace_function` で span にし、失敗したときは `app.tool_error` 属性を足す。最後に会話とエージェントを削除し、`operation_Id` を表示する |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0`、`azure-monitor-opentelemetry` ほか） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- **L1-6 でプロジェクトに Application Insights（`ai103-appinsights`）を接続済み**であること。まだなら、L1-6 の README の手順4・5で作って接続します（手順3で確かめられます）。
- `az login` 済み ／ Python 3.11+
- トレースを読むには、Application Insights に **Log Analytics Reader** 以上が要ります（リソースグループの Owner／Contributor なら含まれます）。
- 費用：推論のトークン代と、Application Insights に取り込むデータ量（このハンズオンでは数十 KB）です。

## 進め方（コピペで実行できます）

全部で11手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | `gpt-4.1-mini` のデプロイを確かめる（無ければ作る） |
| 3 | プロジェクトに Application Insights が接続されているか確かめる |
| 4 | プロジェクトのエンドポイントを取得する |
| 5 | 仮想環境を作って依存を入れる |
| 6 | `.env` を用意する |
| 7 | わざと失敗する質問でエージェントを実行する |
| 8 | 1回の実行の span を並べる |
| 9 | サービス側の span から、モデルがツールに渡した引数を読む |
| 10 | 静かな失敗を、属性で探す |
| 11 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-11_tracing
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$PROJECT = "ai103-project"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$PROJECT_ID = az cognitiveservices account project show --name $FOUNDRY --resource-group $RG --project-name $PROJECT --query id -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。`$PROJECT_ID` はプロジェクトのリソース ID で、手順3で使います（サブスクリプション ID を含むので、画面には出していません）。

### 2. `gpt-4.1-mini` のデプロイを確かめる（無ければ作る）
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧に `gpt-4.1-mini` があればOKです。エージェントに**関数ツール**を持たせるので、Foundry Agent Service のツール対応表で Functions に対応しているモデルを使います。無ければ、次のコマンドでデプロイします（`gpt-4.1-mini  Succeeded` が出ればOK）。
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

### 3. プロジェクトに Application Insights が接続されているか確かめる
```powershell
az rest --method get `
  --url "https://management.azure.com$PROJECT_ID/connections?api-version=2025-06-01" `
  --query "value[?properties.category=='AppInsights'].name" -o tsv
```
`ai103-appinsights` と表示されればOKです。何も表示されなければ、L1-6 の README の手順4・5で作って接続してから戻ります。
> プロジェクトに Application Insights を接続すると、Foundry は**サービス側（server-side）のトレース**を自動で記録します。コードは変えません。このハンズオンでは、さらに自分のコードにも計装（client-side）を足して、両方の span を1本のトレースにつなげます。

### 4. プロジェクトのエンドポイントを取得する
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name $PROJECT `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
```
返ってきた URL（末尾が `/api/projects/ai103-project`）を、手順6で `.env` に貼ります。

### 5. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
./.venv/bin/Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 6. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順4のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-4.1-mini` は最初から入っています。**Application Insights の接続文字列は `.env` に書きません**（コードがプロジェクトの接続から取り出します）。

### 7. わざと失敗する質問でエージェントを実行する
```powershell
python main.py
```
既定の質問は「商品 ZZ9 の在庫は？」です。`ZZ9` は在庫データに無い商品コードなので、ツールが error を返します。
```text
USER> 商品 ZZ9 の在庫は？
[応答1] function_call 1 件
[実行] get_inventory({'product_code': 'ZZ9'}) -> {'error': 'unknown product_code: ZZ9'}
[応答2] function_call 0 件
AI> 申し訳ありませんが、商品コードZZ9は存在しないようです。…
会話とエージェントを削除しました（残り: 0 件）
operation_Id: 59e2c0e348d5ceb99b5c8e7a7795a1b4（Application Insights への反映には数分かかります）
```
- `[応答1] function_call 1 件` は、モデルが関数の呼び出しを**依頼**した件数です。関数を実行したのはアプリ（`run_tool`）で、その結果が `[実行]` の行です。
- プログラムは**例外にならず、最後まで正常に終わります**。ツールは error を「戻り値」として返し、モデルはそれを読んで「見つかりませんでした」と答えています。これが、ログを眺めるだけでは気づきにくい**静かな失敗**です。
- 最後の `operation_Id` は、この実行の親 span のトレース ID です。手順8・9で使います。答えの文面は実行のたびに変わります。
- 成功する例と見比べたいときは `python main.py "商品 X1 の在庫は？"` を実行します。

### 8. 1回の実行の span を並べる
**2〜5分ほど待ってから**実行します（取り込みに時間がかかります）。`<operation_Id>` は手順7で表示された値に置き換えます。
```powershell
$OP = "<operation_Id>"
az monitor app-insights query --resource-group $RG --app ai103-appinsights `
  --analytics-query "dependencies | where operation_Id == '$OP' | order by timestamp asc | project name, ms=round(duration,0), success, role=cloud_RoleName" `
  --query "tables[0].rows" -o tsv
```
```text
l2-11-inventory-scenario	9115	True	inventory-app
create_agent traced-agent	2791	True	inventory-app
POST /api/projects/ai103-project/agents/traced-agent/versions	2787	True	inventory-app
create_conversation	881	True	inventory-app
invoke_agent traced-agent	2525	True	inventory-app
invoke_agent traced-agent:1	1020	True	responsesapi
chat gpt-4.1-mini-2025-04-14	937	True	responsesapi
get_inventory	0	True	inventory-app
invoke_agent traced-agent	2916	True	inventory-app
invoke_agent traced-agent:1	1247	True	responsesapi
chat gpt-4.1-mini-2025-04-14	1142	True	responsesapi
```
- 1列目が span の名前、2列目が所要時間（ミリ秒）、3列目が成功かどうか、4列目がその span を記録した側です。
- `inventory-app` は**このアプリ（client-side）**、`responsesapi` は **Foundry のサービス側**（server-side）の span です。アプリが `get_openai_client()` で取ったクライアントはトレースの文脈を送るので、両方が同じ `operation_Id` の1本のトレースにつながります。
- **`get_inventory` を含め、すべての span が `True`（成功）です**。失敗が例外ではなく戻り値に出ているので、成功・失敗の列だけでは見つかりません。
- 何も表示されないときは、もう数分待って再実行します。

### 9. サービス側の span から、モデルがツールに渡した引数を読む
```powershell
az monitor app-insights query --resource-group $RG --app ai103-appinsights `
  --analytics-query "dependencies | where operation_Id == '$OP' and name startswith 'chat' | order by timestamp asc | extend o = parse_json(tostring(customDimensions['gen_ai.output.messages']))[0] | project finish=tostring(o.finish_reason), tool=tostring(o.parts[0].name), args=tostring(o.parts[0].arguments), input=tostring(customDimensions['gen_ai.usage.input_tokens']), output=tostring(customDimensions['gen_ai.usage.output_tokens'])" `
  --query "tables[0].rows" -o tsv
```
```text
tool_calls	get_inventory	{"product_code":"ZZ9"}	102	17
stop			138	28
```
- 1行目は1回目の推論です。モデルは答えを出さずに終わり（`tool_calls`）、`get_inventory` を引数 `{"product_code":"ZZ9"}` で呼ぶよう依頼しています。**モデルは質問の商品コードをそのまま渡しており、引数の取り違えではない**ことが分かります。
- 2行目は、ツールの結果を受け取ったあとの推論で、`stop`（答えを出して終了）です。
- 右の2列は入力・出力のトークン数です（本文ではなく `gen_ai.usage.*` の属性から取っています。トークン数は実行のたびに変わります）。サービス側の span には、トークン数と一緒に、プロンプトと応答の本文（`gen_ai.input.messages`／`gen_ai.output.messages`）も入っています。本文は個人情報を含みうるので、トレースを読める人を絞ります。アプリ側の span に本文を記録するかどうかは `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` で切り替えます（このコードは開発用に `true`）。

### 10. 静かな失敗を、属性で探す
```powershell
az monitor app-insights query --resource-group $RG --app ai103-appinsights `
  --analytics-query "dependencies | where timestamp > ago(1h) and isnotempty(customDimensions['app.tool_error']) | order by timestamp asc | project timestamp, operation_Id, success, error=tostring(customDimensions['app.tool_error'])" `
  --query "tables[0].rows" -o tsv
```
```text
2026-09-23T22:33:19.159492Z	54b9661c9f803187fe1111920aae3c14	True	unknown product_code: ZZ9
2026-09-23T22:50:34.200837Z	59e2c0e348d5ceb99b5c8e7a7795a1b4	True	unknown product_code: ZZ9
```
- `app.tool_error` は、`main.py` の `get_inventory` が失敗したときに足している属性です。この属性で絞り込むと、**成功扱いの span の中から、ツールが失敗した実行だけ**を拾えます。原因は `unknown product_code: ZZ9`（在庫データに無い商品コード）です。
- 直近1時間に実行した分がすべて出ます。上の例は2回実行した場合で、下の行が手順7〜9の例の実行です。
- `@trace_function` が記録する引数・戻り値（`code.function.*`）は、Application Insights の customDimensions には出ません。KQL で探したい値は、このように `code.` 以外の名前で足します。
- なお `@trace_function` は、`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` をオフにしても、引数と戻り値を**必ず** span に記録します。Application Insights の列には出なくても、ほかの送り先では見えるので、個人情報を受け取る関数に付けるときは注意します。

### 11. 後片付け
- エージェントと会話は、実行のたびに `finally` で削除されます（手順7の `残り: 0 件`）。
- Application Insights とワークスペース、プロジェクトへの接続、`gpt-4.1-mini` のデプロイは、**他のレッスンでも使うので残します**。講座を終えて消すときは、L1-6 の README の手順11を参照してください。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。

## ポイント（試験の論点）
- **server-side トレース**：プロジェクトに Application Insights を接続するだけで、Foundry がエージェントの span を記録します（コード変更なし）。プロンプト エージェントのトレースは一般提供（GA）です。
- **client-side トレース**：`configure_azure_monitor()`（送り先）＋ `AIProjectInstrumentor().instrument()`（GenAI 計測。プレビュー）で、自分のコードの span を足します。`AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` は `instrument()` より**前**に設定します。設定し忘れてもエラーにはならず、**警告が出るだけでエージェントの span が記録されません**（このコードは `main.py` の先頭で設定済み）。
- **client と server をつなぐ**：OpenAI クライアントは、計装の**後**に `get_openai_client()` で取ります（トレースの文脈がリクエストに付き、サービス側の span が同じトレースにつながる）。ポータルのトレースで特定のエージェントに紐づけるには、`agent_reference` に `name` と `id` の両方を渡します。
- **エラー分析**：失敗が例外でなく戻り値に出ると、span は成功のままです。検索できる属性（`app.tool_error` など）を足し、span を辿って「どの呼び出しで・どんな入力で・何が返ったか」を読みます。
- **サンプリング**：Azure Monitor の既定の設定では span が間引かれることがあるので、このデモは `sampling_ratio=1.0` で全件を送ります。本番はコストに応じて下げます。

## つまずき
| 症状 | 対処 |
|---|---|
| 実行時に接続文字列の取得で失敗（接続が見つからない） | 手順3で `AppInsights` の接続があるか確かめる。無ければ L1-6 の手順4・5 |
| 手順8〜10で何も表示されない | 取り込みに数分かかります。待って再実行。`operation_Id` の貼り間違いも確かめる |
| 手順8〜10で `Forbidden`／権限エラー | Application Insights に Log Analytics Reader 以上が要ります（テーブルが保護されている場合は Privileged Monitoring Data Reader も） |
| エージェントの span（`create_agent`・`invoke_agent`）が出ない | `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` が `instrument()` より前に設定されているか（設定し忘れは警告だけでエラーにならない） |
| `responsesapi` の span が無い／別のトレースに分かれる | OpenAI クライアントを `instrument()` の**後**に `get_openai_client()` で取っているか |
| `get_inventory` の span が無い | `@trace_function("get_inventory")` のように、`()` 付きで付けているか |
| `[応答1] function_call 0 件` で、`[実行]` が出ないまま答える | モデルがツールを呼ぶかはモデルが決めます。質問に商品コードが入っているか確かめる |
| `DeploymentNotFound`（404） | `.env` の `MODEL_DEPLOYMENT` が手順2の一覧のデプロイ名と一致しているか |
| `401`／`403`（推論） | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |

## 注意（揮発情報）
- クライアント側の GenAI トレースはプレビューです。span の名前や属性名（`gen_ai.*`）は、OpenTelemetry の GenAI セマンティック規約の版によって変わることがあります。実データの customDimensions を見て調整してください。
- 動作確認：2026-09-24、`azure-ai-projects` 2.7.0 ／ `azure-monitor-opentelemetry` 1.8.10 ／ Azure CLI 2.88。
