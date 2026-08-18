# CLAUDE.md

Contexto para assistentes de IA (Claude Code) neste repositório. Projeto
**didático** de um agente de IA com LangChain 1.0 + LangGraph + PostgreSQL,
construído **do zero, passo a passo**. Priorize clareza e explicação. O
`README.md` é o guia completo (o passo a passo que originou este código).

## Ambiente

- **SO:** Windows. **Terminal:** PowerShell. **Gerenciador:** `uv`. **Editor:** VS Code.
- **Console cp1252:** emoji pode dar `UnicodeEncodeError`; prefixe comandos que
  emitem emoji com `PYTHONIOENCODING=utf-8` (ex.: `langgraph --help`).
- **Não rode em pasta sincronizada em nuvem** (OneDrive/Google Drive/Dropbox): o
  `uv sync` falha com "os error 396" (hardlink). Use `uv sync --link-mode=copy`
  ou, melhor, um projeto fora de `C:\Users\...` (ex.: `C:\Projetos\...`).
- **Modelo padrão:** OpenAI `gpt-3.5-turbo` (trocável para Gemini na string do modelo).

## Comandos

```bash
uv sync                                 # instala dependências (cria .venv)
uv run python agente.py                 # roda o agente no terminal (loop)
uv run uvicorn webhook:app --reload     # sobe o webhook (teste em /docs)
```

Pré-requisitos para RODAR: PostgreSQL rodando + banco `agente_ia` + tabelas
(`sql/01..03`) + `.env` preenchido (inclui `DATABASE_URL` e `DATABASE_URL_RO`).

## Arquivos

- **`agente.py`** — versão TERMINAL (loop). Memória (PostgresSaver), histórico
  legível (conversas/mensagens), resumos, tools (CNPJ/CEP + SQL), sumarização.
  Pede o `login` no início; `thread_id = login`, `owner = login`.
- **`webhook.py`** — versão HTTP (FastAPI). Identidade vem do campo `de` da
  requisição. Monta o agente POR requisição, escolhendo a conexão SQL conforme
  `is_master` (master → `postgres` vê tudo; comum → `agente_leitura` + RLS).
- **`tools/`** — pacote de tools. Padrão: **schema (Pydantic) → service → `@tool`**.
  `__init__.py` exporta `TOOLS` + `tratar_erros_de_tool`. `_shared.py` (HTTP com
  timeout/erro), `cnpj.py` (BrasilAPI + fallback minhareceita), `cep.py` (ViaCEP),
  `error_handling.py` (`wrap_tool_call` middleware), `sql.py` (SQLDatabaseToolkit).
- **`sql/`** — 01 tabelas, 02 usuário só-leitura, 03 RLS, consultar (JOIN).

## Convenções

- **Segredos SÓ do `.env`** (`load_dotenv` + `os.environ`). NUNCA hardcodar; `.env`
  no `.gitignore`, jamais commitar.
- **SQL parametrizado com `%s`** (nunca f-string em query) — anti SQL injection.
- **Nunca fixe o `thread_id`:** derive da identidade (login no terminal, `de` no
  webhook); `owner` = a mesma identidade. Fixo = todos na mesma conversa + owner
  vazio (quebra a RLS).
- **Nova tool:** criar em `tools/`, registrar em `tools/__init__.py` (o agente usa `*TOOLS`).
- **Ligar schema à tool:** `@tool("nome", args_schema=MeuSchema)`.

## APIs verificadas (LangChain 1.x) — não assumir versões antigas

- `create_agent` de `langchain.agents`. Tools/middlewares via
  `create_agent(tools=..., middleware=[...])`.
- `SummarizationMiddleware` (`langchain.agents.middleware`) usa **`trigger=(tipo, N)`**
  (`("tokens", N)`/`("messages", N)`) + **`keep`** (padrão `("messages", 20)`).
  O `keep` tem que ser MENOR que o `trigger`, senão dispara mas não compacta.
- `wrap_tool_call` (`langchain.agents.middleware`) é **middleware** `(request, handler)`.
- `SQLDatabaseToolkit`/`SQLDatabase` de `langchain_community.*` ("sunset", mas
  funciona). Exige OBJETO de modelo (`init_chat_model(...)`). **Driver:** converter
  `postgresql://` → `postgresql+psycopg://` (não temos psycopg2).
- **RLS por usuário:** carimbar `app.usuario` na conexão via
  `SQLDatabase.from_uri(uri, engine_args={"connect_args": {"options": f"-c app.usuario={seguro}"}})`.
  SANITIZAR o valor (só alfanuméricos).
- **Concorrência (produção):** trocar conexão única por `psycopg_pool.ConnectionPool`
  + `PostgresSaver(pool)` (o checkpointer aceita pool).
- Em dúvida sobre uma API, **inspecione a lib instalada** (`inspect.signature`).

## Não fazer

- Não commitar `.env`/segredos. Conferir `git check-ignore .env` antes de commitar.
- Não dar o SQL toolkit ao usuário comum sem a conexão `agente_leitura` + RLS.
- Não publicar/push sem confirmação do dono.
