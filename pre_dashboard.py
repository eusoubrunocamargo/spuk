"""
pre_dashboard.py — Auditoria de campos de texto (pré-variantes)
Uso: streamlit run pre_dashboard.py

Layout:
  ┌─────────────────────────────────────────────────────────────┐
  │  Topbar: corpus · filtro · lista · métricas                  │
  ├──────────────────────────────────────────────────────────── │
  │  Ref + status  │ ← Ant  │ ✓ Aprovar │ ✗ Rejeitar │ Próx →  │
  ├──────────────────────────┬──────────────────────────────────┤
  │  Preview (app mobile)    │  Campos editáveis                │
  └──────────────────────────┴──────────────────────────────────┘

Atalhos de teclado:
  ← / →   navegar   |   A   aprovar e avançar   |   R   rejeitar e avançar
"""

import json
import re
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

CORPUS = {
    "CF/88 — Constituição Federal":                "output/cf88_cards.json",
    "Lei 8.429/1992 — Improbidade Administrativa": "output/lei_8429_cards.json",
}

TIPOS_CARD = [
    "ARTIGO_COMPLETO", "CAPUT_ISOLADO", "INCISO_COM_CAPUT",
    "INCISO_AUTOSSUFICIENTE", "PARAGRAFO_ISOLADO",
    "PARAGRAFO_COM_CAPUT", "ALINEA_COM_INCISO_E_CAPUT",
]

DIFICULDADES = ["FACIL", "MEDIO", "DIFICIL"]

MATERIAS = [
    "Direito Constitucional", "Direito Administrativo", "Direito Penal",
    "Direito Civil", "Direito Processual Civil", "Direito Processual Penal",
    "Direito Tributário", "Direito do Trabalho", "Direito Previdenciário",
]

# Tokens dark (preview espelha o app antes do swipe)
T = {
    "card_bg":   "#1A1A1A",
    "text":      "#F0EBE1",
    "muted":     "#73757F",
    "tag_bg":    "#2a2a2a",
    "tag_text":  "#aaa",
    "parent_bg": "#242424",
    "divider":   "#2e2e2e",
    "border":    "#FF4D4D",
}

FILTROS = [
    "Pendentes", "Todos", "Aprovados", "Rejeitados",
    "PARAGRAFO_ISOLADO", "CAPUT_ISOLADO", "ARTIGO_COMPLETO",
    "INCISO_COM_CAPUT", "INCISO_AUTOSSUFICIENTE", "ALINEA_COM_INCISO_E_CAPUT",
]

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
# Estado
# ---------------------------------------------------------------------------

def init_state(corpus_path: str):
    if st.session_state.get("corpus_path") != corpus_path:
        st.session_state.corpus_path = corpus_path
        for k in ("data", "idx", "pre_card_idx"):
            st.session_state.pop(k, None)
        st.session_state.saved_msg = ""

    if "data" not in st.session_state:
        st.session_state.data = load_data()

    if "idx" not in st.session_state:
        cards = st.session_state.data["cards"]
        pendentes = [i for i, c in enumerate(cards) if not c.get("auditoriaAprovada")]
        st.session_state.idx = pendentes[0] if pendentes else 0

    if "saved_msg" not in st.session_state:
        st.session_state.saved_msg = ""


def _sync(card: dict):
    """Carrega os valores do card nos campos de edição."""
    st.session_state.update({
        "pre_assunto":    card.get("assuntoNome", ""),
        "pre_contexto":   card.get("textoContexto", ""),
        "pre_chain":      card.get("textoChain", "") or "",
        "pre_enriquecido":card.get("textoParentEnriquecido", "") or "",
        "pre_original":   card.get("textoOriginal", ""),
        "pre_tipo":       card.get("tipo", TIPOS_CARD[0]),
        "pre_dificuldade":card.get("dificuldade", "MEDIO"),
        "pre_ativo":      card.get("ativo", True),
        "pre_card_idx":   st.session_state.idx,
    })

