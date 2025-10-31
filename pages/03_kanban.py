# gestion_app.py — Router minimal: login -> switch a Gestión de tareas
import os, unicodedata
import streamlit as st
from auth_google import google_login

# --------- helpers para ubicar la página de Gestión de tareas ----------
def _norm(s: str) -> str:
    s = os.path.basename(s).lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s.replace(' ', '_')

def _pages_dir() -> str | None:
    # respeta mayúsculas/minúsculas en Linux
    for d in ("pages", "Pages", "PAGES"):
        if os.path.isdir(d):
            return d
    for d in os.listdir("."):
        if os.path.isdir(d) and d.lower() == "pages":
            return d
    return None

def _resolve_gt() -> str | None:
    pdir = _pages_dir()
    if not pdir:
        return None
    files = [f for f in os.listdir(pdir) if f.endswith(".py")]
    norm_map = {_norm(f"{pdir}/{f}"): f"{pdir}/{f}" for f in files}
    candidates = [
        "02_gestion_tareas.py","01_gestion_tareas.py",
        "gestion_tareas.py","gestion_de_tareas.py",
        "02_GESTION_TAREAS.py","01_GESTION_TAREAS.py",
    ]
    for c in candidates:
        k = _norm(c if c.startswith(pdir + "/") else f"{pdir}/{c}")
        if k in norm_map:
            return norm_map[k]
    # heurística: cualquier archivo que tenga "gestion" y "tarea"
    for k, p in norm_map.items():
        if "gestion" in k and ("tarea" in k or "tareas" in k):
            return p
    return None

GT_PAGE = _resolve_gt()

# --------- config visual básica (sin secciones ni sidebar) ----------
st.set_page_config(page_title="ENI2025 — Ingreso", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
/* oculta navegación nativa para que no aparezca “Páginas” */
[data-testid="stSidebarNav"]{display:none!important;}
section[data-testid="stSidebar"] nav{display:none!important;}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{display:none!important;}
</style>
""", unsafe_allow_html=True)

# --------- login (sin “Inicio”, solo botón Google) ----------
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or None
allowed_domains = auth_cfg.get("allowed_domains", []) or None

user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None  # nos quedamos aquí para hacer el salto manual
)
if not user:
    st.stop()  # se está mostrando la UI de login; no renders extra

# --------- salto automático a Gestión de tareas (una sola vez) ----------
if GT_PAGE and not st.session_state.get("_jumped_to_gt", False):
    st.session_state["_jumped_to_gt"] = True
    try:
        st.switch_page(GT_PAGE)
    except Exception:
        pass  # si algo falla, mostramos fallback abajo

# Fallback ultra mínimo si no pudo saltar:
if not GT_PAGE:
    st.error("No encontré la página **Gestión de tareas** en la carpeta `pages`. Revisa el nombre del archivo.")
else:
    st.info("Ingresaste correctamente. Abre **Gestión de tareas** desde el menú si no fuiste redirigida automáticamente.")
