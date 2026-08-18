# Agente de IA em Python — do zero, passo a passo

> Um guia didático **completo**, em português do Brasil, para montar um agente de IA usando **LangChain 1.0 + LangGraph + PostgreSQL**. O guia foi escrito na **ordem exata** em que o projeto foi construído: cada passo é um degrau. Você não precisa saber nada de LangChain para começar — vamos explicar cada conceito novo com calma.

---

## O que você vai construir

Ao final deste guia, você terá um agente que:

- **Conversa** com você em português, usando o modelo `gpt-3.5-turbo` da OpenAI.
- **Lembra** do que já foi dito — primeiro na memória RAM, depois de verdade, salvo no **PostgreSQL** (fecha o programa, reabre, e ele continua lembrando).
- **Usa ferramentas** (chamadas de *tools*): busca empresa por **CNPJ**, endereço por **CEP** e consulta o **banco de dados em linguagem natural** (você pergunta "quantas conversas existem?" e o agente escreve o SQL sozinho).
- **Atende por webhook** (uma API HTTP com FastAPI), onde a **identidade do usuário chega junto com a mensagem** — e cada usuário só enxerga os próprios dados, graças ao **isolamento por linha (RLS)** do PostgreSQL.

Vamos construir isso em **19 passos**, mais seções de produção, problemas comuns e como subir para o GitHub.

### Um mapa mental antes de começar

Alguns termos vão se repetir. Guarde estas ideias soltas — vamos aprofundar cada uma no momento certo:

- **Agente**: um "loop" em volta do modelo de IA. O modelo recebe sua pergunta, decide se responde direto ou se chama uma *ferramenta*, lê o resultado da ferramenta e então responde. Quem monta esse loop é o LangChain/LangGraph.
- **Tool (ferramenta)**: uma função Python normal que o agente pode **escolher** chamar. Ex.: "buscar CNPJ".
- **Checkpointer**: o "caderno de memória" do agente. É ele que guarda o histórico da conversa para o agente lembrar da próxima vez.
- **Middleware**: um "porteiro" que fica no meio do caminho e intercepta algo — no nosso caso, erros de ferramentas e a compactação do histórico.

Pronto? Vamos.

---

## 1. Pré-requisitos e instalação

Ambiente assumido neste guia: **Windows**, terminal **PowerShell**, editor **VS Code**, gerenciador de pacotes **`uv`**, banco **PostgreSQL 18** e modelo **OpenAI `gpt-3.5-turbo`**.

### 1.1. Instalar o `uv` (gerenciador de pacotes Python)

O `uv` é um gerenciador moderno e rápido. Ele lê o `pyproject.toml`, baixa as bibliotecas e cria uma pasta `.venv` (ambiente virtual **isolado** para este projeto). No PowerShell:

```powershell
winget install --id=astral-sh.uv -e
```

> **Conceito — ambiente virtual (`.venv`)**: cada projeto Python tem a sua própria "caixa" de bibliotecas, separada do resto do computador. Assim, um projeto não atrapalha o outro. O `uv` cria e gerencia essa caixa para você.

### 1.2. Instalar o PostgreSQL 18

```powershell
winget install --id=PostgreSQL.PostgreSQL.18 -e
```

Durante a instalação (ou depois), você define a **senha do usuário `postgres`** — anote, vamos precisar dela.

**Adicionar o `psql` ao PATH.** O `psql` é o terminal do PostgreSQL. Para chamá-lo de qualquer lugar, adicione a pasta `bin` do Postgres ao PATH do Windows (ex.: `C:\Program Files\PostgreSQL\18\bin`). Você faz isso em *Configurações → Sistema → Sobre → Configurações avançadas do sistema → Variáveis de ambiente → Path → Editar → Novo*.

> **Importante:** depois de mexer no PATH, **feche e reabra o terminal** (o PowerShell só lê o PATH quando abre). Se você não reabrir, o comando `psql` vai continuar "não encontrado".

### 1.3. Criar o banco `agente_ia`

Com o terminal reaberto:

```powershell
psql -U postgres -c "CREATE DATABASE agente_ia;"
```

> **Atenção:** o `psql` vai pedir a **senha do usuário `postgres`** e **não mostra nada enquanto você digita** (nem asteriscos). Isso é normal — a senha é digitada "às cegas". Digite e aperte Enter.

### 1.4. Baixar as dependências com `uv sync`

Dentro da pasta do projeto:

```powershell
uv sync
```

Isso lê a lista de dependências do `pyproject.toml` e cria a `.venv`. As principais bibliotecas do projeto são:

| Pacote | Para que serve |
| --- | --- |
| `langchain`, `langchain-core` | O núcleo do LangChain (agente, mensagens, tools). |
| `langchain-openai` | Conector para os modelos da OpenAI (`gpt-3.5-turbo`). |
| `langgraph` | Monta o "grafo" de execução do agente. |
| `langgraph-checkpoint-postgres` | Salva a memória do agente no PostgreSQL. |
| `psycopg[binary]` | Driver que faz o Python conversar com o PostgreSQL. |
| `python-dotenv` | Lê o arquivo `.env` e carrega os segredos. |
| `requests` | Cliente HTTP para as tools que chamam APIs. |
| `langchain-community` | O `SQLDatabaseToolkit` (consultar o banco em linguagem natural). |
| `fastapi`, `uvicorn` | O webhook (API HTTP). |

> ### ⚠️ AVISO IMPORTANTE — `os error 396` em pastas na nuvem
>
> Se o projeto estiver dentro de uma pasta sincronizada (**OneDrive, Google Drive, Dropbox**), o `uv sync` pode falhar com **`os error 396`**. Isso acontece porque o `uv` tenta usar *hardlinks* (atalhos internos do sistema de arquivos) e a pasta sincronizada não deixa. Soluções, em ordem de preferência:
>
> 1. **Melhor:** mantenha o projeto **fora** de pastas sincronizadas (ex.: `C:\Projetos\Agente_PY_LangChain`).
> 2. Rode com cópia em vez de hardlink: `uv sync --link-mode=copy`.
> 3. Configure de vez: `setx UV_LINK_MODE copy` (depois **reabra o terminal**).

### 1.5. Criar o arquivo `.env` (seus segredos)

O `.env` guarda suas chaves e senhas. Ele **nunca** vai para o GitHub (está no `.gitignore`). Existe um modelo pronto, o `.env.example`. Copie-o:

```powershell
Copy-Item .env.example .env
```

Agora abra o `.env` no VS Code e preencha:

```bash
# OpenAI (modelo gpt-3.5-turbo) — pegue em https://platform.openai.com/api-keys
OPENAI_API_KEY=sua-chave-openai-aqui

# Conexão PRINCIPAL (usuário postgres) — memória, gravação, "master" (ignora RLS)
DATABASE_URL=postgresql://postgres:SUA_SENHA@localhost:5432/agente_ia

# Conexão SÓ-LEITURA (usuário agente_leitura) — usada pelo SQL toolkit; respeita a RLS
DATABASE_URL_RO=postgresql://agente_leitura:senha_leitura@localhost:5432/agente_ia
```

> **Conceito — o formato da URL do banco**: `postgresql://USUARIO:SENHA@HOST:PORTA/BANCO`. Vamos criar o usuário `agente_leitura` mais para frente (Passo 14); por enquanto, deixe a linha `DATABASE_URL_RO` preenchida com um valor qualquer — só vamos precisar dela lá na frente.

As variáveis do **LangSmith** e do **Google Gemini** são opcionais (Passos 12 e futuros).

---

## Como será cada passo

Cada passo abaixo:

1. **Explica o conceito** (o *que* é e *por que* usamos).
2. **Mostra o código relevante** (do arquivo real do projeto — os arquivos são bem comentados linha a linha; aqui focamos no essencial).
3. Diz **o que testar** para ver funcionando.

O arquivo `agente.py` é o resultado FINAL de todos os passos do terminal. Para aprender, imagine que você o construiu aos poucos, começando por um arquivo minúsculo. Para **rodar** o agente a qualquer momento:

```powershell
uv run python agente.py
```

> **Por que `uv run`?** Ele garante que o Python rode **dentro da `.venv`** do projeto (com as bibliotecas certas). Se você rodar só `python agente.py`, pode usar o Python errado, sem as bibliotecas instaladas.

---

## Passo 1 — Agente mínimo (uma pergunta, uma resposta)

**Conceito.** Um agente, no fundo, é o modelo de IA + um loop que sabe usar ferramentas. A função `create_agent` do LangChain monta esse loop para você. Neste primeiro passo, sem ferramentas nem memória, ele é praticamente "só o modelo". Só precisamos da `OPENAI_API_KEY` no `.env`.

**Código.** A espinha dorsal é sempre a mesma:

```python
import os
from dotenv import load_dotenv
from langchain.agents import create_agent

load_dotenv()  # lê o .env e joga as variáveis para dentro do os.environ

system_prompt = (
    "Você é um assistente prestativo que responde em português do Brasil."
)

agente = create_agent(
    model="openai:gpt-3.5-turbo",
    tools=[],
    system_prompt=system_prompt,
)

resultado = agente.invoke(
    {"messages": [{"role": "user", "content": "Olá, quem é você?"}]}
)
print(resultado["messages"][-1].content)
```

