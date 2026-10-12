# L2-12 実践: プロンプト改善 ＋ self-critique で品質を上げる

同じお題を **①baseline（素のプロンプト）→ ②改善プロンプト（役割・対象・形式を明確化）→ ③self-critique（自己批評→改稿）** の3段階で実行し、出力の変化と、そのぶん増えるコスト（呼び出し回数・トークン・時間）を見比べるハンズオンです。

> 対応レクチャー：実践 `L2-12-3`
> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。Azure のリソースは新しく作りません（使ったトークン分だけ課金されます）。

## どのデプロイで何を比べるか

| 手順 | デプロイ | 見るもの |
|---|---|---|
| 6 | `gpt-4.1-mini`（**推論しない**モデル） | プロンプトの技法（役割・対象・形式の指定、self-critique）で出力がどう変わるか。**このレッスンの本題** |
| 7 | `gpt-5.4` ＋ 推論の強さ `medium`（**推論モデル**） | 同じ4回の呼び出しで、**推論トークン**と時間がどれだけ増えるか |
| 8 | 両方 | `temperature` と `reasoning`（推論の強さ）が、どちらのモデルで使えて、どちらで 400 になるか |

Learn の Prompt engineering techniques は、**このページの技法（few-shot・chain-of-thought など）は gpt-5 や o-series のような推論モデルには推奨しない**と明記しています。推論モデルには、目的・制約・出力の形をはっきり伝える、という別の指針（Azure OpenAI reasoning models の Prompting guidance）があります。だからこのページの技法の効果は、推論しないモデル（`gpt-4.1-mini`）で見ます。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | baseline → 改善 → 批評 → 改稿の4回呼び出し。最後に段階ごとの字数・出力トークン（うち推論）・秒を一覧にする。引数でデプロイ名と推論の強さを差し替えられる |
| `param_check.py` | `temperature` と `reasoning` を付けて短い質問を送り、通るか 400 になるかを表示する |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ（`azure-ai-projects>=2.0.0` は 1.x と非互換） |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・Foundry User ロール）。
- `az login` 済み ／ Python 3.11+
- デプロイ `gpt-4.1-mini` と `gpt-5.4` があること（手順2で確かめます。`gpt-4.1-mini` は L2-10 の手順2、`gpt-5.4` は L1-1 の手順2で作成）。

## 進め方（コピペで実行できます）

全部で9手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | 使う2つのデプロイがあるか確かめる |
| 3 | プロジェクトのエンドポイントを取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | 推論しないモデルで、3段階を比べる |
| 7 | 推論モデルで、同じ4回の呼び出しのコストを見る |
| 8 | 使えるパラメーターの違いを確かめる |
| 9 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 02_genai_agents/L2-12_optimize
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. 使う2つのデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name, sku:sku.name}" -o table
```
一覧に `gpt-4.1-mini` と `gpt-5.4` があればOKです。無いときは、`gpt-4.1-mini` は L2-10 の README の手順2、`gpt-5.4` は L1-1 の README の手順2のコマンドで作ります（デプロイ自体は無料。課金は使ったトークン分だけ）。

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
開いた `.env` の `PROJECT_ENDPOINT=` に手順3のエンドポイントを貼って保存します。`MODEL_DEPLOYMENT=gpt-4.1-mini` は最初から入っています。

### 6. 推論しないモデルで、3段階を比べる
```powershell
python main.py
```
4回呼び出すので十数秒かかります。出力は5つのブロックです（長いので、ターミナルを広げて上から読みます）。
```text
モデル（デプロイ名）: gpt-4.1-mini

===== (1) baseline =====
 （形式も長さも指定していないので、前置き・見出し・箇条書き・後書きまで付いた長い文章）

===== (2) 改善プロンプト =====
 【家計簿が続かないあなたに朗報！新感覚アプリ登場】
・自動連携で入力ゼロ、手間いらず
・…（見出し＋箇条書き3つ＋一言の行動喚起）

===== 批評 =====
 ・具体性が乏しい …（辛口の編集者としての弱点の指摘）

===== (3) 改善＋self-critique =====
 （批評を反映して書き直した版）

