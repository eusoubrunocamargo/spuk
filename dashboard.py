"""
dashboard.py — Dashboard de auditoria do SPUK-LEGIS
Uso: streamlit run dashboard.py

Carrega o output/lei_8429_cards.json, permite revisar card a card,
editar campos conservadores do parser, aprovar ou rejeitar cada card,
e persiste os campos `auditoriaAprovada` e `auditadoEm` de volta no JSON.
"""

import json
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

JSON_PATH = Path("output/lei_8429_cards_v3.json")

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

# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def load_data() -> dict:
    """Carrega o JSON do disco. Chamado uma vez por sessão."""
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict):
    """Persiste o JSON inteiro de volta ao disco."""
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Inicialização do estado da sessão
# ---------------------------------------------------------------------------

def init_state():
    if "data" not in st.session_state:
        st.session_state.data = load_data()

    if "idx" not in st.session_state:
        # Abre na primeira card ainda não auditada, ou na 0 se todas já foram
        cards = st.session_state.data["cards"]
        pendentes = [i for i, c in enumerate(cards) if not c.get("auditoriaAprovada")]
        st.session_state.idx = pendentes[0] if pendentes else 0

    if "saved_msg" not in st.session_state:
        st.session_state.saved_msg = ""


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
    """Move o índice e limpa a mensagem de save."""
    novo = st.session_state.idx + delta
    total = total_cards()
    st.session_state.idx = max(0, min(novo, total - 1))
    st.session_state.saved_msg = ""


