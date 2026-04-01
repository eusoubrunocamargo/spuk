"""
dashboard.py — Dashboard de auditoria do SPUK-LEGIS
Uso: streamlit run dashboard.py

Layout:
  ┌─────────────────────────────────────────────────────────┐
  │  Topbar: corpus · filtro · lista de cards · métricas    │
  ├─────────────────────────────────────────────────────────┤
  │  Ref + status │ ← Ant │ ✓ Aprovar │ ✗ Rejeitar │ → Próx │
  ├───────────────┬────────────────┬────────────────────────┤
  │  Antes swipe  │ Feedback acerto│   Feedback erro        │
  ├───────────────┴────────────────┴────────────────────────┤
  │  ▶ ✏️ Editar campos (expander colapsado)                │
  └─────────────────────────────────────────────────────────┘
"""

import json
import re
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Corpus disponíveis
# ---------------------------------------------------------------------------

CORPUS = {
    "Lei 8.429/1992 — Improbidade Administrativa": "output/lei_8429_full.json",
    #"CF/88 — Constituição Federal":                "output/cf88_cards.json",
}

TIPOS_CARD = [
    "ARTIGO_COMPLETO",
    "CAPUT_ISOLADO",
    "INCISO_COM_CAPUT",
    "INCISO_AUTOSSUFICIENTE",
    "PARAGRAFO_ISOLADO",
    "PARAGRAFO_COM_CAPUT",
    "ALINEA_COM_INCISO_E_CAPUT",
]

DIFICULDADES = ["FACIL", "MEDIO", "DIFICIL"]

MATERIAS = [
    "Direito Constitucional",
    "Direito Administrativo",
    "Direito Penal",
    "Direito Civil",
    "Direito Processual Civil",
    "Direito Processual Penal",
    "Direito Tributário",
    "Direito do Trabalho",
    "Direito Previdenciário",
]

ESTILOS_DESTAQUE = ["MARCA", "NEGRITO", "SUBLINHADO", "MARCA_NEGRITO", "ALERTA"]

# Tokens de cor por tema — espelham o app mobile
TEMAS = {
    "dark": {
        "card_bg":  "#1A1A1A",
        "text":     "#F0EBE1",
        "muted":    "#73757F",
        "tag_bg":   "#2a2a2a",
        "tag_text": "#aaa",
        "parent_bg":"#242424",
        "divider":  "#2e2e2e",
        "border":   "#FF4D4D",
    },
    "light": {
        "card_bg":  "#F0EBE1",
        "text":     "#1A1A1A",
        "muted":    "#999BA5",
        "tag_bg":   "#DDD8CE",
        "tag_text": "#555",
        "parent_bg":"#DAD5CB",
        "divider":  "#C8C3B9",
        "border":   "#FF4D4D",
    },
}

# CSS de cada estilo de destaque por tema
_DESTAQUE_CSS = {
    "light": {
        "MARCA":        "background:rgba(240,192,64,0.45);border-radius:3px;padding:0 3px",
        "NEGRITO":      "font-weight:700",
        "SUBLINHADO":   "text-decoration:underline;text-decoration-color:#1A1A1A;"
                        "text-underline-offset:4px",
        "MARCA_NEGRITO":"background:rgba(240,192,64,0.45);border-radius:3px;"
                        "padding:0 3px;font-weight:700",
        "ALERTA":       "color:#FF4D4D;font-weight:700",
    },
    "dark": {
        "MARCA":        "background:#F0C040;color:#1A1A1A;border-radius:3px;"
                        "padding:0 3px;font-weight:700",
        "NEGRITO":      "font-weight:700",
        "SUBLINHADO":   "text-decoration:underline;text-decoration-color:#2ECC71;"
                        "text-underline-offset:3px",
        "MARCA_NEGRITO":"background:#F0C040;color:#1A1A1A;border-radius:3px;"
                        "padding:0 3px;font-weight:700",
        "ALERTA":       "color:#FF4D4D;font-weight:700",
    },
}

# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def json_path() -> Path:
    return Path(st.session_state.get("corpus_path", list(CORPUS.values())[0]))