Três conceitos nascem aqui:

- **`system_prompt`**: a "personalidade" e as instruções fixas do agente. É a primeira coisa que o modelo lê, antes de qualquer pergunta do usuário. Definimos que ele responde em português.
- **O formato das mensagens**: o agente recebe um dicionário `{"messages": [ ... ]}`. Cada mensagem é `{"role": "...", "content": "..."}`. O `role` diz *quem falou* (`"user"` = você; `"assistant"` = o agente; `"system"` = instruções). O `content` é o texto.
- **Onde está a resposta**: `agente.invoke(...)` devolve um dicionário com a **lista completa** de mensagens da conversa. A resposta do agente é sempre a **última** da lista: `resultado["messages"][-1].content` (o `[-1]` pega o último item; `.content` pega o texto).

**O que testar.** Rode `uv run python agente.py`. Ele deve imprimir uma apresentação em português.

---

## Passo 2 — Loop de conversa (bate-papo no terminal)

**Conceito.** Um `invoke` único responde uma vez e sai. Para conversar de verdade, colocamos tudo dentro de um laço `while True` que fica lendo o que você digita, até você pedir para sair.

**Código.**

```python
print("Agente pronto! Digite sua mensagem. Para sair, digite: sair\n")

while True:
    pergunta = input("Você: ")
    if pergunta.strip().lower() == "sair":
        print("Até logo!")
        break
    resultado = agente.invoke(
        {"messages": [{"role": "user", "content": pergunta}]}
    )
    resposta = resultado["messages"][-1].content
    print("Agente:", resposta, "\n")
```

- `input("Você: ")` espera você digitar e apertar Enter.
- `if pergunta ... == "sair": break` sai do laço de forma limpa. **Saia sempre digitando `sair`** — evite fechar com `Ctrl+C` no meio de uma resposta (mais tarde explicamos por que isso pode "machucar" a conversa).

**O que testar.** Converse: mande duas ou três perguntas seguidas. Note um detalhe importante: **neste passo o agente ainda NÃO tem memória**. Cada `invoke` é independente — se você disser seu nome e depois perguntar "qual é o meu nome?", ele não sabe. Vamos resolver isso agora.

---

## Passo 3 — Memória na RAM (InMemorySaver)

**Conceito — checkpointer.** Um **checkpointer** é o "caderno de memória" do agente: depois de cada resposta, ele **salva o estado da conversa** (todas as mensagens). Na próxima pergunta, o agente lê esse caderno e continua de onde parou. O `InMemorySaver` guarda esse caderno na **memória RAM** do programa.

**Conceito — `thread_id`.** Se o mesmo programa atende várias conversas, como o checkpointer sabe qual caderno abrir? Pelo **`thread_id`** — um identificador da conversa. Passamos ele dentro de um `config`:

```python
config = {"configurable": {"thread_id": "renan"}}
```

**Código.**

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()

agente = create_agent(
    model="openai:gpt-3.5-turbo",
    tools=[],
    system_prompt=system_prompt,
    checkpointer=checkpointer,   # <- agora o agente tem memória
)

config = {"configurable": {"thread_id": "renan"}}

