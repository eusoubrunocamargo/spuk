"""
parser.py — Fases 1, 2 e 3 do pipeline SPUK-LEGIS
Extrai, limpa e tokeniza a Lei 8.429/92 a partir do PDF da Câmara dos Deputados.
"""

from dataclasses import dataclass, field
from typing import Optional

import re
import pdfplumber
from pathlib import Path


# ---------------------------------------------------------------------------
# Padrões de reconhecimento estrutural
# ---------------------------------------------------------------------------

# Marcadores que indicam o início de um novo elemento estrutural da lei.
# Uma linha que começa com qualquer um desses padrões NÃO é continuação.
STRUCTURAL_MARKERS = re.compile(
    r'^(?:'
    r'CAPÍTULO\s|'                  # CAPÍTULO I
    r'Seção\s|'                     # Seção I, Seção II-A
    r'Arts?\.\s+\d|'                # Art. 1º, Art. 8º-A, Arts. 4º a 6º
    r'§\s+\d|'                      # § 1º, § 2º
    r'Parágrafo único\.|'           # Parágrafo único.
    r'[IVXLCDM]+\s+-\s|'           # I - , XIV - (incisos)
    r'[a-z]\)\s'                    # a) b) c) (alíneas)
    r')'
)

# Linha que marca o início do texto normativo propriamente dito.
# Tudo antes dela (cabeçalho, título, preâmbulo) é descartado.
INICIO_NORMATIVO = re.compile(r'^CAPÍTULO\s')

# Notas legislativas entre parênteses.
# Cobre todos os padrões observados no PDF da Câmara:
#   (Parágrafo acrescido pela Lei nº 14.230, de 25/10/2021)
#   ("Caput" do artigo com redação dada pela Lei nº 14.230, de 25/10/2021)
#   (Artigo com redação dada pela Lei nº 14.230, de 25/10/2021)
#   (Inciso com redação dada pela Lei nº 14.230, de 25/10/2021)
#   (Revogado pela Lei nº 14.230, de 25/10/2021)
#   (Ementa com redação dada pela Lei nº 14.230, de 25/10/2021)
NOTA_LEGISLATIVA = re.compile(
    r'\s*\([^)]*(?:Lei\s+n|[Rr]evogad|redação|acrescid|[Ee]menta|[Aa]rtigo\s+com|[Ii]nciso\s+com|[Cc]aput|[Vv]ide)[^)]*\)',
    re.IGNORECASE
)

# Linhas de artigos revogados em bloco, ex: "Arts. 4º a 6º (Revogados...)"
# Essas linhas não têm conteúdo normativo — o artigo inteiro foi suprimido.
ARTS_REVOGADOS = re.compile(r'^Arts?\.\s+.*[Rr]evogad', re.IGNORECASE)

# Rótulos estruturais nus, sem conteúdo substantivo após a limpeza.
# Gerados quando o único conteúdo de um elemento era a nota de revogação.
# Exemplos: "§ 1º", "I -", "Parágrafo único.", "a)"
ROTULO_NU = re.compile(
    r'^(?:'
    r'Art\.\s+\d+[ºo°]?(?:-[A-Z])?\.?\s*|'  # Art. 17-A.  (artigo vetado/sem conteúdo)
    r'§\s+\d+[ºo°]?(?:-[A-Z])?\.?\s*|'       # § 1º  ou  § 10-A.
    r'[IVXLCDM]+\s+-\s*|'                     # I -   ou  XIV -
    r'Parágrafo único\.?\s*|'                 # Parágrafo único.
    r'[a-z]\)\s*'                             # a)
    r')[;,\.\s]*$',
    re.IGNORECASE
)

# Linhas de cabeçalho do documento (não fazem parte do texto normativo)
HEADER_LINES = {
    'CÂMARA DOS DEPUTADOS',
    'Centro de Documentação e Informação',
    'O PRESIDENTE DA REPÚBLICA',
    'Faço saber que o Congresso Nacional decreta e eu sanciono a seguinte lei:',
}

