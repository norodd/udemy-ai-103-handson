# L5-1 実践: エンリッチしたインデックスを作り、エージェントの検索ツールに接続する

Blob に置いた文書を、Azure AI Search の **スキルセット**（Text Split でチャンク化 → Azure OpenAI Embedding でベクトル化）で取り込み、**ベクトル付きのインデックス**を作ります。そのインデックスを直接検索して検索方式の違いを見たあと、**Azure AI Search ツール**としてエージェントに付け、引用つきで答えさせます。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential` ＋ 各サービスのマネージド ID）。API キーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `docs/faq.md` | 取り込む文書（架空のアウトドア用品店 Contoso の FAQ） |
| `01_build_index.py` | インデックス・データソース・スキルセット・インデクサーの4つを作り、取り込みの完了を待ってチャンク数を表示する。`--delete` で4つを消す |
| `02_search_index.py` | 同じ質問を、キーワード・ベクトル・ハイブリッド＋セマンティックの3方式で検索し、上位のチャンクを並べる |
| `03_ask_agent.py` | インデックスを Azure AI Search ツールとして付けたエージェントを作り、3つ質問して、最後に消す |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-search-documents`、`azure-ai-projects>=2.0.0`、`azure-identity`、`python-dotenv`） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール・`gpt-5.4` のデプロイ）。
- **Azure AI Search（Basic）とストレージ**は、Foundry IQ のハンズオン（`02_genai_agents/L2-3_foundry_iq`）の手順3で作った `rg-udemy-ai-103-training-search` のものを使います。まだ作っていない（または消した）場合は、そのハンズオンの **README 手順3（作成）と手順4の上2行（自分へのロール）** を先に実行してください。
- `az login` 済み ／ Python 3.11+
- ロールを付けるので、サブスクリプション（またはリソースグループ）の **Owner** か **User Access Administrator** が要ります。
- **費用**：Azure AI Search の Basic は、**置いておくだけで時間単位の課金**があります。このハンズオンの最後（手順12）で、Search とストレージをリソースグループごと消します。ほかは埋め込みと推論のトークン代だけです。

## 進め方（コピペで実行できます）

全部で12手順です。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | リソースの名前を変数に入れる |
| 2 | チャットモデルと埋め込みモデルのデプロイを確かめる |
| 3 | Search の設定を確かめる |
| 4 | 文書をストレージにアップロードする |
| 5 | ロールを付ける（自分・Search・プロジェクト） |
| 6 | 仮想環境を作って依存を入れる |
| 7 | `.env` を作る |
| 8 | エンリッチしたインデックスを作る |
| 9 | インデックスを3つの方式で検索する |
| 10 | プロジェクトに Azure AI Search の接続を作る |
| 11 | エージェントに検索ツールを付けて質問する |
| 12 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 05_info_extraction/L5-1_search_grounding
> ```

### 1. リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$PROJECT = "ai103-project"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY_ID = az cognitiveservices account show --name $FOUNDRY --resource-group $RG --query id -o tsv
$PROJECT_ID = "$FOUNDRY_ID/projects/$PROJECT"
$SRG = "rg-udemy-ai-103-training-search"
$SEARCH = az search service list --resource-group $SRG --query "[0].name" -o tsv
$ST = az storage account list --resource-group $SRG --query "[0].name" -o tsv
"$FOUNDRY / $SEARCH / $ST"
```
`ai103-foundry-<数字> / ai103-search-<数字> / ai103st<数字>` のように3つの名前が表示されればOKです。Search とストレージの名前が空なら、前提の Foundry IQ のハンズオン（手順3）を先に実行します。`$FOUNDRY_ID`・`$PROJECT_ID` はリソース ID で、手順5・10で使います（サブスクリプション ID を含むので、画面には出していません）。

### 2. チャットモデルと埋め込みモデルのデプロイを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
一覧に `gpt-5.4` と `text-embedding-3-large` があればOKです。`text-embedding-3-large` は文書のチャンクと質問文のベクトル化に、`gpt-5.4` はエージェントの頭脳に使います。`text-embedding-3-large` が無ければ、Foundry IQ のハンズオンの手順2のコマンドでデプロイします。

### 3. Search の設定を確かめる
```powershell
az search service show --name $SEARCH --resource-group $SRG `
  --query "{sku:sku.name, identity:identity.type, auth:keys(authOptions)[0], semantic:semanticSearch}" -o table
