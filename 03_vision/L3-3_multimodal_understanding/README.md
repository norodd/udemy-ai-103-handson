# L3-3 実践: 画像キャプションと視覚的QA（マルチモーダル理解）

同じ画像を、画像の入力に対応したチャットモデルに渡し、プロンプトを変えるだけで「簡潔キャプション」「物体の列挙（視覚QA）」「alt-text」の3つを作り分けるハンズオンです。自分の質問で視覚QAをしたり、画像の解像度の扱い（`detail`）で入力トークンがどう変わるかも確かめます。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。Azure のリソースは新しく作りません（使ったトークンの分だけ課金されます）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 画像を base64 データURIに変換し、テキスト＋画像を1通のメッセージにして `chat.completions.create` を呼ぶ。引数なしで3タスク、引数ありで自分の質問（視覚QA）。回答ごとに入力トークン数を表示する |
| `sample.jpg` | 動作確認用のサンプル画像（自作のイラスト：家・木・太陽・雲・柵） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・**Foundry User ロール**）。
- `az login` 済み ／ Python 3.11+
- 画像の入力に対応したチャットモデルのデプロイ（このハンズオンでは `gpt-5.4`。手順2で確かめます。無ければ L1-1 の README の手順2で作成）。

## 進め方（コピペで実行できます）

全部で10手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 画像を理解させるデプロイがあるか確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 入力する画像を見ておく |
| 7 | 3つのタスクを実行する |
| 8 | 自分の質問で視覚QAをする |
| 9 | `detail` を `low` にして、入力トークンを比べる |
| 10 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 03_vision/L3-3_multimodal_understanding
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. 画像を理解させるデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
`gpt-5.4` の行があればOKです。`.env` の `VISION_MODEL` に書くのは左の **name（デプロイ名）** です（モデルのカタログ名ではありません）。画像の入力に対応していないモデルのデプロイ名を書くと、画像が無視されるかエラーになります。

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
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`VISION_MODEL=gpt-5.4` と `IMAGE_DETAIL=auto` は最初から入っています。

### 6. 入力する画像を見ておく
```powershell
code sample.jpg
```
家・木・太陽・雲・白い柵が描かれたイラストです。**窓は2つ**、雲は2つあります。手順7〜9で、モデルの答えがこの画像と合っているかを見比べます。見終わったら、このタブは閉じてかまいません。

### 7. 3つのタスクを実行する
```powershell
python main.py
```
```text
デプロイ: gpt-5.4 ／ 画像: sample.jpg ／ detail: auto

===== 簡潔キャプション =====（入力 921 トークン）
青空の下、木と白い柵に囲まれた家が建つ風景です。

===== 物体の列挙(視覚QA) =====（入力 935 トークン）
- 家
- 木
- 太陽
- 雲
- 白い柵（フェンス）

===== alt-text =====（入力 937 トークン）
青空の下、木と白い柵のある庭に赤茶色の屋根の家が建ち、太陽と雲が浮かぶシンプルなイラスト。
```
- **同じ画像・同じ関数**で、変えているのはプロンプト（`tasks` の文）だけです。キャプション、物体の列挙、alt-text という別々の仕事になります。
- 入力トークンが約900あるのは、**画像もトークンとして数えられる**からです（プロンプトの文は数十トークン）。
- 回答の文面は、実行するたびに少し変わることがあります。

### 8. 自分の質問で視覚QAをする
```powershell
python main.py "窓はいくつありますか？"
```
```text
===== 視覚QA =====（入力 927 トークン）
窓は2つあります。家の正面に左右1つずつ見えます。
```
引数に質問を渡すと、その1問だけを聞きます（`main.py` が「1〜2文で答えてください。」を付け足します）。手順6で見た画像と答えが合っているかを確かめます。

### 9. `detail` を `low` にして、入力トークンを比べる
```powershell
$env:IMAGE_DETAIL = "low"
python main.py "窓はいくつありますか？"
```
```text
デプロイ: gpt-5.4 ／ 画像: sample.jpg ／ detail: low

===== 視覚QA =====（入力 235 トークン）
窓は2つあります。家の正面に左右1つずつ見えます。
```
- `detail` は、画像をどの解像度で読ませるかの指定です（`auto` / `low` / `high`）。`low` にすると画像を小さく読むので、**入力トークン（＝料金）が大きく下がります**（今回は 927 → 235）。
- この画像は単純なイラストなので `low` でも答えは同じでしたが、細かい文字や小さな物体を読ませるときは `low` だと読み落とすことがあります。
- シェルの環境変数（`$env:IMAGE_DETAIL`）は `.env` より優先されます（`load_dotenv()` は、すでにある環境変数を上書きしない）。

確かめたら、環境変数を消して `.env` の値に戻します。
```powershell
Remove-Item Env:IMAGE_DETAIL
```

### 10. 後片付け
このレッスンでは Azure のリソースを作っていないので、削除するものはありません（課金は使ったトークンの分だけで、数円程度です）。`gpt-5.4` のデプロイは後のレッスンでも使うので、残しておきます。

## 注意点（試験の論点）
- 画像は、Chat Completions の `content` を**リスト**にして、`{"type": "text"}` と `{"type": "image_url"}` を並べて渡します。手元のファイルは **base64 データURI**（`data:image/jpeg;base64,...`）、公開されている画像なら URL をそのまま渡せます。複数の画像を並べることもできます（Chat Completions は1回に10枚まで）。**Responses API でも `input_image` として同じように画像を渡せます**。
- 同じ画像入力の上で、**プロンプトを変えるだけ**でキャプション／視覚QA／alt-text を作り分けられます。定型の項目を大量の文書・画像から信頼度つきで抜き出したいなら、Azure Content Understanding を使います。
- **画像も入力トークンとして課金**されます。`detail: low` で安く、`high` で細部まで読ませます。
- MIME タイプは、`main.py` では拡張子が `.png` かどうかだけで決めています（それ以外は `image/jpeg` 扱い）。

## つまずき
- **認証エラー（401 / 403）**：`az login` しているか、Foundry User ロールが付いているかを確かめる。ロールは付けてから反映まで数分かかることがある。
- **404 `DeploymentNotFound`**：`VISION_MODEL` が手順2の一覧の **name（デプロイ名）** と一致しているかを確かめる。
- **画像が読み込めない（`FileNotFoundError`）**：`sample.jpg` と同じフォルダーで `python main.py` を実行しているか確かめる。
- **モデルが画像を無視した回答をする**：デプロイしたモデルが画像の入力に対応しているか、MIME タイプが画像の形式と合っているかを確かめる。
- **設定を変えたのに戻らない**：シェルの環境変数が `.env` より優先されている。`Remove-Item Env:IMAGE_DETAIL` で消す。
