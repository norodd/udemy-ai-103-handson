# L5-3 実践: アナライザーで文書から構造化フィールド＋markdown を抽出する

Azure Content Understanding の**カスタムアナライザー**を作り、請求書の PDF から **構造化フィールド**（会社名・合計・要約・種別）と、RAG 向けの **markdown** を同時に取り出すハンズオンです。フィールドの3つの方式（**extract**／**generate**／**classify**）を1つずつ使い、各フィールドの **confidence**（信頼度）も確かめます。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。
> 課金は、解析したページの分（コンテンツ抽出）と、Content Understanding が文脈を整える処理の分（コンテキスト化）、そしてアナライザーが使うモデルのトークンの分です（1ページの請求書を数回解析する程度なら少額です）。モデルのデプロイ（Standard 系）は、置いておくだけでは課金されません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `set_defaults.py` | リソースの「モデルの既定」（モデル名 → 自分のデプロイ名）を登録して表示する。リソースごとに1回だけ実行すればよい |
| `analyze_document.py` | カスタムアナライザーを作り、文書を解析して markdown とフィールドを表示し、最後にアナライザーを削除する |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-contentunderstanding` 1.1 系＝GA API `2025-11-01`） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・**Foundry User ロール**）。
- `az login` 済み ／ Python 3.11+
- **Content Understanding は、講座共通の Foundry リソースにそのまま入っています**（エンドポイントは `https://<リソース名>.services.ai.azure.com/`）。専用のリソースは要りません。
- 補完モデル `gpt-5.4` は、モデルを選ぶ回（L1-1）でデプロイ済みの前提です。埋め込みモデル `text-embedding-3-large` は手順3でデプロイします。
- データ操作のロールが要ります。講座の検証では **Foundry User** で通りました（SDK の README は **Cognitive Services User** を案内しています。Owner だけでは足りません）。

## 進め方（コピペで実行できます）

全部で11手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | デプロイの一覧を確かめる |
| 3 | 埋め込みモデルをデプロイする |
| 4 | Content Understanding の接続先を確かめる |
| 5 | 仮想環境を作って依存を入れる |
| 6 | `.env` を用意する |
| 7 | モデルの既定を登録する |
| 8 | アナライザーを作って文書を解析する |
| 9 | できた markdown を読む |
| 10 | 既定に無いモデル名で、作成が失敗することを確かめる |
| 11 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 05_info_extraction/L5-3_content_understanding
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. デプロイの一覧を確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{Name:name, Model:properties.model.name, Version:properties.model.version}" -o table
```
- アナライザーは**補完モデル**（フィールドの抽出・要約・分類）と、**埋め込みモデル**の2つを使います。
- `gpt-5.4` があることを確かめます。`text-embedding-3-large` が無ければ、手順3で作ります（既にあれば手順3は飛ばしてかまいません）。

### 3. 埋め込みモデルをデプロイする
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
`Succeeded` になればOKです。デプロイ名はモデル名と同じにしています（手順6の `.env` と合わせるため）。

### 4. Content Understanding の接続先を確かめる
```powershell
"https://$FOUNDRY.services.ai.azure.com/"
```
Foundry リソースの `services.ai.azure.com` のエンドポイントが、Content Understanding の接続先です。手順6で `.env` に貼ります。

### 5. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 6. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `CONTENTUNDERSTANDING_ENDPOINT=` に、手順4の URL を貼って保存します。ほかの行（解析する文書の URL、モデル名、デプロイ名）は最初から入っています。
- `CU_COMPLETION_MODEL`／`CU_EMBEDDING_MODEL` は**モデル名**（カタログの名前）です。アナライザーのコードは、このモデル名しか持ちません。
- `CU_COMPLETION_DEPLOYMENT`／`CU_EMBEDDING_DEPLOYMENT` は**自分のデプロイ名**です。手順7で、モデル名とデプロイ名の対応をリソースに登録します。

### 7. モデルの既定を登録する
```powershell
python set_defaults.py
```
```text
既定を登録しました

--- このリソースの既定（モデル名 → デプロイ名）---
  gpt-5.4 → gpt-5.4
  text-embedding-3-large → text-embedding-3-large

prebuilt-document が対応する補完モデル: 13 種類（gpt-5.4 は対応）
```
- **モデルの既定**（defaults）は、「このモデル名は、このリソースのどのデプロイで動かすか」の対応表です。**Foundry リソースごとに1回**登録すれば、そのリソースのアナライザーすべてで使われます（`PATCH /contentunderstanding/defaults`）。
- 最後の行は、親にする `prebuilt-document` が対応する補完モデルの一覧に、使うモデル名が入っているかの確認です。一覧の数は変わることがあります。
- 登録せずに今の既定を見るだけなら `python set_defaults.py --show` です（一度も登録していないリソースでは `DefaultsNotSet` になります）。

### 8. アナライザーを作って文書を解析する
```powershell
python analyze_document.py
```
```text
アナライザーを作成中...（補完モデル: gpt-5.4）
  作成 5 秒
