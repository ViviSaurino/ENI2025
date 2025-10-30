# ============================
# Gestión — ENI2025 (MÓDULO: una tabla con "Área" y formulario + historial)
# ============================
import os
from io import BytesIO
import numpy as np
import pandas as pd
import streamlit as st

# ❌ [QUITADO] set_page_config — ahora va en pages/01_Gestion.py

# 🔐 Puedes seguir importando utilidades de auth si las usas en funciones
from auth_google import google_login, logout

# Parche compatibilidad Streamlit 1.50 + st-aggrid
import streamlit.components.v1 as _stc
import types as _types
if not hasattr(_stc, "components"):
    _stc.components = _types.SimpleNamespace(MarshallComponentException=Exception)

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, DataReturnMode

# ================== Constantes de layout / UI ==================
SECTION_GAP = 30  # píxeles de separación vertical entre secciones

# ================== Utilidades de fecha/hora ==================
from datetime import datetime, date, time
import pytz

LIMA_TZ = pytz.timezone("America/Lima")

def now_lima_trimmed():
    """Hora actual en Lima sin segundos/microsegundos."""
    return datetime.now(LIMA_TZ).replace(second=0, microsecond=0)

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
        # Prioriza el esquema objetivo si está definido
        if "COLS" in globals() and COLS:
            cols = list(COLS)
        # Si ya hay una base cargada, respeta esas columnas
        elif "df_main" in st.session_state and not st.session_state["df_main"].empty:
            cols = list(st.session_state["df_main"].columns)
        else:
            # Fallback mínimo seguro
            cols = [
                "Área", "Id", "Tarea", "Tipo", "Responsable", "Fase", "Estado",
                "Fecha inicio", "Ciclo de mejora", "Detalle"
            ]

        row = {c: None for c in cols}

        # Defaults útiles
        if "__DEL__" in row:
            row["__DEL__"] = False

        return row

    except Exception:
        # Último recurso si algo falla al determinar columnas
        return {
            "Área": None, "Id": None, "Tarea": None, "Tipo": None, "Responsable": None,
            "Fase": None, "Estado": None, "Fecha inicio": None, "Ciclo de mejora": None,
            "Detalle": None
        }


# ======= Utilidades de tablas (Prioridad / Evaluación) ======= 
# (estos imports duplicados no hacen daño; los mantengo tal cual)
import streamlit as st
from st_aggrid import GridOptionsBuilder
from auth_google import google_login, logout

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

# ===== IDs por Área (PL, BD, CO, ME) =====
AREA_PREFIX = {
    "Jefatura":  "JF",
    "Gestión":  "GE",
    "Metodología":  "MT",
    "Base de datos":  "BD",
    "Monitoreo":  "MO",
    "Capacitación":  "CA",
    "Consistencia":  "CO",
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

    # Alias de compatibilidad por si alguien pasa sheet=
    if "sheet" in kwargs and not sheet_name:
        sheet_name = kwargs.pop("sheet")
    else:
        kwargs.pop("sheet", None)

    buf = BytesIO()

    # Elegir motor disponible: xlsxwriter -> openpyxl
    engine = None
    try:
        import xlsxwriter  # noqa: F401
        engine = "xlsxwriter"
    except Exception:
        try:
            import openpyxl  # noqa: F401
            engine = "openpyxl"
        except Exception:
            raise ImportError(
                "No hay motor para Excel. Instala 'xlsxwriter' o 'openpyxl' en tu entorno."
            )

    with pd.ExcelWriter(buf, engine=engine) as xw:
        sheet = sheet_name or "Tareas"
        (df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)).to_excel(
            xw, sheet_name=sheet, index=False
        )
        # Auto-anchos (solo si el motor lo permite)
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

# ========= Fallbacks seguros para evitar NameError / EmptyDataError =========
import os as _os
import pandas as _pd

if "DATA_DIR" not in globals():
    DATA_DIR = st.session_state.get("DATA_DIR", "data")

if "COLS" not in globals():
    COLS = st.session_state.get(
        "COLS",
        ["Id","Área","Responsable","Tarea","Prioridad","Evaluación","Fecha inicio","__DEL__"]
    )

# 👇 Columnas a exportar a Excel (excluye columnas de control)
COLS_XLSX = [c for c in COLS if c not in ("__DEL__", "DEL")]

# 👇 Nombre de hoja por defecto para exportaciones (Excel/Sheets)
if "TAB_NAME" not in globals():
    TAB_NAME = st.session_state.get("TAB_NAME", "Tareas")

_os.makedirs(DATA_DIR, exist_ok=True)

if "_read_sheet_tab" not in globals():
    def _read_sheet_tab():
        """Fallback robusto: si el CSV no existe, está vacío o corrupto,
        devuelve un DataFrame vacío con columnas COLS."""
        csv_path = _os.path.join(DATA_DIR, "tareas.csv")
        if not _os.path.exists(csv_path) or _os.path.getsize(csv_path) == 0:
            return _pd.DataFrame([], columns=COLS)
        try:
            df = _pd.read_csv(csv_path, encoding="utf-8-sig")
        except (_pd.errors.EmptyDataError, ValueError):
            return _pd.DataFrame([], columns=COLS)
        # Garantiza columnas esperadas
        for c in COLS:
            if c not in df.columns:
                df[c] = None
        # Ordena según COLS, dejando extras al final
        df = df[[c for c in COLS if c in df.columns] + [c for c in df.columns if c not in COLS]]
        return df

if "_save_local" not in globals():
    def _save_local(df):
        csv_path = _os.path.join(DATA_DIR, "tareas.csv")
        try:
            (df if isinstance(df, _pd.DataFrame) else _pd.DataFrame(df)).to_csv(
                csv_path, index=False, encoding="utf-8-sig"
            )
        except Exception:
            pass

if "_write_sheet_tab" not in globals():
    def _write_sheet_tab(df):
        return False, "No conectado a Google Sheets (fallback activo)"

# 👇 Fallback para exportar Excel (firma correcta con sheet_name)
if "export_excel" not in globals():
    def export_excel(df, filename: str = "ENI2025_tareas.xlsx", sheet_name: str = "Tareas"):
        from io import BytesIO
        import pandas as pd
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
            # Copia y elimina columnas de control si existieran
            df_to_write = (df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)).copy()
            for _c in ("__DEL__", "DEL"):
                if _c in df_to_write.columns:
                    df_to_write.drop(columns=[_c], inplace=True)
            df_to_write.to_excel(xw, sheet_name=sheet_name, index=False)
            # Autoajuste simple de anchos
            ws = xw.sheets[sheet_name]
            try:
                for i, col in enumerate(df_to_write.columns):
                    try:
                        maxlen = int(pd.Series(df_to_write[col]).astype(str).map(len).max())
                        maxlen = max(10, min(60, maxlen + 2))
                    except Exception:
                        maxlen = 12
                    ws.set_column(i, i, maxlen)
            except Exception:
                pass
        buf.seek(0)
        return buf


# ====== ⬇️⬇️ NUEVO: CSS de espaciado entre título, píldoras y secciones ⬇️⬇️ ======
st.markdown("""
<style>
/* Espacio debajo del H1 principal */
.block-container h1 {
  margin-bottom: 25px !important;
}

/* Barras superiores con las píldoras (nueva tarea / editar estado / nueva alerta) */
.topbar, .topbar-ux, .topbar-na {
  margin-top: 12px !important;       /* arriba de la píldora */
  margin-bottom: 12px !important;    /* abajo de la píldora  */
}

/* Evitar márgenes extra del botón */
.topbar .stButton, .topbar-ux .stButton, .topbar-na .stButton {
  margin: 0 !important;
}

/* Tira de ayuda */
.help-strip {
  margin-top: 8px !important;
  margin-bottom: 12px !important;
}

/* Tarjetas/secciones (formularios, tablas, etc.) */
.form-card {
  margin-top: 19px !important;       /* distancia entre píldora y tarjeta */
  margin-bottom: 28px !important;    /* separación con la siguiente sección */
  padding-top: 12px !important;
}
</style>
""", unsafe_allow_html=True)

# ====== ⬆️⬆️ FIN CSS de espaciado ⬆️⬆️ ======


# ===== Inicialización de visibilidad por única vez =====
if "_ui_bootstrap" not in st.session_state:
    st.session_state["nt_visible"]  = True   # Nueva tarea
    st.session_state["ux_visible"]  = True   # Editar estado
    st.session_state["na_visible"]  = True   # Nueva alerta
    st.session_state["pri_visible"] = False  # Prioridad
    st.session_state["eva_visible"] = False  # Evaluación
    st.session_state["_ui_bootstrap"] = True

# ===========================
# A PARTIR DE AQUÍ: tu UI va dentro de render()
# ===========================
def render():
    """
    Renderiza TODA la UI de Gestión (formulario, editar estado,
    nueva alerta, prioridad, evaluación, historial, etc.)
    """

# ---------- Estado inicial (RESTABLECIDO) ----------
if "df_main" not in st.session_state:
    # ✅ USAR SOLO el lector robusto; NO volver a leer con read_csv
    base = _read_sheet_tab()
    if base is None or not isinstance(base, pd.DataFrame):
        base = pd.DataFrame([], columns=COLS)

    # Garantizar columnas esperadas
    for c in COLS:
        if c not in base.columns:
            base[c] = None

    # Columna de control
    if "__DEL__" not in base.columns:
        base["__DEL__"] = False
    base["__DEL__"] = base["__DEL__"].fillna(False).astype(bool)

    # Normalización numérica si existe
    if "Calificación" in base.columns:
        base["Calificación"] = pd.to_numeric(base["Calificación"], errors="coerce").fillna(0).astype(int)

    st.session_state["df_main"] = base[COLS + ["__DEL__"]].copy()


