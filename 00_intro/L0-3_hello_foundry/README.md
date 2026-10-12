# L0-3 実践: Hello, Foundry

Microsoft Foundry プロジェクトに**キーレス**（`DefaultAzureCredential`）で接続し、Responses API でチャットモデルを1回呼んで応答を表示する、最小のサンプルです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）です。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | Foundry プロジェクトへキーレス接続し、Responses API を1回呼ぶ最小サンプル |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- Azure サブスクリプション（従量課金）／`az login` 済み
- Python 3.11+、Azure CLI 2.80.0 以上（`az version` で確認。`az cognitiveservices account project` コマンドは 2.80.0 で追加）

## 進め方（コピペで実行できます）

全部で11手順です（その前に、初回だけ手順0で Azure CLI にサインインします）。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。

| 手順 | やること |
|---|---|
| 0 | Azure CLI にサインインする（初回だけ） |
| 1 | サインイン先を確かめる |
| 2 | クォータティアを確認する |
| 3 | リソースグループを作る |
| 4 | Foundry リソースを作る |
| 5 | プロジェクトを作る |
| 6 | チャットモデルをデプロイする |
| 7 | プロジェクトのエンドポイントを取得する |
| 8 | 自分に Foundry User ロールを付ける |
| 9 | 仮想環境を作って依存を入れる |
| 10 | `.env` を用意する |
| 11 | 実行する |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。手順4の変数や手順8の `( … )` は PowerShell の書き方なので、bash / zsh ではなく PowerShell で進めてください。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 00_intro/L0-3_hello_foundry
> ```

### 0. Azure CLI にサインインする（初回だけ）
このハンズオンは、Azure CLI でサインインしたアカウントの資格情報を、コマンドと `main.py`（`DefaultAzureCredential`）の両方で使います。まず Azure CLI が入っているかを確認します。
```powershell
az version
```
`az` が見つからないと表示された場合は、[Azure CLI をインストール](https://learn.microsoft.com/cli/azure/install-azure-cli)してから、ターミナルを開き直してください（Codespaces / Dev Container には最初から入っています）。

続いてサインインします。
```powershell
az login
```
- ブラウザが開くので、Azure サブスクリプションのアカウントでサインインします。サブスクリプションが複数ある場合は、ターミナルに一覧が出るので、使うものの番号を選びます。
- **Codespaces の場合や、ブラウザが開かない場合**は `az login --use-device-code` を実行します。表示された URL（https://microsoft.com/devicelogin ）を手元のブラウザで開き、表示されたコードを入力してサインインします。
- 複数のテナント（ディレクトリ）に所属していて目的のサブスクリプションが一覧に出ない場合は、`az login --tenant <テナントID>` でテナントを指定します。
- サインインは一度行えば、以降のレッスンでもそのまま使えます。Codespaces を作り直した場合や、時間がたって `401` やトークン期限切れのエラーが出た場合は、もう一度 `az login` を実行してください。

### 1. サインイン先を確かめる
```powershell
az account show --query "{subscription:name, state:state}" -o table
```
使うサブスクリプション名が表示されればOKです。別のサブスクリプションが出た場合は `az account set --subscription "<サブスクリプション名またはID>"` で切り替えます。

### 2. クォータティアを確認する（ポータルには出ないので API で見る）
```powershell
az rest --method get `
  --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.CognitiveServices/quotaTiers?api-version=2026-05-01" `
  --query "value[].properties" -o table
```
`CurrentTierName` に今のティアが出ます。**最下位ティア**（Free Tier / Tier 0）だった場合、既定クォータが付くのは `gpt-4.1-mini` / `gpt-5-mini` / `o4-mini` / `text-embedding-3-small` の4モデルだけです。その場合は以下の `gpt-5.4-nano` を `gpt-4.1-mini` に読み替えてください（`.env` の `MODEL_DEPLOYMENT` も同じ名前にします。手順・学習目的は変わりません）。

> ⚠️ `quotaTiers` の api-version は更新が速く、通る値が入れ替わります（2026-09-23 実測：`2026-05-01` は通り、`2023-05-01` や `2026-09-01` は `InvalidResourceType` の404）。404 のエラーメッセージに「サポートされる api-version の一覧」が出るので、その中の値に差し替えてください。

### 3. リソースグループを作る
このリソースグループと、次に作る Foundry リソース・プロジェクトは、**講座全体で共通**に使います（以降のレッスンは、ここで作るプロジェクトのエンドポイントを使い回します）。
```powershell
az group create --name rg-udemy-ai-103-training --location japaneast `
  --query "{name:name, state:properties.provisioningState}" -o table
```

