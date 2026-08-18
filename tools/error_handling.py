# tools/error_handling.py — tratamento de erro central para TODAS as tools
# =============================================================================
# Envolve a execução de qualquer tool: se ela falhar, devolve uma ToolMessage
# amigável em vez de derrubar o programa.
#
# Implementamos AS DUAS versões, para funcionar nos dois modos do agente:
#   - wrap_tool_call  (SÍNCRONA)  -> agente com .invoke  (ex.: webhook.py)
#   - awrap_tool_call (ASSÍNCRONA) -> agente com .ainvoke (ex.: agente.py com MCP)
# Antes usávamos o atalho @wrap_tool_call (só sync); com MCP o agente virou async
# e passou a exigir também a versão async. Por isso subclassamos AgentMiddleware.
# =============================================================================

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


def _mensagem_de_erro(request, erro):
    """Monta a ToolMessage amigável (reaproveitada nas duas versões)."""
    return ToolMessage(
        content=f"A ferramenta falhou: {erro}",
        tool_call_id=request.tool_call["id"],   # amarra a resposta ao pedido certo
    )


class TratarErrosDeTool(AgentMiddleware):
    """Captura erros de QUALQUER tool (sync e async) e devolve mensagem amigável."""

    # Versão SÍNCRONA — usada quando o agente roda com .invoke
    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)              # executa a tool normalmente
        except Exception as e:
            return _mensagem_de_erro(request, e)

    # Versão ASSÍNCRONA — usada quando o agente roda com .ainvoke (repare no await)
    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)        # executa a tool (await, é async)
        except Exception as e:
            return _mensagem_de_erro(request, e)


# Instância pronta (mesmo NOME de antes -> não precisa mudar os imports em lugar nenhum).
tratar_erros_de_tool = TratarErrosDeTool()
