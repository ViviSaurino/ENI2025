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

# --- Lectura de filtros de acceso (secrets) ---
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or []
allowed_domains = auth_cfg.get("allowed_domains", []) or []

# Aviso útil si no configuraste filtros (evita que te "cierre la puerta" en local)
if not allowed_emails and not allowed_domains:
    st.caption("⚠️ No hay filtros de acceso en `st.secrets['auth']`. Cualquier cuenta podrá iniciar sesión (modo abierto).")

# --- Login Google ---
# Sugerido: usar redirect_page explícito al archivo actual (estable en multi-page)
user = google_login(
    allowed_emails=allowed_emails if allowed_emails else None,
    allowed_domains=allowed_domains if allowed_domains else None,
    redirect_page="gestion_app.py"
)

# Si aún no hay usuario, detenemos el render (el componente de login se muestra igual)
if not user:
    st.stop()

# --- Redirección a Gestión de tareas (una sola vez, y solo si realmente cambia de página) ---
def _try_switch_page():
    targets = (
        "pages/02_gestion_tareas.py",  # nombre de archivo exacto
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
        # Solo marcamos el flag si la redirección NO lanzó excepción
        st.session_state["_routed_to_gestion_tareas"] = True
    else:
        # Si no se pudo redirigir, lo informamos y dejamos el menú lateral operativo
        st.info("No pude redirigirte automáticamente. Usa el menú lateral 👉 **Gestión de tareas**.")

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

# --- Cuerpo (mensaje de aterrizaje) ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
