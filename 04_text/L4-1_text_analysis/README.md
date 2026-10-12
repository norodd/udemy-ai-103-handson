# L4-1 実践: レビュー分析（感情＋エンティティ＋要約を構造化JSONで抽出）

同じレビュー群を、①**生成プロンプト版**（Responses API の structured outputs）と ②**既製機能版**（Azure Language の感情分析＋NER）の2通りで分析し、結果の違いを比較するハンズオンです。

> 対応レクチャー：実践 `L4-1-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。Azure のリソースは新しく作りません（使ったトークン・呼び出し分だけ課金されます）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | **生成プロンプト版**：Responses API の `text.format`（`json_schema`／`strict`）で構造化JSONを抽出する。引数でレビューの番号を選べる（`python main.py 1 3`。省略すると全件） |
| `language_sdk_compare.py` | **既製機能版**：Azure Language（`azure-ai-textanalytics`）の言語検出 → 感情分析＋オピニオンマイニング → NER |
| `reviews.json` | 分析対象のレビュー文（3件。日本語2件・英語1件） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・**Foundry User ロール**）。
- `az login` 済み ／ Python 3.11+
- デプロイ `gpt-5.4` があること（手順2で確かめます。無ければ L1-1 の README の手順2で作成）。
- **Azure Language は、講座共通の Foundry リソースにそのまま入っています**（Foundry リソースは複数の AI サービスをまとめたリソースで、Language のエンドポイントも持っています）。Language 用のリソースを別に作る必要はありません。呼び出しに要るロールは、L0-3 の手順8でリソースに付けた **Foundry User** で足ります（Language 専用の `Cognitive Services Language Reader` でも可）。

## 進め方（コピペで実行できます）

全部で8手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 使うデプロイがあるか確かめる |
| 3 | 接続先を2つ取得する（プロジェクト／Language） |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 生成プロンプト版で、レビューを1件ずつ分析する |
| 7 | 既製機能版で、同じレビューを分析する |
| 8 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 04_text/L4-1_text_analysis
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. 使うデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name, sku:sku.name}" -o table
```
一覧に `gpt-5.4` があればOKです（`main.py` の既定のデプロイ名）。構造化出力（`json_schema`／`strict`）に対応したモデルなら、別のデプロイでも動きます。

### 3. 接続先を2つ取得する（プロジェクト／Language）
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name ai103-project `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
az cognitiveservices account show `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "properties.endpoints.Language" -o tsv
```
1つ目（末尾が `/api/projects/ai103-project`）は生成プロンプト版がモデルを呼ぶ入口、2つ目（`https://<リソース名>.cognitiveservices.azure.com/`）は既製機能版が Language を呼ぶ入口です。**同じ Foundry リソースでも、入口の URL が違います**。どちらも手順5で `.env` に貼ります。

### 4. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
./.venv/bin/Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 5. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `PROJECT_ENDPOINT=` に手順3の1つ目、`AZURE_LANGUAGE_ENDPOINT=` に2つ目を貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` は最初から入っています。

### 6. 生成プロンプト版で、レビューを1件ずつ分析する
```powershell
python main.py 1
```
```text
モデル（デプロイ名）: gpt-5.4

