# L4-2 実践: 多言語翻訳とトーン制御の比較

Azure Translator のテキスト翻訳 API（GA `2026-06-06`）で、①**NMT**（従来型の多言語翻訳）と ②**LLM**（トーン制御つき翻訳）を実行し、訳文を比較するハンズオンです。

> 認証は**キーレス**（`az login` ＋ `DefaultAzureCredential`）。APIキーは使いません。Azure のリソースは新しく作りません（翻訳した文字数・トークン分だけ課金されます）。

## ファイル構成
| ファイル | 役割 |
|---|---|
| `main.py` | ① NMT で多言語翻訳 → ② LLM でトーン制御（formal / informal）翻訳、の順に実行する。`python main.py nmt-tone` で「NMT に tone を付けた場合」を確かめる |
| `.env.sample` | 環境変数の雛形 |
| `requirements.txt` | Python 依存パッケージ |
| `README.md` | このファイル（手順とコマンド） |

## 前提
- L0-3（Hello, Foundry）を終えていること（講座共通のリソースグループ `rg-udemy-ai-103-training`・Foundry リソース・プロジェクト `ai103-project`・**Foundry User ロール**）。
- `az login` 済み ／ Python 3.11+
- デプロイ `gpt-5.4` があること（手順2で確かめます。無ければ L1-1 の README の手順2で作成）。
- **Azure Translator は、講座共通の Foundry リソースにそのまま入っています**（Foundry リソースは複数の AI サービスをまとめたリソースで、Translator もカスタムドメインのエンドポイントから呼べます）。Translator 用のリソースを別に作る必要はありません。

## 進め方（コピペで実行できます）

全部で9手順です。各手順のコードブロックを、そのままターミナルに貼り付けて実行します。手順1で決めた変数を後の手順で使うので、**同じターミナルで続けて**実行してください。

| 手順 | やること |
|---|---|
| 1 | 共通リソースの名前を変数に入れる |
| 2 | LLM 翻訳に使うデプロイがあるか確かめる |
| 3 | Translator の接続先を取得する |
| 4 | 仮想環境を作って依存を入れる |
| 5 | `.env` を用意する |
| 6 | NMT と LLM（トーン制御）で翻訳する |
| 7 | NMT に tone を付けたらどうなるか確かめる |
| 8 | 存在しないデプロイ名で、LLM 翻訳だけ失敗させる |
| 9 | 後片付け |

> コマンドは **PowerShell** 用です（Codespaces のターミナルで `pwsh` を選ぶ／Windows の PowerShell／Mac・Linux は PowerShell 7 を入れて `pwsh`）。行末の `` ` `` は行の継続です。
>
> 最初に、リポジトリのルートからこのフォルダーへ移動しておきます。
> ```powershell
> cd 04_text/L4-2_translation
> ```

### 1. 共通リソースの名前を変数に入れる
```powershell
$RG = "rg-udemy-ai-103-training"
$FOUNDRY = az cognitiveservices account list --resource-group $RG --query "[?kind=='AIServices'] | [0].name" -o tsv
$FOUNDRY
```
`ai103-foundry-<数字>` が表示されればOKです。

### 2. LLM 翻訳に使うデプロイがあるか確かめる
```powershell
az cognitiveservices account deployment list `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "[].{name:name, model:properties.model.name, sku:sku.name}" -o table
```
一覧に `gpt-5.4` があればOKです。LLM 翻訳には、**同じ Foundry リソースにある**チャットモデルのデプロイ名を渡します（NMT はデプロイ不要です）。

### 3. Translator の接続先を取得する
```powershell
az cognitiveservices account show `
  --name $FOUNDRY `
  --resource-group $RG `
  --query "properties.endpoint" -o tsv
```
`https://<リソース名>.cognitiveservices.azure.com/` が表示されます。これが**カスタムドメインのエンドポイント**で、キーレス（Entra ID）で Translator を呼ぶときの入口です（グローバルの `api.cognitive.microsofttranslator.com` を Entra ID で使うには、リソース ID などの追加ヘッダーが要ります。このハンズオンはカスタムドメインで呼びます）。手順5で `.env` に貼ります。

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
開いた `.env` の `TRANSLATOR_ENDPOINT=` に手順3の URL を貼って保存します。`TRANSLATOR_KEY=` は**空のまま**にします（空ならキーレスで呼びます。**キーが入っていると、キー認証が先に使われます**。キーレスに移したつもりでキーが残っていると、黙ってキーで呼び続けるので注意）。`LLM_DEPLOYMENT=gpt-5.4` は最初から入っています。

