# shared.py
import os
import pandas as pd
import streamlit as st
from auth_google import google_login, logout

# =========================
# Esquema de columnas (canon)
# =========================

# Núcleo visible (según tus grids y colw/target_cols)
COLS_CORE = [
    "Id","Área","Fase","Responsable",
    "Tarea","Tipo","Detalle","Ciclo de mejora","Complejidad","Prioridad",
    "Estado",
    "Duración",                 # (opcional) si no lo calculas aún quedará vacío
    "Fecha Registro","Hora Registro",
    "Fecha inicio","Hora de inicio",
    "Fecha Vencimiento","Hora Vencimiento",
    "Fecha Terminado","Hora Terminado",
    "¿Generó alerta?",
    "Fecha de detección","Hora de detección",
    "¿Se corrigió?","Fecha de corrección","Hora de corrección",
    "Cumplimiento","Evaluación","Calificación",
    "Fecha Pausado","Hora Pausado",
    "Fecha Cancelado","Hora Cancelado",
    "Fecha Eliminado","Hora Eliminado",
]

# Columnas internas/auxiliares que usa la app para cálculos y limpieza
COLS_INTERNAL = [
    "Estado modificado",
    "Fecha estado modificado","Hora estado modificado",
    "Fecha estado actual","Hora estado actual",
    "N° de alerta","Tipo de alerta",
    "Fecha","Hora",            # fuentes crudas para completar Registro si falta
    "Vencimiento",             # fuente cruda para completar Fecha/Hora Vencimiento
    "¿Eliminar?",              # flag usado en algunas vistas
    "__SEL__","__DEL__",       # selección/tachado en grids
]

# (Opcional) Si mantienes este campo en otras vistas/cálculos, lo conservamos
EXTRAS_COMPAT = [
    "Días hábiles",
]

# Esquema canónico total
COLS_CANON = COLS_CORE + COLS_INTERNAL + EXTRAS_COMPAT

# Orden sugerido para exportar/guardar (sin columnas internas)
COLS_EXPORT = [c for c in COLS_CORE + EXTRAS_COMPAT if c not in {"__SEL__","__DEL__"}]

# =========================
# Normalización de nombres
# =========================
RENAME_LEGACY_TO_NEW = {
    # nombres antiguos -> nombres actuales
    "Fecha fin": "Fecha Terminado",
    "Fecha detectada": "Fecha de detección",
    "Hora detectada":  "Hora de detección",
    "Fecha corregida": "Fecha de corrección",
    "Hora corregida":  "Hora de corrección",
    # por si vinieran variantes sin mayúsculas iniciales
    "fecha fin": "Fecha Terminado",
    "fecha detectada": "Fecha de detección",
    "hora detectada":  "Hora de detección",
    "fecha corregida": "Fecha de corrección",
    "hora corregida":  "Hora de corrección",
}

# =========================
# Autenticación compartida
# =========================
def ensure_login():
    """Fuerza login y devuelve dict user. Guarda en st.session_state['user']."""
    if "user" in st.session_state and st.session_state["user"]:
        return st.session_state["user"]

    allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
    allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

    user = google_login(
        allowed_emails=allowed_emails,
        allowed_domains=allowed_domains,
        redirect_page=None
    )
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

# =========================
# Datos compartidos (df_main)
# =========================
def _blank_df() -> pd.DataFrame:
    """DataFrame vacío con el esquema canónico."""
    return pd.DataFrame(columns=COLS_CANON)

def _apply_renames(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas legadas a las actuales si existen."""
    to_rename = {old: new for old, new in RENAME_LEGACY_TO_NEW.items() if old in df.columns}
    if to_rename:
        df = df.rename(columns=to_rename)
    return df

def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura presencia de todas las columnas del esquema canónico."""
    for c in COLS_CANON:
        if c not in df.columns:
            df[c] = pd.NA
    # Id siempre string
    if "Id" in df.columns:
        df["Id"] = df["Id"].astype(str)
    # Flags booleanos por defecto
    for flag in ["__SEL__","__DEL__","¿Eliminar?","¿Generó alerta?","¿Se corrigió?"]:
        if flag in df.columns:
            # Mantén como bool si ya vino; si no, inicializa False
            if df[flag].isna().all():
                df[flag] = False
    return df

def init_data(csv_path: str = "data/tareas.csv"):
    """Carga/crea df_main compartido en st.session_state['df_main'] con columnas normalizadas."""
    if "df_main" in st.session_state and isinstance(st.session_state["df_main"], pd.DataFrame):
        return

    try:
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=["", "NaN", "nan"])
        else:
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            df = _blank_df()
    except Exception:
        df = _blank_df()

    # Normaliza nombres y asegura columnas
    df = _apply_renames(df)
    df = _ensure_columns(df)

    # Reordena (primero exportables, luego internas, luego cualquier otra extra que hubiera)
    front = [c for c in COLS_EXPORT if c in df.columns]
    intern = [c for c in COLS_INTERNAL if c in df.columns]
    others = [c for c in df.columns if c not in set(front + intern)]
    df = df[front + intern + others].copy()

    st.session_state["df_main"] = df

def save_local(csv_path: str = "data/tareas.csv") -> bool:
    """Guarda df_main a CSV local en un orden estable (sin columnas internas)."""
    try:
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        df = st.session_state.get("df_main", _blank_df()).copy()

        # Aseguramos columnas y reordenamos para exportar
        df = _apply_renames(df)
        df = _ensure_columns(df)

        cols = [c for c in COLS_EXPORT if c in df.columns]
        # Conserva extras no internas (por si agregas campos nuevos visibles)
        extras_visibles = [c for c in df.columns if c not in set(cols + COLS_INTERNAL)]
        out = df[cols + extras_visibles].copy()

        out.to_csv(csv_path, index=False, encoding="utf-8-sig")
        return True
    except Exception:
        return False
