# gestion_app.py  (Inicio / router)
import os, unicodedata
import streamlit as st
from auth_google import google_login, logout

# --- Config inicial ---
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

# ---------- Resolver robusto de páginas (como en Kanban) ----------
def _norm(s: str) -> str:
    s = os.path.basename(s).lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s.replace(' ', '_')

def _pages_dir() -> str | None:
    # detecta "pages" en cualquier casing
    for d in ("pages", "Pages", "PAGES"):
        if os.path.isdir(d):
            return d
    for d in os.listdir("."):
        if os.path.isdir(d) and d.lower() == "pages":
            return d
    return None

def _resolve(cands: list[str]) -> str | None:
    pdir = _pages_dir()
    if not pdir:
        return None
    files = [f for f in os.listdir(pdir) if f.endswith(".py")]
    norm_map = {_norm(f"{pdir}/{f}"): f"{pdir}/{f}" for f in files}
    # intenta candidatos exactos
    for c in cands:
        k = _norm(c if c.startswith((pdir + "/", pdir + "\\")) else f"{pdir}/{c}")
        if k in norm_map:
            return norm_map[k]
    # heurística por keywords
    for k, p in norm_map.items():
        if "gestion" in k and ("tarea" in k or "tareas" in k):
            return p
    for k, p in norm_map.items():
        if "kanban" in k:
            return p
    return None

GT_PAGE = _resolve([
    "02_gestion_tareas.py", "01_gestion_tareas.py",
    "gestion_tareas.py", "gestion_de_tareas.py",
    "02_GESTION_TAREAS.py", "01_GESTION_TAREAS.py",
])
KB_PAGE = _resolve(["03_kanban.py", "02_kanban.py", "kanban.py"])

# --- Lectura de filtros de acceso (secrets) ---
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or None
allowed_domains = auth_cfg.get("allowed_domains", []) or None

# --- Login Google ---
user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None  # nos quedamos aquí
)
if not user:
    st.stop()

# --- Redirección a Gestión de tareas (solo una vez y solo si existe) ---
def _try_switch_page():
    if GT_PAGE:
        try:
            st.switch_page(GT_PAGE)
            return True
        except Exception:
            pass
    # intentos alternos por nombre/slug
    for t in ("02_gestion_tareas", "Gestión de tareas", "Gestion de tareas"):
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

    st.page_link("gestion_app.py", label="Inicio", icon="🏠")

    if GT_PAGE:
        st.page_link(GT_PAGE, label="Gestión de tareas", icon="📁")
    else:
        st.markdown("• Gestión de tareas")

    if KB_PAGE:
        st.page_link(KB_PAGE, label="Kanban", icon="🧩")
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