### 6. NMT と LLM（トーン制御）で翻訳する
```powershell
python main.py
```
```text
=== ① NMT 多言語翻訳 ===
原文: ご来店ありがとうございます。本日のおすすめをご案内します。
  [en] Thank you for visiting. Here are today's recommendations.
  [es] Gracias por visitarnos. Aquí tienes las recomendaciones de hoy.
  [de] Vielen Dank für Ihren Besuch. Hier sind die heutigen Empfehlungen.

=== ② LLM トーン制御（英語：formal vs informal／デプロイ: gpt-5.4）===
  [formal]   Thank you for visiting our store. We will guide you through today's recommendations.
  [informal] Thank you for coming in. Let me tell you today's recommendations.
```
- ① は `targets` に `deploymentName` を書かない（＝NMT）。1回の呼び出しで3言語に訳せます。
- ② は `targets` に `deploymentName`（手順2のデプロイ名）と `tone` を書く（＝LLM 翻訳）。**同じ API・同じ URL で、`targets` の書き方だけで NMT と LLM が切り替わります**。
- LLM の訳文は、実行するたびに少し変わることがあります（上の例と一字一句同じでなくてかまいません）。見るのは「formal と informal で、丁寧さや言い回しが違う」ことです。

### 7. NMT に tone を付けたらどうなるか確かめる
```powershell
python main.py nmt-tone
```
```text
=== NMT に tone を付けた場合 ===
  [formal] Thank you for visiting. Here are today's recommendations.
  [informal] Thank you for visiting. Here are today's recommendations.
```
`deploymentName` を書かない NMT の要素に `tone` を付けても、**エラーにはならず、黙って無視されます**（2行とも手順6の `[en]` と同じ文）。tone（と gender）は LLM 翻訳だけの機能です。

### 8. 存在しないデプロイ名で、LLM 翻訳だけ失敗させる
```powershell
$env:LLM_DEPLOYMENT = "no-such-deployment"
python main.py
```
```text
=== ① NMT 多言語翻訳 ===
  …（① は成功する）

=== ② LLM トーン制御（英語：formal vs informal／デプロイ: no-such-deployment）===
[HTTPエラー] 400: {"code":"400","message":"Failed to get information on deployment no-such-deployment. Please double check that the deployment exists."}
```
- NMT はデプロイを使わないので成功し、LLM 翻訳だけが失敗します。デプロイが見つからないときは **404 ではなく 400** が返り、本文に理由が書かれています。
- シェルの環境変数（`$env:LLM_DEPLOYMENT`）は `.env` より優先されます（`load_dotenv()` は、すでにある環境変数を上書きしない）。

確かめたら、環境変数を消して `.env` の値に戻します。
```powershell
Remove-Item Env:LLM_DEPLOYMENT
```

### 9. 後片付け
このレッスンでは Azure のリソースを作っていないので、削除するものはありません（課金は翻訳した文字数とトークンの分だけで、1円未満です）。`gpt-5.4` のデプロイは後のレッスンでも使うので、残しておきます。

## 注意点（試験の論点）
- **NMT と LLM は同じ API**：`targets` の要素に `deploymentName` を書くと LLM 翻訳、書かないと NMT（汎用モデル）。カスタム翻訳（Custom Translator）のモデルを使うときは、`deploymentName` にカテゴリ ID を書きます。
- **tone / gender は LLM 翻訳のみ**。NMT に付けても効きません（エラーにもなりません）。
- **キーレスで呼ぶには、カスタムドメインのエンドポイント**を使い、トークンのスコープは `https://cognitiveservices.azure.com/.default`（Foundry の推論の `https://ai.azure.com/.default` とは宛先が違います）。キー認証のときは `Ocp-Apim-Subscription-Key`（とリージョン）ヘッダーを使います。

## つまずき
- **401 / 403**：エンドポイントがカスタムドメイン（`<リソース名>.cognitiveservices.azure.com`）になっているか、ロールが付いているか、`.env` の `TRANSLATOR_KEY` に古いキーが残っていないかを確かめる。ロールは付けてから反映まで数分かかることがある。403 は無料枠を使い切ったときにも出る。
- **LLM 翻訳だけ 400**：`LLM_DEPLOYMENT` が、同じ Foundry リソースにある**デプロイ名**（カタログ名ではない）かを確かめる（手順8）。
- **tone が効かない**：`targets` の要素に `deploymentName` を指定しているか確認する（手順7）。
- **設定を変えたのに戻らない**：シェルの環境変数が `.env` より優先されている。`Remove-Item Env:LLM_DEPLOYMENT` で消す。
- **リクエストが大きすぎて 400**：上限は NMT が要素1000個・各5万文字、LLM が要素50個・各5000文字。分割して送る。
- **429**：時間あたりの制限。間隔をあけて送り直す。
