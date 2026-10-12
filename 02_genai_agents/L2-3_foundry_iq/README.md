# L2-3 実践: Foundry IQ のナレッジベースをエージェントに接続する

Azure AI Search に **ナレッジソース**（Blob の文書）と **ナレッジベース**を作り、それを **MCP ツール**としてエージェントに付けて、文書に基づいて答えさせるハンズオンです。Foundry IQ の「ナレッジソース → ナレッジベース → エージェント」の3段を、コマンドとコードで1つずつ組み立てます。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential` ＋ 各サービスのマネージド ID）。API キーは使いません。
> ナレッジベースの MCP エンドポイント、LLM によるクエリ計画・推論の強さ、プロジェクト接続の `RemoteTool` は**プレビュー**の機能です（API バージョン `2026-08-01-preview` / `2025-10-01-preview`）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `product_info.md` | 取り込む文書（架空の製品 Contoso SmartHub X1 の製品情報。File Search のハンズオンと同じ内容） |
| `create_kb.py` | Search の REST API で、ナレッジソース（Blob）→ 取り込み待ち → ナレッジベースを作る。`--delete` で消す |
| `kb_retrieve.py` | ナレッジベースの retrieve を直接呼び、内側で起きたこと（クエリ計画・サブクエリ・検索件数）を表示する |
| `main.py` | ナレッジベースを MCP ツール（`knowledge_base_retrieve`）として付けたエージェントを作り、3つ質問して、最後に消す |
| `agent_instructions.txt` | エージェントへの指示（ツールを使う・無ければ「分かりません」・引用を付ける・2行以内） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0`、`azure-identity`、`python-dotenv`、`requests`） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール・`gpt-5.4` のデプロイ）。
- `az login` 済み ／ Python 3.11+
- 新しいリソースグループを作ってロールを付けるので、**サブスクリプション**の **Owner** か **User Access Administrator** が要ります（`rg-udemy-ai-103-training` だけの Owner では足りません）。
- **費用**：Azure AI Search の Basic は、**置いておくだけで時間単位の課金**があります（Free はマネージド ID を使えないので、この構成では使えません）。ほかは推論と埋め込みのトークン代だけです。
- このハンズオンで作る Search とストレージは、後の「検索パイプラインをエージェントにつなぐ」ハンズオン（`05_info_extraction/L5-1_search_grounding`）でも使います。**続けて進めるなら残し、やめるなら手順12で消します**。

## 進め方（コピペで実行できます）

全部で12手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1〜3で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | チャットモデルと埋め込みモデルのデプロイを確かめる |
| 3 | Search 用のリソースグループ・Azure AI Search・ストレージを作る |
| 4 | 文書をストレージにアップロードする |
| 5 | ロールを付ける（自分・Search・プロジェクト） |
| 6 | 仮想環境を作って依存を入れる |
| 7 | `.env` を作る |
| 8 | ナレッジソースとナレッジベースを作る |
| 9 | ナレッジベースの中で何が起きるかを見る |
| 10 | プロジェクトに MCP 接続（RemoteTool）を作る |
| 11 | エージェントにナレッジベースを付けて質問する |
| 12 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-3_foundry_iq
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$PROJECT = "ai103-project"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY_ID = az cognitiveservices account show --name $FOUNDRY --resource-group $RG --query id -o tsv
$PROJECT_ID = "$FOUNDRY_ID/projects/$PROJECT"
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。`$FOUNDRY_ID`・`$PROJECT_ID` はリソース ID で、手順5・10で使います（サブスクリプション ID を含むので、画面には出していません）。

### 2. チャットモデルと埋め込みモデルのデプロイを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧に `gpt-5.4` と `text-embedding-3-large` があればOKです。`gpt-5.4` はエージェントの頭脳とナレッジベースのクエリ計画に、`text-embedding-3-large` は文書と質問のベクトル化に使います。`text-embedding-3-large` が無ければ、次のコマンドでデプロイします（`text-embedding-3-large  Succeeded` が出ればOK）。
```powershell
az cognitiveservices account deployment create `
  --name $FOUNDRY `
  --resource-group $RG `
  --deployment-name text-embedding-3-large `
  --model-name text-embedding-3-large `
  --model-version 1 `
  --model-format OpenAI `
  --sku-name GlobalStandard `
  --sku-capacity 10 `
  --query "{name:name, state:properties.provisioningState}" -o table