文書を解析中...
  解析 7 秒

--- markdown（1641 文字を output.md に保存。先頭6行）---
  CONTOSO LTD.
  # INVOICE
  Contoso Headquarters
  123 456th St
  New York, NY, 10001
  INVOICE: INV-100

--- フィールド（値 / confidence）---
  company_name: CONTOSO LTD. / 0.92
  total_amount: 110.0 / 0.80
  document_summary: Contoso Ltd.がMicrosoft向けに発行した請求書で、合計は$110.00。 / 0.82
  document_type: invoice / 0.89

アナライザー 'l5_3_doc_analyzer_<数字>' を削除しました
```
- 1回の解析で、**markdown**（RAG やエージェントに渡す、構造を保ったテキスト）と、**スキーマどおりのフィールド**（業務システムに渡す値）が同時に返ります。
- `company_name`／`total_amount` は **extract**（原文から抜き出す）、`document_summary` は **generate**（モデルが文を作る）、`document_type` は **classify**（決めた選択肢から選ぶ）です。
- confidence はサービスが付ける信頼度です。いくつ以上なら自動で通すかは、アプリの側で決めます。値や秒数、要約の文面は実行のたびに変わることがあります。
- アナライザーは、スクリプトの最後（`finally`）で削除しています。

### 9. できた markdown を読む
```powershell
Select-String -Path output.md -Pattern '^#', '<table>'
```
```text
output.md:4:# INVOICE
output.md:42:<table>
output.md:62:<table>
output.md:106:<table>
```
見出しは `#`、表は **HTML の `<table>`** で表されます。全体はエディターで開いて読みます。
```powershell
code output.md
```

### 10. 既定に無いモデル名で、作成が失敗することを確かめる
```powershell
$env:CU_COMPLETION_MODEL = "gpt-4.1"
python analyze_document.py
```
```text
アナライザーを作成中...（補完モデル: gpt-4.1）
エラー: HTTP 400 InvalidRequest
  内側のエラー: DefaultDeploymentModelNotFound
  Defaults have not yet been set to 'gpt-4.1'. Call 'PATCH /contentunderstanding/defaults' first.
```
- `gpt-4.1` は対応モデルの一覧には入っていますが、**このリソースの既定に登録していない**ので、アナライザーの作成で止まります。原因は「対応していない」ではなく「既定に無い」です。
- シェルの環境変数（`$env:...`）は `.env` より優先されます（`load_dotenv()` は、すでにある環境変数を上書きしない）。

確かめたら、環境変数を消して `.env` の値に戻します。
```powershell
Remove-Item Env:CU_COMPLETION_MODEL
```

### 11. 後片付け
```powershell
Remove-Item output.md
```
- アナライザーはスクリプトが削除済みです。
- モデルの既定と `text-embedding-3-large` のデプロイは、**残しておきます**（置いておくだけでは課金されないので、残しておいても構いません）。消すときは次のコマンドです。
  ```powershell
  az cognitiveservices account deployment delete --name $FOUNDRY --resource-group $RG --deployment-name text-embedding-3-large
  ```

## 注意点（試験の論点）
- **カスタムアナライザー＝親のアナライザー＋フィールドのスキーマ**。GA（`2025-11-01`）で親にできるのは `prebuilt-document`／`prebuilt-image`／`prebuilt-audio`／`prebuilt-video` の4つです（プレビュー時代の `prebuilt-documentAnalyzer` は使えません）。
- **フィールドの方式は3つ**：extract（抜き出す）／generate（生成する）／classify（選択肢から選ぶ）。
- **モデルは名前で指定し、デプロイへの対応はリソースの既定**で決まる。既定が無いと `DefaultDeploymentModelNotFound`（手順10）。
- **confidence は既定では返らない**：`estimate_field_source_and_confidence=True` で有効にします。
- アナライザーの ID に使えるのは英数字・ドット・アンダースコアだけです（ハイフンは `InvalidAnalyzerId`）。

## つまずき
- **`DefaultDeploymentModelNotFound`**：使うモデル名が既定に登録されていない。手順7を実行する。`.env` のモデル名と、手順7の表示が合っているか確かめる。
- **`DefaultsNotSet`**：このリソースで一度も既定を登録していない（手順7）。
- **401 / 403**：データ操作のロール（Foundry User、Cognitive Services User など）が付いているか確かめる。ロールは付けてから反映まで数分かかることがある。
- **接続できない**：`.env` のエンドポイントが `https://<リソース名>.services.ai.azure.com/` になっているか確かめる。
- **`DeploymentNotFound` 系**：既定に書いたデプロイ名が、実際のデプロイ名と違う（手順2で名前を確かめ、`.env` の `CU_*_DEPLOYMENT` を直して手順7をやり直す）。
