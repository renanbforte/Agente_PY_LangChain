# agente.py — agente ASSÍNCRONO (para suportar MCP) com histórico legível,
# tools (CNPJ/CEP + SQL + MCP) e sumarização.
# =============================================================================
# POR QUE ASYNC? As tools de MCP (ex.: Google Calendar) são ASSÍNCRONAS — só
# funcionam com `await agente.ainvoke(...)`. Por isso este arquivo é async.
#
# NOTA (WINDOWS): o `ainvoke` precisa de um checkpointer async. O async do
# PostgreSQL (AsyncPostgresSaver) exige o SelectorEventLoop; já os servidores
# MCP (subprocessos) exigem o ProactorEventLoop — e no Windows os dois NÃO
# convivem. Solução: usamos o InMemorySaver (memória do agente em RAM), que roda
# no loop padrão. As tabelas conversas/mensagens/resumos CONTINUAM persistindo,
# porque usam a conexão SÍNCRONA (psycopg.connect), que não tem esse conflito.
# =============================================================================

import os
import asyncio                                    # [ASYNC] roda a função async main()
from dotenv import load_dotenv
from langchain.agents import create_agent
# [WINDOWS] checkpointer em RAM (funciona com ainvoke no loop padrão; ver nota acima):
from langgraph.checkpoint.memory import InMemorySaver
import psycopg
from tools import TOOLS, tratar_erros_de_tool
from tools.sql import criar_tools_sql
from tools.mcp import criar_tools_mcp             # [ASYNC] as tools de MCP (async)
from langchain.chat_models import init_chat_model
from langchain.agents.middleware import SummarizationMiddleware

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
DATABASE_URL_RO = os.environ["DATABASE_URL_RO"]   # conexão só-leitura, para o SQL toolkit

system_prompt = (
    "Você é um assistente prestativo que responde em português do Brasil. "
    "Você tem ferramentas para buscar empresas por CNPJ, endereços por CEP, "
    "consultar o banco de dados do projeto e gerenciar a agenda do Google Calendar. "
    "Quando o usuário perguntar sobre os DADOS do banco (ex.: 'quantas conversas "
    "existem'), use as ferramentas de SQL: primeiro liste as tabelas, veja o schema "
    "e só então rode a query. Para agenda, use as ferramentas do Google Calendar."
)


# --- Funções que salvam o histórico em texto limpo (síncronas) ---------------
# Usam psycopg síncrono (sem o conflito de loop do Windows). Chamá-las dentro do
# async é OK: são rápidas. É por isso que o histórico continua PERSISTINDO.

def garantir_conversa(conn, thread_id, owner):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversas (thread_id, owner) VALUES (%s, %s) "
            "ON CONFLICT (thread_id) DO NOTHING RETURNING id",
            (thread_id, owner),
        )
        linha = cur.fetchone()
        if linha is not None:
            conversa_id = linha[0]
        else:
            cur.execute("SELECT id FROM conversas WHERE thread_id = %s", (thread_id,))
            conversa_id = cur.fetchone()[0]
    conn.commit()
    return conversa_id


def salvar_mensagem(conn, conversa_id, papel, conteudo, owner):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO mensagens (conversa_id, papel, conteudo, owner) "
            "VALUES (%s, %s, %s, %s)",
            (conversa_id, papel, conteudo, owner),
        )
    conn.commit()


def salvar_resumo(conn, thread_id, mensagem_id, resumo):
    """Salva um resumo na tabela 'resumos'. ON CONFLICT evita duplicar o mesmo."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO resumos (thread_id, mensagem_id, resumo) "
            "VALUES (%s, %s, %s) ON CONFLICT (mensagem_id) DO NOTHING",
            (thread_id, mensagem_id, resumo),
        )
    conn.commit()


def identificar_usuario(conn, login):
    """Busca/cria o usuário e devolve (id, login, is_master).
    ATENÇÃO: só IDENTIFICA (pergunta quem é), NÃO AUTENTICA. Não é segurança real."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO usuarios (login) VALUES (%s) ON CONFLICT (login) DO NOTHING",
            (login,),
        )
        cur.execute("SELECT id, login, is_master FROM usuarios WHERE login = %s", (login,))
        linha = cur.fetchone()
    conn.commit()
    return linha


# --- Programa principal (ASYNC) ----------------------------------------------
async def main():                                 # [ASYNC] o corpo é async def
    conn = psycopg.connect(DATABASE_URL)          # conexão SÍNCRONA p/ NOSSAS tabelas

    # [WINDOWS] checkpointer em RAM (sem context manager, sem setup).
    checkpointer = InMemorySaver()

    modelo_obj = init_chat_model("openai:gpt-3.5-turbo")   # objeto p/ o SQL toolkit
    sql_tools = criar_tools_sql(DATABASE_URL_RO, modelo_obj)
    mcp_tools = await criar_tools_mcp()            # [ASYNC] await: carrega as tools do MCP

    memoria_middleware = SummarizationMiddleware(
        model="openai:gpt-3.5-turbo",
        trigger=("tokens", 2000),
    )

    agente = create_agent(
        model="openai:gpt-3.5-turbo",
        tools=[*TOOLS, *sql_tools, *mcp_tools],    # [ASYNC] + as tools de MCP
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        middleware=[tratar_erros_de_tool, memoria_middleware],
    )

    login = input("Quem é você (login)? ").strip().lower() or "renan"
    thread_id = login                              # cada login = a conversa dele
    config = {"configurable": {"thread_id": thread_id}}
    conversa_id = garantir_conversa(conn, thread_id, owner=login)

    print("Agente pronto! Digite sua mensagem. Para sair, digite: sair\n")

    while True:
        pergunta = input("Você: ")
        if pergunta.strip().lower() == "sair":
            print("Até logo!")
            break
        salvar_mensagem(conn, conversa_id, "user", pergunta, owner=login)

        # [ASYNC] ainvoke (assíncrono) no lugar de invoke — obrigatório com MCP.
        resultado = await agente.ainvoke(
            {"messages": [{"role": "user", "content": pergunta}]},
            config,
        )
        resposta = resultado["messages"][-1].content
        salvar_mensagem(conn, conversa_id, "assistant", resposta, owner=login)

        # Detecta e salva o resumo da sumarização (igual antes).
        PREFIXO = "Here is a summary of the conversation to date:"
        for msg in resultado["messages"]:
            conteudo = msg.content
            if isinstance(conteudo, str) and conteudo.startswith(PREFIXO):
                salvar_resumo(conn, thread_id, getattr(msg, "id", None), conteudo)

        print("Agente:", resposta, "\n")

    conn.close()


# [ASYNC] asyncio.run(...) executa a função async main() de forma síncrona.
if __name__ == "__main__":
    asyncio.run(main())
