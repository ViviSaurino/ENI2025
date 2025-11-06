# ============================  
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd
from pathlib import Path

from auth_google import google_login, logout
from shared import ensure_df_main, inject_global_css, patch_streamlit_aggrid  # ✅ import seguro

# 🔐 ACL / Roles
from features.security import acl  # <-- NUEVO
from utils.avatar import show_user_avatar_from_session  # <-- NUEVO (import avatar)

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
    font-weight:400;
    font-size:16px;
    color:#4B5563;
  }
  section[data-testid="stSidebar"] .stButton > button{
    background:#C7A0FF !important;
    color:#FFFFFF !important;
    border:none !important;
    border-radius:12px !important;
    font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  section[data-testid="stSidebar"] .stButton > button:hover{ filter:brightness(0.95); }

  /* Logo un poco más a la izquierda */
  section[data-testid="stSidebar"] .eni-logo-wrap{ margin-left:-28px; }

  /* Radio de navegación: más compacto */
  .eni-nav label{ padding:6px 8px !important; }

  /* Compactar sidebar */
  section[data-testid="stSidebar"] .block-container{
    padding-top:6px !important;
    padding-bottom:10px !important;
  }
  section[data-testid="stSidebar"] .eni-logo-wrap{ margin-top:-6px !important; }
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{ gap:8px !important; }
  section[data-testid="stSidebar"] .avatar-wrap{ margin:6px 0 6px !important; }
  section[data-testid="stSidebar"] .avatar-wrap img{ border-radius:9999px !important; }
  section[data-testid="stSidebar"]{ overflow-y:hidden !important; }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN ============
if "user" not in st.session_state:
    google_login()
    st.stop()

email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

# ============ Carga de ROLES / ACL ============
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

# ========= Hook "maybe_save" + Google Sheets =========
def _push_gsheets(df: pd.DataFrame):
    if "gsheets" not in st.secrets or "gcp_service_account" not in st.secrets:
        raise KeyError("Faltan 'gsheets' o 'gcp_service_account' en secrets.")

    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(st.secrets["gsheets"]["spreadsheet_url"])
    ws_name = st.secrets["gsheets"].get("worksheet", "TareasRecientes")

    try:
        ws = ss.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        rows = str(max(1000, len(df) + 10))
        cols = str(max(26, len(df.columns) + 5))
        ws = ss.add_worksheet(title=ws_name, rows=rows, cols=cols)

    df_out = df.copy().fillna("").astype(str)
    values = [list(df_out.columns)] + df_out.values.tolist()
    ws.clear()
    ws.update("A1", values)

def _maybe_save_chain(persist_local_fn, df: pd.DataFrame):
    res = acl.maybe_save(user_acl, persist_local_fn, df)
    try:
        if st.session_state.get("user_dry_run", False):
            res["msg"] = res.get("msg", "") + " | DRY-RUN: no se sincronizó Google Sheets."
            return res
        _push_gsheets(df)
        res["msg"] = res.get("msg", "") + " | Sincronizado a Google Sheets."
    except Exception as e:
        res["msg"] = res.get("msg", "") + f" | GSheets error: {e}"
    return res

st.session_state["maybe_save"] = _maybe_save_chain
# ========= FIN hook =========

# Mapeo de claves de pestaña para permisos
TAB_KEY_BY_SECTION = {
    "🧰 Gestión de tareas": "tareas_recientes",
    "🗂️ Kanban": "kanban",
    "📅 Gantt": "gantt",
    "📊 Dashboard": "dashboard",
}

def render_if_allowed(tab_key: str, render_fn):
    if acl.can_see_tab(user_acl, tab_key):
        render_fn()
    else:
        st.warning("No tienes permiso para esta sección.")

# ============ Sidebar ============
with st.sidebar:
    if LOGO_PATH.exists():
        st.markdown("<div class='eni-logo-wrap'>", unsafe_allow_html=True)
        st.image(str(LOGO_PATH), width=120)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='eni-banner'>Esta es la plataforma unificada para gestión - ENI2025</div>", unsafe_allow_html=True)

    st.header("Secciones")
    nav_labels = [
        "📘 Gestión de tareas",
        "🗂️ Kanban",
        "📅 Gantt",
        "📊 Dashboard",
    ]
    default_idx = nav_labels.index(st.session_state.get("nav_section", "📘 Gestión de tareas"))
    nav_choice = st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False,
    )

    st.divider()
    dn = st.session_state.get("user_display_name", email or "Usuario")
    show_user_avatar_from_session(size=150)
    st.markdown(f"👋 **Hola, {dn}**")
    st.caption(f"**Usuario:** {email or '—'}")
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ============ UI principal ============
section = st.session_state.get("nav_section", "📘 Gestión de tareas")
tab_key = TAB_KEY_BY_SECTION.get(section, "tareas_recientes")

if section == "📘 Gestión de tareas":
    st.title("📘 Gestión de tareas")

    # --- WRAPPER + CSS ANTI-BOTÓN FANTASMA ---
    st.markdown('<div class="eni-gestion-wrap">', unsafe_allow_html=True)

    def _render_gestion():
        try:
            from features.dashboard.view import render_all
            render_all(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista de Gestión de tareas pendiente.")
            st.exception(e)

    render_if_allowed(tab_key, _render_gestion)

    # ✅ Oculta cualquier stButton fuera de .hist-actions (fila oficial) y .hist-search (Buscar)
    st.markdown("""
    <style>
      .eni-gestion-wrap .stButton{ display:none !important; }
      .eni-gestion-wrap .hist-actions .stButton,
      .eni-gestion-wrap .hist-search .stButton{ display:inline-flex !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # cierre del wrapper

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
        st.caption("Próximamente: visualizaciones y KPIs del dashboard.")
        st.write("")

    render_if_allowed(tab_key, _render_dashboard)
