"""L2-8 リモート MCP サーバーのツールをエージェントに接続して呼ぶ。

MCPTool でリモート MCP サーバー（GitHub）を宣言し、require_approval="always" で
承認フロー（mcp_approval_request → mcp_approval_response）を自分のコードで処理する。
MCP サーバーへの認証（GitHub の PAT）はコードに書かず、プロジェクトの接続に持たせる。
Foundry への認証はキーレス（az login ＋ DefaultAzureCredential）。finally で後片付け。

処理の流れ:
    1. Foundry のプロジェクト接続を確認し、MCP ツールを持つエージェントを作成する
    2. 質問を送信し、モデルから返されたツール一覧や承認要求を確認する
    3. 承認要求の内容を表示し、利用者の判断を承認応答としてモデルに返す
    4. ツールの実行結果を含む最終応答を表示し、会話とエージェントを削除する

設定:
    PROJECT_ENDPOINT       Foundry プロジェクトのエンドポイント（必須）
    MODEL_DEPLOYMENT        使用するモデルのデプロイ名（省略時は gpt-5.4）
    MCP_CONNECTION_NAME    Foundry に登録した MCP 接続名（必須）
    MCP_SERVER_URL         MCP サーバーの URL（省略時は GitHub Copilot MCP）

使い方:
    python main.py                        # 既定：「私の GitHub のユーザー名は？」（承認プロンプトが出る。y で呼ぶ、それ以外は拒否）
    python main.py "別の質問"             # 質問を差し替える
"""

import os
import sys
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, MCPTool
from openai.types.responses.response_input_param import McpApprovalResponse
from dotenv import load_dotenv

# .env の設定を環境変数として読み込む
load_dotenv()
# Foundry プロジェクトの接続先と、エージェントに使わせるモデルのデプロイ名
PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT")
MODEL_DEPLOYMENT = os.getenv("MODEL_DEPLOYMENT", "gpt-5.4")

# MCP 接続名と接続先。GitHub の認証情報は Foundry 側の接続で管理する。
# このスクリプトでは接続の資格情報を読み出したり、ログに出したりしない。
MCP_CONNECTION_NAME = os.getenv("MCP_CONNECTION_NAME")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://api.githubcopilot.com/mcp")

# 作成するエージェント名と、このサンプルで利用を許可するツール
AGENT_NAME = "mcp-agent"
ALLOWED_TOOLS = ["get_me"]  # 許可リスト：この講座で使うツールだけに絞る（最小権限）


def count_items(response) -> str:
    """応答内のイベント種別と件数を、確認しやすい文字列にまとめる。

    Responses API は通常のテキストだけでなく、ツール一覧・承認要求・
    ツール実行結果などを output の項目として返すため、その内訳を表示する。
    """
    kinds: dict[str, int] = {}
    for item in response.output:
        # Responses API の各出力を種類ごとに集計する
        t = getattr(item, "type", "?")
        kinds[t] = kinds.get(t, 0) + 1
    return " / ".join(f"{k} {v} 件" for k, v in kinds.items())


