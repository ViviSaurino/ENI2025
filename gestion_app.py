# ============================ 
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd
from pathlib import Path

from auth_google import google_login, logout
from shared import (
    patch_streamlit_aggrid,
    inject_global_css,
    ensure_df_main,
)

# Ruta del logo (arriba, a la izquierda del sidebar)
LOGO_PATH = Path("assets/branding/eni2025_logo.png")

# ============ Config de página ============
st.set_page_config(
    page_title="Gestión — ENI2025",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ Parches/estilos globales ============
patch_streamlit_aggrid()
inject_global_css()

# 👉 Estilos específicos (banner + botón cerrar sesión + logo más a la izquierda)
st.markdown("""
<style>
  .eni-banner{
    margin:6px 0 14px;
    font-weight:400;  /* sin negrita */
    font-size:16px;
    color:#4B5563;
  }
  section[data-testid="stSidebar"] .stButton > button{
    background:#C7A0FF !important;
    color:#FFFFFF !important;
    border:none !important;
    border-radius:12px !important;  /* menos curvatura */
    font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  section[data-testid="stSidebar"] .stButton > button:hover{ filter:brightness(0.95); }

  /* Logo un poco más a la izquierda */
  section[data-testid="stSidebar"] .eni-logo-wrap{ margin-left:-28px; }

  /* Radio de navegación: más compacto */
  .eni-nav label{ padding:6px 8px !important; }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN ============
if "user" not in st.session_state:
    google_login()
    st.stop()

email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

# ============ Sidebar ============
with st.sidebar:
    # Logo
    if LOGO_PATH.exists():
        st.markdown("<div class='eni-logo-wrap'>", unsafe_allow_html=True)
        st.image(str(LOGO_PATH), width=120)
        st.markdown("</div>", unsafe_allow_html=True)

    # Banner
    st.markdown("<div class='eni-banner'>Esta es la plataforma unificada para gestión - ENI2025</div>", unsafe_allow_html=True)

    # Navegación (clicable) solicitada
    st.header("Secciones")
    nav_labels = [
        "🧰 Gestión de tareas",
        "🗂️ Kanban",
        "📅 Gantt",
        "📊 Dashboard",
    ]
    default_idx = nav_labels.index(st.session_state.get("nav_section", "🧰 Gestión de tareas"))
    nav_choice = st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False,
    )

    st.divider()
    st.markdown(f"**Usuario:** {email or '—'}")
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ============ UI principal ============
# Ruteo a vistas según la opción elegida en el sidebar
section = st.session_state.get("nav_section", "🧰 Gestión de tareas")

if section == "🧰 Gestión de tareas":
    st.title("🧰 Gestión de tareas")
    try:
        # Reutilizamos la vista funcional del Dashboard
        from features.dashboard.view import render_all
        render_all(st.session_state.get("user"))
    except Exception as e:
        st.info("Vista de Gestión de tareas pendiente.")
        st.exception(e)

elif section == "🗂️ Kanban":
    st.title("🗂️ Kanban")
    try:
        from features.kanban.view import render as render_kanban
        render_kanban(st.session_state.get("user"))
    except Exception as e:
        st.info("Vista Kanban pendiente (features/kanban/view.py).")
        st.exception(e)

elif section == "📅 Gantt":
    st.title("📅 Gantt")
    try:
        from features.gantt.view import render as render_gantt
        render_gantt(st.session_state.get("user"))
    except Exception as e:
        st.info("Vista Gantt pendiente (features/gantt/view.py).")
        st.exception(e)

else:  # "📊 Dashboard"
    st.title("📊 Dashboard")
    # 🔹 Por ahora no hay contenido; dejamos la sección en blanco con un placeholder suave
    st.caption("Próximamente: visualizaciones y KPIs del dashboard.")
    st.write("")  # espacio en blanco
