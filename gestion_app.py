# -*- coding: utf-8 -*-
# ============================  
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd
from pathlib import Path
import importlib
import types
import base64  # para incrustar el video como base64

# ===== Import robusto de shared con fallbacks =====
def _fallback_ensure_df_main():
    import os
    path = os.path.join("data", "tareas.csv")
    os.makedirs("data", exist_ok=True)

    if "df_main" in st.session_state:
        return

    # columnas mínimas (mismas que vienes usando)
    base_cols = ["Id","Área","Responsable","Tarea","Prioridad",
                 "Evaluación","Fecha inicio","__DEL__"]
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            df = pd.read_csv(path, encoding="utf-8-sig")
        else:
            df = pd.DataFrame([], columns=base_cols)
    except Exception:
        df = pd.DataFrame([], columns=base_cols)

    if "__DEL__" not in df.columns:
        df["__DEL__"] = False
    df["__DEL__"] = df["__DEL__"].fillna(False).astype(bool)

    if "Calificación" in df.columns:
        df["Calificación"] = pd.to_numeric(df["Calificación"], errors="coerce").fillna(0).astype(int)

    st.session_state["df_main"] = df

try:
    _shared = importlib.import_module("shared")
    patch_streamlit_aggrid = getattr(_shared, "patch_streamlit_aggrid")
    inject_global_css      = getattr(_shared, "inject_global_css")
    ensure_df_main         = getattr(_shared, "ensure_df_main")
except Exception:
    # si shared.py tiene SyntaxError o falla el import, seguimos con stubs seguros
    patch_streamlit_aggrid = lambda: None
    inject_global_css      = lambda: None
    ensure_df_main         = _fallback_ensure_df_main

# 🔐 ACL / Roles
from features.security import acl
from utils.avatar import show_user_avatar_from_session

LOGO_PATH  = Path("assets/branding/eni2025_logo.png")
ROLES_XLSX = "data/security/roles.xlsx"

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

