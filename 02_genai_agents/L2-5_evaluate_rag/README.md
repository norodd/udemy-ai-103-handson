# L2-5 実践: RAG の回答を評価器でスコア化する

`azure-ai-evaluation` の `evaluate()` で、**Groundedness（根拠性）・Relevance（関連性）・Coherence（一貫性）** の3つの評価器を `data.jsonl`（質問・文脈・回答の組が3件）にまとめて実行し、1件ずつのスコアと pass/fail を表で見るハンズオンです。

> 対応レクチャー：実践 `L2-5-3`
>
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。
>
> 評価の取りまとめは**手元（ローカル）**で行い、採点役の呼び出しだけが Azure に行きます（`evaluate()` に `azure_ai_project` を渡していないので、結果は Foundry ポータルには残りません）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | 3つの評価器を組み立て、`data.jsonl` に対して `evaluate()` を実行し、スコアと pass/fail を表で表示する |
| `data.jsonl` | 評価データ（`query`・`context`・`response` の組が3件。3件目は、わざと文脈と食い違う回答） |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・Foundry User ロール）。
- 採点役（judge）に使う **`gpt-4.1-mini`** のデプロイがあること（手順2で確かめます。無い場合は下の「つまずき」の作り方）。
- `az login` 済み ／ Python 3.11+
- **講座共通のリソースは変更しません**。評価はローカルで行い、Azure 側に作るものはありません。

## 進め方（コピペで実行できます）

全部で10手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 採点役のデプロイを確かめる |
| 3 | 採点役を呼ぶエンドポイントを表示する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 評価データを見る |
| 7 | 評価を実行する |
| 8 | しきい値を上げて、pass/fail が変わるのを見る |
| 9 | 採点役を推論モデルにすると失敗することを確かめる |
| 10 | 後片付け（削除するものは無い） |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-5_evaluate_rag
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. 採点役のデプロイを確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name}" -o table
```
`gpt-4.1-mini` の行があればOKです。`.env` の `JUDGE_DEPLOYMENT` に書くのは左の **name（デプロイ名）** です。

評価器（Groundedness など）は、採点役の LLM に「採点用のプロンプト」を送って1〜5の点を付けさせる **AI 支援の評価器**です。この採点役に、推論をしないモデルの `gpt-4.1-mini` を使います。採点役には推論モデルも使えますが、このレッスンの `main.py` は評価器を既定の設定（非推論モデル向けのパラメーター）で呼ぶためです（推論モデルにするとどうなるかは手順9）。

### 3. 採点役を呼ぶエンドポイントを表示する
```powershell
"https://$FOUNDRY.openai.azure.com/"
```
表示された URL を、手順5で `.env` の `AZURE_OPENAI_ENDPOINT` に貼ります。評価器は Azure OpenAI の形式（`azure_endpoint`・`azure_deployment`・`api_version`）で採点役につなぐので、**プロジェクトのエンドポイントではなく、リソースの `openai.azure.com` のエンドポイント**を使います。

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
開いた `.env` の `AZURE_OPENAI_ENDPOINT=` に手順3の URL を貼って保存します。`JUDGE_DEPLOYMENT=gpt-4.1-mini` は最初から入っています。
> ⚠️ このレッスンのキー名は `AZURE_OPENAI_ENDPOINT` と `JUDGE_DEPLOYMENT` です。前のレッスンの `.env` を丸ごと写さないでください（`PROJECT_ENDPOINT` とは値も違います）。

### 6. 評価データを見る
```powershell
Get-Content data.jsonl
```
1行が1件で、`query`（質問）・`context`（検索で取れた文脈）・`response`（RAG の回答）の3つが入っています。
```text
{"query": "保証期間は？", "context": "保証期間：購入から1年間。", "response": "保証は1年間です。"}
{"query": "対応OSは？", "context": "対応OS：Windows 11 と macOS 14 以降。", "response": "Windows 11 と macOS 14 以降に対応します。"}
{"query": "返品はできる？", "context": "未開封なら30日以内は返品可能。", "response": "いつでも全額返金で返品できます。"}
```
3件目の回答は、文脈（未開封なら30日以内）に無いことを言っています。**質問には答えているが、文脈に基づいていない**回答です。

### 7. 評価を実行する
```powershell
python main.py
```
3件 × 3つの評価器で、採点役を計9回呼びます（10〜40秒ほど。混み合うと `429` が返り、SDK が自動で待って再試行するので時間が延びます）。
```text
採点役: gpt-4.1-mini ／ しきい値: 3（1〜5 のスコアがこれ以上なら pass）
評価中…（data.jsonl の各行を、3つの評価器がそれぞれ採点します）

No  質問            根拠性       関連性       一貫性
1   保証期間は？    4.0 pass     5.0 pass     4.0 pass
2   対応OSは？      5.0 pass     5.0 pass     4.0 pass
3   返品はできる？  2.0 fail     5.0 pass     4.0 pass