# Título do diploma legal — também é cabeçalho, não conteúdo normativo
TITULO_LEI = re.compile(r'^LEI\s+N[ºo°]\s+\d')


# ---------------------------------------------------------------------------
# Fase 1: Extração de texto
# ---------------------------------------------------------------------------

def extract_text(pdf_path: str) -> str:
    """
    Abre o PDF com pdfplumber e extrai o texto de todas as páginas,
    concatenando com newline. Retorna o texto bruto completo.
    """
    paginas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto_pagina = page.extract_text()
            if texto_pagina:
                paginas.append(texto_pagina)
    return '\n'.join(paginas)


# ---------------------------------------------------------------------------
# Fase 2: Limpeza
# ---------------------------------------------------------------------------

def _is_structural(line: str) -> bool:
    """Verifica se uma linha inicia um novo elemento estrutural."""
    return bool(STRUCTURAL_MARKERS.match(line.strip()))


def _join_continuation_lines(raw_text: str) -> list:
    """
    Junta linhas físicas (quebras do PDF) em linhas lógicas completas.

    Uma linha física é 'continuação' se não começa com um marcador estrutural.
    Ex: o texto de um parágrafo longo que o pdfplumber quebrou em 3 linhas
    é reunido em uma única string.

    Isso é essencial para que o regex de notas legislativas funcione corretamente,
    pois algumas notas cruzam a fronteira de duas linhas físicas.

    Tudo que precede o primeiro CAPÍTULO (cabeçalho, título, preâmbulo)
    é ignorado — não é conteúdo normativo.
    """
    logical_lines = []
    current = None
    normativo_iniciado = False  # flag: já chegamos ao primeiro CAPÍTULO?

    for raw_line in raw_text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        # Aguarda o início do texto normativo (primeiro CAPÍTULO)
        if not normativo_iniciado:
            if INICIO_NORMATIVO.match(line):
                normativo_iniciado = True
            else:
                continue  # descarta cabeçalho, título e preâmbulo

        if _is_structural(line):
            # Nova unidade estrutural: salva a anterior e começa uma nova
            if current is not None:
                logical_lines.append(current)
            current = line
        else:
            # Continuação: cola ao conteúdo atual com espaço
            if current is not None:
                current = current + ' ' + line

    if current is not None:
        logical_lines.append(current)

    return logical_lines


def clean_text(raw_text: str) -> list:
    """
    Recebe o texto bruto do PDF e retorna uma lista de linhas lógicas
    limpas, prontas para a tokenização hierárquica da Fase 3.

    O que é removido:
    - Cabeçalhos do documento (Câmara dos Deputados, título, preâmbulo)
    - Notas legislativas entre parênteses (redações dadas, acréscimos, revogações)
    - Artigos/parágrafos/incisos inteiramente revogados
    - Linhas que ficam como rótulo vazio após a limpeza
    """
    logical_lines = _join_continuation_lines(raw_text)

    cleaned = []
    for line in logical_lines:
        stripped = line.strip()

        # Descarta cabeçalhos e título
        if stripped in HEADER_LINES:
            continue
        if TITULO_LEI.match(stripped):
            continue

        # Descarta artigos revogados em bloco (ex: "Arts. 4º a 6º (Revogados...)")
        if ARTS_REVOGADOS.match(stripped):
            continue

        # Remove notas legislativas inline
        sem_nota = NOTA_LEGISLATIVA.sub('', stripped).strip()

        # Descarta rótulos nus — elementos cujo único conteúdo era a nota
        # Ex: "Parágrafo único." e "§ 1º" gerados por itens revogados
        if not sem_nota or ROTULO_NU.fullmatch(sem_nota):
            continue

        cleaned.append(sem_nota)

    return cleaned


# ---------------------------------------------------------------------------
# Fase 3: Tokenização hierárquica
# ---------------------------------------------------------------------------

