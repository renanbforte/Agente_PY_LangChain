-- ============================================================================
-- consultar_conversas.sql — ver o histórico em TEXTO LIMPO (JOIN)
-- ----------------------------------------------------------------------------
-- Junta 'mensagens' com 'conversas' (pela chave estrangeira) e ordena por data.
-- Rode no Query Tool do pgAdmin (banco agente_ia) ou no psql.
-- OBS: rodando como 'postgres' (master), você vê tudo (ignora a RLS).
-- ============================================================================

SELECT
    c.thread_id AS conversa,     -- vem da tabela conversas (apelido "c")
    m.papel     AS quem_falou,   -- 'user' ou 'assistant' (tabela mensagens, apelido "m")
    m.conteudo  AS mensagem,     -- o texto
    m.criada_em AS quando        -- a data/hora
FROM mensagens AS m              -- tabela principal (apelidada "m")
JOIN conversas AS c              -- juntamos com conversas (apelidada "c")
    ON m.conversa_id = c.id      -- a chave estrangeira em ação
ORDER BY m.criada_em ASC;        -- do mais antigo ao mais novo


-- Ver apenas UMA conversa (troque o thread_id):
-- SELECT c.thread_id, m.papel, m.conteudo, m.criada_em
-- FROM mensagens m JOIN conversas c ON m.conversa_id = c.id
-- WHERE c.thread_id = '5511999998888'
-- ORDER BY m.criada_em ASC;

-- Ver os resumos gerados pela sumarização:
-- SELECT thread_id, resumo, criada_em FROM resumos ORDER BY criada_em DESC;
