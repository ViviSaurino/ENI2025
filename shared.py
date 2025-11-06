# ============================
# Utilidades compartidas (ENI2025)
# ============================
from __future__ import annotations
import os
from io import BytesIO
from datetime import datetime, date, time
import pandas as pd
import streamlit as st

# -------- Patch Streamlit + st-aggrid ----------
def patch_streamlit_aggrid():
    try:
        import streamlit.components.v1 as _stc
        import types as _types
        if not hasattr(_stc, "components"):
            _stc.components = _types.SimpleNamespace(MarshallComponentException=Exception)
    except Exception:
        pass

# --------- Zona horaria Lima ----------
try:
    import pytz
    LIMA_TZ = pytz.timezone("America/Lima")
except Exception:
    try:
        from zoneinfo import ZoneInfo
        LIMA_TZ = ZoneInfo("America/Lima")
    except Exception:
        LIMA_TZ = None

def now_lima_trimmed():
    now = datetime.now()
    try:
        if LIMA_TZ:
            if hasattr(LIMA_TZ, "localize"):
                now = LIMA_TZ.localize(now)
            else:
                now = now.replace(tzinfo=LIMA_TZ)
    except Exception:
        pass
    return now.replace(second=0, microsecond=0)

def combine_dt(d, t):
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
        return pd.Timestamp(datetime.combine(d, time(0, 0)))

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

# -------- Datos base / persistencia local --------
DATA_DIR = st.session_state.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

COLS = st.session_state.get(
    "COLS",
    ["Id","Área","Responsable","Tarea","Prioridad","Evaluación","Fecha inicio","__DEL__"]
)
TAB_NAME = st.session_state.get("TAB_NAME", "Tareas")
COLS_XLSX = [c for c in COLS if c not in ("__DEL__","DEL")]

def _csv_path() -> str:
    """Ruta legacy (compatibilidad): data/tareas.csv"""
    return os.path.join(DATA_DIR, "tareas.csv")

def _local_store_path() -> str:
    """
    Ruta principal de persistencia usada por features/dashboard/view._save_local:
    data/local/df_main.csv
    """
    base_dir = os.path.join(DATA_DIR, "local")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "df_main.csv")

def _read_csv_safe(path: str, cols: list[str]) -> pd.DataFrame:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame([], columns=cols)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except (pd.errors.EmptyDataError, ValueError):
        return pd.DataFrame([], columns=cols)
    # asegurar columnas mínimas
    for c in cols:
        if c not in df.columns:
            df[c] = None
    # ordenar: primero las conocidas, luego el resto
    df = df[[c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]]
    return df

def read_local() -> pd.DataFrame:
    """
    Loader unificado:
    1) Intenta leer del destino principal (data/local/df_main.csv).
    2) Si no existe, cae a la ruta legacy (data/tareas.csv).
    """
    primary = _local_store_path()
    legacy = _csv_path()
    if os.path.exists(primary) and os.path.getsize(primary) > 0:
        return _read_csv_safe(primary, COLS)
    return _read_csv_safe(legacy, COLS)

def save_local(df: pd.DataFrame):
    """
    Guardado unificado:
    - Escribe SIEMPRE en data/local/df_main.csv (principal).
    - Además duplica en data/tareas.csv (compatibilidad).
    """
    try:
        primary = _local_store_path()
        df.to_csv(primary, index=False, encoding="utf-8-sig")
    except Exception:
        pass
    try:
        legacy = _csv_path()
        df.to_csv(legacy, index=False, encoding="utf-8-sig")
    except Exception:
        pass

def write_sheet_tab(df: pd.DataFrame):
    """Placeholder si luego conectas a Google Sheets."""
    return False, "No conectado a Google Sheets (fallback activo)"

