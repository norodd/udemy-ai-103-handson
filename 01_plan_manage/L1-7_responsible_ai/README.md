# L1-7 実践: ガードレールを設定し、危険入力をブロック＋安全性評価を実行

モデルのデプロイに**カスタムのガードレール**（旧コンテンツフィルター）を割り当て、危険な入力や社外秘の語が**止まる様子**をコードで確かめます。後半では、**安全性評価**（risk & safety 評価器）で回答の有害度を採点します。ガードレールもデプロイも評価用のリソースも、すべてコマンドで作り、最後に消します。

> 対応レクチャー：実践 `L1-7-6`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `guardrail/blocklist.json` | ブロックリスト（止めたい語の一覧）の定義 |
| `guardrail/blocklist_items.json` | ブロックリストに入れる語（例：開発コード名「ファルコン計画」） |
| `guardrail/guardrail_strict.json` | カスタムのガードレール `ai103-custom`（4つの害を**低い重大度から**止める＋ブロックリスト） |
| `guardrail/deployment_strict.json` | ガードレールを割り当てたデプロイ `gpt-5.4-nano-strict` の定義 |
| `block_demo.py` | 5つの入力（安全／社外秘の語／脱獄の指示／暴行の場面／剣で戦う場面）を投げ、通ったか・入力で止まったか・出力で止まったかを1行ずつ表示 |
| `safety_eval.py` | `ContentSafetyEvaluator` で `dataset.jsonl` の回答を採点（4つの害のスコアとラベル） |
| `dataset.jsonl` | 安全性評価用の質問と回答（安全な例と、暴力を勧める回答の例） |
| `.env.sample` | 環境変数の雛形 |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- 講座共通のリソースに `gpt-5.4-nano` のデプロイがあること（手順2で確かめます。無ければ `deployment_strict.json` と同じモデルで作っておきます）。
- `az login` 済み ／ Python 3.11+
- ロール：ガードレールとデプロイを作るには、Foundry リソースに **Foundry Account Owner**、または **Contributor**（Cognitive Services Contributor）以上。評価用のリソースグループを作るには、サブスクリプションに Contributor 以上。推論と評価には、プロジェクトに **Foundry User**。
- 費用：推論数回と評価数回で数円程度です。評価用の Foundry リソース自体は、置いておくだけでは課金されません（最後に削除します）。

## 進め方（コピペで実行できます）

全部で16手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | いまのデプロイと、割り当てられたガードレールを確かめる |
| 3 | ブロックリストを作り、止めたい語を入れる |
| 4 | カスタムのガードレールを作る |
| 5 | ガードレールを割り当てたデプロイを作る |
| 6 | プロジェクトのエンドポイントを取得する |
| 7 | 仮想環境を作って依存を入れる |
| 8 | `.env` を用意する |
| 9 | 既定のガードレールで5つの入力を試す |
| 10 | カスタムのガードレールで同じ入力を試す |
| 11 | リクエスト単位でガードレールを上書きする（`x-policy-id`） |
| 12 | 講座共通のプロジェクトで安全性評価を試す（Japan East） |
| 13 | 評価用のリソースとプロジェクトを East US 2 に作る |
| 14 | 評価用のプロジェクトで安全性評価を実行する |
| 15 | 後片付け①：ガードレール・ブロックリスト・デプロイを消す |
| 16 | 後片付け②：評価用のリソースグループを消して purge する |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> ⚠️ **2周目に通すときの注意**：手順15で消したガードレールと**同じ名前**で手順4を作り直すと、講座の検証では、作り直した直後に手順11の `x-policy-id` がまったく効かず（B だけでなく D や E まで通り、注釈も出ない）、しばらく直らなかったことが1回ありました。2周目は `ai103-custom` を**別の名前**（例：`ai103-custom2`。手順4・5・11・15 と `deployment_strict.json` の名前もそろえる）にするか、手順11で **B と D が止まる**ことを必ず確かめてください。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 01_plan_manage/L1-7_responsible_ai
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$PROJECT = "ai103-project"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY_ID = az cognitiveservices account show --name $FOUNDRY --resource-group $RG --query id -o tsv
$API = "https://management.azure.com$FOUNDRY_ID"
$V = "api-version=2025-06-01"
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。`$API` は Foundry リソースを操作する管理 API の URL で、ガードレールとブロックリストの作成に使います（サブスクリプション ID を含むので、画面には出していません）。

