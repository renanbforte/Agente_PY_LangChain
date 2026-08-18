-- ============================================================================
-- 03_isolamento_rls.sql — isolamento multi-usuário com Row-Level Security (RLS)
-- ----------------------------------------------------------------------------
-- Com o SQL toolkit, o modelo escreve SQL LIVRE. Filtrar "no código" não segura.
-- A trava confiável é a RLS do PostgreSQL: cada linha tem um 'owner', e uma
-- política só deixa o usuário ver as linhas dele. Mesmo um "SELECT * FROM
-- mensagens" só devolve as linhas do usuário atual — o banco filtra.
--
-- O master é de graça: superusuários (postgres) IGNORAM a RLS e veem tudo.
-- Rode como postgres, no banco 'agente_ia'. (Precisa do 02_usuario_leitura.sql antes.)
-- ============================================================================

-- ===== conversas =====
-- preenche o owner das linhas já existentes (usa o thread_id como dono)
UPDATE conversas SET owner = thread_id WHERE owner IS NULL;
-- liga a RLS
ALTER TABLE conversas ENABLE ROW LEVEL SECURITY;
-- política: só LÊ as linhas cujo owner bate com a variável de sessão app.usuario
--   (o 'true' em current_setting devolve NULL se a variável não estiver setada;
--    aí a política não casa com ninguém e o usuário vê NADA — seguro/fail-closed)
DROP POLICY IF EXISTS conversa_do_dono ON conversas;
CREATE POLICY conversa_do_dono ON conversas
    FOR SELECT USING (owner = current_setting('app.usuario', true));

-- ===== mensagens =====
UPDATE mensagens m SET owner = c.thread_id
    FROM conversas c WHERE m.conversa_id = c.id AND m.owner IS NULL;
ALTER TABLE mensagens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mensagem_do_dono ON mensagens;
CREATE POLICY mensagem_do_dono ON mensagens
    FOR SELECT USING (owner = current_setting('app.usuario', true));

-- garante que o usuário só-leitura possa SELECT nas duas tabelas
GRANT SELECT ON conversas, mensagens TO agente_leitura;

-- ----------------------------------------------------------------------------
-- Como promover um MASTER (vê tudo): marque na tabela usuarios.
-- ----------------------------------------------------------------------------
-- UPDATE usuarios SET is_master = TRUE WHERE login = '5511999998888';

-- ----------------------------------------------------------------------------
-- Como TESTAR a isolação (conectado como o usuário só-leitura):
--   psql -U agente_leitura -d agente_ia
--   SELECT count(*) FROM conversas;                 -- 0 (sem app.usuario definido)
--   SET app.usuario = '5511999998888';
--   SELECT thread_id, owner FROM conversas;         -- só as desse usuário
-- E como postgres (master, ignora RLS): vê TODAS.
-- ----------------------------------------------------------------------------
