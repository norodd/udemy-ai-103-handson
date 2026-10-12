# L1-5 実践: キーレス化（DefaultAzureCredential ＋ ロール割り当て）

**APIキーを使わず**、Microsoft Entra ID（`az login`／マネージドID）のトークンで Foundry を呼び、
**ロール割り当て**と **local auth 無効化（`disableLocalAuth`）** までやってキーレスを仕上げるハンズオンです。

> 対応レクチャー：座学 `L1-5-1`(キーレス・マネージドID)／`L1-5-2`(RBAC・Key Vault)／`L1-5-3`(ネットワーク分離)、実践 `L1-5-4` ／ 対応スキル：S1.c-4
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。キー方式は「無効化されることを確認する」ためだけに登場します。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | **Foundry プロジェクト**を `AIProjectClient` + `DefaultAzureCredential` でキーレス呼び出し（Responses API） |
| `keyless_openai_direct.py` | **OpenAI SDK + トークンプロバイダー**でモデル直接呼び出し。キー方式との対比 |
| `assign_role_disable_key.azcli` | README 手順6〜8・14〜16（ロール・トークンの宛先・local auth 無効化）とキー再生成をまとめたもの（参考） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |

## 前提
- L0-3（Hello, Foundry）を終えていること（`az login` 済み・Python 3.11+・Azure CLI 2.80.0 以上）
- このレッスンは **キー認証を止める（`disableLocalAuth`）** ので、講座共通のリソース（`rg-udemy-ai-103-training`）では行いません。**練習用のリソースグループ `rg-udemy-ai-103-training-l15` に Foundry リソースを作って試し、最後に丸ごと消します**。共通のリソースには一切触れません。
- ロール割り当てには、サブスクリプションかリソースグループで **Owner** または **User Access Administrator** が必要です。

## 進め方（コピペで実行できます）

全部で17手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 練習用の名前を変数に決める |
| 2 | 練習用のリソースグループを作る |
| 3 | Foundry リソースを作る |
| 4 | プロジェクトを作る |
| 5 | モデルをデプロイする |
| 6 | いま自分に効いているロールを確かめる |
| 7 | プロジェクトに Foundry User を割り当てる |
| 8 | リソースに Cognitive Services User を割り当てる |
| 9 | 仮想環境を作って依存を入れる |
| 10 | 接続先を2つ取得する |
| 11 | `.env` を用意する |
| 12 | プロジェクト経由でキーレス呼び出し（`main.py`） |
| 13 | リソース直接でキーレス呼び出し（`keyless_openai_direct.py`） |
| 14 | トークンの宛先（スコープ）違いを確かめる |
| 15 | キー方式でも呼べることを確かめる（比較用） |
| 16 | キー認証を無効にして、キー方式が拒否されることを確かめる |
| 17 | 後片付け（練習用のリソースグループを消して purge） |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 01_plan_manage/L1-5_keyless_security
> ```

### 1. 練習用の名前を変数に決める
```powershell
$RG = "rg-udemy-ai-103-training-l15"
$LOCATION = "japaneast"
$ACCOUNT = "ai103-l15-$(Get-Random -Minimum 10000 -Maximum 99999)"
$PROJECT = "ai103-l15-proj"
$ACCOUNT
```
Foundry リソースの名前はサブドメインになるので**世界で一意**にする必要があり、末尾に乱数を付けます。

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
  --query "{name:name, kind:kind, state:properties.provisioningState}" -o table
```
`--custom-domain`（カスタムサブドメイン）は、Entra ID のトークン認証の前提条件です。

### 4. プロジェクトを作る
```powershell
az cognitiveservices account project create `
  --name $ACCOUNT `
  --resource-group $RG `
  --project-name $PROJECT `
  --location $LOCATION `
  --query "{name:name, state:properties.provisioningState}" -o table
```

### 5. モデルをデプロイする
```powershell
az cognitiveservices account deployment create `
  --name $ACCOUNT `
  --resource-group $RG `
  --deployment-name gpt-5.4 `
  --model-name gpt-5.4 `
  --model-version "2026-03-05" `
  --model-format OpenAI `
  --sku-name GlobalStandard `
  --sku-capacity 10 `
  --query "{name:name, state:properties.provisioningState}" -o table
```
`insufficient quota` で失敗したら、`gpt-5-mini`（バージョン `2025-08-07`）に読み替え、手順11で `.env` の `MODEL_DEPLOYMENT` も合わせます。

