# -*- coding: utf-8 -*- 
# ============================  
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd
from pathlib import Path
import importlib
import base64  # para incrustar el video como base64
from urllib.parse import quote  # para codificar el nombre en la URL

# ===== Import robusto de shared con fallbacks =====
def _fallback_ensure_df_main():
    import os
    path = os.path.join("data", "tareas.csv")
    os.makedirs("data", exist_ok=True)

    if "df_main" in st.session_state:
        return

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
    patch_streamlit_aggrid = lambda: None
    inject_global_css      = lambda: None
    ensure_df_main         = _fallback_ensure_df_main

# 🔐 ACL / Roles
from features.security import acl
from utils.avatar import show_user_avatar_from_session  # por si luego lo usamos

LOGO_PATH = Path("assets/branding/eni2025_logo.png")
HEADER_IMG_PATH = Path("assets/ENCABEZADO.png")  # 👈 nuevo banner horizontal
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

# 👉 Estilos específicos (sidebar + layout + topbar + tarjetas)
st.markdown(
    """
<style>
  /* ===== Fondo general de la APP → BLANCO ===== */
  html, body, [data-testid="stAppViewContainer"]{
    background:#FFFFFF;
  }

  .eni-banner{
    margin:6px 0 14px;
    font-weight:400;
    font-size:16px;
    color:#4B5563;
  }

  /* Oculta bloques de código / fragmentos sueltos tipo </div> */
  div[data-testid="stCodeBlock"],
  pre,
  code{
    display:none !important;
  }

  /* ===== Fila superior: Gestión de tareas + VS EN RECTÁNGULO BLANCO ===== */
  .eni-main-topbar{
    background:#FFFFFF;
    border-radius:8px;
    border:1px solid #E5E7EB;
    padding:10px 20px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin:6px -45px 18px -50px;   /* top  right  bottom  left */
    box-shadow:0 6px 16px rgba(15,23,42,0.06);
  }
  .eni-main-topbar-title{
    font-size:15px;
    font-weight:700;
    color:#374151;
    letter-spacing:0.08em;
    text-transform:uppercase;
  }
  .eni-main-topbar-user{
    display:flex;
    align-items:center;
    gap:8px;
    font-size:13px;
    color:#4B5563;
  }
  .eni-main-topbar-avatar{
    width:38px;
    height:38px;
    border-radius:999px;
    background:#C4B5FD;
    display:flex;
    align-items:center;
    justify-content:center;
    color:#FFFFFF;
    font-weight:700;
    font-size:15px;
  }

  /* ===== Banner horizontal ENCABEZADO debajo del topbar ===== */
  .eni-main-hero{
    margin:0 -45px 22px -50px;   /* mismo ancho que el topbar */
    border-radius:0px;
    box-shadow:0 18px 40px rgba(148,163,184,0.32);
    height:190px; 
    background:linear-gradient(90deg,  #93C5FD 0%, #B157D6 100%);
    position:relative;
    overflow:hidden;
  }
  .eni-main-hero-img{
    position:absolute;
    right:40px; 
    bottom:0;
    height:200px; 
    width:auto; 
  }

  /* ===== Card lila principal (ya no se usa, pero lo dejo por si acaso) ===== */
  .eni-main-card-header{
    background:#C4B5FD;
    border-radius:8px;
    padding:22px 28px;
    box-shadow:0 18px 40px rgba(148,163,184,0.35);
    margin:0 -10px 26px -50px;
  }
  .eni-main-card-header-title{
    font-size:22px;
    font-weight:800;
    color:#FFFFFF;
    margin-bottom:4px;
  }
  .eni-main-card-header-sub{
    font-size:12px;
    color:#F9FAFB;
    margin:0;
  }

  /* ===== Panel blanco debajo de cabecera (ya no se usa aquí) ===== */
  .eni-panel-card{
    background:#FFFFFF;
    border-radius:8px;
    min-height:303px;
    box-shadow:0 10px 26px rgba(148,163,184,0.18);
    padding:18px 24px;
    margin:0 -10px -8px -50px;
  }

  /* Contenedor general para vistas a ancho completo (Editar estado, etc.) */
  .eni-view-wrapper{
    margin-top:-8px;
  }

  /* ===== Sidebar plomito clarito ===== */
  section[data-testid="stSidebar"] .stButton > button{
    border-radius:8px !important;
    font-weight:600 !important;
  }

  section[data-testid="stSidebar"] .eni-logo-wrap{
    margin-left:-10px;
    margin-top:-6px !important;
  }
  section[data-testid="stSidebar"] .block-container{
    padding-top:6px !important;
    padding-bottom:10px !Important;
  }
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{
    gap:8px !important;
  }

  [data-testid="stSidebar"]{
    overflow-y:hidden !important;
    background:#F3F4F6 !important;   /* gris muy clarito */
    min-width:230px !important;
    max-width:230px !important;
    color:#111827 !important;
    border-right:1px solid #E5E7EB;
  }

  /* Menú de secciones */
  section[data-testid="stSidebar"] .stRadio > div{
    gap:4px !important;
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"]{
    margin-bottom:8px;
    padding:8px 10px;
    border-radius:12px;
    background:transparent;
    transition:all .15s ease-in-out;
    display:flex;
    flex-direction:row;
    align-items:center;
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child{
    display:none !important;   /* oculta el botón redondo */
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"] > div:last-child{
    padding-left:6px !important;
    font-size:13px;
    font-weight:500;
  }
  /* Opción ACTIVA */
  section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="true"]{
    background:#C4B5FD !important;
    color:#FFFFFF !important;
    border-radius:14px !important;
    border:1px solid #A855F7 !important;
    box-shadow:0 6px 14px rgba(148,163,184,0.45);
  }
  /* Opciones INACTIVAS */
  section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="false"]{
    background:transparent !important;
    color:#4B5563 !important;
    border-radius:14px !important;
    border:1px solid transparent !important;
    box-shadow:none !important;
  }

  /* Iconitos del menú lateral */
  section[data-testid="stSidebar"] [data-baseweb="radio"]::before{
    font-size:18px;
    margin-right:8px;
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(1)::before{
    content:"📋";
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(2)::before{
    content:"🗂️";
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(3)::before{
    content:"📅";
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(4)::before{
    content:"📊";
  }

  *::-webkit-scrollbar{
    width:0px;
    height:0px;
  }

  header[data-testid="stHeader"]{
    height:0px;
    padding:0px;
    visibility:hidden;
  }

  html body [data-testid="stAppViewContainer"] .main .block-container{
    padding-top:0rem !important;
    margin-top:-1rem !important;
    background:transparent;
  }

  /* ===== Grid de tarjetas rápidas (derecha) ===== */
  .eni-quick-grid-wrapper{
    margin:0px -45px 18px 0;
  }

  .eni-quick-column{
    display:flex;
    flex-direction:column;
    gap:13px;
  }

  .eni-quick-grid{
    display:grid;
    grid-template-columns:repeat(2, 1fr);
    gap:16px;
    align-items:stretch;
    grid-auto-rows:143px;
    margin-top:10px;
  }

  .eni-quick-card-link,
  .eni-quick-card-link:link,
  .eni-quick-card-link:visited,
  .eni-quick-card-link:hover,
  .eni-quick-card-link:active{
      text-decoration:none !important;
      color:inherit;
  }
  .eni-quick-card-link:focus-visible{
      outline:none;
  }

  .eni-quick-card{
    border-radius:8px;
    padding:16px 12px 12px 16px;
    box-shadow:0 10px 22px rgba(148,163,184,0.40);
    border:none;
    height:143px;
    display:flex;
    flex-direction:column;
    justify-content:space-between;
    align-items:flex-start;
    transition:all .15s ease-in-out;
    overflow:hidden;
  }

  .eni-quick-card-text{
    max-width:100%;
  }
  .eni-quick-card-title{
    font-size:14px;
    font-weight:700;
    color:#FFFFFF;
    margin-bottom:4px;
  }
  .eni-quick-card-sub{
    font-size:11px;
    color:#F9FAFB;
    margin:0;
  }
  .eni-quick-card-icon{
    font-size:42px;
    margin-left:60px;
    transform:translateY(-8px);
  }
  .eni-quick-card-link:hover .eni-quick-card{
    box-shadow:0 14px 28px rgba(148,163,184,0.55);
    transform:translateY(-2px);
  }
  .eni-quick-card--nueva_tarea{
    background:#49BEA9;
  }
  .eni-quick-card--nueva_alerta{
    background:#7FCCB2;
  }
  .eni-quick-card--editar_estado{
    background:#93C5FD;
  }
  .eni-quick-card--prioridad_evaluacion{
    background:#A8D4F3;
  }

  /* Tarjeta ancha "Nueva tarea" */
  .eni-quick-card-wide-nt{
    background:#D9C6FF;
    border-radius:8px;
    padding:15px 15px 20px 15px;
    box-shadow:0 12px 28px rgba(148,163,184,0.45);
    display:flex;
    align-items:center;
    justify-content:space-between;
  }

  /* Reducir espacio entre columnas principales */
  div[data-testid="stHorizontalBlock"]{
    gap:0.4rem !important;
    column-gap:0.4rem !important;
  }

  /* Reducir espacio superior en títulos internos */
  html body [data-testid="stAppViewContainer"] .main .block-container h1,
  html body [data-testid="stAppViewContainer"] .main .block-container h2,
  html body [data-testid="stAppViewContainer"] .main .block-container h3{
    margin-top:0.2rem !important;
  }

  .eni-main-topbar-title{
    text-transform:none !important;
  }
</style>
""",
    unsafe_allow_html=True,
)