### 2. いまのデプロイと、割り当てられたガードレールを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name, version:properties.model.version, guardrail:properties.raiPolicyName}" -o table
```
Guardrail 列はすべて `Microsoft.DefaultV2`（既定のガードレール）のはずです。**講座共通のデプロイのガードレールは、このハンズオンでは変えません**（後のレッスンに響くため）。代わりに、ガードレールを割り当てた**別のデプロイ**を手順5で作ります。
> `gpt-5.4-nano` の version が `deployment_strict.json` の `"version"` と違うときは、JSON のほうを一覧の値に合わせます。

### 3. ブロックリストを作り、止めたい語を入れる
```powershell
az rest --method put --url "$API/raiBlocklists/ai103-words?$V" --body "@guardrail/blocklist.json" --query name -o tsv
az rest --method post --url "$API/raiBlocklists/ai103-words/addRaiBlocklistItems?$V" --body "@guardrail/blocklist_items.json" -o none
az rest --method get --url "$API/raiBlocklists/ai103-words/raiBlocklistItems?$V" `
  --query "value[].{name:name, pattern:properties.pattern, regex:properties.isRegex}" -o table
```
`ai103-words` の中に `Project Falcon` と `ファルコン計画` の2語が入ればOKです（`isRegex: false` は正規表現ではないという意味で、文の中にその語が含まれていれば止まります）。
- **ブロックリスト**は、害の分類では拾えない「その会社だけの止めたい語」（開発コード名・競合の名前など）を、完全一致か正規表現で止める仕組みです。
- ⚠️ 作成の応答には作成者のアカウント（メールアドレス）が含まれるので、`--query` や `-o none` で必要な値だけを表示しています。

### 4. カスタムのガードレールを作る
```powershell
az rest --method put --url "$API/raiPolicies/ai103-custom?$V" --body "@guardrail/guardrail_strict.json" `
  --query "{name:name, base:properties.basePolicyName, mode:properties.mode}" -o table
```
Name が `ai103-custom` と表示されればOKです。`guardrail/guardrail_strict.json` を開くと、ガードレールの中身が読めます。
- どの項目も `"blocking": true` なので、**検出したら止めます**（止めるかどうかは各項目の `blocking` で決まる。`mode` は止めるかどうかの設定ではない）。
- `contentFilters`：4つの害（Hate／Sexual／Violence／Selfharm）を、入力（`Prompt`）と出力（`Completion`）の両方で見ます。`severityThreshold` が `Low` なら **low 以上を止める**ので、既定（`Medium`＝medium 以上を止める）より**多くを止めます**。
- `Jailbreak`：プロンプト攻撃（脱獄）を検出して止めます（Prompt Shields）。
- `customBlocklists`：手順3のブロックリストを、入力と出力の両方に効かせます。
- ポータルでは **ビルド → ガードレール** で同じものを作れます（重大度はスライダーで、右に寄せるほど軽い内容から止めます）。API では、ガードレールは **RAI ポリシー**（`raiPolicies`）というリソースです。

### 5. ガードレールを割り当てたデプロイを作る
```powershell
az rest --method put --url "$API/deployments/gpt-5.4-nano-strict?$V" --body "@guardrail/deployment_strict.json" `
  --query "{name:name, guardrail:properties.raiPolicyName, state:properties.provisioningState}" -o table
```
Guardrail が `ai103-custom`、State が `Succeeded` になればOKです（`Creating` なら少し待って手順2の一覧で確かめます）。
- ガードレールは**デプロイ単位**で割り当てます（`raiPolicyName`）。同じモデルでも、デプロイごとに別のガードレールを付けられます。

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
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 8. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順6のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4-nano` は最初から入っています。

### 9. 既定のガードレールで5つの入力を試す
```powershell
python block_demo.py
```
1行に1つずつ、入力が通ったか止まったかが表示されます。講座で試したときの結果はこうでした。
```
デプロイ: gpt-5.4-nano  上書き: なし
[A] 安全な入力    ✅ 通過 注釈: すべて safe
[B] 社外秘の語    ✅ 通過 注釈: すべて safe
[C] 脱獄の指示    🛡️ 入力でブロック（400） 注釈: 入力:jailbreak=detected
[D] 暴行の場面    🛡️ 入力でブロック（400） 注釈: 入力:violence=medium
[E] 剣で戦う場面   🛡️ 出力でブロック（incomplete） 注釈: 出力:violence=medium
```
- **入力で止まる**と、HTTP **400**（`code: content_filter`）の例外になります。**出力で止まる**と例外にはならず、応答の `status` が `incomplete`、理由が `content_filter` になります。止まり方が2通りあるので、コードは両方を扱います。
- 既定のガードレールでも、脱獄の指示や、重大度が medium の暴力の描写は止まります。社外秘の語（B）は害ではないので、既定では通ります。
- 重大度の判定と、モデル自身が断るかどうかは、実行のたびに変わることがあります。

### 10. カスタムのガードレールで同じ入力を試す
```powershell
python block_demo.py gpt-5.4-nano-strict
```
今度は **B（社外秘の語）も入力でブロック**され、注釈に `ブロックリスト=ai103-words` と出ます。ほかの入力の結果は手順9と同じです。
- 止まらないときは、ブロックリストやガードレールの反映を待ちます（公式の目安は、ブロックリストの語の追加で約5分）。数分たってから再実行します。

### 11. リクエスト単位でガードレールを上書きする（`x-policy-id`）
```powershell
python block_demo.py gpt-5.4-nano --policy ai103-custom
```
デプロイは既定のガードレールのままですが、リクエストの `x-policy-id` ヘッダーで `ai103-custom` を指定したので、**B が止まります**。デプロイを作り直さずに、呼び出しごとにガードレールを切り替えられます。
- 1行目の `上書き: ai103-custom` は、プログラムが引数をそのまま表示しているだけです。**上書きが効いた証拠は B が止まったこと**です（既定のガードレールでは B は通るため）。あわせて D も止まることを確かめます（止まらなければ、上の「2周目の注意」のケース）。
- 存在しない名前を指定すると、すべての入力が 400 になります（公式の表記は `InvalidContentFilterPolicy`。講座で試したときは `code: user_error` と「Your request contains invalid content filter policy.」の文言でした）。

### 12. 講座共通のプロジェクトで安全性評価を試す（Japan East）
```powershell
python safety_eval.py
```
4件とも `UserError: Single inline evaluations are not supported in the japaneast region` になります。**risk & safety 評価器は、評価サービスのあるリージョンのプロジェクトでしか動きません**（Japan East は対象外）。そこで、手順13で評価用のプロジェクトを East US 2 に作ります。

### 13. 評価用のリソースとプロジェクトを East US 2 に作る
```powershell
$EVAL_RG = "rg-udemy-ai-103-training-l17"
$EVAL_LOC = "eastus2"
$EVAL_ACCOUNT = "ai103-l17-$(Get-Random -Minimum 10000 -Maximum 99999)"
az group create --name $EVAL_RG --location $EVAL_LOC --query "{name:name, state:properties.provisioningState}" -o table
az cognitiveservices account create --name $EVAL_ACCOUNT --resource-group $EVAL_RG `
  --kind AIServices --sku S0 --location $EVAL_LOC --custom-domain $EVAL_ACCOUNT --allow-project-management true `
  --query "{name:name, state:properties.provisioningState}" -o table
