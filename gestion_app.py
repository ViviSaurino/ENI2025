# gestion_app.py  (Inicio / router)
import os, unicodedata
import streamlit as st
from auth_google import google_login, logout

# -------- helpers de resolución de páginas ----------
def _norm(s: str) -> str:
    s = os.path.basename(s).lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s.replace(' ', '_')

def _pages_dir() -> str | None:
    for d in ("pages", "Pages", "PAGES"):
        if os.path.isdir(d):
            return d
    # por si existe con otra capitalización
    for d in os.listdir("."):
        if os.path.isdir(d) and d.lower() == "pages":
            return d
    return None

def _resolve_tareas(cands: list[str]) -> str | None:
    """Devuelve SOLO la página de 'gestión de tareas' o None (nunca kanban)."""
    pdir = _pages_dir()
    if not pdir:
        return None
    norm_map = {_norm(f"{pdir}/{f}"): f"{pdir}/{f}" for f in os.listdir(pdir) if f.endswith(".py")}
    for c in cands:
        k = _norm(c if c.startswith(pdir) else f"{pdir}/{c}")
        if k in norm_map:
            return norm_map[k]
    # heurística: archivos que contengan gestion + tarea(s)
    for k, p in norm_map.items():
        if "gestion" in k and ("tarea" in k or "tareas" in k):
            return p
    return None

def _resolve_kanban(cands: list[str]) -> str | None:
    """Devuelve la página de kanban (si no encuentra candidatos, usa la primera que contenga 'kanban')."""
    pdir = _pages_dir()
    if not pdir:
        return None
    norm_map = {_norm(f"{pdir}/{f}"): f"{pdir}/{f}" for f in os.listdir(pdir) if f.endswith(".py")}
    for c in cands:
        k = _norm(c if c.startswith(pdir) else f"{pdir}/{c}")
        if k in norm_map:
            return norm_map[k]
    for k, p in norm_map.items():
        if "kanban" in k:
            return p
    return None

GT_PAGE = _resolve_tareas([
    "01_gestion_tareas.py", "02_gestion_tareas.py",
    "gestion_tareas.py", "gestion_de_tareas.py",
    "Gestión de tareas.py", "GESTION_TAREAS.py",
])
KB_PAGE = _resolve_kanban([
    "03_kanban.py", "02_kanban.py", "kanban.py", "KANBAN.py",
])

# --- Config inicial ---
st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Oculta navegación nativa del sidebar
st.markdown("""
<style>
[data-testid="stSidebarNav"]{display:none!important;}
section[data-testid="stSidebar"] nav{display:none!important;}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{display:none!important;}
</style>
""", unsafe_allow_html=True)

# --- Filtros de acceso ---
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or []
allowed_domains = auth_cfg.get("allowed_domains", []) or []
if not allowed_emails and not allowed_domains:
    st.caption("⚠️ Modo abierto: sin filtros en `st.secrets['auth']`.")

# --- Login Google (sin redirect aquí para evitar bucles) ---
user = google_login(
    allowed_emails=allowed_emails if allowed_emails else None,
    allowed_domains=allowed_domains if allowed_domains else None,
    redirect_page=None,
)
if not user:
    st.stop()

# --- Redirigir una sola vez a Gestión de tareas (si existe) ---
def _try_switch_to_tasks() -> bool:
    if GT_PAGE:
        try:
            st.switch_page(GT_PAGE)
            return True
        except Exception:
            pass
    return False

if not st.session_state.get("_routed_to_gestion_tareas", False):
    if _try_switch_to_tasks():
        st.session_state["_routed_to_gestion_tareas"] = True
    else:
        st.info("No pude redirigirte automáticamente. Usa el menú lateral 👉 **Gestión de tareas**.")

# --- Sidebar: navegación + usuario ---
with st.sidebar:
    st.header("Secciones")
    st.page_link("gestion_app.py", label="Inicio", icon="🏠")
    if GT_PAGE:
        st.page_link(GT_PAGE, label="Gestión de tareas", icon="📁")
    else:
        st.markdown("• Gestión de tareas")
    if KB_PAGE:
        st.page_link(KB_PAGE, label="Kanban", icon="🧩")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# --- Cuerpo ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
