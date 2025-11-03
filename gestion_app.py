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

# 👉 Estilos específicos: banner ENI y píldora lila para Cerrar sesión
st.markdown("""
<style>
  /* Banner informativo ENI */
  .eni-banner{
    margin:6px 0 14px;
    font-weight:600;
    font-size:16px;
    color:#4B5563;
  }
  /* Píldora lila para botón de Cerrar sesión en el sidebar */
  #logout-pill button{
    background:#C7A0FF !important;
    color:#ffffff !important;
    border:none !important;
    border-radius:24px !important;
    font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  #logout-pill button:hover{ filter:brightness(0.95); }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN (SOLO ESTE GUARD) ============
# Si no hay usuario, google_login() renderiza la portada (BIENVENIDOS lila + hero)
if "user" not in st.session_state:
    google_login()     # <- muestra portada y NO devuelve hasta autenticar
    st.stop()

# A partir de aquí ya hay sesión válida
email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

# ============ Sidebar ============
with st.sidebar:
    # 👉 Texto arriba de secciones
    st.markdown("<div class='eni-banner'>Esta es la plataforma unificada para gestión - ENI2025</div>", unsafe_allow_html=True)

    st.header("Secciones")
    st.caption("App unificada (sin *pages*).")
    st.divider()
    st.markdown(f"**Usuario:** {email or '—'}")

    # 👉 Botón con estilo píldora lila (sin cambiar la lógica)
    st.markdown("<div id='logout-pill'>", unsafe_allow_html=True)
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()
    st.markdown("</div>", unsafe_allow_html=True)

# ============ Datos ============
ensure_df_main()  # inicializa st.session_state["df_main"]

# ============ UI principal ============
st.title("📂 Gestión - ENI 2025")

# Cargar la vista principal (si aún no la tienes lista, no rompe)
try:
    from features.dashboard.view import render_all
    # 🔹 Pasamos el usuario a la vista para que decida si muestra bienvenida o dashboard
    render_all(st.session_state.get("user"))
except Exception as e:
    st.info("Carga de la vista principal pendiente (features/dashboard/view.py).")
    st.exception(e)