def load_data() -> dict:
    with open(json_path(), encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict):
    with open(json_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Estado da sessão
# ---------------------------------------------------------------------------

def init_state(corpus_path: str):
    if st.session_state.get("corpus_path") != corpus_path:
        st.session_state.corpus_path = corpus_path
        st.session_state.pop("data", None)
        st.session_state.pop("idx", None)
        st.session_state.pop("edit_card_idx", None)
        st.session_state.saved_msg = ""

    if "data" not in st.session_state:
        st.session_state.data = load_data()

    if "idx" not in st.session_state:
        cards = st.session_state.data["cards"]
        pendentes = [i for i, c in enumerate(cards) if not c.get("auditoriaAprovada")]
        st.session_state.idx = pendentes[0] if pendentes else 0

    if "saved_msg" not in st.session_state:
        st.session_state.saved_msg = ""


def _reset_edit_state(card: dict):
    """Sincroniza os campos de edição com o card atual. Chamado ao navegar."""
    variante_correta = next(
        (v for v in card.get("variantes", []) if v.get("correto")), None
    )
    destaques_atuais = (variante_correta.get("destaques") or []) if variante_correta else []
    st.session_state.update({
        "edit_tipo":                     card.get("tipo", TIPOS_CARD[0]),
        "edit_contexto":                 card.get("textoContexto", ""),
        "edit_assunto":                  card.get("assuntoNome", ""),
        "edit_dificuldade":              card.get("dificuldade", "MEDIO"),
        "edit_materia":                  card.get("materiaNome", MATERIAS[0]),
        "edit_texto_original":           card.get("textoOriginal", ""),
        "edit_texto_chain":              card.get("textoChain", "") or "",
        "edit_texto_parent":             card.get("textoParent", "") or "",
        "edit_texto_parent_enriquecido": card.get("textoParentEnriquecido", "") or "",
        "edit_ativo":                    card.get("ativo", True),
        "edit_destaques":                _destaques_to_textarea(destaques_atuais),
        "edit_card_idx":                 st.session_state.idx,
    })


# ---------------------------------------------------------------------------
# Helpers gerais
# ---------------------------------------------------------------------------

def current_card() -> dict:
    return st.session_state.data["cards"][st.session_state.idx]


def total_cards() -> int:
    return len(st.session_state.data["cards"])


def count_auditados() -> int:
    return sum(1 for c in st.session_state.data["cards"] if "auditadoEm" in c)


def count_aprovados() -> int:
    return sum(1 for c in st.session_state.data["cards"] if c.get("auditoriaAprovada"))


def navigate(delta: int):
    novo = st.session_state.idx + delta
    st.session_state.idx = max(0, min(novo, total_cards() - 1))
    st.session_state.saved_msg = ""


_CROSS_REF_RE = re.compile(
    r'\b(?:previsto|referido|mencionado|constante|disposto|'
    r'nos\s+termos|na\s+forma)\s+(?:no|nos|na|nas|do|dos|da|das)?\s*'
    r'(?:inciso|art\.?|artigo|parágrafo|§|alínea)',
    re.IGNORECASE,
)


def _has_cross_ref(texto: str | None) -> bool:
    if not texto:
        return False
    return bool(_CROSS_REF_RE.search(texto))


def apply_and_save(card: dict, updates: dict, aprovada: bool):
    card.update(updates)
    card["auditoriaAprovada"] = aprovada
    card["auditadoEm"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_data(st.session_state.data)
    st.session_state.saved_msg = "✓ Salvo" if aprovada else "✗ Rejeitado"


def _build_updates(card: dict) -> dict:
    """Monta o dict de updates a partir dos valores atuais dos widgets de edição."""
    novos_destaques = _parse_destaques_raw(
        st.session_state.get("edit_destaques", "")
    )
    variantes_atualizadas = []
    for v in card.get("variantes", []):
        if v.get("correto"):
            variantes_atualizadas.append({
                **v,
                "destaques": novos_destaques or v.get("destaques", []),
            })
        else:
            variantes_atualizadas.append(v)

    return {
        "tipo":                   st.session_state.get("edit_tipo", card["tipo"]),
        "textoContexto":          st.session_state.get("edit_contexto", card["textoContexto"]),
        "textoOriginal":          st.session_state.get("edit_texto_original", card["textoOriginal"]),
        "textoParent":            st.session_state.get("edit_texto_parent") or card.get("textoParent"),
        "textoChain":             st.session_state.get("edit_texto_chain", ""),
        "textoParentEnriquecido": st.session_state.get("edit_texto_parent_enriquecido") or None,
        "assuntoNome":            st.session_state.get("edit_assunto", card["assuntoNome"]),
        "dificuldade":            st.session_state.get("edit_dificuldade", card["dificuldade"]),
        "materiaNome":            st.session_state.get("edit_materia", card.get("materiaNome")),
        "ativo":                  st.session_state.get("edit_ativo", card.get("ativo", True)),
        "variantes":              variantes_atualizadas,
    }


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_destaques_raw(raw: str) -> list:
    """
    Converte o texto do textarea em lista de dicts.
    Formato: "texto::ESTILO" por linha.
    Sem sufixo '::' → estilo = MARCA (retrocompatível).
    """
    result = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "::" in line:
            texto, estilo = line.rsplit("::", 1)
            estilo = estilo.strip().upper()
            if estilo not in ESTILOS_DESTAQUE:
                estilo = "MARCA"
        else:
            texto, estilo = line, "MARCA"
        result.append({"texto": texto.strip(), "estilo": estilo})
    return result


def _destaques_to_textarea(destaques: list) -> str:
    """
    Converte lista de dicts (ou strings do formato antigo) para o formato
    'texto::ESTILO' do textarea — um por linha.
    """
    lines = []
    for d in destaques:
        if isinstance(d, str):
            lines.append(f"{d}::MARCA")
        else:
            lines.append(f"{d['texto']}::{d.get('estilo', 'MARCA')}")
    return "\n".join(lines)


def _apply_highlights(texto: str, destaques: list, theme: str = "dark") -> str:
    """
    Envolve cada destaque com <span> cujo CSS depende do estilo e do tema.
    Aceita tanto list[dict] (novo formato) quanto list[str] (formato antigo).
    Processa do maior para o menor trecho para evitar sobreposições parciais.
    """
    resultado = _esc(texto)
    css_map = _DESTAQUE_CSS.get(theme, _DESTAQUE_CSS["dark"])

    def sort_key(d):
        return len(d["texto"] if isinstance(d, dict) else d)

    for d in sorted(destaques, key=sort_key, reverse=True):
        texto_d = d["texto"] if isinstance(d, dict) else d
        estilo  = d.get("estilo", "MARCA") if isinstance(d, dict) else "MARCA"
        css     = css_map.get(estilo, css_map["MARCA"])
        d_esc   = _esc(texto_d)
        resultado = resultado.replace(
            d_esc,
            f'<span style="{css}">{d_esc}</span>',
            1,
        )
    return resultado


def _apply_erro_markup(texto_apresentado: str,
                       trecho_alterado: str | None,
                       trecho_original: str | None) -> str:
    """
    Substitui trechoAlterado por:
      [trechoAlterado em vermelho tachado] [trechoOriginal em verde]
    """
    resultado = _esc(texto_apresentado)
    if trecho_alterado and trecho_original:
        old_esc = _esc(trecho_alterado)
        new_esc = _esc(trecho_original)
        markup = (
            f'<span style="color:#FF6B6B;text-decoration:line-through;'
            f'opacity:0.85">{old_esc}</span>'
            f'&thinsp;<span style="color:#2ECC71;font-weight:700">{new_esc}</span>'
        )
        resultado = resultado.replace(old_esc, markup, 1)
    return resultado


def _card_shell(
    label: str,
    label_color: str,
    contexto: str,
    texto_pai: str,
    texto_html: str,
    tipo: str,
    dif_cor: str,
    dificuldade: str,
    footer_html: str = "",
    height: int = 440,
    theme: str = "dark",
) -> str:
    """
    Template HTML de card mobile.
    texto_html pode conter tags <span> e <mark> (não é re-escapado aqui).
    theme: "dark" | "light" — aplica os tokens de cor do app mobile.
    """
    t = TEMAS.get(theme, TEMAS["dark"])
    tipo_label = tipo.replace("_", " ")
    parent_block = ""
    if texto_pai:
        parent_block = f"""
        <p style="font-size:11px;font-weight:400;color:{t['muted']};line-height:1.5;
            margin:0 0 10px 0;padding:7px 10px;background:{t['parent_bg']};
            border-radius:8px;border-left:3px solid {t['border']};">{_esc(texto_pai)}</p>"""

    return f"""
    <div style="display:flex;flex-direction:column;align-items:center;padding:2px 0 4px 0;">
        <p style="font-size:10px;font-weight:900;letter-spacing:0.12em;
            text-transform:uppercase;color:{label_color};margin:0 0 6px 0;">{label}</p>
        <div style="background:{t['card_bg']};border-radius:22px;width:100%;
            display:flex;flex-direction:column;padding:18px 16px 14px 16px;
            box-shadow:0 4px 20px rgba(0,0,0,0.2);">
            <div style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;">
                <span style="font-size:9px;font-weight:900;letter-spacing:0.1em;
                    text-transform:uppercase;color:{t['tag_text']};background:{t['tag_bg']};
                    border-radius:20px;padding:3px 8px;">{tipo_label}</span>
                <span style="font-size:9px;font-weight:900;letter-spacing:0.1em;
                    text-transform:uppercase;color:{dif_cor};background:{t['tag_bg']};
                    border-radius:20px;padding:3px 8px;">{dificuldade}</span>
            </div>
            <p style="font-size:11px;font-weight:700;letter-spacing:0.05em;
                text-transform:uppercase;color:#FF4D4D;margin:0 0 8px 0;
                line-height:1.3;">{_esc(contexto)}</p>
            {parent_block}
            <p style="font-size:14px;font-weight:400;color:{t['text']};
                line-height:1.6;margin:0;">{texto_html}</p>
            {footer_html}
        </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Renders das três colunas de preview
# ---------------------------------------------------------------------------

def _texto_pai(card: dict) -> str:
    return (
        card.get("textoParentEnriquecido")
        or card.get("textoChain")
        or card.get("textoParent")
        or ""
    )


def _dif_cor(card: dict) -> str:
    return {"FACIL": "#4CAF50", "MEDIO": "#FF9800", "DIFICIL": "#FF4D4D"}.get(
        card.get("dificuldade", "MEDIO"), "#888"
    )


def render_preview_antes(card: dict, height: int = 440):
    """Col 1 — card como o usuário vê antes de fazer o swipe."""
    footer = """
    <hr style="border:none;border-top:1px solid #2e2e2e;margin:14px 0 10px 0;">
    <div style="display:flex;gap:10px;">
        <button style="flex:1;background:#2a2a2a;border:2px solid #444;
            border-radius:14px;color:#F0F0F0;font-size:12px;font-weight:900;
            letter-spacing:0.05em;text-transform:uppercase;padding:12px 0;
            cursor:default;">← Errado</button>
        <button style="flex:1;background:#FF4D4D;border:none;border-radius:14px;
            color:#fff;font-size:12px;font-weight:900;letter-spacing:0.05em;
            text-transform:uppercase;padding:12px 0;cursor:default;">Correto →</button>
    </div>"""
    html = _card_shell(
        label="ANTES DO SWIPE", label_color="#666",
        contexto=card.get("textoContexto", ""),
        texto_pai=_texto_pai(card),
        texto_html=_esc(card.get("textoOriginal", "")),
        tipo=card.get("tipo", ""),
        dif_cor=_dif_cor(card),
        dificuldade=card.get("dificuldade", "MEDIO"),
        footer_html=footer,
        height=height,
    )
    components.html(html, height=height, scrolling=False)


def render_feedback_acerto(card: dict, height: int = 440):
    """
    Col 2 — feedback quando o usuário acerta. Tema light (#F0EBE1).
    Destaques respeitam estilo por item (MARCA / NEGRITO / SUBLINHADO / MARCA_NEGRITO).
    """
    variante_correta = next(
        (v for v in card.get("variantes", []) if v.get("correto")), None
    )

    if not variante_correta:
        st.info("Variante correta não gerada para este card.")
        return

    dif_cor = {"FACIL": "#4CAF50", "MEDIO": "#FF9800", "DIFICIL": "#FF4D4D"}.get(
        card.get("dificuldade", "MEDIO"), "#888"
    )
    destaques = variante_correta.get("destaques") or []
    texto_html = _apply_highlights(variante_correta["textoApresentado"], destaques, theme="light")
    footer = f"""
    <hr style="border:none;border-top:1px solid {TEMAS['light']['divider']};margin:14px 0 10px 0;">
    <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:18px;">✅</span>
        <span style="font-size:11px;font-weight:700;color:#2ECC71;
            letter-spacing:0.06em;text-transform:uppercase;">Correto!</span>
    </div>"""
    html = _card_shell(
        label="FEEDBACK — ACERTO", label_color="#2ECC71",
        contexto=card.get("textoContexto", ""),
        texto_pai=_texto_pai(card),
        texto_html=texto_html,
        tipo=card.get("tipo", ""),
        dif_cor=dif_cor,
        dificuldade=card.get("dificuldade", "MEDIO"),
        footer_html=footer,
        height=height,
        theme="light",
    )
    components.html(html, height=height, scrolling=False)

    # Textarea de destaques com hint de sintaxe
    st.text_area(
        "Destaques (um por linha — formato: trecho::ESTILO)",
        key="edit_destaques",
        height=90,
        help=(
            "Estilos disponíveis: MARCA · NEGRITO · SUBLINHADO · MARCA_NEGRITO\n"
            "Sem sufixo → MARCA por padrão.\n"
            "Ex:\ndolo::NEGRITO\nvontade livre e consciente::NEGRITO\n"
            "não bastando a voluntariedade do agente::SUBLINHADO"
        ),
    )


def render_feedback_erro(card: dict, height: int = 440):
    """
    Col 3 — feedback quando o usuário erra. Tema dark (#1A1A1A).
    trechoAlterado em vermelho tachado · trechoOriginal em verde.
    """
    variantes_incorretas = [v for v in card.get("variantes", []) if not v.get("correto")]

    if not variantes_incorretas:
        st.info("Variantes incorretas não geradas para este card.")
        return

    opcoes = [
        f"{v.get('tipoArmadilha', '?')} — "
        + (v["trechoAlterado"][:45] + "…" if len(v.get("trechoAlterado", "")) > 45
           else v.get("trechoAlterado", "?"))
        for v in variantes_incorretas
    ]
    escolha = st.selectbox(
        "Variante incorreta",
        range(len(opcoes)),
        format_func=lambda x: opcoes[x],
        key="err_variante_idx",
        label_visibility="collapsed",
    )
    v = variantes_incorretas[escolha]
    texto_html = _apply_erro_markup(
        v["textoApresentado"],
        v.get("trechoAlterado"),
        v.get("trechoOriginal"),
    )
    footer = f"""
    <hr style="border:none;border-top:1px solid {TEMAS['dark']['divider']};margin:14px 0 10px 0;">
    <div style="display:flex;align-items:center;gap:8px;">
        <span style="font-size:18px;">❌</span>
        <span style="font-size:11px;font-weight:700;color:#FF4D4D;
            letter-spacing:0.06em;text-transform:uppercase;">
            Errado — {_esc(v.get('tipoArmadilha') or '')}
        </span>
    </div>"""
    html = _card_shell(
        label="FEEDBACK — ERRO", label_color="#FF4D4D",
        contexto=card.get("textoContexto", ""),
        texto_pai=_texto_pai(card),
        texto_html=texto_html,
        tipo=card.get("tipo", ""),
        dif_cor=_dif_cor(card),
        dificuldade=card.get("dificuldade", "MEDIO"),
        footer_html=footer,
        height=height,
        theme="dark",
    )
    components.html(html, height=height, scrolling=False)


# ---------------------------------------------------------------------------
# Topbar horizontal
# ---------------------------------------------------------------------------

def render_topbar(cards: list):
    """Barra superior com corpus, filtro, lista de navegação e métricas."""
    total  = total_cards()
    audits = count_auditados()
    aprovs = count_aprovados()

    corpus_atual      = st.session_state.get("corpus_path", list(CORPUS.values())[0])
    corpus_labels     = list(CORPUS.keys())
    corpus_atual_label = next(
        (k for k, v in CORPUS.items() if v == corpus_atual), corpus_labels[0]
    )

    col_title, col_corpus, col_filtro, col_lista, col_metrics = st.columns(
        [1, 2, 2, 5, 3], gap="small"
    )

    with col_title:
        st.markdown("**SPUK** · Auditoria")

    with col_corpus:
        escolha_corpus = st.selectbox(
            "Corpus",
            corpus_labels,
            index=corpus_labels.index(corpus_atual_label),
            label_visibility="collapsed",
        )
        novo_path = CORPUS[escolha_corpus]
        if novo_path != corpus_atual:
            if not Path(novo_path).exists():
                st.error(f"Não encontrado: `{novo_path}`")
            else:
                st.session_state.corpus_path = novo_path
                st.rerun()

    FILTROS = [
        "Todos", "Pendentes", "Aprovados", "Rejeitados",
        "PARAGRAFO_ISOLADO", "CAPUT_ISOLADO", "ARTIGO_COMPLETO",
        "INCISO_COM_CAPUT", "INCISO_AUTOSSUFICIENTE", "ALINEA_COM_INCISO_E_CAPUT",
    ]

    with col_filtro:
        filtro = st.selectbox(
            "Filtro",
            FILTROS,
            key="filtro_ativo",
            label_visibility="collapsed",
        )

    def match(c):
        if filtro == "Pendentes":  return "auditadoEm" not in c
        if filtro == "Aprovados":  return c.get("auditoriaAprovada") is True
        if filtro == "Rejeitados": return c.get("auditoriaAprovada") is False
        if filtro in TIPOS_CARD:   return c.get("tipo") == filtro
        return True

    indices_filtrados = [i for i, c in enumerate(cards) if match(c)]

    with col_lista:
        if indices_filtrados:
            labels = []
            for i in indices_filtrados:
                c = cards[i]
                icon = "✓" if c.get("auditoriaAprovada") else ("✗" if "auditadoEm" in c else "·")
                labels.append(f"{icon} [{i+1:04d}] {c['referencia']}")

            current_pos = (
                indices_filtrados.index(st.session_state.idx)
                if st.session_state.idx in indices_filtrados else 0
            )
            escolha = st.selectbox(
                f"{len(indices_filtrados)} cards",
                range(len(labels)),
                index=current_pos,
                format_func=lambda x: labels[x],
                label_visibility="collapsed",
            )
            if indices_filtrados[escolha] != st.session_state.idx:
                st.session_state.idx = indices_filtrados[escolha]
                st.session_state.saved_msg = ""
                st.rerun()
        else:
            st.caption("Nenhum card neste filtro.")

    with col_metrics:
        pct = int(audits / total * 100) if total else 0
        st.caption(
            f"**{audits}/{total}** auditados ({pct}%) · **{aprovs}** aprovados"
        )
        st.progress(audits / total if total else 0)


# ---------------------------------------------------------------------------
# Editor principal
# ---------------------------------------------------------------------------

def render_card_editor(card: dict):
    idx   = st.session_state.idx
    total = total_cards()

    # Sincroniza campos de edição ao trocar de card
    if st.session_state.get("edit_card_idx") != idx:
        _reset_edit_state(card)

    # --- Linha de referência + ações ---
    col_ref, col_ant, col_apr, col_rej, col_prox, col_msg = st.columns(
        [4, 1, 2, 2, 1, 2], gap="small"
    )

    with col_ref:
        status_icon = (
            "✅" if card.get("auditoriaAprovada") is True
            else ("❌" if "auditadoEm" in card else "⏳")
        )
        ativo_tag = "" if card.get("ativo", True) else " · 🔕 inativo"
        st.markdown(
            f"**{card['referencia']}** &nbsp;{status_icon}&nbsp; "
            f"<span style='color:#888;font-size:12px'>"
            f"card {idx+1}/{total} · ordem {card['ordemEstudo']}{ativo_tag}"
            f"</span>",
            unsafe_allow_html=True,
        )

    updates = _build_updates(card)

    with col_ant:
        if st.button("← Ant", use_container_width=True, disabled=(idx == 0)):
            navigate(-1)
            st.rerun()

    with col_apr:
        if st.button("✓ Aprovar", type="primary", use_container_width=True):
            apply_and_save(card, updates, aprovada=True)
            if idx < total - 1:
                navigate(1)
            st.rerun()

    with col_rej:
        if st.button("✗ Rejeitar", use_container_width=True):
            apply_and_save(card, updates, aprovada=False)
            if idx < total - 1:
                navigate(1)
            st.rerun()

    with col_prox:
        if st.button("Próx →", use_container_width=True, disabled=(idx == total - 1)):
            navigate(1)
            st.rerun()

    with col_msg:
        if st.session_state.saved_msg:
            if "✓" in st.session_state.saved_msg:
                st.success(st.session_state.saved_msg)
            else:
                st.error(st.session_state.saved_msg)

    # --- Três colunas de preview ---
    PREVIEW_HEIGHT = 440
    col_antes, col_acerto, col_erro = st.columns(3, gap="medium")

    with col_antes:
        render_preview_antes(card, height=PREVIEW_HEIGHT)

    with col_acerto:
        render_feedback_acerto(card, height=PREVIEW_HEIGHT)

    with col_erro:
        render_feedback_erro(card, height=PREVIEW_HEIGHT)

    # --- Expander de edição ---
    cross_ref_alerta = (
        _has_cross_ref(card.get("textoParent"))
        and not card.get("textoParentEnriquecido")
    )
    expander_label = "✏️ Editar campos" + (" ⚠️ referência cruzada detectada" if cross_ref_alerta else "")

    with st.expander(expander_label, expanded=False):
        ec1, ec2 = st.columns(2, gap="large")

        with ec1:
            st.selectbox("Tipo", TIPOS_CARD, key="edit_tipo",
                help="Altere para PARAGRAFO_COM_CAPUT se o parágrafo excepciona o caput.")
            st.text_input("textoContexto", key="edit_contexto",
                help="Header exibido ao usuário. Condense para 'Art. 9º — Título'.")
            st.text_input("assuntoNome", key="edit_assunto")
            st.selectbox("Dificuldade", DIFICULDADES, key="edit_dificuldade")
            st.selectbox("Matéria", MATERIAS, key="edit_materia")
            st.checkbox("Ativo", key="edit_ativo",
                help="Desmarque para excluir da geração de variantes.")
            if "auditadoEm" in card:
                st.caption(f"Auditado em: {card['auditadoEm']}")

        with ec2:
            st.text_area("textoOriginal", key="edit_texto_original", height=100,
                help="Texto da lei. Edite só para corrigir erros de extração do PDF.")

            if card.get("textoChain") or card.get("textoParent"):
                st.text_input("textoChain  (avô > pai)", key="edit_texto_chain",
                    help="Cadeia hierárquica completa. Edite se incompleta.")

            if card.get("textoParent"):
                st.text_area("textoParent  (pai imediato)", key="edit_texto_parent",
                    height=70, help="Edite só para corrigir erros de extração.")

            if card.get("textoParent") or card.get("textoChain"):
                if cross_ref_alerta:
                    st.warning(
                        "⚠️ O textoParent contém referência a outro dispositivo. "
                        "Preencha o campo abaixo com o contexto resolvido.",
                        icon=None,
                    )
                st.text_area(
                    "textoParentEnriquecido  (contexto resolvido)",
                    key="edit_texto_parent_enriquecido",
                    height=80,
                    help=(
                        "Preencha quando o textoParent referencia outro artigo. "
                        "Ex: 'O imposto previsto no inciso III "
                        "(renda e proventos de qualquer natureza)'"
                    ),
                )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="SPUK — Auditoria",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Oculta a sidebar — toda navegação está no topbar
    st.markdown(
        "<style>[data-testid='stSidebar']{display:none}</style>",
        unsafe_allow_html=True,
    )

    corpus_path = st.session_state.get("corpus_path", list(CORPUS.values())[0])

    if not Path(corpus_path).exists():
        st.error(f"Arquivo não encontrado: `{corpus_path}`")
        st.info("Execute o parser para gerar o JSON do corpus selecionado.")
        st.stop()

    init_state(corpus_path)
    cards = st.session_state.data["cards"]
    render_topbar(cards)
    st.divider()
    render_card_editor(current_card())


if __name__ == "__main__":
    main()