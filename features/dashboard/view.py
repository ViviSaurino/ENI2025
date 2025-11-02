# features/sections.py
import streamlit as st
import pandas as pd

# ====== Importar sub-vistas con fallbacks seguros ======
def _stub(msg):
    def _inner():
        st.warning(msg)
    return _inner

try:
    from features.nueva_tarea.view import render as render_nueva_tarea
except Exception:
    render_nueva_tarea = _stub("Crea `features/nueva_tarea/view.py` con `render()` para la sección **Nueva tarea**.")

try:
    from features.editar_tarea.view import render as render_editar_tarea
except Exception:
    render_editar_tarea = _stub("Crea `features/editar_tarea/view.py` con `render()` para **Editar estado**.")

try:
    from features.nueva_alerta.view import render as render_nueva_alerta
except Exception:
    render_nueva_alerta = _stub("Crea `features/nueva_alerta/view.py` con `render()` para **Nueva alerta**.")

try:
    from features.prioridad.view import render as render_prioridad
except Exception:
    render_prioridad = _stub("Crea `features/prioridad/view.py` con `render()` para **Prioridad**.")

try:
    from features.evaluacion.view import render as render_evaluacion
except Exception:
    render_evaluacion = _stub("Crea `features/evaluacion/view.py` con `render()` para **Evaluación**.")

# Historial (opcional): si no tienes módulo, mostramos df_main directamente
try:
    from features.historial.view import render as render_historial
except Exception:
    def render_historial():
        st.subheader("📝 Tareas recientes")
        df = st.session_state.get("df_main", pd.DataFrame([])).copy()
        if "__DEL__" in df.columns:
            df = df.drop(columns="__DEL__")
        st.dataframe(df, use_container_width=True, height=380)

# ====== Helpers UI (toggle + píldoras) ======
def _chev(is_open: bool) -> str:
    return "▾" if is_open else "▸"

def _section(title: str, key_flag: str, pill_class: str):
    st.markdown(f'<div class="topbar" id="ntbar">', unsafe_allow_html=True)
    c1, c2 = st.columns([0.03, 0.97], gap="small")
    with c1:
        def _flip():
            st.session_state[key_flag] = not st.session_state.get(key_flag, True)
        st.button(_chev(st.session_state.get(key_flag, True)), key=f"tgl_{key_flag}", help="Mostrar/ocultar", on_click=_flip)
    with c2:
        st.markdown(f'<div class="{pill_class}">{title}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ====== Estado inicial de visibilidad (una sola vez) ======
if "_ui_bootstrap" not in st.session_state:
    st.session_state["nt_visible"]  = True   # Nueva tarea
    st.session_state["ux_visible"]  = True   # Editar estado
    st.session_state["na_visible"]  = True   # Nueva alerta
    st.session_state["pri_visible"] = False  # Prioridad
    st.session_state["eva_visible"] = False  # Evaluación
    st.session_state["_ui_bootstrap"] = True

# ====== Renderizador maestro ======
def render_all():
    # Título principal de la app (post-login)
    st.title("📂 Gestión - ENI 2025")

    # 1) Nueva tarea
    _section("📝  Nueva tarea", "nt_visible", "form-title")
    if st.session_state["nt_visible"]:
        st.markdown('<div class="form-card">', unsafe_allow_html=True)
        render_nueva_tarea()
        st.markdown('</div>', unsafe_allow_html=True)

    # 2) Editar estado
    _section("✏️  Editar estado", "ux_visible", "form-title-ux")
    if st.session_state["ux_visible"]:
        st.markdown('<div class="form-card">', unsafe_allow_html=True)
        render_editar_tarea()
        st.markdown('</div>', unsafe_allow_html=True)

    # 3) Nueva alerta
    _section("🚨  Nueva alerta", "na_visible", "form-title-na")
    if st.session_state["na_visible"]:
        st.markdown('<div class="form-card">', unsafe_allow_html=True)
        render_nueva_alerta()
        st.markdown('</div>', unsafe_allow_html=True)

    # 4) Prioridad (grid)
    _section("🧭  Prioridad", "pri_visible", "form-title-pri")
    if st.session_state["pri_visible"]:
        st.markdown('<div class="form-card" id="prior-grid">', unsafe_allow_html=True)
        render_prioridad()
        st.markdown('</div>', unsafe_allow_html=True)

    # 5) Evaluación (grid)
    _section("📊  Evaluación", "eva_visible", "form-title-eval")
    if st.session_state["eva_visible"]:
        st.markdown('<div class="form-card" id="eval-grid">', unsafe_allow_html=True)
        render_evaluacion()
        st.markdown('</div>', unsafe_allow_html=True)

    # 6) Historial / Tareas recientes
    render_historial()
