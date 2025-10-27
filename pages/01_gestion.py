# pages/01_gestion.py
import streamlit as st
from auth_google import google_login, logout
import gestion_app

st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- login (aquí, no en el módulo) ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

user = google_login(allowed_emails=allowed_emails,
                    allowed_domains=allowed_domains,
                    redirect_page=None)
if not user:
    st.stop()

with st.sidebar:
    st.header("gestion app")
    st.page_link("pages/01_gestion.py", label="gestion", icon="📂")
    st.page_link("pages/02_kanban.py", label="kanban",  icon="🗂️")
    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        logout()
        st.rerun()

# --- aquí se pinta TODO lo de Gestión ---
gestion_app.render()
