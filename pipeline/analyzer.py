"""
analyzer.py — Etapa 3 do pipeline SPUK-LEGIS

Cruza os 200 cards auditados da Lei 8.429/92 com as questões CERTO_ERRADO
do dataset CEBRASPE e produz o fingerprint de armadilhas por artigo.

Para cada grupo de artigos, o LLM:
  1. Classifica cada questão como LITERALIDADE ou DOUTRINA
  2. Para LITERALIDADE: identifica o card testado, o trecho alterado,
     e classifica o tipo de armadilha CEBRASPE
  3. Consolida frequência histórica de armadilhas por card

Uso via CLI:
    python main.py analyze output/lei_8429_cards.json \\
        --questoes questoes/dataset_sanitizado_lei8429.json \\
        --output output/lei_8429_fingerprint.json
"""

import json
import os
import time
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
import anthropic

load_dotenv()

# ---------------------------------------------------------------------------
# Taxonomia de armadilhas
# ---------------------------------------------------------------------------
TIPOS_ARMADILHA = {
    "NUMERAL":      "Troca de número, prazo, fração, quórum (ex: 30 dias → 15 dias)",
    "QUALIFICADOR": "Troca de adjetivo/substantivo de conotação similar",
    "NEGACAO":      "Inserção ou remoção de elemento negativo (ex: não poderá → poderá)",
    "ABSOLUTO":     "Troca entre termos absolutos e relativos (ex: sempre → em regra)",
    "SUJEITO":      "Troca do titular da competência/obrigação (ex: União → Estado)",
    "VERBO_MODAL":  "Troca entre poder/dever/ser vedado",
    "ESCOPO":       "Ampliação ou restrição do alcance da norma (ex: superior → inferior)",
    "ORDEM":        "Inversão de elementos numa lista ou hierarquia",
}

# ---------------------------------------------------------------------------
# Mapeamento: id_assunto_nome → artigos cobertos
# ---------------------------------------------------------------------------
ASSUNTO_PARA_ARTIGOS = {
    "Das Disposições Gerais (arts. 1º a 8º-A da Lei nº 8.429/1992)": [
        "Art. 1º", "Art. 2º", "Art. 3º", "Art. 7º", "Art. 8º", "Art. 8º-A"
    ],
    "Dos Atos de Improbidade (arts. 9º a 11 da Lei nº 8.429/1992)": [
        "Art. 9º", "Art. 10", "Art. 11"
    ],
    "Das Penas (art. 12 da Lei nº 8.429/1992)": ["Art. 12"],
    "Da Declaração de Bens (art. 13 da Lei nº 8.429/1992)": ["Art. 13"],
    "Do Procedimento Administrativo e do Processo Judicial (arts. 14 a 18-A da Lei nº 8.429/1992)": [
        "Art. 14", "Art. 15", "Art. 16", "Art. 17", "Art. 17-B",
        "Art. 17-C", "Art. 17-D", "Art. 18", "Art. 18-A"
    ],
    "Das Disposições Penais (arts. 19 a 22 da Lei nº 8.429/1992)": [
        "Art. 19", "Art. 20", "Art. 21", "Art. 22"
    ],
    "Da Prescrição (arts. 23 a 23-C da Lei nº 8.429/1992)": [
        "Art. 23", "Art. 23-A", "Art. 23-B", "Art. 23-C"
    ],
    "Tópicos Mesclados de Improbidade Administrativa (Lei nº 8.429/1992)": [],
}


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

