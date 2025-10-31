# gestion_app.py  (Inicio / router)
import os
import streamlit as st
from auth_google import google_login, logout

# --- Config inicial (primero siempre) ---
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

# --- Rutas de páginas (fijas) ---
GT_PATH = "pages/02_gestion_tareas.py"
KB_PATH = "pages/03_kanban.py"

def _exists(p: str) -> bool:
    try:
        return os.path.exists(p)
    except Exception:
        return False

# --- Lectura de filtros de acceso (secrets) ---
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or None
allowed_domains = auth_cfg.get("allowed_domains", []) or None

# --- Login Google ---
user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None  # nos quedamos en esta página tras login
)
if not user:
    st.stop()

# --- Redirección a Gestión de tareas (una sola vez) ---
def _try_switch_page():
    targets = (
        GT_PATH,                    # archivo exacto
        "02_gestion_tareas",        # slug alterno
        "Gestión de tareas",        # título visible
        "Gestion de tareas",
    )
    for t in targets:
        try:
            st.switch_page(t)
            return True
        except Exception:
            continue
    return False

if not st.session_state.get("_routed_to_gestion_tareas", False):
    st.session_state["_routed_to_gestion_tareas"] = True
    if not _try_switch_page():
        st.info("No pude redirigirte automáticamente. Usa el menú lateral 👉 **Gestión de tareas**.")

# --- Sidebar: navegación fija + usuario ---
with st.sidebar:
    st.header("Secciones")
    # Inicio
    st.page_link("gestion_app.py", label="Inicio", icon="🏠")

    # Gestión de tareas (solo si existe el archivo, para evitar excepción)
    if _exists(GT_PATH):
        st.page_link(GT_PATH, label="Gestión de tareas", icon="📁")
    else:
        st.markdown("• Gestión de tareas")

    # Kanban
    if _exists(KB_PATH):
        st.page_link(KB_PATH, label="Kanban", icon="🧩")
    else:
        st.markdown("• Kanban")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# --- Cuerpo (mensaje de aterrizaje) ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
