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
    os.makedirs("data", exist_okay=True)

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
        font-size:80px;          /* más grande */
        font-weight:800;
        color:#B38CFB;
        line-height:0.83;
        margin-bottom:12px;
      }
      .eni-hero-pill{
        display:inline-block;
        padding:10px 22px;
        border-radius:999px;
        background-color:#E0ECFF;
        color:#2B3A67;
        font-weight:600;
        font-size:14px;
        letter-spacing:0.04em;
        margin-bottom:24px;
      }
    </style>
    """, unsafe_allow_html=True)

    # Un pequeño margen superior solo en la pantalla de login
    st.markdown("<div style='margin-top:10vh;'></div>", unsafe_allow_html=True)

    col1, col2 = st.columns([1.1, 1])

    # Columna izquierda: BIENVENIDOS + píldora + contraseña
    with col1:
        st.markdown("<div class='eni-hero-title'>BIEN<br>VENIDOS</div>", unsafe_allow_html=True)
        st.markdown("<div class='eni-hero-pill'>GESTIÓN DE TAREAS ENI 2025</div>", unsafe_allow_html=True)
        st.write("")

        # sub-columna más angosta para que los inputs
        # tengan un ancho parecido al de la píldora
        form_col, _ = st.columns([0.55, 0.45])
        with form_col:
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
            # sin borde, sin sombra