def load_cards(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [c for c in data["cards"] if c.get("ativo")]


def load_questoes(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [q for q in data if q["tipo_questao"] == "CERTO_ERRADO"]


# ---------------------------------------------------------------------------
# Agrupamento
# ---------------------------------------------------------------------------

def build_grupos(cards: list, questoes: list) -> list:
    cards_por_artigo = defaultdict(list)
    for card in cards:
        art = card["referencia"].split(",")[0].strip()
        cards_por_artigo[art].append(card)

    questoes_por_assunto = defaultdict(list)
    for q in questoes:
        questoes_por_assunto[q["id_assunto_nome"]].append(q)

    grupos = []
    for assunto, artigos in ASSUNTO_PARA_ARTIGOS.items():
        qs = questoes_por_assunto.get(assunto, [])
        if not qs:
            continue

        if artigos:
            cs = []
            for art in artigos:
                cs.extend(cards_por_artigo.get(art, []))
        else:
            cs = cards  # Tópicos Mesclados: todos os cards

        if not cs:
            continue

        grupos.append({"assunto": assunto, "artigos": artigos,
                       "cards": cs, "questoes": qs})
    return grupos


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _formata_cards(cards: list) -> str:
    linhas = []
    for c in cards:
        ref = c["referencia"]
        parent = f'\n   Contexto do pai: "{c["textoParent"]}"' if c.get("textoParent") else ""
        linhas.append(f'[{ref}]{parent}\n   "{c["textoOriginal"]}"')
    return "\n\n".join(linhas)


def _formata_questoes(questoes: list) -> str:
    linhas = []
    for i, q in enumerate(questoes, 1):
        gabarito = "CERTO" if q["gabarito"] == "C" else "ERRADO"
        linhas.append(
            f'Q{i:03d} [id={q["id_tec"]}] [gabarito={gabarito}]\n'
            f'   "{q["enunciado_texto"]}"'
        )
    return "\n\n".join(linhas)


def build_prompt(grupo: dict) -> str:
    tipos_str = "\n".join(
        f"  - {tipo}: {desc}" for tipo, desc in TIPOS_ARMADILHA.items()
    )
    return f"""Você é um especialista em análise de questões CEBRASPE da Lei 8.429/1992.

## Tarefa

Analise cada questão e determine:
1. Se testa LITERALIDADE da lei ou DOUTRINA/conceito.
2. Para LITERALIDADE: qual card é testado, qual trecho foi alterado, qual armadilha.

## Taxonomia de armadilhas CEBRASPE

{tipos_str}

## Texto dos cards (dispositivos da lei)

{_formata_cards(grupo["cards"])}

## Questões

{_formata_questoes(grupo["questoes"])}

## Output

Responda SOMENTE com JSON válido, sem markdown, sem texto antes ou depois:

{{
  "analises": [
    {{
      "id_tec": "string",
      "tipo_cobranca_revisado": "LITERALIDADE_LEI" | "DOUTRINA" | "JURISPRUDENCIA" | "CASO_CONCRETO",
      "referencia_card": "Art. X, Y" | null,
      "armadilha": {{
        "trechoOriginal": "texto exato da lei",
        "trechoAlterado": "como a questão apresentou",
        "tipoArmadilha": "NUMERAL|QUALIFICADOR|NEGACAO|ABSOLUTO|SUJEITO|VERBO_MODAL|ESCOPO|ORDEM",
        "explicacao": "explicação curta"
      }} | null,
      "observacao": "string opcional"
    }}
  ]
}}

Regras:
- Questão DOUTRINA → referencia_card e armadilha = null
- Questão LITERALIDADE + gabarito ERRADO → armadilha OBRIGATÓRIA
- Questão LITERALIDADE + gabarito CERTO → armadilha = null, mas preencha referencia_card
- trechoOriginal: copie exatamente da lei; trechoAlterado: copie exatamente da questão
"""


# ---------------------------------------------------------------------------
# Chamada LLM com retry
# ---------------------------------------------------------------------------

def call_llm(prompt: str, client: anthropic.Anthropic, verbose: bool = False) -> dict:
    for tentativa in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            texto = response.content[0].text.strip()

            if verbose:
                print(f"    tokens: {response.usage.input_tokens}in / {response.usage.output_tokens}out")

            # Detecta truncamento pelo stop_reason antes de tentar parsear
            if response.stop_reason == "max_tokens":
                raise RuntimeError(
                    "Resposta truncada (max_tokens atingido). "
                    "Reduza o batch ou aumente max_tokens."
                )

            # Remove markdown fence se presente
            if texto.startswith("```"):
                texto = texto.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            return json.loads(texto)

        except json.JSONDecodeError as e:
            print(f"    [WARN] JSON inválido na tentativa {tentativa + 1}: {e}")
            if tentativa == 2:
                raise
            time.sleep(3)

        except anthropic.RateLimitError:
            wait = 30 * (tentativa + 1)
            print(f"    [RATE LIMIT] aguardando {wait}s...")
            time.sleep(wait)

    raise RuntimeError("Falha após 3 tentativas")


# ---------------------------------------------------------------------------
# Consolidação do fingerprint
# ---------------------------------------------------------------------------

def consolidar(todos_resultados: list, questoes_index: dict) -> dict:
    fingerprint = defaultdict(lambda: {
        "questoesAnalisadas": 0,
        "questoesLiteralidade": 0,
        "frequenciaArmadilhas": defaultdict(int),
        "exemplosReais": [],
        "observacoes": [],
    })
    reclassificacao = {}

    for resultado in todos_resultados:
        for analise in resultado.get("analises", []):
            id_tec = str(analise.get("id_tec", ""))
            tipo = analise.get("tipo_cobranca_revisado", "DOUTRINA")
            ref = analise.get("referencia_card")

            if id_tec:
                reclassificacao[id_tec] = tipo

            if tipo != "LITERALIDADE_LEI" or not ref:
                continue

            fp = fingerprint[ref]
            fp["questoesAnalisadas"] += 1
            fp["questoesLiteralidade"] += 1

            arm = analise.get("armadilha")
            if arm and arm.get("tipoArmadilha"):
                fp["frequenciaArmadilhas"][arm["tipoArmadilha"]] += 1
                enunciado = ""
                if id_tec in questoes_index:
                    enunciado = questoes_index[id_tec]["enunciado_texto"]
                fp["exemplosReais"].append({
                    "id_tec": id_tec,
                    "textoQuestao": enunciado,
                    "trechoOriginal": arm.get("trechoOriginal"),
                    "trechoAlterado": arm.get("trechoAlterado"),
                    "tipoArmadilha": arm["tipoArmadilha"],
                    "explicacao": arm.get("explicacao"),
                })

            obs = analise.get("observacao")
            if obs:
                fp["observacoes"].append(obs)

    # Serializa defaultdicts
    fingerprint_final = {}
    for ref, dados in fingerprint.items():
        fingerprint_final[ref] = {
            "questoesAnalisadas": dados["questoesAnalisadas"],
            "questoesLiteralidade": dados["questoesLiteralidade"],
            "frequenciaArmadilhas": dict(dados["frequenciaArmadilhas"]),
            "exemplosReais": dados["exemplosReais"],
            "observacoes": "; ".join(dados["observacoes"]) or None,
        }

    return {"fingerprint": fingerprint_final, "reclassificacao": reclassificacao}


def batch_grupo(grupo: dict, batch_size: int = 25) -> list:
    """
    Divide um grupo com muitas questões em batches menores.
    Cards são compartilhados por todos os batches do mesmo grupo.
    Cada batch resulta numa chamada independente ao LLM.
    """
    questoes = grupo["questoes"]
    if len(questoes) <= batch_size:
        return [grupo]

    batches = []
    for start in range(0, len(questoes), batch_size):
        batches.append({
            "assunto": grupo["assunto"],
            "artigos": grupo["artigos"],
            "cards": grupo["cards"],
            "questoes": questoes[start:start + batch_size],
        })
    return batches

def analyze(cards_path: str, questoes_path: str, output_path: str,
            verbose: bool = True) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY não encontrada. Configure em .env"
        )

    client = anthropic.Anthropic(api_key=api_key)

    print("Carregando dados...")
    cards = load_cards(cards_path)
    questoes = load_questoes(questoes_path)
    questoes_index = {str(q["id_tec"]): q for q in questoes}
    print(f"  {len(cards)} cards ativos | {len(questoes)} questões CERTO_ERRADO")

    grupos = build_grupos(cards, questoes)

    # Expande grupos grandes em batches de 25 questões
    BATCH_SIZE = 25
    batches = []
    for g in grupos:
        batches.extend(batch_grupo(g, batch_size=BATCH_SIZE))

    total_qs_cobertas = sum(len(g["questoes"]) for g in grupos)
    print(f"  {len(grupos)} grupos → {total_qs_cobertas} questões → {len(batches)} batches (≤{BATCH_SIZE} questões cada)\n")

    todos_resultados = []
    batch_num = 0

    for grupo in grupos:
        grupo_batches = batch_grupo(grupo, batch_size=BATCH_SIZE)
        n_cs = len(grupo["cards"])
        label = grupo["assunto"][:55]
        print(f"[{grupos.index(grupo)+1}/{len(grupos)}] {label}...")
        print(f"    {n_cs} cards | {len(grupo['questoes'])} questões → {len(grupo_batches)} batch(es)")

        grupo_resultados = []
        for b_idx, batch in enumerate(grupo_batches, 1):
            batch_num += 1
            if len(grupo_batches) > 1:
                print(f"    batch {b_idx}/{len(grupo_batches)} ({len(batch['questoes'])} questões)")

            prompt = build_prompt(batch)
            resultado = call_llm(prompt, client, verbose=verbose)
            grupo_resultados.append(resultado)
            todos_resultados.append(resultado)

            if batch_num < len(batches):
                time.sleep(2)

        n_lit = sum(
            1 for r in grupo_resultados
            for a in r.get("analises", [])
            if a.get("tipo_cobranca_revisado") == "LITERALIDADE_LEI"
        )
        n_arm = sum(
            1 for r in grupo_resultados
            for a in r.get("analises", [])
            if a.get("armadilha") is not None
        )
        print(f"    → {n_lit} literalidade | {n_arm} armadilhas")

    print("\nConsolidando fingerprint...")
    output = consolidar(todos_resultados, questoes_index)

    fp = output["fingerprint"]
    total_arm = sum(sum(d["frequenciaArmadilhas"].values()) for d in fp.values())
    print(f"  Cards com fingerprint: {len(fp)}")
    print(f"  Armadilhas catalogadas: {total_arm}")
    print(f"  Questões reclassificadas: {len(output['reclassificacao'])}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Fingerprint salvo → {output_path}")
    return output