def ensure_df_main():
    """
    Inicializa st.session_state['df_main'] desde almacenamiento local.
    Lee del mismo archivo que escribe _save_local (data/local/df_main.csv),
    con fallback a la ruta legacy.
    """
    if "df_main" in st.session_state:
        return
    base = read_local()
    if "__DEL__" not in base.columns:
        base["__DEL__"] = False
    base["__DEL__"] = base["__DEL__"].fillna(False).astype(bool)
    if "Calificación" in base.columns:
        base["Calificación"] = pd.to_numeric(base["Calificación"], errors="coerce").fillna(0).astype(int)
    keep_cols = [c for c in COLS if c in base.columns] + (["__DEL__"] if "__DEL__" in base.columns else [])
    st.session_state["df_main"] = base[keep_cols].copy()

# --------- Fila en blanco ----------
def blank_row():
    try:
        if "COLS" in globals() and COLS:
            cols = list(COLS)
        elif "df_main" in st.session_state and isinstance(st.session_state["df_main"], pd.DataFrame) and not st.session_state["df_main"].empty:
            cols = list(st.session_state["df_main"].columns)
        else:
            cols = ["Área","Id","Tarea","Tipo","Responsable","Fase","Estado","Fecha inicio","Ciclo de mejora","Detalle"]
        row = {c: None for c in cols}
        if "__DEL__" in row:
            row["__DEL__"] = False
        return row
    except Exception:
        return {"Área":None,"Id":None,"Tarea":None,"Tipo":None,"Responsable":None,"Fase":None,"Estado":None,"Fecha inicio":None,"Ciclo de mejora":None,"Detalle":None}

# --------- Exportar a Excel ----------
def export_excel(df: pd.DataFrame, filename: str = "ENI2025_tareas.xlsx", sheet_name: str = "Tareas", **kwargs) -> BytesIO:
    if "sheet" in kwargs and not sheet_name:
        sheet_name = kwargs.pop("sheet")
    else:
        kwargs.pop("sheet", None)

    buf = BytesIO()
    engine = None
    try:
        import xlsxwriter  # noqa
        engine = "xlsxwriter"
    except Exception:
        try:
            import openpyxl  # noqa
            engine = "openpyxl"
        except Exception:
            raise ImportError("Instala 'xlsxwriter' u 'openpyxl' para exportar a Excel.")

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

# --------- Catálogos y mapas ----------
AREAS_OPC = st.session_state.get(
    "AREAS_OPC",
    ["Jefatura","Gestión","Metodología","Base de datos","Capacitación","Monitoreo","Consistencia"]
)
FASES = ["Capacitación","Post-capacitación","Pre-consistencia","Consistencia","Operación de campo"]
EMO_AREA = {"😃 Jefatura":"Jefatura","✏️ Gestión":"Gestión","💻 Base de datos":"Base de datos","📈  Metodología":"Metodología","🔠 Monitoreo":"Monitoreo","🥇 Capacitación":"Capacitación","💾 Consistencia":"Consistencia"}
EMO_COMPLEJIDAD = {"🔴 Alta":"Alta","🟡 Media":"Media","🟢 Baja":"Baja"}
EMO_PRIORIDAD   = {"🔥 Alta":"Alta","✨ Media":"Media","🍃 Baja":"Baja"}
EMO_ESTADO      = {"🍼 No iniciado":"No iniciado","⏳ En curso":"En curso"}
SI_NO = ["Sí","No"]
CUMPLIMIENTO = ["Entregado a tiempo","Entregado con retraso","No entregado","En riesgo de retraso"]

# --------- IDs por área/persona ----------
import re
def _area_initial(area: str) -> str:
    if not area: return ""
    m = re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", str(area))
    return (m.group(0).upper() if m else "")

def _person_initials(nombre: str) -> str:
    if not nombre: return ""
    parts = [p for p in re.split(r"\s+", str(nombre).strip()) if p]
    if not parts: return ""
    import re as _re
    ini1 = _re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", parts[0])[:1].upper() if parts else ""
    ini2 = ""
    for p in parts[1:]:
        t = _re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", p)
        if t:
            ini2 = t[0].upper()
            break
    return f"{ini1}{ini2}"

def make_id_prefix(area: str, responsable: str) -> str:
    return f"{_area_initial(area)}{_person_initials(responsable)}"

