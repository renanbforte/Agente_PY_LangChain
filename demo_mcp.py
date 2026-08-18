# demo_mcp.py — um agente ASSÍNCRONO que usa as tools de um servidor MCP
# =============================================================================
# Este é o "esqueleto" para agentes com MCP. Como as tools de MCP são
# assíncronas, TUDO aqui é async: usamos `await agente.ainvoke(...)` (e não o
# `.invoke` síncrono, que não funciona com MCP).
#
# Rodar:  uv run python demo_mcp.py
# (Precisa da OPENAI_API_KEY no .env. A 1ª execução baixa o servidor MCP — demora
#  um pouco. As tools vêm do registro em tools/mcp.py.)
# =============================================================================

import asyncio
from dotenv import load_dotenv
from langchain.agents import create_agent
from tools.mcp import criar_tools_mcp

load_dotenv()   # carrega a OPENAI_API_KEY do .env


async def main():
    # 1) Pega as tools dos servidores MCP (conecta e lista). É await porque é async.
    mcp_tools = await criar_tools_mcp()
    print("Tools de MCP carregadas:", [t.name for t in mcp_tools])

    # 2) Monta o agente com essas tools. Aqui usamos SÓ as de MCP para focar; num
    #    agente real, você juntaria com as suas: tools=[*TOOLS, *mcp_tools].
    agente = create_agent(
        model="openai:gpt-3.5-turbo",
        tools=mcp_tools,
        system_prompt="Você responde em português. Use as ferramentas quando precisar.",
    )

    # 3) Conversa. USAMOS ainvoke (async), porque as tools de MCP são assíncronas.
    pergunta = "Que horas são agora em São Paulo?"
    resultado = await agente.ainvoke(
        {"messages": [{"role": "user", "content": pergunta}]}
    )
    print("Você:", pergunta)
    print("Agente:", resultado["messages"][-1].content)


# asyncio.run(...) executa a função async main() de forma síncrona (uma vez).
if __name__ == "__main__":
    asyncio.run(main())
