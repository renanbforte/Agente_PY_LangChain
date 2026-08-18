# tools/cnpj.py — tool que busca dados de empresa por CNPJ (com FALLBACK)

from pydantic import BaseModel, Field, field_validator
from langchain_core.tools import tool
from ._shared import http_get_json, ToolAPIError


class CNPJInput(BaseModel):
    cnpj: str = Field(..., description="CNPJ da empresa (14 dígitos; pode vir com pontos/barra/traço)")

    @field_validator("cnpj")
    @classmethod
    def limpar_cnpj(cls, v):
        digitos = "".join(c for c in v if c.isdigit())
        if len(digitos) != 14:
            raise ValueError("O CNPJ deve conter 14 dígitos.")
        return digitos


def buscar_cnpj_service(cnpj):
    """Tenta várias fontes em ordem. Se a 1ª falhar (ex.: 429), tenta a próxima.
    As duas devolvem os MESMOS campos, então o resto do código não muda."""
    fontes = [
        f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}",   # 1ª tentativa
        f"https://minhareceita.org/{cnpj}",               # fallback (mesmo formato)
    ]
    ultimo_erro = None
    for url in fontes:                        # tenta cada fonte, em ordem
        try:
            return http_get_json(url)         # deu certo -> retorna e para
        except ToolAPIError as e:
            ultimo_erro = e                   # falhou -> guarda e tenta a próxima
    # Se TODAS falharam, aí sim desistimos, informando o último erro.
    raise ToolAPIError(f"Nenhuma fonte de CNPJ respondeu. Último erro: {ultimo_erro}")


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