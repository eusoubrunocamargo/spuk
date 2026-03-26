"""
exporter.py — Etapa 6 do pipeline SPUK-LEGIS

Recebe o JSON completo aprovado no dashboard Streamlit e gera
o arquivo SQL Flyway para inserção nas tabelas do app rinhadeconcurseiro.

Implementado após a aprovação no dashboard (Etapa 5).
"""


def export(full_json_path: str, corpus_sigla: str) -> str:
    """
    Gera e retorna o conteúdo SQL da migration Flyway.
    """
    raise NotImplementedError("exporter.py será implementado na Etapa 6.")