### 4. Foundry リソースを作る
1行目で、Foundry リソースの名前を変数 `$FOUNDRY` に決めます。この名前はカスタムドメイン（`https://<名前>.services.ai.azure.com`）にもなるので**世界で一意**である必要があり、末尾に乱数を付けています。
```powershell
$FOUNDRY = "ai103-foundry-$(Get-Random -Minimum 10000 -Maximum 99999)"
az cognitiveservices account create `
  --name $FOUNDRY `
  --resource-group rg-udemy-ai-103-training `
  --kind AIServices `
  --sku S0 `
  --location japaneast `
  --custom-domain $FOUNDRY `
  --assign-identity `
  --allow-project-management true `
  --query "{name:name, kind:kind, state:properties.provisioningState}" -o table
```
- 手順5〜8も `$FOUNDRY` を使います。**同じターミナルで続けて**実行してください。ターミナルを開き直した場合は、`$FOUNDRY = az cognitiveservices account list -g rg-udemy-ai-103-training --query "[0].name" -o tsv` で取り直せます。
- 使用済みの名前だと `CustomDomainInUse` になります。1行目からもう一度実行すれば、別の乱数で作り直せます。
- `--assign-identity` が無いと、次のプロジェクト作成が `managed identity must be enabled` で失敗します。
- ⚠️ **既存アカウントに対してこのコマンドを再実行すると** `(BadRequest) PublicNetworkAccess is required for this resouce`（Azure側のスペルミスもそのまま）で失敗します。`--public-network-access Enabled` という引数は存在しません（`unrecognized arguments`）。**既にリソースがある場合は `create` を再実行せず**、`az cognitiveservices account show --name $FOUNDRY --resource-group rg-udemy-ai-103-training` で状態を確認するだけにしてください。

### 5. プロジェクトを作る
```powershell
az cognitiveservices account project create `
  --name $FOUNDRY `
  --resource-group rg-udemy-ai-103-training `
  --project-name ai103-project `
  --location japaneast `
  --query "{name:name, state:properties.provisioningState}" -o table
```
> ⚠️ 親のリソースを指す引数は `--account-name` ではなく **`--name`/`-n`** です（`--account-name` はこのサブコマンドでは通らず `the following arguments are required: --name/-n` になります）。`project create` は `--project-name` も必須です。

### 6. チャットモデルをデプロイする
```powershell
az cognitiveservices account deployment create `
  --name $FOUNDRY `
  --resource-group rg-udemy-ai-103-training `
  --deployment-name gpt-5.4-nano `
  --model-name gpt-5.4-nano `
  --model-version "2026-03-17" `
  --model-format OpenAI `
  --sku-capacity 10 `
  --sku-name GlobalStandard `
  --query "{name:name, state:properties.provisioningState}" -o table
```
`State` が `Succeeded` になればOKです。あとから状態だけ確かめたいときは `deployment create` を `deployment show` に変え、`--model-*` と `--sku-*` の行を外して実行します。
> ⚠️ `--model-version` と対応 SKU は更新されます。収録時点の値が古い場合は、ポータルのモデルカードか `az cognitiveservices model list --location japaneast --query "[?model.name=='gpt-5.4-nano'].{version:model.version,skus:join(',',model.skus[].name)}" -o table` で現行の値を確認して指定してください。

### 7. プロジェクトのエンドポイントを取得する
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group rg-udemy-ai-103-training `
  --project-name ai103-project `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
```
- 返ってきた URL（末尾が `/api/projects/ai103-project`）を、手順10で `.env` に貼ります。
- ⚠️ **Build > Models のデプロイ詳細に出るエンドポイントとは別物**です。そちらを貼ると `main.py` は404になります。ポータルなら、プロジェクトの**ホーム（welcome）画面**に出る「プロジェクト エンドポイント」を使ってください。

