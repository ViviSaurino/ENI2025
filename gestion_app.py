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
  margin-top: 6px !important;
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
  margin-top: 10px !important;
  margin-bottom: 28px !important;
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
[data-testid="stSidebar"][aria-expanded="true"]{
  width: 200px !important;
  min-width: 200px !important;
}
[data-testid="stSidebar"][aria-expanded="true"] > div{ width: 200px !important; }
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
  width: fit-content !important;
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

#ux-section .form-card [data-testid="stHorizontalBlock"]:nth-of-type(1)
  > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width: 0 !important; }

#ux-section .form-card [data-testid="stHorizontalBlock"]:nth-of-type(2)
  > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width: 0 !important; }

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

/* ===== Alineación robusta botón + píldora ===== */
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

/* === Overwrite de help-strips === */
#nt-help, #ux-help, #na-help, #pri-help, #eva-help{
  transform: none !important;
  margin-top: 10px !important;
  margin-bottom: 14px !important;
}
.help-strip,
.form-card > .help-strip{
  margin-top: 10px !important;
}

/* ===== ULTRA PATCH: toggle SOLO en #ntbar ===== */
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
  margin-bottom: 11px !important;
}

/* Respiro superior para tarjetas */
#nt-section .form-card,
#ux-section .form-card,
#na-section .form-card,
#pri-section .form-card,
#eva-section .form-card{
  margin-top: 6px !important;
}

/* ===== (ag-align-fix) integrado al bloque principal ===== */
#prior-grid .ag-header-viewport,
#prior-grid .ag-center-cols-viewport,
#eval-grid  .ag-header-viewport,
#eval-grid  .ag-center-cols-viewport{
  padding-left:0 !important;
  padding-right:0 !important;
}
#prior-grid .ag-header, #prior-grid .ag-center-cols-container,
#eval-grid  .ag-header, #eval-grid  .ag-center-cols-container{
  transform: translateX(0) !important;
}
#prior-grid .ag-header-cell, #prior-grid .ag-cell,
#eval-grid  .ag-header-cell, #eval-grid  .ag-cell{
  border-right:1px solid #E9EDF3 !important;
}
            
/* === PATCH FINAL: alinear y igualar anchos en EDITAR ESTADO === */
#ux-section .form-card [data-baseweb="input"] > div,
#ux-section .form-card [data-baseweb="textarea"] > div,
#ux-section .form-card [data-baseweb="select"] > div,
#ux-section .form-card [data-baseweb="datepicker"] > div{
  width: 100% !important;
  max-width: none !important;
  min-width: 0 !important;
  box-sizing: border-box !important;
}

/* Asegura que el combobox (contenido interno del select) también use 100% */
#ux-section .form-card [data-baseweb="select"] [role="combobox"]{
  width: 100% !important;
  max-width: none !important;
  min-width: 0 !important;
  box-sizing: border-box !important;
}

/* Neutraliza cualquier min-width heredado en las 3 primeras celdas de la fila 1
   (Área, Fase, Responsable) para que respeten exactamente los anchos de columnas */
