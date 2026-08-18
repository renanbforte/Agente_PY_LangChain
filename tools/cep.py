# tools/cep.py — tool que busca endereço por CEP (ViaCEP)

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
    # Lógica ESPECÍFICA do ViaCEP (200 com erro=true) fica aqui, na tool.
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