@dataclass
class Token:
    """
    Representa uma unidade estrutural atômica da lei após a tokenização.

    Campos:
        tipo      — categoria estrutural (ver constantes abaixo)
        rotulo    — identificador da unidade, ex: "Art. 9º", "§ 1º", "I", "a"
        texto     — conteúdo normativo sem o rótulo
        titulo    — usado apenas em CAPITULO e SECAO para guardar o nome da seção
    """
    tipo: str
    rotulo: str
    texto: str
    titulo: str = ""   # preenchido só para CAPITULO e SECAO


# Constantes de tipo — espelham a hierarquia legislativa brasileira
T_CAPITULO        = "CAPITULO"
T_SECAO           = "SECAO"
T_ART_CAPUT       = "ART_CAPUT"
T_PARAGRAFO_UNICO = "PARAGRAFO_UNICO"
T_PARAGRAFO       = "PARAGRAFO"
T_INCISO          = "INCISO"
T_ALINEA          = "ALINEA"


# Regexes de tokenização — cada padrão captura (rotulo, texto) nos grupos 1 e 2.
# A ordem de declaração importa: os mais específicos vêm antes dos mais genéricos.
_PATTERNS = [
    # CAPÍTULO I DAS DISPOSIÇÕES GERAIS
    # grupo 1: "CAPÍTULO I"   grupo 2: "DAS DISPOSIÇÕES GERAIS"
    (T_CAPITULO,        re.compile(r'^(CAPÍTULO\s+[IVXLCDM]+)\s+(.+)$')),

    # Seção I  Dos Atos de Improbidade...
    # Seção II-A  (se existir)
    # grupo 1: "Seção I"   grupo 2: título da seção
    (T_SECAO,           re.compile(r'^(Seção\s+\S+)\s+(.+)$')),

    # Art. 1º texto...  |  Art. 8º-A texto...  |  Art. 10. texto...  |  Art. 17-B. texto...
    # O ponto final do numeral decimal (Art. 10.) é capturado pelo \.? opcional.
    # grupo 1: "Art. 10"   grupo 2: texto do caput
    (T_ART_CAPUT,       re.compile(r'^(Art\.\s+\d+[ºo°]?(?:-[A-Z])?\.?)\s+(.+)$')),

    # Parágrafo único. texto...
    # grupo 1: "Parágrafo único"   grupo 2: texto
    (T_PARAGRAFO_UNICO, re.compile(r'^(Parágrafo único)\.\s+(.+)$')),

    # § 1º texto...  |  § 10. texto...  |  § 10-A. texto...  |  § 10-B. texto...
    # O \.? final captura o ponto decimal nos parágrafos acima do nono.
    # grupo 1: "§ 10"   grupo 2: texto
    (T_PARAGRAFO,       re.compile(r'^(§\s+\d+[ºo°]?(?:-[A-Z])?\.?)\s+(.+)$')),

    # I - texto...   XIV - texto...   (algarismos romanos maiúsculos)
    # grupo 1: "I"   grupo 2: texto do inciso
    # Atenção: o regex exige pelo menos 1 caractere de conteúdo após o traço
    # para não casar com rótulos nus que escaparam da limpeza.
    (T_INCISO,          re.compile(r'^([IVXLCDM]+)\s+-\s+(.+)$')),

    # a) texto...   b) texto...
    # grupo 1: "a"   grupo 2: texto da alínea
    (T_ALINEA,          re.compile(r'^([a-z])\)\s+(.+)$')),
]


