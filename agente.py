# agente.py — agente com memória (PostgreSQL), histórico legível e tools

import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg
# A "vitrine" do pacote tools/: a lista com todas as tools.
from tools import TOOLS, tratar_erros_de_tool
from tools.sql import criar_tools_sql
from langchain.chat_models import init_chat_model
from langchain.agents.middleware import SummarizationMiddleware

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

DATABASE_URL_RO = os.environ["DATABASE_URL_RO"]   # conexão só-leitura, para o SQL toolkit

system_prompt = (
    "Você é um assistente prestativo que responde em português do Brasil. "
    "Você tem ferramentas para buscar empresas por CNPJ, endereços por CEP e para "
    "consultar o banco de dados do projeto. Quando o usuário perguntar sobre os "
    "DADOS do banco (ex.: 'quantas conversas existem', 'liste as últimas mensagens'), "
    "use as ferramentas de SQL: primeiro liste as tabelas, veja o schema da tabela "
    "relevante e só então escreva e rode a query."
)


# --- Funções que salvam o histórico em texto limpo ---------------------------

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
            """
            INSERT INTO resumos (thread_id, mensagem_id, resumo)
            VALUES (%s, %s, %s)
            ON CONFLICT (mensagem_id) DO NOTHING
            """,
            (thread_id, mensagem_id, resumo),
        )
    conn.commit()


def identificar_usuario(conn, login):
    """Busca o usuário pelo login; se não existir, cria como NÃO-master.
    Devolve (id, login, is_master).

    ATENÇÃO: isto só IDENTIFICA (pergunta quem é), NÃO AUTENTICA (não prova).
    Em produção, aqui entraria uma senha/token. Não use como segurança real."""
    with conn.cursor() as cur:
        # Se o login não existir, cria (sempre como não-master, por segurança).
        cur.execute(
            "INSERT INTO usuarios (login) VALUES (%s) ON CONFLICT (login) DO NOTHING",
            (login,),
        )
        cur.execute(
            "SELECT id, login, is_master FROM usuarios WHERE login = %s",
            (login,),
        )
        linha = cur.fetchone()
    conn.commit()
    return linha   # (id, login, is_master)

# --- Programa principal ------------------------------------------------------

conn = psycopg.connect(DATABASE_URL)



with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
    checkpointer.setup()

    modelo_obj = init_chat_model("openai:gpt-3.5-turbo")   # objeto de modelo p/ o toolkit
    sql_tools = criar_tools_sql(DATABASE_URL_RO, modelo_obj)   # <- usa o usuário só-leitura

    # Cria o middleware de sumarização. trigger=("tokens", 2000) significa:
    # "quando o histórico passar de 2000 tokens, resuma as mensagens antigas".
    memoria_middleware = SummarizationMiddleware(
        model="openai:gpt-3.5-turbo",     # usa o mesmo modelo para escrever o resumo
        trigger=("tokens", 2000),         # trigger=("messages", 6),
        #keep=("messages", 2),            <- ESSENCIAL no messages: mantém só as 2 últimas
    )

    agente = create_agent(
        model="openai:gpt-3.5-turbo",
        tools=[*TOOLS, *sql_tools],
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        middleware=[tratar_erros_de_tool, memoria_middleware],   # <- novo: tool que falha não derruba o programa
        
    )

    login = input("Quem é você (login)? ").strip().lower() or "renan"
    thread_id = login                                        # cada login = a conversa dele
    config = {"configurable": {"thread_id": thread_id}}
    conversa_id = garantir_conversa(conn, thread_id, owner=login)   # grava o dono

    print("Agente pronto! Digite sua mensagem. Para sair, digite: sair\n")

    while True:
        pergunta = input("Você: ")
        if pergunta.strip().lower() == "sair":
            print("Até logo!")
            break
        salvar_mensagem(conn, conversa_id, "user", pergunta, owner=login)
        resultado = agente.invoke(
            {"messages": [{"role": "user", "content": pergunta}]},
            config,
        )
        resposta = resultado["messages"][-1].content
        salvar_mensagem(conn, conversa_id, "assistant", resposta, owner=login)

        # Procura, entre as mensagens do estado, a que é um RESUMO e a salva.
        PREFIXO = "Here is a summary of the conversation to date:"
        for msg in resultado["messages"]:
            conteudo = msg.content
            if isinstance(conteudo, str) and conteudo.startswith(PREFIXO):
                salvar_resumo(conn, thread_id, getattr(msg, "id", None), conteudo)

        print("Agente:", resposta, "\n")

conn.close()