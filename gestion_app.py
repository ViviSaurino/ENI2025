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

# from auth_google import google_login, logout  # <-- ELIMINADO

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

LOGO_PATH = Path("assets/branding/eni2025_logo.png")
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

# 👉 Estilos específicos (banner + botón cerrar sesión + logo más a la izquierda)
st.markdown("""
<style>
  .eni-banner{ margin:6px 0 14px; font-weight:400; font-size:16px; color:#4B5563; }
  section[data-testid="stSidebar"] .stButton > button{
    background:#C7A0FF !important; color:#FFFFFF !important; border:none !important;
    border-radius:12px !important; font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  section[data-testid="stSidebar"] .stButton > button:hover{ filter:brightness(0.95); }
  section[data-testid="stSidebar"] .eni-logo-wrap{ margin-left:-28px; margin-top:-6px !important; }
  section[data-testid="stSidebar"] .block-container{ padding-top:6px !important; padding-bottom:10px !important; }
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{ gap:8px !important; }
  section[data-testid="stSidebar"] .avatar-wrap{ margin:6px 0 6px !important; }
  section[data-testid="stSidebar"] .avatar-wrap img{ border-radius:9999px !important; }

  /* Sidebar más delgado, fondo plomo suave */
  [data-testid="stSidebar"]{
    overflow-y:hidden !important;
    background-color:#F5F6FB !important;
    min-width:180px !important;
    max-width:180px !important;
  }

  /* 🔼 Subir un poquito el contenido principal */
  html body [data-testid="stAppViewContainer"] .main .block-container{
    padding-top: 0rem !important;
    margin-top: -1rem !important;
  }

  /* 🔼 Comprimir header para que no deje espacio arriba */
  header[data-testid="stHeader"]{
    height: 0px;
    padding: 0px;
    visibility: hidden;
  }

  /* ===== Menú de secciones estilo pastilla en el sidebar ===== */
  section[data-testid="stSidebar"] .stRadio > div{
    gap:4px !important;
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"]{
    margin-bottom:4px;
    padding:6px 10px;
    border-radius:999px;
    background:transparent;
    transition:all .15s ease-in-out;
  }
  /* ocultar el circulito del radio */
  section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child{
    display:none;
  }
  section[data-testid="stSidebar"] [data-baseweb="radio"] > div:last-child{
    padding-left:0 !important;
  }
  /* opción seleccionada */
  section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="true"]{
    background:#C7A0FF !important;
    color:#FFFFFF !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35);
  }
  /* opciones no seleccionadas */
  section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="false"]{
    color:#4B5563 !important;
  }

  /* Ocultar barras de scroll visualmente pero permitir scroll */
  *::-webkit-scrollbar{
    width:0px;
    height:0px;
  }

  /* ===== Hero principal en la vista Gestión de tareas ===== */
  .eni-main-hero{
    background:#E5D4FF;
    border-radius:24px;
    padding:18px 24px;
    margin-bottom:22px;
    display:flex;
    align-items:center;
    justify-content:space-between;
  }
  .eni-main-hero-left-title{
    font-size:14px;
    font-weight:600;
    color:#4B5563;
  }
  .eni-main-hero-left-name{
    font-size:24px;
    font-weight:800;
    color:#4C1D95;
    margin:2px 0 6px 0;
  }
  .eni-main-hero-left-sub{
    font-size:13px;
    color:#4B5563;
    margin:0;
  }

  /* ===== Tarjetas rápidas (7 rectángulos) ===== */
  .eni-quick-card{
    background:#FFFFFF;
    border-radius:18px;
    padding:16px 18px;
    box-shadow:0 8px 20px rgba(148,163,184,.18);
    border:1px solid #E5E7EB;
    height:100%;
    margin-bottom:18px;  /* separa más las filas de tarjetas */
  }
  .eni-quick-card-title{
    font-size:14px;
    font-weight:700;
    color:#111827;
    margin-bottom:4px;
  }
  .eni-quick-card-sub{
    font-size:12px;
    color:#6B7280;
    margin:0;
  }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN POR CONTRASEÑA ============
APP_PASSWORD = "Inei2025$"

def check_app_password() -> bool:
    """
    Portada tipo hero: BIENVENIDOS + píldora celeste + campo de contraseña.
    Si la contraseña es correcta, marca password_ok y crea un usuario genérico.
    """

    # 🎨 Estilos para título, píldora, botón ENTRAR jade y espaciado de inputs
    st.markdown("""
    <style>
      .eni-hero-title{
        font-size:77px;          /* BIEN / VENIDOS grande */
        font-weight:900;
        color:#B38CFB;
        line-height:0.80;
        margin-bottom:10px;
      }
      .eni-hero-pill{
        display:inline-block;
        padding:10px 53px;
        border-radius:12px;
        background-color:#C0C2FF;   /* lila un poquito más oscuro */
        border:1px solid #C0C2FF;
        color:#FFFFFF;              /* letras blancas */
        font-weight:700;
        font-size:14px;
        letter-spacing:0.04em;
        margin-bottom:10px;
        white-space: nowrap;  /* evita el salto de línea */
      }

      /* 🎨 Botón ENTRAR jade un poquito más oscuro, letras blancas */
      [data-testid="stAppViewContainer"] .main .stButton > button{
        background:#8FD9C1 !important;   /* jade algo más oscuro */
        color:#FFFFFF !important;        /* texto blanco */
        border-radius:12px !important;
        border:1px solid #8FD9C1 !important;
        font-weight:900 !important;      /* negrita fuerte */
        letter-spacing:0.04em !important;/* similar a la píldora */
        text-transform:uppercase !important;
      }
      [data-testid="stAppViewContainer"] .main .stButton > button:hover{
        filter:brightness(0.97);
      }

      /* 🔽 Reducir espacio entre select "¿Quién está editando?" y contraseña */
      .eni-login-form [data-testid="stSelectbox"]{
        margin-bottom:0.0rem !important;
      }
      .eni-login-form [data-testid="stTextInput"]{
        margin-top:-0.45rem !important;
      }
    </style>
    """, unsafe_allow_html=True)

    # ✅ Si ya pasó la contraseña, no mostramos login otra vez
    if st.session_state.get("password_ok", False):
        return True

    # 🔒 Ocultar scroll solo en la pantalla de login
    st.markdown("""
    <style>
      html, body, [data-testid="stAppViewContainer"], .main{
        overflow: hidden !important;
      }
    </style>
    """, unsafe_allow_html=True)

    # Margen superior sólo en la pantalla de login
    st.markdown("<div style='margin-top:7vh;'></div>", unsafe_allow_html=True)

    # Columnas generales con espaciador a la izquierda
    space_col, col1, col2 = st.columns([0.20, 0.55, 0.35])
        
    # Columna izquierda: título + subcolumna
    with space_col:
        st.write("")
    with col1:
        st.markdown("<div class='eni-hero-title'>BIEN<br>VENIDOS</div>", unsafe_allow_html=True)

        form_col, _ = st.columns([0.66, 0.60])  # <-- ancho de píldora e inputs
        with form_col:
            st.markdown("<div class='eni-login-form'>", unsafe_allow_html=True)

            st.markdown("<div class='eni-hero-pill'>GESTIÓN DE TAREAS ENI 2025</div>", unsafe_allow_html=True)
            st.write("")

            # 👉 Lista desplegable: ¿Quién está editando?
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

            # Botón ENTRAR
            if st.button("ENTRAR", use_container_width=True):
                if pwd == APP_PASSWORD:
                    st.session_state["password_ok"] = True
                    # usuario genérico para que el resto del código siga igual
                    st.session_state["user_email"] = "eni2025@app"
                    st.session_state["user"] = {"email": "eni2025@app"}
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta. Vuelve a intentarlo 🙂")

            st.markdown("</div>", unsafe_allow_html=True)

    # Columna derecha: héroe animado (video autoplay sin controles) o logo como respaldo
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

# Si no pasó la contraseña, no seguimos con la app
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

# --- AJUSTE: forzar is_active y can_edit_all_tabs para esta sesión ---
def _to_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("true", "verdadero", "sí", "si", "1", "x", "y")

if user_acl is None:
    user_acl = {}

# Normaliza (por si vienen como VERDADERO/FALSO o Sí/No desde Excel)
for _k in ("is_active", "can_edit_all_tabs"):
    if _k in user_acl:
        user_acl[_k] = _to_bool(user_acl[_k])

# Fuerza flags para esta sesión
user_acl["is_active"] = True
user_acl["can_edit_all_tabs"] = True

# Refleja también en roles_df en memoria (útil para otras vistas)
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
# --- FIN AJUSTE ---

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

# ====== Logout local (reemplaza al de auth_google) ======
def logout():
    for k in ("user", "user_email", "password_ok", "acl_user",
              "auth_ok", "nav_section", "roles_df"):
        st.session_state.pop(k, None)
    st.rerun()

# Mapeo de claves de pestaña para permisos
TAB_KEY_BY_SECTION = {
    "🧰 Gestión de tareas": "tareas_recientes",
    "🗂️ Kanban": "kanban",
    "📅 Gantt": "gantt",
    "📊 Dashboard": "dashboard",
}
def render_if_allowed(tab_key: str, render_fn):
    # 👉 ACL desactivado: todas las personas pueden ver todas las secciones
    render_fn()

# ============ Sidebar ============
with st.sidebar:
    if LOGO_PATH.exists():
        st.markdown("<div class='eni-logo-wrap'>", unsafe_allow_html=True)
        st.image(str(LOGO_PATH), width=120)
        st.markdown("</div>", unsafe_allow_html=True)

    nav_labels = ["📘 Gestión de tareas","🗂️ Kanban","📅 Gantt","📊 Dashboard"]
    default_idx = nav_labels.index(st.session_state.get("nav_section", "📘 Gestión de tareas"))
    nav_choice = st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False
    )

    st.divider()
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# Helper para tarjetas rápidas
def _quick_card(title: str, subtitle: str) -> str:
    return f"""
    <div class="eni-quick-card">
      <div class="eni-quick-card-title">{title}</div>
      <p class="eni-quick-card-sub">{subtitle}</p>
    </div>
    """

# ============ UI principal ============
section = st.session_state.get("nav_section", "📘 Gestión de tareas")
tab_key = TAB_KEY_BY_SECTION.get(section, "tareas_recientes")

if section == "📘 Gestión de tareas":
    # (sin st.title grande para dejar solo la cabecera lila)

    # ---- Cabecera central lila (Bienvenid@ + nombre, sin círculo con inicial) ----
    dn = st.session_state.get("user_display_name", "Usuario")

    st.markdown(f"""
    <div class="eni-main-hero">
      <div class="eni-main-hero-left">
        <div class="eni-main-hero-left-title">Bienvenid@</div>
        <div class="eni-main-hero-left-name">{dn}</div>
        <p class="eni-main-hero-left-sub">
          A la plataforma unificada para gestión - ENI2025
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- 7 rectángulos: 3 + 3 + 1 ----
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        st.markdown(_quick_card("Nueva tarea", "Registrar una nueva tarea asignada."), unsafe_allow_html=True)
    with col_a2:
        st.markdown(_quick_card("Editar estado", "Actualizar fases y fechas de las tareas."), unsafe_allow_html=True)
    with col_a3:
        st.markdown(_quick_card("Nueva alerta", "Registrar alertas y riesgos prioritarios."), unsafe_allow_html=True)

    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        st.markdown(_quick_card("Prioridad", "Revisar y ajustar la prioridad de tareas."), unsafe_allow_html=True)
    with col_b2:
        st.markdown(_quick_card("Evaluación", "Calificar la evaluación de avances."), unsafe_allow_html=True)
    with col_b3:
        st.markdown(_quick_card("Cumplimiento", "Visualizar el nivel de cumplimiento."), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        _quick_card("Tareas recientes", "Resumen de las últimas tareas actualizadas."),
        unsafe_allow_html=True
    )

    # ---- Vista de gestión de tareas existente ----
    st.markdown('<div class="eni-gestion-wrap">', unsafe_allow_html=True)

    def _render_gestion():
        try:
            from features.dashboard.view import render_all
            render_all(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista de Gestión de tareas pendiente.")
            st.exception(e)
    render_if_allowed(tab_key, _render_gestion)

    st.markdown("""
    <style>
      .eni-gestion-wrap .stButton{ display:none !important; }
      .eni-gestion-wrap .hist-actions .stButton,
      .eni-gestion-wrap .hist-search .stButton{ display:inline-flex !important; }
    </style>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

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
