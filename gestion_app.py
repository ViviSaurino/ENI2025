# gestion_app.py  (Inicio / router)
import os
import streamlit as st
from auth_google import google_login, logout

# --- Config inicial (primero siempre) ---
st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="expanded",   # ← expandido para ver las 3 secciones
)

# Oculta la navegación nativa de páginas (usamos nuestro menú con page_link)
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Lectura de filtros de acceso (secrets) ---
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or []
allowed_domains = auth_cfg.get("allowed_domains", []) or []

# Aviso útil si no configuraste filtros (modo abierto)
if not allowed_emails and not allowed_domains:
    st.caption("⚠️ No hay filtros de acceso en `st.secrets['auth']`. Cualquier cuenta podrá iniciar sesión (modo abierto).")

# --- Login Google ---
# ⚠️ IMPORTANTE: no pasar redirect_page aquí para NO cortar el render con st.stop()
user = google_login(
    allowed_emails=allowed_emails if allowed_emails else None,
    allowed_domains=allowed_domains if allowed_domains else None,
    redirect_page=None
)
if not user:
    st.stop()

# --- Redirección a Gestión de tareas (una sola vez por sesión) ---
def _try_switch_page() -> bool:
    targets = (
        "pages/02_gestion_tareas.py",  # ruta exacta del archivo
        "02_gestion_tareas",           # slug alterno
        "02 gestion tareas",           # texto alterno
        "Gestión de tareas",           # título visible alterno
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
    if _try_switch_page():
        st.session_state["_routed_to_gestion_tareas"] = True
    else:
        st.info("No pude redirigirte automáticamente. Usa el menú lateral 👉 **Gestión de tareas**.")

# --- Sidebar: navegación fija + usuario ---
with st.sidebar:
    st.header("Secciones")
    st.page_link("gestion_app.py",             label="Inicio",             icon="🏠")
    st.page_link("pages/02_gestion_tareas.py", label="Gestión de tareas",  icon="🗂️")
    st.page_link("pages/03_kanban.py",         label="Kanban",             icon="🧩")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# --- Cuerpo (mensaje de aterrizaje) ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
