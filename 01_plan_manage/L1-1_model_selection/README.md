# L1-1 実践: 2モデル（大／小）を同一タスクで比較する

同じプロンプトを **「大きいモデル」と「小さいモデル」** に投げ、**出力・レイテンシ・トークン数（≒コスト）** を並べて比較する CLI です。座学で学ぶ「精度／レイテンシ／コストはトレードオフ」を自分の目で確かめるのが狙いです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 2モデルに同一プロンプトを投げ、レイテンシ／入出力トークン／本文を並べて表示 |
| `.env.sample` | 環境変数の雛形（エンドポイントと比較する2モデル名） |
| `requirements.txt` | Python 依存パッケージ |

## 前提
- L0-3（Hello, Foundry）を終えていること。L0-3 で作った**講座共通のリソース**（リソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・`gpt-5.4-nano` のデプロイ・自分への **Foundry User** ロール）をそのまま使います。
- `az login` 済み ／ Python 3.11+

## 進め方（コピペで実行できます）

全部で7手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。

| 手順 | やること |
|---|---|
| 1 | 共通の Foundry リソースの名前を確かめる |
| 2 | 比較用の大きいモデル（`gpt-5.4`）をデプロイする |
| 3 | 2つのデプロイがそろったか確かめる |
| 4 | プロジェクトのエンドポイントを取得する |
| 5 | 仮想環境を作って依存を入れる |
| 6 | `.env` を用意する |
| 7 | 実行する |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 01_plan_manage/L1-1_model_selection
> ```

### 1. 共通の Foundry リソースの名前を確かめる
L0-3 で作った Foundry リソースの名前（末尾に乱数が付いています）を、変数 `$FOUNDRY` に入れて表示します。
```powershell
$FOUNDRY = az cognitiveservices account list --resource-group rg-udemy-ai-103-training --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。手順2〜4はこの変数を使うので、**同じターミナルで続けて**実行してください。

### 2. 比較用の大きいモデル（`gpt-5.4`）をデプロイする
小さいモデル `gpt-5.4-nano` は L0-3 でデプロイ済みです。比較相手の大きいモデルを追加します。
```powershell
az cognitiveservices account deployment create `
  --name $FOUNDRY `
  --resource-group rg-udemy-ai-103-training `
  --deployment-name gpt-5.4 `
  --model-name gpt-5.4 `
  --model-version "2026-03-05" `
  --model-format OpenAI `
  --sku-capacity 10 `
  --sku-name GlobalStandard `
  --query "{name:name, state:properties.provisioningState}" -o table
```
- `State` が `Succeeded` になればOKです。デプロイを置いておくだけでは課金されません（呼び出した分だけ）。
- `insufficient quota` で失敗したら、下の「クォータ不足でモデルをデプロイできないとき」を見てください（`gpt-5-mini` と `gpt-4.1-mini` の組み合わせに読み替えます）。
- `--model-version` は更新されます。通らないときは `az cognitiveservices model list --location japaneast --query "[?model.name=='gpt-5.4'].model.version" -o tsv` で現行の値を確認してください。

### 3. 2つのデプロイがそろったか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group rg-udemy-ai-103-training `
  --query "[].{name:name, model:properties.model.name, sku:sku.name}" -o table
```
`gpt-5.4` と `gpt-5.4-nano` の2行が出れば準備完了です。ここに出る `name`（デプロイ名）を、手順6で `.env` に書きます。

### 4. プロジェクトのエンドポイントを取得する
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group rg-udemy-ai-103-training `
  --project-name ai103-project `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
```
返ってきた URL（末尾が `/api/projects/ai103-project`）を、手順6で `.env` に貼ります。L0-3 の `.env` と同じ値です。

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
開いた `.env` の `PROJECT_ENDPOINT=` に手順4のエンドポイントを貼って保存します。
- 比較する2つのデプロイ名は `MODEL_LARGE=gpt-5.4` と `MODEL_SMALL=gpt-5.4-nano` として、最初から入っています。
- ⚠️ **L0-3 の `.env` とはキー名が違います**（L0-3 は `MODEL_DEPLOYMENT` の1つ、こちらは `MODEL_LARGE` と `MODEL_SMALL` の2つ）。L0-3 の `.env` をそのままコピーすると、2つとも既定値のままになるので注意してください。

