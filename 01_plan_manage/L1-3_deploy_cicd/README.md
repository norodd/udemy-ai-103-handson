# L1-3 実践: Foundry でのソリューション構築（インフラ／デプロイ／CI-CD）

モデルデプロイを **CLI／Bicep（IaC）で再現**し、**スモークテスト**で動作確認、さらに **GitHub Actions の雛形**で「評価ゲート → デプロイ」の流れを体験するハンズオンです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `deploy_model.azcli` | README 手順1〜8（CLI で作る）をスクリプトにまとめたもの（参考） |
| `main.bicep` | **IaC（Bicep）**：同じ構成を宣言的にコード化（`accounts`／`accounts/projects`／`accounts/deployments`） |
| `deploy_bicep.azcli` | README 手順9〜10（Bicep の what-if → 適用）をまとめたもの（参考） |
| `main.py` | デプロイの**スモークテスト**（キーレスで推論し、デプロイの健全性を確認） |
| `.env.sample` | `main.py` 用の環境変数雛形（`PROJECT_ENDPOINT` / `DEPLOYMENT_NAME`） |
| `requirements.txt` | Python 依存パッケージ |
| `eval/dataset.json` | 評価ゲート用のデータセット（評価器＋テストクエリ） |
| `github-workflow-sample/evaluate-and-deploy.yml` | **GitHub Actions 雛形**：PR で評価ゲート、main で評価→デプロイ |

## 前提
- L0-3（Hello, Foundry）を終えていること（`az login` 済み・Python 3.11+・Azure CLI 2.80.0 以上）
- このレッスンは **「Foundry リソースを作ること」そのものが主題**なので、講座共通のリソース（`rg-ai103`）は使わず、**練習用のリソースグループ `rg-ai103-l13` に作って、最後に丸ごと消します**。共通のリソースには一切触れません。
- 作成には、サブスクリプションかリソースグループで **Contributor 以上**が必要です。

## 進め方（コピペで実行できます）

全部で14手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 練習用の名前を変数に決める |
| 2 | 練習用のリソースグループを作る |
| 3 | Foundry リソースを作る |
| 4 | キー認証を無効にする（キーレス強制） |
| 5 | プロジェクトを作る |
| 6 | 使えるモデルを確かめる |
| 7 | モデルをデプロイする |
| 8 | デプロイの状態を確かめる |
| 9 | Bicep で差分を見る（what-if） |
| 10 | Bicep を適用する |
| 11 | 自分に Foundry User ロールを付ける |
| 12 | 仮想環境を作って依存を入れる |
| 13 | `.env` を用意してスモークテストを流す |
| 14 | 後片付け（練習用のリソースグループを消す） |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 01_plan_manage/L1-3_deploy_cicd
> ```

### 1. 練習用の名前を変数に決める
Foundry リソースの名前はサブドメイン（`https://<名前>.services.ai.azure.com`）になるので**世界で一意**にする必要があり、末尾に乱数を付けます。
```powershell
$RG = "rg-ai103-l13"
$LOCATION = "japaneast"
$ACCOUNT = "ai103-l13-$(Get-Random -Minimum 10000 -Maximum 99999)"
$PROJECT = "ai103-l13-proj"
$DEPLOYMENT = "chat"
$ACCOUNT
```

### 2. 練習用のリソースグループを作る
```powershell
az group create --name $RG --location $LOCATION `
  --query "{name:name, state:properties.provisioningState}" -o table
```

### 3. Foundry リソースを作る
```powershell
az cognitiveservices account create `
  --name $ACCOUNT `
  --resource-group $RG `
  --kind AIServices `
  --sku S0 `
  --location $LOCATION `
  --custom-domain $ACCOUNT `
  --allow-project-management true `
  --assign-identity `
  --query "{name:name, kind:kind, state:properties.provisioningState}" -o table
```
- `--kind AIServices` が Foundry リソース、`--allow-project-management` がプロジェクトを作れるようにする指定、`--custom-domain` が Entra ID 認証に必要なサブドメイン、`--assign-identity` がマネージド ID です。

### 4. キー認証を無効にする（キーレス強制）
`az cognitiveservices account update` にはキー認証を無効にするオプションが無いので、汎用の `az resource update` で `properties.disableLocalAuth` を設定します。
```powershell
az resource update `
  --ids (az cognitiveservices account show --name $ACCOUNT --resource-group $RG --query id -o tsv) `
  --set properties.disableLocalAuth=true `
  --query "properties.disableLocalAuth" -o tsv
```
`true` が返れば、この Foundry リソースは Entra ID（キーレス）でしか呼べなくなります（反映には数分かかることがあります）。

### 5. プロジェクトを作る
```powershell
az cognitiveservices account project create `
  --name $ACCOUNT `
  --resource-group $RG `
  --project-name $PROJECT `
  --location $LOCATION `
  --query "{name:name, state:properties.provisioningState}" -o table
```

### 6. 使えるモデルを確かめる
モデル名・バージョン・SKU は更新が速いので、デプロイの前にこのリソースで使える値を確かめます。
```powershell
az cognitiveservices account list-models `
  --name $ACCOUNT `
  --resource-group $RG `
  --query "[?name=='gpt-5.4-nano'].{name:name, version:version, format:format}" -o table