st.markdown("""
<style>
  .eni-banner{
    margin:6px 0 14px;
    font-weight:400;
    font-size:16px;
    color:#4B5563;
  }

  /* Botón Cerrar sesión en sidebar */
  section[data-testid="stSidebar"] .stButton > button{
    background:#C7A0FF !important;
    color:#FFFFFF !important;
    border:none !important;
    border-radius:12px !important;
    font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  section[data-testid="stSidebar"] .stButton > button:hover{
    filter:brightness(0.95);
  }

  section[data-testid="stSidebar"] .eni-logo-wrap{
    margin-left:-8px;
    margin-top:8px !important;
    margin-bottom:12px !important;
  }
  section[data-testid="stSidebar"] .block-container{
    padding-top:6px !important;
    padding-bottom:10px !important;
  }
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{
    gap:8px !important;
  }
  section[data-testid="stSidebar"] .avatar-wrap{
    margin:6px 0 6px !important;
  }
  section[data-testid="stSidebar"] .avatar-wrap img{
    border-radius:9999px !important;
  }
  section[data-testid="stSidebar"]{
    overflow-y:hidden !important;
  }

  /* Layout principal */
  html body [data-testid="stAppViewContainer"] .main .block-container{
    padding-top:0.5rem !important;
    margin-top:0rem !important;
  }

  /* Ocultar header nativo de Streamlit */
  header[data-testid="stHeader"]{
    height: 0px;
    padding: 0px;
    visibility: hidden;
  }

  /* Sidebar más angosto + iconos grises un poco más grandes */
  section[data-testid="stSidebar"]{
    min-width: 230px !important;
    max-width: 230px !important;
  }
  section[data-testid="stSidebar"] [data-testid="stRadio"] label{
    gap:0.35rem !important;
  }
  section[data-testid="stSidebar"] [data-testid="stRadio"] label span:first-child{
    font-size:1.15rem !important;
    color:#6B7280 !important;  /* gris icono */
  }
  section[data-testid="stSidebar"] [data-testid="stRadio"] label p{
    margin-bottom:0px !important;
    font-size:0.95rem !important;
  }

  /* Hero principal dentro de la app (tarjeta lila) */
  .eni-main-hero{
    margin-top: 0.5rem;
    margin-bottom: 1.0rem;
  }
  .eni-main-hero-label{
    font-size:1.05rem;
    font-weight:800;
    color:#4B5563;
    margin-bottom:0.25rem;
  }
  .eni-main-hero-card{
    background:#E5D8FF;
    border-radius:18px;
    padding:18px 32px;
  }
  .eni-main-hero-name{
    font-size:1.35rem;
    font-weight:800;
    color:#4C1D95;
  }
  .eni-main-hero-sub{
    font-size:0.9rem;
    color:#4B5563;
    margin-top:4px;
  }

  /* Contenedor de tarjetas de inicio */
  .eni-home-cards{
    margin-top: 1.4rem;
  }
  .eni-home-cards [data-testid="stHorizontalBlock"]{
    gap:16px !important;
  }
  .eni-home-cards [data-testid="stButton"] > button{
    width:100%;
    background:#FFFFFF;
    color:#111827;
    border-radius:18px;
    border:1px solid #E5E7EB;
    padding:18px 22px;
    box-shadow:0 10px 25px rgba(15,23,42,0.06);
    display:flex;
    flex-direction:row;
    justify-content:space-between;
    align-items:flex-start;
    text-align:left;
    white-space:normal;
  }
  /* Texto dentro de la tarjeta */
  .eni-home-cards [data-testid="stButton"] > button div p{
    font-size:0.95rem;
    line-height:1.4;
    white-space:pre-line;  /* respeta salto de línea \\n */
  }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN POR CONTRASEÑA ============
APP_PASSWORD = "Inei2025$"

def check_app_password() -> bool:
    """
    Portada tipo hero: BIENVENIDOS + píldora + contraseña.
    """

    st.markdown("""
    <style>
      .eni-hero-title{
        font-size:77px;
        font-weight:900;
        color:#B38CFB;
        line-height:0.80;
        margin-bottom:10px;
      }
      .eni-hero-pill{
        display:inline-block;
        padding:10px 53px;
        border-radius:12px;
        background-color:#C0C2FF;
        border:1px solid #C0C2FF;
        color:#FFFFFF;
        font-weight:700;
        font-size:14px;
        letter-spacing:0.04em;
        margin-bottom:10px;
        white-space:nowrap;
      }
      [data-testid="stAppViewContainer"] .main .stButton > button{
        background:#8FD9C1 !important;
        color:#FFFFFF !important;
        border-radius:12px !important;
        border:1px solid #8FD9C1 !important;
        font-weight:900 !important;
        letter-spacing:0.04em !important;
        text-transform:uppercase !important;
      }
      [data-testid="stAppViewContainer"] .main .stButton > button:hover{
        filter:brightness(0.97);
      }
      .eni-login-form [data-testid="stSelectbox"]{
        margin-bottom:0.0rem !important;
      }
      .eni-login-form [data-testid="stTextInput"]{
        margin-top:-0.45rem !important;
      }
    </style>
    """, unsafe_allow_html=True)

    if st.session_state.get("password_ok", False):
        return True

    st.markdown("""
    <style>
      html, body, [data-testid="stAppViewContainer"], .main{
        overflow: hidden !important;
      }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:7vh;'></div>", unsafe_allow_html=True)

    space_col, col1, col2 = st.columns([0.20, 0.55, 0.35])

    with space_col:
        st.write("")

    with col1:
        st.markdown("<div class='eni-hero-title'>BIEN<br>VENIDOS</div>", unsafe_allow_html=True)

        form_col, _ = st.columns([0.66, 0.60])
        with form_col:
            st.markdown("<div class='eni-login-form'>", unsafe_allow_html=True)

            st.markdown("<div class='eni-hero-pill'>GESTIÓN DE TAREAS ENI 2025</div>", unsafe_allow_html=True)
            st.write("")

            editor_options = [
                "Brayan Pisfil 😎",
                "Elizabet Cama 🌸",
                "Enrique Oyola 🧠",
                "Jaime Agreda 📘",
                "John Talla 🛠️",
                "Lucy Advíncula 🌈",
                "Stephane Grande 📊",
                "Tiffany Bautista ✨",
                "Vivian Saurino 💜",
                "Yoel Camizán 🚀",
            ]
            default_name = st.session_state.get("user_display_name", "")
            try:
                default_index = editor_options.index(default_name)
            except ValueError:
                default_index = 0

            editor_name = st.selectbox(
                "¿Quién está editando?",
                editor_options,
                index=default_index,
                key="editor_name_login",
            )
            st.session_state["user_display_name"] = editor_name

            pwd = st.text_input("Ingresa la contraseña", type="password", key="eni_pwd")

            if st.button("ENTRAR", use_container_width=True):
                if pwd == APP_PASSWORD:
                    st.session_state["password_ok"] = True
                    st.session_state["user_email"] = "eni2025@app"
                    st.session_state["user"] = {"email": "eni2025@app"}
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta. Vuelve a intentarlo 🙂")

            st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        hero_video = Path("assets/hero.mp4")
        logo_img   = Path("assets/branding/eni2025_logo.png")

        if hero_video.exists():
            with open(hero_video, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode("utf-8")
            video_html = f"""
            <div style="margin-left:-280px; margin-top:-120px;">
              <video autoplay loop muted playsinline
                     style="width:100%;max-width:460px;
                            display:block;margin:0;">
                <source src="data:video/mp4;base64,{b64}" type="video/mp4">
              </video>
            </div>
            """
            st.markdown(video_html, unsafe_allow_html=True)
        elif logo_img.exists():
            st.image(str(logo_img), use_column_width=True)
        else:
            st.write("")

    return False

if not check_app_password():
    st.stop()

# ============ AUTENTICACIÓN (usuario genérico) ============
email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "eni2025@app")

# ============ Carga de ROLES / ACL ============
try:
    if "roles_df" not in st.session_state:
        st.session_state["roles_df"] = acl.load_roles(ROLES_XLSX)
    user_acl = acl.find_user(st.session_state["roles_df"], email)
except Exception as _e:
    st.error("No pude cargar el archivo de roles. Verifica data/security/roles.xlsx.")
    st.stop()

def _to_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("true", "verdadero", "sí", "si", "1", "x", "y")

if user_acl is None:
    user_acl = {}

for _k in ("is_active", "can_edit_all_tabs"):
    if _k in user_acl:
        user_acl[_k] = _to_bool(user_acl[_k])

user_acl["is_active"] = True
user_acl["can_edit_all_tabs"] = True

try:
    _roles_df = st.session_state.get("roles_df")
    if isinstance(_roles_df, pd.DataFrame):
        mask_me = _roles_df["email"].astype(str).str.lower() == (email or "").lower()
        if mask_me.any():
            _roles_df.loc[mask_me, "is_active"] = True
            _roles_df.loc[mask_me, "can_edit_all_tabs"] = True
            st.session_state["roles_df"] = _roles_df
except Exception:
    pass

if not user_acl or not user_acl.get("is_active", False):
    st.error("No tienes acceso (usuario no registrado o inactivo).")
    st.stop()

_ok, _msg = acl.can_access_now(user_acl)
if not _ok:
    st.info(_msg)
    st.stop()

st.session_state["acl_user"] = user_acl
st.session_state["user_display_name"] = st.session_state.get("user_display_name") or user_acl.get("display_name", email or "Usuario")
st.session_state["user_dry_run"] = bool(user_acl.get("dry_run", False))
st.session_state["save_scope"] = user_acl.get("save_scope", "all")

display_name = st.session_state["user_display_name"]

# ========= Hook "maybe_save" + Google Sheets =========
def _push_gsheets(df: pd.DataFrame):
    if "gsheets" not in st.secrets or "gcp_service_account" not in st.secrets:
        raise KeyError("Faltan 'gsheets' o 'gcp_service_account' en secrets.")
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
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

# ====== Logout local ======
def logout():
    for k in ("user", "user_email", "password_ok", "acl_user",
              "auth_ok", "nav_section", "roles_df", "selected_home_view"):
        st.session_state.pop(k, None)
    st.rerun()

# Mapeo de claves de pestaña para permisos
TAB_KEY_BY_SECTION = {
    "📘 Gestión de tareas": "tareas_recientes",
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

    nav_labels = ["📘 Gestión de tareas","🗂️ Kanban","📅 Gantt","📊 Dashboard"]
    current_section = st.session_state.get("nav_section", "📘 Gestión de tareas")
    # 🔧 Fix ValueError: si quedó algo viejo en sesión, volvemos a 'Gestión de tareas'
    if current_section not in nav_labels:
        current_section = "📘 Gestión de tareas"
    default_idx = nav_labels.index(current_section)

    st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False
    )

    st.divider()
    show_user_avatar_from_session(size=150)
    st.markdown(f"👋 **Hola, {display_name}**")
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ============ UI principal ============
section = st.session_state.get("nav_section", "📘 Gestión de tareas")
tab_key = TAB_KEY_BY_SECTION.get(section, "tareas_recientes")

if section == "📘 Gestión de tareas":
    # ---- Hero principal ----
    st.markdown(f"""
    <div class="eni-main-hero">
      <div class="eni-main-hero-label"><strong>Bienvenid@</strong></div>
      <div class="eni-main-hero-card">
        <div class="eni-main-hero-name">{display_name}</div>
        <div class="eni-main-hero-sub">A la plataforma unificada Gestión - ENI2025</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Tarjetas de inicio (6 tarjetas, 3 x fila) ----
    selected_view = st.session_state.get("selected_home_view", "Nueva tarea")

    st.markdown('<div class="eni-home-cards">', unsafe_allow_html=True)

    # Fila 1
    col1, col2, col3 = st.columns(3)
    with col1:
        label = "Nueva tarea 📝\nRegistrar una nueva tarea asignada."
        if st.button(label, key="card_nueva_tarea"):
            st.session_state["selected_home_view"] = "Nueva tarea"
            selected_view = "Nueva tarea"
    with col2:
        label = "Editar estado ✏️\nActualizar fases y fechas de las tareas."
        if st.button(label, key="card_editar_estado"):
            st.session_state["selected_home_view"] = "Editar estado"
            selected_view = "Editar estado"
    with col3:
        label = "Nueva alerta ⚠️\nRegistrar alertas y riesgos prioritarios."
        if st.button(label, key="card_nueva_alerta"):
            st.session_state["selected_home_view"] = "Nueva alerta"
            selected_view = "Nueva alerta"

    # Fila 2
    col4, col5, col6 = st.columns(3)
    with col4:
        label = "Prioridad ⭐\nRevisar y ajustar la prioridad de tareas."
        if st.button(label, key="card_prioridad"):
            st.session_state["selected_home_view"] = "Prioridad"
            selected_view = "Prioridad"
    with col5:
        label = "Evaluación y cumplimiento 📊\nCalificar avances y visualizar el nivel de cumplimiento."
        if st.button(label, key="card_eval_cump"):
            st.session_state["selected_home_view"] = "Evaluación y cumplimiento"
            selected_view = "Evaluación y cumplimiento"
    with col6:
        label = "Tareas recientes ⏱️\nResumen de las últimas tareas actualizadas."
        if st.button(label, key="card_tareas_recientes"):
            st.session_state["selected_home_view"] = "Tareas recientes"
            selected_view = "Tareas recientes"

    st.markdown("</div>", unsafe_allow_html=True)

    st.write("")
    st.caption(
        f"Vista seleccionada: **{selected_view}** "
        "(contenido específico se implementará dentro de la app)."
    )

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

else:
    st.title("📊 Dashboard")
    def _render_dashboard():
        st.caption("Próximamente: visualizaciones y KPIs del dashboard.")
        st.write("")
    render_if_allowed(tab_key, _render_dashboard)
