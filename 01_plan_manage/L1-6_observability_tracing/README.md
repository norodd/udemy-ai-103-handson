# L1-6 実践: トレースを仕込んで Application Insights で可視化

自分の生成AIアプリに **OpenTelemetry トレース**を仕込み、**Azure Monitor Application Insights** に送って、「どの呼び出しに・何ミリ秒かかり・何トークン使ったか」を確かめるハンズオンです。Application Insights の作成とプロジェクトへの接続も、コマンドで行います。

> 対応レクチャー：実践 `L1-6-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `trace_app.py` | プロジェクトに接続した Application Insights の接続文字列を取得（`project.telemetry`）→ エクスポートを設定（`configure_azure_monitor`）→ GenAI 計測を有効化（`AIProjectInstrumentor`）→ 自作関数を `@trace_function` で span にする → Responses API で2回推論し、最後に `operation_Id` を表示する |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0`、`azure-monitor-opentelemetry` ほか） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- モデルは **`gpt-5.4`**（L1-1 で講座共通のプロジェクトにデプロイ済み）。
- `az login` 済み ／ Python 3.11+
- ロール：`rg-udemy-ai-103-training` にリソースを作れること（Contributor 以上）。トレースを読むには、Application Insights に **Log Analytics Reader** 以上が要ります（リソースグループの Owner／Contributor なら含まれます）。
- 費用：Application Insights（Log Analytics）は、主に**取り込んだデータ量**で課金されます（Application Insights のデータは、既定の保持期間の範囲なら保持の料金はかかりません）。このハンズオンで送るのは数十 KB 程度です。

## 進め方（コピペで実行できます）

全部で11手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | `gpt-5.4` のデプロイがあるか確かめる |
| 3 | プロジェクトに Application Insights が接続されているか確かめる |
| 4 | Log Analytics ワークスペースと Application Insights を作る |
| 5 | Application Insights をプロジェクトに接続する |
| 6 | プロジェクトのエンドポイントを取得する |
| 7 | 仮想環境を作って依存を入れる |
| 8 | `.env` を用意する |
| 9 | トレースを仕込んだアプリを実行する |
| 10 | Application Insights でトレースを確かめる |
| 11 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 01_plan_manage/L1-6_observability_tracing
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$LOC = "japaneast"
$PROJECT = "ai103-project"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$PROJECT_ID = az cognitiveservices account project show --name $FOUNDRY --resource-group $RG --project-name $PROJECT --query id -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。`$PROJECT_ID` はプロジェクトのリソース ID で、手順3・5で使います（サブスクリプション ID を含むので、画面には出していません）。

### 2. `gpt-5.4` のデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧の Name 列に `gpt-5.4` があればOKです。

### 3. プロジェクトに Application Insights が接続されているか確かめる
```powershell
az rest --method get `
  --url "https://management.azure.com$PROJECT_ID/connections?api-version=2025-06-01" `
  --query "value[?properties.category=='AppInsights'].name" -o tsv
```
何も表示されなければ、まだ接続されていません。手順4・5で作って接続します。名前が表示されたら接続済みなので、手順6へ進みます。
> トレースの送り先は、**プロジェクトに接続した Application Insights**です。プロジェクトに接続できる Application Insights は1つです。

### 4. Log Analytics ワークスペースと Application Insights を作る
```powershell
az extension add --name application-insights --upgrade --only-show-errors
az monitor log-analytics workspace create `
  --resource-group $RG --workspace-name ai103-logs --location $LOC `
  --query "{name:name, state:provisioningState}" -o table
$WS_ID = az monitor log-analytics workspace show --resource-group $RG --workspace-name ai103-logs --query id -o tsv
az monitor app-insights component create `
  --resource-group $RG --app ai103-appinsights --location $LOC `
  --workspace $WS_ID --kind web --application-type web `
  --query "{name:name, state:provisioningState}" -o table