#ux-section .form-card [data-testid="stHorizontalBlock"]:nth-of-type(1)
  > [data-testid="column"]:nth-of-type(-n+3) [data-baseweb="select"] > div{
  min-width: 0 !important;
  width: 100% !important;
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

# ================== Formulario ==================

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

submitted = False

if st.session_state.get("nt_visible", True):
    # Tira de ayuda
    st.markdown("""
    <div class="help-strip help-strip-nt" id="nt-help">
      ✳️ <strong>Completa los campos principales</strong> para registrar una nueva tarea
    </div>
    """, unsafe_allow_html=True)

    # ===== CSS: fuerzas 100% de controles =====
    st.markdown("""
    <style>
    #form-nt .stTextInput, 
    #form-nt .stSelectbox, 
    #form-nt .stDateInput, 
    #form-nt .stTimeInput, 
    #form-nt .stTextArea { width: 100% !important; }
    #form-nt .stTextInput > div,
    #form-nt .stSelectbox > div,
    #form-nt .stDateInput > div,
    #form-nt .stTimeInput > div,
    #form-nt .stTextArea > div { width: 100% !important; max-width: none !important; }
    #form-nt [data-baseweb="select"],
    #form-nt [data-baseweb="select"] > div,
    #form-nt [data-baseweb="select"] input { width: 100% !important; }
    #form-nt [data-testid="stDateInput"] input,
    #form-nt [data-testid^="stTimeInput"] input { width: 100% !important; }
    #form-nt [data-testid^="stTimeInput"] > div { width: 100% !important; }
    #form-nt .stButton, 
    #form-nt .stButton > button, 
    #form-nt [data-testid^="baseButton"] button {
      width: 100% !important; display:block !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="form-card" id="form-nt">', unsafe_allow_html=True)

    # Catálogo de fases
    FASES = [
        "Capacitación",
        "Post-capacitación",
        "Pre-consistencia",
        "Consistencia",
        "Operación de campo",
    ]

    with st.form("form_nueva_tarea", clear_on_submit=True):
        # ===== Rejilla unificada (ambas filas) =====
        # Ajustes solicitados: A más ancho; Fw un poco más angosto (pero cabe “Operación de campo”).
        A  = 1.80  # Área / Tipo  (↑ para calzar con la píldora de 'Nueva tarea')
        Fw = 2.10  # Fase / Estado (↓ leve, pero muestra “Operación de campo” completo)
        T  = 3.00  # Tarea / Fecha de inicio
        D  = 2.00  # Detalle de tarea / Hora de inicio
        R  = 2.00  # Responsable / ID asignado
        C  = 1.60  # Ciclo de mejora / Botón

        # ============== FILA 1 ==============
        r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")

        area = r1c1.selectbox("Área", options=AREAS_OPC, index=0, key="nt_area")

        fase = r1c2.selectbox(
            "Fase",
            options=FASES,
            index=None,
            placeholder="Selecciona una fase",
            key="nt_fase"
        )

        tarea   = r1c3.text_input("Tarea", placeholder="Describe la tarea")
        detalle = r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)")
        resp    = r1c5.text_input("Responsable", placeholder="Nombre")

        ciclo_mejora = r1c6.selectbox(
            "Ciclo de mejora",
            options=["1", "2", "3", "+4"],
            index=0,
            key="nt_ciclo_mejora"
        )

        # ============== FILA 2 (misma malla) ==============
        c2_1, c2_2, c2_3, c2_4, c2_5, c2_6 = st.columns([A, Fw, T, D, R, C], gap="medium")

        tipo   = c2_1.text_input("Tipo de tarea", placeholder="Tipo o categoría")
        estado = _opt_map(c2_2, "Estado", EMO_ESTADO, "No iniciado")

        fi_d   = c2_3.date_input("Fecha de inicio", value=None, key="fi_d")
        fi_t   = c2_4.time_input("Hora de inicio", value=None, step=60, key="fi_t")

        # ID asignado (debajo de Responsable)
        try:
            _df_tmp = st.session_state["df_main"]
            id_preview = next_id_area(_df_tmp, area)
        except Exception:
            id_preview = ""
        c2_5.text_input("ID asignado", value=id_preview, disabled=True)

        # Botón (debajo de Ciclo de mejora) con spacer para alinear altura
        with c2_6:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("💾 Agregar", use_container_width=True)

    # ============== POST Submit ==============
    if submitted:
        try:
            # 1) Base actual
            df = st.session_state["df_main"].copy()

            # Garantiza "Ciclo de mejora"
            if "Ciclo de mejora" not in df.columns:
                df["Ciclo de mejora"] = ""

            # 2) Nueva fila
            f_ini = combine_dt(fi_d, fi_t)

            new = blank_row()
            new.update({
                "Área": area,
                "Id": next_id_area(df, area),   # ID real guardado
                "Tarea": tarea,
                "Tipo": tipo,
                "Responsable": resp,
                "Fase": fase,
                "Estado": estado,
                "Fecha inicio": f_ini,
                "Ciclo de mejora": ciclo_mejora,
                "Detalle": detalle,
            })

            # 3) Inserta + normaliza fecha
            df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
            if "Fecha inicio" in df.columns:
                df["Fecha inicio"] = pd.to_datetime(df["Fecha inicio"], errors="coerce")

            # 4) Estado y guardado CSV
            st.session_state["df_main"] = df.copy()
            os.makedirs("data", exist_ok=True)
            df.reindex(columns=COLS, fill_value=None).to_csv(
                os.path.join("data", "tareas.csv"),
                index=False, encoding="utf-8-sig", mode="w"
            )

            # 5) Mensaje y refresco
            st.success(f"✔ Tarea agregada (Id {new['Id']}).")
            st.rerun()

        except Exception as e:
            st.error(f"No pude guardar la nueva tarea: {e}")

    st.markdown('</div>', unsafe_allow_html=True)  # cierra .form-card


# ================== Actualizar estado ==================

st.session_state.setdefault("ux_visible", True)
chev2 = "▾" if st.session_state["ux_visible"] else "▸"

# ---------- Barra superior (triangulito + píldora) ----------
st.markdown('<div class="topbar-ux">', unsafe_allow_html=True)
c_toggle2, c_pill2 = st.columns([0.028, 0.965], gap="medium")
with c_toggle2:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_ux():
        st.session_state["ux_visible"] = not st.session_state["ux_visible"]
    st.button(chev2, key="ux_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_ux)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill2:
    st.markdown('<div class="form-title-ux">&nbsp;&nbsp;🔁&nbsp;&nbsp;Editar estado</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["ux_visible"]:

    st.markdown("""
    <div class="help-strip help-strip-ux" id="ux-help">
      🔄 <strong>Actualiza el estado</strong> de una tarea ya registrada usando los filtros
    </div>
    """, unsafe_allow_html=True)

    # ====== CONTENEDOR LOCAL (quita min-width y fuerza 100%) ======
    st.markdown('<div id="ux-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #ux-section .form-card [data-baseweb="input"] > div,
      #ux-section .form-card [data-baseweb="textarea"] > div,
      #ux-section .form-card [data-baseweb="select"] > div,
      #ux-section .form-card [data-baseweb="datepicker"] > div{
        width:100% !important; max-width:none !important; box-sizing:border-box !important; min-width:0 !important;
      }
      #ux-section .form-card [data-baseweb="select"] [role="combobox"]{ width:100% !important; }
    </style>
    """, unsafe_allow_html=True)

    # ===== Proporciones EXACTAS usadas en "Nueva tarea" (fila de 6 controles) =====
    # Mantenlas aquí sincronizadas con la fila de "Nueva tarea":
    W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BTN = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    # Base
    df_all = st.session_state["df_main"].copy()
    for col_req in ["Estado", "Fecha estado", "Hora estado"]:
        if col_req not in df_all.columns:
            df_all[col_req] = None

    st.markdown('<div class="form-card">', unsafe_allow_html=True)

    # ===== Filtros (alineados 1:1 con "Nueva tarea") =====
    with st.form("ux_filtros", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_btn = st.columns(
            [W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BTN], gap="medium"
        )

        ux_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0, key="ux_area")

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        ux_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="ux_fase")

        src_resp = df_all if ux_area == "Todas" else df_all[df_all["Área"] == ux_area]
        responsables_all = sorted([x for x in src_resp.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        ux_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0, key="ux_resp")

        ux_desde = c_desde.date_input("Desde", value=None, key="ux_desde")
        ux_hasta = c_hasta.date_input("Hasta",  value=None, key="ux_hasta")

        with c_btn:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado =====
    df_filtrado = df_all.copy()
    if do_buscar:
        if ux_area != "Todas":
            df_filtrado = df_filtrado[df_filtrado["Área"] == ux_area]
        if ux_fase != "Todas" and "Fase" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == ux_fase]
        if ux_resp != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Responsable"].astype(str) == ux_resp]
        base_fecha_col = "Fecha inicio" if "Fecha inicio" in df_filtrado.columns else "Fecha estado"
        if base_fecha_col in df_filtrado.columns:
            fcol = pd.to_datetime(df_filtrado[base_fecha_col], errors="coerce")
            if ux_desde:
                df_filtrado = df_filtrado[fcol >= pd.to_datetime(ux_desde)]
            if ux_hasta:
                df_filtrado = df_filtrado[fcol <= (pd.to_datetime(ux_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    # ===== Tabla (visible aún vacía) =====
    cols_view = ["Id", "Tarea", "Estado", "Fecha estado", "Hora estado"]
    for c in cols_view:
        if c not in df_filtrado.columns:
            df_filtrado[c] = None

    df_view = df_filtrado[cols_view].copy().rename(columns={
        "Estado": "Estado actual",
        "Fecha estado": "Fecha estado actual",
        "Hora estado": "Hora estado actual"
    })
    df_view["Estado modificado"] = ""
    df_view["Fecha estado modificado"] = ""
    df_view["Hora estado modificado"]  = ""

    st.markdown("**Resultados**")

    gob = GridOptionsBuilder.from_dataframe(df_view)
    gob.configure_grid_options(
        suppressMovableColumns=True, domLayout="normal", ensureDomOrder=True,
        rowHeight=38, headerHeight=42
    )
    for c_ro in ["Id", "Tarea", "Estado actual", "Fecha estado actual", "Hora estado actual"]:
        gob.configure_column(c_ro, editable=False)

    ESTADOS_OPC = ["", "En curso", "Terminado", "Pausado", "Cancelado", "Eliminado"]
    gob.configure_column("Estado modificado", editable=True,
                         cellEditor="agSelectCellEditor", cellEditorParams={"values": ESTADOS_OPC}, width=180)
    gob.configure_column("Fecha estado modificado", editable=True, width=180)
    gob.configure_column("Hora estado modificado",   editable=True, width=150)

    grid = AgGrid(
        df_view,
        gridOptions=gob.build(),
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=False,
        enable_enterprise_modules=False,
        reload_data=False,
        height=180
    )

    # ===== Botón Guardar (alineado al último corte) =====
    _spacer, _btncol = st.columns([W_AREA+W_FASE+W_RESP+W_DESDE+W_HASTA, W_BTN], gap="medium")
    with _btncol:
        if st.button("💾 Guardar cambios", use_container_width=True):
            try:
                df_editado = pd.DataFrame(grid["data"]).copy()
                df_base = st.session_state["df_main"].copy()
                for col_req in ["Estado", "Fecha estado", "Hora estado"]:
                    if col_req not in df_base.columns:
                        df_base[col_req] = None

                cambios = 0
                for _, row in df_editado.iterrows():
                    id_row = str(row.get("Id", "")).strip()
                    if not id_row: 
                        continue
                    est_mod = str(row.get("Estado modificado", "")).strip()
                    f_mod   = str(row.get("Fecha estado modificado", "")).strip()
                    h_mod   = str(row.get("Hora estado modificado", "")).strip()
                    if not est_mod and not f_mod and not h_mod:
                        continue
                    m = df_base["Id"].astype(str).str.strip() == id_row
                    if not m.any():
                        continue
                    if est_mod: df_base.loc[m, "Estado"] = est_mod
                    if f_mod:
                        try: _ = pd.to_datetime(f_mod); df_base.loc[m, "Fecha estado"] = f_mod
                        except Exception: pass
                    if h_mod:
                        ok = True
                        try: hh, mm = h_mod.split(":"); int(hh); int(mm)
                        except Exception: ok = False
                        if ok: df_base.loc[m, "Hora estado"] = h_mod
                    cambios += 1

                if cambios > 0:
                    st.session_state["df_main"] = df_base.copy()
                    _save_local(df_base[COLS].copy() if set(COLS).issubset(df_base.columns) else df_base.copy())
                    st.success(f"✔ Cambios guardados: {cambios} fila(s) actualizada(s).")
                else:
                    st.info("No se detectaron cambios para guardar.")
            except Exception as e:
                st.error(f"No pude guardar los cambios: {e}")

    st.markdown('</div>', unsafe_allow_html=True)  # cierra .form-card
    st.markdown('</div>', unsafe_allow_html=True)  # cierra #ux-section


# ================== Actualizar estado ==================

st.session_state.setdefault("ux_visible", True)
chev2 = "▾" if st.session_state["ux_visible"] else "▸"

# ---------- Barra superior (triangulito + píldora) ----------
st.markdown('<div class="topbar-ux">', unsafe_allow_html=True)
c_toggle2, c_pill2 = st.columns([0.028, 0.965], gap="medium")
with c_toggle2:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_ux():
        st.session_state["ux_visible"] = not st.session_state["ux_visible"]
    st.button(chev2, key="ux_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_ux)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill2:
    st.markdown('<div class="form-title-ux">&nbsp;&nbsp;🔁&nbsp;&nbsp;Editar estado</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["ux_visible"]:

    st.markdown("""
    <div class="help-strip help-strip-ux" id="ux-help">
      🔄 <strong>Actualiza el estado</strong> de una tarea ya registrada usando los filtros
    </div>
    """, unsafe_allow_html=True)

    # ====== CONTENEDOR LOCAL (quita min-width y fuerza 100%) ======
    st.markdown('<div id="ux-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      /* Fuerza 100% en inputs/selects/fechas dentro de esta sección */
      #ux-section .form-card [data-baseweb="input"] > div,
      #ux-section .form-card [data-baseweb="textarea"] > div,
      #ux-section .form-card [data-baseweb="select"] > div,
      #ux-section .form-card [data-baseweb="datepicker"] > div{
        width:100% !important; max-width:none !important; box-sizing:border-box !important; min-width:0 !important;
      }
      #ux-section .form-card [data-baseweb="select"] [role="combobox"]{ width:100% !important; }

      /* Neutraliza min-width heredado SOLO en las 3 primeras celdas de la 1ª fila (Área, Fase, Responsable) */
      #ux-section .form-card [data-testid="stHorizontalBlock"]:nth-of-type(1)
        > [data-testid="column"]:nth-of-type(-n+3) [data-baseweb="select"] > div{
        min-width:0 !important; width:100% !important;
      }
    </style>
    """, unsafe_allow_html=True)

    # ===== Proporciones EXACTAS usadas en "Nueva tarea" (fila de 6 controles) =====
    # Mantener sincronizadas con la fila de "Nueva tarea":
    W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BTN = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    # Base
    df_all = st.session_state["df_main"].copy()
    for col_req in ["Estado", "Fecha estado", "Hora estado"]:
        if col_req not in df_all.columns:
            df_all[col_req] = None

    st.markdown('<div class="form-card">', unsafe_allow_html=True)

    # ===== Filtros (alineados 1:1 con "Nueva tarea") =====
    with st.form("ux_filtros", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_btn = st.columns(
            [W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BTN], gap="medium"
        )

        ux_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0, key="ux_area")

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        ux_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="ux_fase")

        src_resp = df_all if ux_area == "Todas" else df_all[df_all["Área"] == ux_area]
        responsables_all = sorted([x for x in src_resp.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        ux_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0, key="ux_resp")

        ux_desde = c_desde.date_input("Desde", value=None, key="ux_desde")
        ux_hasta = c_hasta.date_input("Hasta",  value=None, key="ux_hasta")

        with c_btn:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado =====
    df_filtrado = df_all.copy()
    if do_buscar:
        if ux_area != "Todas":
            df_filtrado = df_filtrado[df_filtrado["Área"] == ux_area]
        if ux_fase != "Todas" and "Fase" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == ux_fase]
        if ux_resp != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Responsable"].astype(str) == ux_resp]
        base_fecha_col = "Fecha inicio" if "Fecha inicio" in df_filtrado.columns else "Fecha estado"
        if base_fecha_col in df_filtrado.columns:
            fcol = pd.to_datetime(df_filtrado[base_fecha_col], errors="coerce")
            if ux_desde:
                df_filtrado = df_filtrado[fcol >= pd.to_datetime(ux_desde)]
            if ux_hasta:
                df_filtrado = df_filtrado[fcol <= (pd.to_datetime(ux_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    # ===== Tabla (visible aún vacía) =====
    cols_view = ["Id", "Tarea", "Estado", "Fecha estado", "Hora estado"]
    for c in cols_view:
        if c not in df_filtrado.columns:
            df_filtrado[c] = None

    df_view = df_filtrado[cols_view].copy().rename(columns={
        "Estado": "Estado actual",
        "Fecha estado": "Fecha estado actual",
        "Hora estado": "Hora estado actual"
    })
    df_view["Estado modificado"] = ""
    df_view["Fecha estado modificado"] = ""
    df_view["Hora estado modificado"]  = ""

    st.markdown("**Resultados**")

    gob = GridOptionsBuilder.from_dataframe(df_view)
    gob.configure_grid_options(
        suppressMovableColumns=True, domLayout="normal", ensureDomOrder=True,
        rowHeight=38, headerHeight=42
    )
    for c_ro in ["Id", "Tarea", "Estado actual", "Fecha estado actual", "Hora estado actual"]:
        gob.configure_column(c_ro, editable=False)

    ESTADOS_OPC = ["", "En curso", "Terminado", "Pausado", "Cancelado", "Eliminado"]
    gob.configure_column("Estado modificado", editable=True,
                         cellEditor="agSelectCellEditor", cellEditorParams={"values": ESTADOS_OPC}, width=180)
    gob.configure_column("Fecha estado modificado", editable=True, width=180)
    gob.configure_column("Hora estado modificado",   editable=True, width=150)

    grid = AgGrid(
        df_view,
        gridOptions=gob.build(),
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=False,
        enable_enterprise_modules=False,
        reload_data=False,
        height=180
    )

    # ===== Botón Guardar (alineado al último corte) =====
    _spacer, _btncol = st.columns([W_AREA+W_FASE+W_RESP+W_DESDE+W_HASTA, W_BTN], gap="medium")
    with _btncol:
        if st.button("💾 Guardar cambios", use_container_width=True):
            try:
                df_editado = pd.DataFrame(grid["data"]).copy()
                df_base = st.session_state["df_main"].copy()
                for col_req in ["Estado", "Fecha estado", "Hora estado"]:
                    if col_req not in df_base.columns:
                        df_base[col_req] = None

                cambios = 0
                for _, row in df_editado.iterrows():
                    id_row = str(row.get("Id", "")).strip()
                    if not id_row: 
                        continue
                    est_mod = str(row.get("Estado modificado", "")).strip()
                    f_mod   = str(row.get("Fecha estado modificado", "")).strip()
                    h_mod   = str(row.get("Hora estado modificado", "")).strip()
                    if not est_mod and not f_mod and not h_mod:
                        continue
                    m = df_base["Id"].astype(str).str.strip() == id_row
                    if not m.any():
                        continue
                    if est_mod: df_base.loc[m, "Estado"] = est_mod
                    if f_mod:
                        try: _ = pd.to_datetime(f_mod); df_base.loc[m, "Fecha estado"] = f_mod
                        except Exception: pass
                    if h_mod:
                        ok = True
                        try: hh, mm = h_mod.split(":"); int(hh); int(mm)
                        except Exception: ok = False
                        if ok: df_base.loc[m, "Hora estado"] = h_mod
                    cambios += 1

                if cambios > 0:
                    st.session_state["df_main"] = df_base.copy()
                    _save_local(df_base[COLS].copy() if set(COLS).issubset(df_base.columns) else df_base.copy())
                    st.success(f"✔ Cambios guardados: {cambios} fila(s) actualizada(s).")
                else:
                    st.info("No se detectaron cambios para guardar.")
            except Exception as e:
                st.error(f"No pude guardar los cambios: {e}")

    st.markdown('</div>', unsafe_allow_html=True)  # cierra .form-card
    st.markdown('</div>', unsafe_allow_html=True)  # cierra #ux-section


# =========================== PRIORIDAD ===============================

st.session_state.setdefault("pri_visible", True)
chev_pri = "▾" if st.session_state["pri_visible"] else "▸"

st.markdown('<div class="topbar-pri">', unsafe_allow_html=True)
c_toggle_p, c_pill_p = st.columns([0.028, 0.965], gap="medium")
with c_toggle_p:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_pri(): st.session_state["pri_visible"] = not st.session_state["pri_visible"]
    st.button(chev_pri, key="pri_toggle", help="Mostrar/ocultar", on_click=_toggle_pri)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill_p:
    st.markdown('<div class="form-title-pri">🧭&nbsp;&nbsp;Prioridad</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

if st.session_state["pri_visible"]:
    st.markdown("""
    <div class="help-strip" id="pri-help">
      🧭 <strong>Asigna o edita prioridades</strong> para varias tareas a la vez (solo jefatura)
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    df_all = st.session_state["df_main"].copy()

    # ===== Claves estables y lectura desde session_state =====
    # (asegura persistencia al hacer clic fuera del form)
    _k_area  = "pri_area_sel"
    _k_resp  = "pri_resp_sel"
    _k_d     = "pri_desde"
    _k_h     = "pri_hasta"
    _k_tasks = "pri_tareas_sel"

    with st.form("form_prioridad", clear_on_submit=False):
        # === Fila de filtros con pesos que calzan con el grid ===
        W_AREA, W_RESP, W_TAREA, W_PRI = COL_W_AREA, PILL_W_RESP, COL_W_TAREA, COL_W_PRIORIDAD
        r1_area, r1_resp, r1_desde, r1_hasta, r1_tarea, r1_ids = st.columns(
            [W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_PRI], gap="small"
        )

        areas_opts = ["Todas"] + AREAS_OPC
        area_sel = r1_area.selectbox("Área", options=areas_opts, index=0, key=_k_area, disabled=not CAN_EDIT)

        df_resp = df_all if st.session_state[_k_area] == "Todas" else df_all[df_all["Área"] == st.session_state[_k_area]]
        responsables_all = sorted([x for x in df_resp["Responsable"].astype(str).unique() if x and x != "nan"])
        resp_sel = r1_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0, key=_k_resp, disabled=not CAN_EDIT)

        r1_desde.date_input("Desde", value=None, key=_k_d, disabled=not CAN_EDIT)
        r1_hasta.date_input("Hasta", value=None, key=_k_h, disabled=not CAN_EDIT)

        # Dataset filtrado + lista multiselección de tareas
        def _filtra(df):
            out = df.copy()
            if st.session_state[_k_area] != "Todas":
                out = out[out["Área"] == st.session_state[_k_area]]
            if st.session_state[_k_resp] != "Todos":
                out = out[out["Responsable"].astype(str) == st.session_state[_k_resp]]
            if st.session_state[_k_d]:
                fcol = pd.to_datetime(out["Fecha inicio"], errors="coerce")
                out = out[fcol.dt.date >= st.session_state[_k_d]]
            if st.session_state[_k_h]:
                fcol = pd.to_datetime(out["Fecha inicio"], errors="coerce")
                out = out[fcol.dt.date <= st.session_state[_k_h]]
            return out

        df_f = _filtra(df_all).dropna(subset=["Id"]).copy()
        df_f["Tarea_str"] = df_f["Tarea"].astype(str).replace({"nan": ""})
        opciones_tarea = df_f["Tarea_str"].tolist()

        r1_tarea.multiselect("Tarea (multi)", opciones_tarea, default=st.session_state.get(_k_tasks, []),
                             key=_k_tasks, disabled=not CAN_EDIT)

        # Ids seleccionados (solo lectura) — calculado SIEMPRE desde session_state
        if st.session_state[_k_tasks]:
            ids_sel = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]), "Id"].astype(str).tolist()
        else:
            ids_sel = []
        r1_ids.text_input("Ids seleccionados", value=", ".join(ids_sel) if ids_sel else "—", disabled=True)

        # ===== Tabla editable PRIORIDAD (AgGrid) =====
        st.write("")
        if ids_sel:
            df_tab = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]),
                              ["Id", "Área", "Responsable", "Tarea", "Prioridad"]].copy()
        else:
            df_tab = pd.DataFrame(columns=["Id","Área","Responsable","Tarea","Prioridad"])

        if "Prioridad" not in df_tab.columns:
            df_tab["Prioridad"] = "Media"
        df_tab["Id"] = df_tab["Id"].astype(str)

        st.caption("Lista seleccionada")
        df_pri = _clean_df_for_grid(df_tab)
        grid_opt_pri = _grid_options_prioridad(df_pri)

        # ⬇️ Paso 4: wrapper con ID para aplicar el CSS de alineación
        st.markdown('<div id="prior-grid">', unsafe_allow_html=True)
        grid_pri = AgGrid(
            df_pri,
            gridOptions=grid_opt_pri,
            fit_columns_on_grid_load=False,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            allow_unsafe_jscode=True,
            theme="balham",
            height=180,
            custom_css={
                ".ag-root-wrapper": {"height": "180px !important"},
                ".ag-body-viewport": {"height": "140px !important"},
            },
            key="grid_prior"   # clave estable
        )
        st.markdown('</div>', unsafe_allow_html=True)

        edited = pd.DataFrame(grid_pri["data"]) if isinstance(grid_pri, dict) and "data" in grid_pri else df_pri.copy()

        # === Botón con ancho de la última columna ===
        b1, b2, b3, b4, b5, b6 = st.columns([W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_PRI], gap="small")
        with b6:
            do_save_pri = st.form_submit_button("🧭 Dar prioridad", use_container_width=True, disabled=not CAN_EDIT)

    if CAN_EDIT and 'do_save_pri' in locals() and do_save_pri:
        if edited.empty:
            st.warning("No hay filas seleccionadas para actualizar.")
        else:
            df = st.session_state["df_main"].copy()
            for _, row in edited.iterrows():
                m = df["Id"].astype(str) == str(row["Id"])
                if m.any():
                    df.loc[m, "Prioridad"] = row.get("Prioridad", df.loc[m, "Prioridad"])
            st.session_state["df_main"] = df.copy()
            _save_local(df[COLS].copy())
            ok, msg = _write_sheet_tab(df[COLS].copy())
            st.success(f"✔ Prioridades actualizadas ({len(edited)} filas). {msg}") if ok else st.warning(f"Actualizado localmente. {msg}")
    elif not CAN_EDIT:
        st.info("🔒 Solo jefatura puede editar prioridades.")
    st.markdown('</div>', unsafe_allow_html=True)  # form-card