```
`basic  SystemAssigned  aadOrApiKey  free` が表示されればOKです。
- **Basic 以上**：Free はマネージド ID を使えないので、このキーレス構成では使えません。
- **SystemAssigned**：Search が、自分のマネージド ID で Blob と埋め込みモデルをキー無しで読みます。
- **aadOrApiKey**：ロール（Microsoft Entra ID）でも呼べる設定です（既定は API キーだけ）。
- **free**：セマンティックランカーのプランです。月の無料枠の範囲で使えます（手順9・11のハイブリッド＋セマンティック検索が使う）。

### 4. 文書をストレージにアップロードする
```powershell
$ST_ID = az storage account show --name $ST --resource-group $SRG --query id -o tsv
az storage container create --account-name $ST --name l5-1-docs --auth-mode login -o tsv
az storage blob upload --account-name $ST --container-name l5-1-docs `
  --file docs/faq.md --name faq.md --auth-mode login --overwrite --no-progress -o none
az storage blob list --account-name $ST --container-name l5-1-docs --auth-mode login --query "[].name" -o tsv
```
最後に `faq.md` と表示されればOKです（2行目の `True` はコンテナーを新しく作ったという意味で、既にあれば `False`）。キー無しでアップロードするには、自分に **Storage Blob Data Contributor** が要ります（Foundry IQ のハンズオンの手順4で付けています）。

### 5. ロールを付ける（自分・Search・プロジェクト）
```powershell
$ME = az ad signed-in-user show --query id -o tsv
$SEARCH_ID = az search service show --name $SEARCH --resource-group $SRG --query id -o tsv
$SEARCH_MI = az search service show --name $SEARCH --resource-group $SRG --query identity.principalId -o tsv
$PROJECT_MI = az resource show --ids $PROJECT_ID --query identity.principalId -o tsv
az role assignment create --assignee-object-id $ME --assignee-principal-type User --role "Search Service Contributor" --scope $SEARCH_ID -o none
az role assignment create --assignee-object-id $ME --assignee-principal-type User --role "Search Index Data Contributor" --scope $SEARCH_ID -o none
az role assignment create --assignee-object-id $SEARCH_MI --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" --scope $ST_ID -o none
az role assignment create --assignee-object-id $SEARCH_MI --assignee-principal-type ServicePrincipal --role "Cognitive Services User" --scope $FOUNDRY_ID -o none
az role assignment create --assignee-object-id $PROJECT_MI --assignee-principal-type ServicePrincipal --role "Search Index Data Contributor" --scope $SEARCH_ID -o none
az role assignment create --assignee-object-id $PROJECT_MI --assignee-principal-type ServicePrincipal --role "Search Service Contributor" --scope $SEARCH_ID -o none
az role assignment list --scope $SEARCH_ID --query "[].{role:roleDefinitionName, who:principalType}" -o table
```
| 誰に | どこに | ロール | 何のため |
|---|---|---|---|
| 自分 | Search | Search Service Contributor ＋ Search Index Data Contributor | インデックス・スキルセットなどを作り、検索する（手順8・9） |
| Search のマネージド ID | ストレージ | Storage Blob Data Reader | インデクサーが文書を読む |
| Search のマネージド ID | Foundry リソース | Cognitive Services User | 埋め込みスキルと、クエリ時のベクトル化（vectorizer）が埋め込みモデルを呼ぶ |
| プロジェクトのマネージド ID | Search | Search Index Data Contributor ＋ Search Service Contributor | エージェントの Azure AI Search ツールがインデックスを検索する（手順10の接続が使う） |

- Foundry IQ のハンズオンで付けたロールと重なるものは、実行しても同じ割り当てが返るだけです。
- 最後の一覧に、Search にかかるロールが並べばOKです。**ロールの反映には5分ほどかかる**ことがあります。
- Azure AI Search ツールのページは、前提の節では「Foundry リソース（アカウント）のマネージド ID」、トラブルシュートの表では「プロジェクトのマネージド ID」に付けるよう書いています。講座の検証（2026-09-24）では、**プロジェクトのマネージド ID** に付けたときに通りました。

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
Get-Content .env | Select-String "ENDPOINT"
```
`.env.sample` の `<foundry>`・`<project>`・`<search>` を手順1の名前に置き換え、ストレージのリソース ID を入れます。最後の行で、置き換えたエンドポイント3つを表示します（ストレージのリソース ID はサブスクリプション ID を含むので表示しません）。

### 8. エンリッチしたインデックスを作る
```powershell
python 01_build_index.py
```
```text
① インデックス  l5-1-outdoor
② データソース  l5-1-outdoor-ds（コンテナー l5-1-docs）
③ スキルセット  l5-1-outdoor-ss（Text Split 300字・重なり30字 → Embedding 3072次元）
④ インデクサー  l5-1-outdoor-idxr
⑤ 取り込み      success：処理 1 件 / 失敗 0 件
⑥ インデックスのドキュメント数（＝チャンク数） 3
```
- ①〜④の4つが、Azure AI Search の**インデックス作成パイプライン**です。インデクサーがデータソース（Blob）から文書を読み、スキルセットでチャンク化とベクトル化をして、インデックスに書き込みます。
- ③のスキルセットが **AI エンリッチメント**の部分です。Text Split が文書を最大 300 字のチャンクに、なるべく文の切れ目で区切り（前のチャンクと 30 字重ねる）、Azure OpenAI Embedding が各チャンクをベクトルにします。300 は設定できる最小の値です（これより小さいとスキルセットの作成が 400 になります）。
- ⑥：文書は1つでも、チャンクに分けて**チャンクごとに1ドキュメント**として入ります（index projections）。
- 失敗が1件以上なら、手順5の Search のマネージド ID のロール（ストレージ・Foundry）を確かめます。403 なら自分のロールがまだ反映されていません。

### 9. インデックスを3つの方式で検索する
```powershell
python 02_search_index.py
```
```text
質問: 送料はいくら？
[キーワード]
  0.284  返品・交換 / バックパック SummitPack / お手入れ
  0.262  お手入れ / 配送 / サポート窓口
