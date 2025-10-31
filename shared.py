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



























# ================== Utilidades de fecha/hora ==================
from datetime import datetime, date, time

# TZ robusta: usa pytz si está, si no zoneinfo
try:
    import pytz
    LIMA_TZ = pytz.timezone("America/Lima")
except Exception:
    try:
        from zoneinfo import ZoneInfo
        LIMA_TZ = ZoneInfo("America/Lima")
    except Exception:
        LIMA_TZ = None  # fallback sin TZ

def now_lima_trimmed():
    """Hora actual en Lima sin segundos/microsegundos."""
    now = datetime.now()
    if LIMA_TZ:
        try:
            # Si es pytz, localize; si es ZoneInfo, replace tzinfo
            if hasattr(LIMA_TZ, "localize"):
                now = LIMA_TZ.localize(now)
            else:
                now = now.replace(tzinfo=LIMA_TZ)
        except Exception:
            pass
    return now.replace(second=0, microsecond=0)

def combine_dt(d, t):
    """
    Une fecha (date|str) y hora (time|str 'HH:mm') en pd.Timestamp.
    Si falta fecha -> NaT. Si falta hora -> 00:00.
    """
    if d in (None, "", pd.NaT):
        return pd.NaT

    if isinstance(d, str):
        d_parsed = pd.to_datetime(d, errors="coerce")
        if pd.isna(d_parsed):
            return pd.NaT
        d = d_parsed.date()
    elif isinstance(d, pd.Timestamp):
        d = d.date()
    elif isinstance(d, date):
        pass
    else:
        return pd.NaT

    if t in (None, "", "HH:mm", pd.NaT):
        try:
            return pd.Timestamp(datetime.combine(d, time(0, 0)))
        except Exception:
            return pd.NaT

    if isinstance(t, str):
        try:
            hh, mm = t.strip().split(":")
            t = time(int(hh), int(mm))
        except Exception:
            return pd.NaT
    elif isinstance(t, pd.Timestamp):
        t = time(t.hour, t.minute, t.second)
    elif isinstance(t, time):
        pass
    else:
        return pd.NaT

    try:
        return pd.Timestamp(datetime.combine(d, t))
    except Exception:
        return pd.NaT

# ===== Hora auto al elegir fecha (usa zona Lima) =====
def _auto_time_on_date():
    if st.session_state.get("fi_d"):
        st.session_state["fi_t"] = now_lima_trimmed().time()

# ================== Utilidad: fila en blanco ==================
def blank_row():
    """
    Devuelve un diccionario 'fila en blanco' que respeta el orden de columnas.
    - Si existe COLS (lista de columnas objetivo), la usa.
    - Si hay df_main en session_state, usa sus columnas actuales.
    - En último caso, usa un conjunto mínimo seguro de columnas.
    """
    try:
        if "COLS" in globals() and COLS:
            cols = list(COLS)
        elif "df_main" in st.session_state and isinstance(st.session_state["df_main"], pd.DataFrame) and not st.session_state["df_main"].empty:
            cols = list(st.session_state["df_main"].columns)
        else:
            cols = [
                "Área", "Id", "Tarea", "Tipo", "Responsable", "Fase", "Estado",
                "Fecha inicio", "Ciclo de mejora", "Detalle"
            ]

        row = {c: None for c in cols}
        if "__DEL__" in row:
            row["__DEL__"] = False
        return row

    except Exception:
        return {
            "Área": None, "Id": None, "Tarea": None, "Tipo": None, "Responsable": None,
            "Fase": None, "Estado": None, "Fecha inicio": None, "Ciclo de mejora": None,
            "Detalle": None
        }

# ======= Utilidades de tablas (Prioridad / Evaluación) =======
# (estos imports duplicados no hacen daño; los mantengo tal cual)
import streamlit as st
from st_aggrid import GridOptionsBuilder
# from auth_google import google_login, logout  # ya gestionado arriba

# ===== Ajuste 1: Constantes y fallbacks (deben estar antes del formulario) =====
AREAS_OPC = st.session_state.get(
    "AREAS_OPC",
    ["Jefatura", "Gestión", "Metodología", "Base de datos", "Capacitación", "Monitoreo", "Consistencia"]
)
ESTADO = ["No iniciado", "En curso"]
CUMPLIMIENTO = ["Entregado a tiempo", "Entregado con retraso", "No entregado", "En riesgo de retraso"]
SI_NO = ["Sí", "No"]

# ===== Ajuste 3: Reglas de anchos (igualar columnas) =====
PILL_W_AREA  = 168  # píldora "Área"
PILL_W_RESP  = 220  # píldora "Responsable"
PILL_W_HASTA = 220  # píldora "Hasta"
PILL_W_TAREA = PILL_W_HASTA

ALIGN_FIXES = {
    "Id":          10,
    "Área":        10,
    "Responsable": 10,
    "Tarea":       10,
    "Prioridad":   10,
    "Evaluación":  10,
    "Desde":       10,
}

COL_W_ID         = PILL_W_AREA
COL_W_AREA       = PILL_W_RESP
COL_W_DESDE      = PILL_W_RESP
COL_W_TAREA      = PILL_W_TAREA
COL_W_PRIORIDAD  = COL_W_TAREA + COL_W_ID
COL_W_EVALUACION = COL_W_TAREA + COL_W_ID

