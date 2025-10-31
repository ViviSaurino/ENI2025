# gestion_app.py  (Inicio / router)
import streamlit as st
from auth_google import google_login, logout

# --- Config inicial ---
st.set_page_config(page_title="Gestión — ENI2025", layout="wide", initial_sidebar_state="collapsed")

# Oculta la navegación nativa de páginas
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ========= Helpers robustos para navegación =========
def _safe_switch_page(targets: list[str]) -> bool:
    """Intenta cambiar de página probando varios targets. Devuelve True si alguna funcionó."""
    for t in targets:
        try:
            st.switch_page(t)
            return True
        except Exception:
            continue
    return False

def _safe_page_link(targets: list[str], label: str, icon: str = "🧭"):
    """
    Dibuja un page_link contra el primer target válido.
    Si ninguno existe, muestra un rótulo gris (no clickable) sin romper la app.
    """
    for t in targets:
        try:
            st.page_link(t, label=label, icon=icon)
            return
        except Exception:
            continue
    st.markdown(f"<span style='opacity:.55;'>• {icon} {label}</span>", unsafe_allow_html=True)

# Variantes de rutas (minúsculas / MAYÚSCULAS / slugs / títulos)
TARGET_TAREAS = [
    # minúsculas
    "pages/01_gestion_tareas.py", "pages/02_gestion_tareas.py",
    "01_gestion_tareas", "02_gestion_tareas",
    # MAYÚSCULAS (Linux es case-sensitive)
    "pages/01_GESTION_TAREAS.py", "pages/02_GESTION_TAREAS.py",
    "01_GESTION_TAREAS", "02_GESTION_TAREAS",
    # Camel/Pascal por si acaso
    "pages/01_Gestion_Tareas.py", "pages/02_Gestion_Tareas.py",
    "01_Gestion_Tareas", "02_Gestion_Tareas",
    # por título
    "Gestión de tareas", "Gestion de tareas",
]

TARGET_KANBAN = [
    "pages/02_kanban.py", "pages/03_kanban.py",
    "02_kanban", "03_kanban",
    "pages/02_KANBAN.py", "pages/03_KANBAN.py",
    "02_KANBAN", "03_KANBAN",
    "Kanban",
]

# --- Filtros de acceso (secrets) ---
auth_cfg = st.secrets.get("auth", {}) or {}
allowed_emails  = auth_cfg.get("allowed_emails", []) or []
allowed_domains = auth_cfg.get("allowed_domains", []) or []
if not allowed_emails and not allowed_domains:
    st.caption("⚠️ No hay filtros de acceso en `st.secrets['auth']`. Modo abierto (cualquier cuenta podrá iniciar sesión).")

# --- Login Google ---
user = google_login(
    allowed_emails=allowed_emails or None,
    allowed_domains=allowed_domains or None,
    redirect_page=None,   # el enrutamiento lo hacemos abajo
)
if not user:
    st.stop()

# --- Redirección a Gestión de tareas (una sola vez por sesión) ---
if not st.session_state.get("_routed_to_gestion_tareas", False):
    if _safe_switch_page(TARGET_TAREAS):
        st.session_state["_routed_to_gestion_tareas"] = True
    else:
        st.info("No pude redirigirte automáticamente. Usa el menú lateral 👉 **Gestión de tareas**.")

# --- Sidebar: navegación + usuario ---
with st.sidebar:
    st.header("Secciones")
    try:
        st.page_link("gestion_app.py", label="Inicio", icon="🏠")
    except Exception:
        st.markdown("<span style='opacity:.55;'>• 🏠 Inicio</span>", unsafe_allow_html=True)

    _safe_page_link(TARGET_TAREAS, label="Gestión de tareas", icon="🗂️")
    _safe_page_link(TARGET_KANBAN, label="Kanban", icon="🧩")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# --- Cuerpo (mensaje de aterrizaje) ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