```
2つとも `Succeeded` になればOKです。Application Insights は**ワークスペースベース**で作ります。トレースの実体は、このワークスペース（Log Analytics）に保存されます。

### 5. Application Insights をプロジェクトに接続する
```powershell
$AI_ID = az monitor app-insights component show --resource-group $RG --app ai103-appinsights --query id -o tsv
$AI_CS = az monitor app-insights component show --resource-group $RG --app ai103-appinsights --query connectionString -o tsv
@{ properties = @{ category = "AppInsights"; target = $AI_ID; authType = "ApiKey"; isSharedToAll = $true;
   credentials = @{ key = $AI_CS }; metadata = @{ ApiType = "Azure"; ResourceId = $AI_ID } } } |
  ConvertTo-Json -Depth 5 | Set-Content conn.json
az rest --method put `
  --url "https://management.azure.com$PROJECT_ID/connections/ai103-appinsights?api-version=2025-06-01" `
  --body "@conn.json" `
  --query "{name:name, category:properties.category}" -o table
Remove-Item conn.json
```
Name が `ai103-appinsights`、Category が `AppInsights` と表示されればOKです。
- 接続の中身は、Application Insights の**接続文字列**です（送り先を示す値。画面にもファイルにも残さないよう、変数から一時ファイルを作ってすぐ消しています）。
- Foundry ポータルでは **管理 → プロジェクトの詳細 → 接続されたリソース → 接続の追加 → Application Insights** で同じことができます。講座で確かめた Azure CLI（2.88）の `az cognitiveservices account project connection create` では、この種類（AppInsights）の接続を作れなかったので、ここでは管理 API（`az rest`）で作っています。

### 6. プロジェクトのエンドポイントを取得する
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name $PROJECT `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
```
返ってきた URL（末尾が `/api/projects/ai103-project`）を、手順8で `.env` に貼ります。

### 7. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
./.venv/bin/Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 8. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順6のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` は最初から入っています。**Application Insights の接続文字列は `.env` に書きません**（コードがプロジェクトの接続から取り出します）。

### 9. トレースを仕込んだアプリを実行する
```powershell
python trace_app.py
```
2つの質問を投げて、答えとトークン数、最後に `operation_Id` を表示します。
```text
Q: Microsoft Foundry の可観測性とは何ですか？1文で答えてください。
[分類] general  [トークン] 入力 50 / 出力 69
A: …

Q: デプロイしたモデルが動かないエラーの切り分け手順を3つ、それぞれ20文字以内で挙げてください。
[分類] support  [トークン] 入力 66 / 出力 30
A: …

--- トレース送信完了。operation_Id: d00a160a4b795ca8e39cab0f42d0e3dc ---
Application Insights への反映には数分かかります。
```
- `[分類]` は自作関数 `classify_question` が決めた値で、モデルが決めたものではありません（「エラー」「動かない」を含めば support）。
- `[トークン]` は応答の `usage` から表示しています。同じ値が span の属性（`gen_ai.usage.*`）にも記録されます。
- `operation_Id` は、この実行の親 span のトレース ID です。Application Insights では、1回の実行の span が同じ `operation_Id` でつながります。答えの文面とトークン数は実行のたびに変わります。

### 10. Application Insights でトレースを確かめる
**2〜5分ほど待ってから**実行します（取り込みに時間がかかります）。`<operation_Id>` は手順9で表示された値に置き換えます。
```powershell
$OP = "<operation_Id>"
az monitor app-insights query --resource-group $RG --app ai103-appinsights `
  --analytics-query "dependencies | where operation_Id == '$OP' | order by timestamp asc | project name, ms=round(duration,0), input=tostring(customDimensions['gen_ai.usage.input_tokens']), output=tostring(customDimensions['gen_ai.usage.output_tokens']), category=tostring(customDimensions['app.question_category'])" `
  --query "tables[0].rows" -o tsv