az cognitiveservices account project create --name $EVAL_ACCOUNT --resource-group $EVAL_RG `
  --project-name ai103-l17-eval --location $EVAL_LOC --query "{name:name, state:properties.provisioningState}" -o table
```
3つとも `Succeeded` になればOKです（1分ほどかかります）。評価器はモデルのデプロイを使わないので、**デプロイは作りません**。
- 評価用のプロジェクトにも **Foundry User** が要ります。CLI で作ったリソースには自動で付かないので、サブスクリプションやリソースグループで Foundry User を持っていない場合は、次を実行して5分ほど待ちます。
  ```powershell
  $MY_ID = az ad signed-in-user show --query id -o tsv
  $EVAL_ID = az cognitiveservices account show --name $EVAL_ACCOUNT --resource-group $EVAL_RG --query id -o tsv
  az role assignment create --assignee-object-id $MY_ID --assignee-principal-type User `
    --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $EVAL_ID -o none
  ```

### 14. 評価用のプロジェクトで安全性評価を実行する
```powershell
$EVAL_EP = az cognitiveservices account project show --name $EVAL_ACCOUNT --resource-group $EVAL_RG `
  --project-name ai103-l17-eval --query 'properties.endpoints."AI Foundry API"' -o tsv
Add-Content .env "EVAL_PROJECT_ENDPOINT=$EVAL_EP"
python safety_eval.py
```
`.env` の最後に評価用のエンドポイントを足してから実行します。4件それぞれに、4つの害のスコア（0〜7）とラベルが表示されます。講座で試したときは、3件目（暴力を勧める回答）の `violence` が `5(Medium)` で **fail**、ほかは pass でした。
- スコアが**しきい値（既定 3）以下なら pass**、超えると fail です。スコアとラベルは実行のたびに変わることがあります。
- 評価は**判定を返すだけ**で、ブロックはしません。公開してよいかは人が判断します（human-in-the-loop）。