# dentro do while, passe o config em TODA chamada:
resultado = agente.invoke(
    {"messages": [{"role": "user", "content": pergunta}]},
    config,   # <- o mesmo thread_id => a mesma conversa
)
```

Repare: com o checkpointer, você **não** precisa mais reenviar o histórico à mão. Basta mandar a mensagem nova e o **mesmo `config`**; o checkpointer junta com o que já estava salvo.

**O que testar — o teste do nome.**

1. Rode o agente, diga: *"Meu nome é Renan."*
2. Pergunte: *"Qual é o meu nome?"* → ele responde **"Renan"** ✅ (lembrou, porque estamos na mesma sessão).
3. Digite `sair`, rode de novo e pergunte de novo *"Qual é o meu nome?"* → ele **NÃO sabe** ❌.

Por quê esqueceu ao reabrir? Porque o `InMemorySaver` guarda tudo na **RAM**, e a RAM é apagada quando o programa fecha. Para a memória sobreviver ao fechar/reabrir, precisamos gravar em disco — no PostgreSQL. É o próximo passo.

---

## Passo 4 — Memória PERSISTENTE (PostgresSaver)

**Conceito.** Trocamos o `InMemorySaver` (RAM) pelo `PostgresSaver`, que salva o caderno de memória **no banco PostgreSQL**. Agora a memória é **persistente**: fecha o programa, reabre, e o agente continua lembrando.

Duas novidades importantes:

- **O bloco `with`**: o `PostgresSaver` precisa **abrir** e depois **fechar** a conexão com o banco de forma organizada. O Python faz isso com o `with`: tudo que estiver **dentro** do `with` tem a conexão viva; ao sair do bloco, ela é fechada automaticamente. **Regra de ouro: tudo que usa o checkpointer fica DENTRO do `with`** (a criação do agente, o loop de conversa — tudo).
- **`checkpointer.setup()`**: na primeira vez, o PostgresSaver precisa criar as tabelas dele no banco (tabelas com nomes como `checkpoints`). O `setup()` faz isso. Pode chamar sempre — se já existir, ele não recria.

**Código.**

```python
import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
    checkpointer.setup()   # cria as tabelas do checkpointer (1ª vez)

    agente = create_agent(
        model="openai:gpt-3.5-turbo",
        tools=[],
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": "renan"}}

    while True:
        pergunta = input("Você: ")
        if pergunta.strip().lower() == "sair":
            break
        resultado = agente.invoke(
            {"messages": [{"role": "user", "content": pergunta}]},
            config,
        )
        print("Agente:", resultado["messages"][-1].content, "\n")
```

**O que testar — o teste do nome, agora de verdade.** Diga seu nome, digite `sair`, **rode de novo** e pergunte "qual é o meu nome?". Agora ele **lembra** mesmo depois de fechar e reabrir. 🎉 A memória está no banco.

---

## Passo 5 — Histórico legível (tabelas próprias)

**Conceito — por que criar nossas próprias tabelas?** O checkpointer salva tudo, mas no formato **interno** dele: colunas `jsonb` (JSON binário) que são praticamente **ilegíveis** para um humano. Se você quiser abrir o banco e **ler a conversa em texto limpo** ("quem falou o quê e quando"), precisa de tabelas suas, simples.

Criamos duas tabelas principais (e mais duas que usaremos adiante). Rode o arquivo `sql/01_criar_tabelas.sql` uma vez, conectado ao `agente_ia`:

```sql
CREATE TABLE IF NOT EXISTS conversas (
    id SERIAL PRIMARY KEY,
    thread_id TEXT UNIQUE NOT NULL,    -- código da conversa; UNIQUE = não repete
    owner TEXT,                        -- dono da conversa (identidade do usuário)
    criada_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mensagens (
    id SERIAL PRIMARY KEY,
    conversa_id INTEGER NOT NULL REFERENCES conversas(id),  -- chave estrangeira
    papel TEXT NOT NULL,               -- 'user' ou 'assistant'
    conteudo TEXT NOT NULL,
    owner TEXT,
    criada_em TIMESTAMP DEFAULT NOW()
);
```

> **Conceito — chave estrangeira (`REFERENCES`)**: `conversa_id INTEGER ... REFERENCES conversas(id)` diz que cada mensagem **pertence** a uma conversa existente. É o elo entre as duas tabelas: uma conversa tem **muitas** mensagens; cada mensagem aponta para **uma** conversa. O banco garante que você não crie uma mensagem "órfã" (apontando para uma conversa que não existe).

**Rodando o SQL.** Duas formas:

```powershell
# via psql
psql -U postgres -d agente_ia -f sql/01_criar_tabelas.sql
```

Ou no **pgAdmin**: clique com o botão direito no banco **`agente_ia`** → *Query Tool* → cole o conteúdo → Execute (F5). (Atenção: abra o Query Tool **no banco certo**, `agente_ia`, não no `postgres`.)

**As funções que salvam o histórico.** Em `agente.py`:

```python
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
```

Três conceitos de SQL/segurança aqui:

- **`RETURNING id`**: quando fazemos um `INSERT`, o banco cria uma linha com um `id` novo. O `RETURNING id` pede ao banco para **devolver esse id** na hora — assim já sabemos o número da conversa recém-criada.
- **`ON CONFLICT (thread_id) DO NOTHING`**: como `thread_id` é `UNIQUE`, tentar inserir uma conversa que já existe daria erro. O `ON CONFLICT ... DO NOTHING` diz: "se já existir, não faça nada" (não quebra). Aí o código busca o `id` que já estava lá.
- **`%s` (query parametrizada) — NUNCA use f-string!** Repare que passamos os valores **separados**, como `(thread_id, owner)`, e usamos `%s` no texto do SQL. O driver junta tudo com segurança. Se você montasse a query com f-string (`f"... VALUES ('{thread_id}')"`), um valor malicioso poderia **injetar SQL** e, por exemplo, apagar tabelas. Isso se chama **SQL injection**. Usar `%s` é a defesa: **texto do SQL e dados andam sempre separados**.

No `while`, salvamos cada pergunta e cada resposta:

```python
salvar_mensagem(conn, conversa_id, "user", pergunta, owner=login)
resultado = agente.invoke({"messages": [{"role": "user", "content": pergunta}]}, config)
resposta = resultado["messages"][-1].content
salvar_mensagem(conn, conversa_id, "assistant", resposta, owner=login)
```

**O que testar — ver o histórico com um JOIN.** Rode `sql/consultar_conversas.sql` no pgAdmin (banco `agente_ia`):

```sql
SELECT
    c.thread_id AS conversa,
    m.papel     AS quem_falou,
    m.conteudo  AS mensagem,
    m.criada_em AS quando
FROM mensagens AS m
JOIN conversas AS c ON m.conversa_id = c.id
ORDER BY m.criada_em ASC;
```

> **Conceito — JOIN**: as mensagens guardam só o `conversa_id` (um número). Para ver o `thread_id` legível da conversa, **juntamos** as duas tabelas pelo elo `m.conversa_id = c.id`. O `JOIN` é isso: costurar duas tabelas por uma coluna em comum. Você deve ver suas conversas em texto limpo.

---

## Passo 6 — A primeira tool (buscar CNPJ)

**Conceito — o que é uma tool.** Uma *tool* é uma função Python que você **entrega ao agente** e ele pode **decidir** chamar quando fizer sentido. Você não chama a função no código; **o modelo decide** chamá-la lendo a descrição dela. Ex.: o usuário manda um CNPJ; o agente percebe "isto é uma tarefa para a ferramenta `buscar_cnpj`", chama a tool, lê o resultado e responde.

**A anatomia de uma tool — 3 camadas.** Em `tools/cnpj.py`, seguimos sempre o padrão **schema → service → `@tool`**:

**1) Schema (Pydantic)** — descreve e valida os dados de entrada:

```python
from pydantic import BaseModel, Field, field_validator

class CNPJInput(BaseModel):
    cnpj: str = Field(..., description="CNPJ da empresa (14 dígitos; pode vir com pontos/barra/traço)")

    @field_validator("cnpj")
    @classmethod
    def limpar_cnpj(cls, v):
        digitos = "".join(c for c in v if c.isdigit())
        if len(digitos) != 14:
            raise ValueError("O CNPJ deve conter 14 dígitos.")
        return digitos
```

> **Conceito — Pydantic e o `schema`**: o Pydantic descreve **qual é a entrada** da tool (aqui, um campo `cnpj` que é texto). O `description` do `Field` **ajuda o modelo a preencher certo**. O `field_validator` limpa a entrada (tira pontos e barras) e garante 14 dígitos **antes** de chamar a API.

**2) Service** — a lógica pura (sem LangChain), que vamos ver completa no Passo 10 (com fallback).

**3) A função com `@tool`** — o que o agente enxerga:

```python
from langchain_core.tools import tool

@tool("buscar_cnpj", args_schema=CNPJInput)
def buscar_cnpj(cnpj):
    """Busca os dados cadastrais de uma empresa brasileira pelo CNPJ: razão social,
    nome fantasia, situação, cidade/UF e atividade principal. Use sempre que o
    usuário informar um CNPJ e quiser saber de qual empresa se trata."""
    d = buscar_cnpj_service(cnpj)
    return (
        f"CNPJ {d.get('cnpj', cnpj)}: {d.get('razao_social')} "
        f"(nome fantasia: {d.get('nome_fantasia') or '—'}). "
        f"Situação: {d.get('descricao_situacao_cadastral')}. "
        f"Local: {d.get('municipio')}-{d.get('uf')}. "
        f"Atividade: {d.get('cnae_fiscal_descricao')}."
    )
```

Dois pontos **cruciais**:

- **A docstring é decisiva.** Aquele texto entre `"""..."""` **não é comentário decorativo** — é o que o modelo lê para **decidir se e quando** chamar a tool. Escreva-a bem: diga o que a tool faz e *quando* usá-la. Docstring vaga = agente que não sabe quando chamar.
- **`args_schema=CNPJInput` LIGA o schema à tool.** É isso que conecta a validação Pydantic (a 1ª camada) à função. O `"buscar_cnpj"` é o nome pelo qual o agente chama a tool.

**Boas práticas de `requests` (a lição real).** A tool chama a **BrasilAPI**. Uma pegadinha real deste projeto: a URL **precisa do `/api/`**:

```
✅ certo:   https://brasilapi.com.br/api/cnpj/v1/{cnpj}
❌ errado:  https://brasilapi.com.br/cnpj/v1/{cnpj}   -> devolve HTML, não JSON!
```

Sem o `/api/`, o servidor devolve uma **página HTML** em vez de JSON, e o código quebra ao tentar ler como JSON. **Lição: teste a URL no navegador antes** — se aparecer JSON, ok; se aparecer uma página, a URL está errada. Além disso, ao chamar APIs, sempre use **timeout** (não esperar para sempre), **cheque o status HTTP** e **leia o JSON com segurança** — é o que faremos no `_shared.py` (Passo 9).

**O que testar.** Adicione a tool ao agente (`tools=[buscar_cnpj]`) e pergunte: *"Que empresa é o CNPJ 00.000.000/0001-91?"*. O agente deve chamar a tool e responder com a razão social.

---

## Passo 7 — Organizar as tools num pacote (`tools/`)

**Conceito.** Conforme as tools crescem, colocar tudo em um arquivo vira bagunça. Criamos um **pacote** `tools/` (uma pasta com um arquivo `__init__.py`). O `__init__.py` é a **"vitrine"** do pacote: ele reúne todas as tools numa lista central chamada `TOOLS`.

**Código — `tools/__init__.py`:**

```python
from .cnpj import buscar_cnpj
from .cep import buscar_cep
from .error_handling import tratar_erros_de_tool

TOOLS = [
    buscar_cnpj,
    buscar_cep,
]

__all__ = ["TOOLS", "tratar_erros_de_tool"]
```

No `agente.py`, importamos a lista pronta e a "espalhamos" com `*TOOLS`:

```python
from tools import TOOLS, tratar_erros_de_tool

agente = create_agent(
    model="openai:gpt-3.5-turbo",
    tools=[*TOOLS, *sql_tools],   # o *TOOLS "desempacota" a lista aqui
    ...
)
```

> **Conceito — o `*` (desempacotar lista)**: `tools=[*TOOLS, *sql_tools]` coloca **todos os itens** de `TOOLS` e de `sql_tools` dentro da lista. É como despejar dois saquinhos numa caixa só.

**A lição.** Para adicionar uma nova tool, você **mexe só no pacote `tools/`** (cria o arquivo da tool e a inclui na lista `TOOLS`). O `agente.py` continua com `tools=[*TOOLS, *sql_tools]` — **não muda nada**. Isso é organização: o "registro central" fica num lugar só.

---

## Passo 8 — Tratamento de erro central (middleware)

**Conceito — middleware.** Um **middleware** é um "porteiro" que se coloca **no meio do caminho** entre o agente e a execução de uma tool. Ele pode observar e intervir. Aqui, usamos um middleware para **capturar erros** de qualquer tool.

**Por que precisamos disso?** Tools chamam a internet (APIs), e a internet falha: a API pode cair, dar timeout, retornar `429 Too Many Requests`... Sem tratamento, uma tool que levanta uma exceção **derruba o programa inteiro**. Com o middleware, a falha vira uma **`ToolMessage` amigável**: o agente **lê** essa mensagem de erro e responde ao usuário com jeito ("não consegui consultar agora, tente de novo").

**Código — `tools/error_handling.py`:**

```python
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage

@wrap_tool_call
def tratar_erros_de_tool(request, handler):
    """Se uma tool falhar, devolve mensagem amigável em vez de derrubar o programa."""
    try:
        return handler(request)          # tenta rodar a tool normalmente
    except Exception as e:
        return ToolMessage(
            content=f"A ferramenta falhou: {e}",
            tool_call_id=request.tool_call["id"],   # amarra a resposta ao pedido certo
        )
```

- `@wrap_tool_call` transforma a função num middleware que **envolve** toda chamada de tool.
- `handler(request)` é a execução real da tool. Colocamos num `try/except`: se der certo, devolvemos o resultado; se der erro, devolvemos uma `ToolMessage`.
- `tool_call_id=request.tool_call["id"]` **amarra** a resposta ao pedido certo (o agente sabe qual chamada de tool aquela resposta responde).

Para ativar, entregamos o middleware ao agente:

```python
agente = create_agent(
    ...,
    middleware=[tratar_erros_de_tool, memoria_middleware],
)
```

**O que testar.** Force um erro (ex.: um CNPJ que não existe, ou desligue a internet) e mande a pergunta. Sem o middleware, o programa quebraria; com ele, o agente responde educadamente.

---

## Passo 9 — Segunda tool (CEP) e o princípio DRY (`_shared.py`)

**Conceito.** Vamos criar a segunda tool, `buscar_cep` (endereço a partir do CEP, via **ViaCEP**). Ao criá-la, percebemos que a lógica de **chamar HTTP com timeout, checar status e ler JSON** seria **copiada** do `cnpj.py`. Código repetido é ruim (se você corrige um bug, tem que lembrar de corrigir nos dois lugares). O princípio **DRY** ("Don't Repeat Yourself" — não se repita) diz: escreva essa lógica **uma vez** e reutilize.

**A infraestrutura compartilhada — `tools/_shared.py`:**

```python
import requests

class ToolAPIError(Exception):
    pass

def http_get_json(url, timeout=10):
    """Faz um GET e devolve o JSON — com timeout, checagem de status e leitura
    segura. Levanta ToolAPIError com mensagem clara em qualquer falha."""
    try:
        resp = requests.get(url, timeout=timeout)   # nunca esperar para sempre
    except requests.Timeout:
        raise ToolAPIError(f"O serviço demorou demais para responder ({url}).")
    except requests.RequestException as e:
        raise ToolAPIError(f"Falha de rede ao acessar o serviço: {e}")
    if resp.status_code != 200:
        raise ToolAPIError(f"O serviço respondeu com status HTTP {resp.status_code}.")
    try:
        return resp.json()
    except ValueError:
        raise ToolAPIError("A resposta não veio em JSON válido.")
```

> **Conceito — exceção própria (`ToolAPIError`)**: criar uma classe de erro (herdando de `Exception`) deixa claro que é um "erro esperado de tool" (API fora do ar, etc.), diferente de um bug qualquer. Assim, o `cnpj.py` pode capturar **só** esse tipo e decidir o que fazer (ex.: tentar outra fonte).

**A tool de CEP — `tools/cep.py`** (agora enxuta, usando o `_shared`):

```python
from pydantic import BaseModel, Field, field_validator
from langchain_core.tools import tool
from ._shared import http_get_json, ToolAPIError

class CEPInput(BaseModel):
    cep: str = Field(..., description="CEP com 8 dígitos (pode vir com traço, ex.: 01001-000)")

    @field_validator("cep")
    @classmethod
    def limpar_cep(cls, v):
        digitos = "".join(c for c in v if c.isdigit())
        if len(digitos) != 8:
            raise ValueError("O CEP deve conter 8 dígitos.")
        return digitos

def buscar_cep_service(cep):
    url = f"https://viacep.com.br/ws/{cep}/json/"
    dados = http_get_json(url)
    # Quirk do ViaCEP: responde 200 com {"erro": true} quando NÃO acha o CEP.
    if dados.get("erro"):
        raise ToolAPIError(f"CEP {cep} não encontrado.")
    return dados

@tool("buscar_cep", args_schema=CEPInput)
def buscar_cep(cep):
    """Busca o endereço (rua, bairro, cidade, estado) de um CEP brasileiro.
    Use quando o usuário informar um CEP e quiser saber o endereço."""
    d = buscar_cep_service(cep)
    return (
        f"CEP {d.get('cep')}: {d.get('logradouro')}, {d.get('bairro')}, "
        f"{d.get('localidade')}-{d.get('uf')}."
    )
```

> **O "quirk" do ViaCEP:** ao contrário de outras APIs, o ViaCEP responde **`200 OK`** (sucesso!) mesmo quando o CEP não existe — só que o JSON vem `{"erro": true}`. Por isso a checagem de status HTTP no `_shared` **não basta** aqui; a lógica **específica** do ViaCEP (`if dados.get("erro")`) fica na tool, não no compartilhado. Cada API tem suas manias; trate-as onde elas importam.

E o `cnpj.py` também fica enxuto reaproveitando `http_get_json` (veja o service completo no próximo passo). **Lição do DRY:** a parte comum (HTTP) mora no `_shared.py`; a parte específica de cada API mora na tool.

**O que testar.** Adicione `buscar_cep` à lista `TOOLS` e pergunte: *"Qual o endereço do CEP 01001-000?"*.

---

## Passo 10 — Fallback entre APIs (resiliência do CNPJ)

**Conceito — fallback.** APIs gratuitas às vezes ficam sobrecarregadas e respondem `429 Too Many Requests`. Para o agente não ficar "na mão", usamos um **fallback**: se a fonte principal falhar, tentamos uma **segunda fonte** que devolve os **mesmos campos**. Isso é **resiliência**: continuar funcionando mesmo quando uma parte falha.

**Código — o service em `tools/cnpj.py`:**

```python
from ._shared import http_get_json, ToolAPIError

def buscar_cnpj_service(cnpj):
    """Tenta várias fontes em ordem. Se a 1ª falhar (ex.: 429), tenta a próxima.
    As duas devolvem os MESMOS campos, então o resto do código não muda."""
    fontes = [
        f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}",   # 1ª tentativa
        f"https://minhareceita.org/{cnpj}",               # fallback (mesmo formato)
    ]
    ultimo_erro = None
    for url in fontes:
        try:
            return http_get_json(url)         # deu certo -> retorna e para
        except ToolAPIError as e:
            ultimo_erro = e                   # falhou -> guarda e tenta a próxima
    raise ToolAPIError(f"Nenhuma fonte de CNPJ respondeu. Último erro: {ultimo_erro}")
```

A lógica é um laço: percorre a lista de fontes; na primeira que responder, retorna e para; se **todas** falharem, aí sim desiste, informando o último erro (que o middleware do Passo 8 transforma em resposta amigável).

**O que testar.** Difícil forçar o `429` de propósito, mas você pode simular trocando a 1ª URL por uma inválida e conferir que ele cai para a `minhareceita.org` e ainda responde.

---

## Passo 11 — Tool de SQL (consultar o banco em linguagem natural)

**Conceito.** Até aqui, nossas tools chamam APIs externas. Agora vamos dar ao agente a capacidade de **consultar o próprio banco em linguagem natural**: o usuário pergunta "quantas conversas existem?" e o agente **escreve e executa o SQL sozinho**. Usamos o **`SQLDatabaseToolkit`** do `langchain-community`, que entrega **4 tools** de uma vez:

- `sql_db_list_tables` — lista as tabelas.
- `sql_db_schema` — mostra as colunas de uma tabela.
- `sql_db_query_checker` — revisa a query antes de rodar.
- `sql_db_query` — **executa** a query.

Por isso o `system_prompt` orienta o agente a seguir a ordem certa: **listar tabelas → ver o schema → escrever e rodar a query**.

**Código — `tools/sql.py`:**

```python
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit

def criar_tools_sql(database_url, modelo, app_usuario=None):
    uri = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine_args = {}
    banco = SQLDatabase.from_uri(uri, engine_args=engine_args)
    toolkit = SQLDatabaseToolkit(db=banco, llm=modelo)
    return toolkit.get_tools()
```

E no `agente.py`, note que o toolkit precisa de um **objeto de modelo**, não da string:

```python
from langchain.chat_models import init_chat_model

modelo_obj = init_chat_model("openai:gpt-3.5-turbo")   # OBJETO, não a string
sql_tools = criar_tools_sql(DATABASE_URL_RO, modelo_obj)
```

Três armadilhas reais deste passo:

- **Precisa de um OBJETO de modelo.** Em `create_agent(model="openai:gpt-3.5-turbo")` usamos a **string**. Mas o `SQLDatabaseToolkit` quer um **objeto** de modelo — por isso criamos `modelo_obj = init_chat_model(...)` e passamos ele.
- **⚠️ Pegadinha do driver — troque `postgresql://` por `postgresql+psycopg://`.** Por baixo, o toolkit usa SQLAlchemy, que por padrão procura o driver antigo `psycopg2`. Nós instalamos o `psycopg` (versão 3), não o `psycopg2`. A linha `uri = database_url.replace("postgresql://", "postgresql+psycopg://", 1)` diz ao SQLAlchemy: "use o driver `psycopg` v3". Sem isso, dá erro de driver não encontrado.
- **⚠️ Aviso de segurança.** A tool `sql_db_query` executa **qualquer SQL** — inclusive `DELETE` e `DROP`. Não há um "modo só-leitura" nativo aqui. Se o modelo, por engano ou por um pedido malicioso, gerar um `DROP TABLE`, ele roda. Vamos **blindar** isso no Passo 14 (usuário só-leitura) e no Passo 17 (RLS).

> **Nota:** o `langchain-community` está em fase de *sunset* (aposentadoria) e mostra um `DeprecationWarning` ao importar. **Ele ainda funciona** normalmente; é só um aviso.

**O que testar.** Pergunte: *"Quantas conversas existem no banco?"* ou *"Liste as últimas 5 mensagens."*. Observe (nos logs ou no LangSmith) o agente chamando as 4 tools em sequência.

---

## Passo 12 — LangSmith (observabilidade, zero código)

**Conceito — observabilidade.** Quando o agente faz várias coisas por baixo (chama tools, escreve SQL, resume histórico), fica difícil enxergar o que aconteceu. O **LangSmith** é um painel que **grava cada execução** (um *trace*) para você inspecionar. O melhor: **não precisa mexer no código** — basta preencher variáveis no `.env`.

**Código — nada!** Só o `.env`:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=sua-chave-langsmith-aqui
LANGSMITH_PROJECT=agente-py-langchain
```

Com isso, o LangChain envia os traces para [smith.langchain.com](https://smith.langchain.com/).

**Como ler um trace.** Abra o projeto no painel e clique numa execução. Você verá a **sequência** de passos, tipicamente: **AI** (o modelo decide chamar uma tool) → **TOOL** (a tool roda e devolve um resultado) → **AI** (o modelo lê o resultado e responde). Para cada passo você vê **inputs**, **outputs** e o **consumo de tokens** — ótimo para entender e depurar.

> **Lembrete de segurança:** a `LANGSMITH_API_KEY` é um segredo. Ela mora **só no `.env`** (que está no `.gitignore`). **Nunca** a coloque em `print(...)` nem a envie para lugar nenhum.

---

## Passo 13 — Sumarização (economizar tokens com resumo)

**Conceito — janela de contexto e tokens.** O modelo só "enxerga" uma quantidade limitada de texto de cada vez — a **janela de contexto** — medida em **tokens** (pedaços de palavras). Conversas longas estouram essa janela e **custam mais** (você paga por token). A **sumarização** resolve isso: quando o histórico fica grande, um middleware **resume as mensagens antigas** num parágrafo e descarta o detalhe, mantendo só as mensagens recentes.

**Código — `SummarizationMiddleware` em `agente.py`:**

```python
from langchain.agents.middleware import SummarizationMiddleware

memoria_middleware = SummarizationMiddleware(
    model="openai:gpt-3.5-turbo",     # o modelo que ESCREVE o resumo
    trigger=("tokens", 2000),         # QUANDO resumir: ao passar de 2000 tokens
    # keep=("messages", 2),           # QUANTO manter depois de resumir
)

agente = create_agent(
    ...,
    middleware=[tratar_erros_de_tool, memoria_middleware],
)
```

### `trigger` × `keep` — leia com atenção (é onde todo mundo tropeça)

- **`trigger` = QUANDO resumir.** Pode ser por tokens `("tokens", 2000)` ou por número de mensagens `("messages", 6)`. Quando o histórico passa desse limite, a sumarização dispara.
- **`keep` = QUANTO manter depois de resumir.** Depois de resumir, ele **descarta as antigas** e **mantém as N mais recentes** intactas. O **padrão do `keep` é 20 mensagens**.

A regra de ouro: **o `keep` tem que ser MENOR que o `trigger`.** Pense assim — se o gatilho dispara quando há, digamos, o equivalente a 6 mensagens, mas você mandou manter as últimas 20, então **não há nada para descartar** (você quer manter mais do que tem). O resultado: **dispara, mas não compacta nada**. É a causa nº 1 de "liguei a sumarização e não vejo resumo nenhum". Por isso, com `trigger=("messages", 6)`, use algo como `keep=("messages", 2)`.

### Como VER o resumo gerado

Duas formas:

1. **No LangSmith**: o trace mostra o passo de sumarização.
2. **Numa tabela `resumos`**: no `agente.py`, depois de cada resposta, procuramos entre as mensagens do estado aquela que **começa** com o prefixo padrão do resumo e a salvamos:

```python
PREFIXO = "Here is a summary of the conversation to date:"
for msg in resultado["messages"]:
    conteudo = msg.content
    if isinstance(conteudo, str) and conteudo.startswith(PREFIXO):
        salvar_resumo(conn, thread_id, getattr(msg, "id", None), conteudo)
```

A função `salvar_resumo` grava na tabela `resumos` (criada no `sql/01`), com `ON CONFLICT (mensagem_id) DO NOTHING` para não duplicar o mesmo resumo.

**O que testar.** Baixe o `trigger` (ex.: `("messages", 6)` com `keep=("messages", 2)`), converse bastante e depois rode `SELECT thread_id, resumo FROM resumos;` no pgAdmin para ver o resumo salvo.

---

## Passo 14 — Usuário PostgreSQL só-leitura (blindar o SQL)

**Conceito.** Lembra do aviso do Passo 11? A tool `sql_db_query` roda qualquer SQL, inclusive `DELETE`/`DROP`. A defesa **mais forte** não é no código (o modelo escreve SQL livre e pode driblar), e sim **no banco**: criamos um usuário PostgreSQL que **só tem permissão de LER** (`SELECT`). Assim, mesmo que o modelo gere um `DROP TABLE`, o banco **recusa** — porque aquele usuário simplesmente não tem esse poder.

**Código — `sql/02_usuario_leitura.sql`** (rode como `postgres`; troque a senha):

```sql
CREATE USER agente_leitura WITH PASSWORD 'senha_leitura';

GRANT CONNECT ON DATABASE agente_ia TO agente_leitura;
GRANT USAGE ON SCHEMA public TO agente_leitura;

-- concede APENAS SELECT nas tabelas atuais...
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agente_leitura;
-- ...e também nas tabelas FUTURAS
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agente_leitura;
```

Depois, aponte a `DATABASE_URL_RO` do `.env` para esse usuário:

```bash
DATABASE_URL_RO=postgresql://agente_leitura:senha_leitura@localhost:5432/agente_ia
```

E faça o SQL toolkit usar essa conexão só-leitura (no `agente.py` já está assim):

```python
sql_tools = criar_tools_sql(DATABASE_URL_RO, modelo_obj)   # <- usa o usuário só-leitura
```

Repare na divisão: a `DATABASE_URL` (usuário `postgres`) fica para **gravar** o histórico e para a **memória** (checkpointer); a `DATABASE_URL_RO` (usuário `agente_leitura`) fica para as **consultas** do agente. **O poder de escrever nunca chega às mãos do modelo.**

**O que testar.** Peça ao agente para "apagar a tabela mensagens". Ele pode até tentar gerar o SQL, mas o banco vai **negar** por falta de permissão — e o middleware de erro devolve a recusa de forma amigável.

---

## Passo 15 — Webhook (FastAPI): a identidade chega junto

Chegamos à versão que roda como serviço HTTP: o `webhook.py`.

**Conceito — a diferença central.** No terminal, **você digita quem é** (o `login`). Num webhook conectado a um canal (WhatsApp, chat do site, etc.), a **identidade chega dentro da requisição** — no campo `de` — enviada pela plataforma. O usuário não digita "eu sou fulano"; a **plataforma** já diz quem é.

> **Conceito — identificação × autenticação (seja honesto com isto):**
> - **Identificação** = "quem você diz ser". No terminal, você digita seu login — isso **não prova nada**; serve só para desenvolvimento.
> - **Autenticação** = "provar que é você mesmo" (senha, token, assinatura).
> - No webhook, a identidade no campo `de` vem **validada pela plataforma** (ela já autenticou o usuário no canal dela). Mas o **seu** webhook ainda precisa **verificar a ASSINATURA** da requisição para ter certeza de que ela veio mesmo da plataforma, e não de um impostor. Essa verificação de assinatura é uma etapa externa (depende da plataforma) — no código ela aparece como um lembrete (`# PRODUÇÃO: verifique a ASSINATURA...`).

**Conceito — montagem ÚNICA na subida.** No terminal, montamos o agente uma vez e conversamos num loop. No webhook, o servidor sobe **uma vez** e depois atende **muitas requisições**. Então preparamos o que é comum (conexão, checkpointer, objeto de modelo) **na subida do servidor**:

```python
conn = psycopg.connect(DATABASE_URL)               # grava com postgres (ignora RLS)

_cm = PostgresSaver.from_conn_string(DATABASE_URL)
checkpointer = _cm.__enter__()
checkpointer.setup()

modelo_obj = init_chat_model("openai:gpt-3.5-turbo")
```

E definimos a API com FastAPI:

```python
from fastapi import FastAPI
from pydantic import BaseModel

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
    ...
    resultado = agente.invoke({"messages": [{"role": "user", "content": msg.texto}]}, config)
    resposta = resultado["messages"][-1].content
    return {"de": identidade, "is_master": is_master, "resposta": resposta}
```

> **Conceito — o `BaseModel` da requisição**: a classe `Mensagem` diz que toda requisição precisa ter dois campos de texto: `de` (quem enviou) e `texto` (a mensagem). O FastAPI valida isso automaticamente.

**Instalar o FastAPI/uvicorn** (se ainda não estiverem):

```powershell
uv add fastapi uvicorn
```

> **Conceito — dependência é por projeto.** Cada projeto tem a sua própria `.venv`. `uv add` instala **neste** projeto. Outro projeto teria a própria caixa de bibliotecas, independente.

**Como rodar e testar.**

```powershell
uv run uvicorn webhook:app --reload
```

- `webhook:app` = no arquivo `webhook.py`, use a variável `app`.
- `--reload` = reinicia sozinho quando você salva o arquivo (bom para desenvolvimento).

Abra no navegador: **http://127.0.0.1:8000/docs**. O FastAPI gera uma página de teste. Clique em **POST /webhook** → *Try it out* → mande um corpo assim:

```json
{ "de": "renan", "texto": "Olá! Quantas conversas existem no banco?" }
```

Você recebe de volta a resposta do agente.

---

## Passo 16 — Tabela de usuários + master

**Conceito.** Precisamos saber **quem é cada usuário** e **quem pode ver tudo** (o "master"). A tabela `usuarios` (do `sql/01`) guarda isso:

```sql
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    login TEXT UNIQUE NOT NULL,        -- identificador (número validado / login)
    nome TEXT,
    is_master BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = vê tudo; FALSE = só o dele
    criado_em TIMESTAMP DEFAULT NOW()
);
```

A função `identificar_usuario` busca o usuário pelo login e, **se ele não existir, cria como NÃO-master** (por segurança — ninguém vira master por acidente):

```python
def identificar_usuario(conn, login):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO usuarios (login) VALUES (%s) ON CONFLICT (login) DO NOTHING",
            (login,),
        )
        cur.execute("SELECT id, login, is_master FROM usuarios WHERE login = %s", (login,))
        linha = cur.fetchone()
    conn.commit()
    return linha   # (id, login, is_master)
```

> Repare o comentário honesto no código: isto **identifica** (pergunta quem é), **não autentica** (não prova). Em produção, aqui entraria uma senha/token.

**Como promover um master** (dar a alguém o poder de ver tudo): rode no banco, trocando o login:

```sql
UPDATE usuarios SET is_master = TRUE WHERE login = 'renan';
```

---

## Passo 17 — Isolamento multi-usuário com `owner` + RLS

**Conceito — o problema.** Com o SQL toolkit, o modelo escreve SQL **livre**. Se o usuário "joão" pedir "liste todas as mensagens", o modelo escreve `SELECT * FROM mensagens` — e isso traria as mensagens de **todos**, inclusive de outros usuários. **Filtrar no código não segura**, porque o modelo pode escrever qualquer query. Precisamos de uma trava **no banco**.

**Conceito — RLS (Row-Level Security, segurança em nível de linha).** É um recurso do PostgreSQL onde cada **linha** tem um "dono" (a coluna `owner`) e uma **política** decide quais linhas cada usuário pode ver. Com a RLS ligada, mesmo um `SELECT * FROM mensagens` **só devolve as linhas do usuário atual** — o próprio banco filtra, invisivelmente. O modelo não tem como escapar disso.

**Código — `sql/03_isolamento_rls.sql`:**

```sql
-- preenche o owner das linhas já existentes
UPDATE conversas SET owner = thread_id WHERE owner IS NULL;

-- liga a RLS
ALTER TABLE conversas ENABLE ROW LEVEL SECURITY;

-- política: só LÊ as linhas cujo owner bate com a variável de sessão app.usuario
DROP POLICY IF EXISTS conversa_do_dono ON conversas;
CREATE POLICY conversa_do_dono ON conversas
    FOR SELECT USING (owner = current_setting('app.usuario', true));
```

(O mesmo é feito para a tabela `mensagens`.) Entendendo:

- **`owner`** = a identidade do dono da linha.
- **`ENABLE ROW LEVEL SECURITY`** = liga a trava naquela tabela.
- **`USING (owner = current_setting('app.usuario', true))`** = a política. `current_setting('app.usuario', true)` lê uma **variável de sessão** chamada `app.usuario` (nós a definimos por conexão — Passo 18). A política só deixa ver as linhas onde `owner` = essa variável.
- O **`true`** em `current_setting(..., true)` faz devolver **NULL** se a variável não estiver setada. Aí a política não casa com ninguém e o usuário vê **NADA** — isso é *fail-closed* (falha fechando, o padrão seguro: na dúvida, não mostra nada).

**Por que RLS e não filtro no código?** Porque o modelo escreve SQL livre; a única trava confiável está **abaixo** dele, no banco.

**O master é "de graça".** Superusuários do PostgreSQL (como o `postgres`) **ignoram a RLS** por natureza. Então: se o agente do master usa a conexão `postgres`, ele vê **tudo** automaticamente, sem precisar de política especial.

**Como gravamos o `owner`.** As funções `garantir_conversa` e `salvar_mensagem` recebem `owner` e o gravam em cada linha — é isso que "carimba" o dono.

**Como TESTAR direto no `psql`** (conectado como o usuário só-leitura):

```sql
-- psql -U agente_leitura -d agente_ia
SELECT count(*) FROM conversas;            -- 0 (sem app.usuario definido -> vê nada)
SET app.usuario = 'renan';
SELECT thread_id, owner FROM conversas;    -- só as linhas do 'renan'
```

E, conectado como `postgres` (master), você vê **todas** (ignora a RLS).

---

## Passo 18 — Ligar a RLS ao agente (o "wiring")

**Conceito.** A RLS filtra pela variável de sessão `app.usuario`. Falta **definir** essa variável na conexão de cada usuário. Fazemos isso na função `criar_tools_sql`, "carimbando" o `app.usuario` na conexão do banco.

**Código — `tools/sql.py`:**

```python
def criar_tools_sql(database_url, modelo, app_usuario=None):
    uri = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine_args = {}
    if app_usuario is not None:
        # SEGURANÇA: só alfanuméricos, para o "de" não injetar options extras na
        # conexão (ex.: "-c outra=coisa"). Número de telefone continua intacto.
        seguro = "".join(c for c in app_usuario if c.isalnum())
        engine_args = {"connect_args": {"options": f"-c app.usuario={seguro}"}}

    banco = SQLDatabase.from_uri(uri, engine_args=engine_args)
    toolkit = SQLDatabaseToolkit(db=banco, llm=modelo)
    return toolkit.get_tools()
```

A cadeia é: `engine_args` → `connect_args` → `options` com `"-c app.usuario=..."`. Isso injeta, **na hora de conectar**, o comando que define a variável de sessão. A partir daí, toda query naquela conexão respeita a política RLS daquele usuário.

> **⚠️ Sanitização (anti-injeção):** `seguro = "".join(c for c in app_usuario if c.isalnum())` mantém **só letras e números**. Sem isso, um `de` malicioso poderia injetar `-c outra=coisa` na string de conexão e mexer em outras configurações. Um número de telefone (formado só por dígitos) passa intacto. **Nunca** confie no valor do `de` sem limpar.

**Como o webhook escolhe a conexão por requisição** (`webhook.py`):

```python
if is_master:
    sql_tools = criar_tools_sql(DATABASE_URL, modelo_obj)                      # vê tudo
else:
    sql_tools = criar_tools_sql(DATABASE_URL_RO, modelo_obj, app_usuario=identidade)  # só o dele
```

- **Master** → usa a conexão `postgres` (`DATABASE_URL`), que **ignora a RLS**: vê tudo.
- **Comum** → usa a conexão só-leitura (`DATABASE_URL_RO`) **com** `app_usuario=identidade`: a RLS filtra e ele vê **só o dele**.

E por isso o agente é montado **por requisição** no webhook (as tools de SQL dependem de quem está perguntando).

**O que testar (o teste que amarra tudo).** Faça a **mesma** pergunta — "liste todas as conversas" — com dois `de` diferentes no `/docs`:

- `{"de": "renan", "texto": "liste todas as conversas"}` (se `renan` for master) → vê **todas**.
- `{"de": "joao", "texto": "liste todas as conversas"}` (comum) → vê **só as do joão**.

Mesma pergunta, respostas diferentes — o banco isolou por usuário. 🔒

---

## Passo 19 — A REGRA DE OURO: nunca fixe o `thread_id`

**Conceito.** O `thread_id` identifica a conversa (a memória), e o `owner` identifica o dono das linhas (a RLS). Ambos devem vir da **identidade real** do usuário:

- No **terminal**: `thread_id = login` e `owner = login` (o login digitado).
- No **webhook**: `thread_id = identidade` e `owner = identidade` (o campo `de`).

```python
# agente.py
login = input("Quem é você (login)? ").strip().lower() or "renan"
thread_id = login                                # cada login = a conversa dele
config = {"configurable": {"thread_id": thread_id}}
conversa_id = garantir_conversa(conn, thread_id, owner=login)   # grava o dono
```

**O perigo de fixar.** Se você deixasse `thread_id = "renan"` **cravado** no código, aconteceriam duas catástrofes:

1. **Todos os usuários cairiam na MESMA conversa** — cada um lendo a memória do outro.
2. O `owner` ficaria errado/vazio, **quebrando a RLS** (as políticas dependem do `owner` correto).

**Regra de ouro:** o `thread_id` e o `owner` **sempre** derivam da identidade (login no terminal / `de` no webhook). Nunca os deixe fixos no código.

---

## Passo 20 — Plugar um MCP (ferramentas externas prontas)

**Conceito — o que é MCP.** Até aqui, cada tool foi **escrita por você** (schema → service → `@tool`). O **MCP (Model Context Protocol)** é um "padrão de tomada": um **servidor externo** já expõe ferramentas prontas (ex.: Google Calendar com "criar evento", "listar eventos"), e o seu agente vira um **cliente** que se conecta e ganha essas ferramentas de graça. É como plugar um pendrive de capacidades.

**Como o LangChain consome MCP.** Pelo pacote `langchain-mcp-adapters`. Instale:

```powershell
uv add langchain-mcp-adapters
```

### ⚠️ Duas coisas que descobrimos testando (e que mudam o código)

1. **As tools de MCP são ASSÍNCRONAS.** Chamar o agente com o `.invoke` síncrono **falha** (`NotImplementedError: StructuredTool does not support sync invocation`). Você **precisa** usar `await agente.ainvoke(...)` — ou seja, o código que usa MCP é `async`.
2. **`uvx`/`npx` em pasta na nuvem** (que baixam o servidor MCP) batem no mesmo **`os error 396`** do `uv sync`. A correção é passar `UV_LINK_MODE=copy` no `env` do servidor MCP.

### O padrão reutilizável — `tools/mcp.py` (um "registro" de servidores)

Assim como o `tools/__init__.py` é o registro das suas tools, o `tools/mcp.py` é o **registro dos servidores MCP**. Para **adicionar um MCP novo**, você acrescenta **uma entrada** no dicionário `MCP_SERVERS`:

```python
# tools/mcp.py (resumo)
import os
from langchain_mcp_adapters.client import MultiServerMCPClient

_ENV = {**os.environ, "UV_LINK_MODE": "copy"}   # evita o os error 396 no subprocesso

MCP_SERVERS = {
    "time": {                                    # servidor de exemplo (hora atual, sem login)
        "command": "uvx", "args": ["mcp-server-time"],
        "transport": "stdio", "env": _ENV,
    },
    # Para ADICIONAR um MCP novo: só mais uma entrada aqui.
}

async def criar_tools_mcp():                     # ASYNC — as tools de MCP são async
    client = MultiServerMCPClient(MCP_SERVERS)
    return await client.get_tools()
```

### O agente com MCP — `demo_mcp.py` (tudo `async`)

```python
import asyncio
from dotenv import load_dotenv
from langchain.agents import create_agent
from tools.mcp import criar_tools_mcp

load_dotenv()

async def main():
    mcp_tools = await criar_tools_mcp()          # pega as tools do MCP
    agente = create_agent(
        model="openai:gpt-3.5-turbo",
        tools=mcp_tools,                         # (num agente real: [*TOOLS, *mcp_tools])
        system_prompt="Você responde em português. Use as ferramentas quando precisar.",
    )
    r = await agente.ainvoke(                    # ainvoke (async), não invoke!
        {"messages": [{"role": "user", "content": "Que horas são agora em São Paulo?"}]}
    )
    print(r["messages"][-1].content)

if __name__ == "__main__":
    asyncio.run(main())                         # roda o async main de forma síncrona
```

Rode com `uv run python demo_mcp.py`. A 1ª execução baixa o servidor MCP (demora um pouco) e depois o agente responde a hora usando a ferramenta do MCP.

### Adicionar o Google Calendar (o exemplo real)

O código já está pronto — é só uma entrada nova no `MCP_SERVERS`. A parte trabalhosa é **externa** (no site do Google, não em Python).

**Entenda o OAuth:** você não dá sua senha do Google ao agente. Você autoriza o app **na tela do Google**, que devolve um **token** com acesso só à sua agenda. Duas peças: o `credentials.json` (identifica o app) e o token (sua permissão, gerada ao autorizar).

1. **Node.js** (para o `npx`): `winget install --id=OpenJS.NodeJS -e` → reabra o terminal → teste `npx --version`.
2. **Google Cloud Console** (https://console.cloud.google.com):
   - Crie um projeto e **ative a Google Calendar API** (APIs e serviços → Biblioteca).
   - **Tela de permissão OAuth** → tipo **Externo** → em **"Usuários de teste"** adicione o **seu e-mail**. ⚠️ Sem isso, dá **erro 403** na autorização.
   - **Credenciais** → Criar → **ID do cliente OAuth** → tipo **"App para computador" (Desktop app)**. ⚠️ **NÃO** "Aplicativo da Web" (que gera a chave `"web"`; o servidor exige a chave `"installed"`). Baixe o JSON.
   - Salve como `C:\Users\voce\google_credentials.json` (**fora** do projeto/Git — é segredo).
3. **Autorize uma vez** (abre o navegador):
   ```powershell
   $env:GOOGLE_OAUTH_CREDENTIALS="C:\Users\voce\google_credentials.json"
   npx @cocal/google-calendar-mcp auth
   ```
   (Se aparecer "app não verificado": **Avançado → Continuar**.)
4. **Descomente** a entrada `google_calendar` no `tools/mcp.py` (Ctrl+/ nas 5 linhas) e ajuste o caminho.

> ⚠️ **Segurança:** o agente passa a **criar/alterar/apagar** eventos (efeitos reais) — comece com uma agenda de teste. `credentials.json` e tokens são **segredo** (fora do Git).

**Padrão para QUALQUER MCP:** instale `langchain-mcp-adapters` → adicione uma entrada em `MCP_SERVERS` → use o agente **assíncrono** (`await agente.ainvoke(...)`). É sempre igual.

---

## Agente síncrono × assíncrono (qual usar?)

O MCP forçou o agente a virar **assíncrono** — vale entender a diferença, porque é uma decisão importante.

- **Síncrono (`agente.invoke`)** — o programa faz **uma coisa de cada vez**, em ordem, e **espera** cada passo terminar antes do próximo. É a fila de banco com um caixa só: simples de ler e depurar.
- **Assíncrono (`await agente.ainvoke`)** — o programa pode **esperar sem travar**: enquanto uma operação de espera (rede, subprocesso) não termina, o "loop de eventos" cuida de outra coisa. É o garçom que, enquanto a cozinha prepara um prato, atende outra mesa.

**Quando usar SÍNCRONO:**
- Scripts simples, terminal de um usuário só.
- Todas as tools são síncronas (CNPJ, CEP, SQL).
- Você quer o código mais **fácil de ler e depurar**. *(Comece sempre aqui.)*

**Quando usar ASSÍNCRONO:**
- Você usa **tools assíncronas** — como as de **MCP** (elas SÓ funcionam com `ainvoke`). É o motivo nº 1 aqui.
- Você precisa de **concorrência real**: um servidor (webhook) atendendo **muitos usuários ao mesmo tempo** sem um travar o outro.
- O trabalho é "de espera" (muita rede/I/O), onde o async aproveita melhor o tempo ocioso.

**A regra deste projeto:** sem MCP → fique no **síncrono** (mais simples). Com MCP → o agente **precisa** ser assíncrono. Não é "async é melhor"; é "async quando a ferramenta ou a escala pedem". O custo do async: **tudo** precisa ter versão async (você verá no Passo 21).

---

## Passo 21 — Conectar o MCP no agente principal (converter para async)

Ligar o MCP no `agente.py` é **convertê-lo para assíncrono**. As mudanças (procure `# [ASYNC]` no arquivo):

1. `import asyncio`.
2. Todo o corpo vira **`async def main()`**.
3. `mcp_tools = await criar_tools_mcp()`.
4. `tools=[*TOOLS, *sql_tools, *mcp_tools]`.
5. Trocar o invoke por **`await agente.ainvoke(...)`**.
6. No fim: `asyncio.run(main())`.

Duas peças precisaram de ajuste especial:

### Checkpointer + o conflito do Windows

O `ainvoke` exige um checkpointer **async**. O async do PostgreSQL (`AsyncPostgresSaver`) exige o `SelectorEventLoop`; os servidores **MCP (subprocessos)** exigem o `ProactorEventLoop` — e **no Windows os dois não convivem** (o Selector não roda subprocessos). Solução: usar o **`InMemorySaver`** (memória do agente em RAM), que funciona no loop padrão.

> A memória **de contexto** do agente some ao reabrir. MAS as tabelas `conversas`/`mensagens`/`resumos` **continuam persistindo**, porque usam a conexão **síncrona** (`psycopg.connect`), sem o conflito. (No Linux/Mac, ou rodando o MCP via HTTP, dá para ter `AsyncPostgresSaver` + MCP com persistência total.)

### Middleware de erro (sync E async)

O atalho `@wrap_tool_call` cria só a versão **síncrona**. Com `ainvoke`, o agente exige também a **assíncrona** (`awrap_tool_call`). Solução: subclassar `AgentMiddleware` com as **duas** versões — assim o mesmo middleware serve o `agente.py` (async) e o `webhook.py` (sync):

```python
class TratarErrosDeTool(AgentMiddleware):
    def wrap_tool_call(self, request, handler):          # síncrona (invoke)
        try: return handler(request)
        except Exception as e: return _mensagem_de_erro(request, e)
    async def awrap_tool_call(self, request, handler):    # assíncrona (ainvoke)
        try: return await handler(request)
        except Exception as e: return _mensagem_de_erro(request, e)

tratar_erros_de_tool = TratarErrosDeTool()
```

Pronto: `uv run python agente.py` sobe o agente com CNPJ + CEP + SQL + **Google Calendar**, tudo junto. Teste: *"marque na minha agenda hoje às 18h uma reunião teste"*.

---

## Produção (para colocar em uso, não só teste)

O código atual é ótimo para **aprender e testar**, mas alguns ajustes são necessários antes de expor o webhook a usuários reais.

### Concorrência e POOL de conexões

**O problema.** No `webhook.py`, abrimos **uma única** conexão (`conn = psycopg.connect(...)`) na subida. Isso funciona para teste sequencial (uma requisição de cada vez). Mas o FastAPI atende **requisições simultâneas** — e uma conexão `psycopg` **não é segura** para uso simultâneo (duas requisições mexendo na mesma conexão ao mesmo tempo se atropelam e dão erro).

**A correção — pool de conexões.** Um **pool** é um "conjunto" de conexões prontas: cada requisição pega uma emprestada, usa e devolve. Assim, requisições simultâneas usam conexões **diferentes**.

```python
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

pool = ConnectionPool(conninfo=DATABASE_URL)   # conjunto de conexões

# o checkpointer aceita um pool:
checkpointer = PostgresSaver(pool)
checkpointer.setup()
```

E, no endpoint, pegue uma conexão do pool para cada requisição:

```python
@app.post("/webhook")
def receber(msg: Mensagem):
    with pool.connection() as conn:      # pega emprestada; devolve ao sair do with
        # ... identificar_usuario, garantir_conversa, salvar_mensagem usando 'conn' ...
        ...
```

### Verificar a assinatura do webhook

Antes de confiar no campo `de`, **verifique a assinatura** da requisição (cada plataforma tem seu método — geralmente um cabeçalho HMAC que você recalcula com um segredo compartilhado). Sem isso, qualquer um pode mandar um `de` fingindo ser outra pessoa.

### ✅ Checklist "para colocar em uso"

- [ ] **Identidade validada** (não é só o que o usuário digita).
- [ ] **Assinatura do webhook verificada** (a requisição veio mesmo da plataforma).
- [ ] **Usuário PostgreSQL só-leitura** para as consultas do agente (`agente_leitura`).
- [ ] **RLS ligada** nas tabelas com dados de usuário (`conversas`, `mensagens`).
- [ ] **Master via `postgres`** (ignora RLS) e **comum via `agente_leitura` + `app.usuario`** (RLS filtra).
- [ ] **Pool de conexões** (não uma conexão única) para aguentar requisições simultâneas.
- [ ] **Segredos só no `.env`** (nunca commitados, nunca em `print`).

---

## Problemas comuns (erros REAIS que aparecem)

**(a) "Rodei e não apareceu nada."** Provavelmente o arquivo está vazio ou você rodou o comando errado. O comando certo é:
```powershell
uv run python agente.py
```

**(b) `os error 396` no `uv sync`.** A pasta está em nuvem (OneDrive/Drive/Dropbox) e o hardlink falhou. Use:
```powershell
uv sync --link-mode=copy
```
Ou mova o projeto para fora da pasta sincronizada (ex.: `C:\Projetos\...`).

**(c) `ModuleNotFoundError` (ex.: `jsonpatch`).** A `.venv` corrompeu (muitas vezes por ter sido **copiada** de outro lugar, em vez de recriada). Recrie do zero:
```powershell
Remove-Item -Recurse -Force .venv
uv sync --link-mode=copy
```

**(d) `openai.BadRequestError` falando de `tool_calls` sem resposta.** A conversa ficou "machucada": você interrompeu com **Ctrl+C no meio de uma tool**, então ficou um pedido de tool **sem** a resposta correspondente no histórico, e a OpenAI recusa. Como resolver:
- Troque o `thread_id` (comece uma conversa nova, "limpa").
- Use o **middleware de erro** (Passo 8), que evita deixar tools sem resposta.
- E **saia sempre com `sair`**, nunca com Ctrl+C no meio de uma resposta.

**(e) API respondeu HTML ou `429`.** Se veio **HTML** em vez de JSON, a URL está errada — **teste a URL no navegador antes** (lembre: a BrasilAPI precisa do `/api/`). Se veio **`429 Too Many Requests`**, é limite de uso (*rate limit*) → conte com o **fallback** (Passo 10).

**(f) `UnicodeEncodeError` no terminal (por causa de emoji).** O console do Windows (cp1252) engasga com emoji. Force UTF-8 antes de rodar:
```powershell
$env:PYTHONIOENCODING="utf-8"; uv run python agente.py
```

**(g) A sumarização não gera resumo.** Faltou o `keep` **menor** que o `trigger`. Se o `keep` (padrão 20) for maior que o histórico no momento do gatilho, ele dispara mas **não compacta nada**. Ajuste, ex.: `trigger=("messages", 6)` com `keep=("messages", 2)`.

**(h) MCP: `StructuredTool does not support sync invocation`.** As tools de MCP são **assíncronas** — use `await agente.ainvoke(...)`, não o `invoke` síncrono.

**(i) MCP: `McpError: Connection closed`.** Um servidor MCP **não subiu**. Como o `get_tools()` inicia TODOS os servidores juntos, **um falho derruba todos**. Isole: rode o servidor "na mão" para ver o erro real (ex.: `npx -y @cocal/google-calendar-mcp`). Causa comum: você comentou uma entrada **pela metade** (deixou o `},` sem `#`) — comente/descomente o bloco **inteiro** (Ctrl+/).

**(j) MCP: `os error 396` no `uvx`/`npx`.** Mesmo problema de nuvem do `uv sync`. Passe `UV_LINK_MODE=copy` no `env` do servidor MCP (já está no `tools/mcp.py` via `_ENV`).

**(k) Async: `NotImplementedError: awrap_tool_call ... not available`.** Seu middleware só tem a versão **síncrona** (`@wrap_tool_call`), mas o agente rodou em async. Subclasse `AgentMiddleware` com `wrap_tool_call` **e** `awrap_tool_call` (Passo 21).

**(l) Async no Windows: `Psycopg cannot use the 'ProactorEventLoop'`.** Conflito entre o `AsyncPostgresSaver` (quer `SelectorEventLoop`) e os subprocessos do MCP (querem `ProactorEventLoop`). Use o `InMemorySaver` com MCP no Windows (Passo 21).

**(m) Google Calendar: `Invalid credentials file format ... "installed"`.** Seu `credentials.json` é do tipo **"Aplicativo da Web"** (chave `"web"`). Crie a credencial como **"App para computador" (Desktop app)** — o JSON terá a chave `"installed"`.

**(n) Google Calendar: `Erro 403: access_denied`.** Seu app OAuth está em "Teste" e seu e-mail não é testador. Adicione-o em **Tela de permissão OAuth → Usuários de teste**.

---

## Resumo dos arquivos do projeto

| Arquivo | O que faz |
| --- | --- |
| `agente.py` | Versão **terminal** (loop). Memória (PostgresSaver), histórico legível (conversas/mensagens), resumos, tools (CNPJ/CEP + SQL), sumarização. Pede o `login`; `thread_id = login`, `owner = login`. |
| `webhook.py` | Versão **HTTP** (FastAPI). Identidade vem do campo `de`. Monta o agente **por requisição**, escolhendo a conexão SQL por `is_master` (master → `postgres`; comum → `agente_leitura` + RLS). |
| `tools/__init__.py` | A "vitrine" do pacote: a lista central `TOOLS` e o `tratar_erros_de_tool`. |
| `tools/_shared.py` | Infra compartilhada: `http_get_json` (HTTP com timeout/status/JSON seguro) e a exceção `ToolAPIError`. |
| `tools/cnpj.py` | Tool de CNPJ (BrasilAPI + **fallback** minhareceita). Padrão schema → service → `@tool`. |
| `tools/cep.py` | Tool de CEP (ViaCEP; trata o quirk `{"erro": true}`). |
| `tools/error_handling.py` | Middleware `wrap_tool_call`: tool que falha vira `ToolMessage` amigável (não derruba o programa). |
| `tools/sql.py` | `criar_tools_sql`: as 4 tools de SQL (SQLDatabaseToolkit), driver `psycopg`, e o carimbo do `app.usuario` (RLS). |
| `sql/01_criar_tabelas.sql` | Cria `conversas`, `mensagens`, `resumos`, `usuarios`. |
| `sql/02_usuario_leitura.sql` | Cria o usuário `agente_leitura` (só `SELECT`). |
| `sql/03_isolamento_rls.sql` | Liga a RLS e cria as políticas por `owner`. |
| `sql/consultar_conversas.sql` | Consulta com JOIN para ler o histórico em texto limpo. |
| `pyproject.toml` | "Documento de identidade" do projeto: nome, versão do Python, dependências. |
| `.env.example` | Modelo de segredos (vai para o GitHub, sem valores reais). |
| `.env` | Seus segredos reais (**ignorado** pelo Git). |
| `.gitignore` | Lista do que **não** vai ao GitHub (`.env`, `.venv/`, caches). |
| `CLAUDE.md` | Contexto do projeto para assistentes de IA (Claude Code). |
| `uv.lock` | Trava as versões exatas das dependências (gerado pelo `uv`). |

---

## Como subir ao seu GitHub

**Antes de tudo, confirme que o `.env` está protegido** (você não quer vazar suas chaves):

```powershell
git init
git check-ignore .env      # DEVE imprimir ".env" (prova que está ignorado)
git status                 # o ".env" NÃO pode aparecer na lista
```

> Se `git check-ignore .env` **não** imprimir nada, o `.env` **não** está sendo ignorado — pare e confira o `.gitignore` antes de continuar. Nunca faça `git add` com o `.env` desprotegido.

Depois:

```powershell
git add .
git commit -m "primeiro commit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
git push -u origin main
```

- `git add .` prepara todos os arquivos (menos os ignorados).
- `git commit` grava a "foto" atual do projeto.
- `git branch -M main` nomeia a branch principal de `main`.
- `git remote add origin <URL>` aponta para o repositório no GitHub (crie um repositório vazio lá antes e copie a URL).
- `git push -u origin main` envia tudo.

Pronto! Seu agente está no GitHub — e, graças ao `.gitignore`, **sem** os seus segredos. 🚀

---

### Palavra final

Você construiu, passo a passo, um agente que conversa, lembra de verdade, usa ferramentas, consulta o banco em linguagem natural e atende por webhook com **isolamento por usuário**. Cada degrau resolveu um problema real e apresentou um conceito novo. A partir daqui, o caminho natural é: trocar o modelo (Gemini), adicionar novas tools (mexendo só no pacote `tools/`) e endurecer a produção (assinatura + pool). Bons estudos!