# =========================== EVALUACIÓN ===============================

st.session_state.setdefault("eva_visible", True)
chev_eva = "▾" if st.session_state["eva_visible"] else "▸"

st.markdown('<div class="topbar-eval">', unsafe_allow_html=True)
c_toggle_e, c_pill_e = st.columns([0.028, 0.965], gap="medium")
with c_toggle_e:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_eva(): st.session_state["eva_visible"] = not st.session_state["eva_visible"]
    st.button(chev_eva, key="eva_toggle", help="Mostrar/ocultar", on_click=_toggle_eva)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill_e:
    st.markdown('<div class="form-title-eval">📝&nbsp;&nbsp;Evaluación</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

if st.session_state["eva_visible"]:
    st.markdown("""
    <div class="help-strip" id="eva-help">
      📝 <strong>Registra una evaluación</strong> por varias tareas a la vez (solo jefatura).
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    df_all = st.session_state["df_main"].copy()

    # ===== Claves estables y lectura desde session_state =====
    _k_area  = "eva_area_sel"
    _k_resp  = "eva_resp_sel"
    _k_d     = "eva_desde"
    _k_h     = "eva_hasta"
    _k_tasks = "eva_tareas_sel"

    with st.form("form_evaluacion", clear_on_submit=False):
        # Pesos calcados a los anchos del grid
        W_AREA, W_RESP, W_TAREA, W_EVA = COL_W_AREA, PILL_W_RESP, COL_W_TAREA, COL_W_EVALUACION

        # Fila de filtros (alineada a columnas del grid)
        c_area, c_resp, c_desde, c_hasta, c_tarea, c_id = st.columns(
            [W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_EVA], gap="small"
        )

        area_sel = c_area.selectbox("Área", options=["Todas"] + AREAS_OPC, index=0, key=_k_area, disabled=not CAN_EDIT)
        df_resp = df_all if st.session_state[_k_area] == "Todas" else df_all[df_all["Área"] == st.session_state[_k_area]]
        responsables_all = sorted([x for x in df_resp["Responsable"].astype(str).unique() if x and x != "nan"])
        resp_sel = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0, key=_k_resp, disabled=not CAN_EDIT)

        c_desde.date_input("Desde", value=None, key=_k_d, disabled=not CAN_EDIT)
        c_hasta.date_input("Hasta", value=None, key=_k_h, disabled=not CAN_EDIT)

        # Multiselección de tareas para evaluar
        def _filtra(df):
            out = df.copy()
            if st.session_state[_k_area] != "Todas":
                out = out[out["Área"] == st.session_state[_k_area]]
            if st.session_state[_k_resp] != "Todos":
                out = out[out["Responsable"].astype(str) == st.session_state[_k_resp]]
            if st.session_state[_k_d]:
                fcol = pd.to_datetime(out["Fecha inicio"], errors="coerce")
                out = out[fcol.dt.date >= st.session_state[_k_d]]
            if st.session_state[_k_h]:
                fcol = pd.to_datetime(out["Fecha inicio"], errors="coerce")
                out = out[fcol.dt.date <= st.session_state[_k_h]]
            return out

        df_f = _filtra(df_all).dropna(subset=["Id"]).copy()
        df_f["Tarea_str"] = df_f["Tarea"].astype(str).replace({"nan": ""})
        tareas_opts = df_f["Tarea_str"].tolist()

        c_tarea.multiselect("Tarea (multi)", tareas_opts, default=st.session_state.get(_k_tasks, []),
                            key=_k_tasks, disabled=not CAN_EDIT)

        if st.session_state[_k_tasks]:
            ids_sel = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]), "Id"].astype(str).tolist()
        else:
            ids_sel = []
        c_id.text_input("Ids seleccionados", value=", ".join(ids_sel) if ids_sel else "—", disabled=True)

        st.write("")

        # ===== Tabla editable de Evaluación (AgGrid) =====
        if ids_sel:
            df_tab_e = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]),
                                ["Id", "Área", "Responsable", "Tarea"]].copy()
        else:
            df_tab_e = pd.DataFrame(columns=["Id","Área","Responsable","Tarea"])

        if not df_tab_e.empty:
            df_tab_e["Evaluación"] = 5
        else:
            # ✅ fix: crear columna vacía con dtype int (evita error de longitud)
            df_tab_e["Evaluación"] = pd.Series(dtype=int)

        df_tab_e["Id"] = df_tab_e["Id"].astype(str)

        st.caption("Lista seleccionada")
        df_eval_tab = _clean_df_for_grid(df_tab_e)
        grid_opt_eval = _grid_options_evaluacion(df_eval_tab)

        # ⬇️ Paso 4: wrapper con ID para aplicar el CSS de alineación
        st.markdown('<div id="eval-grid">', unsafe_allow_html=True)
        grid_eval = AgGrid(
            df_eval_tab,
            gridOptions=grid_opt_eval,
            fit_columns_on_grid_load=False,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            allow_unsafe_jscode=True,
            theme="balham",
            height=180,
            custom_css={
                ".ag-root-wrapper": {"height": "180px !important"},
                ".ag-body-viewport": {"height": "140px !important"},
            },
            key="grid_eval"    # clave estable
        )
        st.markdown('</div>', unsafe_allow_html=True)

        edited_eval = pd.DataFrame(grid_eval["data"]) if isinstance(grid_eval, dict) and "data" in grid_eval else df_eval_tab.copy()

        # Botón con el MISMO ancho que la última columna (Evaluación)
        bx1, bx2, bx3, bx4, bx5, bx6 = st.columns([W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_EVA], gap="small")
        with bx6:
            do_save_eval = st.form_submit_button("✅ Evaluar", use_container_width=True, disabled=not CAN_EDIT)

    if CAN_EDIT and 'do_save_eval' in locals() and do_save_eval:
        if edited_eval.empty:
            st.warning("No hay filas seleccionadas para evaluar.")
        else:
            df = st.session_state["df_main"].copy()
            for _, row in edited_eval.iterrows():
                m = df["Id"].astype(str) == str(row["Id"])
                if m.any():
                    df.loc[m, "Evaluación"] = row.get("Evaluación", df.loc[m, "Evaluación"])
            st.session_state["df_main"] = df.copy()
            _save_local(df[COLS].copy())
            ok, msg = _write_sheet_tab(df[COLS].copy())
            st.success(f"✔ Evaluación registrada ({len(edited_eval)} filas). {msg}") if ok else st.warning(f"Actualizado localmente. {msg}")
    elif not CAN_EDIT:
        st.info("🔒 Solo jefatura puede registrar evaluaciones.")
    st.markdown('</div>', unsafe_allow_html=True)  # form-card


# ================== Historial ================== 
 
st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
st.subheader("📝 Tareas recientes")
st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
df_view = st.session_state["df_main"].copy()

# Mismas proporciones que usas arriba
A = 1.2   # Área
F = 1.2   # Fase
T = 3.2   # Tarea / Tipo de alerta
D = 2.4   # Detalle / (Fecha alerta + Fecha corregida)

# Responsables (antes de filtrar)
responsables = sorted([x for x in df_view["Responsable"].astype(str).unique() if x and x != "nan"])

# ---- FILA DE 5 FILTROS ----
cA, cR, cE, cD, cH = st.columns([A + F, T/2, T/2, D/2, D/2], gap="medium")

area_sel  = cA.selectbox("Área", options=["Todas"] + AREAS_OPC, index=0)
resp_sel  = cR.selectbox("Responsable", options=["Todos"] + responsables, index=0)
estado_sel = cE.selectbox("Estado", options=["Todos"] + ESTADO, index=0)

# Calendarios (rango de fechas)
f_desde = cD.date_input("Desde", value=None, key="f_desde")
f_hasta = cH.date_input("Hasta",  value=None, key="f_hasta")

# ---- Filtros de datos ----
df_view["Fecha inicio"] = pd.to_datetime(df_view.get("Fecha inicio"), errors="coerce")

if area_sel != "Todas":
    df_view = df_view[df_view["Área"] == area_sel]
if resp_sel != "Todos":
    df_view = df_view[df_view["Responsable"].astype(str) == resp_sel]
if estado_sel != "Todos":
    df_view = df_view[df_view["Estado"] == estado_sel]
if f_desde:
    df_view = df_view[df_view["Fecha inicio"].dt.date >= f_desde]
if f_hasta:
    df_view = df_view[df_view["Fecha inicio"].dt.date <= f_hasta]
st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)

# === ORDEN DE COLUMNAS ===
cols_first = ["Id", "Área", "Responsable", "Tarea", "Tipo", "Ciclo de mejora"]
if "Ciclo de mejora" not in df_view.columns:
    df_view["Ciclo de mejora"] = ""

cols_order = cols_first + [c for c in df_view.columns if c not in cols_first + ["__DEL__"]]
extra = ["__DEL__"] if "__DEL__" in df_view.columns else []

df_grid = (pd.DataFrame(columns=cols_order + extra) if df_view.empty
           else df_view.reindex(columns=cols_order + extra).copy())

# **CLAVE**: forzar Id a string antes de renderizar el grid
if "Id" in df_grid.columns:
    df_grid["Id"] = df_grid["Id"].astype(str).fillna("")

# ================= GRID OPTIONS =================
gob = GridOptionsBuilder.from_dataframe(df_grid)
gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True)

gob.configure_grid_options(
    rowSelection="multiple",
    rowMultiSelectWithClick=True,           # permite click + checkbox
    suppressRowClickSelection=False,
    rememberSelection=True,                 # recuerda selección
    domLayout="normal",
    rowHeight=38,
    headerHeight=42,
    enableRangeSelection=True,
    enableCellTextSelection=True,
    singleClickEdit=True,
    stopEditingWhenCellsLoseFocus=True,
    undoRedoCellEditing=True,
    enterMovesDown=True,
    getRowId=JsCode("function(p){ return (p.data && (p.data.Id || p.data['Id'])) + ''; }"),
)

# Selección múltiple con checkbox en Id + select-all
if "Id" in df_grid.columns:
    gob.configure_column(
        "Id",
        editable=False, width=110, pinned="left",
        checkboxSelection=True,
        headerCheckboxSelection=True,
        headerCheckboxSelectionFilteredOnly=True
    )
if "Área" in df_grid.columns:
    gob.configure_column("Área", editable=True,  width=160, pinned="left")
if "Responsable" in df_grid.columns:
    gob.configure_column("Responsable", pinned="left")

if "__DEL__" in df_grid.columns:
    gob.configure_column("__DEL__", hide=True)

colw = {"Tarea":220,"Tipo":160,"Responsable":200,"Fase":140,"Complejidad":130,"Prioridad":130,"Estado":130,
        "Fecha inicio":160,"Vencimiento":160,"Fecha fin":160,"Duración":110,"Días hábiles":120,
        "Cumplimiento":180,"¿Generó alerta?":150,"Tipo de alerta":200,"¿Se corrigió?":140,"Evaluación":170,"Calificación":120}

flag_formatter = JsCode("""
function(p){ const v=String(p.value||'');
  if(v==='Alta') return '🔴 Alta'; if(v==='Media') return '🟡 Media'; if(v==='Baja') return '🟢 Baja'; return v||'—'; }""")

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
  else if(v==='Entregado con retraso'){bg:'#00ACC1'}
  else if(v==='No entregado'){bg:'#006064'}
  else if(v==='En riesgo de retraso'){bg:'#0277BD'}
  else if(v==='Aprobada'){bg:'#8BC34A'; fg:'#0A2E00'}
  else if(v==='Desaprobada'){bg:'#FF8A80'}
  else if(v==='Pendiente de revisión'){bg:'#BDBDBD'; fg:'#2B2B2B'}
  else if(v==='Observada'){bg:'#D7A56C'}
  return { backgroundColor:bg, color:fg, fontWeight:'600', textAlign:'center',
           borderRadius:'10px', padding:'4px 10px' };
}""")

fmt_dash = JsCode("""
function(p){ if(p.value===null||p.value===undefined) return '—';
  const s=String(p.value).trim().toLowerCase();
  if(s===''||s==='nan'||s==='nat'||s==='none'||s==='null') return '—';
  return String(p.value); }""")

stars_fmt = JsCode("""
function(p){
  let n = parseInt(p.value||0); if(isNaN(n)||n<0) n=0; if(n>5) n=5;
  return '★'.repeat(n) + '☆'.repeat(5-n);
}""")

for c, fx in [("Tarea",3), ("Tipo",2), ("Tipo de alerta",2), ("Responsable",2), ("Fase",1)]:
    if c in df_grid.columns:
        gob.configure_column(c, editable=True, minWidth=colw.get(c,120), flex=fx, valueFormatter=fmt_dash)

for c in ["Complejidad", "Prioridad"]:
    if c in df_grid.columns:
        gob.configure_column(c, editable=True, cellEditor="agSelectCellEditor",
                             cellEditorParams={"values": ["Alta","Media","Baja"]},
                             valueFormatter=flag_formatter, minWidth=colw[c], maxWidth=220, flex=1)

for c, vals in [("Estado", ESTADO), ("Cumplimiento", CUMPLIMIENTO), ("¿Generó alerta?", SI_NO),
                ("¿Se corrigió?", SI_NO), ("Evaluación", ["Aprobada","Desaprobada","Pendiente de revisión","Observada","Cancelada","Pausada"])]:
    if c in df_grid.columns:
        gob.configure_column(c, editable=True, cellEditor="agSelectCellEditor",
                             cellEditorParams={"values": vals}, cellStyle=chip_style, valueFormatter=fmt_dash,
                             minWidth=colw.get(c, 120), maxWidth=260, flex=1)

if "Calificación" in df_grid.columns:
    gob.configure_column("Calificación", editable=True, valueFormatter=stars_fmt,
                         minWidth=colw["Calificación"], maxWidth=140, flex=0)

# Editor de fecha/hora (FIX: classList con punto)
date_time_editor = JsCode("""
class DateTimeEditor{
  init(p){
    this.eInput = document.createElement('input');
    this.eInput.type = 'datetime-local';
    this.eInput.classList.add('ag-input');   // <-- FIX AQUÍ
    this.eInput.style.width = '100%';
    const v = p.value ? new Date(p.value) : null;
    if (v && !isNaN(v.getTime())){
      const pad = n => String(n).padStart(2,'0');
      this.eInput.value = v.getFullYear() + '-' + pad(v.getMonth()+1) + '-' + pad(v.getDate())
                        + 'T' + pad(v.getHours()) + ':' + pad(v.getMinutes());
    }
  }
  getGui(){ return this.eInput }
  afterGuiAttached(){ this.eInput.focus() }
  getValue(){ return this.eInput.value }
}""")

date_time_fmt = JsCode("""
function(p){ if(p.value===null||p.value===undefined) return '—';
  const d=new Date(String(p.value).trim()); if(isNaN(d.getTime())) return '—';
  const pad=n=>String(n).padStart(2,'0');
  return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes()); }""")

for c in ["Fecha inicio","Vencimiento","Fecha fin"]:
    if c in df_grid.columns:
        gob.configure_column(c, editable=True, cellEditor=date_time_editor, valueFormatter=date_time_fmt,
                             minWidth=colw[c], maxWidth=200, flex=1)

dur_getter = JsCode("function(p){const s=p.data['Fecha inicio'],e=p.data['Vencimiento'];if(!s||!e)return null;const sd=new Date(s),ed=new Date(e);if(isNaN(sd.getTime()))return null;return Math.floor((ed-sd)/(1000*60*60*24));}")
bd_getter  = JsCode("function(p){const s=p.data['Fecha inicio'],e=p.data['Vencimiento'];if(!s||!e)return null;let sd=new Date(s),ed=new Date(e);if(isNaN(sd.getTime()))return null;if(ed<sd)return 0;sd=new Date(sd.getFullYear(),sd.getMonth(),sd.getDate());ed=new Date(ed.getFullYear(),ed.getMonth(),ed.getDate());let c=0;const one=24*60*60*1000;for(let t=sd.getTime();t<=ed.getTime();t+=one){const d=new Date(t).getDay();if(d!==0&&d!==6)c++;}return c;}")

if "Duración" in df_grid.columns:
    gob.configure_column("Duración", editable=False, valueGetter=dur_getter, valueFormatter=fmt_dash, minWidth=colw["Duración"], maxWidth=130, flex=0)
if "Días hábiles" in df_grid.columns:
    gob.configure_column("Días hábiles", editable=False, valueGetter=bd_getter, valueFormatter=fmt_dash, minWidth=colw["Días hábiles"], maxWidth=140, flex=0)

# Tooltips en headers
for col in df_grid.columns:
    gob.configure_column(col, headerTooltip=col)

# === Autosize callbacks ===
autosize_on_ready = JsCode("""
function(params){
  const all = params.columnApi.getAllDisplayedColumns();
  params.columnApi.autoSizeColumns(all, true);
}
""")
autosize_on_data = JsCode("""
function(params){
  if (params.api && params.api.getDisplayedRowCount() > 0){
    const all = params.columnApi.getAllDisplayedColumns();
    params.columnApi.autoSizeColumns(all, true);
  }
}
""")

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

# Guarda la selección actual (Ids) en session_state
sel_rows_now = grid.get("selected_rows", []) if isinstance(grid, dict) else []
st.session_state["hist_sel_ids"] = [str(r.get("Id", "")).strip() for r in sel_rows_now if str(r.get("Id", "")).strip()]

# Sincroniza ediciones por Id (solo si hay data)
if isinstance(grid, dict) and "data" in grid and grid["data"] is not None and len(grid["data"]) > 0:
    try:
        edited = pd.DataFrame(grid["data"]).copy()
        base = st.session_state["df_main"].copy().set_index("Id")
        st.session_state["df_main"] = base.combine_first(edited.set_index("Id")).reset_index()
    except Exception:
        pass

# ---- Botones ----
total_btn_width = (A + F) + (T / 2)
btn_w = total_btn_width / 4

b_del, b_xlsx, b_save_local, b_save_sheets, _spacer = st.columns(
    [btn_w, btn_w, btn_w, btn_w, (T / 2) + D],
    gap="medium"
)

# 1) Borrar seleccionados
with b_del:
    if st.button("🗑️ Borrar", use_container_width=True):
        ids = st.session_state.get("hist_sel_ids", [])
        if ids:
            df0 = st.session_state["df_main"].copy()
            st.session_state["df_main"] = df0[~df0["Id"].astype(str).isin(ids)].copy()
            st.session_state["hist_sel_ids"] = []
            st.success(f"Eliminadas {len(ids)} fila(s).")
            st.rerun()
        else:
            st.warning("No hay filas seleccionadas.")

# 2) Exportar Excel
with b_xlsx:
    try:
        # Copia segura y limpia columnas de control antes de exportar
        df_xlsx = st.session_state["df_main"].copy()
        drop_cols = [c for c in ("__DEL__", "DEL") if c in df_xlsx.columns]
        if drop_cols:
            df_xlsx.drop(columns=drop_cols, inplace=True)

        # Si existe COLS_XLSX, respeta ese orden; si no, sigue el actual
        cols_order = globals().get("COLS_XLSX", [])
        if cols_order:
            cols_order = [c for c in cols_order if c in df_xlsx.columns]
            if cols_order:
                df_xlsx = df_xlsx.reindex(columns=cols_order)

        xlsx_b = export_excel(
            df_xlsx,
            sheet_name=TAB_NAME  # (Ajuste 2) usar sheet_name, no 'sheet'
        )
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

# 4) Subir a Sheets
with b_save_sheets:
    if st.button("📤 Subir a Sheets", use_container_width=True):
        df = st.session_state["df_main"][COLS].copy()
        _save_local(df.copy())
        ok, msg = _write_sheet_tab(df.copy())
        st.success(msg) if ok else st.warning(msg)