# ---------- CSS ----------
st.markdown("""
<style>
/* =================== Variables de tema =================== */
:root{
  --lilac:      #B38BE3;
  --lilac-50:   #F6EEFF;
  --lilac-600:  #8B5CF6;

  --blue-pill-bg: #38BDF8;
  --blue-pill-bd: #0EA5E9;
  --blue-pill-fg: #ffffff;

  /* Alto unificado de botón y píldora */
  --pill-h: 36px;

  /* Ancho de las píldoras (Nueva tarea / Editar estado / Nueva alerta) */
  --pill-width: 158px;

  /* Celeste institucional de títulos */
  --pill-azul:      #94BEEA;
  --pill-azul-bord: #94BEEA;

  /* ===== Píldoras para Prioridad / Evaluación ===== */
  --pill-rosa:      #67D3C4;
  --pill-rosa-bord: #67D3C4;
}

/* ======= ESPACIADO GLOBAL AÑADIDO ======= */
/* Más aire debajo del título principal */
.block-container h1{
  margin-bottom: 18px !important;
}
/* Margen arriba/abajo para TODAS las barras con píldoras */
.topbar, .topbar-ux, .topbar-na, .topbar-pri, .topbar-eval{
  margin-top: 12px !important;
  margin-bottom: 12px !important;
}
/* Separación general entre tarjetas/secciones */
.form-card{
  margin-top: 10px !important;      /* respiro arriba */
  margin-bottom: 28px !important;   /* respiro abajo entre secciones */
}
/* ======================================= */

/* =================== Inputs =================== */
.form-card [data-baseweb="input"] > div,
.form-card [data-baseweb="textarea"] > div,
.form-card [data-baseweb="select"] > div,
.form-card [data-baseweb="datepicker"] > div{
  min-height: 44px !important;
  border-radius: 12px !important;
  border: 1px solid #E5E7EB !important;
  background: #fff !important;
  width: 100% !important;
  box-sizing: border-box !important;
}
.form-card [data-baseweb="input"] input,
.form-card [data-baseweb="textarea"] textarea,
.form-card [data-baseweb="select"] div,
.form-card [data-baseweb="datepicker"] input{
  font-size: 15px !important;
}

/* Foco */
.form-card [data-baseweb="input"] > div:has(input:focus),
.form-card [data-baseweb="textarea"] > div:has(textarea:focus),
.form-card [data-baseweb="select"] > div:focus-within,
.form-card [data-baseweb="datepicker"] > div:focus-within{
  border-color: #60A5FA !important;
  box-shadow: 0 0 0 3px rgba(96,165,250,.25) !important;
}

/* =================== Sidebar (ancho dinámico) =================== */
[data-testid="stSidebar"]{
  background: var(--lilac-50) !important;
  border-right: 1px solid #ECE6FF !important;
  transition: width .2s ease, min-width .2s ease;
}
/* Sidebar ABIERTA -> 200px */
[data-testid="stSidebar"][aria-expanded="true"]{
  width: 200px !important;
  min-width: 200px !important;
}
[data-testid="stSidebar"][aria-expanded="true"] > div{ width: 200px !important; }
/* Sidebar CERRADA -> 0px (contenido se expande) */
[data-testid="stSidebar"][aria-expanded="false"]{
  width: 0 !important;
  min-width: 0 !important;
}
[data-testid="stSidebar"][aria-expanded="false"] > div{ width: 0 !important; }
[data-testid="stSidebar"] a{
  color: var(--lilac-600) !important;
  font-weight: 600 !important;
  text-decoration: none !important;
}
[data-testid="stSidebar"] .stButton > button{
  border-radius: 12px !important;
  background: var(--lilac) !important;
  border: 1px solid var(--lilac) !important;
  color:#fff !important;
  font-weight:800 !important;
  box-shadow: 0 8px 18px rgba(179,139,227,.25) !important;
}
[data-testid="stSidebar"] .stButton > button:hover{ filter: brightness(.96); }

/* =================== Píldoras (títulos celestes) =================== */
.form-title,
.form-title-ux,
.form-title-na{
  display:inline-flex !important;
  align-items:center !important;
  gap:.5rem !important;
  padding: 6px 12px !important;
  border-radius: 12px !important;
  background: var(--pill-azul) !important;
  border: 1px solid var(--pill-azul-bord) !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  letter-spacing: .2px !important;
  margin: 6px 0 10px 0 !important;
  width: var(--pill-width) !important;
  justify-content: center !important;
  box-shadow: 0 6px 16px rgba(148,190,234,.3) !important;
  min-height: var(--pill-h) !important;
  height: var(--pill-h) !important;
  line-height:1 !important;
  white-space: nowrap !important;
  font-size: 14px !important;
}

/* =================== Triangulito (toggle) =================== */
.toggle-icon{
  display:flex !important;
  align-items:center !important;
}
/* (Se mantiene para compatibilidad, pero lo anulamos abajo con el override) */
.toggle-icon .stButton>button{
  padding: 0px !important;
  min-width: 32px !important;
  height: var(--pill-h) !important;
  border-radius: 10px !important;
  background: var(--lilac-600) !important;
  border: 1px solid var(--lilac-600) !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  line-height: 1 !important;
  display:inline-flex !important; align-items:center !important;
  box-shadow: 0 4px 12px rgba(139,92,246,.25) !important;
}
.toggle-icon .stButton>button:hover{ filter: brightness(.98) !important; }
.toggle-icon .stButton>button:focus{
  outline: none !important; box-shadow: 0 0 0 2px rgba(139,92,246,.35) !important;
}

/* =================== SELECTs =================== */
.form-card [data-baseweb="select"] > div{
  overflow: visible !important;
  white-space: nowrap !important;
  text-overflow: clip !important;
  width: fit-content !重要;
  min-width: 240px !important;
}
.form-card [data-baseweb="select"] [role="combobox"]{
  overflow: visible !important;
  white-space: nowrap !important;
  text-overflow: clip !important;
}
.form-card [data-baseweb="select"] span,
.form-card [data-baseweb="select"] label,
.form-card [data-baseweb="select"] div div{
  white-space: nowrap !important;
  text-overflow: clip !important;
  overflow: visible !important;
  max-width: none !important;
}

/* Anchura mayor para Área y Estado (fila 1 col 1 y fila 2 col 1) */
.form-card [data-testid="stHorizontalBlock"]:nth-of-type(1)
  > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width: 300px !important; }
.form-card [data-testid="stHorizontalBlock"]:nth-of-type(2)
  > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width: 300px !important; }

/* =================== Responsivo =================== */
@media (max-width: 980px){
  .form-card [data-baseweb="select"] > div{ min-width: 200px !important; }
  .form-title, .form-title-ux, .form-title-na{ width: auto !important; }
}

/* =================== Tarjeta de Alertas (grid) =================== */
.form-card.alertas-grid{
  display: grid !important;
  grid-template-columns: repeat(5, 1fr);
  grid-column-gap: 20px;
  grid-row-gap: 16px;
  align-items: start;
}
.form-card.alertas-grid [data-testid="stHorizontalBlock"]{ display: contents !important; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(1){ grid-column: 1; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(2){ grid-column: 2 / 5; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(3){ grid-column: 5; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(4){ grid-column: 1; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(5){ grid-column: 2; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(6){ grid-column: 3; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(7){ grid-column: 4; }
.form-card.alertas-grid > [data-testid="column"]:nth-of-type(8){ grid-column: 5; }
.form-card.alertas-grid [data-baseweb="select"] > div,
.form-card.alertas-grid [data-baseweb="input"] > div,
.form-card.alertas-grid [data-baseweb="datepicker"] > div{
  width: 100% !important; min-width: 0 !important; white-space: normal !important;
}

/* =================== Botones dentro de la card =================== */
.form-card .stButton > button,
.form-card [data-testid="baseButton-secondary"],
.form-card [data-testid="baseButton-primary"]{ width: 100% !important; }
.form-card .stButton > button{ padding-top: 10px !important; padding-bottom: 10px !important; }

/* =================== Download button =================== */
[data-testid="stDownloadButton"] a,
[data-testid="stDownloadButton"] button,
[data-testid="stDownloadButton"] a *,
[data-testid="stDownloadButton"] button *{
  font-size: var(--actions-font) !important;
  line-height: 1.05 !important;
  white-space: nowrap !important;
}
[data-testid="stDownloadButton"] a,
[data-testid="stDownloadButton"] button{
  padding: var(--actions-pad-y) var(--actions-pad-x) !important;
  border-radius: 12px !important;
  border: 1px solid #E5E7EB !important;
  display: inline-flex !important; align-items: center !important; gap: 6px !important;
}

/* =================== Franja de indicaciones =================== */
.help-strip{
  display:block !important;
  padding:2px 0 !important;
  line-height:1.25 !important;
  margin-top: 0px !important;
  margin-bottom: 14px !important;
}
.form-card > .help-strip{
  margin-top: 0px !important;
  margin-bottom: 14px !important;
}
.help-strip strong{ display:inline-block !important; }

/* =================== Topbar (expander + píldora) =================== */
.topbar, .topbar-ux, .topbar-na{
  display:flex !important;
  align-items:center !important;
  gap:8px !important;
}
.topbar .stButton,
.topbar-ux .stButton,
.topbar-na .stButton{ display:inline-flex !important; align-items:center !important; }
.topbar .stButton>button,
.topbar-ux .stButton>button,
.topbar-na .stButton>button,
.pill-btn .stButton>button{
  height: var(--pill-h) !important;
  padding:0 16px !important;
  border-radius:10px !important;
  display:inline-flex !important; align-items:center !important;
}

/* ================================================================== */
/* =================== PRIORIDAD / EVALUACIÓN ======================= */
/* ================================================================== */

/* Barras superiores (mismo layout) */
.topbar-pri, .topbar-eval{
  display:flex !important;
  align-items:center !important;
  gap:8px !important;
}
.topbar-pri .stButton, .topbar-eval .stButton{
  display:inline-flex !important; align-items:center !important;
}
.topbar-pri .stButton>button, .topbar-eval .stButton>button{
  height: var(--pill-h) !important; padding:0 16px !important; border-radius:10px !important;
  display:inline-flex !important; align-items:center !important;
}

/* ===== Píldoras ROSA (Prioridad y Evaluación) ===== */
.form-title-pri,
.form-title-eval{
  display:inline-flex !important;
  align-items:center !important;
  gap:.5rem !important;
  padding:6px 12px !important;
  border-radius:12px !important;
  background: var(--pill-rosa) !important;
  border: 1px solid var(--pill-rosa-bord) !important;
  color:#ffffff !important;
  font-weight: 800 !important;
  font-size: 14px !important;
  letter-spacing:.2px !important;
  white-space: nowrap !important;
  margin:6px 0 10px 0 !important;
  width: var(--pill-width) !important;
  justify-content:center !important;
  box-shadow:0 6px 16px rgba(214,154,194,.30) !important;
  min-height: var(--pill-h) !important;
  height: var(--pill-h) !important;
  line-height:1 !important;
}

/* Responsivo */
@media (max-width: 980px){
  .form-title-pri, .form-title-eval{ width: auto !important; }
}

/* ===== Compactar espacios entre bloques ===== */
.block-container [data-testid="stVerticalBlock"]{
  row-gap: 10px !important;
  gap: 6px !important;
}
.block-container [data-testid="stVerticalBlock"]:has(.topbar),
.block-container [data-testid="stVerticalBlock"]:has(.topbar-ux),
.block-container [data-testid="stVerticalBlock"]:has(.topbar-na),
.block-container [data-testid="stVerticalBlock"]:has(.topbar-pri),
.block-container [data-testid="stVerticalBlock"]:has(.topbar-eval){
  row-gap: 4px !important;
  gap: 4px !important;
}
.block-container [data-testid="stHorizontalBlock"]:has(.topbar),
.block-container [data-testid="stHorizontalBlock"]:has(.topbar-ux),
.block-container [data-testid="stHorizontalBlock"]:has(.topbar-na),
.block-container [data-testid="stHorizontalBlock"]:has(.topbar-pri),
.block-container [data-testid="stHorizontalBlock"]:has(.topbar-eval){
  column-gap: 8px !important;
  gap: 8px !important;
}
.block-container .element-container:has(.topbar),
.block-container .element-container:has(.topbar-ux),
.block-container .element-container:has(.topbar-na),
.block-container .element-container:has(.topbar-pri),
.block-container .element-container:has(.topbar-eval){
  margin-top: 19px !important;
  margin-bottom: 6px !important;
}

/* ===== Alineación robusta botón + píldora en TODAS las barras ===== */
.topbar, .topbar-ux, .topbar-na, .topbar-pri, .topbar-eval{
  align-items: center !important;
}
.block-container .stMarkdown:has(.form-title),
.block-container .stMarkdown:has(.form-title-ux),
.block-container .stMarkdown:has(.form-title-na),
.block-container .stMarkdown:has(.form-title-pri),
.block-container .stMarkdown:has(.form-title-eval){
  margin: 0 !important;
}

/* === Override para bajar indicaciones (todas y por sección) === */
#nt-help,
#ux-help,
#na-help,
#pri-help,
#eva-help{
  transform: none !important;
  margin-top: 10px !important;
  margin-bottom: 14px !important;
}
.help-strip,
.form-card > .help-strip{
  margin-top: 10px !important;
}

/* ===== ULTRA PATCH: eliminar “cuadradito” del toggle SOLO en #ntbar ===== */

/* 0) El contenedor de la columna NO debe aportar padding ni sombra */
#ntbar .toggle-icon,
#ntbar .toggle-icon .element-container,
#ntbar .toggle-icon [data-testid="stVerticalBlock"],
#ntbar .toggle-icon [data-testid="stHorizontalBlock"],
#ntbar .toggle-icon [data-testid="stButton"]{
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}

/* 1) Mata fondo/borde/sombra de TODOS los wrappers del botón en este bloque */
#ntbar .toggle-icon .stButton,
#ntbar .toggle-icon .stButton > div,
#ntbar .toggle-icon [data-testid^="stButton"],
#ntbar .toggle-icon [data-testid^="stButton"] > div,
#ntbar .toggle-icon [data-testid^="baseButton"],
#ntbar .toggle-icon [data-testid^="baseButton"] > div,
#ntbar .toggle-icon [data-testid^="baseButton"] > div > div{
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
  min-height: 0 !important;
}

/* 2) El <button> real */
#ntbar .toggle-icon .stButton button,
#ntbar .toggle-icon [data-testid^="stButton"] button,
#ntbar .toggle-icon [data-testid^="baseButton"] button,
#ntbar .toggle-icon button[kind],
#ntbar .toggle-icon button[class*="primary"],
#ntbar .toggle-icon button[class*="secondary"],
#ntbar .toggle-icon [role="button"]{
  background: transparent !important;
  background-image: none !important;
  border: 0 !important;
  box-shadow: none !important;
  outline: 0 !important;
  -webkit-appearance: none !important;
  appearance: none !important;
  padding: 0 !important;
  margin: 0 !important;
  width: auto !important;
  min-width: 0 !important;
  height: auto !important;
  min-height: 0 !important;
  border-radius: 0 !important;

  font-weight: 800 !important;
  font-size: 20px !important;
  line-height: 1 !important;
  transform: translateY(8px);
  color: inherit !important;
  cursor: pointer !important;
}

/* 3) Evita que :hover/:focus/:active reintroduzcan estilos del tema */
#ntbar .toggle-icon .stButton button:hover,
#ntbar .toggle-icon .stButton button:focus,
#ntbar .toggle-icon .stButton button:active,
#ntbar .toggle-icon [data-testid^="stButton"] button:hover,
#ntbar .toggle-icon [data-testid^="stButton"] button:focus,
#ntbar .toggle-icon [data-testid^="stButton"] button:active,
#ntbar .toggle-icon [data-testid^="baseButton"] button:hover,
#ntbar .toggle-icon [data-testid^="baseButton"] button:focus,
#ntbar .toggle-icon [data-testid^="baseButton"] button:active,
#ntbar .toggle-icon [role="button"]:hover,
#ntbar .toggle-icon [role="button"]:focus,
#ntbar .toggle-icon [role="button"]:active{
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  outline: 0 !important;
}

/* 4) Por si el tema agrega pseudo-elementos decorativos */
#ntbar .toggle-icon .stButton button::before,
#ntbar .toggle-icon .stButton button::after,
#ntbar .toggle-icon [data-testid^="stButton"] button::before,
#ntbar .toggle-icon [data-testid^="stButton"] button::after,
#ntbar .toggle-icon [data-testid^="baseButton"] button::before,
#ntbar .toggle-icon [data-testid^="baseButton"] button::after,
#ntbar .toggle-icon [role="button"]::before,
#ntbar .toggle-icon [role="button"]::after{
  content: none !important;
  display: none !important;
}

/* ========== NUCLEAR RESET PARA EL TOGGLE EN #ntbar ========== */
#ntbar .toggle-icon *,
#ntbar .toggle-icon *::before,
#ntbar .toggle-icon *::after{
  background: transparent !important;
  background-color: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}
#ntbar .toggle-icon :is(button, [role="button"], [data-testid^="baseButton"] button){
  all: unset !important;
  display: inline !important;
  cursor: pointer !important;
  user-select: none !important;
  font-weight: 800 !important;
  font-size: 20px !important;
  line-height: 1 !important;
  color: inherit !important;
  transform: translateY(8px);
  -webkit-appearance: none !important;
  appearance: none !important;
  padding: 0 !important;
  margin: 0 !important;
  border-radius: 0 !important;
}
#ntbar .toggle-icon :is(button, [role="button"], [data-testid^="baseButton"] button):hover,
#ntbar .toggle-icon :is(button, [role="button"], [data-testid^="baseButton"] button):focus,
#ntbar .toggle-icon :is(button, [role="button"], [data-testid^="baseButton"] button):active{
  all: unset !important;
  display: inline !important;
  cursor: pointer !important;
  font-weight: 800 !important;
  font-size: 20px !important;
  line-height: 1 !important;
  color: inherit !important;
  transform: translateY(8px);
}
#ntbar .toggle-icon [data-testid],
#ntbar .toggle-icon .stButton,
#ntbar .toggle-icon .stButton > div{
  min-width: 0 !important;
  min-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
}

/* Más espacio entre las indicaciones (help-strip) y la sección */
#nt-help, #ux-help, #na-help, #pri-help, #eva-help{
  margin-bottom: 10px !important;
}

/* Respiro superior para tarjetas */
#nt-section .form-card,
#ux-section .form-card,
#na-section .form-card,
#pri-section .form-card,
#eva-section .form-card{
  margin-top: 8px !important;
}

/* ===== (ag-align-fix) integrado al bloque principal ===== */
/* quita padding lateral que desalineaba 1–2px */
#prior-grid .ag-header-viewport,
#prior-grid .ag-center-cols-viewport,
#eval-grid  .ag-header-viewport,
#eval-grid  .ag-center-cols-viewport{
  padding-left:0 !important;
  padding-right:0 !important;
}
/* evita corrimientos distintos entre header y body */
#prior-grid .ag-header, #prior-grid .ag-center-cols-container,
#eval-grid  .ag-header, #eval-grid  .ag-center-cols-container{
  transform: translateX(0) !important;
}
/* bordes de columnas uniformes (las “líneas plomitas”) */
#prior-grid .ag-header-cell, #prior-grid .ag-cell,
#eval-grid  .ag-header-cell, #eval-grid  .ag-cell{
  border-right:1px solid #E9EDF3 !important;
}
           
</style>
""", unsafe_allow_html=True)