### 8. 自分に Foundry User ロールを付ける
コードからモデルを呼ぶ（データプレーンの操作）には、**Foundry User** ロールが必要です。ポータルで作った場合は自動で付きますが、**CLI や SDK で作った場合は付きません**。Owner や Contributor もモデルの呼び出し権限は含みません。自分のアカウントに、手順4のリソースを範囲として付けます。
```powershell
az role assignment create `
  --role "Foundry User" `
  --assignee (az ad signed-in-user show --query id -o tsv) `
  --scope (az cognitiveservices account show --name $FOUNDRY --resource-group rg-udemy-ai-103-training --query id -o tsv) `
  --query "{principalType:principalType, created:createdOn}" -o table
```
- `principalType` が `User` の行が出れば割り当てできています。反映まで数分かかることがあります（手順11で 403 が出たら、少し待ってから再実行）。
- ロールの割り当てには、サブスクリプションかリソースグループで **Owner**（または User Access Administrator）が必要です。権限が無い場合は、管理者にこのロールの割り当てを依頼してください。
- `Foundry User` という名前が見つからない（`Role 'Foundry User' doesn't exist`）場合は、旧名の反映待ちです。`--role` にロール ID `53ca6127-db72-4b80-b1b0-d745d6d5456d` を指定してください。

### 9. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
./.venv/bin/Activate.ps1
pip install -r requirements.txt
```
- 2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell は `.\.venv\Scripts\Activate.ps1`、bash / zsh は `source .venv/bin/activate` にします。
- プロンプトの先頭に `(.venv)` が付けば有効化できています。

> ⚠️ `azure-ai-projects` は **2.x**（新／Foundry プロジェクト）を使います。1.x（classic／Hub）とは互換性がありません。`pip show azure-ai-projects` で2.0以上を確認してください。

### 10. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順7のエンドポイントを貼り、`MODEL_DEPLOYMENT` を手順6のデプロイ名（`gpt-5.4-nano`）にして保存します（`.env` は `.gitignore` 対象です。コードに直書き・コミットしないでください）。

### 11. 実行する
```powershell
python main.py
```

## 期待される出力（例）
```
✅ キーレスで接続: https://ai103-foundry-12345.services.ai.azure.com/api/projects/ai103-project

----- モデル応答 -----
（モデルからの説明文が続く）
```
呼び出しが成功したことと、答えの内容が正しいことは別です。モデルはそれらしい文章を自信を持って書くことがあるので、内容が正しいかは自分で確認してください。

## つまずき
- **`DefaultAzureCredential failed to retrieve a token`**（環境変数・マネージドID・Azure CLI などの資格情報がすべて失敗した、という表示）：Azure CLI にサインインしていません。手順0の `az login` を実行してください。
- **`401`（認証エラー）**：`az login` していない／トークン期限切れ。`az login` をやり直し、`az account show` で正しいサブスクリプションか確認。
- **`403`**：手順8の **Foundry User** ロールが付いているか確認（付けた直後は反映に数分かかることがある）。
- **`404`（モデルが見つからない）**：`.env` の `MODEL_DEPLOYMENT` は**カタログ名ではなくデプロイ名**。実際のデプロイ名と一致しているか確認。
- **`az cognitiveservices account create` が `(InsufficientQuota)` で失敗**：モデルのTPMではなく**リソース作成レベルの別クォータ**です。無料試用版・学生サブスクリプションで起きやすく、従量課金への切り替えかサポートリクエストが必要です。
- **`insufficient quota` でデプロイできない**：手順2のクォータティア確認に戻り、`gpt-4.1-mini` 等の最下位ティアで使えるモデルに読み替えてください。

## 後片付け
ここで作ったリソースグループ・Foundry リソース・プロジェクトは、**講座の最後まで共通で使います**。消さずに残しておいてください（Standard デプロイは呼び出さない限り課金されません）。学習を長く中断する場合や、講座を終えて完全に片付ける場合だけ、次を実行します：
```powershell
az group delete --name rg-udemy-ai-103-training --yes --no-wait
```
