# spuk

Pipeline de geração de conteúdo para o **SPUK-LEGIS** — primeiro modo do SPUK, feature de repetição espaçada da plataforma [Rinha de Concurseiro](https://github.com/seu-usuario/rinhadeconcurseiro).

O SPUK-LEGIS apresenta trechos de lei para julgamento C/E via swipe tinder-like, com feedback imediato destacando a armadilha da banca.

---

## Visão geral

Este repositório **produz conhecimento** — transforma o texto bruto da Lei 8.429/92 em cards auditáveis e depois em SQL Flyway pronto para o app.

```
corpus/lei_8429.pdf
        │
        ▼
   [1. parser.py]          → output/lei_8429_cards.json
        │
        ▼ (revisão humana)
   [2. analyzer.py]        → output/lei_8429_fingerprint.json
        │
        ▼
   [3. generator.py]       → output/lei_8429_full.json
        │
        ▼ (dashboard Streamlit)
   [4. exporter.py]        → output/V10__seed_spuk_lei8429.sql
```

---

## Pré-requisitos

- Python 3.10+
- Dependências: `pip install -r requirements.txt`
- Chave da API Anthropic em `.env` (necessária apenas para `analyzer.py` e `generator.py`)

---

## Uso

```bash
# Etapa 1 — parser (sem LLM, determinístico)
python main.py parse corpus/lei_8429.pdf --output output/lei_8429_cards.json

# Etapa 2 — revisão humana do JSON de cards (manual)

# Etapa 3 — analyzer (LLM: mapeia armadilhas das questões CEBRASPE)
python main.py analyze output/lei_8429_cards.json \
  --questoes questoes/dataset_sanitizado_lei8429.json \
  --output output/lei_8429_fingerprint.json

# Etapa 4 — generator (LLM: gera variantes com armadilhas)
python main.py generate output/lei_8429_cards.json \
  --fingerprint output/lei_8429_fingerprint.json \
  --output output/lei_8429_full.json

# Etapa 5 — dashboard de auditoria (revisão humana das variantes)
streamlit run dashboard.py

# Etapa 6 — exporter (gera SQL Flyway)
python main.py export output/lei_8429_full.json \
  --corpus LEI8429 \
  --output output/V10__seed_spuk_lei8429.sql
```

---

## Estrutura do repositório

```
spuk/
├── README.md
├── requirements.txt
├── .env.example
│
├── corpus/
│   └── lei_8429.pdf          ← PDF completo da Câmara dos Deputados
│
├── questoes/
│   └── dataset_sanitizado_lei8429.json   ← 235 questões CERTO_ERRADO CEBRASPE
│
├── pipeline/
│   ├── __init__.py
│   ├── parser.py             ← Etapa 1: PDF → JSON de cards (sem LLM)
│   ├── analyzer.py           ← Etapa 3: questões → fingerprint de armadilhas
│   ├── generator.py          ← Etapa 4: cards + fingerprint → variantes
│   ├── validator.py          ← validação de schema do JSON
│   └── exporter.py           ← Etapa 6: JSON aprovado → SQL Flyway
│
├── prompts/
│   ├── analyzer.md           ← prompt para o analyzer.py
│   └── generator.md          ← prompt para o generator.py
│
├── output/                   ← arquivos gerados (gitignored)
│   ├── lei_8429_cards.json
│   ├── lei_8429_fingerprint.json
│   ├── lei_8429_full.json
│   └── V10__seed_spuk_lei8429.sql
│
├── dashboard.py              ← Streamlit: auditoria das variantes
└── main.py                   ← CLI unificada
```

---

## Taxonomia de armadilhas CEBRASPE

| Tipo | Descrição | Exemplo |
|---|---|---|
| `NUMERAL` | Troca de número, prazo, fração, quórum | `30 dias` → `15 dias` |
| `QUALIFICADOR` | Troca de adjetivo/substantivo de conotação similar | `solidária` → `participativa` |
| `NEGAÇÃO` | Inserção ou remoção de elemento negativo | `não poderá` → `poderá` |
| `ABSOLUTO` | Troca entre termos absolutos e relativos | `sempre` → `em regra` |
| `SUJEITO` | Troca do titular da competência/obrigação | `União` → `Estado` |
| `VERBO_MODAL` | Troca entre poder/dever/ser vedado | `deverá` → `poderá` |
| `ESCOPO` | Ampliação ou restrição do alcance da norma | `superior` → `inferior` |
| `ORDEM` | Inversão de elementos numa lista ou hierarquia | troca inciso I pelo II |