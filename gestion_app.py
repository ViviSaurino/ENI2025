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

    base_cols = ["Id", "Área", "Responsable", "Tarea", "Prioridad",
                 "Evaluación", "Fecha inicio", "__DEL__"]
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
  /* =========================================================
     NUEVO LOOK (como tu imagen):
     - Fondo celeste (con franja superior más clara)
     - Sidebar azul oscuro/negro + texto BLANCO
     ========================================================= */

  /* ===== Fondo general de la APP (celeste) ===== */
  html, body, [data-testid="stAppViewContainer"]{
    background:#edf2fa;;   /* celeste base (más oscuro) */
  }

  /* Franja superior (celeste más claro) */
  [data-testid="stAppViewContainer"]{
    position:relative;
  }
  [data-testid="stAppViewContainer"]::before{
    content:"";
    position:fixed;
    top:0; left:0; right:0;
    height:120px;                 /* “arriba un celeste más claro” */
    background:#D9ECFF;           /* celeste claro */
    z-index:0;
  }
  /* Asegura que el contenido quede encima de la franja */
  html body [data-testid="stAppViewContainer"] .main{
    position:relative;
    z-index:1;
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
    margin:32px 0 47px 0;   /* top  right  bottom  left  (más espacio con el banner) */
    box-shadow:none;  /* sin sombra */
  }
  .eni-main-topbar-title{
    font-size:15px;
    font-weight:700;
    color:#374151;
    letter-spacing:0.08em;
    text-transform:none;
  }

  /* ✅ Link clickeable para volver a Home (sin tile) */
  .eni-home-link,
  .eni-home-link:link,
  .eni-home-link:visited,
  .eni-home-link:hover,
  .eni-home-link:active{
    text-decoration:none !important;
    color:#374151 !important;
    cursor:pointer;
  }

  .eni-main-topbar-user{
    display:flex;
    align-items:center;
    gap:8px;
    font-size:13px;
    color:#4B5563;
    position:relative;
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
    cursor:pointer;
  }
  /* Link Cerrar sesión que aparece al pasar/clickear sobre el avatar */
  .eni-main-topbar-logout{
    display:none;
    margin-left:8px;
    padding:6px 12px;
    border-radius:999px;
    border:1px solid #E5E7EB;
    background:#F9FAFB;
    font-size:12px;
    color:#6B7280;
    text-decoration:none;
    white-space:nowrap;
  }
  .eni-main-topbar-user:hover .eni-main-topbar-logout,
  .eni-main-topbar-user:focus-within .eni-main-topbar-logout{
    display:inline-flex;
  }

  /* ===== Banner horizontal ENCABEZADO debajo del topbar ===== */
  .eni-main-hero{
    margin:0 0px 30px 0px;   /* mismo ancho que el topbar */
    border-radius:10px;
    box-shadow:none;  /* sin sombra en el encabezado lila/azul */
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
  .eni-main-hero-text{
    position:absolute;
    left:32px;
    top:40px;
    color:#FFFFFF;
  }
  .eni-main-hero-welcome{
    font-size:18px;
    font-weight:500;
    opacity:0.95;
  }
  .eni-main-hero-name{
    font-size:26px;
    font-weight:800;
    margin-top:2px;
  }

  /* ===== Panel blanco (no se usa aquí pero lo dejamos) ===== */
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

  /* ===== Sidebar minimalista ===== */
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
    padding-bottom:10px !important;
  }
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{
    gap:8px !important;
  }

  /* ===== Sidebar fondo oscuro + texto blanco ===== */
  [data-testid="stSidebar"]{
    overflow-y:hidden !important;
    background:#2a2a53 !important;   /* azul oscuro/negro */
    width:230px;
    color:#FFFFFF !important;
    border-right:1px solid rgba(255,255,255,0.10);
  }

  /* Cuando está visible: fijamos ancho 230px */
  [data-testid="stSidebar"][aria-expanded="true"]{
    min-width:230px !important;
    max-width:230px !important;
  }

  /* Cuando está oculta: ancho 0 para que el contenido se expanda */
  [data-testid="stSidebar"][aria-expanded="false"]{
    min-width:0 !important;
    max-width:0 !important;
    border-right:none !important;
  }

  /* Menú de secciones */
  section[data-testid="stSidebar"] .stRadio > div{
    gap:4px !important;
  }

  section[data-testid="stSidebar"] [data-baseweb="radio"]{
    margin-bottom:10px;
    padding:10px 14px;
    border-radius:10px;
    background:transparent;
    transition:all .15s ease-in-out;
    display:flex;
    flex-direction:row;
    align-items:center;
    gap:8px;
    width:100%;
    box-sizing:border-box;
    cursor:pointer;
    color:#FFFFFF !important;  /* ✅ para que se vea el texto */
  }

  section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child{
    display:none !important;   /* oculta el botón redondo */
  }

  section[data-testid="stSidebar"] [data-baseweb="radio"] > div:last-child{
    padding-left:0 !important;
    font-size:11px !important;
    line-height:1.1 !important;
    font-weight:600;
    white-space:nowrap;
    color:inherit !important; /* ✅ hereda blanco */
  }

  /* Hover: pastilla azul más clara */
  section[data-testid="stSidebar"] [data-baseweb="radio"]:hover{
    background:rgba(255,255,255,0.10) !important;
    color:#FFFFFF !important;
  }

  /* Opción ACTIVA */
  section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="true"]{
    background:rgba(255,255,255,0.14) !important;
    color:#FFFFFF !important;
    border-radius:10px !important;
    box-shadow:none !important;
    font-weight:700 !important;
  }

  /* Opción INACTIVA */
  section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="false"]{
    background:transparent !important;
    color:rgba(255,255,255,0.85) !important; /* blanco suave pero visible */
    border-radius:10px !important;
    box-shadow:none !important;
  }

  /* Iconitos del menú lateral (emoji) */
  section[data-testid="stSidebar"] [data-baseweb="radio"]::before{
    font-size:18px;
    margin-right:10px;
    opacity:0.95;
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(1)::before{ content:"📋"; }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(2)::before{ content:"🗂️"; }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(3)::before{ content:"📅"; }
  section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(4)::before{ content:"📊"; }

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

  /* ===== Grid de tarjetas rápidas ===== */
  .eni-quick-grid-wrapper{
    margin:0px 0 18px 0;
  }

  .eni-quick-grid{
    display:grid;
    grid-template-columns:repeat(5, minmax(0, 1fr));
    gap:18px;
    align-items:stretch;
    margin-top:20px;
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
    border-radius:12px;
    padding:18px 18px 16px 18px;
    box-shadow:0 10px 22px rgba(148,163,184,0.30);
    border:1px solid #E5E7EB;
    background:#FFFFFF;
    display:flex;
    flex-direction:row;
    justify-content:space-between;
    align-items:center;
    transition:all .15s ease-in-out;

    /* 👇 MISMA ALTURA PARA TODAS LAS TARJETAS */
    min-height: 120px;
    height: 120px;

    /* ✅ FIX: recorta lo que sobresale (iconos) */
    overflow:hidden;
  }

  .eni-quick-card-text{
    max-width:100%;
    text-align:left;
    min-width:0;
  }
  .eni-quick-card-title{
    font-size:14px;
    font-weight:700;
    color:#111827;
    margin-bottom:4px;
    text-align:left;
    white-space:nowrap;
  }
  .eni-quick-card-sub{
    font-size:11px;
    color:#6B7280;
    margin:0;
    text-align:left;
    display:-webkit-box;
    -webkit-line-clamp:3;
    -webkit-box-orient:vertical;
    overflow:hidden;
  }
  .eni-quick-card-icon{
    margin-left:12px;
    flex:0 0 auto;
    display:flex;
    align-items:center;
    justify-content:center;
    line-height:1;
    font-size: clamp(22px, 2.4vw, 46px);
  }
  .eni-quick-card-link:hover .eni-quick-card{
    box-shadow:0 14px 28px rgba(148,163,184,0.45);
    transform:translateY(-2px);
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

  /* Botones: ancho completo + wrap del texto (no se sale) */
  div[data-testid="stButton"] > button{
    width: 100%;
    white-space: normal !important;
    word-break: break-word;
    line-height: 1.15;
  }

  /* Labels de inputs: que puedan partir línea */
  label, .stSelectbox label, .stTextInput label, .stDateInput label{
    white-space: normal !important;
  }

  /* ✅ Ajuste fino para laptop sin cambiar a 2 filas */
  @media (max-width: 1400px){
    .eni-quick-card{ padding:14px 12px 12px 12px; }
    .eni-quick-card-icon{ font-size: clamp(20px, 2.2vw, 40px); margin-left:10px; }
    .eni-quick-card-title{ white-space: normal; }
  }

  /* ✅ Banner/hero: que no se rompa en pantallas chicas */
  @media (max-width: 900px){
    .eni-main-hero{ height:160px; }
    .eni-main-hero-text{ left:18px; top:26px; }
    .eni-main-hero-name{ font-size:22px; }
    .eni-main-hero-img{ right:10px; height:170px; }
    [data-testid="stSidebar"][aria-expanded="true"]{
      min-width:200px !important;
      max-width:200px !important;
    }
  }

  @media (max-width: 650px){
    .eni-main-hero{ height:auto; padding-bottom:16px; }
    .eni-main-hero-img{ display:none; }
    .eni-main-hero-text{ position:relative; left:0; top:0; padding:18px; }
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

# ====== Logout local (se usa desde el enlace del avatar) ======
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

def _on_sidebar_nav_change():
    # ✅ Al cambiar sección, volvemos a la "home" de Gestión (banner + tarjetas)
    st.session_state["home_tile"] = ""

    # ✅ CLAVE: reescribir la URL SIN tile (igual que el botón "Volver")
    display_name = st.session_state.get("user_display_name", "Usuario")
    try:
        # Streamlit nuevo
        st.query_params["auth"] = "1"
        st.query_params["u"] = display_name
        # si existía, lo borramos explícitamente
        if "tile" in st.query_params:
            st.query_params.pop("tile", None)
    except Exception:
        try:
            # Streamlit antiguo
            st.experimental_set_query_params(auth="1", u=display_name)
        except Exception:
            pass

    st.rerun()

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
        on_change=_on_sidebar_nav_change,  # ✅ AQUÍ
    )

    # (Botón Cerrar sesión se quitó; ahora está en el círculo VS del topbar)

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

# 👇 El "estado" de qué vista mostrar SIEMPRE viene de la URL
st.session_state["home_tile"] = tile_param or ""
tile = st.session_state["home_tile"]

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

    u_param = quote(st.session_state.get("user_display_name", "Usuario"), safe="")

    # ---- Topbar con avatar + logout ----
    if tile:
        # ✅ Dentro de una tarjeta: SÍ es clickeable (volver a home)
        st.markdown(
            f"""
            <div class="eni-main-topbar">
              <div class="eni-main-topbar-title">
                <a class="eni-home-link" href="?auth=1&u={u_param}" target="_self">🏠 Volver</a>
              </div>
              <div class="eni-main-topbar-user">
                <div class="eni-main-topbar-avatar">{initials}</div>
                <a href="?logout=1" class="eni-main-topbar-logout">Cerrar sesión</a>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # ✅ Home: NO es clickeable (solo texto)
        st.markdown(
            f"""
            <div class="eni-main-topbar">
              <div class="eni-main-topbar-title">📋 Gestión de tareas</div>
              <div class="eni-main-topbar-user">
                <div class="eni-main-topbar-avatar">{initials}</div>
                <a href="?logout=1" class="eni-main-topbar-logout">Cerrar sesión</a>
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

    # ===== SIN TARJETA → Banner ENCABEZADO + tarjetas debajo =====
    else:
        # --- Texto de bienvenida según nombre ---
        first_name = dn_clean.split()[0] if dn_clean else "Usuario"
        first_name_l = first_name.lower()

        # nombres que son de mujer aunque no terminen en "a"
        female_names = {"elizabet", "lucy", "tiffany", "vivian"}

        if first_name_l.endswith("a") or first_name_l in female_names:
            welcome_word = "Bienvenida"
        else:
            welcome_word = "Bienvenido"

        welcome_line1 = welcome_word
        welcome_line2 = dn_clean

        # --- Banner horizontal ENCABEZADO ---
        if HEADER_IMG_PATH.exists():
            try:
                with open(HEADER_IMG_PATH, "rb") as f:
                    data = f.read()
                b64_header = base64.b64encode(data).decode("utf-8")
                st.markdown(
                    f"""
                    <div class="eni-main-hero">
                      <div class="eni-main-hero-text">
                        <div class="eni-main-hero-welcome">{welcome_line1}</div>
                        <div class="eni-main-hero-name">{welcome_line2}</div>
                      </div>
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

        # --- Tarjetas 5 en fila ---
        display_name = st.session_state.get("user_display_name", "Usuario")
        u_param = quote(display_name, safe="")

        cards_html = f"""
        <div class="eni-quick-grid-wrapper">
          <div class="eni-quick-grid">
            {_quick_card_link(
                "1. Nueva tarea",
                "Registra una nueva tarea y revísala",
                "➕",
                "nueva_tarea",
            )}
            {_quick_card_link(
                "2. Editar estado",
                "Actualiza fases y fechas",
                "✏️",
                "editar_estado",
            )}
            {_quick_card_link(
                "3. Nueva alerta",
                "Registra alertas y riesgos prioritarios",
                "⚠️",
                "nueva_alerta",
            )}
            {_quick_card_link(
                "4. Prioridad",
                "Revisa los niveles de prioridad",
                "⭐",
                "prioridad_evaluacion",
            )}
            {_quick_card_link(
                "5. Evaluación",
                "Revisa las evaluaciones y cumplimiento",
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