# ============ AUTENTICACIÓN POR CONTRASEÑA ============
APP_PASSWORD = "Inei2025$"

def check_app_password() -> bool:
    # Si viene ?logout=1 limpiamos la sesión para forzar login
    logout_flag = ""
    try:
        params0 = st.query_params
        raw_logout = params0.get("logout", "")
        if isinstance(raw_logout, list):
            logout_flag = raw_logout[0] if raw_logout else ""
        else:
            logout_flag = raw_logout
    except Exception:
        try:
            params0 = st.experimental_get_query_params()
            raw_logout = params0.get("logout", [""])
            logout_flag = raw_logout[0] if raw_logout else ""
        except Exception:
            logout_flag = ""

    if logout_flag == "1":
        for k in ("user", "user_email", "password_ok", "acl_user",
                  "auth_ok", "nav_section", "roles_df", "home_tile", "user_display_name"):
            st.session_state.pop(k, None)

    if st.session_state.get("password_ok", False):
        return True

    auth_flag = ""
    user_name_from_qs = ""

    try:
        params = st.query_params
        raw_auth = params.get("auth", "")
        raw_u    = params.get("u", "")
        if isinstance(raw_auth, list):
            auth_flag = raw_auth[0] if raw_auth else ""
        else:
            auth_flag = raw_auth
        if isinstance(raw_u, list):
            user_name_from_qs = raw_u[0] if raw_u else ""
        else:
            user_name_from_qs = raw_u
    except Exception:
        try:
            params = st.experimental_get_query_params()
            raw_auth = params.get("auth", [""])
            raw_u    = params.get("u", [""])
            auth_flag = raw_auth[0] if raw_auth else ""
            user_name_from_qs = raw_u[0] if raw_u else ""
        except Exception:
            auth_flag = ""
            user_name_from_qs = ""

    if user_name_from_qs:
        st.session_state["user_display_name"] = user_name_from_qs

    if auth_flag == "1":
        if not st.session_state.get("password_ok", False):
            st.session_state["password_ok"] = True
            st.session_state["user_email"] = "eni2025@app"
            st.session_state["user"] = {"email": "eni2025@app"}
        return True

    # ---- Pantalla de login ----
    st.markdown(
        """
    <style>
      /* Fondo BLANCO solo para el LOGIN */
      html, body, [data-testid="stAppViewContainer"]{
        background:#FFFFFF !important;
      }

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
        white-space: nowrap;
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
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
    <style>
      html, body, [data-testid="stAppViewContainer"], .main{
        overflow: hidden !important;
      }
    </style>
    """,
        unsafe_allow_html=True,
    )

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

                    name_lower = editor_name.lower()
                    is_vivi_login = any(t in name_lower for t in ("vivian", "vivi", "saurino"))
                    is_enrique_login = any(t in name_lower for t in ("enrique", "kike", "oyola"))
                    st.session_state["is_247_user"] = bool(is_vivi_login or is_enrique_login)

                    try:
                        st.query_params["auth"] = "1"
                        st.query_params["u"] = editor_name
                    except Exception:
                        st.experimental_set_query_params(auth="1", u=editor_name)

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