```

### 3. Search 用のリソースグループ・Azure AI Search・ストレージを作る
```powershell
$SRG = "rg-udemy-ai-103-training-search"
$SEARCH = "ai103-search-$(Get-Random -Maximum 99999)"
$ST = "ai103st$(Get-Random -Maximum 99999)"
az group create --name $SRG --location japaneast --query properties.provisioningState -o tsv
az search service create --name $SEARCH --resource-group $SRG --location japaneast `
  --sku basic --identity-type SystemAssigned `
  --auth-options aadOrApiKey --aad-auth-failure-mode http401WithBearerChallenge `
  --query "{name:name, sku:sku.name, identity:identity.type, state:provisioningState}" -o table
az storage account create --name $ST --resource-group $SRG --location japaneast `
  --sku Standard_LRS --allow-blob-public-access false `
  --query "{name:name, state:provisioningState}" -o table
```
- Search は **Basic** で作ります。**システム割り当てマネージド ID**（`--identity-type SystemAssigned`）は、Search が Blob と埋め込みモデルをキー無しで読むために要ります。
- `--auth-options aadOrApiKey` で、**ロール（Microsoft Entra ID）でも呼べる**ようにします（既定は API キーだけ）。
- Search の作成には **10〜20分**かかります。終わると `basic  SystemAssigned  Succeeded` が表示されます。
- 別のターミナルで続きをやるときは、名前を取り直します：`$SRG = "rg-udemy-ai-103-training-search"; $SEARCH = az search service list -g $SRG --query "[0].name" -o tsv; $ST = az storage account list -g $SRG --query "[0].name" -o tsv`

### 4. 文書をストレージにアップロードする
```powershell
$ME = az ad signed-in-user show --query id -o tsv
$ST_ID = az storage account show --name $ST --resource-group $SRG --query id -o tsv
az role assignment create --assignee-object-id $ME --assignee-principal-type User `
  --role "Storage Blob Data Contributor" --scope $ST_ID -o none
az storage container create --account-name $ST --name l2-3-kb --auth-mode login -o tsv
az storage blob upload --account-name $ST --container-name l2-3-kb `
  --file product_info.md --name product_info.md --auth-mode login --overwrite --no-progress -o none
az storage blob list --account-name $ST --container-name l2-3-kb --auth-mode login --query "[].name" -o tsv
```
最後に `product_info.md` と表示されればOKです。キー無しでアップロードするには、自分に **Storage Blob Data Contributor** が要ります（Owner だけでは足りません）。付けた直後は反映に時間がかかり、`AuthorizationPermissionMismatch` になることがあります。そのときは1〜2分待って、下の3行を実行し直します。

### 5. ロールを付ける（自分・Search・プロジェクト）
```powershell
$SEARCH_ID = az search service show --name $SEARCH --resource-group $SRG --query id -o tsv
$SEARCH_MI = az search service show --name $SEARCH --resource-group $SRG --query identity.principalId -o tsv
$PROJECT_MI = az resource show --ids $PROJECT_ID --query identity.principalId -o tsv
az role assignment create --assignee-object-id $ME --assignee-principal-type User --role "Search Service Contributor" --scope $SEARCH_ID -o none
az role assignment create --assignee-object-id $ME --assignee-principal-type User --role "Search Index Data Contributor" --scope $SEARCH_ID -o none
az role assignment create --assignee-object-id $SEARCH_MI --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" --scope $ST_ID -o none
az role assignment create --assignee-object-id $SEARCH_MI --assignee-principal-type ServicePrincipal --role "Cognitive Services User" --scope $FOUNDRY_ID -o none
az role assignment create --assignee-object-id $PROJECT_MI --assignee-principal-type ServicePrincipal --role "Search Index Data Reader" --scope $SEARCH_ID -o none
az role assignment list --scope $SEARCH_ID --query "[].{role:roleDefinitionName, who:principalType}" -o table
```
| 誰に | どこに | ロール | 何のため |
|---|---|---|---|
| 自分 | Search | Search Service Contributor ＋ Search Index Data Contributor | ナレッジソース・ナレッジベースを作る（手順8） |
| Search のマネージド ID | ストレージ | Storage Blob Data Reader | 文書を取り込む |
| Search のマネージド ID | Foundry リソース | Cognitive Services User | 埋め込みモデルと、クエリ計画の LLM を呼ぶ |
| プロジェクトのマネージド ID | Search | Search Index Data Reader | エージェントがナレッジベースを検索する（手順10の接続が使う） |

最後の一覧に、Search にかかる3つのロール（Search Service Contributor・Search Index Data Contributor・Search Index Data Reader）が並べばOKです。**ロールの反映には5〜10分ほどかかる**ことがあるので、少し待ってから手順8に進みます。
> Foundry の RBAC のページは「Foundry では Cognitive Services で始まるロールを付けない」と案内していますが、Azure AI Search のナレッジソース・ナレッジベースのページは、Search のマネージド ID に **Cognitive Services User** を付けるよう案内しています。ここは Search の案内に従っています。

