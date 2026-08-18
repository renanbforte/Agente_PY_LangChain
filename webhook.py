# webhook.py — webhook com identidade + isolamento por usuário (RLS)

import os
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg
from tools import TOOLS, tratar_erros_de_tool
from tools.sql import criar_tools_sql

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]          # postgres (master) — ignora RLS
DATABASE_URL_RO = os.environ["DATABASE_URL_RO"]    # agente_leitura — respeita RLS

system_prompt = (
    "Você é um assistente prestativo que responde em português do Brasil. "
    "Você pode consultar o banco de dados do projeto quando perguntarem sobre os dados."
)


# --- MONTAGEM ÚNICA (na subida do servidor) ---------------------------------
conn = psycopg.connect(DATABASE_URL)               # grava com postgres (ignora RLS)

_cm = PostgresSaver.from_conn_string(DATABASE_URL)
checkpointer = _cm.__enter__()
checkpointer.setup()

modelo_obj = init_chat_model("openai:gpt-3.5-turbo")   # objeto de modelo p/ o toolkit


# --- Funções de banco -------------------------------------------------------
def identificar_usuario(conn, login):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO usuarios (login) VALUES (%s) ON CONFLICT (login) DO NOTHING", (login,))
        cur.execute("SELECT id, login, is_master FROM usuarios WHERE login = %s", (login,))
        linha = cur.fetchone()
    conn.commit()
    return linha


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
            "INSERT INTO mensagens (conversa_id, papel, conteudo, owner) VALUES (%s, %s, %s, %s)",
            (conversa_id, papel, conteudo, owner),
        )
    conn.commit()


# --- A API ------------------------------------------------------------------
app = FastAPI()

class Mensagem(BaseModel):
    de: str
    texto: str


@app.post("/webhook")
def receber(msg: Mensagem):
    # PRODUÇÃO: verifique a ASSINATURA da requisição antes de confiar no "de".
    identidade = msg.de.strip()
    thread_id = identidade
    config = {"configurable": {"thread_id": thread_id}}

    _id, login, is_master = identificar_usuario(conn, identidade)

    # ---- LIGA O RLS AO AGENTE: a conexão do SQL depende de quem é ----
    if is_master:
        sql_tools = criar_tools_sql(DATABASE_URL, modelo_obj)                     # vê tudo
    else:
        sql_tools = criar_tools_sql(DATABASE_URL_RO, modelo_obj, app_usuario=identidade)  # só o dele

    # Monta o agente para ESTA requisição, com as tools de SQL certas.
    agente = create_agent(
        model="openai:gpt-3.5-turbo",
        tools=[*TOOLS, *sql_tools],
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        middleware=[tratar_erros_de_tool],
    )

    conversa_id = garantir_conversa(conn, thread_id, owner=identidade)
    salvar_mensagem(conn, conversa_id, "user", msg.texto, owner=identidade)

    resultado = agente.invoke(
        {"messages": [{"role": "user", "content": msg.texto}]}, config,
    )
    resposta = resultado["messages"][-1].content
    salvar_mensagem(conn, conversa_id, "assistant", resposta, owner=identidade)

    return {"de": identidade, "is_master": is_master, "resposta": resposta}