def tokenize(clean_lines: list) -> list:
    """
    Recebe a lista de linhas limpas da Fase 2 e retorna uma lista plana de Tokens.

    Cada linha limpa produz exatamente um Token. Linhas que não casam com nenhum
    padrão são logadas como aviso e ignoradas (não devem ocorrer com o PDF correto).
    """
    tokens = []

    for line in clean_lines:
        matched = False

        for tipo, pattern in _PATTERNS:
            m = pattern.match(line)
            if m:
                # rstrip('.') remove o ponto decimal de rótulos como "Art. 10."
                # e "§ 10-B." sem afetar ordinais ("Art. 1º") nem "Parágrafo único"
                rotulo = m.group(1).strip().rstrip('.')
                conteudo = m.group(2).strip()

                if tipo in (T_CAPITULO, T_SECAO):
                    # Para capítulos e seções, o "conteúdo" é na verdade o título
                    # estrutural (ex: "DAS DISPOSIÇÕES GERAIS"). Guardamos em
                    # `titulo` e deixamos `texto` vazio — eles não geram cards.
                    tokens.append(Token(tipo=tipo, rotulo=rotulo, texto="", titulo=conteudo))
                else:
                    tokens.append(Token(tipo=tipo, rotulo=rotulo, texto=conteudo))

                matched = True
                break

        if not matched:
            # Não deveria acontecer com o PDF correto, mas melhor logar do que
            # perder silenciosamente conteúdo normativo.
            print(f"[WARN] Linha não reconhecida pelo tokenizador: {line!r}")

    return tokens


# ---------------------------------------------------------------------------
# Fase 4: Geração dos cards
# ---------------------------------------------------------------------------

@dataclass
class ArticleGroup:
    """
    Estrutura intermediária que agrupa os tokens de um artigo antes
    da aplicação da árvore de decisão.
    """
    caput: Token
    paragrafo_unico: Optional[Token] = None
    paragrafos: list = field(default_factory=list)          # List[Token]
    incisos_do_caput: list = field(default_factory=list)    # List[Token]
    # Mapa rotulo_paragrafo → lista de incisos daquele parágrafo
    # ex: {"§ 1º": [Token(INCISO, "I", ...), Token(INCISO, "II", ...)]}
    incisos_do_paragrafo: dict = field(default_factory=dict)
    # Mapa rotulo_inciso → lista de alíneas (para incisos do caput)
    # ex: {"IV": [Token(ALINEA, "a", ...), Token(ALINEA, "b", ...)]}
    alineas_do_inciso_caput: dict = field(default_factory=dict)
    # Mapa (rotulo_para, rotulo_inciso) → lista de alíneas (para incisos de parágrafo)
    alineas_do_inciso_para: dict = field(default_factory=dict)
    contexto_capitulo: str = ""   # título do capítulo atual
    contexto_secao: str = ""      # título da seção atual (pode ser vazio)


def _group_articles(tokens: list) -> list:
    """
    Percorre a lista plana de tokens e agrupa-os em ArticleGroups.

    Rastreamos dois ponteiros:
      current_parent_token  — caput ou parágrafo que está coletando incisos
      current_inciso_token  — inciso que está coletando alíneas
    """
    groups = []
    current_group: Optional[ArticleGroup] = None
    current_parent_token: Optional[Token] = None
    current_inciso_token: Optional[Token] = None
    ctx_capitulo = ""
    ctx_secao = ""

    for token in tokens:
        if token.tipo == T_CAPITULO:
            if current_group:
                groups.append(current_group)
                current_group = None
            ctx_capitulo = token.titulo
            ctx_secao = ""
            current_parent_token = None
            current_inciso_token = None

        elif token.tipo == T_SECAO:
            if current_group:
                groups.append(current_group)
                current_group = None
            ctx_secao = token.titulo
            current_parent_token = None
            current_inciso_token = None

        elif token.tipo == T_ART_CAPUT:
            if current_group:
                groups.append(current_group)
            current_group = ArticleGroup(
                caput=token,
                contexto_capitulo=ctx_capitulo,
                contexto_secao=ctx_secao,
            )
            current_parent_token = token
            current_inciso_token = None

        elif token.tipo == T_PARAGRAFO_UNICO:
            if current_group:
                current_group.paragrafo_unico = token
                current_parent_token = token
                current_inciso_token = None

        elif token.tipo == T_PARAGRAFO:
            if current_group:
                current_group.paragrafos.append(token)
                current_parent_token = token
                current_inciso_token = None

        elif token.tipo == T_INCISO:
            if current_group and current_parent_token:
                if current_parent_token.tipo == T_ART_CAPUT:
                    current_group.incisos_do_caput.append(token)
                else:
                    key = current_parent_token.rotulo
                    current_group.incisos_do_paragrafo.setdefault(key, []).append(token)
                current_inciso_token = token  # alíneas seguintes pertencem a este inciso

        elif token.tipo == T_ALINEA:
            if current_group and current_inciso_token and current_parent_token:
                if current_parent_token.tipo == T_ART_CAPUT:
                    # Alínea de inciso do caput
                    key = current_inciso_token.rotulo
                    current_group.alineas_do_inciso_caput.setdefault(key, []).append(token)
                else:
                    # Alínea de inciso de parágrafo
                    key = (current_parent_token.rotulo, current_inciso_token.rotulo)
                    current_group.alineas_do_inciso_para.setdefault(key, []).append(token)

    if current_group:
        groups.append(current_group)

    return groups