=== レビュー 1 ===
入力: 先週このワイヤレスイヤホンを渋谷の店舗で買いました。音質は最高ですが、左側のバッテリーがすぐ切れます。サポートの対応は丁寧でした。
分析結果(JSON):
{
  "sentiment": "mixed",
  "entities": [
    {"text": "ワイヤレスイヤホン", "category": "製品"},
    {"text": "渋谷の店舗", "category": "場所"},
    {"text": "音質", "category": "機能"},
    {"text": "左側のバッテリー", "category": "機能"},
    {"text": "サポート", "category": "組織"}
  ],
  "summary": "渋谷の店舗で購入したワイヤレスイヤホンについて、音質は非常に高く評価されています。…"
}
```
続けて、3件目も分析します。
```powershell
python main.py 3
```
```text
=== レビュー 3 ===
入力: 新しいスマートウォッチ、デザインは気に入っています。普通かな。
分析結果(JSON):
{
  "sentiment": "mixed",
  …
```
- `sentiment` は、スキーマの `enum` で決めた4つ（`positive`／`negative`／`neutral`／`mixed`）のどれかしか返りません。`entities` の `category` は自由な文字列なので、呼ぶたびに言い方が変わることがあります。
- 画面で読みやすいように、`entities` の要素だけ1行1件で表示しています（中身は同じ JSON です）。
- 引数を付けずに `python main.py` とすると、3件すべてを順に分析します。

### 7. 既製機能版で、同じレビューを分析する
```powershell
python language_sdk_compare.py
```
```text
=== レビュー 1 ===
感情: positive  スコア: pos=0.71 neu=0.06 neg=0.23
  側面: 音質(positive) ← 最高
  側面: サポート(positive) ← 丁寧
エンティティ: 先週(DateTime), ワイヤレスイヤホン(Product), 渋谷(Location), 店舗(Location), バッテリー(Product), サポート(PersonType)

=== レビュー 2 ===
感情: negative  スコア: pos=0.00 neu=0.01 neg=0.99
  側面: hotel room(positive) ← spacious, clean
  側面: breakfast(negative) ← disappointing, overpriced
エンティティ: hotel room(Location), Osaka(Location)

=== レビュー 3 ===
感情: positive  スコア: pos=1.00 neu=0.00 neg=0.00
エンティティ: スマートウォッチ(Product)
```
（実際の値は、モデルや実行ごとに変わることがあります）

**見比べるところ**：
- **判定が割れる**：レビュー1・3は、生成プロンプト版が `mixed`、既製機能版が `positive` になりました。既製機能版は**文ごとの感情から文書全体のラベルを決め**、生成プロンプト版は**文書全体をモデルが読んで判定する**ので、同じレビューでも割れることがあります（「どちらが正しい」ではなく、何を基準にした判定かで選びます）。
- **既製機能版にしか無いもの**：信頼度スコア（`pos`／`neu`／`neg`）、側面ごとの感情（オピニオンマイニング）、決まった分類体系のエンティティカテゴリ（`Product`・`Location`・`DateTime` など）。
- **生成プロンプト版にしか無いもの**：要約（`summary`）と、開発者が決められるカテゴリ（このコードは例をプロンプトに書き、`enum` では縛っていない）。既製機能にも要約の API はありますが、これも 2029年3月31日に退役予定です。
- 既製機能版は、言語を指定しないと既定の `"en"` として解析されるので、先に `detect_language` で言語を検出してから渡しています。

### 8. 後片付け
このレッスンでは Azure のリソースを作っていないので、削除するものはありません（課金は呼び出した分だけで、数円程度です）。`gpt-5.4` のデプロイは後のレッスンでも使うので、残しておきます。

## 注意点（試験の論点）
- 構造化出力（`json_schema`／`strict`）を使う場合、スキーマの**すべてのフィールドを required にする**・**object には `additionalProperties: false` を付ける**という制約があります。
- システムメッセージは、専用の `instructions` パラメーターで渡します（講座の検証環境では、`system` と `user` を `type` なしで並べた `input` が 400 エラーになりました）。
- 言語検出・NER・PII 検出のような**決まったタスクは既製機能**（スコアや決まった分類体系が付く）、**独自のカテゴリや要約をまとめて1回で欲しいなら生成プロンプト**、という使い分けが問われます。感情分析（オピニオンマイニング）・キーフレーズ抽出・要約は既製機能にもありますが、**2029年3月31日に退役予定**で、Learn は新しいプロジェクトを Foundry のモデルへ向けるよう案内しています。

## つまずき
- **`[エラー] Error code: 404 - ... DeploymentNotFound ...`**：`.env` の `MODEL_DEPLOYMENT` が自分の環境に無いデプロイ名です。カタログ名ではなく、手順2の一覧の `Name` 列の値にします。認証自体は通っています（404 はデプロイが見つからないだけ）。
- **既製機能版で 401／403**：`AZURE_LANGUAGE_ENDPOINT` が手順3の2つ目（`cognitiveservices.azure.com`）になっているか、Foundry User ロールがリソースに付いているかを確かめます。ロールは付けてから反映まで数分かかることがあります。
- **環境変数を変えても反映されない**：`load_dotenv()` は、すでに設定済みの環境変数を上書きしません。シェルの環境変数（`$env:MODEL_DEPLOYMENT=...`）は `.env` より優先されます。
- **感情が期待とずれる**：既製機能版と生成プロンプト版は判定基準が違うので、割れること自体は想定内です。
