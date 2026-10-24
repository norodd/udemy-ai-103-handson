# L2-4 実践: 複数ステップのツール呼び出し（検索→計算→整形）

Responses API の function calling ループを**自分の手で回し**、2つの自作ツール（在庫の検索・合計の計算）をモデルが順番に呼び、最後にモデルが結果を文章に整形する、多段の流れを観察するハンズオンです。外部サービスは使わず、ツールはすべてモック（アプリ内の固定データ）です。

> 対応レクチャー：実践 `L2-4-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 自作ツール（`search_products`・`calc_total`）の実装とツール定義、function calling ループの本体 |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- L1-1 でデプロイした `gpt-5.4` を使います（無い場合は、L1-1 の README 手順2でデプロイするか、`gpt-5.4-nano` に読み替え）。
- `az login` 済み ／ Python 3.11+
- **新しいリソースは作りません**。推論を数回するだけです（数円程度）。

## 進め方（コピペで実行できます）

全部で7手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 使うデプロイを確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 既定の質問で実行する（検索 → 計算 → 整形） |
| 7 | 質問を変えて実行する（並列のツール呼び出し） |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-4_multistep_tools
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. 使うデプロイを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
`gpt-5.4` の行があればOKです。`.env` の `MODEL_DEPLOYMENT` に書くのは左の **name（デプロイ名）** です（モデルのカタログ名ではありません）。

### 3. プロジェクトのエンドポイントを取得する
```powershell
$result = az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name ai103-project `
  -o json | ConvertFrom-Json

$result.properties.endpoints.'AI Foundry API'
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
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` は最初から入っています。
> ⚠️ このレッスンのキー名は `PROJECT_ENDPOINT` と `MODEL_DEPLOYMENT` です。前のレッスンの `.env` を丸ごと写さず、値だけを移してください。

### 6. 既定の質問で実行する（検索 → 計算 → 整形）
```powershell
python main.py
```
既定の質問は「ノートPCの在庫の合計金額を計算して、結果を日本語で2行にまとめて。」です（画面に収まるよう行数を指定しています）。次のように、**ツール呼び出しが2段続いてから**最終回答が出ます。
```text
[応答1] function_call 1 件
[ツール呼び出し] search_products({"category":"ノートPC"})
[応答2] function_call 1 件
[ツール呼び出し] calc_total({"items":[{"name":"X1","price":180000,"qty":3},{"name":"X2","price":220000,"qty":2}]})
[応答3] function_call 0 件

=== 最終回答 ===
（合計 980,000 円と内訳をまとめた文章）
```
1段目の検索結果（在庫の一覧）が、2段目の計算ツールの引数になっています。前のツールの出力が次のツールの入力になる、これが多段です。最後の「整形」はツールではなく、モデルが最終回答の文章にまとめます。`calc_total` が返すのは合計だけなので、最終回答の内訳の金額は、モデルが自分で計算して書き足したものです。文面は実行のたびに変わるので、確かめるのは**ツールが返した合計とログの順番**です。

### 7. 質問を変えて実行する（並列のツール呼び出し）
```powershell
python main.py "ノートPCとモニターの在庫の合計金額を、それぞれ計算して。3行で"
```
質問はコマンドライン引数で差し替えられます（`main.py` は編集しません）。互いに独立した2カテゴリを聞くと、**1回の応答に function_call が2件**入ることがあります（`[応答1] function_call 2 件`）。これが**並列のツール呼び出し**です。モデルが1件ずつ順番に呼ぶこともあり、その場合は `1 件` の応答が続きます。どちらでも、結果は `call_id` で注文票に結びつけて返すので、取り違えは起きません。なお「並列」はモデルの頼み方のことで、このアプリは受け取った複数件を `for` で順番に実行します。

## 期待される出力（例）
手順6・7のとおりです。最終回答の文面は実行のたびに変わります。

## ポイント（試験の論点）
- **実行するのはアプリ**。モデルは `function_call`（関数名と引数の JSON 文字列）を返すだけで、アプリが関数を実行し、`function_call_output` を `call_id` 付きで返す。
- **ループを終わらせるのはモデル**（`function_call` が 0 件になったら最終回答）。アプリ側は上限（`range(6)`）で無限ループを防ぐ。
- **信頼性の3点セット**：スキーマ（`required`・型）で縛る／例外をエラーとして結果に返す（`json.loads` も `try` の中）／ループに上限を置く。`strict: true` を付けない限りスキーマはモデルへの指示で、破られたときの受け皿がエラー処理です（`strict: true` は並列の関数呼び出しと併用できません）。
- 履歴を自分で持つときは、モデルの出力（`res.output`。推論モデルなら `reasoning` 項目も）を**丸ごと**入力に積む。`function_call` だけを積むと 400 になることがある。
- `tool_choice` の既定は `auto`（ツールが付いていても呼ばれるとは限らない）。特定の関数を強制するときは関数名を指定する。

## つまずき
| 症状 | 対処 |
|---|---|
| `DeploymentNotFound`（404） | `MODEL_DEPLOYMENT` が**デプロイ名**と一致しているか（手順2の name） |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| 推論モデルで `400` | `function_call` だけでなく、`res.output` を丸ごと `messages` に積んでいるか |
| ツールが呼ばれない | `description` や引数の説明を具体的にする（`tool_choice` の既定は `auto`） |
| `[警告] ツール呼び出しの上限に達しました。` | 6回回っても最終回答に届かなかった。ツールの戻り値や質問を見直す |

## 後片付け
- 推論を数回するだけ（数円程度）。削除が必要なリソースはありません。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。
