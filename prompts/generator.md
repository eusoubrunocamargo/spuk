# Prompt — generator.py

> Este prompt será elaborado na Etapa 4, junto com a implementação do `generator.py`.

## Objetivo

Dado um card da Lei 8.429/92 e o fingerprint de armadilhas do artigo correspondente,
gerar 2–3 variantes do texto priorizando os tipos de armadilha de maior frequência histórica.

## Output esperado

JSON com o array `variantes` no formato definido em `SPUK_LEGIS_STATUS.md`, incluindo
`textoApresentado`, `correto`, `trechoOriginal`, `trechoAlterado` e `tipoArmadilha`.