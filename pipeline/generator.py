"""
generator.py — Etapa 4 do pipeline SPUK-LEGIS

Recebe o JSON de cards revisado e o fingerprint de armadilhas e
gera 2–3 variantes por card via LLM, priorizando as armadilhas
de maior frequência histórica para cada artigo.

Implementado após o analyzer.py (Etapa 3).
"""


def generate(cards_path: str, fingerprint_path: str) -> dict:
    raise NotImplementedError("generator.py será implementado na Etapa 4.")