===== まとめ（gpt-4.1-mini） =====
段階            字数  出力トークン  うち推論    秒
(1) baseline     400           282         0   6.6
(2) 改善         115            95         0   2.3
批評             319           252         0   3.4
(3) 改稿         183           146         0   3.0
合計                           775         0  15.3  （呼び出し 4 回）
```
- **(2)** が指定した形式（見出し・箇条書き3つ・行動喚起）と分量（120字程度）に寄っているかを見ます。
- **(3)** は、批評の指摘（具体性など）が反映されたかを **(2) と見比べます**。分量が増えたり、お題に無い数字が入ったりして、悪くなることもあります。
- **まとめ**の表で、self-critique が足した「批評」「改稿」の2回ぶんのトークンと時間を見ます。品質を上げるほどコストも増えます。
- 出力は毎回変わります。数字は実行例です。

### 7. 推論モデルで、同じ4回の呼び出しのコストを見る
```powershell
python main.py gpt-5.4 medium
```
1つ目の引数がデプロイ名、2つ目が推論の強さ（reasoning effort）です。出力の最後の**まとめ**だけを見ます。
```text
===== まとめ（gpt-5.4 / medium） =====
段階            字数  出力トークン  うち推論    秒
(1) baseline     509           463        96  10.2
(2) 改善         120           443       337   8.3
批評            2110          1632       105  21.9
(3) 改稿         134           629       516  10.6
合計                          3167      1054  51.1  （呼び出し 4 回）
```
- 「うち推論」が 0 でなくなります。**推論トークンは画面には出ませんが、出力トークンとして課金されます**。同じ4回でも、トークンも時間も増えます。
- 推論の強さを付けずに `python main.py gpt-5.4` で実行すると、この環境では「うち推論」が 0 のままでした（講座の検証。`gpt-5.4` は推論の強さの既定が `none`）。**既定はモデルごとに違う**（`medium` や `high` が既定のモデルもある）ので、推論させたいときは推論の強さを明示します。

### 8. 使えるパラメーターの違いを確かめる
```powershell
python param_check.py
```
```text
OK   gpt-4.1-mini {'temperature': 0.2}  → 答え 2（うち推論トークン 0）
400  gpt-4.1-mini {'reasoning': {'effort': 'medium'}}  → Unsupported parameter: 'reasoning.effort' is not supported with this model.
OK   gpt-5.4      {'reasoning': {'effort': 'medium'}}  → 答え 2（うち推論トークン 36）
400  gpt-5.4      {'reasoning': {'effort': 'medium'}, 'temperature': 0.2}  → Unsupported parameter: 'temperature' is not supported with this model.
```
- 推論しないモデルは `temperature` が使え、推論の強さは使えません。
- 推論モデル（推論を有効にしたとき）は、推論の強さが使え、`temperature` は 400 になります。Learn の Azure OpenAI reasoning models も、推論モデルの多くは `temperature`・`top_p` などを使えないとしています（講座の検証では、推論の強さが既定の `none` のときは `temperature` も通りました）。**出力を調整したいときは、推論モデルではサンプリングではなく、推論の強さと指示（完了の条件・出力の形）で調整します。**

### 9. 後片付け
このレッスンで作ったリソースはありません。デプロイ `gpt-4.1-mini` と `gpt-5.4` は後続のレッスンでも使うので残します。レッスンフォルダーの `.venv` と `.env` は、不要になったら消してかまいません（`.env` はコミットされません）。
```powershell
deactivate
Remove-Item -Recurse -Force .venv, .env
```

## ポイント（試験の論点）
- **プロンプト改善**：役割・対象・出力形式・分量を明確にすると、出力がそろう（推論しないモデルで効く技法）。
- **self-critique**：生成 → 批評 → 改稿のループ。呼び出しが増えるので、コストと遅延も増える。**重要な回答に絞って使う**。
- **「良くなった」は評価器で裏を取る**。このコードは採点しない。L2-5 の評価器で baseline と改稿を同じ観点で採点して比べる（測って・直して・また測る）。
- **推論モデルでは技法とパラメーターが変わる**：技法ページの技法（few-shot・CoT など）は推奨されない（目的・制約・出力の形は明確に伝える）／推論を有効にしたときは `temperature`・`top_p` を使わない／推論トークンも出力トークンとして課金される。モデルを替えたら、プロンプトを見直して測り直す。

## つまずき
| 症状 | 対処 |
|---|---|
| `DeploymentNotFound`（404） | 手順2の一覧にそのデプロイ名があるか。`.env` の `MODEL_DEPLOYMENT`、手順7の引数と一致しているか |
| `401`/`403` | `az login` 済みか、プロジェクトに **Foundry User** ロールがあるか |
| `PROJECT_ENDPOINT が未設定です` | `.env` の作成・値の入力を確認 |
| 手順7で `Unsupported parameter: 'reasoning.effort'` | 推論しないモデル（`gpt-4.1-mini` など）に推論の強さを渡している。手順8の2行目と同じ。推論の強さは推論モデルにだけ渡す |
| (3) が (2) より悪くなった | self-critique は必ず良くなるとは限らない。批評の観点を絞る／改稿時に元の制約も渡す／評価器で比べる |
| 実行に時間がかかる | 1回の実行で4回呼び出す。推論モデル（手順7）はさらに長い（講座の検証で約50秒） |

## 後片付け
- 新しく作ったリソースはありません（手順9）。デプロイは後続のレッスンでも使うので残します。
