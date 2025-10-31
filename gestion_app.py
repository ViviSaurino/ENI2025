# gestion_app.py  (Inicio / router)
import streamlit as st
from auth_google import google_login, logout

st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Oculta la navegación nativa de páginas
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Login ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None
)
if not user:
    st.stop()

# --- Redirección a Gestión de tareas (una vez por sesión) ---
if not st.session_state.get("_routed_to_gestion_tareas", False):
    st.session_state["_routed_to_gestion_tareas"] = True
    for t in (
        "pages/02_gestion_tareas.py",
        "02_gestion_tareas",
        "02 gestion tareas",
        "Gestión de tareas",
        "Gestion de tareas",
    ):
        try:
            st.switch_page(t)
            break
        except Exception:
            pass

# --- Sidebar: navegación fija + usuario ---
with st.sidebar:
    st.header("Inicio")
    st.page_link("gestion_app.py",             label="Inicio",             icon="🏠")
    st.page_link("pages/02_gestion_tareas.py", label="Gestión de tareas",  icon="🗂️")
    st.page_link("pages/03_kanban.py",         label="Kanban",             icon="🧩")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# --- Cuerpo (sin page_link aquí) ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
