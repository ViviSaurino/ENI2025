# gestion_app.py  (Inicio / router)
import streamlit as st
from auth_google import google_login, logout

st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="collapsed",   # colapsada al entrar (antes de login)
)

# 🔧 Oculta la navegación nativa de páginas (la que muestra “gestion app / kanban” arriba)
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Login (gate aquí) ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None
)
if not user:
    st.stop()

# --- Tras el login: redirigir a "Gestión de tareas" (una sola vez por sesión) ---
# Requiere que exista: pages/02_gestion_tareas.py
if not st.session_state.get("_routed_to_gestion_tareas", False):
    st.session_state["_routed_to_gestion_tareas"] = True
    # Intentos robustos (algunas instalaciones resuelven por nombre, otras por ruta)
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

# --- Sidebar (navegación fija + caja de usuario) ---
with st.sidebar:
    st.header("Inicio")
    st.page_link("gestion_app.py",             label="Inicio",             icon="🏠")
    st.page_link("pages/02_gestion_tareas.py", label="Gestión de tareas",  icon="🗂️")
    st.page_link("pages/03_kanban.py",         label="Kanban",             icon="🧩")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        # Limpia flags locales para que la próxima vez vuelva a redirigir
        for k in ("_routed_to_gestion_tareas",):
            st.session_state.pop(k, None)
        logout()
        st.rerun()

# --- Contenido (sin page_link para evitar DuplicateWidgetID) ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