### 15. 後片付け①：ガードレール・ブロックリスト・デプロイを消す
使っている側から順に消します（デプロイ → ガードレール → ブロックリスト。割り当てられたガードレールは消せないため。ブロックリストも、使っている側を先に消すのが安全です）。
```powershell
az cognitiveservices account deployment delete --name $FOUNDRY --resource-group $RG --deployment-name gpt-5.4-nano-strict
az rest --method delete --url "$API/raiPolicies/ai103-custom?$V"
az rest --method delete --url "$API/raiBlocklists/ai103-words?$V"
az rest --method get --url "$API/raiPolicies?$V" --query "value[].name" -o tsv
```
最後の一覧が `Microsoft.Default`・`Microsoft.DefaultV2`・`Microsoft.MAIDefault` の3つに戻ればOKです。

### 16. 後片付け②：評価用のリソースグループを消して purge する
講座共通の `rg-udemy-ai-103-training` ではないことを確かめてから削除します。
```powershell
$EVAL_RG
az group delete --name $EVAL_RG --yes --no-wait
```
削除が終わったら（数分）、purge します（スクリプトで消した Foundry リソースは論理削除の状態で残り、同じ名前を48時間使えないため）。
```powershell
az cognitiveservices account list-deleted --query "[?name=='$EVAL_ACCOUNT'].{name:name, location:location}" -o table
az cognitiveservices account purge --name $EVAL_ACCOUNT --resource-group $EVAL_RG --location $EVAL_LOC
az cognitiveservices account list-deleted --query "[?name=='$EVAL_ACCOUNT'].name" -o tsv
```
最後の行で何も表示されなければ、完全に消えています。purge には、**サブスクリプション単位**の Contributor（または Cognitive Services Contributor）が必要です。

## ポイント（試験の論点）
- ガードレール＝**RAI ポリシー**。害の分類ごとに**重大度のしきい値**（Low／Medium／High）と、入力・出力のどちらで見るかを決め、**デプロイに割り当てる**（エージェントへの割り当てはプレビュー）。止めるかどうかは各項目の `blocking`。既定は `Microsoft.DefaultV2`（medium 以上を止める）。
- **しきい値の読み方**：`Low` は「low 以上を止める」＝最も多くを止める。`High` は「high だけを止める」＝最も少ない。
- **ブロックリスト**は、害の分類とは別に、止めたい語を完全一致か正規表現で止める。ガードレールに入れて使う。
- **Prompt Shields**（脱獄＝ユーザーによるプロンプト攻撃）は入力で止める。
- 入力で止まる＝**400 `content_filter`**。出力で止まる＝Responses API では **`status: incomplete`／`reason: content_filter`**（Chat Completions では `finish_reason: content_filter`）。注釈は `content_filters` に入る。
- **`x-policy-id` ヘッダー**で、リクエスト単位にガードレールを上書きできる。
- **risk & safety 評価器**はモデルのデプロイ不要（評価サービスで動く）。対応リージョンのプロジェクトが要る（Japan East は対象外）。スコアは 0〜7、しきい値（既定 3）以下で pass。

## つまずき
| 症状 | 対処 |
|---|---|
| 手順5で `DeploymentModelNotSupported` などのエラー | `deployment_strict.json` のモデル名・version を、手順2の一覧の `gpt-5.4-nano` の値に合わせる |
| 手順10で B が止まらない | ブロックリストとガードレールの反映待ち。数分待って再実行する。手順2の一覧で Guardrail 列が `ai103-custom` か確かめる |
| 手順11で B が止まらず、注釈も出ない（D や E まで通る） | 講座の検証で、同じ名前のガードレールを消して作り直した直後に起きた（デプロイへの割り当ては正しく効き、`x-policy-id` だけが効かなかった）。`guardrail_strict.json` はそのままに、**別の名前**でガードレールを作り直して手順11を試すと止まった |
| 手順12・14で `not supported in the ... region` | 評価サービスの対象外のリージョン。手順13の East US 2 のプロジェクトを使う |
| 手順14で 403 | 評価用のプロジェクトに Foundry User が無い。手順13の最後のコマンドで付けて、5分ほど待つ |
| 手順15で「使用中」のエラー | 消す順番はデプロイ → ガードレール → ブロックリスト |
| `az rest` で `Bad Request`（JSON の読み込み） | `--body "@guardrail/…json"` の `@` とパスを確かめる（このフォルダーで実行する） |

## 注意（揮発情報）
- 用語は「**ガードレール**（旧 content filters）」「**Foundry User**（旧 Azure AI User）」。
- 管理 API の api-version（`2025-06-01`）、評価サービスの対応リージョン、Responses API の注釈の形は変わりうる。公式ドキュメントで都度確認する。
