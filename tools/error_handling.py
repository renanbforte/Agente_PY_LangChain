# tools/error_handling.py — tratamento de erro central para TODAS as tools

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage


# @wrap_tool_call vira um middleware que "envolve" a execução de qualquer tool.
#   request -> descreve a chamada da tool (tem request.tool_call com "id")
#   handler -> executa a tool de verdade; chamamos handler(request)
@wrap_tool_call
def tratar_erros_de_tool(request, handler):
    """Se uma tool falhar, devolve mensagem amigável em vez de derrubar o programa."""
    try:
        return handler(request)          # tenta rodar a tool normalmente
    except Exception as e:
        # A tool deu erro (429, rede, CNPJ inválido...). Em vez de crashar,
        # devolvemos uma ToolMessage: o agente lê e responde ao usuário com jeito.
        return ToolMessage(
            content=f"A ferramenta falhou: {e}",
            tool_call_id=request.tool_call["id"],   # amarra a resposta ao pedido certo
        )