# ---------- Título ----------
st.title("📂 Gestión - ENI 2025")

# ===== helpers de select con emojis =====
def _opt_map(container, label, mapping, default_value):
    keys = list(mapping.keys())
    try:
        default_idx = [v for v in mapping.values()].index(default_value)
    except ValueError:
        default_idx = 0
    shown = container.selectbox(label, keys, index=default_idx)
    return mapping[shown]

# Emojis/colores
EMO_AREA = {
    "😃 Jefatura": "Jefatura",
    "✏️ Gestión": "Gestión",
    "💻 Base de datos": "Base de datos",
    "📈  Metodología": "Metodología",
    "🔠 Monitoreo": "Monitoreo",
    "🥇 Capacitación": "Capacitación",
    "💾 Consistencia": "Consistencia",
}
EMO_COMPLEJIDAD = {"🔴 Alta": "Alta", "🟡 Media": "Media", "🟢 Baja": "Baja"}
EMO_PRIORIDAD   = {"🔥 Alta": "Alta", "✨ Media": "Media", "🍃 Baja": "Baja"}
EMO_ESTADO      = {"🍼 No iniciado": "No iniciado","⏳ En curso": "En curso"}
EMO_SI_NO       = {"✅ Sí": "Sí", "🚫 No": "No"}

# ======= CATÁLOGO DE FASES (igual) =======
FASES = [
    "Capacitación",
    "Post-capacitación",
    "Pre-consistencia",
    "Consistencia",
    "Operación de campo",
]

# ================== Utilidades de ID ==================
import re
import pandas as pd
from datetime import datetime

def _area_initial(area: str) -> str:
    """
    Devuelve la primera letra alfabética del nombre del área (incluye tildes) en MAYÚSCULA.
    Ej.: 'Jefatura' -> 'J', 'monitoreo' -> 'M'
    """
    if not area:
        return ""
    m = re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", str(area))
    return (m.group(0).upper() if m else "")

def _person_initials(nombre: str) -> str:
    """
    Toma la primera letra del nombre y la primera del primer apellido.
    Ej.: 'Vivian Saurino' -> 'VS'; 'Elías A. Aguirre' -> 'EA'
    Maneja puntos e iniciales sueltas.
    """
    if not nombre:
        return ""
    # Limpia separando por espacios y descartando vacíos
    parts = [p for p in re.split(r"\s+", str(nombre).strip()) if p]
    if not parts:
        return ""
    # Primera inicial (nombre)
    ini1 = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", parts[0])[:1].upper() if parts else ""
    # Segunda inicial (primer apellido que no sea inicial suelta tipo "A.")
    ini2 = ""
    for p in parts[1:]:
        t = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", p)
        if t:
            ini2 = t[0].upper()
            break
    return f"{ini1}{ini2}"

def make_id_prefix(area: str, responsable: str) -> str:
    """
    Construye el prefijo del ID: [primera letra de área][inicial nombre][inicial apellido]
    Ej.: 'Jefatura' + 'Vivian Saurino' -> 'JVS'
    """
    a = _area_initial(area)
    p = _person_initials(responsable)
    return f"{a}{p}"

def next_id_by_person(df: pd.DataFrame, area: str, responsable: str) -> str:
    """
    Devuelve el siguiente ID correlativo para el prefijo calculado a partir de área y responsable.
    Formato: PREFIJO + '_' + correlativo (1, 2, 3, ...)
    Ej.: 'JVS_1', 'JVS_2', 'MEA_1', etc.
    Cuenta existentes en df['Id'] que empiezan con 'PREFIJO_'.
    """
    prefix = make_id_prefix(area, responsable)
    if not prefix:
        return ""
    if "Id" not in df.columns or df.empty:
        seq = 1
    else:
        serie = df["Id"].astype(str).fillna("")
        seq = 1 + serie.str.startswith(prefix + "_").sum()
    return f"{prefix}_{seq}"

# ====== Callback opcional: poner hora automática cuando se elige fecha ======
# Nota: este callback se usa con date_input FUERA del st.form (porque dentro no disparan on_change).
# Se define aquí de forma segura por si 'st' no está importado en este módulo.
if "_auto_time_on_date" not in globals():
    def _auto_time_on_date():
        """
        Si hay fecha (fi_d) y no hay hora (fi_t) en st.session_state,
        fija la hora actual (sin segundos). Requiere que en el módulo principal exista:
        `import streamlit as st`.
        """
        try:
            # 'st' debe existir en el módulo principal
            import streamlit as st  # import local y seguro
            if st.session_state.get("fi_d") and not st.session_state.get("fi_t"):
                now = datetime.now().replace(second=0, microsecond=0)
                st.session_state["fi_t"] = now.time()
        except Exception:
            # Si no hay streamlit o no hay session_state, simplemente no hacemos nada.
            pass


# ================== Formulario (misma malla + hora inmediata) ==================

st.session_state.setdefault("nt_visible", True)
chev = "▾" if st.session_state.get("nt_visible", True) else "▸"

# ---------- Barra superior ----------
st.markdown('<div id="ntbar" class="topbar">', unsafe_allow_html=True)
c_toggle, c_pill = st.columns([0.028, 0.965], gap="medium")
with c_toggle:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_nt():
        st.session_state["nt_visible"] = not st.session_state.get("nt_visible", True)
    st.button(chev, key="nt_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_nt)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill:
    st.markdown('<div class="form-title">&nbsp;&nbsp;📝&nbsp;&nbsp;Nueva tarea</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state.get("nt_visible", True):

    # ===== Scope local para NO afectar otras secciones =====
    st.markdown('<div id="nt-section">', unsafe_allow_html=True)

    # ===== Indicaciones cortas (debajo de la píldora) =====
    st.markdown("""
    <div class="help-strip">
      ✳️ Completa: <strong>Área, Fase, Tarea, Responsable y Fecha</strong>. La hora es automática.
    </div>
    """, unsafe_allow_html=True)

    # ===== ESPACIADOR entre indicaciones y el card (único ajuste pedido) =====
    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

    submitted = False

    # ===== Card REAL que envuelve TODAS las celdas =====
    with st.container(border=True):
        # Sentinel para limitar estilos SOLO a este card
        st.markdown('<span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

        # CSS mínimo SOLO para inputs al 100% dentro de este card
        st.markdown("""
        <style>
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea{
            width:100% !important;
          }
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea > div{
            width:100% !important; max-width:none !important;
          }
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid="stDateInput"] input,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid^="stTimeInput"] input{
            width:100% !important;
          }
        </style>
        """, unsafe_allow_html=True)

        # Proporciones (tus originales)
        A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

        # ---------- FILA 1 ----------
        r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
        area = r1c1.selectbox("Área", options=AREAS_OPC, index=0, key="nt_area")
        FASES = ["Capacitación","Post-capacitación","Pre-consistencia","Consistencia","Operación de campo"]
        fase   = r1c2.selectbox("Fase", options=FASES, index=None, placeholder="Selecciona una fase", key="nt_fase")
        tarea  = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
        detalle= r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
        resp   = r1c5.text_input("Responsable", placeholder="Nombre", key="nt_resp")
        ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")

        # ---------- FILA 2 ----------
        c2_1, c2_2, c2_3, c2_4, c2_5, c2_6 = st.columns([A, Fw, T, D, R, C], gap="medium")
        tipo   = c2_1.text_input("Tipo de tarea", placeholder="Tipo o categoría", key="nt_tipo")
        estado = _opt_map(c2_2, "Estado", EMO_ESTADO, "No iniciado")

        # Fecha editable + callback inmediato
        st.session_state.setdefault("fi_d", None)
        st.session_state.setdefault("fi_t", None)
        c2_3.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)

        # Hora auto (solo lectura)
        _t = st.session_state.get("fi_t"); _t_txt = ""
        if _t is not None:
            try: _t_txt = _t.strftime("%H:%M")
            except Exception: _t_txt = str(_t)
        c2_4.text_input("Hora (auto)", value=_t_txt, disabled=True,
                        help="Se asigna al elegir la fecha", key="fi_t_view")

        # ID preview
        _df_tmp = st.session_state.get("df_main", pd.DataFrame()).copy() if "df_main" in st.session_state else pd.DataFrame()
        prefix = make_id_prefix(st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp))
        if st.session_state.get("fi_d"):
            id_preview = next_id_by_person(_df_tmp, st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp))
        else:
            id_preview = f"{prefix}_" if prefix else ""
        c2_5.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

        # Botón
        with c2_6:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            submitted = st.button("➕ Agregar", use_container_width=True, key="btn_agregar")

    # Cierra scope local
    st.markdown("</div>", unsafe_allow_html=True)  # cierra #nt-section

    # ---------- Guardado ----------
    if submitted:
        try:
            df = st.session_state.get("df_main", pd.DataFrame()).copy()

            def _sanitize(df_in: pd.DataFrame, target_cols=None) -> pd.DataFrame:
                df_out = df_in.copy()
                if "DEL" in df_out.columns and "__DEL__" in df_out.columns:
                    df_out["__DEL__"] = df_out["__DEL__"].fillna(False) | df_out["DEL"].fillna(False)
                    df_out = df_out.drop(columns=["DEL"])
                elif "DEL" in df_out.columns:
                    df_out = df_out.rename(columns={"DEL": "__DEL__"})
                df_out = df_out.loc[:, ~pd.Index(df_out.columns).duplicated()].copy()
                if not df_out.index.is_unique: df_out = df_out.reset_index(drop=True)
                if target_cols:
                    target = list(dict.fromkeys(list(target_cols)))
                    for c in target:
                        if c not in df_out.columns: df_out[c] = None
                    ordered = [c for c in target] + [c for c in df_out.columns if c not in target]
                    df_out = df_out.loc[:, ordered].copy()
                return df_out

            df = _sanitize(df, COLS if "COLS" in globals() else None)
            f_ini = combine_dt(st.session_state.get("fi_d"), st.session_state.get("fi_t"))

            new = blank_row()
            new.update({
                "Área": area,
                "Id": next_id_by_person(df, area, st.session_state.get("nt_resp", "")),
                "Tarea": st.session_state.get("nt_tarea", ""),
                "Tipo": st.session_state.get("nt_tipo", ""),
                "Responsable": st.session_state.get("nt_resp", ""),
                "Fase": fase,
                "Estado": estado,
                "Fecha inicio": f_ini,
                "Ciclo de mejora": ciclo_mejora,
                "Detalle": st.session_state.get("nt_detalle", ""),
            })

            df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
            if "Fecha inicio" in df.columns:
                df["Fecha inicio"] = pd.to_datetime(df["Fecha inicio"], errors="coerce")

            df = _sanitize(df, COLS if "COLS" in globals() else None)
            st.session_state["df_main"] = df.copy()
            os.makedirs("data", exist_ok=True)
            df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig", mode="w")

            st.success(f"✔ Tarea agregada (Id {new['Id']}).")
            st.rerun()
        except Exception as e:
            st.error(f"No pude guardar la nueva tarea: {e}")