# ---------------------------------------------------------------------------
# Helpers
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
    st.session_state.idx = max(0, min(st.session_state.idx + delta, total_cards() - 1))
    st.session_state.saved_msg = ""

_CROSS_REF_RE = re.compile(
    r'\b(?:previsto|referido|mencionado|constante|disposto|'
    r'nos\s+termos|na\s+forma)\s+(?:no|nos|na|nas|do|dos|da|das)?\s*'
    r'(?:inciso|art\.?|artigo|parágrafo|§|alínea)',
    re.IGNORECASE,
)

def _has_cross_ref(texto: str | None) -> bool:
    return bool(_CROSS_REF_RE.search(texto)) if texto else False

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _build_updates() -> dict:
    return {
        "tipo":                   st.session_state.get("pre_tipo"),
        "assuntoNome":            st.session_state.get("pre_assunto", ""),
        "textoContexto":          st.session_state.get("pre_contexto", ""),
        "textoChain":             st.session_state.get("pre_chain", ""),
        "textoParentEnriquecido": st.session_state.get("pre_enriquecido") or None,
        "textoOriginal":          st.session_state.get("pre_original", ""),
        "dificuldade":            st.session_state.get("pre_dificuldade", "MEDIO"),
        "ativo":                  st.session_state.get("pre_ativo", True),
    }