def apply_and_save(card: dict, updates: dict, aprovada: bool):
    """
    Aplica as edições ao card, seta os campos de auditoria e persiste.
    `updates` é um dict com os campos editáveis que o usuário modificou.
    """
    card.update(updates)
    card["auditoriaAprovada"] = aprovada
    card["auditadoEm"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_data(st.session_state.data)
    st.session_state.saved_msg = "✓ Salvo" if aprovada else "✗ Rejeitado"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def render_sidebar(cards: list):
    """Painel lateral com progresso e navegação rápida."""
    st.sidebar.title("SPUK-LEGIS")
    st.sidebar.caption("Auditoria de cards")

    total = total_cards()
    auditados = count_auditados()
    aprovados = count_aprovados()

    st.sidebar.metric("Total de cards", total)
    st.sidebar.metric("Auditados", f"{auditados} / {total}")
    st.sidebar.metric("Aprovados", aprovados)
    st.sidebar.progress(auditados / total if total else 0)

    st.sidebar.divider()

    # Filtro rápido por tipo ou por estado
    filtro = st.sidebar.selectbox(
        "Filtrar lista por",
        ["Todos", "Pendentes", "Aprovados", "Rejeitados",
         "PARAGRAFO_ISOLADO", "CAPUT_ISOLADO", "ARTIGO_COMPLETO",
         "INCISO_COM_CAPUT", "INCISO_AUTOSSUFICIENTE", "PARAGRAFO_COM_CAPUT"],
    )

    def match(c):
        if filtro == "Pendentes":
            return "auditadoEm" not in c
        if filtro == "Aprovados":
            return c.get("auditoriaAprovada") is True
        if filtro == "Rejeitados":
            return c.get("auditoriaAprovada") is False
        if filtro in TIPOS_CARD:
            return c.get("tipo") == filtro
        return True  # Todos

    indices_filtrados = [i for i, c in enumerate(cards) if match(c)]

    if indices_filtrados:
        # Exibe lista clicável das referências filtradas
        labels = []
        for i in indices_filtrados:
            c = cards[i]
            icon = "✓" if c.get("auditoriaAprovada") else ("✗" if "auditadoEm" in c else "·")
            labels.append(f"{icon} [{i+1:03d}] {c['referencia']}")

        # Encontra a posição do card atual dentro da lista filtrada
        current_pos = indices_filtrados.index(st.session_state.idx) \
            if st.session_state.idx in indices_filtrados else 0

        escolha = st.sidebar.selectbox(
            f"{len(indices_filtrados)} cards",
            range(len(labels)),
            index=current_pos,
            format_func=lambda x: labels[x],
        )
        if indices_filtrados[escolha] != st.session_state.idx:
            st.session_state.idx = indices_filtrados[escolha]
            st.session_state.saved_msg = ""
            st.rerun()
    else:
        st.sidebar.info("Nenhum card neste filtro.")


def render_preview(contexto: str, texto_parent: str | None, texto: str,
                   tipo: str, dificuldade: str):
    """
    Renderiza uma simulação visual de como o card aparece para o usuário final.

    Quando textoParent está presente (INCISO_COM_CAPUT), exibe-o em estilo
    suave entre o header de contexto e o texto julgável — exatamente como
    o app mostrará o caput ou parágrafo pai antes do inciso testável.
    """
    dif_cores = {"FACIL": "#4CAF50", "MEDIO": "#FF9800", "DIFICIL": "#FF4D4D"}
    dif_cor = dif_cores.get(dificuldade, "#888")

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    tipo_label = tipo.replace("_", " ")

    parent_block = ""
    if texto_parent:
        parent_block = f"""
        <p style="
            font-size: 12px; font-weight: 400; color: #888;
            line-height: 1.55; margin: 0 0 14px 0;
            padding: 10px 12px; background: #222;
            border-radius: 10px; border-left: 3px solid #FF4D4D;
        ">{esc(texto_parent)}</p>"""

    html = f"""
    <div style="display:flex; flex-direction:column; align-items:center; padding:8px 0 16px 0;">
        <p style="
            font-size:11px; font-weight:700; letter-spacing:0.12em;
            text-transform:uppercase; color:#666; margin:0 0 12px 0;
        ">Preview — visão do usuário</p>

        <div style="
            background:#1A1A1A; border-radius:28px; width:100%; max-width:380px;
            display:flex; flex-direction:column; padding:28px 24px 24px 24px;
            box-shadow:0 8px 32px rgba(0,0,0,0.45);
        ">
            <div style="display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap;">
                <span style="
                    font-size:10px; font-weight:900; letter-spacing:0.1em;
                    text-transform:uppercase; color:#aaa;
                    background:#2a2a2a; border-radius:20px; padding:4px 10px;
                ">{tipo_label}</span>
                <span style="
                    font-size:10px; font-weight:900; letter-spacing:0.1em;
                    text-transform:uppercase; color:{dif_cor};
                    background:#2a2a2a; border-radius:20px; padding:4px 10px;
                ">{dificuldade}</span>
            </div>

            <p style="
                font-size:12px; font-weight:700; letter-spacing:0.06em;
                text-transform:uppercase; color:#FF4D4D; margin:0 0 14px 0; line-height:1.4;
            ">{esc(contexto)}</p>

            {parent_block}

            <p style="
                font-size:15px; font-weight:400; color:#F0F0F0;
                line-height:1.65; margin:0 0 auto 0; flex-grow:1;
            ">{esc(texto)}</p>

            <hr style="border:none; border-top:1px solid #2e2e2e; margin:20px 0 16px 0;">

            <div style="display:flex; gap:12px;">
                <button style="
                    flex:1; background:#2a2a2a; border:2px solid #444; border-radius:16px;
                    color:#F0F0F0; font-size:13px; font-weight:900; letter-spacing:0.05em;
                    text-transform:uppercase; padding:14px 0; cursor:default;
                ">← Errado</button>
                <button style="
                    flex:1; background:#FF4D4D; border:none; border-radius:16px;
                    color:#fff; font-size:13px; font-weight:900; letter-spacing:0.05em;
                    text-transform:uppercase; padding:14px 0; cursor:default;
                ">Correto →</button>
            </div>
        </div>
    </div>
    """
    components.html(html, height=540, scrolling=False)


def render_card_editor(card: dict):
    """
    Formulário de edição do card atual (coluna esquerda) ao lado da
    preview em tempo real do card no app (coluna direita).
    """
    idx = st.session_state.idx
    total = total_cards()

    # Cabeçalho com referência e status — acima das colunas, largura total
    col_ref, col_status = st.columns([3, 1])
    with col_ref:
        st.subheader(card["referencia"])
    with col_status:
        if card.get("auditoriaAprovada") is True:
            st.success("Aprovado")
        elif "auditadoEm" in card:
            st.error("Rejeitado")
        else:
            st.info("Pendente")

    st.caption(f"Card {idx + 1} de {total}  |  ordemEstudo: {card['ordemEstudo']}")

    # Layout em duas colunas: formulário | preview
    col_form, col_prev_panel = st.columns([1, 1], gap="large")

    with col_form:
        # --- Campos editáveis ---
        novo_tipo = st.selectbox(
            "Tipo",
            TIPOS_CARD,
            index=TIPOS_CARD.index(card["tipo"]) if card["tipo"] in TIPOS_CARD else 0,
            help="O parser atribui PARAGRAFO_ISOLADO por padrão; altere para PARAGRAFO_COM_CAPUT se o parágrafo modifica ou excepciona o caput.",
        )

        novo_contexto = st.text_input(
            "textoContexto  (header exibido ao usuário)",
            value=card["textoContexto"],
            help="Condense para algo como 'Art. 9º — Enriquecimento Ilícito'.",
        )

        novo_assunto = st.text_input(
            "assuntoNome",
            value=card["assuntoNome"],
        )

        nova_dificuldade = st.selectbox(
            "Dificuldade",
            DIFICULDADES,
            index=DIFICULDADES.index(card["dificuldade"]) if card["dificuldade"] in DIFICULDADES else 1,
        )

        # Texto original — somente leitura, pois é o texto normativo bruto
        st.text_area(
            "textoOriginal  (somente leitura)",
            value=card["textoOriginal"],
            height=120,
            disabled=True,
            help="Texto extraído diretamente da lei. Alterações aqui devem ser feitas diretamente no JSON.",
        )

        # textoParent — exibido somente quando preenchido (incisos com caput)
        if card.get("textoParent"):
            st.text_area(
                "textoParent  (somente leitura)",
                value=card["textoParent"],
                height=80,
                disabled=True,
                help="Texto do caput ou parágrafo pai exibido acima do inciso no app.",
            )

        novo_ativo = st.checkbox(
            "Ativo  (desmarque para excluir da geração de variantes)",
            value=card.get("ativo", True),
        )

        if "auditadoEm" in card:
            st.caption(f"Auditado em: {card['auditadoEm']}")

    with col_prev_panel:
        # A preview lê os valores atuais dos widgets, refletindo edições
        # em tempo real antes de qualquer save.
        render_preview(
            contexto=novo_contexto,
            texto_parent=card.get("textoParent"),
            texto=card["textoOriginal"],
            tipo=novo_tipo,
            dificuldade=nova_dificuldade,
        )

    st.divider()

    # --- Botões de ação — largura total, abaixo das colunas ---
    col_prev, col_aprovar, col_rejeitar, col_next = st.columns([1, 2, 2, 1])

    updates = {
        "tipo": novo_tipo,
        "textoContexto": novo_contexto,
        "assuntoNome": novo_assunto,
        "dificuldade": nova_dificuldade,
        "ativo": novo_ativo,
    }

    with col_prev:
        if st.button("← Anterior", use_container_width=True, disabled=(idx == 0)):
            navigate(-1)
            st.rerun()

    with col_aprovar:
        if st.button("✓ Aprovar e avançar", type="primary", use_container_width=True):
            apply_and_save(card, updates, aprovada=True)
            if idx < total - 1:
                navigate(1)
            st.rerun()

    with col_rejeitar:
        if st.button("✗ Rejeitar e avançar", use_container_width=True):
            apply_and_save(card, updates, aprovada=False)
            if idx < total - 1:
                navigate(1)
            st.rerun()

    with col_next:
        if st.button("Próximo →", use_container_width=True, disabled=(idx == total - 1)):
            navigate(1)
            st.rerun()

    if st.session_state.saved_msg:
        st.success(st.session_state.saved_msg) \
            if "✓" in st.session_state.saved_msg \
            else st.error(st.session_state.saved_msg)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="SPUK-LEGIS — Auditoria",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if not JSON_PATH.exists():
        st.error(f"Arquivo não encontrado: `{JSON_PATH}`")
        st.info("Execute primeiro: `python main.py parse corpus/lei_8429.pdf --output output/lei_8429_cards.json`")
        st.stop()

    init_state()

    cards = st.session_state.data["cards"]
    render_sidebar(cards)
    render_card_editor(current_card())


if __name__ == "__main__":
    main()