### 6. いま自分に効いているロールを確かめる
```powershell
$MY_ID = az ad signed-in-user show --query id -o tsv
$ACCOUNT_ID = az cognitiveservices account show --name $ACCOUNT --resource-group $RG --query id -o tsv
$PROJECT_ID = "$ACCOUNT_ID/projects/$PROJECT"
az role assignment list --assignee $MY_ID --scope $ACCOUNT_ID --include-inherited `
  --query "[].{role:roleDefinitionName, scope:scope}" -o table
```
- `--include-inherited` で、**上位（サブスクリプション／リソースグループ）から継承されている割り当て**も並びます。
- **Owner / Contributor では推論できません。** これらはコントロールプレーンのロールで、データアクションを持ちません。
- ⚠️ 表示される `scope` にはサブスクリプション ID が入ります。画面を共有するときは注意してください。

### 7. プロジェクトに Foundry User を割り当てる（`main.py` 用）
```powershell
az role assignment create `
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" `
  --assignee-object-id $MY_ID --assignee-principal-type User `
  --scope $PROJECT_ID `
  --query "{role:roleDefinitionName, principalType:principalType}" -o table
```
Foundry 系のロールは改称のロールアウト中なので、**名前ではなく GUID** で指定します（`53ca6127-...` が Foundry User、旧 Azure AI User）。

### 8. リソースに Cognitive Services User を割り当てる（`keyless_openai_direct.py` 用）
```powershell
az role assignment create `
  --role "Cognitive Services User" `
  --assignee-object-id $MY_ID --assignee-principal-type User `
  --scope $ACCOUNT_ID `
  --query "{role:roleDefinitionName, principalType:principalType}" -o table
az role assignment list --assignee $MY_ID --scope $PROJECT_ID --include-inherited `
  --query "[].{role:roleDefinitionName, scope:scope}" -o table
```
- 作成直後の応答には `role` 列が入らないので、最後のコマンドで一覧を出して確かめます（プロジェクトに効いているロールが、継承元も含めて並びます）。
- `Cognitive Services OpenAI User` は **OpenAI モデルだけ**に効きます。アカウントスコープの `Foundry User` でも同じデータアクションが入ります。
- ⚠️ **反映は即時ではありません。** 公式ガイダンスは「最初の呼び出しまで **5分以上待つ**」です。

### 9. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
./.venv/bin/Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 10. 接続先を2つ取得する
```powershell
az cognitiveservices account project show `
  --name $ACCOUNT --resource-group $RG --project-name $PROJECT `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
"https://$ACCOUNT.openai.azure.com/openai/v1/"
```
1つ目が**プロジェクト**のエンドポイント（`main.py` 用）、2つ目が**リソース直接**の OpenAI 互換エンドポイント（`keyless_openai_direct.py` 用）です。

### 11. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
`PROJECT_ENDPOINT=` に手順10の1つ目、`FOUNDRY_OPENAI_BASE_URL=` に2つ目を貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` は最初から入っています。`FOUNDRY_API_KEY=` は**空のまま**にします（キーはファイルに書きません）。

### 12. プロジェクト経由でキーレス呼び出し（`main.py`）
```powershell
python main.py
```
`✅ キーレスで接続` とモデルの応答が出ればOKです。403 が出たら、手順7のロールの反映を数分待って再実行します。

### 13. リソース直接でキーレス呼び出し（`keyless_openai_direct.py`）
```powershell
python keyless_openai_direct.py
```
方式A（キーレス）の応答が出て、方式B（キー）は `FOUNDRY_API_KEY` が未設定なのでスキップされます。

### 14. トークンの宛先（スコープ）違いを確かめる
```powershell
$ARM_TOKEN = az account get-access-token --scope "https://management.azure.com/.default" --query accessToken -o tsv
$AI_TOKEN  = az account get-access-token --scope "https://ai.azure.com/.default" --query accessToken -o tsv
(Invoke-WebRequest -SkipHttpErrorCheck -Uri "https://$ACCOUNT.openai.azure.com/openai/v1/models" -Headers @{ Authorization = "Bearer $ARM_TOKEN" }).StatusCode
(Invoke-WebRequest -SkipHttpErrorCheck -Uri "https://$ACCOUNT.openai.azure.com/openai/v1/models" -Headers @{ Authorization = "Bearer $AI_TOKEN" }).StatusCode
```
同じ ID で取ったトークンでも、**宛先（audience）が違えば 401**、Foundry 用（`https://ai.azure.com/.default`）なら **200** です。