[No3 groundedness の理由] Let's think step by step: The context states that returns are possible within 30 days if the product is unopened. The response claims …

=== 集計（3件の平均と pass の割合） ===
groundedness  平均 3.67 ／ pass の割合 0.67
relevance     平均 5.00 ／ pass の割合 1.00
coherence     平均 4.00 ／ pass の割合 1.00
```
- **スコア（1〜5）は採点役のモデルが付けます**。同じデータでも実行のたびに変わることがあるので、絶対値より「どの行が低いか」を見ます。
- **pass/fail はしきい値で決まります**。既定のしきい値は 3 で、スコアが 3 以上なら pass です（採点役が pass/fail を決めているわけではありません）。
- 3件目は、関連性は 5（質問には答えている）なのに、根拠性は低く fail です。**観点を分けて測る**ので、「答えてはいるが根拠が無い」ことが分かります。
- `[… の理由]` は、採点役が書いた採点の理由（`reason`）です。日本語のデータでも、理由は英語で返りました。画面に収まるよう、先頭 150 文字で切っています。
- 集計の「pass の割合」は、しきい値以上だった件数の割合です（3件中2件なら 0.67）。

### 8. しきい値を上げて、pass/fail が変わるのを見る
```powershell
python main.py --threshold 5
```
しきい値を 5 にすると、5点以外はすべて fail になります。**スコアは同じでも（実行ごとのぶれを除けば）、しきい値で pass/fail が変わる**ことが分かります。`--threshold` は `main.py` が評価器に渡す `threshold` です（コードは書き換えません）。

### 9. 採点役を推論モデルにすると失敗することを確かめる
```powershell
$env:JUDGE_DEPLOYMENT = "gpt-5.4"
python main.py
```
すべての欄が `error` になり、採点役の API のエラーが表示されます。
```text
採点に失敗した評価器があります（error の欄）。
  採点役の API のエラー: 400 Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.
```
評価器は既定で、非推論モデル向けのパラメーター（`max_tokens` など）を付けて採点役を呼びます。推論モデルはこれを受け付けないので 400 になります。推論モデルを採点役にするときは、評価器に `is_reasoning_model=True` を渡す必要があります（このレッスンの `main.py` は渡していません）。Learn は、採点役に推論モデルも非推論モデルも使えるとしています。

確かめたら、環境変数を元に戻します（`.env` の `gpt-4.1-mini` に戻ります）。
```powershell
Remove-Item Env:JUDGE_DEPLOYMENT
```
> 環境変数は `.env` より優先されます（`python-dotenv` は、すでにある環境変数を上書きしません）。

### 10. 後片付け
評価はローカルで行い、Azure 側に作ったものはありません。講座共通のリソースも変更していないので、削除するものはありません。レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。

## ポイント（試験の論点）
- **RAG の品質は観点を分けて測る**：Groundedness（回答が文脈に基づいているか）・Relevance（質問に答えているか）・Coherence（読みやすく筋が通っているか）。
- **AI 支援の評価器は採点役の LLM が必要**（`model_config`）。スコアは 1〜5、既定のしきい値は 3、しきい値以上が pass（[RAG evaluators](https://learn.microsoft.com/azure/foundry/concepts/evaluation-evaluators/rag-evaluators)）。
- **`evaluate()`** は、データセットの全行 × 全評価器をまとめて実行し、行ごとの結果（`rows`）と集計（`metrics`）を返す。
- 採点役を推論モデルにするなら `is_reasoning_model=True`。
- ポータルに結果を残したいときは、`evaluate()` に `azure_ai_project` を渡す（クラウドに記録する）。

## つまずき
| 症状 | 対処 |
|---|---|
| `AZURE_OPENAI_ENDPOINT が未設定です` | `.env` を作ったか、手順3の URL を貼ったか（手順5） |
| `error` の欄と `401`／`403` | `az login` 済みか、Foundry リソースに推論できるロール（Foundry User など）があるか |
| `error` の欄と `404`（DeploymentNotFound） | `JUDGE_DEPLOYMENT` がデプロイ名と一致しているか（手順2の name） |
| `error` の欄と `400` の `max_tokens` | 採点役が推論モデルになっている（手順9）。`Remove-Item Env:JUDGE_DEPLOYMENT` と `.env` を確認 |
| 時間がかかる | 採点役の呼び出しが `429` で待たされている。SDK が自動で再試行するので待つ |
| `gpt-4.1-mini` のデプロイが無い | 次のコマンドで作ります（課金は使ったトークン分だけ）。`az cognitiveservices account deployment create --name $FOUNDRY --resource-group $RG --deployment-name gpt-4.1-mini --model-name gpt-4.1-mini --model-version 2025-04-14 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10` |

## 後片付け
- Azure 側に作ったものはありません（手順10）。講座共通のリソースもそのまま使います。
