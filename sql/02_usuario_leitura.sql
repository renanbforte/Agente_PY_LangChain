-- ============================================================================
-- 02_usuario_leitura.sql — cria o usuário PostgreSQL SÓ-LEITURA
-- ----------------------------------------------------------------------------
-- Este usuário é usado pelo SQL toolkit dos usuários COMUNS: ele só consegue
-- LER (SELECT). Assim, mesmo que o modelo gere um DELETE/DROP, o banco RECUSA.
-- A segurança fica no banco, não no código — à prova do modelo.
--
-- Rode como postgres, no banco 'agente_ia'. TROQUE 'senha_leitura' por uma senha.
-- ============================================================================

-- 1. cria o usuário só de leitura
CREATE USER agente_leitura WITH PASSWORD 'senha_leitura';

-- 2. deixa ele CONECTAR e enxergar o schema
GRANT CONNECT ON DATABASE agente_ia TO agente_leitura;
GRANT USAGE ON SCHEMA public TO agente_leitura;

-- 3. concede APENAS SELECT (leitura) nas tabelas atuais...
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agente_leitura;

-- 4. ...e também nas tabelas FUTURAS (criadas depois pelo postgres)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agente_leitura;
