# tools/mcp.py — conecta a servidores MCP e devolve as tools deles
# =============================================================================
# MCP (Model Context Protocol) é um "padrão de tomada" para plugar o agente em
# servidores externos que já expõem ferramentas prontas (ex.: Google Calendar).
# Em vez de escrever a tool (schema→service→@tool), você CONECTA num servidor.
#
# ⚠️ IMPORTANTE: as tools de MCP são ASSÍNCRONAS. Por isso a função aqui é
# `async`, e quem usa o agente com MCP precisa chamá-lo com `await
# agente.ainvoke(...)` (o `.invoke` síncrono NÃO funciona com tools de MCP).
# =============================================================================

import os
from langchain_mcp_adapters.client import MultiServerMCPClient

# Passamos o ambiente atual + UV_LINK_MODE=copy para o SUBPROCESSO do servidor MCP.
# Sem o UV_LINK_MODE=copy, o `uvx`/`npx` (que baixam o servidor) podem falhar com
# "os error 396" em pastas sincronizadas na nuvem — o mesmo problema do uv sync.
# O {**os.environ, ...} faz um "merge": mantém o PATH etc. e acrescenta a variável.
_ENV = {**os.environ, "UV_LINK_MODE": "copy"}


# --- REGISTRO de servidores MCP ---------------------------------------------
# Para ADICIONAR um MCP novo no futuro: acrescente UMA entrada aqui. Só isso.
#   "command"/"args" -> como INICIAR o servidor MCP (um processo)
#   "transport"      -> "stdio" = processo local que fala por entrada/saída padrão
#   "env"            -> variáveis de ambiente para esse subprocesso
MCP_SERVERS = {
    # Servidor de EXEMPLO: hora atual e conversão de fuso. Não precisa de login.
    # `uvx` roda uma ferramenta Python (mcp-server-time) sem instalar no projeto.
    "time": {
        "command": "uvx",
        "args": ["mcp-server-time"],
        "transport": "stdio",
        "env": _ENV,
    },

    # ------------------------------------------------------------------------
    # EXEMPLO FUTURO — Google Calendar (precisa de Node.js + OAuth do Google):
    #   1. Instale o Node.js (para o `npx`).
    #   2. Crie um projeto no Google Cloud, ative a Calendar API e baixe o
    #      credentials.json (OAuth). Guarde-o FORA do Git (é segredo!).
    #   3. Descomente a entrada abaixo e ajuste o caminho do credentials.json.
    # ------------------------------------------------------------------------
    # "google_calendar": {
    #     "command": "npx",
    #     "args": ["-y", "@cocal/google-calendar-mcp"],
    #     "transport": "stdio",
    #     "env": {**_ENV, "GOOGLE_OAUTH_CREDENTIALS": "caminho/para/credentials.json"},
    # },
}


async def criar_tools_mcp():
    """Conecta aos servidores do MCP_SERVERS e devolve a LISTA de tools deles.
    É ASYNC (as tools de MCP são assíncronas). Use com `await`."""
    client = MultiServerMCPClient(MCP_SERVERS)   # cria o cliente com o registro
    return await client.get_tools()              # conecta e lista as tools