def main() -> None:
    # 必須設定がない場合は、処理を始める前に設定方法を案内して終了する
    if not PROJECT_ENDPOINT or not MCP_CONNECTION_NAME:
        raise SystemExit("PROJECT_ENDPOINT / MCP_CONNECTION_NAME を .env に設定してください。")
    # コマンドライン引数があれば質問として使い、なければ既定の質問を使う
    question = sys.argv[1] if len(sys.argv) > 1 else "私の GitHub のユーザー名は？"

    # DefaultAzureCredential により、Azure CLI などのログイン情報で認証する
    project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())
    openai = project.get_openai_client()

    # エージェントに公開するリモート MCP サーバーを定義する。
    # allowed_tools で利用可能な操作を限定し、require_approval="always" で
    # ツールを実際に実行する前に、毎回利用者の確認を必須にする。
    tool = MCPTool(
        server_label="github",
        server_url=MCP_SERVER_URL,
        require_approval="always",
        allowed_tools=ALLOWED_TOOLS,
        project_connection_id=MCP_CONNECTION_NAME,
    )

    # finally 節で確実に削除できるよう、作成前は None にしておく
    agent = conversation = None
    try:
        # 接続は名前と種類だけ確かめる（資格情報の値は取り出さない）
        conn = project.connections.get(MCP_CONNECTION_NAME)
        print(f"接続: {conn.name}（種類: {conn.type}）")

        # モデル、自然言語の指示、利用可能なツールをまとめてエージェントの版を作る。
        # MCP 接続の認証情報は project_connection_id で参照し、定義に直接含めない。
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(
                model=MODEL_DEPLOYMENT,
                instructions="必要に応じて MCP ツールを使ってください。答えは1〜2行で簡潔に書いてください。",
                tools=[tool],
            ),
        )
        print(f"エージェント作成: name={agent.name}, version={agent.version}, model={MODEL_DEPLOYMENT}")
        # 会話 ID は複数回の Responses API 呼び出しで会話の文脈を維持するために使う。
        conversation = openai.conversations.create()
        # Responses API にエージェント名を渡し、このエージェントを使って応答させる。
        ref = {"agent_reference": {"name": agent.name, "type": "agent_reference"}}

        # 1) 質問する → ツールを呼ぶ前に、承認要求（mcp_approval_request）が返る
        print(f"\nUSER> {question}")
        # 最初の応答には、ツール一覧や承認要求など、次に必要な処理が含まれる場合がある。
        response = openai.responses.create(conversation=conversation.id, input=question, extra_body=ref)
        print(f"[応答1] {count_items(response)}")
        for item in response.output:
            if getattr(item, "type", None) == "mcp_list_tools":  # サーバーから取り寄せたツールの一覧
                # 接続先が公開するツールをログに表示し、サーバーと取得結果を確認できるようにする。
                names = [t.name for t in (item.tools or [])]
                print(f"[ツール一覧] server={item.server_label} {len(names)} 件: {', '.join(names)}")

        # 2) 承認要求を人間が確かめて、承認か拒否かを返す
        input_list = []
        for item in response.output:
            if getattr(item, "type", None) == "mcp_approval_request" and item.id:
                # 要求されたツール名と引数を確認してから判断できるよう、実行前に内容を表示する。
                print(f"[承認要求] server={item.server_label} tool={item.name} arguments={item.arguments}")
                # y の場合だけ承認し、それ以外（空入力を含む）は拒否する。
                approve = input("このMCPツール呼び出しを承認しますか？ (y/N): ").strip().lower() == "y"
                # 承認要求 ID と判断結果を Responses API に返す
                input_list.append(McpApprovalResponse(
                    type="mcp_approval_response", approve=approve, approval_request_id=item.id))

        # 3) 承認応答を返して、前回の応答から処理を再開させる。
        # 承認要求がなければ追加リクエストは送らず、最初の応答をそのまま表示する。
        if input_list:
            response = openai.responses.create(
                input=input_list, previous_response_id=response.id, extra_body=ref)
            print(f"[応答2] {count_items(response)}")
            for item in response.output:
                if getattr(item, "type", None) == "mcp_call":
                    # ツール実行結果は内容そのものではなく、状態と文字数を表示する
                    status = f"エラー: {item.error}" if getattr(item, "error", None) \
                        else f"結果 {len(item.output or '')} 文字"
                    print(f"[MCP 呼び出し] tool={item.name} {status}")
        # ツール実行が承認された場合は結果を踏まえた回答、拒否された場合は拒否後の回答を表示する。
        print(f"AI> {response.output_text}")

    except Exception as ex:  # 教育目的の素朴なエラーハンドリング（1行で表示）
        print(f"[エラー] {type(ex).__name__}: {str(ex).splitlines()[0][:150]}")
    finally:
        # 成功・失敗にかかわらず、作成した会話とエージェントの版を後片付けする
        if conversation:
            openai.conversations.delete(conversation_id=conversation.id)
        if agent:
            project.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
            # 同じ名前のエージェントが残っていないか確認する
            left = [a.name for a in project.agents.list() if a.name == agent.name]
            print(f"会話とエージェントを削除しました（残り: {len(left)} 件）")


if __name__ == "__main__":
    main()