st.session_state["acl_user"] = user_acl
st.session_state["user_display_name"] = (
    st.session_state.get("user_display_name")
    or user_acl.get("display_name", "Usuario")
)
st.session_state["user_dry_run"] = bool(user_acl.get("dry_run", False))
st.session_state["save_scope"] = user_acl.get("save_scope", "all")

# ========= Hook "maybe_save" + Google Sheets ==========
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
              "auth_ok", "nav_section", "roles_df", "home_tile", "user_display_name"):
        st.session_state.pop(k, None)
    try:
        st.experimental_set_query_params()
    except Exception:
        pass
    st.rerun()

# ====== Navegación / permisos ======
DEFAULT_SECTION = "Gestión de tareas"

TAB_KEY_BY_SECTION = {
    "Gestión de tareas": "tareas_recientes",
    "Kanban": "kanban",
    "Gantt": "gantt",
    "Dashboard": "dashboard",
}

TILE_TO_VIEW_MODULE = {
    "nueva_tarea": "features.nueva_tarea.view",
    "nueva_alerta": "features.nueva_alerta.view",
    "editar_estado": "features.editar_estado.view",
    "prioridad_evaluacion": "features.prioridad.view",
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

    nav_labels = ["Gestión de tareas", "Kanban", "Gantt", "Dashboard"]
    current_section = st.session_state.get("nav_section", DEFAULT_SECTION)
    if current_section not in nav_labels:
        current_section = DEFAULT_SECTION
    default_idx = nav_labels.index(current_section)

    st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False,
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ===== Tarjetas rápidas (HTML con <a>, como antes) =====
def _quick_card_link(title: str, subtitle: str, icon: str, tile_key: str) -> str:
    display_name = st.session_state.get("user_display_name", "Usuario")
    u_param = quote(display_name, safe="")
    card_class = f"eni-quick-card eni-quick-card--{tile_key}"
    return f"""
    <a href="?auth=1&u={u_param}&tile={tile_key}" target="_self" class="eni-quick-card-link">
      <div class="{card_class}">
        <div class="eni-quick-card-text">
          <div class="eni-quick-card-title">{title}</div>
          <p class="eni-quick-card-sub">{subtitle}</p>
        </div>
        <div class="eni-quick-card-icon">{icon}</div>
      </div>
    </a>
    """

# ===== leer parámetro de tarjeta seleccionada (tile) =====
tile_param = ""
try:
    params = st.query_params
    raw = params.get("tile", "")
    if isinstance(raw, list):
        tile_param = raw[0] if raw else ""
    else:
        tile_param = raw
except Exception:
    try:
        params = st.experimental_get_query_params()
        raw = params.get("tile", [""])
        tile_param = raw[0] if raw else ""
    except Exception:
        tile_param = ""

if tile_param:
    st.session_state["home_tile"] = tile_param

tile = st.session_state.get("home_tile", "")

section = st.session_state.get("nav_section", DEFAULT_SECTION)
tab_key = TAB_KEY_BY_SECTION.get(section, "tareas_recientes")

# ============ Contenido principal ============
if section == "Gestión de tareas":
    dn = st.session_state.get("user_display_name", "Usuario")

    # Nombre “limpio” sin emoji final
    parts = dn.split()
    if parts:
        last = parts[-1]
        if not any(ch.isalnum() for ch in last):
            dn_clean = " ".join(parts[:-1]) or dn
        else:
            dn_clean = dn
    else:
        dn_clean = dn

    # Iniciales para el círculo (VS, EO, etc.)
    name_parts_clean = dn_clean.split()
    initials = ""
    for p in name_parts_clean[:2]:
        if p:
            initials += p[0].upper()
    initials = initials or "VS"

    # ---- Topbar siempre igual ----
    st.markdown(
        f"""
        <div class="eni-main-topbar">
          <div class="eni-main-topbar-title">📋 Gestión de tareas</div>
          <div class="eni-main-topbar-user">
            <div class="eni-main-topbar-avatar">{initials}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ===== SI HAY TARJETA SELECCIONADA → SOLO FEATURE (como Kanban/Gantt) =====
    if tile:
        module_path = TILE_TO_VIEW_MODULE.get(tile)
        if module_path:
            try:
                view_module = importlib.import_module(module_path)
                render_fn = getattr(view_module, "render", None)
                if render_fn is None:
                    render_fn = getattr(view_module, "render_all", None)

                if callable(render_fn):
                    st.markdown('<div class="eni-view-wrapper">', unsafe_allow_html=True)
                    view_module_fn_user = st.session_state.get("user")
                    render_fn(view_module_fn_user)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info(
                        "Vista pendiente para esta tarjeta "
                        "(no se encontró función 'render' ni 'render_all')."
                    )
            except Exception as e:
                st.info("No se pudo cargar la vista para esta tarjeta.")
                st.exception(e)
        else:
            st.info("Todavía no hay una vista vinculada a esta tarjeta.")

    # ===== SIN TARJETA → Banner ENCABEZADO + 5 tarjetas debajo =====
    else:
        # --- Banner horizontal ENCABEZADO ---
        if HEADER_IMG_PATH.exists():
            try:
                with open(HEADER_IMG_PATH, "rb") as f:
                    data = f.read()
                b64_header = base64.b64encode(data).decode("utf-8")
                st.markdown(
                    f"""
                    <div class="eni-main-hero">
                      <img src="data:image/png;base64,{b64_header}"
                           alt="ENI 2025 encabezado"
                           class="eni-main-hero-img" />
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            except Exception:
                # Fallback sencillo
                st.image(str(HEADER_IMG_PATH), use_column_width=True)
        else:
            st.caption("Plataforma de gestión ENI — 2025")

        # --- Tarjeta ancha + grid de 4 tarjetas DEBAJO del banner ---
        display_name = st.session_state.get("user_display_name", "Usuario")
        u_param = quote(display_name, safe="")

        # 🔹 1) Tarjeta ancha NUEVA TAREA ARRIBA
        nueva_tarea_html = f"""
        <div class="eni-quick-grid-wrapper">
          <a href="?auth=1&u={u_param}&tile=nueva_tarea"
             target="_self"
             class="eni-quick-card-link">
            <div class="eni-quick-card-wide-nt">
              <div class="eni-quick-card-text">
                <div class="eni-quick-card-title">1. Nueva tarea</div>
                <p class="eni-quick-card-sub">
                  Registra una nueva tarea y revísalas
                </p>
              </div>
              <div class="eni-quick-card-icon">➕</div>
            </div>
          </a>
        </div>
        """
        st.markdown(nueva_tarea_html, unsafe_allow_html=True)

        # 🔹 2) Grid 2×2 con las 4 tarjetas DEBAJO
        cards_html = f"""
        <div class="eni-quick-grid-wrapper">
          <div class="eni-quick-grid">
            {_quick_card_link(
                "2. Editar estado",
                "Actualiza fases y fechas de las tareas",
                "✏️",
                "editar_estado",
            )}
            {_quick_card_link(
                "3. Nueva alerta",
                "Registra alertas y riesgos prioritarios de las tareas",
                "⚠️",
                "nueva_alerta",
            )}
            {_quick_card_link(
                "4. Prioridad",
                "Revisa los niveles de prioridad de las tareas",
                "⭐",
                "prioridad_evaluacion",
            )}
            {_quick_card_link(
                "5. Evaluación",
                "Revisa las evaluaciones y cumplimiento de las tareas",
                "📝",
                "nueva_tarea",
            )}
          </div>
        </div>
        """
        st.markdown(cards_html, unsafe_allow_html=True)

elif section == "Kanban":
    st.title("🗂️ Kanban")
    def _render_kanban():
        try:
            from features.kanban.view import render as render_kanban
            render_kanban(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista Kanban pendiente (features/kanban/view.py).")
            st.exception(e)
    render_if_allowed(tab_key, _render_kanban)

elif section == "Gantt":
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
