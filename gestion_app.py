# gestion_app.py  (Inicio / router)
import os, re
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

# ========= Helpers de navegación robusta =========
def _discover_pages(keywords: list[str]) -> list[str]:
    """
    Busca scripts .py que contengan todas las 'keywords' (case-insensitive)
    primero en ./pages y luego en la raíz. Devuelve rutas relativas ordenadas.
    """
    found = []
    kw = [k.lower() for k in keywords]
    for base in ("pages", "."):
        if not os.path.isdir(base): 
            continue
        for fn in os.listdir(base):
            if not fn.lower().endswith(".py"):
                continue
            name = fn.lower()
            if all(k in name for k in kw):
                path = os.path.join(base, fn) if base == "pages" else fn
                found.append(path)
    # Ordena priorizando numeración tipo "01_", "02_", etc.
    def _sort_key(p):
        m = re.match(r".*?(\d+)", os.path.basename(p))
        return (int(m.group(1)) if m else 9999, p.lower())
    return sorted(set(found), key=_sort_key)

def _safe_switch_page(targets: list[str]) -> bool:
    """Intenta cambiar de página probando varios targets. True si alguna funcionó."""
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
    Si ninguno existe, muestra un rótulo gris (no clickable).
    """
    for t in targets:
        try:
            st.page_link(t, label=label, icon=icon)
            return
        except Exception:
            continue
    st.markdown(f"<span style='opacity:.55;'>• {icon} {label}</span>", unsafe_allow_html=True)

# Variantes por si hiciera falta (backups)
TARGET_TAREAS_FALLBACKS = [
    "pages/01_gestion_tareas.py", "pages/02_gestion_tareas.py",
    "pages/01_GESTION_TAREAS.py", "pages/02_GESTION_TAREAS.py",
    "pages/01_Gestion_Tareas.py", "pages/02_Gestion_Tareas.py",
    "01_gestion_tareas", "02_gestion_tareas",
    "01_GESTION_TAREAS", "02_GESTION_TAREAS",
    "01_Gestion_Tareas", "02_Gestion_Tareas",
    "Gestión de tareas", "Gestion de tareas",
]

TARGET_KANBAN_FALLBACKS = [
    "pages/02_kanban.py", "pages/03_kanban.py",
    "pages/02_KANBAN.py", "pages/03_KANBAN.py",
    "02_kanban", "03_kanban", "02_KANBAN", "03_KANBAN",
    "Kanban",
]

# Descubrimiento real en el filesystem
FOUND_TAREAS = _discover_pages(["gestion", "tarea"])
FOUND_KANBAN = _discover_pages(["kanban"])

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
    redirect_page=None,   # enrutamos abajo
)
if not user:
    st.stop()

# --- Redirección a Gestión de tareas (una sola vez por sesión) ---
if not st.session_state.get("_routed_to_gestion_tareas", False):
    if _safe_switch_page(FOUND_TAREAS + TARGET_TAREAS_FALLBACKS):
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

    _safe_page_link(FOUND_TAREAS + TARGET_TAREAS_FALLBACKS, label="Gestión de tareas", icon="🗂️")
    _safe_page_link(FOUND_KANBAN + TARGET_KANBAN_FALLBACKS, label="Kanban", icon="🧩")

    st.divider()
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("_routed_to_gestion_tareas", None)
        logout()
        st.rerun()

# --- Cuerpo ---
st.info("Redirigiéndote a **Gestión de tareas**… Si no ocurre automáticamente, usa el menú lateral.")