def _make_referencia(art_rotulo: str, filho_rotulo: Optional[str] = None,
                     avo_rotulo: Optional[str] = None,
                     bisneto_rotulo: Optional[str] = None) -> str:
    """
    Monta o campo `referencia` do card.

    Exemplos:
        _make_referencia("Art. 9º")                       → "Art. 9º"
        _make_referencia("Art. 9º", "II")                 → "Art. 9º, II"
        _make_referencia("Art. 9º", "§ 1º")               → "Art. 9º, § 1º"
        _make_referencia("Art. 9º", "I", "§ 1º")          → "Art. 9º, § 1º, I"
        _make_referencia("Art. 17-C.", "a", "IV")         → "Art. 17-C., IV, a"
        _make_referencia("Art. X.", "a", "I", "§ 1º")    → "Art. X., § 1º, I, a"
    """
    if bisneto_rotulo:
        # alínea de inciso de parágrafo: art, §, inciso, alínea
        return f"{art_rotulo}, {bisneto_rotulo}, {avo_rotulo}, {filho_rotulo}"
    if avo_rotulo:
        return f"{art_rotulo}, {avo_rotulo}, {filho_rotulo}"
    if filho_rotulo:
        return f"{art_rotulo}, {filho_rotulo}"
    return art_rotulo


def _make_texto_contexto(art_rotulo: str, ctx_secao: str, ctx_capitulo: str) -> str:
    """
    Gera o campo `textoContexto` — o 'header suave' exibido acima do card.

    Usa a seção quando disponível (mais específico); recai no capítulo caso contrário.
    O revisor humano vai condensar este texto para algo mais curto, mas o parser
    já entrega uma versão legível e informativa.
    """
    contexto = ctx_secao if ctx_secao else ctx_capitulo
    if contexto:
        return f"{art_rotulo} — {contexto}"
    return art_rotulo


