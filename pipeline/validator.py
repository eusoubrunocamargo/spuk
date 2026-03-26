"""
validator.py — Validação de schema do JSON intermediário SPUK-LEGIS

Valida que o JSON de cards ou o JSON completo (com variantes) estão
em conformidade com o schema esperado antes de avançar para a próxima etapa.

Implementado junto com o generator.py (Etapa 4).
"""


def validate_cards(data: dict) -> list:
    """
    Valida o JSON de cards (saída do parser ou revisado).
    Retorna uma lista de erros encontrados (vazia se válido).
    """
    raise NotImplementedError("validator.py será implementado na Etapa 4.")


def validate_full(data: dict) -> list:
    """
    Valida o JSON completo com variantes (saída do generator).
    Retorna uma lista de erros encontrados (vazia se válido).
    """
    raise NotImplementedError("validator.py será implementado na Etapa 4.")