### 7. 実行する
```powershell
python main.py
```

## 期待される出力（例）
```
===== 大 (LARGE): gpt-5.4 =====
レイテンシ: 1.83s / 入力トークン: 31 / 出力トークン: 96
出力:
Microsoft Foundry は… （3文の説明）

===== 小 (SMALL): gpt-5.4-nano =====
レイテンシ: 0.92s / 入力トークン: 31 / 出力トークン: 88
出力:
Microsoft Foundry は… （3文の説明）
```
数値はリージョン・混雑で変動します。**傾向**（小さいモデルの方が速く・安い）が見えればOKです。

## クォータ不足でモデルをデプロイできないとき

Foundry ポータルでデプロイしようとして **`gpt-5.4 isn't available due to insufficient quota`** と出る場合、設定ミスではありません。**そのサブスクリプションに、そのモデルの割り当てが1つも無い**状態です。

Foundry はサブスクリプションごとに **クォータティア**（最下位＝Free Tier / Tier 0 〜 Tier 6）を割り当てており、**ティアの表に載っているモデルにしか既定クォータが付きません**。初期ティアは利用実績と Microsoft との契約関係で決まるため、**作りたてのサブスクリプションは最下位ティアになりやすい**です。

現在のティアの確認（ポータルには表示がないため API で確認します）：

```powershell
az rest --method get `
  --url "https://management.azure.com/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.CognitiveServices/quotaTiers?api-version=2026-05-01"
```
> ⚠️ `api-version` は更新が速く、通る値が入れ替わります（2026-09-23実測：`2026-05-01` は通り、`2023-05-01` や `2026-09-01` は404）。404 のエラーメッセージに「サポートされる api-version の一覧」が出るので、その中の値に差し替えてください。

**最下位ティアで既定クォータが付与されるのは次の4モデルだけ**です（すべて GlobalStandard）。

| モデル | 既定クォータ |
|---|---|
| `gpt-4.1-mini` | 200,000 TPM |
| `gpt-5-mini` | 500,000 TPM |
| `o4-mini` | 100,000 TPM |
| `text-embedding-3-small` | 1,000,000 TPM |

### 対処1：使えるモデルに差し替える（推奨）
手順2の代わりに、最下位ティアでも既定クォータが付く2つのモデルをデプロイします（手順1の `$FOUNDRY` を使うので同じターミナルで実行）。
```powershell
az cognitiveservices account deployment create `
  --name $FOUNDRY --resource-group rg-udemy-ai-103-training `
  --deployment-name gpt-5-mini --model-name gpt-5-mini --model-version "2025-08-07" `
  --model-format OpenAI --sku-capacity 10 --sku-name GlobalStandard `
  --query "{name:name, state:properties.provisioningState}" -o table
az cognitiveservices account deployment create `
  --name $FOUNDRY --resource-group rg-udemy-ai-103-training `
  --deployment-name gpt-4.1-mini --model-name gpt-4.1-mini --model-version "2025-04-14" `
  --model-format OpenAI --sku-capacity 10 --sku-name GlobalStandard `
  --query "{name:name, state:properties.provisioningState}" -o table
