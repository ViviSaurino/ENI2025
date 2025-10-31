# gestion_app.py  (Inicio / router)
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
    Intenta dibujar un page_link contra varios targets.
    Muestra el primero que exista; si ninguno existe, muestra un texto deshabilitado.
    """
    for t in targets:
        try:
            st.page_link(t, label=label, icon=icon)
            return
        except Exception:
            continue
    # fallback visual (no clickable) para que no crashee
    st.markdown(f"<span style='opacity:.6;'>• {icon} {label}</span>", unsafe_allow_html=True)

# Mapas de posibles rutas/nombres según cómo hayas guardado los archivos en /pages
TARGET_TAREAS = [
    "pages/01_gestion_tareas.py",
    "pages/02_gestion_tareas.py",
    "01_gestion_tareas",
    "02_gestion_tareas",
    "Gestión de tareas",
    "Gestion de tareas",
]
TARGET_KANBAN = [
    "pages/02_kanban.py",
    "pages/03_kanban.py",
    "02_kanban",
    "03_kanban",
    "Kanban",
]

# --- Lectura de filtros de acceso (secrets) ---
auth_cfg = st.secrets.get("auth", {}) or {}
allowed_emails  = auth_cfg.get("allowed_emails", []) or []
allowed_domains = auth_cfg.get("allowed_domains", []) or []

if not allowed_emails and not allowed_domains:
    st.caption("⚠️ No hay filtros de acceso en `st.secrets['auth']`. Modo abierto (cualquier cuenta podrá iniciar sesión).")

# --- Login Google ---
# Nota: sin redirect_page para evitar reruns innecesarios; el router se maneja abajo.
user = google_login(
    allowed_emails=allowed_emails or None,
    allowed_domains=allowed_domains or None,
    redirect_page=None,
)
if not user:
    st.stop()

# --- Redirección automática a Gestión de tareas (solo 1 vez por sesión) ---
if not st.session_state.get("_routed_to_gestion_tareas", False):
    if _safe_switch_page(TARGET_TAREAS):
        st.session_state["_routed_to_gestion_tareas"] = True
    else:
        st.info("No pude redirigirte automáticamente. Usa el menú lateral 👉 **Gestión de tareas**.")

# --- Sidebar: navegación fija + usuario ---
with st.sidebar:
    st.header("Secciones")

    # Inicio siempre existe
    try:
        st.page_link("gestion_app.py", label="Inicio", icon="🏠")
    except Exception:
        st.markdown("<span style='opacity:.6;'>• 🏠 Inicio</span>", unsafe_allow_html=True)

    # Links robustos (no revientan si el archivo todavía no existe)
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
