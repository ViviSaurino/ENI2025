# -*- coding: utf-8 -*-
# ============================
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd
from pathlib import Path
import importlib
import base64
from urllib.parse import quote

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
        df["Calificación"] = (
            pd.to_numeric(df["Calificación"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

    st.session_state["df_main"] = df


try:
    _shared = importlib.import_module("shared")
    patch_streamlit_aggrid = getattr(_shared, "patch_streamlit_aggrid")
    inject_global_css = getattr(_shared, "inject_global_css")
    ensure_df_main = getattr(_shared, "ensure_df_main")
except Exception:
    patch_streamlit_aggrid = lambda: None
    inject_global_css = lambda: None
    ensure_df_main = _fallback_ensure_df_main

# 🔐 ACL / Roles
from features.security import acl
from utils.avatar import show_user_avatar_from_session  # por si luego lo usas

LOGO_PATH = Path("assets/branding/eni2025_logo.png")
ROLES_XLSX = "data/security/roles.xlsx"

# ============ Config de página ============
st.set_page_config(
    page_title="Gestión — ENI2025",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============ Parches/estilos globales ============
patch_streamlit_aggrid()
inject_global_css()

st.markdown(
    """
<style>
html, body{
  margin:0;
  padding:0;
}
html, body, [data-testid="stAppViewContainer"]{
  /* Fondo lila igual que cabecera */
  background-color:#C4A5FF;
}

/* quitar espacio arriba */
[data-testid="stAppViewContainer"] > .main{
  padding-top:0 !important;
  margin-top:0 !important;
}

/* contenedor central */
html body [data-testid="stAppViewContainer"] .main .block-container{
  padding-top:0rem !important;
  padding-left:0rem !important;
  padding-right:0rem !important;
  margin-top:0rem !important;
  background:transparent;
}

/* TOPBAR blanca */
.eni-main-topbar{
  background:#FFFFFF;
  padding:10px 24px;
  border-radius:0;
  display:flex;
  align-items:center;
  justify-content:space-between;
  margin:0 24px 12px 24px;
  box-shadow:0 12px 26px rgba(15,23,42,0.10);
}
/* Ocultamos el texto "Dashboard" */
.eni-main-topbar-title{
  display:none;
}
.eni-main-topbar-user{
  display:flex;
  align-items:center;
  gap:10px;
  font-size:13px;
  color:#4B5563;
}
.eni-main-topbar-avatar{
  width:32px;
  height:32px;
  border-radius:999px;
  background:linear-gradient(135deg,#A855F7,#EC4899);
  display:flex;
  align-items:center;
  justify-content:center;
  color:#FFFFFF;
  font-weight:700;
  font-size:14px;
}

/* Sidebar */
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
[data-testid="stSidebar"]{
  overflow-y:hidden !important;
  background:#FFFFFF !important;
  min-width:230px !important;
  max-width:230px !important;
  color:#111827 !important;
  border-right:1px solid #E5E7EB;
}
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
  display:none;
}
section[data-testid="stSidebar"] [data-baseweb="radio"] > div:last-child{
  padding-left:6px !important;
  font-size:13px;
  font-weight:500;
}
section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="true"]{
  background:#EEF2FF !important;
  color:#4F46E5 !important;
  box-shadow:none;
}
section[data-testid="stSidebar"] [data-baseweb="radio"][aria-checked="false"]{
  color:#4B5563 !important;
}

/* iconitos menú */
section[data-testid="stSidebar"] [data-baseweb="radio"]::before{
  font-size:18px;
  margin-right:8px;
}
section[data-testid="stSidebar"] [data-baseweb="radio"]:nth-child(1)::before{
  content:"📋";
}
section[data-testid="stSidebar"] [data-base