### 15. キー方式でも呼べることを確かめる（比較用）
```powershell
$env:FOUNDRY_API_KEY = az cognitiveservices account keys list --name $ACCOUNT --resource-group $RG --query key1 -o tsv
python keyless_openai_direct.py
```
キーは**画面に出さず**環境変数に入れます（`.env` の空の行より環境変数が優先されます）。いまはキー認証が有効なので、方式A・方式Bとも応答が返ります。

### 16. キー認証を無効にして、キー方式が拒否されることを確かめる
```powershell
az resource update --ids $ACCOUNT_ID --set properties.disableLocalAuth=true --query "properties.disableLocalAuth" -o tsv
python keyless_openai_direct.py
```
- `true` が返ったあと、方式Aは成功し、方式Bは **403 `AuthenticationTypeDisabled`** になります（環境によっては **401**「Access denied due to invalid subscription key or wrong API endpoint」になることもあります。どちらもキー方式が拒否されたという意味です）。
- 反映は「通常数分、最大で数時間」です。まだ方式Bが通るときは、少し待って `python keyless_openai_direct.py` を再実行します。
- 組織全体に強制したいときは、Azure Policy「Azure AI Services resources should have key access disabled」を使います。

### 17. 後片付け（練習用のリソースグループを消して purge）
講座共通の `rg-udemy-ai-103-training` ではないことを確かめてから削除します。
```powershell
$env:FOUNDRY_API_KEY = $null
$RG
az group delete --name $RG --yes --no-wait
```
削除が終わったら（数分）、purge してクォータを空けます（スクリプトで消したリソースは、デプロイのクォータを最大48時間つかんだままになるため）。
```powershell
az cognitiveservices account list-deleted --query "[?name=='$ACCOUNT'].{name:name, location:location}" -o table
az cognitiveservices account purge --name $ACCOUNT --resource-group $RG --location $LOCATION
```
- purge には、**サブスクリプション単位**の Contributor（または Cognitive Services Contributor）が必要です。権限が無い場合は purge せず、48時間たてば自動で空きます。
- 手順7・8で付けたロールは、リソースと一緒に消えます。

## 必要なロール（ここが試験の論点）
| 呼び方 | 必要なロール | スコープ |
|---|---|---|
| `main.py`（プロジェクト経由） | **Foundry User**（旧 Azure AI User、GUID `53ca6127-db72-4b80-b1b0-d745d6d5456d`） | プロジェクト／アカウント（上位からの継承も可） |
| `keyless_openai_direct.py`（リソース直接） | **Cognitive Services User**（アカウントスコープの **Foundry User** でも可） | Foundry アカウント |

- ⚠️ **`Owner` / `Contributor` では推論できません。**
- ⚠️ **ロールは上位スコープから継承されます。** サブスクリプションやリソースグループに `Foundry User` が付いていれば、リソース／プロジェクトに何も付けなくても呼べます。「なぜ動くのか」も手順6で確認してください。

## つまずき
- **`403 Forbidden` / `401 PermissionDenied`**：ロール不足。上の表のロールを割り当て、**5分以上待って**再実行。`Owner` だけでは（Entra ID のトークンでは）通りません。Owner はキーを取り出せるのでキー方式なら通りますが、それはロールと無関係に入れてしまうというキーの性質です。
- **`401 Unauthorized`（`audience is incorrect`）**：トークンの**宛先違い**。スコープは `https://ai.azure.com/.default`。`az login` していない場合もここ。
- **`disableLocalAuth` 後にキー方式が 403**：期待どおりの動作です（`AuthenticationTypeDisabled`）。
- **カスタムサブドメインが無い**：トークン認証を受け付けず **401 Unauthorized** になる。カスタムサブドメインはトークン認証の前提条件で、あとから変更できません（手順3の `--custom-domain`）。
- **`model not found`**：`MODEL_DEPLOYMENT` は**カタログ名ではなくデプロイ名**。
- **キーを漏らしてしまった**：`az cognitiveservices account keys regenerate --key-name Key1`（Key2 も）で失効させます。⚠️ `disableLocalAuth=true` の**あと**だと再生成は失敗するので、順序は「再生成が先、無効化があと」です（`assign_role_disable_key.azcli` の 6）。
