# tools/sql.py — cria as 4 tools de SQL (consultar o banco em linguagem natural)

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit


def criar_tools_sql(database_url, modelo, app_usuario=None):
    """Cria as 4 tools de SQL. Se app_usuario for informado, carimba a variável
    de sessão app.usuario na conexão — é isso que faz o RLS filtrar por usuário."""
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