-- ============================================================================
-- 01_criar_tabelas.sql — tabelas de histórico legível e de usuários
-- ----------------------------------------------------------------------------
-- Rode UMA vez, conectado ao banco 'agente_ia' (como o usuário postgres).
-- No pgAdmin: Query Tool no banco agente_ia → cole → Execute (F5).
-- No psql:    psql -U postgres -d agente_ia -f sql/01_criar_tabelas.sql
--
-- Observação: o LangGraph cria as tabelas dele (checkpoints...) sozinho, via
-- checkpointer.setup(). ESTAS tabelas são as NOSSAS, para ler o histórico em
-- texto limpo e para saber quem é cada usuário.
-- ============================================================================

-- Uma linha por conversa (uma "sessão" de bate-papo).
CREATE TABLE IF NOT EXISTS conversas (
    id SERIAL PRIMARY KEY,             -- id único, autoincrementado (1, 2, 3...)
    thread_id TEXT UNIQUE NOT NULL,    -- código da conversa; UNIQUE = não repete
    owner TEXT,                        -- dono da conversa (a identidade do usuário)
    criada_em TIMESTAMP DEFAULT NOW()  -- data/hora automática
);

-- Muitas linhas por conversa (cada pergunta e cada resposta).
CREATE TABLE IF NOT EXISTS mensagens (
    id SERIAL PRIMARY KEY,
    conversa_id INTEGER NOT NULL REFERENCES conversas(id),  -- chave estrangeira -> conversas.id
    papel TEXT NOT NULL,               -- 'user' ou 'assistant'
    conteudo TEXT NOT NULL,            -- o texto da mensagem
    owner TEXT,                        -- dono da mensagem (mesma identidade da conversa)
    criada_em TIMESTAMP DEFAULT NOW()
);

-- Guarda os resumos gerados pela sumarização (para ler em texto limpo).
CREATE TABLE IF NOT EXISTS resumos (
    id SERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    mensagem_id TEXT UNIQUE,           -- id da mensagem-resumo; UNIQUE = não duplica
    resumo TEXT NOT NULL,
    criada_em TIMESTAMP DEFAULT NOW()
);

-- Quem existe e quem pode ver tudo (master).
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    login TEXT UNIQUE NOT NULL,        -- identificador (número validado / login)
    nome TEXT,
    is_master BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = vê tudo; FALSE = só o dele
    criado_em TIMESTAMP DEFAULT NOW()
);
