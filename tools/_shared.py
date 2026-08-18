# tools/_shared.py — infraestrutura COMPARTILHADA entre as tools

import requests


# Nosso próprio tipo de erro. Criar uma classe (herdando de Exception) deixa
# claro que é um "erro esperado de tool", diferente de um bug qualquer.
class ToolAPIError(Exception):
    pass


def http_get_json(url, timeout=10):
    """Faz um GET e devolve o JSON — com timeout, checagem de status e leitura
    segura. Levanta ToolAPIError com mensagem clara em qualquer falha.
    Escrito UMA vez, usado por TODAS as tools de API (princípio DRY)."""
    try:
        resp = requests.get(url, timeout=timeout)   # timeout: nunca esperar para sempre
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