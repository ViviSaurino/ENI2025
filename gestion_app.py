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

from auth_google import google_login, logout

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
  section[data-testid="stSidebar"]{ overflow-y:hidden !important; }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN POR CONTRASEÑA ============
APP_PASSWORD = "Inei2025$"

def check_app_password() -> bool:
    """
    Portada tipo hero: BIENVENIDOS + píldora celeste + campo de contraseña.
    Si la contraseña es correcta, marca password_ok y crea un usuario genérico.
    """
    if st.session_state.get("password_ok", False):
        return True

    # Estilos para el título y la píldora
    st.markdown("""
    <style>
      .eni-hero-title{
        font-size:96px;          /* BIEN / VENIDOS grande */
        font-weight:800;
        color:#B38CFB;
        line-height:0.80;
        margin-bottom:10px;
      }
      .eni-hero-pill{
        display:inline-block;
        padding:10px 110px;
        border-radius:999px;
        background-color:#E0ECFF;
        color:#2B3A67;
        font-weight:600;
        font-size:14px;
        letter-spacing:0.04em;
        margin-bottom:18px;
      }
    </style>
    """, unsafe_allow_html=True)

    # Margen superior sólo en la pantalla de login
    st.markdown("<div style='margin-top:8vh;'></div>", unsafe_allow_html=True)

    # Columnas generales
    col1, col2 = st.columns([1.0, 1.0])

    # Columna izquierda: título + subcolumna más angosta para que
    # la píldora y los inputs tengan un ancho parecido a "VENIDOS"
    with col1:
        st.markdown("<div class='eni-hero-title'>BIEN<br>VENIDOS</div>", unsafe_allow_html=True)

        form_col, _ = st.columns([0.100, 0.100])  # <-- controla el ancho de la píldora e inputs
        with form_col:
            st.markdown("<div class='eni-hero-pill'>GESTIÓN DE TAREAS ENI 2025</div>", unsafe_allow_html=True)
            st.write("")

            pwd = st.text_input("Ingresa la contraseña", type="password", key="eni_pwd")
            if st.button("Ingresar", use_container_width=True):
                if pwd == APP_PASSWORD:
                    st.session_state["password_ok"] = True
                    # usuario genérico para que el resto del código siga igual
                    st.session_state["user_email"] = "eni2025@app"
                    st.session_state["user"] = {"email": "eni2025@app"}
                    st.experimental_rerun()
                else:
                    st.error("Contraseña incorrecta. Vuelve a intentarlo 🙂")

    # Columna derecha: héroe animado (video autoplay sin controles) o logo como respaldo
    with col2:
        hero_video = Path("assets/hero.mp4")
        logo_img   = Path("assets/branding/eni2025_logo.png")

        if hero_video.exists():
            with open(hero_video, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode("utf-8")
            # Pegadito al bloque de texto
            video_html = f"""
            <div style="margin-left:-140px; margin-top:-5px;">
              <video autoplay loop muted playsinline
                     style="width:100%;max-width:520px;
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
# Ya no usamos google_login; tomamos el email desde session_state o ponemos uno por defecto
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
    nav_labels = ["📘 Gestión de tareas","🗂️ Kanban","📅 Gantt","📊 Dashboard"]
    default_idx = nav_labels.index(st.session_state.get("nav_section", "📘 Gestión de tareas"))
    nav_choice = st.radio("Navegación", nav_labels, index=default_idx, label_visibility="collapsed", key="nav_section", horizontal=False)

    st.divider()
    dn = st.session_state.get("user_display_name", email or "Usuario")
    show_user_avatar_from_session(size=150)
    st.markdown(f"👋 **Hola, {dn}**")
    st.caption(f"**Usuario:** {email or '—'}")
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        # limpiamos la contraseña y usuario genérico; se puede mantener logout() por compatibilidad
        st.session_state["password_ok"] = False
        st.session_state.pop("user", None)
        st.session_state.pop("user_email", None)
        logout()
        st.experimental_rerun()

# ============ Datos ============
ensure_df_main()

# ============ UI principal ============
section = st.session_state.get("nav_section", "📘 Gestión de tareas")
tab_key = TAB_KEY_BY_SECTION.get(section, "tareas_recientes")

if section == "📘 Gestión de tareas":
    st.title("📘 Gestión de tareas")
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
