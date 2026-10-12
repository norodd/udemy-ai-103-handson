# L1-4 実践: クォータ確認 ＋ レート制限リトライ ＋ コストタグ

デプロイの **クォータ消費をプログラムで確認**し、**レート制限(429)に強いリトライ**を実装し、**コスト按分のタグ**を付けるハンズオンです。

> 対応レクチャー：座学 `L1-4-1`(クォータ)／`L1-4-2`(レート制限・スケーリング)／`L1-4-3`(コスト管理)、実践 `L1-4-4` ／ 対応スキル：S1.c-1
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `check_quota.py` | **ARM REST**（quotaTiers / Usages / Model Capacities API）でティア・クォータ消費・空き容量を確認 |
| `retry_demo.py` | **429 リトライ**：SDK 組み込み（`max_retries`）と手動の指数バックオフ＋ジッター |
| `tag_resources.azcli` | README 手順8〜10（コスト按分タグ）と予算アラートの例をまとめたもの（参考） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- L1-1 でデプロイした `gpt-5.4` を使います（無い場合は、L1-1 の README 手順2でデプロイするか、`gpt-5.4-nano` に読み替え）。
- ロール：クォータの閲覧は、サブスクリプションで **Reader 以上**（最小権限なら **Cognitive Services Usages Reader**）。タグ付与は対象リソースに **Contributor** 以上。
- **新しいリソースは作りません**。講座共通のリソースにタグを足すだけです。

## 進め方（コピペで実行できます）

全部で10手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前とサブスクリプションを変数に入れる |
| 2 | 使うデプロイを確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | クォータを確認する（`check_quota.py`） |
| 7 | リトライ付きで推論する（`retry_demo.py`） |
| 8 | リソースグループにタグを付ける |
| 9 | Foundry リソースのタグを確かめる（継承されない） |
| 10 | Foundry リソースにタグを付ける |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 01_plan_manage/L1-4_quota_cost
> ```

### 1. 共通リソースの名前とサブスクリプションを変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$env:AZURE_SUBSCRIPTION_ID = az account show --query id -o tsv
$FOUNDRY
```
- `ai103-foundry-<数字>` が表示されればOKです。
- サブスクリプション ID は**画面に出さずに**環境変数へ入れます。`check_quota.py` はここから読みます（`.env` に書く必要はありません）。

### 2. 使うデプロイを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name, sku:sku.name, capacity:sku.capacity}" -o table
```
`gpt-5.4` の行があればOKです。`capacity` はこのデプロイに割り当てたクォータ（単位は千 TPM）で、手順6の消費量と対応します。

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
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 5. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` と `QUOTA_LOCATION=japaneast`（共通リソースのリージョン）は最初から入っています。
> ⚠️ このレッスンのキー名は `MODEL_DEPLOYMENT` です（L1-1 は `MODEL_LARGE`／`MODEL_SMALL`、L1-3 は `DEPLOYMENT_NAME`）。前のレッスンの `.env` を丸ごと写さず、値だけを移してください。

### 6. クォータを確認する（`check_quota.py`）
```powershell
python check_quota.py
```
ティア（サブスクリプションの等級）→ `japaneast` のクォータ消費／上限 → `gpt-5.4` を置ける空き容量（リージョン別）の順に表示されます。

### 7. リトライ付きで推論する（`retry_demo.py`）
```powershell
python retry_demo.py
```
方式A（SDK 組み込みリトライ）と方式B（手動の指数バックオフ）で、同じ質問に2回答えます。通常は 429 は出ません（出たら自動で待って再試行します）。

### 8. リソースグループにタグを付ける
```powershell
az tag update `
  --resource-id (az group show --name $RG --query id -o tsv) `
  --operation merge `
  --tags project=ai103-course env=dev costcenter=training `
  --query "properties.tags" -o json
```
`--operation merge` は**既存のタグを残したまま足す**指定です（`az tag create` は全置換で、既存タグが消えます）。

