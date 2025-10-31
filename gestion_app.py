# gestion_app.py  (Inicio / router)
import streamlit as st
from auth_google import google_login, logout

# ---------------- Config inicial ----------------
st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="expanded",
)

# (Opcional) Oculta navegación nativa si la tuvieras en otro layout
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ---------------- Login ----------------
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or None
allowed_domains = auth_cfg.get("allowed_domains", []) or None

user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None   # ← no forzamos redirección aquí
)
if not user:
    st.stop()

# ---------------- Rutas constantes (SIN autodetección) ----------------
HOME_PAGE = "gestion_app.py"
GT_PAGE   = "pages/02_gestion_tareas.py"
KB_PAGE   = "pages/03_kanban.py"

# ---------------- Sidebar fijo y correcto ----------------
with st.sidebar:
    st.header("Secciones")
    st.page_link(HOME_PAGE, label="Inicio",             icon="🏠")
    st.page_link(GT_PAGE,   label="Gestión de tareas",  icon="📁")
    st.page_link(KB_PAGE,   label="Kanban",             icon="🧩")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# ---------------- Cuerpo (Inicio minimal) ----------------
st.title("🏠 Inicio")
st.caption("Bienvenida a ENI2025 — Panel de gestión.")

# Intento de redirección silencioso (solo una vez). Si falla, no molesta.
if not st.session_state.get("_routed_to_gestion_tareas", False):
    try:
        st.session_state["_routed_to_gestion_tareas"] = True
        st.switch_page(GT_PAGE)
        st.stop()
    except Exception:
        pass

# Botón manual (por si el switch_page no está disponible en el entorno)
if st.button("Ir a Gestión de tareas", type="primary"):
    try:
        st.switch_page(GT_PAGE)
        st.stop()
    except Exception:
        st.info("Abre **Gestión de tareas** desde el menú lateral.")
