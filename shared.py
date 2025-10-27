# shared.py
import os, pandas as pd, streamlit as st
from auth_google import google_login, logout

# Columnas mínimas esperadas (ajústalas si tu app usa más)
COLS_MIN = [
    "Id","Área","Responsable","Tarea","Tipo","Fase","Complejidad","Prioridad",
    "Estado","Fecha inicio","Vencimiento","Fecha fin","Duración","Días hábiles",
    "¿Generó alerta?","Tipo de alerta","¿Se corrigió?","Fecha detectada","Fecha corregida",
    "Evaluación","Calificación","Ciclo de mejora","Cumplimiento"
]

def ensure_login():
    """Fuerza login y devuelve dict user. Guarda en st.session_state['user']."""
    if "user" in st.session_state and st.session_state["user"]:
        return st.session_state["user"]

    allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
    allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

    user = google_login(allowed_emails=allowed_emails, allowed_domains=allowed_domains, redirect_page=None)
    if not user:
        st.stop()
    st.session_state["user"] = user
    return user

def sidebar_userbox(user):
    with st.sidebar:
        st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
            st.rerun()

def _blank_df():
    df = pd.DataFrame(columns=COLS_MIN)
    return df

def init_data(csv_path="data/tareas.csv"):
    """Carga/crea df_main compartido."""
    if "df_main" in st.session_state and isinstance(st.session_state["df_main"], pd.DataFrame):
        return

    try:
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, dtype=str)
        else:
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            df = _blank_df()
    except Exception:
        df = _blank_df()

    # Normaliza columnas mínimas
    for c in COLS_MIN:
        if c not in df.columns:
            df[c] = None
    # Id como str
    if "Id" in df.columns:
        df["Id"] = df["Id"].astype(str)

    st.session_state["df_main"] = df[COLS_MIN].copy()

def save_local(csv_path="data/tareas.csv"):
    """Guarda df_main a CSV local (silencioso)."""
    try:
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        st.session_state["df_main"][COLS_MIN].to_csv(csv_path, index=False, encoding="utf-8-sig")
        return True
    except Exception:
        return False
