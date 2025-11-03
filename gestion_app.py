# ============================
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd

from auth_google import google_login, logout
from shared import (
    patch_streamlit_aggrid,
    inject_global_css,
    ensure_df_main,
)

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

# 👉 Estilos específicos: banner ENI y botón lila de cerrar sesión
st.markdown("""
<style>
  /* Banner informativo ENI (sin negrita) */
  .eni-banner{
    margin:6px 0 14px;
    font-weight:400; /* <- normal */
    font-size:16px;
    color:#4B5563;
  }
  /* Botón de Cerrar sesión en el sidebar: lila + texto blanco */
  section[data-testid="stSidebar"] .stButton > button{
    background:#C7A0FF !important;
    color:#FFFFFF !important;
    border:none !important;
    border-radius:24px !important;
    font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  section[data-testid="stSidebar"] .stButton > button:hover{
    filter:brightness(0.95);
  }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN ============
if "user" not in st.session_state:
    google_login()
    st.stop()

email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

# ============ Sidebar ============
with st.sidebar:
    st.markdown("<div class='eni-banner'>Esta es la plataforma unificada para gestión - ENI2025</div>", unsafe_allow_html=True)

    st.header("Secciones")
    st.caption("App unificada (sin *pages*).")
    st.divider()
    st.markdown(f"**Usuario:** {email or '—'}")

    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ============ UI principal ============
st.title("📂 Gestión - ENI 2025")

try:
    from features.dashboard.view import render_all
    render_all(st.session_state.get("user"))
except Exception as e:
    st.info("Carga de la vista principal pendiente (features/dashboard/view.py).")
    st.exception(e)