COLUMN_WIDTHS = {
    "Id":          COL_W_ID        + ALIGN_FIXES.get("Id", 0),
    "Área":        COL_W_AREA      + ALIGN_FIXES.get("Área", 0),
    "Responsable": PILL_W_RESP     + ALIGN_FIXES.get("Responsable", 0),
    "Tarea":       COL_W_TAREA     + ALIGN_FIXES.get("Tarea", 0),
    "Prioridad":   COL_W_PRIORIDAD + ALIGN_FIXES.get("Prioridad", 0),
    "Evaluación":  COL_W_EVALUACION+ ALIGN_FIXES.get("Evaluación", 0),
    "Desde":       COL_W_DESDE     + ALIGN_FIXES.get("Desde", 0),
}

# ===== IDs por Área (normalizado a minúsculas) =====
AREA_PREFIX = {
    "jefatura":      "JF",
    "gestión":       "GE",
    "metodología":   "MT",
    "base de datos": "BD",
    "monitoreo":     "MO",
    "capacitación":  "CA",
    "consistencia":  "CO",
}

def next_id_area(df, area: str) -> str:
    import pandas as pd
    area_key = str(area).strip().lower()
    pref = AREA_PREFIX.get(area_key, "OT")
    serie_ids = df.get("Id", pd.Series([], dtype=str)).astype(str)
    nums = (serie_ids.str.extract(rf"^{pref}(\d+)$")[0]).dropna()
    try:
        mx = nums.astype(int).max()
        nxt = int(mx) + 1 if pd.notna(mx) else 1
    except Exception:
        nxt = 1
    return f"{pref}{nxt}"

def _clean_df_for_grid(df):
    if df.index.name is not None:
        df.index.name = None
    return df.reset_index(drop=True).copy()

def _grid_options_prioridad(df):
    gob = GridOptionsBuilder.from_dataframe(df, enableRowGroup=False, enableValue=False, enablePivot=False)
    gob.configure_grid_options(
        suppressMovableColumns=True,
        domLayout="normal",
        ensureDomOrder=True,
        rowHeight=38,
        headerHeight=42
    )
    gob.configure_column("Id",            width=COLUMN_WIDTHS["Id"],          editable=False)
    gob.configure_column("Área",          width=COLUMN_WIDTHS["Área"],        editable=False)
    gob.configure_column("Responsable",   width=COLUMN_WIDTHS["Responsable"], editable=False)
    if "Desde" in df.columns:
        gob.configure_column("Desde",     width=COLUMN_WIDTHS["Desde"],       editable=False)
    gob.configure_column("Tarea",         width=COLUMN_WIDTHS["Tarea"],       editable=False)
    gob.configure_column(
        "Prioridad",
        width=COLUMN_WIDTHS["Prioridad"],
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": ["Urgente", "Alta", "Media", "Baja"]}
    )
    gob.configure_grid_options(suppressColumnVirtualisation=False)
    return gob.build()

def _grid_options_evaluacion(df):
    gob = GridOptionsBuilder.from_dataframe(df, enableRowGroup=False, enableValue=False, enablePivot=False)
    gob.configure_grid_options(
        suppressMovableColumns=True,
        domLayout="normal",
        ensureDomOrder=True,
        rowHeight=38,
        headerHeight=42
    )
    gob.configure_column("Id",           width=COLUMN_WIDTHS["Id"],          editable=False)
    gob.configure_column("Área",         width=COLUMN_WIDTHS["Área"],        editable=False)
    gob.configure_column("Responsable",  width=COLUMN_WIDTHS["Responsable"], editable=False)
    if "Desde" in df.columns:
        gob.configure_column("Desde",    width=COLUMN_WIDTHS["Desde"],       editable=False)
    gob.configure_column("Tarea",        width=COLUMN_WIDTHS["Tarea"],       editable=False)
    gob.configure_column(
        "Evaluación",
        width=COLUMN_WIDTHS["Evaluación"],
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": [5,4,3,2,1]}
    )
    gob.configure_grid_options(suppressColumnVirtualisation=False)
    return gob.build()

# --- allow-list (puedes seguir usándolo desde la página) ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

# ========= Utilitario para exportar a Excel (auto-engine) =========
def export_excel(df, filename: str = "ENI2025_tareas.xlsx", sheet_name: str = "Tareas", **kwargs):
    """
    Devuelve un BytesIO con el .xlsx. Usa xlsxwriter si está instalado;
    si no, cae a openpyxl sin que tengas que cambiar nada en el resto del código.
    Acepta 'sheet' como alias de 'sheet_name'.
    """
    from io import BytesIO
    import pandas as pd

    if "sheet" in kwargs and not sheet_name:
        sheet_name = kwargs.pop("sheet")
    else:
        kwargs.pop("sheet", None)

    buf = BytesIO()

    engine = None
    try:
        import xlsxwriter  # noqa: F401
        engine = "xlsxwriter"
    except Exception:
        try:
            import openpyxl  # noqa: F401
            engine = "openpyxl"
        except Exception:
            raise ImportError("No hay motor para Excel. Instala 'xlsxwriter' o 'openpyxl'.")

    with pd.ExcelWriter(buf, engine=engine) as xw:
        sheet = sheet_name or "Tareas"
        (df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)).to_excel(
            xw, sheet_name=sheet, index=False
        )
        try:
            if engine == "xlsxwriter":
                ws = xw.sheets[sheet]
                for i, col in enumerate(df.columns):
                    try:
                        maxlen = int(pd.Series(df[col]).astype(str).map(len).max())
                        maxlen = max(10, min(60, maxlen + 2))
                    except Exception:
                        maxlen = 12
                    ws.set_column(i, i, maxlen)
        except Exception:
            pass

    buf.seek(0)
    return buf
