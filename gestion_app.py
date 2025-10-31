# gestion_app.py  (Inicio / router)
import os
import unicodedata
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

# ===================== Utilidades de navegación =====================

def _norm_name(s: str) -> str:
    """normaliza: minúsculas, sin tildes, espacios->_"""
    s = os.path.basename(s)
    s = s.lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    s = s.replace(' ', '_')
    return s

def resolve_page(preferred_candidates: list[str]) -> str | None:
    """
    Devuelve la ruta real 'pages/xxx.py' si existe.
    - Hace match exacto sobre nombre normalizado.
    - Si no encuentra, prueba una búsqueda difusa por palabras clave.
    """
    if not os.path.isdir("pages"):
        return None

    # todas las páginas .py en /pages
    all_pages = [f"pages/{f}" for f in os.listdir("pages") if f.endswith(".py")]
    norm_map = {_norm_name(p): p for p in all_pages}

    # intento por candidatos preferidos
    for cand in preferred_candidates:
        key = _norm_name(cand)
        if key in norm_map:
            return norm_map[key]

    # búsqueda difusa por palabras clave
    for key, path in norm_map.items():
        if "gestion" in key and "tarea" in key:
            return path  # Gestión de tareas
    for key, path in norm_map.items():
        if "kanban" in key:
            return path

    return None

# Candidatos típicos (cubre 01_/02_, mayúsculas, tildes, etc.)
GESTION_TAREAS_PAGE = resolve_page([
    "02_gestion_tareas.py", "01_gestion_tareas.py",
    "02_GESTION_TAREAS.py", "01_GESTION_TAREAS.py",
    "gestion_de_tareas.py", "Gestión de tareas.py",
])
KANBAN_PAGE = resolve_page([
    "03_kanban.py", "02_kanban.py", "kanban.py", "KANBAN.py",
])

# --- Lectura de filtros de acceso (secrets) ---
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or []
allowed_domains = auth_cfg.get("allowed_domains", []) or []

if not allowed_emails and not allowed_domains:
    st.caption("⚠️ No hay filtros de acceso en `st.secrets['auth']`. Cualquier cuenta podrá iniciar sesión (modo abierto).")

# --- Login Google ---
user = google_login(
    allowed_emails=allowed_emails if allowed_emails else None,
    allowed_domains=allowed_domains if allowed_domains else None,
    redirect_page=None  # no redirigimos aquí; control total abajo
)
if not user:
    st.stop()

# --- Redirección automática a Gestión de tareas (si existe y 1 sola vez) ---
if not st.session_state.get("_routed_to_gestion_tareas", False):
    if GESTION_TAREAS_PAGE:
        try:
            st.session_state["_routed_to_gestion_tareas"] = True
            st.switch_page(GESTION_TAREAS_PAGE)
        except Exception:
            # si la API no puede redirigir, mostramos aviso y seguimos
            st.session_state["_routed_to_gestion_tareas"] = True
            st.info("No pude redirigirte automáticamente. Usa el menú lateral 👉 **Gestión de tareas**.")
    else:
        st.info("No encontré la página de **Gestión de tareas** en la carpeta `pages/`. Verifica el nombre del archivo.")

# --- Sidebar: navegación fija + usuario ---
with st.sidebar:
    st.header("Secciones")
    st.page_link("gestion_app.py", label="Inicio", icon="🏠")

    if GESTION_TAREAS_PAGE:
        st.page_link(GESTION_TAREAS_PAGE, label="Gestión de tareas", icon="📁")
    else:
        st.markdown("• Gestión de tareas")

    if KANBAN_PAGE:
        st.page_link(KANBAN_PAGE, label="Kanban", icon="🧩")
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
