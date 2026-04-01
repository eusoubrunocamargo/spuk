"""
generator.py — Etapa 4 do pipeline SPUK-LEGIS

Recebe o JSON de cards auditado e o fingerprint de armadilhas e
gera 2-3 variantes por card via LLM, priorizando as armadilhas
de maior frequência histórica para cada artigo.

Para cada card ativo:
  - 1 variante CORRETA  (textoOriginal sem alteração)
  - 2 variantes ERRADAS (com armadilhas do fingerprint ou fallback global)

Uso via CLI:
    python main.py generate output/lei_8429_cards.json \\
        --fingerprint output/lei_8429_fingerprint.json \\
        --output output/lei_8429_full.json
"""

import json
import os
import time
import copy
from pathlib import Path
from collections import Counter

from dotenv import load_dotenv
import anthropic

load_dotenv()

# ---------------------------------------------------------------------------
# Distribuição global de armadilhas — fallback para cards sem fingerprint
# ---------------------------------------------------------------------------

# Ordenada por frequência histórica observada no fingerprint da Lei 8.429
ARMADILHAS_FALLBACK = ["NEGACAO", "QUALIFICADOR", "ESCOPO", "SUJEITO", "ABSOLUTO"]

TIPOS_ARMADILHA = {
    "NUMERAL":      "Troca de número, prazo, fração, quórum (ex: 30 dias → 15 dias)",
    "QUALIFICADOR": "Troca de adjetivo ou substantivo por termo de conotação similar mas errado (ex: dolosa → culposa)",
    "NEGACAO":      "Inserção ou remoção de elemento negativo (ex: não poderá → poderá; aplicável → inaplicável)",
    "ABSOLUTO":     "Troca entre termos absolutos e relativos (ex: sempre → em regra; exclusivamente → preferencialmente)",
    "SUJEITO":      "Troca do titular da competência ou obrigação (ex: Ministério Público → autoridade administrativa)",
    "VERBO_MODAL":  "Troca entre poder/dever/ser vedado (ex: poderá → deverá)",
    "ESCOPO":       "Ampliação ou restrição do alcance da norma (ex: superior → inferior; integral → parcial)",
    "ORDEM":        "Inversão de elementos numa lista ou hierarquia",
}


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

