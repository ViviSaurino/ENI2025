# ============================
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd

# ---- Login Google (usa tu portada con hero) ----
from auth_google import google_login, logout

# ---- Utilidades compartidas ----
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

# ============ AUTENTICACIÓN (SOLO ESTE GUARD) ============
# Si no hay usuario, google_login() renderiza la portada (BIENVENIDOS lila + hero)
if "user" not in st.session_state:
    google_login()     # <- muestra portada y NO devuelve hasta autenticar
    st.stop()

# A partir de aquí ya hay sesión válida
email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

# ============ Sidebar ============
with st.sidebar:
    st.header("Secciones")
    st.caption("App unificada (sin *pages*).")
    st.divider()
    st.markdown(f"**Usuario:** {email or '—'}")
    if st.button("Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============ 
ensure_df_main()  # inicializa st.session_state["df_main"]

# ============ UI principal ============
st.title("📂 Gestión - ENI 2025")

# Cargar la vista principal (si aún no la tienes lista, no rompe)
try:
    from features.dashboard.view import render_all
    render_all()
except Exception as e:
    st.info("Carga de la vista principal pendiente (features/dashboard/view.py).")
    st.exception(e)