```
バージョンは更新されます。通らないときは `az cognitiveservices model list --location japaneast --query "[?model.name=='gpt-5-mini' || model.name=='gpt-4.1-mini'].{name:model.name,version:model.version}" -o table` で確認してください（2026-09-23 時点：gpt-5-mini は 2025-08-07、gpt-4.1-mini は 2025-04-14）。

そのうえで、手順6の `.env` を次のように変更すれば、このハンズオンは**そのまま実施できます**。

```
MODEL_LARGE=gpt-5-mini      # 推論モデル。思考トークンを出すので遅く・消費が多い＝「大きい側」
MODEL_SMALL=gpt-4.1-mini    # 非推論モデル。速く・安い＝「小さい側」
```

推論モデル（思考のトークンも出力に数える）対非推論モデルになるため、**レイテンシとトークン数の差はむしろはっきり出ます**。既定の `gpt-5.4` と `gpt-5.4-nano` はどちらも推論モデルです。
※ `gpt-4.1-mini` はライフサイクルが Legacy（廃止予定 2027-04-14。2026-09-19 確認）です。実行時点の廃止スケジュールを確認してください。

### 対処2：クォータ増加を申請する
[クォータ増加申請フォーム](https://aka.ms/oai/stuquotarequest) から、**サブスクリプション・リージョン・モデル名・希望 TPM** を明記して申請します（サブスクリプションの **Owner** または **Contributor** が必要）。承認されてもティアは変わらず、割り当てだけ増えます。反映まで最大15分。
> 申請は「**既存クォータを実際に使っている顧客が優先**」されます。まず対処1で実際に推論を回してから申請すると通りやすくなります。

### 対処3：待つ（自動昇格）
ティアは**消費実績と支払い履歴に応じて自動的に昇格**します。講座を進めるうちに上位モデルも使えるようになります。

### 効かない／注意が必要な回避策
| やろうとしがちなこと | 実際 |
|---|---|
| 別のリージョンでデプロイする | **効きません。** Global Standard のクォータは 2026年5月以降、サブスクリプション単位で**全リージョン共通の1プール**。ポータルの Quota 画面の **Scope 列**が `Global` / `Data Zone` ならこの新方式（リージョン名なら従来のリージョン別方式で、変更が効く可能性あり） |
| TPM（容量）を最小にして再試行 | 割り当てがゼロなら不可 |
| Data Zone Standard / Standard に切り替える | 別プールだが、最下位ティアには対象モデルの行が無いため不可 |
| Instant access（プレビュー）を使う | デプロイ不要だが**同じ per-model global quota を消費**し、**West US 3 のプロジェクト限定**。`gpt-5-mini` などは試せるが、割り当てゼロのモデルは同じく不可 |

## つまずきポイント
| 症状 | 対処 |
|---|---|
| `isn't available due to insufficient quota` | 上記「クォータ不足でモデルをデプロイできないとき」を参照 |
| `Quota exceeded`（割り当てはあるが空きなし） | Manage → Quota で他デプロイの TPM を減らして空きを作る（反映まで最大15分） |
| `DefaultAzureCredential` で認証エラー／403 | `az login` 済みか、L0-3 の手順8で **Foundry User** を付けたか確認 |
| `model not found` / 404 | `.env` のモデル名が**デプロイ名**と一致しているか（カタログ名ではなくデプロイ名） |
| `usage` が `None` | SDK／モデルにより戻り値の形が異なる。`getattr` で防御済み |
| 429（レート制限） | TPM/RPM 超過。少し待つ。詳細は L1-4 |
| エンドポイント形式エラー | `PROJECT_ENDPOINT` が `.../api/projects/<project>` 形式か確認 |

## 後片付け
- このハンズオンは**推論を数回**するだけです。デプロイを置いておくだけでは課金されません（従量課金の GlobalStandard）。
- リソースグループ `rg-udemy-ai-103-training` は**講座の最後まで共通で使うので、消さないでください**。
- `gpt-5.4` のデプロイだけを片付けたい場合は、次を実行します（以降のレッスンで必要になったら、また手順2で作り直せます）。
  ```powershell
  az cognitiveservices account deployment delete --name $FOUNDRY --resource-group rg-udemy-ai-103-training --deployment-name gpt-5.4
  ```

## 注意（揮発情報）
- **モデルID・世代は更新が速い**。デプロイ前に Foundry のカタログで現行IDを確認してください。
- **ティア別 TPM 表はモデル追加のたびに変わります**（新しいモデルは上位ティアのみ、というケースあり）。→ https://learn.microsoft.com/azure/foundry/openai/quotas-limits#quota-tiers
- `quotaTiers` API のバージョンは更新が速い（2026-09-23時点で通るのは `2026-05-01`。404 のエラーメッセージにサポートされる一覧が出る）。