# Separación vertical
st.markdown(f"<div style='height:{SECTION_GAP}px;'></div>", unsafe_allow_html=True)



# ================== EDITAR ESTADO (mismo layout que "Nueva alerta") ==================
st.session_state.setdefault("est_visible", True)
chev_est = "▾" if st.session_state["est_visible"] else "▸"

# ---------- Barra superior ----------
st.markdown('<div class="topbar-eval">', unsafe_allow_html=True)
c_est_toggle, c_est_pill = st.columns([0.028, 0.965], gap="medium")
with c_est_toggle:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_est():
        st.session_state["est_visible"] = not st.session_state["est_visible"]
    st.button(chev_est, key="est_toggle_icon_v3", help="Mostrar/ocultar", on_click=_toggle_est)
    st.markdown('</div>', unsafe_allow_html=True)
with c_est_pill:
    st.markdown('<div class="form-title">&nbsp;&nbsp;✏️&nbsp;&nbsp;Editar estado</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["est_visible"]:

    # --- Contenedor + CSS local ---
    st.markdown('<div id="est-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #est-section .stButton > button { width: 100% !important; }
      #est-section .ag-theme-alpine .ag-header-cell-label{ font-weight: 400 !important; }
      #est-section .ag-body-horizontal-scroll,
      #est-section .ag-center-cols-viewport { overflow-x: hidden !important; }
      .section-est .help-strip + .form-card{ margin-top: 6px !important; }
    </style>
    """, unsafe_allow_html=True)

    # ===== Wrapper UNIDO: help-strip + form-card =====
    st.markdown("""
    <div class="section-est">
      <div class="help-strip">
        🔷 <strong>Actualiza el estado</strong> de una tarea ya registrada usando los filtros
      </div>
      <div class="form-card">
    """, unsafe_allow_html=True)

    # Proporciones
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    # Base
    df_all = st.session_state.get("df_main", pd.DataFrame()).copy()

    # ===== FILTROS =====
    with st.form("est_filtros_v3", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

        AREAS_OPC = st.session_state.get(
            "AREAS_OPC",
            sorted([x for x in df_all.get("Área", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        ) or []
        est_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0)

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        est_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

        df_resp_src = df_all.copy()
        if est_area != "Todas":
            df_resp_src = df_resp_src[df_resp_src.get("Área", "") == est_area]
        if est_fase != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == est_fase]
        responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        est_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0)

        est_desde = c_desde.date_input("Desde", value=None)
        est_hasta = c_hasta.date_input("Hasta",  value=None)

        with c_buscar:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            est_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado de tareas =====
    df_tasks = df_all.copy()
    if est_do_buscar:
        if est_area != "Todas":
            df_tasks = df_tasks[df_tasks.get("Área", "") == est_area]
        if est_fase != "Todas" and "Fase" in df_tasks.columns:
            df_tasks = df_tasks[df_tasks["Fase"].astype(str) == est_fase]
        if est_resp != "Todos":
            df_tasks = df_tasks[df_tasks.get("Responsable", "").astype(str) == est_resp]
        if "Fecha inicio" in df_tasks.columns:
            fcol = pd.to_datetime(df_tasks["Fecha inicio"], errors="coerce")
            if est_desde:
                df_tasks = df_tasks[fcol >= pd.to_datetime(est_desde)]
            if est_hasta:
                df_tasks = df_tasks[fcol <= (pd.to_datetime(est_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    # ===== Tabla "Resultados" =====
    st.markdown("**Resultados**")

    def _fmt_date(s):
        s = pd.to_datetime(s, errors="coerce")
        return s.dt.strftime("%Y-%m-%d").fillna("")

    def _fmt_time(s):
        s = pd.to_datetime(s, errors="coerce")
        return s.dt.strftime("%H:%M").fillna("")

    cols_out = [
        "Id", "Tarea",
        "Estado actual", "Fecha estado actual", "Hora estado actual",
        "Estado modificado", "Fecha estado modificado", "Hora estado modificado"
    ]

    df_view = pd.DataFrame(columns=cols_out)
    if not df_tasks.empty:
        base = df_tasks.copy()
        for need in ["Id","Tarea","Estado","Fecha estado actual","Hora estado actual",
                     "Estado modificado","Fecha estado modificado","Hora estado modificado","Fecha inicio"]:
            if need not in base.columns:
                base[need] = ""

        fecha_estado = base["Fecha estado actual"].replace("", pd.NA)
        hora_estado  = base["Hora estado actual"].replace("", pd.NA)
        fi = base["Fecha inicio"]

        df_view = pd.DataFrame({
            "Id":   base["Id"].astype(str),
            "Tarea": base["Tarea"].astype(str),
            "Estado actual": base["Estado"].astype(str),
            "Fecha estado actual": fecha_estado.fillna(_fmt_date(fi)),
            "Hora estado actual":  hora_estado.fillna(_fmt_time(fi)),
            "Estado modificado":       base["Estado modificado"].astype(str),
            "Fecha estado modificado": _fmt_date(base["Fecha estado modificado"]),
            "Hora estado modificado":  _fmt_time(base["Hora estado modificado"]),
        })[cols_out].copy()

    # ========= editores y estilo seguro (sin DOM manual) =========
    estados_editables = ["En curso","Terminado","Pausado","Cancelado","Eliminado"]

    date_editor = JsCode("""
    class DateEditor{
      init(p){
        this.eInput = document.createElement('input');
        this.eInput.type = 'date';
        this.eInput.classList.add('ag-input');
        this.eInput.style.width = '100%';
        const v = (p.value || '').toString().trim();
        if (/^\\d{4}-\\d{2}-\\d{2}$/.test(v)) { this.eInput.value = v; }
        else {
          const d = new Date(v);
          if (!isNaN(d.getTime())){
            const pad=n=>String(n).padStart(2,'0');
            this.eInput.value = d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
          }
        }
      }
      getGui(){ return this.eInput }
      afterGuiAttached(){ this.eInput.focus() }
      getValue(){ return this.eInput.value }
    }""")

    # Mapea el texto a emoji (se devuelve STRING, no HTML)
    estado_emoji_fmt = JsCode("""
    function(p){
      const v = String(p.value || '');
      const M = {"En curso":"🟣 En curso","Terminado":"✅ Terminado","Pausado":"⏸️ Pausado","Cancelado":"⛔ Cancelado","Eliminado":"🗑️ Eliminado"};
      return M[v] || v;
    }""")

    # Aplica colores con cellStyle (objeto JS), compatible con React
    estado_cell_style = JsCode("""
    function(p){
      const v = String(p.value || '');
      const S = {
        "En curso":   {bg:"#EDE7F6", fg:"#4A148C"},
        "Terminado":  {bg:"#E8F5E9", fg:"#1B5E20"},
        "Pausado":    {bg:"#FFF8E1", fg:"#E65100"},
        "Cancelado":  {bg:"#FFEBEE", fg:"#B71C1C"},
        "Eliminado":  {bg:"#ECEFF1", fg:"#263238"}
      };
      const m = S[v]; if(!m) return {};
      return {backgroundColor:m.bg, color:m.fg, fontWeight:'600', textAlign:'center', borderRadius:'12px'};
    }""")

    on_cell_changed = JsCode("""
    function(params){
      if (params.colDef.field === 'Fecha estado modificado'){
        const pad = n => String(n).padStart(2,'0');
        const d = new Date();
        const hhmm = pad(d.getHours()) + ':' + pad(d.getMinutes());
        params.node.setDataValue('Hora estado modificado', hhmm);
      }
    }""")

    # --- AgGrid ---
    gob = GridOptionsBuilder.from_dataframe(df_view)
    gob.configure_grid_options(
        suppressMovableColumns=True,
        domLayout="normal",
        ensureDomOrder=True,
        rowHeight=38,
        headerHeight=42,
        suppressHorizontalScroll=True
    )
    # SIN checkbox
    gob.configure_selection("single", use_checkbox=False)

    gob.configure_column(
        "Estado modificado",
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": estados_editables},
        valueFormatter=estado_emoji_fmt,
        cellStyle=estado_cell_style,
        minWidth=180
    )
    gob.configure_column("Fecha estado modificado", editable=True, cellEditor=date_editor, minWidth=160)
    gob.configure_column("Hora estado modificado",  editable=False, minWidth=140)

    grid_opts = gob.build()
    grid_opts["onCellValueChanged"] = on_cell_changed.js_code

    grid = AgGrid(
        df_view,
        gridOptions=grid_opts,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=(GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED),
        fit_columns_on_grid_load=True,
        enable_enterprise_modules=False,
        reload_data=False,
        height=260,
        allow_unsafe_jscode=True,
        theme="balham"
    )

    # ===== Guardar cambios (actualiza la MISMA fila por Id) =====
    u1, u2 = st.columns([A+Fw+T_width+D+R, C], gap="medium")
    with u2:
        if st.button("💾 Guardar cambios", use_container_width=True, key="est_guardar_inline_v3"):
            try:
                grid_data = pd.DataFrame(grid.get("data", []))
                if grid_data.empty or "Id" not in grid_data.columns:
                    st.info("No hay cambios para guardar.")
                else:
                    grid_data["Id"] = grid_data["Id"].astype(str)
                    base = st.session_state.get("df_main", pd.DataFrame()).copy()
                    if base.empty:
                        st.warning("No hay base para actualizar.")
                    else:
                        base["Id"] = base["Id"].astype(str)
                        cols_to_merge = ["Estado modificado","Fecha estado modificado","Hora estado modificado"]
                        for c in cols_to_merge:
                            if c not in base.columns:
                                base[c] = ""
                        upd = grid_data[["Id"] + cols_to_merge].copy()
                        base = base.merge(upd, on="Id", how="left", suffixes=("", "_NEW"))
                        for c in cols_to_merge:
                            n = f"{c}_NEW"
                            if n in base.columns:
                                base[c] = base[n].where(base[n].notna() & (base[n] != ""), base[c])
                                base.drop(columns=[n], inplace=True)

                        st.session_state["df_main"] = base.copy()
                        os.makedirs("data", exist_ok=True)
                        base.to_csv(os.path.join("data","tareas.csv"), index=False, encoding="utf-8-sig")
                        st.success("Cambios guardados. *Tareas recientes* se actualizará automáticamente.")
                        st.rerun()
            except Exception as e:
                st.error(f"No pude guardar: {e}")

    # Cerrar form-card + section + contenedor
    st.markdown('</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ================== Nueva alerta ==================

st.session_state.setdefault("na_visible", True)
chev3 = "▾" if st.session_state["na_visible"] else "▸"

# ---------- Barra superior ----------
st.markdown('<div class="topbar-na">', unsafe_allow_html=True)
c_toggle3, c_pill3 = st.columns([0.028, 0.965], gap="medium")
with c_toggle3:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_na():
        st.session_state["na_visible"] = not st.session_state["na_visible"]
    st.button(chev3, key="na_toggle_icon_v2", help="Mostrar/ocultar", on_click=_toggle_na)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill3:
    st.markdown('<div class="form-title-na">&nbsp;&nbsp;⚠️&nbsp;&nbsp;Nueva alerta</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["na_visible"]:

    # --- contenedor local + css ---
    st.markdown('<div id="na-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #na-section .stButton > button { width: 100% !important; }
      .section-na .help-strip-na + .form-card{ margin-top: 6px !important; }
    </style>
    """, unsafe_allow_html=True)

    # ===== Wrapper UNIDO: help-strip + form-card =====
    st.markdown("""
    <div class="section-na">
      <div class="help-strip help-strip-na" id="na-help">
        ⚠️ <strong>Vincula una alerta</strong> a una tarea ya registrada
      </div>
      <div class="form-card">
    """, unsafe_allow_html=True)

    # Proporciones (igual que Editar estado)
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    df_all = st.session_state["df_main"].copy()

    # ===== FILTROS =====
    with st.form("na_filtros_v3", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

        AREAS_OPC = st.session_state.get(
            "AREAS_OPC",
            ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
        )
        na_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0)

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        na_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

        df_resp_src = df_all.copy()
        if na_area != "Todas":
            df_resp_src = df_resp_src[df_resp_src["Área"] == na_area]
        if na_fase != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == na_fase]
        responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        na_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0)

        na_desde = c_desde.date_input("Desde", value=None)
        na_hasta = c_hasta.date_input("Hasta",  value=None)

        with c_buscar:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            na_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado de tareas =====
    df_tasks = df_all.copy()
    if na_do_buscar:
        if na_area != "Todas":
            df_tasks = df_tasks[df_tasks["Área"] == na_area]
        if na_fase != "Todas" and "Fase" in df_tasks.columns:
            df_tasks = df_tasks[df_tasks["Fase"].astype(str) == na_fase]
        if na_resp != "Todos":
            df_tasks = df_tasks[df_tasks["Responsable"].astype(str) == na_resp]
        if "Fecha inicio" in df_tasks.columns:
            fcol = pd.to_datetime(df_tasks["Fecha inicio"], errors="coerce")
            if na_desde:
                df_tasks = df_tasks[fcol >= pd.to_datetime(na_desde)]
            if na_hasta:
                df_tasks = df_tasks[fcol <= (pd.to_datetime(na_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    # ===== Tabla =====
    st.markdown("**Resultados**")

    cols_out = [
        "Id", "Tarea",
        "¿Generó alerta?", "N° alerta",
        "Fecha de detección", "Hora de detección",
        "¿Se corrigió?", "Fecha de corrección", "Hora de corrección",
    ]

    # Data para la grilla (puede ser vacía)
    df_view = pd.DataFrame(columns=cols_out)
    if not df_tasks.empty:
        df_tmp = df_tasks.dropna(subset=["Id"]).copy()
        for needed in ["Tarea"]:
            if needed not in df_tmp.columns:
                df_tmp[needed] = ""
        df_view = df_tmp.assign(
            **{
                "¿Generó alerta?": "No",  # default
                "N° alerta": "1",         # default
                "Fecha de detección": "",
                "Hora de detección": "",
                "¿Se corrigió?": "No",    # default
                "Fecha de corrección": "",
                "Hora de corrección": "",
            }
        )[cols_out].copy()

    # ====== AG-GRID (config directa sin GridOptionsBuilder) ======
    from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode, JsCode

    # editores de fecha
    date_editor = JsCode("""
    class DateEditor{
      init(p){
        this.eInput = document.createElement('input');
        this.eInput.type = 'date';
        this.eInput.classList.add('ag-input');
        this.eInput.style.width = '100%';
        const v = (p.value || '').toString().trim();
        if (/^\\d{4}-\\d{2}-\\d{2}$/.test(v)) { this.eInput.value = v; }
        else {
          const d = new Date(v);
          if (!isNaN(d.getTime())){
            const pad=n=>String(n).padStart(2,'0');
            this.eInput.value = d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
          }
        }
      }
      getGui(){ return this.eInput }
      afterGuiAttached(){ this.eInput.focus() }
      getValue(){ return this.eInput.value }
    }""")

    # Sí/No con emoji (seguro) + color por cellStyle
    si_no_formatter = JsCode("""
    function(p){
      const v = String(p.value || '');
      const M = {"Sí":"✅ Sí","No":"✖️ No","":"—"};
      return M[v] || v;
    }""")

    # ✅ estilo centrado vertical/horizontal y “pill” compacto
    si_no_style_genero = JsCode("""
    function(p){
      const base = {
        display:'flex', alignItems:'center', justifyContent:'center',
        height:'100%', padding:'0 10px', borderRadius:'12px',
        fontWeight:'600', textAlign:'center'
      };
      const v = String(p.value || '');
      if (v === 'Sí') return Object.assign({}, base, {backgroundColor:'#FFF3E0', color:'#E65100'});
      if (v === 'No') return Object.assign({}, base, {backgroundColor:'#ECEFF1', color:'#37474F'});
      return {};
    }""")

    si_no_style_corrigio = JsCode("""
    function(p){
      const base = {
        display:'flex', alignItems:'center', justifyContent:'center',
        height:'100%', padding:'0 10px', borderRadius:'12px',
        fontWeight:'600', textAlign:'center'
      };
      const v = String(p.value || '');
      if (v === 'Sí') return Object.assign({}, base, {backgroundColor:'#E8F5E9', color:'#1B5E20'});
      if (v === 'No') return Object.assign({}, base, {backgroundColor:'#FFE0E0', color:'#B71C1C'});
      return {};
    }""")

    # al cambiar fecha, poner hora actual correspondiente
    on_cell_changed = JsCode("""
    function(params){
      const pad = n => String(n).padStart(2,'0');
      const now = new Date(); const hhmm = pad(now.getHours())+':'+pad(now.getMinutes());
      if (params.colDef.field === 'Fecha de detección'){
        params.node.setDataValue('Hora de detección', hhmm);
      }
      if (params.colDef.field === 'Fecha de corrección'){
        params.node.setDataValue('Hora de corrección', hhmm);
      }
    }""")

    # autosize para ocupar todo el ancho
    on_ready_size = JsCode("function(p){ p.api.sizeColumnsToFit(); }")
    on_first_size = JsCode("function(p){ p.api.sizeColumnsToFit(); }")

    # ColumnDefs SIEMPRE visibles
    col_defs = [
        {"field":"Id", "headerName":"Id", "editable": False, "pinned":"left", "flex":1.2, "minWidth":110},
        {"field":"Tarea", "headerName":"Tarea", "editable": False, "flex":3, "minWidth":200,
         "cellStyle": {"whiteSpace":"nowrap", "overflow":"hidden", "textOverflow":"ellipsis"}},

        {"field":"¿Generó alerta?", "headerName":"¿Generó alerta?",
         "editable": True,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": ["No","Sí"]},
         "valueFormatter": si_no_formatter,
         "cellStyle": si_no_style_genero,
         "flex":1.2, "minWidth":140},

        {"field":"N° alerta", "headerName":"N° alerta",
         "editable": True,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": ["1","2","3","+4"]},
         "flex":0.8, "minWidth":120},

        {"field":"Fecha de detección", "headerName":"Fecha de detección",
         "editable": True, "cellEditor": date_editor, "flex":1.2, "minWidth":150},

        {"field":"Hora de detección", "headerName":"Hora de detección",
         "editable": False, "flex":1.0, "minWidth":140},

        {"field":"¿Se corrigió?", "headerName":"¿Se corrigió?",
         "editable": True,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": ["No","Sí"]},
         "valueFormatter": si_no_formatter,
         "cellStyle": si_no_style_corrigio,
         "flex":1.2, "minWidth":140},

        {"field":"Fecha de corrección", "headerName":"Fecha de corrección",
         "editable": True, "cellEditor": date_editor, "flex":1.2, "minWidth":150},

        {"field":"Hora de corrección", "headerName":"Hora de corrección",
         "editable": False, "flex":1.0, "minWidth":140},
    ]

    grid_opts = {
        "columnDefs": col_defs,
        "defaultColDef": {
            "resizable": True,
            "wrapText": False,      # una sola línea
            "autoHeight": False,    # evita crecer por contenido
            "minWidth": 110,
            "flex": 1
        },
        "suppressMovableColumns": True,
        "domLayout": "normal",
        "ensureDomOrder": True,
        "rowHeight": 38,           # ⬅️ altura de celdas ligeramente mayor
        "headerHeight": 36,        # encabezado compacto (sin cambios en títulos)
        "suppressHorizontalScroll": True,
        "onCellValueChanged": on_cell_changed,
        "onGridReady": on_ready_size,
        "onFirstDataRendered": on_first_size,
    }

    grid = AgGrid(
        df_view,
        gridOptions=grid_opts,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=False,   # autosize en callbacks
        enable_enterprise_modules=False,
        reload_data=False,
        height=220,
        allow_unsafe_jscode=True,
        theme="balham",
    )

    # ===== Guardar (merge por Id en df_main) =====
    _sp, _btn = st.columns([A+Fw+T_width+D+R, C], gap="medium")
    with _btn:
        if st.button("💾 Guardar cambios", use_container_width=True):
            try:
                df_edit = pd.DataFrame(grid["data"]).copy()
                df_base = st.session_state["df_main"].copy()

                cambios = 0
                for _, row in df_edit.iterrows():
                    id_row = str(row.get("Id","")).strip()
                    if not id_row:
                        continue
                    m = df_base["Id"].astype(str).str.strip() == id_row
                    if not m.any():
                        continue

                    def _set(col_base, val):
                        v = "" if val is None else str(val).strip()
                        if v != "":
                            df_base.loc[m, col_base] = v
                            return 1
                        return 0

                    cambios += _set("¿Generó alerta?",     row.get("¿Generó alerta?"))
                    cambios += _set("N° alerta",           row.get("N° alerta"))
                    cambios += _set("Fecha de detección",  row.get("Fecha de detección"))
                    cambios += _set("Hora de detección",   row.get("Hora de detección"))
                    cambios += _set("¿Se corrigió?",       row.get("¿Se corrigió?"))
                    cambios += _set("Fecha de corrección", row.get("Fecha de corrección"))
                    cambios += _set("Hora de corrección",  row.get("Hora de corrección"))

                if cambios > 0:
                    st.session_state["df_main"] = df_base.copy()
                    _save_local(df_base.copy())
                    st.success(f"✔ Cambios guardados: {cambios} actualización(es).")
                else:
                    st.info("No se detectaron cambios para guardar.")
            except Exception as e:
                st.error(f"No pude guardar los cambios: {e}")

    # Cierra form-card + section-na y el contenedor local
    st.markdown('</div></div>', unsafe_allow_html=True)  # cierra .form-card y .section-na
    st.markdown('</div>', unsafe_allow_html=True)        # cierra #na-section

    # Separación vertical entre secciones
    st.markdown(f"<div style='height:{SECTION_GAP}px'></div>", unsafe_allow_html=True)


# =========================== PRIORIDAD ===============================

st.session_state.setdefault("pri_visible", True)
chev_pri = "▾" if st.session_state["pri_visible"] else "▸"

# ---------- Barra superior ----------
st.markdown('<div class="topbar-pri">', unsafe_allow_html=True)
c_toggle_p, c_pill_p = st.columns([0.028, 0.965], gap="medium")
with c_toggle_p:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_pri():
        st.session_state["pri_visible"] = not st.session_state["pri_visible"]
    st.button(chev_pri, key="pri_toggle_v2", help="Mostrar/ocultar", on_click=_toggle_pri)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill_p:
    st.markdown('<div class="form-title-pri">🧭&nbsp;&nbsp;Prioridad</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["pri_visible"]:

    # --- contenedor local + css ---
    st.markdown('<div id="pri-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #pri-section .stButton > button { width: 100% !important; }
      .section-pri .help-strip-pri + .form-card{ margin-top: 6px !important; }

      /* Header visible (altura fija) */
      #pri-section .ag-theme-alpine .ag-header,
      #pri-section .ag-theme-streamlit .ag-header{
        height: 44px !important; min-height: 44px !important;
      }

      /* ===== Encabezados más livianos ===== */
      /* Reducimos el peso tipográfico en ambos temas y evitamos "fake bold" */
      #pri-section .ag-theme-alpine{ --ag-font-weight: 400; }
      #pri-section .ag-theme-streamlit{ --ag-font-weight: 400; }

      #pri-section .ag-theme-alpine .ag-header-cell-label,
      #pri-section .ag-theme-alpine .ag-header-cell-text,
      #pri-section .ag-theme-alpine .ag-header *:not(.ag-icon),
      #pri-section .ag-theme-streamlit .ag-header-cell-label,
      #pri-section .ag-theme-streamlit .ag-header-cell-text,
      #pri-section .ag-theme-streamlit .ag-header *:not(.ag-icon){
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Inter", "Helvetica Neue", Arial, sans-serif !important;
        font-weight: 100 !important;              /* Regular */
        font-synthesis-weight: none !important;   /* sin negrita sintética */
        color: #1f2937 !important;
        opacity: 1 !important;
        visibility: visible !important;
      }

      /* Colores para prioridad (por clase) */
      #pri-section .pri-low   { color:#2563eb !important; }  /* 🔵 Baja */
      #pri-section .pri-med   { color:#ca8a04 !important; }  /* 🟡 Media */
      #pri-section .pri-high  { color:#dc2626 !important; }  /* 🔴 Alta */
    </style>
    """, unsafe_allow_html=True)


    # ===== Wrapper UNIDO: help-strip + form-card =====
    st.markdown("""
    <div class="section-pri">
      <div class="help-strip help-strip-pri" id="pri-help">
        🧭 <strong>Asigna o edita prioridades</strong> para varias tareas a la vez (solo jefatura)
      </div>
      <div class="form-card">
    """, unsafe_allow_html=True)

    # Proporciones
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
    if df_all.empty:
        df_all = pd.DataFrame(columns=["Id","Área","Fase","Responsable","Tarea","Fecha inicio"])

    # Asegurar columna Prioridad con default Media
    if "Prioridad" not in df_all.columns:
        df_all["Prioridad"] = "Media"
    df_all["Prioridad"] = df_all["Prioridad"].fillna("Media").replace({"": "Media"})

    # ===== FILTROS =====
    with st.form("pri_filtros_v2", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

        AREAS_OPC = st.session_state.get(
            "AREAS_OPC",
            ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
        )
        pri_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0, key="pri_area")

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        pri_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="pri_fase")

        # Multiselección de responsables
        df_resp_src = df_all.copy()
        if pri_area != "Todas":
            df_resp_src = df_resp_src[df_resp_src.get("Área","").astype(str) == pri_area]
        if pri_fase != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == pri_fase]

        responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        pri_resp = c_resp.multiselect("Responsable", options=responsables_all, default=[], placeholder="Selecciona responsable(s)")

        pri_desde = c_desde.date_input("Desde", value=None, key="pri_desde")
        pri_hasta = c_hasta.date_input("Hasta",  value=None, key="pri_hasta")

        with c_buscar:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            pri_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado para la tabla =====
    df_filtrado = df_all.copy()
    if pri_do_buscar:
        if pri_area != "Todas":
            df_filtrado = df_filtrado[df_filtrado.get("Área","").astype(str) == pri_area]
        if pri_fase != "Todas" and "Fase" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == pri_fase]
        if pri_resp:
            df_filtrado = df_filtrado[df_filtrado.get("Responsable","").astype(str).isin(pri_resp)]

        base_fecha_col = "Fecha inicio" if "Fecha inicio" in df_filtrado.columns else None
        if base_fecha_col:
            fcol = pd.to_datetime(df_filtrado[base_fecha_col], errors="coerce")
            if pri_desde:
                df_filtrado = df_filtrado[fcol >= pd.to_datetime(pri_desde)]
            if pri_hasta:
                df_filtrado = df_filtrado[fcol <= (pd.to_datetime(pri_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    st.markdown("**Resultados**")

    # ===== DataFrame para la grilla (con columnas aunque esté vacío) =====
    cols_out = ["Id", "Responsable", "Tarea", "Prioridad actual", "Prioridad a ajustar"]
    if df_filtrado.empty:
        df_view = pd.DataFrame({c: pd.Series(dtype="str") for c in cols_out})
    else:
        tmp = df_filtrado.copy()
        for need in ["Id","Responsable","Tarea","Prioridad"]:
            if need not in tmp.columns:
                tmp[need] = ""
        prior_actual = tmp["Prioridad"].fillna("Media").replace({"": "Media"})
        df_view = pd.DataFrame({
            "Id": tmp["Id"].astype(str),
            "Responsable": tmp["Responsable"].astype(str).replace({"nan": ""}),
            "Tarea": tmp["Tarea"].astype(str).replace({"nan": ""}),
            "Prioridad actual": prior_actual.astype(str),
            "Prioridad a ajustar": prior_actual.astype(str)
        })[cols_out].copy()

    # ====== AG-GRID con columnDefs explícitos (muestra encabezados aunque no haya filas) ======
    from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode

    PRI_OPC_SHOW = ["🔵 Baja","🟡 Media","🔴 Alta"]
    PRI_MAP_TO_TEXT = {"🔵 Baja":"Baja","🟡 Media":"Media","🔴 Alta":"Alta",
                       "Baja":"Baja","Media":"Media","Alta":"Alta"}

    # Reglas de color sin JS (expresiones)
    cell_class_rules = {
        "pri-low":  "value == '🔵 Baja' || value == 'Baja'",
        "pri-med":  "value == '🟡 Media' || value == 'Media'",
        "pri-high": "value == '🔴 Alta' || value == 'Alta'",
    }

    col_defs = [
        {"field":"Id", "headerName":"ID", "editable": False, "flex":1.0, "minWidth":110},
        {"field":"Responsable", "headerName":"Responsable", "editable": False, "flex":1.6, "minWidth":160},
        {"field":"Tarea", "headerName":"Tarea", "editable": False, "flex":2.4, "minWidth":240,
         "wrapText": True, "autoHeight": True},
        {"field":"Prioridad actual", "headerName":"Prioridad actual", "editable": False,
         "flex":1.2, "minWidth":160, "cellClassRules": cell_class_rules},
        {"field":"Prioridad a ajustar", "headerName":"Prioridad a ajustar", "editable": True,
         "cellEditor":"agSelectCellEditor", "cellEditorParams":{"values": PRI_OPC_SHOW},
         "flex":1.2, "minWidth":180, "cellClassRules": cell_class_rules},
    ]

    grid_opts = {
        "columnDefs": col_defs,
        "defaultColDef": {
            "resizable": True,
            "wrapText": True,
            "autoHeight": True,
            "minWidth": 120,
            "flex": 1
        },
        "suppressMovableColumns": True,
        "domLayout": "normal",
        "ensureDomOrder": True,
        "rowHeight": 38,
        "headerHeight": 44,
        "suppressHorizontalScroll": True
    }

    # --- Encabezado más liviano DENTRO del iframe (clave) ---
    custom_css_pri = {
        ".ag-header-cell-text": {"font-weight": "600 !important"},
        ".ag-header-group-cell-label": {"font-weight": "600 !important"},
        ".ag-header-cell-label": {"font-weight": "600 !important"},
        ".ag-header": {"font-weight": "600 !important"},
    }

    grid_pri = AgGrid(
        df_view,
        gridOptions=grid_opts,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=False,   # las columnas llenan por flex
        enable_enterprise_modules=False,
        reload_data=False,
        height=220,
        theme="alpine",
        custom_css=custom_css_pri,        # <<--- ajuste que reduce la “negrita”
    )

    # ===== Guardar (actualiza Prioridad en df_main) =====
    _sp_pri, _btn_pri = st.columns([A+Fw+T_width+D+R, C], gap="medium")
    with _btn_pri:
        do_save_pri = st.button("🧭 Dar prioridad", use_container_width=True)

    if do_save_pri:
        try:
            edited = pd.DataFrame(grid_pri.get("data", []))
            if edited.empty:
                st.info("No hay filas para actualizar.")
            else:
                df_base = st.session_state.get("df_main", pd.DataFrame()).copy()
                cambios = 0
                for _, row in edited.iterrows():
                    id_row = str(row.get("Id", "")).strip()
                    if not id_row:
                        continue
                    valor_ui = str(row.get("Prioridad a ajustar", "Media")).strip()
                    nuevo = PRI_MAP_TO_TEXT.get(valor_ui, "Media")  # guardamos sin emoji
                    m = df_base["Id"].astype(str).str.strip() == id_row
                    if m.any():
                        df_base.loc[m, "Prioridad"] = nuevo
                        cambios += 1
                if cambios > 0:
                    st.session_state["df_main"] = df_base.copy()
                    _save_local(df_base.copy())
                    st.success(f"✔ Prioridades actualizadas: {cambios} fila(s).")
                else:
                    st.info("No se detectaron cambios para guardar.")
        except Exception as e:
            st.error(f"No pude guardar los cambios de prioridad: {e}")

    # Cerrar wrappers
    st.markdown('</div></div>', unsafe_allow_html=True)  # cierra .form-card y .section-pri
    st.markdown('</div>', unsafe_allow_html=True)        # cierra #pri-section

    # Separación vertical
    st.markdown(f"<div style='height:{SECTION_GAP}px'></div>", unsafe_allow_html=True)



# =========================== EVALUACIÓN ===============================
st.session_state.setdefault("eva_visible", True)
chev_eva = "▾" if st.session_state["eva_visible"] else "▸"

# ---------- Barra superior ----------
st.markdown('<div class="topbar-eval">', unsafe_allow_html=True)
c_toggle_e, c_pill_e = st.columns([0.028, 0.965], gap="medium")
with c_toggle_e:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_eva():
        st.session_state["eva_visible"] = not st.session_state["eva_visible"]
    st.button(chev_eva, key="eva_toggle_v2", help="Mostrar/ocultar", on_click=_toggle_eva)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill_e:
    st.markdown('<div class="form-title-eval">📝&nbsp;&nbsp;Evaluación</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["eva_visible"]:

    # --- contenedor local + css (botón, headers 600, colores y estrellas) ---
    st.markdown('<div id="eva-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #eva-section .stButton > button { width: 100% !important; }
      .section-eva .help-strip-eval + .form-card{ margin-top: 6px !important; }

      /* Esta regla NO afecta al iframe, se deja como respaldo visual fuera del grid */
      #eva-section .ag-header .ag-header-cell-text{
        font-weight: 600 !important;
      }

      /* Colorear celdas por estado (fuera del iframe; dentro lo hacemos con custom_css_eval) */
      #eva-section .eva-ok  { color:#16a34a !important; }
      #eva-section .eva-bad { color:#dc2626 !important; }
      #eva-section .eva-obs { color:#d97706 !important; }

      /* Estrellas (fuera del iframe; dentro lo hacemos con custom_css_eval) */
      #eva-section .ag-star{
        cursor: pointer; user-select: none;
        font-size: 16px; line-height: 1; margin: 0 1px;
      }
      #eva-section .ag-star.on  { color: #fbbf24; }
      #eva-section .ag-star.off { color: #9ca3af; }
    </style>
    """, unsafe_allow_html=True)

    # ===== Wrapper UNIDO: help-strip + form-card =====
    st.markdown("""
    <div class="section-eva">
      <div class="help-strip help-strip-eval" id="eva-help">
        📝 <strong>Registra/actualiza la evaluación</strong> de tareas filtradas.
      </div>
      <div class="form-card">
    """, unsafe_allow_html=True)

    # Anchos calcados a las otras secciones
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    df_all = st.session_state["df_main"].copy()

    # Asegura columnas base
    if "Evaluación" not in df_all.columns:
        df_all["Evaluación"] = "Sin evaluar"
    if "Calificación" not in df_all.columns:
        df_all["Calificación"] = 0

    # ===== FILTROS (misma fila estándar) =====
    with st.form("eva_filtros_v2", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

        AREAS_OPC = st.session_state.get(
            "AREAS_OPC",
            ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
        )
        eva_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0, key="eva_area")

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        eva_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="eva_fase")

        # --- Responsable como MULTISELECCIÓN ---
        df_resp_src = df_all.copy()
        if eva_area != "Todas":
            df_resp_src = df_resp_src[df_resp_src.get("Área","").astype(str) == eva_area]
        if eva_fase != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == eva_fase]
        responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        eva_resp = c_resp.multiselect("Responsable", options=responsables_all, default=[], placeholder="Selecciona responsable(s)")

        eva_desde = c_desde.date_input("Desde", value=None, key="eva_desde")
        eva_hasta = c_hasta.date_input("Hasta",  value=None, key="eva_hasta")

        with c_buscar:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            eva_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado para tabla =====
    df_filtrado = df_all.copy()
    if eva_do_buscar:
        if eva_area != "Todas":
            df_filtrado = df_filtrado[df_filtrado.get("Área","").astype(str) == eva_area]
        if eva_fase != "Todas" and "Fase" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == eva_fase]
        if eva_resp:  # lista no vacía
            df_filtrado = df_filtrado[df_filtrado.get("Responsable","").astype(str).isin(eva_resp)]

        base_fecha_col = "Fecha inicio" if "Fecha inicio" in df_filtrado.columns else None
        if base_fecha_col:
            fcol = pd.to_datetime(df_filtrado[base_fecha_col], errors="coerce")
            if eva_desde:
                df_filtrado = df_filtrado[fcol >= pd.to_datetime(eva_desde)]
            if eva_hasta:
                df_filtrado = df_filtrado[fcol <= (pd.to_datetime(eva_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    # ===== Tabla de Evaluación =====
    st.markdown("**Resultados**")

    # Mapeos de evaluación (con/sin emoji)
    EVA_OPC_SHOW = ["Sin evaluar", "🟢 Aprobado", "🔴 Desaprobado", "🟠 Observado"]
    EVA_TO_TEXT = {
        "🟢 Aprobado": "Aprobado", "🔴 Desaprobado": "Desaprobado", "🟠 Observado": "Observado",
        "Aprobado":"Aprobado","Desaprobado":"Desaprobado","Observado":"Observado",
        "Sin evaluar":"Sin evaluar","":"Sin evaluar"
    }
    TEXT_TO_SHOW = {"Aprobado":"🟢 Aprobado","Desaprobado":"🔴 Desaprobado","Observado":"🟠 Observado","Sin evaluar":"Sin evaluar"}

    cols_out = ["Id", "Responsable", "Tarea", "Evaluación actual", "Evaluación ajustada", "Calificación"]
    df_view = pd.DataFrame(columns=cols_out)
    if not df_filtrado.empty:
        tmp = df_filtrado.dropna(subset=["Id"]).copy()
        for need in ["Responsable","Tarea","Evaluación","Calificación"]:
            if need not in tmp.columns:
                tmp[need] = ""
        eva_actual_txt = tmp["Evaluación"].fillna("Sin evaluar").replace({"": "Sin evaluar"}).astype(str)
        eva_ajustada_show = eva_actual_txt.apply(lambda v: TEXT_TO_SHOW.get(v, "Sin evaluar"))

        calif = pd.to_numeric(tmp.get("Calificación", 0), errors="coerce").fillna(0).astype(int)
        calif = calif.clip(lower=0, upper=5)

        df_view = pd.DataFrame({
            "Id": tmp["Id"].astype(str),
            "Responsable": tmp["Responsable"].astype(str).replace({"nan": ""}),
            "Tarea": tmp["Tarea"].astype(str).replace({"nan": ""}),
            "Evaluación actual": eva_actual_txt,
            "Evaluación ajustada": eva_ajustada_show,   # arranca con el valor actual (con emoji)
            "Calificación": calif                        # conserva lo guardado (por defecto 0)
        })[cols_out].copy()

    from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

    # CellClassRules para colorear ambas columnas de evaluación
    eva_cell_rules = {
        "eva-ok":  "value == '🟢 Aprobado' || value == 'Aprobado'",
        "eva-bad": "value == '🔴 Desaprobado' || value == 'Desaprobado'",
        "eva-obs": "value == '🟠 Observado' || value == 'Observado'",
    }

    # Renderer de estrellas clicables (actualiza el valor numérico 1..5 en la celda)
    star_renderer = JsCode("""
        function(params){
            var v = parseInt(params.value);
            if (isNaN(v)) v = 0;
            v = Math.max(0, Math.min(5, v));

            var container = document.createElement('div');
            for (let i=1; i<=5; i++){
                var s = document.createElement('span');
                s.className = 'ag-star ' + (i<=v ? 'on' : 'off');
                s.textContent = '★';
                s.setAttribute('data-v', i);
                s.addEventListener('click', function(e){
                    var nv = parseInt(e.target.getAttribute('data-v'));
                    if (!isNaN(nv)){
                        params.node.setDataValue(params.colDef.field, nv);
                    }
                });
                container.appendChild(s);
            }
            return container;
        }
    """)

    gob = GridOptionsBuilder.from_dataframe(df_view)
    gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True, minWidth=120, flex=1)
    gob.configure_grid_options(
        suppressMovableColumns=True, domLayout="normal", ensureDomOrder=True,
        rowHeight=38, headerHeight=44, suppressHorizontalScroll=True
    )

    # Lectura
    for ro in ["Id", "Responsable", "Tarea", "Evaluación actual"]:
        gob.configure_column(ro, editable=False, cellClassRules=eva_cell_rules if ro=="Evaluación actual" else None)

    # Editable: Evaluación ajustada (combo con emojis) + colores
    gob.configure_column(
        "Evaluación ajustada",
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": EVA_OPC_SHOW},
        cellClassRules=eva_cell_rules,
        flex=1.4, minWidth=180
    )

    # Editable: Calificación con estrellas clicables (0..5)
    gob.configure_column(
        "Calificación",
        editable=True,
        cellRenderer=star_renderer,
        flex=1.1, minWidth=160
    )

    # Ajuste de flex para ocupar todo el ancho cómodamente
    gob.configure_column("Id",            flex=1.0, minWidth=110)
    gob.configure_column("Responsable",   flex=1.6, minWidth=160)
    gob.configure_column("Tarea",         flex=2.4, minWidth=260)
    gob.configure_column("Evaluación actual", flex=1.3, minWidth=160)

    # === CSS dentro del iframe de AgGrid (clave para header, colores y estrellas) ===
    custom_css_eval = {
        ".ag-header-cell-text": {"font-weight": "600 !important"},
        ".ag-header-cell-label": {"font-weight": "600 !important"},
        ".ag-header-group-cell-label": {"font-weight": "600 !important"},
        ".ag-theme-alpine": {"--ag-font-weight": "600"},
        ".ag-header": {"font-synthesis-weight": "none !important"},

        # Colores de estado dentro del iframe
        ".eva-ok":  {"color": "#16a34a !important"},
        ".eva-bad": {"color": "#dc2626 !important"},
        ".eva-obs": {"color": "#d97706 !important"},

        # Estrellas dentro del iframe
        ".ag-star":     {"cursor":"pointer", "user-select":"none", "font-size":"16px", "line-height":"1", "margin":"0 1px"},
        ".ag-star.on":  {"color":"#fbbf24"},
        ".ag-star.off": {"color":"#9ca3af"},
    }

    grid_eval = AgGrid(
        df_view,
        gridOptions=gob.build(),
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=False,   # usamos flex
        enable_enterprise_modules=False,
        allow_unsafe_jscode=True,
        reload_data=False,
        theme="alpine",
        height=300,
        custom_css=custom_css_eval  # <<--- AQUI aplicamos estilos dentro del iframe
    )

    # ===== Guardar cambios =====
    _sp_e, _btn_e = st.columns([A+Fw+T_width+D+R, C], gap="medium")
    with _btn_e:
        do_save_eval = st.button("✅ Evaluar", use_container_width=True)

    if do_save_eval:
        try:
            edited = pd.DataFrame(grid_eval["data"]).copy()
            if edited.empty:
                st.info("No hay filas para actualizar.")
            else:
                df_base = st.session_state["df_main"].copy()
                cambios = 0
                for _, row in edited.iterrows():
                    id_row = str(row.get("Id", "")).strip()
                    if not id_row:
                        continue

                    eva_new_raw = str(row.get("Evaluación ajustada", "")).strip()
                    eva_new = EVA_TO_TEXT.get(eva_new_raw, "Sin evaluar")

                    cal_new = row.get("Calificación", 0)
                    try:
                        cal_new = int(cal_new)
                    except Exception:
                        cal_new = 0
                    cal_new = max(0, min(5, cal_new))

                    m = df_base["Id"].astype(str).str.strip() == id_row
                    if not m.any():
                        continue

                    # Actualiza evaluación y calificación (persisten para el siguiente ajuste)
                    if eva_new:
                        df_base.loc[m, "Evaluación"] = eva_new
                        cambios += 1
                    df_base.loc[m, "Calificación"] = cal_new
                    cambios += 1

                if cambios > 0:
                    st.session_state["df_main"] = df_base.copy()
                    _save_local(df_base.copy())
                    st.success(f"✔ Evaluaciones actualizadas: {cambios} cambio(s).")
                else:
                    st.info("No se detectaron cambios para guardar.")
        except Exception as e:
            st.error(f"No pude guardar las evaluaciones: {e}")

    # Cierra form-card + section-eva y el contenedor local
    st.markdown('</div></div>', unsafe_allow_html=True)  # cierra .form-card y .section-eva
    st.markdown('</div>', unsafe_allow_html=True)        # cierra #eva-section

    # Separación vertical entre secciones
    st.markdown(f"<div style='height:{SECTION_GAP}px'></div>", unsafe_allow_html=True)



# ================== Historial ==================

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
st.subheader("📝 Tareas recientes")
st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# Base completa sin filtrar para poblar combos
df_all = st.session_state["df_main"].copy()
df_view = df_all.copy()

# ===== Proporciones de filtros (alineadas al resto de secciones) =====
A_f, Fw_f, T_width_f, D_f, R_f, C_f = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

# ===== FILA DE 5 FILTROS + Buscar =====
with st.form("hist_filtros_v1", clear_on_submit=False):
    cA, cF, cR, cD, cH, cB = st.columns([A_f, Fw_f, T_width_f, D_f, R_f, C_f], gap="medium")

    # Área
    area_sel = cA.selectbox("Área", options=["Todas"] + st.session_state.get(
        "AREAS_OPC",
        ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
    ), index=0, key="hist_area")

    # Fase (de lo que exista en la base)
    fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
    fase_sel = cF.selectbox("Fase", options=["Todas"] + fases_all, index=0, key="hist_fase")

    # Responsable (depende de Área/Fase si se eligieron)
    df_resp_src = df_all.copy()
    if area_sel != "Todas":
        df_resp_src = df_resp_src[df_resp_src["Área"] == area_sel]
    if fase_sel != "Todas" and "Fase" in df_resp_src.columns:
        df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == fase_sel]
    responsables = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
    resp_sel = cR.selectbox("Responsable", options=["Todos"] + responsables, index=0, key="hist_resp")

    # Rango de fechas (Fecha inicio)
    f_desde = cD.date_input("Desde", value=None, key="hist_desde")
    f_hasta = cH.date_input("Hasta",  value=None, key="hist_hasta")

    with cB:
        st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
        hist_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

# ---- Aplicar filtros sobre df_view SOLO si se presiona Buscar ----
df_view["Fecha inicio"] = pd.to_datetime(df_view.get("Fecha inicio"), errors="coerce")

if hist_do_buscar:
    if area_sel != "Todas":
        df_view = df_view[df_view["Área"] == area_sel]
    if fase_sel != "Todas" and "Fase" in df_view.columns:
        df_view = df_view[df_view["Fase"].astype(str) == fase_sel]
    if resp_sel != "Todos":
        df_view = df_view[df_view["Responsable"].astype(str) == resp_sel]
    if f_desde:
        df_view = df_view[df_view["Fecha inicio"].dt.date >= f_desde]
    if f_hasta:
        df_view = df_view[df_view["Fecha inicio"].dt.date <= f_hasta]

# ===== ORDENAR POR RECIENTES (fallback a Fecha inicio) =====
for c in ["Fecha estado modificado", "Fecha estado actual", "Fecha inicio"]:
    if c not in df_view.columns:
        df_view[c] = pd.NaT

ts_mod = pd.to_datetime(df_view["Fecha estado modificado"], errors="coerce")
ts_act = pd.to_datetime(df_view["Fecha estado actual"], errors="coerce")
ts_ini = pd.to_datetime(df_view["Fecha inicio"], errors="coerce")

df_view["__ts__"] = ts_mod.combine_first(ts_act).combine_first(ts_ini)
df_view = df_view.sort_values("__ts__", ascending=False, na_position="last")

st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)

