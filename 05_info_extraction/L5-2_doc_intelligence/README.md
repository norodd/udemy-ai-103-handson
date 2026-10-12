# L5-2 実践: PDF/画像を Layout モデルで解析して markdown を生成する

Document Intelligence の **Layout モデル（`prebuilt-layout`）** で PDF を解析し、見出しや表の構造を保った **RAG 向けの markdown** に変換するハンズオンです。あわせて、抽出された**表の数**と、単語ごとの**信頼度スコア**を確かめます。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。Azure のリソースは新しく作りません（解析したページ数の分だけ課金されます。1ページの請求書なら1円未満です）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `analyze_to_markdown.py` | PDF/画像を Layout で解析し、markdown を `output.md` に保存する。表の数と、1ページ目の単語の信頼度もコンソールに表示する |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・**Foundry User ロール**）。
- `az login` 済み ／ Python 3.11+
- **Document Intelligence は、講座共通の Foundry リソースにそのまま入っています**（Foundry リソースは複数の AI サービスをまとめたリソースで、Document Intelligence もカスタムドメインのエンドポイントから呼べます）。Document Intelligence 用のリソースを別に作る必要はありません。モデルのデプロイも要りません。

## 進め方（コピペで実行できます）

全部で9手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | Document Intelligence の接続先を取得する |
| 3 | 解析するサンプルの PDF をダウンロードする |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | Layout で解析して markdown を作る |
| 7 | できた markdown を読む |
| 8 | リージョン共通のエンドポイントで、キーレスが失敗することを確かめる |
| 9 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 05_info_extraction/L5-2_doc_intelligence
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. Document Intelligence の接続先を取得する
```powershell
az cognitiveservices account show `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "properties.endpoint" -o tsv
```
`https://<リソース名>.cognitiveservices.azure.com/` が表示されます。これが**カスタムサブドメインのエンドポイント**で、キーレス（Entra ID）で呼ぶときの入口です。手順5で `.env` に貼ります。

### 3. 解析するサンプルの PDF をダウンロードする
```powershell
New-Item -ItemType Directory -Force sample | Out-Null
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/Azure-Samples/azure-ai-content-understanding-assets/main/document/invoice.pdf" `
  -OutFile sample/invoice.pdf
Get-ChildItem sample
```
公式サンプルの請求書（1ページ・英語・架空の会社）です。L5-3 の Content Understanding でも同じ文書を使うので、出力を見比べられます。自分の PDF や画像（表・見出しを含むもの）を試すときは、`sample/` に置いて `.env` の `INPUT_FILE` を書き換えます。

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
開いた `.env` の `DOCUMENTINTELLIGENCE_ENDPOINT=` に、手順2の URL を貼って保存します。`INPUT_FILE=sample/invoice.pdf` と `OUTPUT_MD=output.md` は最初から入っています。

### 6. Layout で解析して markdown を作る
```powershell
python analyze_to_markdown.py
```
```text
markdown を保存しました: output.md（1650 文字・1 ページ）

表を 3 個検出:
  表#0: 2 行 x 6 列
  表#1: 4 行 x 8 列
  表#2: 5 行 x 2 列

1ページ目の単語: 145 個 / 信頼度0.8未満: 0 個
```
- 解析は**長時間処理**（サービス側の非同期ジョブ）なので、結果が出るまで数秒かかります。
- 「表を N 個検出」は、Layout が**表の構造**（行と列）を取り出せた、という意味です。
- 信頼度0.8未満の単語が**人の目で確かめる候補**です。きれいな英文の PDF では 0 個になることがあります（0.8 はこの教材の例で、しきい値は用途に合わせて決めます）。

### 7. できた markdown を読む
```powershell
Select-String -Path output.md -Pattern '^#', '<table>'
```
```text
output.md:4:# INVOICE
output.md:48:<table>
output.md:68:<table>
output.md:112:<table>
```
- `output.md` から、見出し（行頭の `#`）と表（`<table>`）の行だけを抜き出しています。見出しは `#`、表は **HTML の `<table>`** で、`<table>` が3つ＝手順6の「表を 3 個検出」と対応します。
- これが RAG で「見出しや表の境界で分割する」ときの手がかりになります。

全体はエディターで開いて読みます。
```powershell
code output.md
```

### 8. リージョン共通のエンドポイントで、キーレスが失敗することを確かめる
```powershell
$env:DOCUMENTINTELLIGENCE_ENDPOINT = "https://japaneast.api.cognitive.microsoft.com/"
python analyze_to_markdown.py
```
```text
エラー: HttpResponseError: (BadRequest) Please provide a custom subdomain for token authentication, otherwise API key is required. (…)
Code: BadRequest
Message: Please provide a custom subdomain for token authentication, otherwise API key is required. (…)
エンドポイントがカスタムサブドメイン付きか、データ操作のロール（Foundry User など）が 付いているか、INPUT_FILE のパスを確認してください。
```
- リージョン共通のエンドポイント（`https://<リージョン>.api.cognitive.microsoft.com/`）では、**Entra ID のトークン認証が使えません**（401 ではなく 400 BadRequest で、カスタムサブドメインを求められます）。キーレスで呼ぶには、手順2の**カスタムサブドメイン**のエンドポイントが要ります。
- シェルの環境変数（`$env:...`）は `.env` より優先されます（`load_dotenv()` は、すでにある環境変数を上書きしない）。

確かめたら、環境変数を消して `.env` の値に戻します。
```powershell
Remove-Item Env:DOCUMENTINTELLIGENCE_ENDPOINT
```

### 9. 後片付け
```powershell
Remove-Item output.md
Remove-Item -Recurse sample
```
このレッスンでは Azure のリソースを作っていないので、Azure 側で削除するものはありません。

## 注意点（試験の論点）
- **RAG の前処理は Layout ＋ markdown 出力**：`begin_analyze_document("prebuilt-layout", ..., output_content_format=MARKDOWN)`。結果の `content` が markdown そのもの。Read は文字だけで、表の構造は返しません。請求書の金額などを決まった項目で取るなら、事前構築モデル（`prebuilt-invoice` など。結果は `documents[].fields`）。
- **構造と信頼度は markdown とは別に返る**：`tables`（行数・列数・セル）と `pages[].words[].confidence`（単語ごとの信頼度）。
- **キーレスの条件は、カスタムサブドメインとデータ操作のロール**：Owner／Contributor は管理用で、トークンで呼ぶにはデータ操作のロール（Foundry User、Cognitive Services User など）が要ります。

## つまずき
- **`(BadRequest) Please provide a custom subdomain…`**：リージョン共通のエンドポイントを使っている（手順8）。手順2の URL にする。環境変数が残っていないかも確かめる（`Remove-Item Env:DOCUMENTINTELLIGENCE_ENDPOINT`）。
- **401 / 403**：データ操作のロールが付いているか確かめる。ロールは付けてから反映まで数分かかることがある。
- **`FileNotFoundError`**：手順3の `sample/invoice.pdf` があるか、`.env` の `INPUT_FILE` のパスが合っているか確かめる。
- **`ImportError: DocumentContentFormat`**：SDK が古い（ベータ版は `ContentFormat`）。`azure-ai-documentintelligence>=1.0.0` を入れ直す。旧 `azure-ai-formrecognizer` とは別のパッケージです。
- **ページが欠ける**：Document Intelligence 単体のリソースを無料枠（F0）で作った場合、PDF は先頭2ページしか処理されません（ファイルも4MBまで）。出力の「N ページ」と元の PDF のページ数を突き合わせる。