```
```text
l1-6-trace-demo	7686
classify-question	0			general
chat gpt-5.4	4030	50	69
classify-question	0			support
chat gpt-5.4	3655	66	30
```
- 1列目が span の名前、2列目が所要時間（ミリ秒）です。親の所要時間は、2つの推論の合計とほぼ同じです（推論が順番に2回走った）。`l1-6-trace-demo` が親 span で、その中に自作の `classify-question` と、自動で計測された推論の span（`chat <デプロイ名>`）が並びます。
- 推論の span には、入力・出力のトークン数（`gen_ai.usage.input_tokens`／`output_tokens`）が入っています。
- `classify-question` の行の `general`／`support` は、コードが `app.question_category` という名前で足した属性です。
- 何も表示されないときは、もう数分待って再実行します。
> Azure ポータルでも、Application Insights の **ログ** で同じクエリ（`dependencies | where operation_Id == '…'`）を実行できます。

### 11. 後片付け
- Application Insights とワークスペース、プロジェクトへの接続は、**後のレッスン（エージェントのトレース）でも使うので残します**。
- 課金は、主に取り込んだデータ量にかかります（既定の保持期間の範囲なら保持の料金はかかりません）。講座を終えて不要になったら、次のコマンドで接続とリソースを消します。
  ```powershell
  az rest --method delete --url "https://management.azure.com$PROJECT_ID/connections/ai103-appinsights?api-version=2025-06-01"
  az monitor app-insights component delete --resource-group $RG --app ai103-appinsights
  az monitor log-analytics workspace delete --resource-group $RG --workspace-name ai103-logs --yes
  ```
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。

## ポイント（試験の論点）
- **トレースの送り先は、プロジェクトに接続した Application Insights**。コードは `project.telemetry.get_application_insights_connection_string()` で接続文字列を取り出し、`configure_azure_monitor()` に渡すだけです。
- **GenAI の計測**：`AIProjectInstrumentor().instrument()` で、Responses API などの呼び出しが自動で span になります。計測は実験的な機能で、`AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` を `instrument()` より**前**に設定します。
- **自作処理の span**：`@trace_function` を付けた関数は、それ自体が span になります。KQL で検索したい値は、`set_attribute()` で `code.` 以外の名前を付けて足します（引数・戻り値の `code.*` 属性は customDimensions に出ません）。
- **メッセージ本文の記録**（`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`）は、個人情報を含みうるので開発時だけにします。
- **サンプリング**：Azure Monitor の既定の設定では span が間引かれることがあるので、このデモは `sampling_ratio=1.0` で全件を送ります。本番はコストに応じて下げます。

## つまずき
| 症状 | 対処 |
|---|---|
| 手順5で `AuthorizationFailed` | リソースグループに Contributor 以上が要ります |
| 実行時に接続文字列の取得で失敗（接続が見つからない） | 手順3で `AppInsights` の接続があるか確かめる。無ければ手順4・5 |
| 手順10で何も表示されない | 取り込みに数分かかります。待って再実行。`operation_Id` を貼り間違えていないかも確かめる |
| 手順10で `Forbidden`／権限エラー | Application Insights に Log Analytics Reader 以上が要ります（テーブルが保護されている場合は Privileged Monitoring Data Reader も） |
| 推論の span にトークン数が無い／span が少ない | `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` が `instrument()` より前に設定されているか（本コードは import の前に設定済み）。`sampling_ratio=1.0` になっているか |
| `DeploymentNotFound`（404） | `MODEL_DEPLOYMENT` がデプロイ名（手順2の Name 列）と一致しているか |

## 注意（揮発情報）
- クライアント側の GenAI トレースはプレビューです。span の名前や属性名（`gen_ai.*`）は、OpenTelemetry の GenAI セマンティック規約の版によって変わることがあります。実データの customDimensions を見て調整してください。
- 動作確認：2026-09-24、`azure-ai-projects` 2.7.0 ／ `azure-monitor-opentelemetry` 1.8.10 ／ Azure CLI 2.88。