### 9. Foundry リソースのタグを確かめる（継承されない）
```powershell
az cognitiveservices account show --name $FOUNDRY --resource-group $RG --query tags -o json
```
手順8で付けた `project` などは**出てきません**。リソースは、リソースグループのタグを**継承しません**。

### 10. Foundry リソースにタグを付ける
```powershell
az tag update `
  --resource-id (az cognitiveservices account show --name $FOUNDRY --resource-group $RG --query id -o tsv) `
  --operation merge `
  --tags project=ai103-course env=dev costcenter=training `
  --query "properties.tags" -o json
```
これで、Cost Management の「Cost analysis」でタグ `project` 別にコストを集計できます（反映は最大 24 時間。タグを付ける前の使用量には遡って付きません）。

## 期待される出力（例）
`check_quota.py`：
```
===== クォータティア (このサブスクリプションの等級) =====
現在のティア: Tier 3
...
===== クォータ消費 / 上限 (japaneast) =====
(モデル gpt-5.4 の行だけ表示。全件は USAGE_FILTER を空にする)
One Thousand Tokens Per Minute - gpt-5.4 - GlobalStandard: <使用>/<上限>
...
===== gpt-5.4 (2026-03-05) の Standard 系 空き容量 =====
japaneast (GlobalStandard): <上限-使用> 利用可能
(ほかに N 件のデプロイ先に空きあり。全件は CAPACITY_ALL=1)
```
- 使用量は、このサブスクリプションがこのリージョンで割り当てた**合計**です（他のリソースのデプロイ分も含みます）。
`retry_demo.py`：通常は 429 なしで成功（`max_retries` 設定により、429 が出れば自動でバックオフ再試行）。

## つまずきポイント
| 症状 | 対処 |
|---|---|
| `check_quota.py` で 403 | サブスクリプションに **Reader** 以上（または **Cognitive Services Usages Reader**）を付与 |
| `AZURE_SUBSCRIPTION_ID が未設定です` | 手順1を**同じターミナル**で実行したか確認（別ターミナルでは環境変数が消えます） |
| `limit > 0` の行が出ない | `QUOTA_LOCATION` が共通リソースのリージョン（`japaneast`）か確認 |
| 使いたいモデルの行がそもそも無い／`insufficient quota` でデプロイできない | **クォータティア**が原因。最下位ティア（Free Tier / Tier 0）では `gpt-4.1-mini` / `gpt-5-mini` / `o4-mini` / `text-embedding-3-small` 以外は割り当てゼロ。`.env.sample` のフォールバック（`gpt-5-mini`）に読み替える。**リージョン変更では解決しない** → 詳細はリポジトリ直下の [`FAQ.md`](../../FAQ.md) |
| `model not found` | `MODEL_DEPLOYMENT` が**デプロイ名**と一致しているか（カタログ名でなくデプロイ名） |
| 429 が再現しない | 正常。クォータ超過時に自動再試行される形であることを確認する目的 |
| ティアが取得できない | `quotaTiers` はプレビュー API。取得できなくても後続の確認は続行される |

## 後片付け
- このハンズオンは**推論を数回**するだけ（数円程度）。`check_quota` とタグは無料です。**新しいリソースは作っていません**。
- 付けたタグは、講座共通のリソースを表すものなので**そのまま残して構いません**。外すときは `--operation delete` を使います（例：`az tag update --resource-id <id> --operation delete --tags project=ai103-course env=dev costcenter=training`）。
- ⚠️ `rg-udemy-ai-103-training` は後続のレッスンでも使うので、**リソースグループごとの削除はしないでください**。

## 注意（揮発情報）
- **ARM の api-version**、**capacity unit の RPM/TPM 比**、**SDK 既定リトライ回数**は変動。公式ドキュメントで都度確認。
- **project レベルのコスト按分はプレビュー**。RBAC ロールは改称中（Azure AI User → Foundry User）。