### 6. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 7. `.env` を作る
```powershell
Copy-Item .env.sample .env
(Get-Content .env) `
  -replace '<foundry>', $FOUNDRY -replace '<project>', $PROJECT -replace '<search>', $SEARCH `
  -replace '^STORAGE_RESOURCE_ID=.*', "STORAGE_RESOURCE_ID=$ST_ID" | Set-Content .env
Get-Content .env | Select-Object -First 4 | Select-String -NotMatch STORAGE
```
`.env.sample` の `<foundry>`・`<project>`・`<search>` を手順1・3の名前に置き換え、ストレージのリソース ID を入れます。最後の行で、置き換えたエンドポイント3つを表示します（ストレージのリソース ID はサブスクリプション ID を含むので表示しません）。

### 8. ナレッジソースとナレッジベースを作る
```powershell
python create_kb.py
```
```text
① ナレッジソース product-blob-ks：自動で作られたもの → product-blob-ks-datasource, product-blob-ks-indexer, product-blob-ks-skillset, product-blob-ks-index
② 取り込み完了：処理 1 件 / 失敗 0 件
③ ナレッジベース product-kb：推論の強さ=low、出力=extractiveData、ソース=['product-blob-ks']
MCP エンドポイント：https://ai103-search-<数字>.search.windows.net/knowledgebases/product-kb/mcp?api-version=2026-08-01-preview
```
- ①：Blob のナレッジソースを作ると、Search が **データソース・スキルセット・インデックス・インデクサー**の4つを自動で作り、文書を取り込みます（チャンク化・ベクトル化）。
- ②：取り込み（インデクサーの実行）が終わるまで、10秒おきに状態を見ます。文書1つなら数十秒で終わります。
- ③：ナレッジベースはナレッジソースを束ね、**クエリ計画に使う LLM**（`gpt-5.4`）と**推論の強さ**（`low`）を決めます。
- 403 が出たら、手順5のロールがまだ反映されていない可能性があります。数分待って実行し直します（それでも出るなら、手順3の `--auth-options aadOrApiKey` を確認）。

### 9. ナレッジベースの中で何が起きるかを見る
```powershell
python kb_retrieve.py
```
```text
質問: 延長保証のオプション名と、未開封品の返品期限は？
[クエリ計画] gpt-5.4  入力 914 / 出力 59 トークン
[検索] product-blob-ks ← 延長保証 オプション名 未開封品 返品期限（1 件）
[検索] product-blob-ks ← 未開封品 返品期限 延長保証 オプション名（1 件）
[検索] product-blob-ks ← 返品期限 未開封品 延長保証（1 件）
[推論の強さ] low  推論トークン 913
[根拠] 1 チャンク / 参照 1 件（エージェントにはこの抜き出しが渡る）
```
ナレッジベースの LLM が、1つの質問から**言い換えたサブクエリを作り、並行して**検索しています（クエリ計画）。今回は話題ごとには分かれていません。サブクエリの数と文面は実行のたびに変わります。エージェントのツール（手順11）も同じナレッジベースを検索しますが、MCP の結果には `activity` や `references` が付かないので、中身はこの手順で確かめます。

### 10. プロジェクトに MCP 接続（RemoteTool）を作る
```powershell
$MCP = "https://$SEARCH.search.windows.net/knowledgebases/product-kb/mcp?api-version=2026-08-01-preview"
@{ properties = @{ authType = "ProjectManagedIdentity"; category = "RemoteTool"; target = $MCP;
   isSharedToAll = $true; audience = "https://search.azure.com/"; metadata = @{ ApiType = "Azure" } } } |
  ConvertTo-Json -Depth 5 | Set-Content connection.json
az rest --method put `
  --url "https://management.azure.com$PROJECT_ID/connections/product-kb-mcp?api-version=2025-10-01-preview" `
  --body "@connection.json" `
  --query "{name:name, category:properties.category, auth:properties.authType}" -o table
```
`product-kb-mcp  RemoteTool  ProjectManagedIdentity` が表示されればOKです。エージェントがナレッジベースの MCP エンドポイントを呼ぶとき、この接続が**プロジェクトのマネージド ID**でトークンを取ります（宛先は `https://search.azure.com/`）。

