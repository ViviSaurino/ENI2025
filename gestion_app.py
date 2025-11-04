# ============================ 
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd
from pathlib import Path

from auth_google import google_login, logout
from shared import (
    patch_streamlit_aggrid,
    inject_global_css,
    ensure_df_main,
)

# 🔐 ACL / Roles
from features.security import acl  # <-- NUEVO

# Ruta del logo (arriba, a la izquierda del sidebar)
LOGO_PATH = Path("assets/branding/eni2025_logo.png")
ROLES_XLSX = "data/security/roles.xlsx"  # <-- NUEVO

# ============ Config de página ============
st.set_page_config(
    page_title="Gestión — ENI2025",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ Parches/estilos globales ============
patch_streamlit_aggrid()
inject_global_css()

# 👉 Estilos específicos (banner + botón cerrar sesión + logo más a la izquierda)
st.markdown("""
<style>
  .eni-banner{
    margin:6px 0 14px;
    font-weight:400;  /* sin negrita */
    font-size:16px;
    color:#4B5563;
  }
  section[data-testid="stSidebar"] .stButton > button{
    background:#C7A0FF !important;
    color:#FFFFFF !important;
    border:none !important;
    border-radius:12px !important;  /* menos curvatura */
    font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  section[data-testid="stSidebar"] .stButton > button:hover{ filter:brightness(0.95); }

  /* Logo un poco más a la izquierda */
  section[data-testid="stSidebar"] .eni-logo-wrap{ margin-left:-28px; }

  /* Radio de navegación: más compacto */
  .eni-nav label{ padding:6px 8px !important; }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN ============
if "user" not in st.session_state:
    google_login()
    st.stop()

email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

# ============ Carga de ROLES / ACL (NUEVO) ============
try:
    if "roles_df" not in st.session_state:
        st.session_state["roles_df"] = acl.load_roles(ROLES_XLSX)
    user_acl = acl.find_user(st.session_state["roles_df"], email)
except Exception as _e:
    st.error("No pude cargar el archivo de roles. Verifica data/security/roles.xlsx.")
    st.stop()

if not user_acl or not user_acl.get("is_active", False):
    st.error("No tienes acceso (usuario no registrado o inactivo).")
    st.stop()

# Restringir por horario / fines de semana
_ok, _msg = acl.can_access_now(user_acl)
if not _ok:
    st.info(_msg)
    st.stop()

# Helpers/flags para otras vistas
st.session_state["acl_user"] = user_acl
st.session_state["user_display_name"] = user_acl.get("display_name", email or "Usuario")
st.session_state["user_dry_run"] = bool(user_acl.get("dry_run", False))
st.session_state["save_scope"] = user_acl.get("save_scope", "all")
# Wrapper para persistencias (por si luego lo usas en features)
st.session_state["maybe_save"] = lambda fn, *a, **k: acl.maybe_save(user_acl, fn, *a, **k)

# Mapeo de claves de pestaña para permisos
TAB_KEY_BY_SECTION = {
    "🧰 Gestión de tareas": "tareas_recientes",
    "🗂️ Kanban": "kanban",
    "📅 Gantt": "gantt",
    "📊 Dashboard": "dashboard",
}

def render_if_allowed(tab_key: str, render_fn):
    """Dibuja la vista solo si el usuario tiene permiso por pestaña."""
    if acl.can_see_tab(user_acl, tab_key):
        render_fn()
    else:
        st.warning("No tienes permiso para esta sección.")

# ============ Sidebar ============
with st.sidebar:
    # Logo
    if LOGO_PATH.exists():
        st.markdown("<div class='eni-logo-wrap'>", unsafe_allow_html=True)
        st.image(str(LOGO_PATH), width=120)
        st.markdown("</div>", unsafe_allow_html=True)

    # Banner
    st.markdown("<div class='eni-banner'>Esta es la plataforma unificada para gestión - ENI2025</div>", unsafe_allow_html=True)

    # Navegación (clicable) solicitada
    st.header("Secciones")
    nav_labels = [
        "🧰 Gestión de tareas",
        "🗂️ Kanban",
        "📅 Gantt",
        "📊 Dashboard",
    ]
    default_idx = nav_labels.index(st.session_state.get("nav_section", "🧰 Gestión de tareas"))
    nav_choice = st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False,
    )

    st.divider()
    # Saludo con display_name y avatar (si hay)
    dn = st.session_state.get("user_display_name", email or "Usuario")
    st.markdown(f"👋 **Hola, {dn}**")
    if user_acl.get("avatar_url"):
        st.image(user_acl["avatar_url"], width=72)
    st.caption(f"**Usuario:** {email or '—'}")
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ============ UI principal ============
# Ruteo a vistas según la opción elegida en el sidebar
section = st.session_state.get("nav_section", "🧰 Gestión de tareas")
tab_key = TAB_KEY_BY_SECTION.get(section, "tareas_recientes")

if section == "🧰 Gestión de tareas":
    st.title("🧰 Gestión de tareas")

    def _render_gestion():
        try:
            # Reutilizamos la vista funcional del Dashboard
            from features.dashboard.view import render_all
            render_all(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista de Gestión de tareas pendiente.")
            st.exception(e)

    render_if_allowed(tab_key, _render_gestion)

elif section == "🗂️ Kanban":
    st.title("🗂️ Kanban")

    def _render_kanban():
        try:
            from features.kanban.view import render as render_kanban
            render_kanban(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista Kanban pendiente (features/kanban/view.py).")
            st.exception(e)

    render_if_allowed(tab_key, _render_kanban)

elif section == "📅 Gantt":
    st.title("📅 Gantt")

    def _render_gantt():
        try:
            from features.gantt.view import render as render_gantt
            render_gantt(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista Gantt pendiente (features/gantt/view.py).")
            st.exception(e)

    render_if_allowed(tab_key, _render_gantt)

else:  # "📊 Dashboard"
    st.title("📊 Dashboard")

    def _render_dashboard():
        # 🔹 Por ahora no hay contenido; dejamos la sección en blanco con un placeholder suave
        st.caption("Próximamente: visualizaciones y KPIs del dashboard.")
        st.write("")  # espacio en blanco

    render_if_allowed(tab_key, _render_dashboard)
v
