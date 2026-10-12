# L2-2 実践: File Search ツールで PDF にグラウンディングする RAG

**File Search ツール**を使い、アップロードした PDF に基づいて回答するエージェントを作るハンズオンです。ベクトルストア作成 → PDF のアップロード（自動でチャンク化・ベクトル化）→ File Search ツール付きエージェント作成 → 文書に基づく回答（引用つき）→ 後片付け、の流れを1本の `main.py` で体験します。

> 対応レクチャー：実践 `L2-2-3`
>
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。
>
> ⚠️ **File Search は、モデルのトークン料金とは別に課金があります**（ベクトルストアの保存量など）。`main.py` は `finally` で、会話・エージェント・ベクトルストア・アップロードした PDF を毎回削除し、残っていないことを数えて表示します。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | ベクトルストア作成・PDF のアップロード・File Search エージェント作成・質問（検索と引用の表示）・後片付け |
| `product_info.pdf` | 読み込ませるサンプル文書（架空の製品「Contoso SmartHub X1」の製品情報。1ページ） |
| `product_info.md` | `product_info.pdf` と同じ内容のテキスト版（中身を確かめる用） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換。`openai` は依存として入る） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- L1-1 でデプロイした `gpt-5.4` を使います（エージェントの File Search に対応。無い場合は L1-1 の README 手順2でデプロイ）。
- `az login` 済み ／ Python 3.11+
- **講座共通のリソースは変更しません**。実行中だけベクトルストアなどを作り、終わるたびに削除します。

## 進め方（コピペで実行できます）