[ベクトル]
  0.617  お手入れ / 配送 / サポート窓口
  0.595  返品・交換 / バックパック SummitPack / お手入れ
[ハイブリッド＋セマンティック]
  2.757  お手入れ / 配送 / サポート窓口
  1.982  返品・交換 / バックパック SummitPack / お手入れ
```
- 各行は、上位のチャンクの点数と、そのチャンクに入っている見出しです。答え（送料の金額）は「配送」の見出しがあるチャンクにあります。
- **キーワード**は「返品・交換」のチャンクを1位にしました。どちらのチャンクにも「送料」の語があり（返品のほうは「返品送料」）、キーワード検索は語の一致しか見ないので、答えの無いチャンクが僅差で上に来ました。点数の差は小さく、実行によって順位が入れ替わることもあります。**ベクトル**は意味の近さで「配送」のチャンクを1位にしています。**ハイブリッド＋セマンティック**は両方の結果を合わせ（RRF）、さらにセマンティックランカーで並べ直したものです。この行の点数は、セマンティックランカーの点数（`@search.reranker_score`、0〜4）です。点数の尺度は方式ごとに違うので、方式をまたいで点数を比べません。
- 「お手入れ」が2つのチャンクに出てくるのは、手順8の**重なり（30字）**のためです。
- 質問は `python 02_search_index.py "雨の日に荷物を濡らさないには？"` のように渡せます。順位や点数は質問によって変わります。

### 10. プロジェクトに Azure AI Search の接続を作る
```powershell
@{ properties = @{ authType = "AAD"; category = "CognitiveSearch"; target = "https://$SEARCH.search.windows.net";
   isSharedToAll = $true; metadata = @{ ApiType = "Azure"; ResourceId = $SEARCH_ID } } } |
  ConvertTo-Json -Depth 5 | Set-Content connection.json
az rest --method put `
  --url "https://management.azure.com$PROJECT_ID/connections/l5-1-search?api-version=2025-10-01-preview" `
  --body "@connection.json" `
  --query "{name:name, category:properties.category, auth:properties.authType}" -o table
```
`l5-1-search  CognitiveSearch  AAD` が表示されればOKです。`AAD` は API キーではなく **Microsoft Entra ID**（マネージド ID）で Search に入る接続です。エージェントの Azure AI Search ツールは、この接続を名前で指定して使います（`.env` の `SEARCH_CONNECTION_NAME`）。Foundry ポータルの「接続されたリソース」から作っても同じです。

### 11. エージェントに検索ツールを付けて質問する
```powershell
python 03_ask_agent.py
```
```text
エージェント作成: name=l5-search-agent, version=1

あなた> テントの保証期間は？
[ツール] azure_ai_search_call 1 件
  検索クエリ ← テント 保証期間 保証 warranty tent
AI> テントの保証期間は3年です。通常使用での縫製・ファスナーの不具合が対象です【4:0†source】
[引用] 1 件 ['doc_0']
…
あなた> テントの価格は？
[ツール] azure_ai_search_call 1 件
  検索クエリ ← テント 価格
AI> 分かりません。検索結果にはテントの価格情報は見つかりませんでした【4:0†source】【4:1†source】
[引用] 2 件 ['doc_0', 'doc_1']

後片付け: エージェント 0 件が残っています
```
- `azure_ai_search_call` は、エージェントが Azure AI Search ツールでインデックスを検索した記録です。`検索クエリ` は、**モデルが質問から作った検索文**で、質問そのままとは限りません（英語が混ざることもあります）。
- 答えが見つからない質問にも引用が付くことがあります。引用は「検索して参照した文書」を示すだけで、答えがそこに書いてあったという意味ではありません。
- `【…†source】` は引用の印で、`[引用]` は応答に付いた `url_citation` の注釈です。
- 文面・件数・引用は実行のたびに変わります。自分の質問は `python 03_ask_agent.py "返品の期限は？"` のように渡します。
- `Access denied. Check your permissions or managed identity access to the search service` が出たら、手順5のプロジェクトのマネージド ID のロールがまだ反映されていません。数分待って実行し直します。

