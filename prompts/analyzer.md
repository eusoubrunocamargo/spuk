# Prompt — analyzer.py

> Este prompt será elaborado na Etapa 3, junto com a implementação do `analyzer.py`.

## Objetivo

Dado um card da Lei 8.429/92 e um conjunto de questões CEBRASPE que testam aquele artigo,
identificar: qual artigo cada questão testa, o tipo de armadilha usada, e a modificação exata
realizada no texto (trecho original → trecho alterado).

## Output esperado

JSON no formato do `fingerprint` definido em `SPUK_LEGIS_STATUS.md`.