### 11. エージェントにナレッジベースを付けて質問する
```powershell
python main.py
```
```text
エージェント作成: name=product-kb-agent, version=1

あなた> この製品の保証期間と対応OSを教えて。
[ツール] mcp_call 1 件
  knowledge_base_retrieve ← {"query_variants": ["この製品の保証期間と対応OSを教えて。"]}
AI> 保証期間は購入から1年間（無償修理）で、…対応OSは Windows 11 および macOS 14以降です【5:0†source】
…
あなた> この製品の重さは？
[ツール] mcp_call 1 件
  knowledge_base_retrieve ← {"query_variants": ["この製品の重さは？"]}
AI> 分かりません。製品情報には重さの記載がありません【13:0†source】

後片付け: エージェント 0 件が残っています
```
- `mcp_call` は、エージェントがナレッジベースのツール `knowledge_base_retrieve` を呼んだ記録です。エージェントのモデルが渡すのは `query_variants`（検索したい文）で、そこから先の検索のしかたはナレッジベースの推論の強さで決まります（手順9）。
- `【…†source】` は引用の印です。文書に答えが無い質問でも、検索で文書が見つかれば引用が付くことがあります。
- 文面は実行のたびに変わります。自分の質問は `python main.py "型番は？"` のように渡します。
- 403 が出たら、プロジェクトのマネージド ID の Search Index Data Reader（手順5）がまだ反映されていません。

### 12. 後片付け
**ここから先は、後の検索のハンズオン（`05_info_extraction/L5-1_search_grounding`）と共通の後片付けです。** 続けて進めるなら、①だけ実行して、②③はそのハンズオンの最後に行います。
```powershell
# ① このハンズオンの接続と、ナレッジベース・ナレッジソースを消す
az rest --method delete --url "https://management.azure.com$PROJECT_ID/connections/product-kb-mcp?api-version=2025-10-01-preview"
python create_kb.py --delete
```
```powershell
# ② 講座共通の Foundry リソースに付けた、Search のロールを外す（Search を消すと宛先不明のまま残るため）
az role assignment delete --assignee $SEARCH_MI --role "Cognitive Services User" --scope $FOUNDRY_ID
# ③ Search とストレージをリソースグループごと消す（Basic は置いておくだけで課金される）
$SRG
az group delete --name $SRG --yes --no-wait
```
- ③の前に、`$SRG` が `rg-udemy-ai-103-training-search` であることを目で確かめます。講座共通の `rg-udemy-ai-103-training` は消しません。
- エージェントと会話は、`main.py` が最後に消しています（手順11の `残り 0 件`）。エージェントや接続を消しても、ナレッジベースとナレッジソースは Search 側に残るので、①で別に消します。

## つまずきポイント
| 症状 | 原因と対処 |
|---|---|
| 手順4で `AuthorizationPermissionMismatch` | 自分の Storage Blob Data Contributor がまだ反映されていない。1〜2分待って再実行 |
| 手順8で 403 | 自分の Search Service Contributor / Search Index Data Contributor が未反映の可能性。5〜10分待つ。それでも出るなら Search を `--auth-options aadOrApiKey` で作ったかを確認 |
| 手順8の取り込みで失敗が1件以上 | Search のマネージド ID に Storage Blob Data Reader（ストレージ）か Cognitive Services User（Foundry）が無い |
| 手順11で 403 / ツールが呼ばれない | プロジェクトのマネージド ID に Search Index Data Reader が無い（または未反映）。`agent_instructions.txt` の「ツールを使って」も確認 |
| 手順11で 400 / 404 | MCP エンドポイントの Search 名・ナレッジベース名・API バージョン（`2026-08-01-preview`）を確認 |

## 試験の論点
- Foundry IQ は **ナレッジソース → ナレッジベース → エージェント**の3段。ナレッジベースは複数のエージェントで共有できる再利用可能な部品。
- エージェントからは **MCP ツール**（`knowledge_base_retrieve`。現時点で Foundry Agent Service から使える唯一のツール）として呼ぶ。認証は **RemoteTool** のプロジェクト接続（プロジェクトのマネージド ID）。
- ロール：プロジェクトの MI → Search に **Search Index Data Reader**、Search の MI → Foundry に **Cognitive Services User**（ナレッジベースが LLM を使うとき）。
- 推論の強さ（`minimal`／`low`／`medium`／プレビューの `auto`）：`minimal` は LLM を使わずクエリ計画をしない。`low` 以上で LLM がクエリをサブクエリに分ける。`medium` は結果が足りなければ1回だけ検索し直す。`auto` は軽い検索から始め、足りなければ LLM の計画へ進む。
- ユーザーごとの権限（プレビュー）を効かせるには、取り込み時に権限メタデータ（`ingestionPermissionOptions`）を入れ、MCP ツールの `headers` に `x-ms-query-source-authorization` を置いて、**structured inputs** でユーザーのトークンをリクエストごとに渡す。**ヘッダーが無いと絞り込まれずに全件返る**。ユーザーのトークンはプロジェクトのマネージド ID とは別物。

参照：https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect ／ https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-blob ／ https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base ／ https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-retrieve