# --- FIX: eliminar columnas duplicadas antes de ordenar/reindex ---
df_view = df_view.copy()
df_view.columns = df_view.columns.astype(str)
dups = df_view.columns.duplicated()
if dups.any():
    df_view = df_view.loc[:, ~dups]

# ===== Semántica de tiempos / estado =====
# 1) Estado actual: si existe "Estado modificado" (texto) úsalo para sobrescribir "Estado"
if "Estado modificado" in df_view.columns:
    _em = df_view["Estado modificado"].astype(str).str.strip()
    mask_em = _em.notna() & _em.ne("") & _em.ne("nan")
    if "Estado" not in df_view.columns:
        df_view["Estado"] = ""
    df_view.loc[mask_em, "Estado"] = _em[mask_em]

# 2) Registro (solo para NO INICIADO). NO inventar horas 00:00 ni rellenar con fechas de otros campos.
if "Fecha Registro" not in df_view.columns: df_view["Fecha Registro"] = pd.NaT
if "Hora Registro"   not in df_view.columns: df_view["Hora Registro"]   = ""

if "Estado" in df_view.columns:
    mask_no_ini = df_view["Estado"].astype(str) == "No iniciado"
    # Si alguien quedó con "00:00" o "00:00:00", muéstralo como vacío (—)
    hora_raw = df_view["Hora Registro"].astype(str).str.strip().fillna("")
    mask_hora_cero = hora_raw.eq("00:00") | hora_raw.eq("00:00:00")
    df_view.loc[mask_no_ini & mask_hora_cero, "Hora Registro"] = ""