### 12. 後片付け
```powershell
# ① 接続と、手順8で作った4つの検索オブジェクトを消す（エージェントは 03_ask_agent.py が消している）
az rest --method delete --url "https://management.azure.com$PROJECT_ID/connections/l5-1-search?api-version=2025-10-01-preview"
python 01_build_index.py --delete
# ② 講座共通の Foundry リソースに付けた、Search のロールを外す（Search を消すと宛先不明のまま残るため）
az role assignment delete --assignee $SEARCH_MI --role "Cognitive Services User" --scope $FOUNDRY_ID
az role assignment list --assignee $SEARCH_MI --all --query "length(@)" -o tsv
```
```powershell
# ③ Search とストレージをリソースグループごと消す（Basic は置いておくだけで課金される）
$SRG
az group delete --name $SRG --yes --no-wait
```
- ②の最後の数字は、Search のマネージド ID に残っている割り当ての数です。ストレージへの Storage Blob Data Reader の1件は、③でリソースグループごと消えます。
- ③の前に、`$SRG` が `rg-udemy-ai-103-training-search` であることを目で確かめます。講座共通の `rg-udemy-ai-103-training` は消しません。
- 削除は数分で終わります。`az group exists --name rg-udemy-ai-103-training-search` が `false` を返せば完了です。
- Foundry IQ のハンズオンの手順12②③と同じ後片付けです。どちらか一方で1回やれば足ります。

## つまずきポイント
| 症状 | 原因と対処 |
|---|---|
| 手順1で Search・ストレージの名前が空 | `rg-udemy-ai-103-training-search` がまだ無い。Foundry IQ のハンズオンの手順3で作る |
| 手順4で `AuthorizationPermissionMismatch` | 自分の Storage Blob Data Contributor が無いか未反映。Foundry IQ のハンズオンの手順4で付け、1〜2分待つ |
| 手順8で 403 | 自分の Search Service Contributor / Search Index Data Contributor が未反映。数分待つ |
| 手順8の取り込みで失敗が1件以上 | Search のマネージド ID に Storage Blob Data Reader（ストレージ）か Cognitive Services User（Foundry）が無い |
| 手順9のベクトル検索で 400 / 403 | クエリ時のベクトル化（vectorizer）も Search のマネージド ID で埋め込みモデルを呼ぶ。Cognitive Services User を確かめる |
| 手順11で `Access denied … search service` | プロジェクトのマネージド ID に Search Index Data Contributor ＋ Search Service Contributor が無いか未反映 |
| 手順11で index not found | `.env` の `SEARCH_INDEX_NAME` のつづり（インデックス名は小文字のみ）、手順12の `--delete` で消していないか、接続の Search 名を確認 |

## 試験の論点
- インデックス作成パイプラインは **データソース → スキルセット → インデックス → インデクサー**。**統合ベクトル化**は、取り込み時のベクトル化（スキルセットの Text Split でチャンク化 ＋ Azure OpenAI Embedding でベクトル化）と、クエリ時の質問文のベクトル化（インデックスに定義した **vectorizer**）の両方を Search に任せる仕組み（アプリ側で埋め込みを呼ばなくてよい）。
- 検索方式：キーワード（語の一致）・ベクトル（意味の近さ）・**ハイブリッド**（両方を RRF で合成）＋**セマンティックランカー**（並べ直し）。エージェントの Azure AI Search ツールの既定は `vector_semantic_hybrid`。
- キーレス構成のロール：Search の MI → ストレージに **Storage Blob Data Reader**、Search の MI → 埋め込みモデルのリソースに推論のロール、エージェント側の MI → Search に **Search Index Data Contributor ＋ Search Service Contributor**。
- Azure AI Search ツールが対象にできるインデックスは **1つ**。引用は `url_citation` の注釈で返る。

参照：https://learn.microsoft.com/azure/foundry/agents/how-to/tools/ai-search ／ https://learn.microsoft.com/azure/search/vector-search-integrated-vectorization ／ https://learn.microsoft.com/azure/search/cognitive-search-skill-textsplit ／ https://learn.microsoft.com/azure/search/cognitive-search-skill-azure-openai-embedding ／ https://learn.microsoft.com/azure/search/hybrid-search-overview