全部で9手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 使うデプロイを確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 読み込ませる文書の中身を見る |
| 7 | 既定の2問で実行する（文書にある事実・無い事実） |
| 8 | 自分の質問で実行する |
| 9 | 後片付けを確かめる |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-2_file_search_rag
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
`gpt-5.4` の行があればOKです。`.env` の `MODEL_DEPLOYMENT` に書くのは左の **name（デプロイ名）** です（モデルのカタログ名ではありません）。エージェントに持たせるツールとモデルには相性があり、公式のツール対応表で `gpt-5.4` は File Search が「Yes」です（[Tool support by region and model](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions#tool-support-by-region-and-model)）。

### 3. プロジェクトのエンドポイントを取得する
```powershell
az cognitiveservices account project show `
  --name $FOUNDRY `
  --resource-group $RG `
  --project-name ai103-project `
  --query 'properties.endpoints."AI Foundry API"' -o tsv
```
返ってきた URL（末尾が `/api/projects/ai103-project`）を、手順5で `.env` に貼ります。ベクトルストアもエージェントもプロジェクトに属するので、入口は**プロジェクトのエンドポイント**です。

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
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-5.4` は最初から入っています。
> ⚠️ このレッスンのキー名は `PROJECT_ENDPOINT` と `MODEL_DEPLOYMENT` です。前のレッスンの `.env` を丸ごと写さず、値だけを移してください。

### 6. 読み込ませる文書の中身を見る
```powershell
code product_info.md
```
`product_info.pdf` と同じ内容のテキスト版です。架空の製品なので、**保証期間や対応OSはモデルの一般知識には無く、この文書にしか書かれていません**。重さはどこにも書かれていません。

### 7. 既定の2問で実行する（文書にある事実・無い事実）
```powershell
python main.py
```
PDF をベクトルストアに取り込み（数秒〜十数秒）、エージェントを作って、同じ会話で2問続けて聞き、最後に後片付けをします。全体で30〜60秒ほどかかります。
```text
取り込み: product_info.pdf → status=completed
エージェント作成: name=file-search-rag-agent, version=1

あなた> この製品の保証期間と対応OSを教えて。
[検索] file_search_call 1 件
[引用] 2 件 product_info.pdf
AI> 保証期間は購入から1年間（無償修理）です。
対応OSはWindows 11およびmacOS 14以降です。

あなた> この製品の重さは？
[検索] file_search_call 1 件
[引用] 1 件 product_info.pdf
AI> 文書に記載がありません。

後片付け: ベクトルストア 0 / ファイル 0 / エージェント 0 件が残っています
```
- `status=completed` は、PDF の解析・チャンク化・ベクトル化が終わったという意味です（`upload_and_poll` が終わるまで待ちます）。
- `[検索]` は、応答に入っていた **`file_search_call`（検索の実行）** の数です。モデルが File Search を呼んだことが分かります。
- `[引用]` は、回答の `annotations` に入っていた **`file_citation`（引用）** の数と、引用元のファイル名です。**引用は回答本文とは別の場所に入ります**（本文に「【…】」のような印が付くわけではありません）。
- 2問目は、文書に重さが無いので「文書に記載がありません」と答えています。これは instructions に「文書に書かれていないことは『文書に記載がありません』と答える」と書いてあるからです。今回のように、記載が無いと答えた回にも引用が付くことがあります。引用は**検索で参照した文書を示すもので、答えの根拠がそこに書かれているとは限りません**。
- 答えの文面・件数は実行のたびに変わります。`version` は、同じ名前のエージェントが別に残っていると 1 以外になることがあります。

### 8. 自分の質問で実行する
```powershell
python main.py "開封後に返品はできる？"
```
引数を渡すと、その質問に差し替わります（`main.py` は編集しません）。文書の「返品ポリシー」の節に基づいて、開封後は初期不良のみ14日以内の交換、と答えるはずです。

### 9. 後片付けを確かめる
手順7・8の最後の行 `後片付け: ベクトルストア 0 / ファイル 0 / エージェント 0 件が残っています` が、後片付けの確認です。`main.py` は `finally` で次の4つを削除し、同じ名前のものが残っていないかを数えて表示します。
- 会話（`conversations.delete`）
- エージェントの版（`delete_version`）
- ベクトルストア（`vector_stores.delete`）
- アップロードした PDF（`files.delete`）。**ベクトルストアを消しても、元の文書ファイルは Files に残る**ので、別に消します。

途中でエラーが出ても `finally` は必ず走るので、課金のもとになるベクトルストアがプロジェクトに溜まりません。

## ポイント（試験の論点）
- **File Search の流れ**：ベクトルストアを作る → ファイルを入れる（解析・チャンク化・埋め込みはサービスが自動で行う）→ `FileSearchTool(vector_store_ids=[...])` をエージェントに持たせる。
- **既定のチャンク設定**：チャンク 800 トークン・重なり 400 トークン、埋め込みは `text-embedding-3-large`（256次元）、コンテキストに入れるチャンクは最大20（[File search tool](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/file-search)）。
- **検索はハイブリッド**：クエリの書き換え → 分割 → キーワード検索とセマンティック検索の併用 → 再ランク付け。
- **ベクトルストアはエージェントに1つまで**（会話にも1つまで）。1つのベクトルストアには最大 10,000 ファイル。
- **引用は `annotations` の `file_citation`** に入る。引用が付かないときは、File Search が呼ばれていないか、文書に該当する内容が無い（必ず検索させたいなら `tool_choice` を `required` にする。`required` は「ツールを1つ以上呼ぶ」の意味で、このエージェントのツールは File Search だけなので、File Search が必ず呼ばれる）。
- 既存の Azure AI Search のインデックスを検索したいなら File Search ではなく **Azure AI Search ツール**。

## つまずき
| 症状 | 対処 |
|---|---|
| `DeploymentNotFound`（404） | `MODEL_DEPLOYMENT` が**デプロイ名**と一致しているか（手順2の name） |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| 取り込みが終わらない・`status` が `completed` 以外 | 文書サイズやネットワークによって時間がかかる。対応していない形式・文字コードでないか（テキスト系は UTF-8 など） |
| `[引用] 0 件` | モデルが File Search を呼ばなかったか、該当する内容が無い。ツールが File Search だけなら `tool_choice="required"` で必ず呼ばせられる |
| 後片付けの行で 1 件以上残っている | 前の実行の取り残し（再実行は自分が作った版しか消さない）。Foundry ポータルのプロジェクトで削除する |
| `文書が見つかりません` | `DOC_PATH`（既定 `product_info.pdf`）が実行時のカレントディレクトリから見えているか（このフォルダーで実行する） |

## 後片付け
- 実行のたびに `finally` で、会話・エージェント・ベクトルストア・アップロードした PDF が削除されます（手順9）。講座共通のリソースは変更していないので、ほかに削除するものはありません。
- `Ctrl+C` などで強制終了して `後片付け:` の行が出なかったときは、もう一度 `python main.py` を実行すると、最後の行で同じ名前のものが残っていないか数えられます（残っていたら Foundry ポータルのプロジェクトで削除します）。
- レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。
