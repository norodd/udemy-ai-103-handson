# L3-4 実践: 画像のコンテンツモデレーション（Azure AI Content Safety）

画像を Azure AI Content Safety に送って、4つのカテゴリ（Hate／Sexual／Violence／SelfHarm）の重大度を受け取り、**アプリ側で決めたしきい値**で受理（Accepted）／拒否（Rejected）を判定するハンズオンです。しきい値を変えると、同じ重大度でも判定が変わることと、入力の制限に引っかかったときのエラーも確かめます。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。Content Safety 専用のリソースは作らず、講座共通の Foundry リソース（AIServices）のエンドポイントで呼びます（課金は判定した画像の枚数分だけで、数枚なら数円未満）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 画像を `analyze_image` に送り、カテゴリ別の重大度と、しきい値との比較、最終的な受理／拒否を表示する。引数で画像を差し替え、`--threshold` でしきい値を上書きできる |
| `test.jpg` | 動作確認用の画像（自作の風景イラスト。960×640） |
| `tiny.png` | 入力の制限を確かめるための小さな画像（40×40） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・**Foundry User ロール**）。
- `az login` 済み ／ Python 3.11+
- Foundry リソースのリージョンが Content Safety（画像の分析）に対応していること（講座共通の japaneast は対応）。

## 進め方（コピペで実行できます）

全部で9手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | Foundry リソースのエンドポイントを取得する |
| 3 | 仮想環境を作って依存を入れる |
| 4 | `.env` を用意する |
| 5 | 判定する画像を見ておく |
| 6 | 画像を判定する |
| 7 | しきい値を 0 にして、判定がアプリ側で決まることを確かめる |
| 8 | 入力の制限に引っかかる画像を送る |
| 9 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 03_vision/L3-4_content_safety
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. Foundry リソースのエンドポイントを取得する
```powershell
az cognitiveservices account show `
  --name $FOUNDRY `
  --resource-group $RG `
  --query properties.endpoint -o tsv
```
`https://ai103-foundry-<数字>.cognitiveservices.azure.com/` が返ります。これが Content Safety を含む Foundry Tools の入口です（プロジェクトのエンドポイントではありません）。手順4で `.env` に貼ります。

### 3. 仮想環境を作って依存を入れる
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2行目は Codespaces（Linux）の PowerShell 用です。Windows の PowerShell では `.\.venv\Scripts\Activate.ps1` にします。

### 4. `.env` を用意する
```powershell
cp .env.sample .env
code .env
```
開いた `.env` の `CONTENT_SAFETY_ENDPOINT=` に、手順2のエンドポイントを貼って保存します。

### 5. 判定する画像を見ておく
```powershell
code test.jpg
```
空・山・木・太陽を描いた、ごく普通の風景のイラストです。見終わったら、このタブは閉じてかまいません。

### 6. 画像を判定する
```powershell
python main.py
```
```text
画像: test.jpg（27 KB）
=== カテゴリ別の重大度 (0=Safe,2=Low,4=Medium,6=High) ===
  Hate: severity=0 / しきい値=4 -> OK
  SelfHarm: severity=0 / しきい値=4 -> OK
  Sexual: severity=0 / しきい値=2 -> OK
  Violence: severity=0 / しきい値=2 -> OK

判定: Accepted(受理)
```
- Content Safety が返すのは、**4つのカテゴリそれぞれの重大度（severity）だけ**です。画像の分析では 0・2・4・6 の4段階で返ります（0=Safe、2=Low、4=Medium、6=High）。
- 右側の「しきい値」と「OK／NG」、最後の「判定」は、**`main.py` が作っています**（`THRESHOLDS` と比べて、どれか1つでもしきい値以上なら拒否。「以上で拒否」はこのアプリの設計です）。
- カテゴリは同時に複数付くことがあります（マルチラベル）。そのため、どれか1つの結果だけでなく4つすべてを見ます。

### 7. しきい値を 0 にして、判定がアプリ側で決まることを確かめる
```powershell
python main.py test.jpg --threshold 0
```
```text
  Hate: severity=0 / しきい値=0 -> NG(拒否)
  ...
判定: Rejected(拒否)
```
- 画像も重大度（すべて 0）も手順6と同じなのに、判定だけが拒否に変わります。**判定を決めているのはサービスではなくアプリのしきい値**だ、ということの確認です。
- しきい値 0 は「Safe まで拒否する」設定なので、実際の運用では使いません（ここでは確認のためだけに使っています）。`--threshold` は、その実行のときだけ4つのカテゴリのしきい値をまとめて上書きします。コードの `THRESHOLDS` は変わりません。

### 8. 入力の制限に引っかかる画像を送る
```powershell
python main.py tiny.png
```
```text
画像: tiny.png（0 KB）
Content Safety エラー: 400 InvalidRequestBody: The width of given image is 40 pixels and is less than the minimum requirement of 50 pixels. ...
```
- 画像の分析には入力の制限があります：**ファイルは 4 MB まで、縦横は 50×50〜7200×7200 ピクセル、形式は JPEG／PNG／GIF／BMP／TIFF／WEBP**。
- 制限に合わない画像は、判定されずに 400 で返ります。`main.py` はこれを `HttpResponseError` で受けて、エラーのコードとメッセージだけを表示しています。

### 9. 後片付け
このレッスンでは Azure のリソースを作っていないので、削除するものはありません（課金は判定した画像の枚数分だけです）。

## 注意点（試験の論点）
- Content Safety は**重大度を返すだけ**です。受理／拒否の最終判断は、**アプリ側がしきい値で決めます**（`THRESHOLDS`）。カテゴリごとに違うしきい値にできます（例：性的・暴力は厳しめの 2、ヘイト・自傷は中程度の 4）。
- 画像の分析が返す重大度は **0・2・4・6 の4段階**です（テキストの分析は、指定すれば 0〜7 の8段階でも返せます）。
- 呼び出しは `ContentSafetyClient(エンドポイント, 資格情報)` → `analyze_image(AnalyzeImageOptions(image=ImageData(content=バイト列)))`。画像はバイト列（SDK が base64 にして送る）か、Blob Storage の URL で渡します。
- キーレスで呼ぶには、呼び出す ID にデータ操作のロールが要ります。**Foundry リソースなら Foundry User**（Learn の Foundry の RBAC。この講座では L0-3 で付けた Foundry User で呼べることを確かめています）、**専用の Content Safety リソースなら Cognitive Services User**（＋ Reader）です。

## つまずき
- **認証エラー（401 / 403）**：`az login` しているか、Foundry User（または Cognitive Services User）ロールが付いているかを確かめる。ロールは付けてから反映まで数分かかることがある。
- **`KeyError: 'CONTENT_SAFETY_ENDPOINT'`**：`.env` が無いか、キーの名前が違う。手順4をやり直す。
- **`接続できません（.env の CONTENT_SAFETY_ENDPOINT を確認）: ... non-https ...`**：`.env` をコピーしたあと、値を貼り忘れている（空のまま）。`KeyError` ではなく、https ではないという `ServiceRequestError` になる。手順2のエンドポイントを貼って保存する。
- **400 `InvalidRequestBody`**：画像が入力の制限（4 MB・50×50〜7200×7200・対応形式）に合っていない。
- **401 `Unauthorized`（audience is incorrect）**：`.env` にプロジェクトのエンドポイント（`.../api/projects/...`）を貼っている。Content Safety は手順2のリソースのエンドポイント（`...cognitiveservices.azure.com/`）で呼ぶ。
- **画像が見つかりません**：`main.py` と同じフォルダーで実行しているか確かめる。
