# ============================
# Gestión — ENI2025 (App única)
# ============================
import os
import streamlit as st
import pandas as pd

# ---- Login Google (tu módulo) ----
try:
    from auth_google import google_login, logout
except Exception:
    # Fallback de desarrollo (sin Google)
    def google_login():
        st.session_state["auth_ok"] = True
        st.session_state["user_email"] = st.session_state.get("user_email", "dev@example.com")
        return {}
    def logout():
        for k in ("auth_ok","user_email","auth_user","google_user","g_user","email"):
            st.session_state.pop(k, None)

# ---- Utilidades compartidas ----
from shared import patch_streamlit_aggrid, inject_global_css, ensure_df_main

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

# ============ Helpers de autenticación ============
def _current_email() -> str | None:
    ss = st.session_state
    for k in ("user_email","email"):
        if ss.get(k):
            return ss[k]
    for k in ("auth_user","google_user","g_user"):
        if isinstance(ss.get(k), dict) and ss[k].get("email"):
            return ss[k]["email"]
    return None

def _allowed(email: str | None) -> bool:
    if not email:
        return False
    conf = st.secrets.get("auth", {})
    allowed_emails  = set(conf.get("allowed_emails", []))
    allowed_domains = set(conf.get("allowed_domains", []))
    if email in allowed_emails:
        return True
    try:
        domain = email.split("@", 1)[1].lower()
        if domain in allowed_domains:
            return True
    except Exception:
        pass
    # Si no configuras listas en secrets, se permite el acceso
    return (not allowed_emails and not allowed_domains)

# ============ Vistas ============
from features.dashboard.view import render_bienvenida
from features.sections import render_all

# ============ Ruteo: Bienvenida (pre-login) vs App (post-login) ============
email = _current_email()
if not (email and _allowed(email)):
    # Pantalla de bienvenida LILA + botón de login + animación
    render_bienvenida(on_login=google_login)
    st.stop()

# ====== Sidebar (ya logueado) ======
with st.sidebar:
    st.header("Secciones")
    st.caption("App unificada (sin *pages*).")
    st.divider()
    st.markdown(f"**Usuario:** {email}")
    if st.button("Cerrar sesión", use_container_width=True):
        try:
            logout()
        finally:
            st.rerun()

# ====== Datos base en memoria ======
ensure_df_main()  # crea/carga st.session_state["df_main"]

# ====== Render de TODAS las secciones ======
render_all()