def next_id_by_person(df: pd.DataFrame, area: str, responsable: str) -> str:
    prefix = make_id_prefix(area, responsable)
    if not prefix:
        return ""
    if "Id" not in df.columns or df.empty:
        seq = 1
    else:
        serie = df["Id"].astype(str).fillna("")
        seq = 1 + serie.str.startswith(prefix + "_").sum()
    return f"{prefix}_{seq}"

# --------- CSS global ----------
def inject_global_css():
    st.markdown("""
<style>
:root{
  --lilac:#B38BE3; --lilac-50:#F6EEFF; --lilac-600:#8B5CF6;
  --blue-pill-bg:#38BDF8; --blue-pill-bd:#0EA5E9; --blue-pill-fg:#ffffff;
  --pill-h:36px; --pill-width:158px;
  --pill-azul:#94BEEA; --pill-azul-bord:#94BEEA;
  --pill-rosa:#67D3C4; --pill-rosa-bord:#67D3C4;
}
/* Sidebar */
[data-testid="stSidebar"]{ background:var(--lilac-50) !important; border-right:1px solid #ECE6FF !important; }
[data-testid="stSidebar"] a{ color:var(--lilac-600) !important; font-weight:600 !important; text-decoration:none !important; }
/* Espaciados */
.block-container h1{ margin-bottom:18px !important; }
.topbar, .topbar-ux, .topbar-na, .topbar-pri, .topbar-eval{ margin:12px 0 !important; }
.form-card{ margin-top:10px !important; margin-bottom:28px !important; }
/* Inputs */
.form-card [data-baseweb="input"] > div,
.form-card [data-baseweb="textarea"] > div,
.form-card [data-baseweb="select"] > div,
.form-card [data-baseweb="datepicker"] > div{
  min-height:44px !important; border-radius:12px !important; border:1px solid #E5E7EB !important; background:#fff !important;
}
/* Píldoras celestes */
.form-title,.form-title-ux,.form-title-na{
  display:inline-flex !important; align-items:center !important; gap:.5rem !important;
  padding:6px 12px !important; border-radius:12px !important; background:var(--pill-azul) !important;
  border:1px solid var(--pill-azul-bord) !important; color:#fff !important; font-weight:800 !important;
  margin:6px 0 10px 0 !important; width:var(--pill-width) !important; justify-content:center !important;
  box-shadow:0 6px 16px rgba(148,190,234,.3) !important; min-height:var(--pill-h) !important; height:var(--pill-h) !important;
}
/* SELECT más anchos en primera columna de filas 1 y 2 */
.form-card [data-baseweb="select"] > div{ min-width:240px !important; }
.form-card [data-testid="stHorizontalBlock"]:nth-of-type(1) > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width:300px !important; }
.form-card [data-testid="stHorizontalBlock"]:nth-of-type(2) > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width:300px !important; }
/* Topbar layout */
.topbar, .topbar-ux, .topbar-na{ display:flex !important; align-items:center !important; gap:8px !important; }
.topbar .stButton>button, .topbar-ux .stButton>button, .topbar-na .stButton>button{
  height:var(--pill-h) !important; padding:0 16px !important; border-radius:10px !important; display:inline-flex !important; align-items:center !important;
}
/* PRIORIDAD / EVALUACIÓN */
.topbar-pri, .topbar-eval{ display:flex !important; align-items:center !important; gap:8px !important; }
.form-title-pri, .form-title-eval{
  display:inline-flex !important; align-items:center !important; gap:.5rem !important; padding:6px 12px !important; border-radius:12px !important;
  background:var(--pill-rosa) !important; border:1px solid var(--pill-rosa-bord) !important; color:#fff !important; font-weight:800 !important;
  font-size:14px !important; letter-spacing:.2px !important; white-space:nowrap !important; margin:6px 0 10px 0 !important; width:var(--pill-width) !important;
  justify-content:center !important; box-shadow:0 6px 16px rgba(214,154,194,.30) !important; min-height:var(--pill-h) !important; height:var(--pill-h) !important;
}
</style>
""", unsafe_allow_html=True)
