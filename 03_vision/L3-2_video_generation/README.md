# L3-2 実践: テキストから短い動画を非同期生成して取得する

テキストから短い動画を1本、**非同期のジョブ**として生成し、状態をポーリングで確かめてから `output.mp4` にダウンロードするハンズオンです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。
> 動画生成モデル（`sora-2`）は講座共通のリージョン（japaneast）では使えないため、**このレッスン専用のリソースグループを対応リージョン（swedencentral）に作ります**。最後にリソースグループごと削除します。

## ⚠️ 動画生成モデルの廃止予定
- `sora-2`（2025-12-08 版）は**プレビュー**で、Microsoft Learn のモデル退役スケジュールでは **2026-10-15 に退役**、後継モデルは記載なし（2026-09-24 確認）。退役後の呼び出しは `410 Gone` になります。
- 実行すると openai の Python パッケージが `The Sora API is scheduled to permanently shut down on September 24, 2026.` という警告を出します。これは OpenAI 社が自社で提供している Sora の API の終了予告で、**Azure の `sora-2` の退役日（2026-10-15）とは別**です。講座の検証では **2026-09-24 当日も Azure 上で生成できました**。
- 退役後にこのレッスンを実行できなくなった場合は、動画（実践レクチャー）で流れを確認してください。後継の動画生成モデルが出たら、手順2〜4のモデル名・バージョンを読み替えます（非同期ジョブの流れは同じ考え方です）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | ジョブ作成（`videos.create`）→ ポーリング（`videos.retrieve`）→ 取得（`videos.download_content`）。`list` と `delete` で保存済みの動画も扱う |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（`az login` 済み・Foundry User ロールの考え方）。
- Python 3.11+
- リソースグループとロールの割り当てを作れる権限（サブスクリプションの Owner など）。
- ⚠️ 最下位のクォータティア（Free Tier / Tier 0）には動画生成モデルの割り当てがありません。手順2で上限（limit）が 0 なら、[クォータ増加申請](https://aka.ms/oai/stuquotarequest)が必要です（承認までは動画で流れを確認してください）。

## 進め方（コピペで実行できます）

全部で14手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | このレッスン用の名前を変数に決める |
| 2 | リージョンで使えるか（モデルとクォータ）を確かめる |
| 3 | リソースグループを作る（swedencentral） |
| 4 | Foundry リソースを作る |
| 5 | 動画生成モデルをデプロイする |
| 6 | 自分に Foundry User を割り当てる |
| 7 | 接続先（リソースの `/openai/v1/`）を取得する |
| 8 | 仮想環境を作って依存を入れる |
| 9 | `.env` を用意する |
| 10 | 動画を生成する（ジョブ作成 → ポーリング → 取得） |
| 11 | 生成した動画を見る |
| 12 | 対応していない長さを渡して、エラーの中身を見る |
| 13 | サービスに保存された動画を一覧して削除する |
| 14 | 後片付け（このレッスンと L3-1 のリソースグループ） |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 03_vision/L3-2_video_generation
> ```

### 1. このレッスン用の名前を変数に決める
```powershell
$RG = "rg-udemy-ai-103-training-video"
$LOCATION = "swedencentral"
$ACCOUNT = "ai103-vid-$(Get-Random -Minimum 10000 -Maximum 99999)"
$DEPLOY = "sora-2"
$ACCOUNT
```
Foundry リソースの名前はサブドメインになるので**世界で一意**にする必要があり、重なりにくいよう末尾に乱数を付けます（重なったときは手順4が `CustomDomainInUse` になります）。

### 2. リージョンで使えるか（モデルとクォータ）を確かめる
```powershell
az cognitiveservices model list --location $LOCATION `
  --query "[?model.name=='sora-2'].{version:model.version, retire:model.deprecation.inference}" -o table
az cognitiveservices usage list --location $LOCATION `
  --query "[?contains(name.value,'sora-2')].{name:name.value, used:currentValue, limit:limit}" -o table
```
- 1つ目で、そのリージョンにモデルがあるか、各バージョンの退役日（`retire`）が分かります。退役日を過ぎた版（2025-10-06 版は 2026-07-15 に退役済み）は使えません。
- 2つ目で、サブスクリプションのクォータの使用量（`used`）と上限（`limit`）が分かります。**上限から使用量を引いた空き（limit − used）が、手順5で指定する容量（10）より少ないと、手順5が `InsufficientQuota` で失敗します**。講座の検証では eastus2 がこの状態だったので、空きのある swedencentral を使っています。空きが無いときは `$LOCATION` を別の対応リージョンに変えます。

### 3. リソースグループを作る（swedencentral）
```powershell
az group create --name $RG --location $LOCATION `
  --query "{name:name, location:location, state:properties.provisioningState}" -o table
```

### 4. Foundry リソースを作る
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

### 5. 動画生成モデルをデプロイする
```powershell
az cognitiveservices account deployment create `
  --name $ACCOUNT --resource-group $RG `
  --deployment-name $DEPLOY `
  --model-name sora-2 --model-version 2025-12-08 --model-format OpenAI `
  --sku-name GlobalStandard --sku-capacity 10 `
  --query "{name:name, model:properties.model.name, version:properties.model.version, state:properties.provisioningState}" -o table
```
`Succeeded` になれば完了です。Global Standard のデプロイは、置いてあるだけでは課金されません。課金は**生成した動画の秒数**に応じた従量課金です。

### 6. 自分に Foundry User を割り当てる
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

### 7. 接続先（リソースの `/openai/v1/`）を取得する
```powershell
"https://$ACCOUNT.openai.azure.com/openai/v1/"
```
表示された URL を手順9で `.env` に貼ります。L3-1（画像生成）と同じく、リソースの `/openai/v1/` を直接使います。

### 8. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 9. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `FOUNDRY_OPENAI_BASE_URL=` に手順7の URL を貼って保存します。`VIDEO_MODEL`（デプロイ名）・`VIDEO_SIZE`・`VIDEO_SECONDS` は雛形のままで構いません。

### 10. 動画を生成する（ジョブ作成 → ポーリング → 取得）
```powershell
python main.py
```
```text
デプロイ: sora-2 / サイズ: 1280x720 / 長さ: 4 秒
[SDK の警告] The Sora API is scheduled to permanently shut down on September 24, 2026.
ジョブを作成: video_xxxxxxxx  状態: queued
    8 秒  状態: in_progress  進み: 10%
   14 秒  状態: in_progress  進み: 45%
   28 秒  状態: in_progress  進み: 72%
   42 秒  状態: in_progress  進み: 99%
   55 秒  状態: completed  進み: 100%
保存しました: output.mp4（1,692,561 バイト）  かかった時間: 61 秒
```
- `videos.create` は**すぐに返ります**。返るのはジョブの ID と状態（`queued`）だけで、動画はまだできていません。
- 5秒おきに `videos.retrieve` で状態を確かめ、`completed` になったら `download_content` で取得します。状態は `queued` → `in_progress` → `completed`（失敗なら `failed`）です。
- 講座の検証では1分前後で完成しました（秒数・進みの刻み・ファイルサイズは実行のたびに変わります）。

### 11. 生成した動画を見る
```powershell
Get-Item output.mp4 | Select-Object Name, Length
code output.mp4
```
エディターで再生できます。動画の中身は実行のたびに変わります。生成された動画には音声も入ります。

### 12. 対応していない長さを渡して、エラーの中身を見る
```powershell
python main.py --seconds 5
```
```text
エラー: Error code: 400 - {'error': {'message': "Invalid value: '5'. Supported values are: '4', '8', and '12'.", ...
```
長さ（`seconds`）は `4`・`8`・`12` のどれかです。サイズ（`size`）も決まった値だけで、講座の検証では `720x1280`・`1280x720`・`1024x1792`・`1792x1024` が通り、`480x480` は 400 になりました。エラー本文に使える値が出るので、まずそこを読みます。

### 13. サービスに保存された動画を一覧して削除する
```powershell
python main.py list
python main.py delete all
```
生成した動画はサービス側にも一定期間（ジョブの作成から最大24時間）残ります。`list` で一覧、`delete` で削除できます。最後に `残り: 0 件` と出れば完了です。

### 14. 後片付け（このレッスンと L3-1 のリソースグループ）
```powershell
$RG
az group delete --name $RG --yes --no-wait
az group delete --name rg-udemy-ai-103-training-gen --yes --no-wait
```
- 1行目で `$RG` が講座共通の `rg-udemy-ai-103-training` ではなく `rg-udemy-ai-103-training-video` であることを確かめてから実行します。
- 3行目は L3-1（画像生成）で作ったリソースグループです。L3-1 をやっていない場合は `ResourceGroupNotFound` になりますが、問題ありません。

削除が終わったら（数分）、削除済みのリソースを purge してクォータを空けます。
```powershell
az cognitiveservices account list-deleted `
  --query "[?contains(name,'ai103-vid') || contains(name,'ai103-gen')].{name:name, location:location}" -o table
az cognitiveservices account purge --name $ACCOUNT --resource-group $RG --location $LOCATION
```
L3-1 の `ai103-gen-…` も一覧に出たら、その名前で同じように purge します（`--resource-group rg-udemy-ai-103-training-gen --location eastus2`）。削除しただけのリソースは、デプロイのクォータを最大48時間つかんだままになります。purge には、サブスクリプション単位の Contributor（または Cognitive Services Contributor）が必要です。

## 注意点（試験の論点）
- 動画生成は**非同期のジョブ**です。作成（create）→ 状態の確認（retrieve、ポーリング）→ 取得（download_content）の3段で、作成の応答に動画は入っていません。
- 状態は `queued` → `in_progress` → `completed`／`failed`。`progress` で進み具合（%）も分かります。
- 同時に走らせられる作成ジョブは2つまでです。生成した動画は作成から最大24時間サービスに残ります。
- 動画生成モデルは組み込みの安全対策を持ち、**写実的な（photorealistic）内容や知的財産（IP）に当たる内容はブロック**されます。このレッスンのプロンプトはイラスト調にしています。
- `sora-2` はプレビューで、2026-10-15 に退役予定（後継の記載なし）。プレビューのモデルは、退役時に新しい版へ強制的に切り替わるか、後継なしで退役します。

## つまずき
- **手順5で `InsufficientQuota`**：そのリージョンのクォータが足りません。手順2の `used`・`limit` を見て、空きのあるリージョンに変えるか、クォータ増加を申請します。
- **手順4で `CustomDomainInUse`**：名前が他と重なりました。手順1の `$ACCOUNT` を作り直して、もう一度実行します。
- **`エラー: ... 400 ... Invalid value`**：`--size`／`--seconds`（または `.env` の `VIDEO_SIZE`／`VIDEO_SECONDS`）が対応値になっているか確かめます。
- **`エラー: ... 404 ...`**：`FOUNDRY_OPENAI_BASE_URL` がリソースの `/openai/v1/` 形式か、`VIDEO_MODEL` がデプロイ名と一致しているか確かめます。
- **`エラー: ... 401 ...` / `403 ...`**：手順6のロールの反映待ちか、`az login` の切れです。ロールの反映には最大10分ほどかかるので、少し待って再実行してください。
- **`失敗しました: ...`（状態が `failed`）**：プロンプトが写実的・IP に当たると判定された可能性があります。イラスト調など穏当な内容に変えてください。
- **`エラー: ... 410 ...`**：モデルが退役しています。このレッスンは実行できないので、動画で流れを確認してください。
- **`AttributeError: 'OpenAI' object has no attribute 'videos'`**：openai パッケージが古いです。`pip install -U openai` で更新します。
