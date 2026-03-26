"""
analyzer.py — Etapa 3 do pipeline SPUK-LEGIS

Recebe o JSON de cards revisado e o dataset de questões CEBRASPE e
produz o fingerprint de armadilhas por artigo via LLM.

Implementado após a revisão humana do JSON de cards (Etapa 2).
"""


def analyze(cards_path: str, questoes_path: str) -> dict:
    raise NotImplementedError("analyzer.py será implementado na Etapa 3.")