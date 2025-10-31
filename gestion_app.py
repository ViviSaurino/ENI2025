# gestion_app.py  (Inicio / router)
import os, unicodedata, re
import streamlit as st
from auth_google import google_login, logout

# ---------------- RESOLUCIÓN DE PÁGINAS (robusto) ----------------
def _norm(s: str) -> str:
    """lower + sin acentos + guiones bajos."""
    s = os.path.basename(s).strip()
    s = ''.join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s.lower().replace(" ", "_")

def _pages_dir() -> str | None:
    # Busca carpeta "pages" con cualquier capitalización
    for d in os.listdir("."):
        if os.path.isdir(d) and d.lower() == "pages":
            return d
    return None

def _list_pages() -> list[str]:
    pdir = _pages_dir()
    if not pdir:
        return []
    return [os.path.join(pdir, f) for f in os.listdir(pdir) if f.endswith(".py")]

def _match_by_names(files: list[str], candidates: list[str]) -> str | None:
    """Match exacto por nombre conocido (tolerante a mayúsculas/acentos)."""
    if not files:
        return None
    files_map = {_norm(f): f for f in files}
    for cand in candidates:
        key = _norm(cand if cand.startswith("pages/") else f"pages/{cand}")
        if key in files_map:
            return files_map[key]
    return None

def _match_by_keywords(files: list[str], require_all: list[str]) -> str | None:
    """Match por palabras clave en el nombre del archivo (orden libre)."""
    if not files:
        return None
    req = [r.lower() for r in require_all]
    for f in files:
        k = _norm(f)
        if all(r in k for r in req):
            return f
    return None

def resolve_tareas() -> str | None:
    files = _list_pages()
    # 1) coincidencias directas más comunes
    exact = _match_by_names(files, [
        "01_gestion_tareas.py", "02_gestion_tareas.py",
        "gestion_tareas.py", "gestion_de_tareas.py",
        "Gestión de tareas.py", "GESTION_TAREAS.py",
    ])
    if exact: return exact
    # 2) heurística por keywords (gestión + tarea)
    return _match_by_keywords(files, ["gestion", "tarea"])

def resolve_kanban() -> str | None:
    files = _list_pages()
    exact = _match_by_names(files, [
        "03_kanban.py", "02_kanban.py", "kanban.py", "KANBAN.py",
    ])
    if exact: return exact
    return _match_by_keywords(files, ["kanban"])

GT_PAGE = resolve_tareas()   # ← SOLO gestión de tareas (nunca kanban)
KB_PAGE = resolve_kanban()

# ---------------- CONFIG INICIAL ----------------
st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Ocultar navegación nativa para tener sidebar fijo personalizado
st.markdown("""
<style>
[data-testid="stSidebarNav"]{display:none!important;}
section[data-testid="stSidebar"] nav{display:none!important;}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{display:none!important;}
</style>
""", unsafe_allow_html=True)

# ---------------- LOGIN ----------------
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or []
allowed_domains = auth_cfg.get("allowed_domains", []) or []
if not allowed_emails and not allowed_domains:
    st.caption("⚠️ Modo abierto: sin filtros en `st.secrets['auth']`.")

user = google_login(
    allowed_emails=allowed_emails if allowed_emails else None,
    allowed_domains=allowed_domains if allowed_domains else None,
    redirect_page=None,       # evita bucles
)
if not user:
    st.stop()

# ---------------- REDIRECCIÓN (una sola vez) ----------------
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

# ---------------- SIDEBAR (3 secciones, cada una a su página) ----------------
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

    st.markdown("---")
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# ---------------- CUERPO ----------------
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