# 3) Inicio: solo cuando Estado = En curso (desde Fecha estado modificado); caso contrario, vaciar
if "Hora de inicio" not in df_view.columns: df_view["Hora de inicio"] = ""
if "Estado" in df_view.columns:
    _mod = pd.to_datetime(df_view.get("Fecha estado modificado"), errors="coerce")
    _en_curso = df_view["Estado"].astype(str) == "En curso"
    df_view.loc[_en_curso, "Fecha inicio"]   = _mod
    df_view.loc[_en_curso, "Hora de inicio"] = _mod.dt.strftime("%H:%M")
    df_view.loc[~_en_curso, "Fecha inicio"] = pd.NaT
    df_view.loc[~_en_curso, "Hora de inicio"] = ""

# === ORDEN Y PRESENCIA DE COLUMNAS SEGÚN TU LISTA ===
target_cols = [
    "Id","Área","Fase","Responsable",
    "Tarea","Detalle","Ciclo de mejora","Complejidad","Prioridad",
    "Estado",                      # → header: "Estado actual"
    "Duración",                    # vacío por ahora
    "Fecha Registro","Hora Registro",
    "Fecha inicio","Hora de inicio",   # → header: "Fecha de inicio"
    "Fecha Pausado","Hora Pausado",
    "Fecha Cancelado","Hora Cancelado",
    "Fecha Eliminado","Hora Eliminado",
    "Vencimiento",                    # → header: "Fecha límite"
    "Fecha fin","Hora Terminado",     # → header: "Fecha Terminado"
    "¿Generó alerta?","N° de alerta","Fecha de detección","Hora de detección",
    "¿Se corrigió?","Fecha de corrección","Hora de corrección",
    "Cumplimiento","Evaluación","Calificación"
]

