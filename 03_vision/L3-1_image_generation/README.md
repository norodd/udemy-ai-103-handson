# L3-1 実践: 画像の生成とインペイント（inpainting）

テキストから画像を1枚生成し、中央だけを透明にしたマスクを作って、その部分だけを別の内容に描き直す（inpainting）ハンズオンです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。
> 画像生成モデルは講座共通のリージョン（japaneast）では使えないため、**このレッスン専用のリソースグループを対応リージョン（eastus2）に作ります**。次の動画生成のレッスン（L3-2）は別のリソースグループ（swedencentral）を作りますが、その手順14でこのリソースグループもまとめて片付けるので、後片付けは L3-2 のあとで行います。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 画像生成（`images.generate`）→ マスク作成（Pillow）→ 編集（`images.edit`）の3段 |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（`az login` 済み・Foundry User ロールの考え方）。
- Python 3.11+
- リソースグループとロールの割り当てを作れる権限（サブスクリプションの Owner など）。
- ⚠️ 最下位のクォータティア（Free Tier / Tier 0）には画像生成モデルの割り当てがありません。手順4で `InsufficientQuota` などになったら、[クォータ増加申請](https://aka.ms/oai/stuquotarequest)が必要です（承認までは動画で流れを確認してください）。

## 進め方（コピペで実行できます）

全部で12手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | このレッスン用の名前を変数に決める |
| 2 | リソースグループを作る（eastus2） |
| 3 | Foundry リソースを作る |
| 4 | 画像生成モデルをデプロイする |
| 5 | 自分に Foundry User を割り当てる |
| 6 | 接続先（リソースの `/openai/v1/`）を取得する |
| 7 | 仮想環境を作って依存を入れる |
| 8 | `.env` を用意する |
| 9 | 生成 → マスク → 編集を実行する |
| 10 | 3枚の画像を見比べる |
| 11 | マスクの中身を数値で確かめる |
| 12 | 後片付け（L3-2 のあとで） |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 03_vision/L3-1_image_generation
> ```

### 1. このレッスン用の名前を変数に決める
```powershell
$RG = "rg-udemy-ai-103-training-gen"
$LOCATION = "eastus2"
$ACCOUNT = "ai103-gen-$(Get-Random -Minimum 10000 -Maximum 99999)"
$DEPLOY = "gpt-image-2"
$ACCOUNT
```
- 画像生成モデル（`gpt-image-2`）を Global Standard で使えるのは eastus2・swedencentral などで、**japaneast では使えません**（`az cognitiveservices model list --location <リージョン>` で確かめられます）。
- Foundry リソースの名前はサブドメインになるので**世界で一意**にする必要があり、末尾に乱数を付けます。

### 2. リソースグループを作る（eastus2）
```powershell
az group create --name $RG --location $LOCATION `
  --query "{name:name, location:location, state:properties.provisioningState}" -o table
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
  --query "{name:name, kind:kind, state:properties.provisioningState}" -o table
```
`--custom-domain`（カスタムサブドメイン）は、キーレス（Entra ID のトークン）で呼ぶための前提です。あとから変更できません。

### 4. 画像生成モデルをデプロイする
```powershell
az cognitiveservices account deployment create `
  --name $ACCOUNT --resource-group $RG `
  --deployment-name $DEPLOY `
  --model-name gpt-image-2 --model-version 2026-04-21 --model-format OpenAI `
  --sku-name GlobalStandard --sku-capacity 3 `
  --query "{name:name, model:properties.model.name, sku:sku.name, state:properties.provisioningState}" -o table
```
`Succeeded` になれば完了です。`gpt-image-2` は一般提供（GA）で、利用申請は要りません。Global Standard のデプロイは、置いてあるだけでは課金されません（使った分だけの従量課金です。課金はトークン単位で数えられ、画像のサイズや品質によって1枚あたりの額が変わります）。

### 5. 自分に Foundry User を割り当てる
```powershell
$MY_ID = az ad signed-in-user show --query id -o tsv
$ACCOUNT_ID = az cognitiveservices account show --name $ACCOUNT --resource-group $RG --query id -o tsv
az role assignment create `
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" `
  --assignee-object-id $MY_ID --assignee-principal-type User `
  --scope $ACCOUNT_ID -o none
az role assignment list --assignee $MY_ID --scope $ACCOUNT_ID --include-inherited `
  --query "[].roleDefinitionName" -o tsv
```
- CLI で作ったリソースには、作った人にも推論のロールは自動では付きません。**Foundry User**（旧 Azure AI User。改称の途中なので GUID で指定）を付けます。
- 一覧に `Foundry User` が出れば OK です（上位のスコープから継承したロールも並びます）。反映には数分、長いと10分ほどかかることがあります。

### 6. 接続先（リソースの `/openai/v1/`）を取得する
```powershell
"https://$ACCOUNT.openai.azure.com/openai/v1/"
```
表示された URL を手順8で `.env` に貼ります。⚠️ **プロジェクトのエンドポイント（`.../api/projects/<name>`）経由では、画像の生成・編集が 404 になります**（講座の検証で確認）。このレッスンは、L1-5 の直接呼び出しと同じ形でリソースのエンドポイントを使います。

### 7. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 8. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `FOUNDRY_OPENAI_BASE_URL=` に手順6の URL を貼って保存します。`IMAGE_MODEL` は手順4のデプロイ名（`gpt-image-2`）のままで構いません。

### 9. 生成 → マスク → 編集を実行する
```powershell
python main.py
```
```text
デプロイ: gpt-image-2
保存しました: generated.png（1024x1024）
  生成にかかった時間: 60 秒
保存しました: mask.png（中央が編集対象）
保存しました: edited.png（1024x1024）
  編集にかかった時間: 50 秒

完了: generated.png / mask.png / edited.png を見比べてください。
```
- 生成と編集はそれぞれ1分前後かかることがあります（秒数は実行のたびに変わります）。
- 画像の中身も実行のたびに変わります。

### 10. 3枚の画像を見比べる
```powershell
code generated.png
code mask.png
code edited.png
```
- `generated.png`：プロンプトから生成した元の画像。
- `mask.png`：周りが白（不透明）、中央が透明（エディターでは市松模様）。**透明の部分**が「描き直してよい範囲」です。
- `edited.png`：中央の範囲だけが、編集プロンプトの内容（観葉植物の鉢）で描き直された画像。範囲の外は基本的に元の画像のまま残ります。

### 11. マスクの中身を数値で確かめる
```powershell
Get-ChildItem *.png | Select-Object Name, Length
python -c "from PIL import Image; m=Image.open('mask.png'); print(m.size, m.getpixel((512,512)), m.getpixel((10,10)))"
```
```text
(1024, 1024) (0, 0, 0, 0) (255, 255, 255, 255)
```
- マスクは元画像と**同じ寸法**である必要があります（1024x1024）。
- 中央の画素はアルファ（4つ目の値）が 0＝透明、端の画素は 255＝不透明です。
- `mask.png` はほぼ2色なので、ファイルサイズが生成画像より桁違いに小さくなります。

### 12. 後片付け（L3-2 のあとで）
**次の L3-2（動画生成）を続けて行う場合は、ここでは消しません。** L3-2 の手順14で、このリソースグループの削除と purge もまとめて行います。L3-2 をやらない場合は、ここで次のコマンドで消します。
```powershell
$RG
az group delete --name $RG --yes --no-wait
```
`$RG` が講座共通の `rg-udemy-ai-103-training` ではなく `rg-udemy-ai-103-training-gen` であることを確かめてから実行します。削除が終わったら（数分）、purge してクォータを空けます。
```powershell
az cognitiveservices account list-deleted --query "[?name=='$ACCOUNT'].{name:name, location:location}" -o table
az cognitiveservices account purge --name $ACCOUNT --resource-group $RG --location $LOCATION
```
削除しただけのリソースは、デプロイのクォータを最大48時間つかんだままになります。purge には、サブスクリプション単位の Contributor（または Cognitive Services Contributor）が必要です。

## 注意点（試験の論点）
- 画像の生成は `images.generate`、編集（inpainting）は `images.edit` に**画像・マスク・プロンプト**を渡します。GPT-image 系は画像を **base64（`b64_json`）** で返すので、デコードして保存します。
- マスクは「**透明（アルファ=0）の部分が編集してよい範囲**」というルールです。PNG で、元画像と同じ寸法にします。
- 編集プロンプトは、**マスクの範囲に何を描くか**を具体的に書きます。講座の検証では、短いプロンプト（例：`Place a plant`）だと中央が黒く塗りつぶされて返ることがありました（毎回ではありません）。
- 画像のプロンプトにはコンテンツフィルターがかかります。有害と判定されると画像は返りません。

## つまずき
- **`エラー: ... 404 ...`**：`FOUNDRY_OPENAI_BASE_URL` がプロジェクトのエンドポイントになっていないか確認してください。リソースの `/openai/v1/` 形式が必要です。デプロイ名（`IMAGE_MODEL`）の打ち間違いでも 404 になります。
- **`エラー: ... 401 ...` / `403 ...`**：手順5のロールの反映待ちか、`az login` の切れです。ロールの反映には最大10分ほどかかるので、少し待って再実行してください。
- **`エラー: ... content_filter ...`**：プロンプトがコンテンツフィルターに引っかかっています。穏当な内容に変えてください。
- **編集結果の中央が黒く塗りつぶされる**：編集プロンプトが短すぎる可能性があります。「マスクの範囲に何を描くか」を具体的に書いてください。
- **手順4で `InsufficientQuota`**：対象リージョンの画像生成モデルのクォータが足りません（最下位ティアには割り当てがありません）。クォータ増加申請が必要です。
- **手順3で `CustomDomainInUse`**：名前が他と重なりました。手順1の `$ACCOUNT` を作り直して、もう一度実行します。
