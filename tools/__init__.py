# tools/__init__.py — reúne as tools e o middleware de erro

from .cnpj import buscar_cnpj
from .cep import buscar_cep                       # <- novo
from .error_handling import tratar_erros_de_tool

TOOLS = [
    buscar_cnpj,
    buscar_cep,                                   # <- novo
]

__all__ = ["TOOLS", "tratar_erros_de_tool"]