# Columnas internas NO visibles en el grid
HIDDEN_COLS = [
    "Estado modificado",            # ← ocultar columna textual
    "Fecha estado modificado","Hora estado modificado",
    "Fecha estado actual","Hora estado actual",
    "__ts__","__DEL__"
]

# Asegura presencia de columnas (si faltan, se crean vacías)
for c in target_cols:
    if c not in df_view.columns:
        df_view[c] = ""

# Duración: mantener vacía
df_view["Duración"] = df_view["Duración"].astype(str).fillna("")

# Reindex (sin duplicados y excluyendo ocultas)
target_cols_u = list(dict.fromkeys(target_cols))
rest = [c for c in df_view.columns if c not in target_cols_u + HIDDEN_COLS]
df_grid = df_view.reindex(columns=target_cols_u + rest).copy()
df_grid = df_grid.loc[:, ~df_grid.columns.duplicated()].copy()

# Forzar Id a string
df_grid["Id"] = df_grid["Id"].astype(str).fillna("")

# ================= GRID OPTIONS =================
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

gob = GridOptionsBuilder.from_dataframe(df_grid)
gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True)

gob.configure_grid_options(
    rowSelection="multiple",
    rowMultiSelectWithClick=True,
    suppressRowClickSelection=False,
    rememberSelection=True,
    domLayout="normal",
    rowHeight=32,            # ← más delgado
    headerHeight=42,
    enableRangeSelection=True,
    enableCellTextSelection=True,
    singleClickEdit=True,
    stopEditingWhenCellsLoseFocus=True,
    undoRedoCellEditing=True,
    enterMovesDown=True,
    suppressMovableColumns=False,
    getRowId=JsCode("function(p){ return (p.data && (p.data.Id || p.data['Id'])) + ''; }"),
)