def _cards_from_group(group: ArticleGroup, ordem_inicial: int) -> tuple:
    """
    Aplica a árvore de decisão a um ArticleGroup e retorna:
        (lista_de_cards, próximo_valor_de_ordem)

    Árvore de decisão:
    - Caput sem filhos                        → ARTIGO_COMPLETO
    - Caput com filhos e termina em '.'       → CAPUT_ISOLADO (+ cards dos filhos)
    - Caput com filhos e termina em ':'       → sem card do caput; incisos → INCISO_COM_CAPUT
    - Parágrafo (qualquer)                    → PARAGRAFO_ISOLADO (padrão revisável)
    - Inciso de parágrafo                     → INCISO_COM_CAPUT (parágrafo = contexto)
    """
    cards = []
    ordem = ordem_inicial
    caput = group.caput

    tem_incisos = bool(group.incisos_do_caput)
    tem_paragrafos = bool(group.paragrafos) or group.paragrafo_unico is not None
    caput_fecha_com_dois_pontos = caput.texto.rstrip().endswith(':')

    texto_ctx = _make_texto_contexto(
        caput.rotulo, group.contexto_secao, group.contexto_capitulo
    )
    # Monta o assunto a partir da seção (o revisor vai refinar)
    assunto = group.contexto_secao or group.contexto_capitulo

    # --- Card do caput ---
    if not tem_incisos and not tem_paragrafos:
        # Artigo simples: apenas o caput, sem filhos → ARTIGO_COMPLETO
        cards.append({
            "referencia": _make_referencia(caput.rotulo),
            "tipo": "ARTIGO_COMPLETO",
            "textoContexto": texto_ctx,
            "textoParent": None,
            "textoOriginal": caput.texto,
            "materiaNome": "Direito Administrativo",
            "assuntoNome": assunto,
            "dificuldade": "MEDIO",
            "ordemEstudo": ordem,
            "ativo": True,
            "variantes": [],
        })
        ordem += 1

    elif not caput_fecha_com_dois_pontos:
        # Caput termina em '.': é uma proposição independente e testável → CAPUT_ISOLADO
        cards.append({
            "referencia": _make_referencia(caput.rotulo),
            "tipo": "CAPUT_ISOLADO",
            "textoContexto": texto_ctx,
            "textoParent": None,
            "textoOriginal": caput.texto,
            "materiaNome": "Direito Administrativo",
            "assuntoNome": assunto,
            "dificuldade": "MEDIO",
            "ordemEstudo": ordem,
            "ativo": True,
            "variantes": [],
        })
        ordem += 1
    # Se caput_fecha_com_dois_pontos: não gera card do caput (ele só é contexto)

    # Texto base do caput sem o ":" final — torna-se textoParent dos incisos.
    caput_base = caput.texto.rstrip(':').rstrip()

    # --- Cards dos incisos do caput ---
    for inciso in group.incisos_do_caput:
        tipo_inciso = "INCISO_COM_CAPUT" if caput_fecha_com_dois_pontos else "INCISO_AUTOSSUFICIENTE"
        inciso_fecha_com_dois_pontos = inciso.texto.rstrip().endswith(':')
        alineas = group.alineas_do_inciso_caput.get(inciso.rotulo, [])
        cards.append({
            "referencia": _make_referencia(caput.rotulo, inciso.rotulo),
            "tipo": tipo_inciso,
            "textoContexto": texto_ctx,
            "textoParent": caput_base if tipo_inciso == "INCISO_COM_CAPUT" else None,
            "textoOriginal": inciso.texto,
            "materiaNome": "Direito Administrativo",
            "assuntoNome": assunto,
            "dificuldade": "MEDIO",
            "ordemEstudo": ordem,
            # Inciso introdutório (termina em ':') só vale como card se não tiver alíneas
            "ativo": not inciso_fecha_com_dois_pontos or not alineas,
            "variantes": [],
        })
        ordem += 1

        # --- Alíneas deste inciso do caput ---
        inciso_base = inciso.texto.rstrip(':').rstrip()
        for alinea in alineas:
            # textoParent das alíneas = o inciso pai (sem os ':')
            # textoContexto = mesmo do artigo
            cards.append({
                "referencia": _make_referencia(caput.rotulo, alinea.rotulo, inciso.rotulo),
                "tipo": "ALINEA_COM_INCISO_E_CAPUT",
                "textoContexto": texto_ctx,
                "textoParent": inciso_base,
                "textoOriginal": alinea.texto,
                "materiaNome": "Direito Administrativo",
                "assuntoNome": assunto,
                "dificuldade": "MEDIO",
                "ordemEstudo": ordem,
                "ativo": True,
                "variantes": [],
            })
            ordem += 1

    # --- Cards dos parágrafos ---
    todos_paragrafos = []
    if group.paragrafo_unico:
        todos_paragrafos.append(group.paragrafo_unico)
    todos_paragrafos.extend(group.paragrafos)

    for para in todos_paragrafos:
        # Parágrafo que termina em ':' é puramente introdutório — não testável sozinho.
        para_fecha_com_dois_pontos = para.texto.rstrip().endswith(':')
        cards.append({
            "referencia": _make_referencia(caput.rotulo, para.rotulo),
            "tipo": "PARAGRAFO_ISOLADO",
            "textoContexto": texto_ctx,
            "textoParent": None,
            "textoOriginal": para.texto,
            "materiaNome": "Direito Administrativo",
            "assuntoNome": assunto,
            "dificuldade": "MEDIO",
            "ordemEstudo": ordem,
            "ativo": not para_fecha_com_dois_pontos,
            "variantes": [],
        })
        ordem += 1

        # --- Cards dos incisos deste parágrafo ---
        para_base = para.texto.rstrip(':').rstrip()
        for inciso in group.incisos_do_paragrafo.get(para.rotulo, []):
            ctx_para = f"{caput.rotulo}, {para.rotulo} — {assunto}"
            inciso_fecha_com_dois_pontos = inciso.texto.rstrip().endswith(':')
            alineas = group.alineas_do_inciso_para.get((para.rotulo, inciso.rotulo), [])
            cards.append({
                "referencia": _make_referencia(caput.rotulo, inciso.rotulo, para.rotulo),
                "tipo": "INCISO_COM_CAPUT",
                "textoContexto": ctx_para,
                "textoParent": para_base,
                "textoOriginal": inciso.texto,
                "materiaNome": "Direito Administrativo",
                "assuntoNome": assunto,
                "dificuldade": "MEDIO",
                "ordemEstudo": ordem,
                "ativo": not inciso_fecha_com_dois_pontos or not alineas,
                "variantes": [],
            })
            ordem += 1

            # --- Alíneas deste inciso de parágrafo ---
            inciso_base = inciso.texto.rstrip(':').rstrip()
            for alinea in alineas:
                cards.append({
                    "referencia": _make_referencia(
                        caput.rotulo, alinea.rotulo, inciso.rotulo, para.rotulo
                    ),
                    "tipo": "ALINEA_COM_INCISO_E_CAPUT",
                    "textoContexto": ctx_para,
                    "textoParent": inciso_base,
                    "textoOriginal": alinea.texto,
                    "materiaNome": "Direito Administrativo",
                    "assuntoNome": assunto,
                    "dificuldade": "MEDIO",
                    "ordemEstudo": ordem,
                    "ativo": True,
                    "variantes": [],
                })
                ordem += 1

    return cards, ordem


