# pages/01_Gestion.py
import streamlit as st
from auth_google import google_login, logout
import gestion_app  # <<< tu módulo con toda la UI

# ⚠️ set_page_config SIEMPRE aquí, al inicio de la página
st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Login (mismo que ya usas)
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])
user = google_login(allowed_emails=allowed_emails, allowed_domains=allowed_domains, redirect_page=None)
if not user:
    st.stop()

# Sidebar de usuario
with st.sidebar:
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        logout()
        st.rerun()

# ---------- UI principal (delegada al módulo) ----------
gestion_app.render()   # <<< aquí se pinta TODO lo de Gestión
