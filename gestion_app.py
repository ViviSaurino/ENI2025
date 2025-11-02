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

# ---- Portada lila (bienvenida + animación hero) ----
from features.dashboard.view import render_bienvenida

# ============ Config de página ============
st.set_page_config(
    page_title="Gestión — ENI2025",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="collapsed"  # colapsada en portada
)

# ============ Parches/estilos globales ============
patch_streamlit_aggrid()
inject_global_css()

# ============ Autenticación ============
def _current_email() -> str | None:
    ss = st.session_state
    if ss.get("user_email"): return ss["user_email"]
    if ss.get("email"): return ss["email"]
    for k in ("auth_user","google_user","g_user"):
        v = ss.get(k)
        if isinstance(v, dict) and v.get("email"):
            return v["email"]
    return None

def _allowed(email: str | None) -> bool:
    conf = st.secrets.get("auth", {})
    allowed_emails  = set(conf.get("allowed_emails", []))
    allowed_domains = set(conf.get("allowed_domains", []))
    if not email:
        return False
    if email in allowed_emails:
        return True
    try:
        dom = email.split("@", 1)[1].lower()
    except Exception:
        dom = ""
    if dom and dom in allowed_domains:
        return True
    # si no hay restricciones configuradas, permitir
    return (not allowed_emails and not allowed_domains)

def _show_welcome_and_stop():
    # Portada lila + animación hero + botón Google
    render_bienvenida(on_login=google_login)
    st.stop()

# ---- Gate: si no hay sesión válida, mostrar portada lila ----
email = _current_email()
if not _allowed(email):
    _show_welcome_and_stop()

# ============ Sidebar (solo autenticado) ============
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

# ============ Bootstrap de datos ============
ensure_df_main()  # st.session_state["df_main"]

# ============ UI principal ============
st.title("📂 Gestión - ENI 2025")

# Carga de la vista principal (tareas)
_loaded = False
try:
    # si tu vista principal vive aquí:
    from features.tareas.sections import render as render_main
    render_main()
    _loaded = True
except Exception:
    pass

if not _loaded:
    st.info("Carga aquí tu vista principal (por ejemplo, `features/tareas/sections.py:render()`).")