def load_cards(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_fingerprint(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("fingerprint", {})


# ---------------------------------------------------------------------------
# Seleção de armadilhas para cada card
# ---------------------------------------------------------------------------

def _armadilhas_para_card(card: dict, fingerprint: dict) -> list:
    """
    Retorna lista ordenada de tipos de armadilha para um card específico.

    Se o card tem fingerprint com armadilhas registradas, usa as 2 mais
    frequentes. Caso contrário usa o fallback global.

    Garante sempre pelo menos 2 tipos distintos.
    """
    ref = card["referencia"]

    # Tenta o fingerprint do card exato primeiro
    fp = fingerprint.get(ref, {})
    freq = fp.get("frequenciaArmadilhas", {})

    # Se não achou, tenta o artigo pai (ex: "Art. 9º" para "Art. 9º, II")
    if not freq:
        art_pai = ref.split(",")[0].strip()
        fp = fingerprint.get(art_pai, {})
        freq = fp.get("frequenciaArmadilhas", {})

    if freq:
        # Ordena por frequência e pega as 2 mais comuns
        top = [k for k, _ in Counter(freq).most_common(2)]
        # Completa com fallback se tiver menos de 2
        for f in ARMADILHAS_FALLBACK:
            if len(top) >= 2:
                break
            if f not in top:
                top.append(f)
        return top[:2]

    # Fallback global
    return ARMADILHAS_FALLBACK[:2]


def _exemplos_para_card(card: dict, fingerprint: dict) -> list:
    """
    Retorna exemplos reais da banca para o card (se disponíveis),
    para incluir no prompt como referência de estilo.
    """
    ref = card["referencia"]
    art_pai = ref.split(",")[0].strip()

    exemplos = []
    for key in [ref, art_pai]:
        fp = fingerprint.get(key, {})
        exemplos.extend(fp.get("exemplosReais", []))
        if len(exemplos) >= 2:
            break

    return exemplos[:2]


# ---------------------------------------------------------------------------
# Construção do prompt
# ---------------------------------------------------------------------------

def _formata_card_para_prompt(card: dict, idx: int, armadilhas: list,
                               exemplos: list) -> str:
    """Formata um único card para inclusão no prompt em lote."""
    parent = f'\n   Contexto: "{card["textoParent"]}"' if card.get("textoParent") else ""
    arm_str = " e ".join(armadilhas)
    tipos_desc = "\n   ".join(
        f"- {a}: {TIPOS_ARMADILHA[a]}" for a in armadilhas if a in TIPOS_ARMADILHA
    )

    ex_str = ""
    if exemplos:
        ex_lines = []
        for ex in exemplos:
            if ex.get("trechoOriginal") and ex.get("trechoAlterado"):
                ex_lines.append(
                    f'   "{ex["trechoOriginal"]}" → "{ex["trechoAlterado"]}" ({ex["tipoArmadilha"]})'
                )
        if ex_lines:
            ex_str = "\n   Exemplos reais da banca:\n" + "\n".join(ex_lines)

    return f"""CARD #{idx} [{card["referencia"]}]{parent}
   Texto: "{card["textoOriginal"]}"
   Armadilhas a usar: {arm_str}
   {tipos_desc}{ex_str}"""


def build_prompt(batch: list, fingerprint: dict) -> tuple:
    """
    Monta o prompt para um lote de cards.
    Retorna (prompt_str, lista_de_metadados) onde metadados contém
    as armadilhas selecionadas para cada card — usadas na consolidação.
    """
    cards_str_parts = []
    metadados = []

    for i, card in enumerate(batch):
        armadilhas = _armadilhas_para_card(card, fingerprint)
        exemplos = _exemplos_para_card(card, fingerprint)
        cards_str_parts.append(_formata_card_para_prompt(card, i + 1, armadilhas, exemplos))
        metadados.append({"referencia": card["referencia"], "armadilhas": armadilhas})

    tipos_str = "\n".join(
        f"  - {t}: {d}" for t, d in TIPOS_ARMADILHA.items()
    )

    prompt = f"""Você é especialista em elaboração de questões CEBRASPE de concursos públicos brasileiros.

## Sua tarefa

Para cada CARD abaixo, gere EXATAMENTE 3 variantes:
  - 1 variante CORRETA: reproduz o texto original fielmente (sem alteração)
  - 2 variantes ERRADAS: aplicam as armadilhas especificadas, cada uma com UMA alteração cirúrgica

## Taxonomia de armadilhas

{tipos_str}

## Regras para as variantes ERRADAS

1. Altere APENAS um elemento por variante — nunca dois ao mesmo tempo
2. A alteração deve ser sutil e plausível, como a banca CEBRASPE faz
3. O restante do texto deve ser idêntico ao original
4. Prefira trocar palavras específicas em vez de reescrever frases
5. Para NEGACAO: pode inserir "não", trocar "aplicável" por "inaplicável", etc.
6. Para QUALIFICADOR: troque "dolosa" por "culposa", "solidária" por "subsidiária", etc.

## Cards a processar

{chr(10).join(cards_str_parts)}

## Output

Responda SOMENTE com JSON válido, sem markdown, sem texto adicional:

{{
  "variantes": [
    {{
      "card_idx": 1,
      "variantes": [
        {{
          "textoApresentado": "texto completo da variante",
          "correto": true,
          "trechoOriginal": null,
          "trechoAlterado": null,
          "tipoArmadilha": null
        }},
        {{
          "textoApresentado": "texto com armadilha aplicada",
          "correto": false,
          "trechoOriginal": "trecho exato do original",
          "trechoAlterado": "como ficou na variante errada",
          "tipoArmadilha": "NEGACAO"
        }},
        {{
          "textoApresentado": "texto com outra armadilha",
          "correto": false,
          "trechoOriginal": "trecho exato do original",
          "trechoAlterado": "como ficou na variante errada",
          "tipoArmadilha": "QUALIFICADOR"
        }}
      ]
    }}
  ]
}}

Gere o objeto "variantes" para TODOS os {len(batch)} cards acima, na ordem.
"""
    return prompt, metadados


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

            if response.stop_reason == "max_tokens":
                raise RuntimeError("Resposta truncada. Reduza o batch.")

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
# Consolidação das variantes no JSON de cards
# ---------------------------------------------------------------------------

def _validar_variante(v: dict, texto_original: str) -> bool:
    """
    Valida que a variante tem estrutura correta e que a variante correta
    não foi alterada em relação ao texto original.
    """
    campos = ["textoApresentado", "correto", "trechoOriginal", "trechoAlterado", "tipoArmadilha"]
    if not all(k in v for k in campos):
        return False

    # A variante correta deve ter texto idêntico ou muito próximo ao original
    if v["correto"] and v["textoApresentado"].strip() != texto_original.strip():
        # Permite pequenas diferenças de espaçamento
        if v["textoApresentado"].strip().lower() != texto_original.strip().lower():
            return False

    # Variante errada deve ter trechos preenchidos
    if not v["correto"] and not v.get("trechoAlterado"):
        return False

    return True


def consolidar(cards_data: dict, todos_resultados: list,
               cards_processados: list) -> dict:
    """
    Aplica as variantes geradas de volta ao JSON de cards.
    Retorna o JSON completo com variantes populadas.
    """
    # Índice rápido de cards por referência
    cards_idx = {c["referencia"]: i for i, c in enumerate(cards_data["cards"])}

    total_ok = 0
    total_err = 0

    for resultado, card in zip(todos_resultados, cards_processados):
        ref = card["referencia"]
        texto_original = card["textoOriginal"]

        # O resultado pode vir com índice 1..N ou direto como lista
        variantes_raw = resultado.get("variantes", [])

        # Suporte a dois formatos: lista de dicts com card_idx, ou lista direta
        if variantes_raw and isinstance(variantes_raw[0], dict) and "variantes" in variantes_raw[0]:
            # Formato: {"variantes": [{"card_idx": 1, "variantes": [...]}]}
            variantes_list = variantes_raw[0].get("variantes", [])
        else:
            variantes_list = variantes_raw

        variantes_validadas = [
            v for v in variantes_list
            if _validar_variante(v, texto_original)
        ]

        if not variantes_validadas:
            total_err += 1
            continue

        idx = cards_idx.get(ref)
        if idx is not None:
            cards_data["cards"][idx]["variantes"] = variantes_validadas
            total_ok += 1

    print(f"  Variantes aplicadas: {total_ok} | Erros/vazios: {total_err}")
    return cards_data


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def generate(cards_path: str, fingerprint_path: str, output_path: str,
             batch_size: int = 10, verbose: bool = True) -> dict:
    """
    Pipeline completo do generator.

    1. Carrega cards auditados e fingerprint
    2. Para cada lote de cards ativos: monta prompt → chama LLM → coleta variantes
    3. Consolida variantes de volta no JSON
    4. Salva lei_8429_full.json
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY não encontrada. Configure em .env")

    client = anthropic.Anthropic(api_key=api_key)

    print("Carregando dados...")
    cards_data = load_cards(cards_path)
    fingerprint = load_fingerprint(fingerprint_path)

    cards_ativos = [c for c in cards_data["cards"] if c.get("ativo")]
    # Só processa cards que ainda não têm variantes
    cards_pendentes = [c for c in cards_ativos if not c.get("variantes")]

    print(f"  {len(cards_ativos)} cards ativos | {len(cards_pendentes)} sem variantes")

    if not cards_pendentes:
        print("  Todos os cards já têm variantes. Nada a fazer.")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(cards_data, f, ensure_ascii=False, indent=2)
        return cards_data

    # Divide em batches
    batches = [
        cards_pendentes[i:i + batch_size]
        for i in range(0, len(cards_pendentes), batch_size)
    ]
    print(f"  {len(batches)} batches de até {batch_size} cards\n")

    todos_resultados = []
    todos_cards_processados = []

    for i, batch in enumerate(batches, 1):
        print(f"[{i}/{len(batches)}] {len(batch)} cards...")
        prompt, metadados = build_prompt(batch, fingerprint)

        resultado = call_llm(prompt, client, verbose=verbose)

        # O LLM retorna um objeto com lista "variantes" — precisamos fatiar
        # um resultado por card para a consolidação
        variantes_por_card = resultado.get("variantes", [])

        for j, card in enumerate(batch):
            # Extrai as variantes deste card específico
            if j < len(variantes_por_card):
                item = variantes_por_card[j]
                # Normaliza formato
                if "variantes" in item:
                    sub_variantes = item["variantes"]
                else:
                    sub_variantes = item if isinstance(item, list) else []
                todos_resultados.append({"variantes": sub_variantes})
            else:
                todos_resultados.append({"variantes": []})
            todos_cards_processados.append(card)

        # Salva checkpoint incremental após cada batch
        consolidar(cards_data, todos_resultados[-len(batch):],
                   todos_cards_processados[-len(batch):])
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(cards_data, f, ensure_ascii=False, indent=2)

        if i < len(batches):
            time.sleep(2)

    print(f"\n✓ Output salvo → {output_path}")

    # Estatísticas finais
    cards_com_variantes = sum(
        1 for c in cards_data["cards"]
        if c.get("variantes")
    )
    total_variantes = sum(
        len(c.get("variantes", []))
        for c in cards_data["cards"]
    )
    print(f"  Cards com variantes: {cards_com_variantes}")
    print(f"  Total de variantes:  {total_variantes}")

    return cards_data