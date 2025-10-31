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
    # Fallback de desarrollo
    def google_login():
        st.session_state["auth_ok"] = True
        st.session_state["user_email"] = st.session_state.get("user_email", "dev@example.com")
        return {}
    def logout():
        for k in ("auth_ok","user_email","auth_user","google_user","g_user","email"):
            st.session_state.pop(k, None)

# ---- Utilidades compartidas ----
from shared import (
    patch_streamlit_aggrid, inject_global_css, ensure_df_main,
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

# ============ Autenticación ============
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
    return (not allowed_emails and not allowed_domains)  # si no hay lista, permitir

def _login_gate():
    email = _current_email()
    if email and _allowed(email):
        return True

    st.info("🔐 Inicia sesión con tu cuenta permitida para acceder a **Gestión — ENI2025**.")
    col1, col2 = st.columns([1,2])
    with col1:
        if st.button("Iniciar sesión con Google", use_container_width=True):
            try:
                google_login()
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo iniciar sesión: {e}")
    st.stop()

# Lanza el gate
_login_gate()

# ============ Sidebar ============
with st.sidebar:
    st.header("Secciones")
    st.caption("App unificada (sin *pages*).")
    st.divider()
    email = _current_email()
    st.markdown(f"**Usuario:** {email or '—'}")
    if st.button("Cerrar sesión", use_container_width=True):
        try:
            logout()
        finally:
            st.rerun()

# ============ Bootstrap de datos ============
ensure_df_main()  # carga/crea st.session_state["df_main"]

# ============ UI principal ============
st.title("📂 Gestión - ENI 2025")

# Import tardío para no romper el arranque si faltan dependencias
try:
    from features.view import render
except Exception as e:
    st.error("No se pudo cargar la vista principal (features/view.py).")
    st.exception(e)
else:
    render()