# ----- Fijas a la izquierda (inmovibles) -----
gob.configure_column("Id",
    headerName="ID",
    editable=False, width=110, pinned="left",
    checkboxSelection=True,
    headerCheckboxSelection=True,
    headerCheckboxSelectionFilteredOnly=True,
    suppressMovable=True
)
gob.configure_column("Área",        editable=True,  width=160, pinned="left", suppressMovable=True)
gob.configure_column("Fase",        editable=True,  width=140, pinned="left", suppressMovable=True)
gob.configure_column("Responsable", editable=True,  minWidth=180, pinned="left", suppressMovable=True)

# ----- Alias de encabezados -----
gob.configure_column("Estado",        headerName="Estado actual")
gob.configure_column("Vencimiento",   headerName="Fecha límite")
gob.configure_column("Fecha inicio",  headerName="Fecha de inicio")
gob.configure_column("Fecha fin",     headerName="Fecha Terminado")

# ----- Ocultas en GRID -----
for ocultar in HIDDEN_COLS + ["Fecha Pausado","Hora Pausado","Fecha Cancelado","Hora Cancelado","Fecha Eliminado","Hora Eliminado"]:
    if ocultar in df_view.columns:
        gob.configure_column(ocultar, hide=True, suppressMenu=True, filter=False)

# ----- Formatters útiles -----
flag_formatter = JsCode("""
function(p){
  const v=String(p.value||'');
  if(v==='Alta') return '🔴 Alta';
  if(v==='Media') return '🟡 Media';
  if(v==='Baja') return '🟢 Baja';
  return v||'—';
}""")

chip_style = JsCode("""
function(p){
  const v = String(p.value || '');
  let bg='#E0E0E0', fg='#FFFFFF';
  if (v==='No iniciado'){bg='#90A4AE'}
  else if(v==='En curso'){bg='#B388FF'}
  else if(v==='Terminado'){bg='#00C4B3'}
  else if(v==='Cancelado'){bg='#FF2D95'}
  else if(v==='Pausado'){bg='#7E57C2'}
  else if(v==='Entregado a tiempo'){bg='#00C4B3'}
  else if(v==='Entregado con retraso'){bg='#00ACC1'}
  else if(v==='No entregado'){bg='#006064'}
  else if(v==='En riesgo de retraso'){bg='#0277BD'}
  else if(v==='Aprobada'){bg:'#8BC34A'; fg='#0A2E00'}
  else if(v==='Desaprobada'){bg:'#FF8A80'}
  else if(v==='Pendiente de revisión'){bg:'#BDBDBD'; fg:'#2B2B2B'}
  else if(v==='Observada'){bg:'#D7A56C'}
  return { backgroundColor:bg, color:fg, fontWeight:'600', textAlign:'center',
           borderRadius:'10px', padding:'4px 10px' };
}""")

fmt_dash = JsCode("""
function(p){
  if(p.value===null||p.value===undefined) return '—';
  const s=String(p.value).trim().toLowerCase();
  if(s===''||s==='nan'||s==='nat'||s==='none'||s==='null') return '—';
  return String(p.value);
}""")

date_time_fmt = JsCode("""
function(p){
  if(p.value===null||p.value===undefined) return '—';
  const d=new Date(String(p.value).trim()); if(isNaN(d.getTime())) return '—';
  const pad=n=>String(n).padStart(2,'0');
  return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes());
}""")

date_only_fmt = JsCode("""
function(p){
  if(p.value===null||p.value===undefined) return '—';
  const d=new Date(String(p.value).trim()); if(isNaN(d.getTime())){
     const s=String(p.value).trim(); if(/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
     return '—';
  }
  const pad=n=>String(n).padStart(2,'0');
  return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
}""")

time_only_fmt = JsCode("""
function(p){
  const v = String(p.value||'').trim();
  if(!v) return '—';
  const m = v.match(/^(\d{1,2}):(\d{2})/);
  if(m) return (m[1].padStart(2,'0')) + ':' + m[2];
  const d = new Date(v);
  if(!isNaN(d.getTime())){
    const pad=n=>String(n).padStart(2,'0');
    return pad(d.getHours())+':'+pad(d.getMinutes());
  }
  return v;
}""")

# ----- Config de columnas (ancho/flex y formatos) -----
colw = {
    "Tarea":260, "Detalle":240, "Ciclo de mejora":140, "Complejidad":130, "Prioridad":130,
    "Estado":130, "Duración":110, "Fecha Registro":160, "Hora Registro":140,
    "Fecha inicio":160, "Hora de inicio":140, "Vencimiento":160,
    "Fecha fin":160, "Hora Terminado":140, "¿Generó alerta?":150, "N° de alerta":140,
    "Fecha de detección":160, "Hora de detección":140, "¿Se corrigió?":140,
    "Fecha de corrección":160, "Hora de corrección":140, "Cumplimiento":180, "Evaluación":170, "Calificación":120
}

for c, fx in [("Tarea",3), ("Detalle",2), ("Ciclo de mejora",1), ("Complejidad",1), ("Prioridad",1), ("Estado",1),
              ("Duración",1), ("Fecha Registro",1), ("Hora Registro",1),
              ("Fecha inicio",1), ("Hora de inicio",1),
              ("Vencimiento",1), ("Fecha fin",1), ("Hora Terminado",1),
              ("¿Generó alerta?",1), ("N° de alerta",1), ("Fecha de detección",1), ("Hora de detección",1),
              ("¿Se corrigió?",1), ("Fecha de corrección",1), ("Hora de corrección",1),
              ("Cumplimiento",1), ("Evaluación",1), ("Calificación",0)]:
    if c in df_grid.columns:
        gob.configure_column(
            c,
            editable=True if c not in ["Duración"] else False,
            minWidth=colw.get(c,120),
            flex=fx,
            valueFormatter=(
                date_only_fmt if c=="Fecha Registro" else
                time_only_fmt if c in ["Hora Registro","Hora de inicio","Hora Pausado","Hora Cancelado","Hora Eliminado",
                                       "Hora Terminado","Hora de detección","Hora de corrección"] else
                date_time_fmt if c in ["Fecha inicio","Vencimiento","Fecha fin","Fecha de detección","Fecha de corrección"] else
                (None if c in ["Calificación","Prioridad"] else fmt_dash)
            ),
            suppressMenu=True if c in ["Fecha Registro","Hora Registro","Fecha inicio","Hora de inicio","Vencimiento","Fecha fin",
                                       "Fecha de detección","Hora de detección","Fecha de corrección","Hora de corrección"] else False,
            filter=False if c in ["Fecha Registro","Hora Registro","Fecha inicio","Hora de inicio","Vencimiento","Fecha fin",
                                  "Fecha de detección","Hora de detección","Fecha de corrección","Hora de corrección"] else None
        )

# Prioridad con banderitas
if "Prioridad" in df_grid.columns:
    gob.configure_column("Prioridad",
        editable=True, cellEditor="agSelectCellEditor",
        cellEditorParams={"values": ["Alta","Media","Baja"]},
        valueFormatter=flag_formatter, minWidth=colw["Prioridad"], maxWidth=220, flex=1
    )

# Chips
for c, vals in [("Cumplimiento", CUMPLIMIENTO),
                ("¿Se corrigió?", SI_NO),
                ("¿Generó alerta?", SI_NO),
                ("Evaluación", ["Aprobada","Desaprobada","Pendiente de revisión","Observada","Cancelada","Pausada"])]:
    if c in df_grid.columns:
        gob.configure_column(c, editable=True, cellEditor="agSelectCellEditor",
                             cellEditorParams={"values": vals},
                             cellStyle=chip_style, valueFormatter=fmt_dash,
                             minWidth=colw.get(c,120), maxWidth=260, flex=1)

# Calificación con estrellas (formato)
if "Calificación" in df_grid.columns:
    gob.configure_column("Calificación", editable=True, valueFormatter=JsCode("""
      function(p){ let n=parseInt(p.value||0); if(isNaN(n)||n<0) n=0; if(n>5) n=5; return '★'.repeat(n)+'☆'.repeat(5-n); }
    """), minWidth=colw["Calificación"], maxWidth=140, flex=0)

# Tooltips
for col in df_grid.columns:
    gob.configure_column(col, headerTooltip=col)

# === Autosize callbacks ===
autosize_on_ready = JsCode("""
function(params){
  const all = params.columnApi.getAllDisplayedColumns();
  params.columnApi.autoSizeColumns(all, true);
}""")
autosize_on_data = JsCode("""
function(params){
  if (params.api && params.api.getDisplayedRowCount() > 0){
    const all = params.columnApi.getAllDisplayedColumns();
    params.columnApi.autoSizeColumns(all, true);
  }
}""")

grid_opts = gob.build()
grid_opts["onGridReady"] = autosize_on_ready.js_code
grid_opts["onFirstDataRendered"] = autosize_on_data.js_code
grid_opts["onColumnEverythingChanged"] = autosize_on_data.js_code

# Recordar selección entre reruns
grid_opts["rowSelection"] = "multiple"
grid_opts["rowMultiSelectWithClick"] = True
grid_opts["rememberSelection"] = True

grid = AgGrid(
    df_grid, key="grid_historial", gridOptions=grid_opts, height=500,
    fit_columns_on_grid_load=False,
    data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
    update_mode=(GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED
                 | GridUpdateMode.FILTERING_CHANGED | GridUpdateMode.SORTING_CHANGED
                 | GridUpdateMode.SELECTION_CHANGED),
    allow_unsafe_jscode=True, theme="balham",
)

# Guarda selección
sel_rows_now = grid.get("selected_rows", []) if isinstance(grid, dict) else []
st.session_state["hist_sel_ids"] = [str((r.get("Id") or r.get("ID") or "")).strip()
                                    for r in sel_rows_now if str((r.get("Id") or r.get("ID") or "")).strip()]

# Sincroniza ediciones por Id
if isinstance(grid, dict) and "data" in grid and grid["data"] is not None and len(grid["data"]) > 0:
    try:
        edited = pd.DataFrame(grid["data"]).copy()
        base = st.session_state["df_main"].copy().set_index("Id")
        st.session_state["df_main"] = base.combine_first(edited.set_index("Id")).reset_index()
    except Exception:
        pass

# ---- Botones ----
total_btn_width = (1.2 + 1.2) + (3.2 / 2)
btn_w = total_btn_width / 4
b_del, b_xlsx, b_save_local, b_save_sheets, _spacer = st.columns(
    [btn_w, btn_w, btn_w, btn_w, (3.2 / 2) + 2.4],
    gap="medium"
)

# 1) Borrar seleccionados
with b_del:
    if st.button("🗑️ Borrar", use_container_width=True):
        sel_rows_now = grid.get("selected_rows", []) if isinstance(grid, dict) else []
        ids = [str((r.get("Id") or r.get("ID") or "")).strip() for r in sel_rows_now
               if str((r.get("Id") or r.get("ID") or "")).strip()]
        if ids:
            df0 = st.session_state["df_main"].copy()
            st.session_state["df_main"] = df0[~df0["Id"].astype(str).isin(ids)].copy()
            st.session_state["hist_sel_ids"] = []
            st.success(f"Eliminadas {len(ids)} fila(s).")
            st.rerun()
        else:
            st.warning("No hay filas seleccionadas.")

# 2) Exportar Excel (respeta orden oficial)
with b_xlsx:
    try:
        df_xlsx = st.session_state["df_main"].copy()
        drop_cols = [c for c in ("__DEL__", "DEL") if c in df_xlsx.columns]
        if drop_cols:
            df_xlsx.drop(columns=drop_cols, inplace=True)
        cols_order = globals().get("COLS_XLSX", []) or target_cols[:]
        cols_order = [c for c in cols_order if c in df_xlsx.columns]
        if cols_order:
            df_xlsx = df_xlsx.reindex(columns=cols_order)
        xlsx_b = export_excel(df_xlsx, sheet_name=TAB_NAME)
        st.download_button(
            "⬇️ Exportar Excel",
            data=xlsx_b,
            file_name="tareas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except ImportError:
        st.error("No pude generar Excel: falta instalar 'xlsxwriter' u 'openpyxl' en el entorno.")
    except Exception as e:
        st.error(f"No pude generar Excel: {e}")

# 3) Guardar (tabla local)
with b_save_local:
    if st.button("💽 Guardar", use_container_width=True):
        df = st.session_state["df_main"][COLS].copy()
        _save_local(df.copy())
        st.success("Datos guardados en la tabla local (CSV).")

# 4) Subir a Sheets (respeta orden oficial)
with b_save_sheets:
    if st.button("📤 Subir a Sheets", use_container_width=True):
        df = st.session_state["df_main"].copy()
        cols_order = globals().get("COLS_XLSX", []) or target_cols[:]
        cols_order = [c for c in cols_order if c in df.columns]
        if cols_order:
            df = df.reindex(columns=cols_order)
        _save_local(df.copy())
        ok, msg = _write_sheet_tab(df.copy())
        st.success(msg) if ok else st.warning(msg)