def apply_and_save(card: dict, aprovada: bool):
    card.update(_build_updates())
    card["auditoriaAprovada"] = aprovada
    card["auditadoEm"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_data(st.session_state.data)
    st.session_state.saved_msg = "✓ Salvo" if aprovada else "✗ Rejeitado"

# ---------------------------------------------------------------------------
# Preview HTML — imita a tela do app (dark theme, antes do swipe)
# ---------------------------------------------------------------------------

def render_preview(card: dict, height: int = 460):
    referencia  = _esc(card.get("referencia", ""))
    contexto    = _esc(st.session_state.get("pre_contexto", card.get("textoContexto", "")))
    assunto     = _esc(st.session_state.get("pre_assunto",  card.get("assuntoNome", "")))
    original    = _esc(st.session_state.get("pre_original", card.get("textoOriginal", "")))
    tipo        = (st.session_state.get("pre_tipo", card.get("tipo", "")) or "").replace("_", " ")
    dif         = st.session_state.get("pre_dificuldade", card.get("dificuldade", "MEDIO"))
    dif_cor     = {"FACIL": "#4CAF50", "MEDIO": "#FF9800", "DIFICIL": "#FF4D4D"}.get(dif, "#888")
    ativo       = st.session_state.get("pre_ativo", card.get("ativo", True))

    chain       = st.session_state.get("pre_chain", card.get("textoChain", "")) or ""
    enriquecido = st.session_state.get("pre_enriquecido", card.get("textoParentEnriquecido", "")) or ""
    parent_raw  = enriquecido or chain or card.get("textoParent", "") or ""
    parent_block = ""
    if parent_raw:
        parent_block = f"""
        <p style="font-size:15px;color:{T['muted']};line-height:1.5;margin:0 0 10px 0;
            padding:7px 10px;background:{T['parent_bg']};border-radius:8px;
            border-left:3px solid {T['border']};word-break:break-word;">{_esc(parent_raw)}</p>"""

    inativo_badge = "" if ativo else (
        f'<span style="font-size:9px;font-weight:900;letter-spacing:0.08em;'
        f'text-transform:uppercase;color:#FF9800;background:{T["tag_bg"]};'
        f'border-radius:20px;padding:3px 8px;">🔕 INATIVO</span>'
    )

    html = f"""
    <style>
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{ margin: 0; overflow-x: hidden; background: transparent; }}
    </style>
    <div style="width:100%;overflow-x:hidden;padding:2px 2px 4px 2px;">
        <div style="background:{T['card_bg']};border-radius:18px;width:100%;
            display:flex;flex-direction:column;padding:16px 16px 14px 16px;
            box-shadow:0 4px 20px rgba(0,0,0,0.4);">

            <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:8px;">
                <span style="font-size:13px;font-weight:900;letter-spacing:0.04em;
                    color:{T['muted']}">{referencia}</span>
                <div style="display:flex;gap:5px;flex-wrap:wrap;">
                    <span style="font-size:9px;font-weight:900;letter-spacing:0.08em;
                        text-transform:uppercase;color:{T['tag_text']};background:{T['tag_bg']};
                        border-radius:20px;padding:2px 8px;">{tipo}</span>
                    <span style="font-size:9px;font-weight:900;letter-spacing:0.08em;
                        text-transform:uppercase;color:{dif_cor};background:{T['tag_bg']};
                        border-radius:20px;padding:2px 8px;">{dif}</span>
                    {inativo_badge}
                </div>
            </div>

            <p style="font-size:15px;font-weight:700;letter-spacing:0.05em;
                text-transform:uppercase;color:#FF4D4D;margin:0 0 2px 0;
                line-height:1.3;word-break:break-word;">{contexto}</p>

            <p style="font-size:15px;color:{T['muted']};margin:0 0 10px 0;
                letter-spacing:0.02em;">{assunto}</p>

            {parent_block}

            <hr style="border:none;border-top:1px solid {T['divider']};margin:0 0 10px 0;">

            <p style="font-size:14px;font-weight:400;color:{T['text']};
                line-height:1.65;margin:0;word-break:break-word;">{original}</p>
        </div>
    </div>
    """
    components.html(html, height=height, scrolling=True)



# ---------------------------------------------------------------------------
# Topbar
# ---------------------------------------------------------------------------

def render_topbar(cards: list):
    total  = total_cards()
    audits = count_auditados()
    aprovs = count_aprovados()
    pct    = int(audits / total * 100) if total else 0

    corpus_atual       = st.session_state.get("corpus_path", list(CORPUS.values())[0])
    corpus_labels      = list(CORPUS.keys())
    corpus_atual_label = next(
        (k for k, v in CORPUS.items() if v == corpus_atual), corpus_labels[0]
    )

    # Aplica CSS para evitar quebra de linha nos selects da topbar
    st.markdown("""
        <style>
        div[data-testid="stHorizontalBlock"] > div:first-child p {
            white-space: nowrap;
            font-size: 13px;
            font-weight: 700;
            line-height: 2.4;
        }
        </style>
    """, unsafe_allow_html=True)

    col_corpus, col_filtro, col_lista, col_metrics = st.columns(
        [2, 1.5, 5, 3], gap="small"
    )

    with col_corpus:
        escolha = st.selectbox(
            "Corpus", corpus_labels,
            index=corpus_labels.index(corpus_atual_label),
            label_visibility="collapsed",
        )
        novo_path = CORPUS[escolha]
        if novo_path != corpus_atual:
            if not Path(novo_path).exists():
                st.error(f"Não encontrado: `{novo_path}`")
            else:
                st.session_state.corpus_path = novo_path
                st.rerun()

    with col_filtro:
        filtro = st.selectbox(
            "Filtro", FILTROS, key="pre_filtro",
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

            pos = (
                indices_filtrados.index(st.session_state.idx)
                if st.session_state.idx in indices_filtrados else 0
            )
            escolha_card = st.selectbox(
                f"{len(indices_filtrados)} cards",
                range(len(labels)),
                index=pos,
                format_func=lambda x: labels[x],
                label_visibility="collapsed",
            )
            if indices_filtrados[escolha_card] != st.session_state.idx:
                st.session_state.idx = indices_filtrados[escolha_card]
                st.session_state.saved_msg = ""
                st.rerun()
        else:
            st.caption("Nenhum card neste filtro.")

    with col_metrics:
        st.markdown(
            f"<div style='font-size:12px;line-height:1.4;padding-top:6px'>"
            f"<b>{audits}/{total}</b> auditados ({pct}%) &nbsp;·&nbsp; "
            f"<b>{aprovs}</b> aprovados"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.progress(audits / total if total else 0)



# ---------------------------------------------------------------------------
# Atalhos de teclado
# ---------------------------------------------------------------------------

def inject_keyboard_shortcuts():
    """
    Injeta JS no parent que mapeia:
      ←  →  — navegar   |   A — aprovar   |   R — rejeitar
    Localiza os botões pelo texto visível e simula clique.
    Ignora quando o foco está em input/textarea.
    """
    components.html("""
    <script>
    (function() {
        function clickByText(text) {
            const btns = window.parent.document.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.innerText.trim() === text && !btn.disabled) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }

        window.parent.document.addEventListener('keydown', function(e) {
            const tag = e.target.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;

            switch(e.key) {
                case 'ArrowRight': e.preventDefault(); clickByText('Próx →'); break;
                case 'ArrowLeft':  e.preventDefault(); clickByText('← Ant');  break;
                case 'a': case 'A': e.preventDefault(); clickByText('✓ Aprovar'); break;
                case 'r': case 'R': e.preventDefault(); clickByText('✗ Rejeitar'); break;
            }
        }, { once: false });
    })();
    </script>
    """, height=0)


# ---------------------------------------------------------------------------
# Layout principal
# ---------------------------------------------------------------------------

def render_editor(card: dict):
    idx   = st.session_state.idx
    total = total_cards()

    if st.session_state.get("pre_card_idx") != idx:
        _sync(card)

    # --- Barra de ação compacta (HTML + botões Streamlit alinhados) ---
    icon = (
        "✅" if card.get("auditoriaAprovada") is True
        else ("❌" if "auditadoEm" in card else "⏳")
    )
    flags = []
    if not card.get("ativo", True):        flags.append("🔕 inativo")
    if _has_cross_ref(card.get("textoParent")) and not card.get("textoParentEnriquecido"):
        flags.append("⚠️ ref cruzada")
    flag_str = "  ·  " + "  ·  ".join(flags) if flags else ""

    col_info, col_ant, col_apr, col_rej, col_prox, col_msg = st.columns(
        [5, 1, 2, 2, 1, 2], gap="small"
    )
    with col_info:
        st.markdown(
            f"<div style='padding-top:6px;line-height:1.3'>"
            f"<span style='font-size:15px;font-weight:800'>{card['referencia']}</span>"
            f"&ensp;{icon}&ensp;"
            f"<span style='font-size:11px;color:#888'>"
            f"{idx+1}/{total} &nbsp;·&nbsp; ordem {card['ordemEstudo']}{flag_str}"
            f"</span></div>",
            unsafe_allow_html=True,
        )
    with col_ant:
        if st.button("←", use_container_width=True, disabled=(idx == 0),
                     help="Anterior  [tecla ←]"):
            navigate(-1); st.rerun()
    with col_apr:
        if st.button("✓ Aprovar", type="primary", use_container_width=True,
                     help="Aprovar e avançar  [tecla A]"):
            apply_and_save(card, aprovada=True)
            if idx < total - 1: navigate(1)
            st.rerun()
    with col_rej:
        if st.button("✗ Rejeitar", use_container_width=True,
                     help="Rejeitar e avançar  [tecla R]"):
            apply_and_save(card, aprovada=False)
            if idx < total - 1: navigate(1)
            st.rerun()
    with col_prox:
        if st.button("→", use_container_width=True, disabled=(idx == total - 1),
                     help="Próximo  [tecla →]"):
            navigate(1); st.rerun()
    with col_msg:
        if st.session_state.saved_msg:
            if "✓" in st.session_state.saved_msg:
                st.success(st.session_state.saved_msg)
            else:
                st.error(st.session_state.saved_msg)

    # --- Duas colunas: preview | campos ---
    col_prev, col_edit = st.columns([10, 11], gap="medium")

    with col_prev:
        render_preview(card, height=460)

    with col_edit:
        # Linha 1: assunto + contexto
        r1a, r1b = st.columns([1, 2], gap="small")
        with r1a:
            st.text_input("Assunto", key="pre_assunto", label_visibility="visible")
        with r1b:
            st.text_input("Contexto (header vermelho)", key="pre_contexto",
                label_visibility="visible")

        # Linha 2: chain (condicional)
        if card.get("textoChain") or card.get("textoParent"):
            st.text_input("textoChain  (avô > pai)", key="pre_chain",
                help="Cadeia hierárquica. Edite se incompleta.")

        # Linha 3: enriquecido (condicional)
        if card.get("textoParent") or card.get("textoChain"):
            if _has_cross_ref(card.get("textoParent")) and not card.get("textoParentEnriquecido"):
                st.warning("⚠️ Referência cruzada — preencha o contexto abaixo.", icon=None)
            st.text_area("textoParentEnriquecido", key="pre_enriquecido", height=60,
                help="Contexto resolvido quando textoParent referencia outro artigo.")

        # Linha 4: textoOriginal
        st.text_area("textoOriginal", key="pre_original", height=130,
            help="Texto da lei. Edite só para corrigir erros de extração do PDF.")

        # Linha 5: tipo + dificuldade + ativo + auditadoEm
        r5a, r5b, r5c, r5d = st.columns([2, 1.5, 1, 2], gap="small")
        with r5a:
            st.selectbox("Tipo", TIPOS_CARD, key="pre_tipo",
                label_visibility="visible")
        with r5b:
            st.selectbox("Dificuldade", DIFICULDADES, key="pre_dificuldade",
                label_visibility="visible")
        with r5c:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            st.checkbox("Ativo", key="pre_ativo")
        with r5d:
            if "auditadoEm" in card:
                st.markdown(
                    f"<div style='font-size:11px;color:#888;padding-top:28px'>"
                    f"auditado em<br>{card['auditadoEm']}</div>",
                    unsafe_allow_html=True,
                )



# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="SPUK — Pré-auditoria",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown("""
        <style>
        /* Esconde sidebar e deploy button */
        [data-testid="stSidebar"]          { display: none }
        [data-testid="stDeployButton"]     { display: none }
        #MainMenu                          { display: none }
        header[data-testid="stHeader"]     { display: none }

        /* Padding mínimo da página */
        .block-container {
            padding-top:    0.6rem !important;
            padding-bottom: 0.3rem !important;
            padding-left:   1.2rem !important;
            padding-right:  1.2rem !important;
            max-width: 100% !important;
        }

        /* Reduz gap vertical entre elementos do Streamlit */
        [data-testid="stVerticalBlock"] { gap: 0.3rem !important; }

        /* Inputs e textareas mais compactos */
        [data-testid="stTextInput"]  > div { padding-bottom: 0 !important; }
        [data-testid="stTextArea"]   > div { padding-bottom: 0 !important; }
        .stSelectbox                 > div { padding-bottom: 0 !important; }

        /* Labels menores */
        label[data-testid="stWidgetLabel"] > div {
            font-size: 11px !important;
            margin-bottom: 2px !important;
        }

        /* Divider mais fino */
        hr { margin: 0.3rem 0 !important; }

        /* Remove o espaço do iframe vazio do inject_keyboard_shortcuts */
        iframe[height="0"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    corpus_path = st.session_state.get("corpus_path", list(CORPUS.values())[0])

    if not Path(corpus_path).exists():
        st.error(f"Arquivo não encontrado: `{corpus_path}`")
        st.info("Execute o parser para gerar o JSON do corpus selecionado.")
        st.stop()

    init_state(corpus_path)
    cards = st.session_state.data["cards"]
    render_topbar(cards)
    st.divider()
    render_editor(current_card())
    inject_keyboard_shortcuts()


if __name__ == "__main__":
    main()