def build_cards(tokens: list) -> dict:
    """
    Fase 4 completa: recebe a lista de tokens e retorna o JSON intermediário
    pronto para revisão humana (antes da geração de variantes).

    Estrutura de retorno compatível com o schema definido no SPUK_LEGIS_STATUS.md.
    """
    groups = _group_articles(tokens)

    all_cards = []
    ordem = 1
    for group in groups:
        cards, ordem = _cards_from_group(group, ordem)
        all_cards.extend(cards)

    return {
        "corpus": {
            "sigla": "LEI8429",
            "nome": "Lei de Improbidade Administrativa — Lei 8.429/1992",
            "anoVigencia": 1992,
        },
        "cards": all_cards,
    }


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def parse(pdf_path: str) -> dict:
    """
    Pipeline completo: PDF → JSON de cards.
    Encadeia as quatro fases e retorna o dicionário pronto para serialização.
    """
    raw   = extract_text(pdf_path)
    lines = clean_text(raw)
    tokens = tokenize(lines)
    return build_cards(tokens)


def main():
    """
    CLI: python parser.py <caminho_do_pdf> [--output <arquivo.json>]
    Se --output for omitido, imprime na saída padrão.
    """
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Parser da Lei 8.429/92 — SPUK-LEGIS")
    ap.add_argument("pdf", help="Caminho para o PDF da lei (ex: corpus/lei_8429.pdf)")
    ap.add_argument("--output", "-o", help="Arquivo JSON de saída (padrão: stdout)")
    args = ap.parse_args()

    resultado = parse(args.pdf)

    json_str = json.dumps(resultado, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        total = len(resultado["cards"])
        print(f"✓ {total} cards gerados → {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()