```

### 7. モデルをデプロイする
```powershell
az cognitiveservices account deployment create `
  --name $ACCOUNT `
  --resource-group $RG `
  --deployment-name $DEPLOYMENT `
  --model-name gpt-5.4-nano `
  --model-version "2026-03-17" `
  --model-format OpenAI `
  --sku-name GlobalStandard `
  --sku-capacity 10 `
  --query "{name:name, state:properties.provisioningState}" -o table
```
デプロイ名 `chat` が、コードから呼ぶときに `model` に渡す名前になります（カタログのモデル名ではありません）。

### 8. デプロイの状態を確かめる
```powershell
az cognitiveservices account deployment show `
  --name $ACCOUNT `
  --resource-group $RG `
  --deployment-name $DEPLOYMENT `
  --query "{state:properties.provisioningState, model:properties.model.name, version:properties.model.version, upgrade:properties.versionUpgradeOption}" -o table
```
`upgrade`（バージョン自動更新ポリシー）は CLI では読み取りだけで、変更は REST／Azure PowerShell／ポータルで行います。

### 9. Bicep で差分を見る（what-if）
手順3〜7で作ったものと同じ構成を、`main.bicep` で宣言しています。同じリソースグループに対して **what-if** を実行すると、「適用したら何が変わるか」だけが表示され、何も作られません（CI/CD の PR 段階に相当）。
```powershell
az deployment group what-if `
  --resource-group $RG `
  --template-file main.bicep `
  --parameters foundryName=$ACCOUNT projectName=$PROJECT deploymentName=$DEPLOYMENT
```
- すでに同じものがあるので、新しく作られるもの（`+ Create`）は出ず、3つとも `~ Modify` になります。
- `-` の付いた行は、テンプレートに書いていない、Azure 側で付いた値です。what-if は冒頭の Note のとおりノイズ（誤検知）を含むので、`-` を見たら「本当に消してよい値か」を読んでから適用を判断します。

### 10. Bicep を適用する
```powershell
az deployment group create `
  --resource-group $RG `
  --template-file main.bicep `
  --parameters foundryName=$ACCOUNT projectName=$PROJECT deploymentName=$DEPLOYMENT `
  --query "properties.outputs.{projectEndpoint:projectEndpoint.value, deployment:deploymentNameOut.value}" -o table
```
- 宣言型なので、何度適用しても同じ状態になります（冪等）。リソースは増えません。
- 出力の `projectEndpoint` が、手順13で `.env` に書く値です（同じテンプレートの `foundryEndpoint` はアカウント単位の別物）。

### 11. 自分に Foundry User ロールを付ける
CLI や Bicep で作った Foundry リソースには、Foundry User ロールが自動では付きません（L0-3 の手順8と同じ理由）。
```powershell
az role assignment create `
  --role "Foundry User" `
  --assignee (az ad signed-in-user show --query id -o tsv) `
  --scope (az cognitiveservices account show --name $ACCOUNT --resource-group $RG --query id -o tsv) `
  --query "{principalType:principalType, created:createdOn}" -o table
```
反映まで数分かかることがあります（手順13で 403 が出たら、少し待ってから再実行）。

### 12. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
./.venv/Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 13. `.env` を用意してスモークテストを流す
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順10の `projectEndpoint` を貼って保存します（`DEPLOYMENT_NAME=chat` は最初から入っています）。保存したら実行します。
```powershell
python main.py
```
`✅ デプロイは正常に推論できています。` と出れば、作ったデプロイが実際に呼べる状態です。

### 14. 後片付け（練習用のリソースグループを消す）
このレッスンで作ったものは、練習用のリソースグループ `rg-ai103-l13` にまとまっています。**講座共通の `rg-ai103` ではない**ことを確かめてから削除します。
```powershell
$RG
az group delete --name $RG --yes --no-wait
```
削除した Foundry リソースは「論理的に削除された」状態で残り、スクリプトで消した場合は、**デプロイのクォータを最大48時間つかんだまま**になります。削除が終わったら（数分）、完全に消して（purge）クォータを空けます。
```powershell
az cognitiveservices account list-deleted --query "[?name=='$ACCOUNT'].{name:name, location:location}" -o table
az cognitiveservices account purge --name $ACCOUNT --resource-group $RG --location $LOCATION
```
- 1行目で、削除済みの一覧に自分の練習用リソースがあることを確かめます（まだ出ないときは、少し待ってから再実行）。
- purge には、**サブスクリプション単位**の Contributor（または Cognitive Services Contributor）が必要です。権限が無い場合は purge せず、48時間たてば自動で空きます。
- purge したリソースは元に戻せません。

## CI/CD 雛形（任意・次のレクチャー）

- `github-workflow-sample/evaluate-and-deploy.yml` をリポジトリ直下 `.github/workflows/` にコピーし、OIDC（キーレス）と各リポジトリ変数を設定すると、PR で評価ゲート・main で評価→デプロイが動きます。
- 動かすには、ほかに次の3つが要ります：①評価対象の **Foundry エージェント**（`AGENT_IDS` に `名前:バージョン` で指定）②フェデレーション資格情報を付けた ID への**ロール割り当て**（評価とデプロイに必要な権限）③デプロイ先の**練習用リソースグループ**（講座共通の `rg-ai103` は指定しない）。
- `ai-agent-evals` は採点結果を Summary に出すだけで、**点数が低くてもジョブは失敗しません**。点数で deploy を止めたいときは、基準に届かなければ `exit 1` するステップを evaluate ジョブに足します。

## 注意（揮発情報）
- **モデル名/バージョン・SKU・API バージョン**は変動します。`list-models` と公式ドキュメントで都度確認。
- `microsoft/ai-agent-evals` と `azd` の hosted agent CI/CD は**プレビュー**。
