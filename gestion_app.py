# ============================
# Gestión — ENI2025 (UNA TABLA con "Área" y formulario + historial)
# ============================
import os
from io import BytesIO
import numpy as np
import pandas as pd
import streamlit as st

# 🔐 Login Google
from auth_google import google_login, logout

# Parche compatibilidad Streamlit 1.50 + st-aggrid
import streamlit.components.v1 as _stc
import types as _types
if not hasattr(_stc, "components"):
    _stc.components = _types.SimpleNamespace(MarshallComponentException=Exception)

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, DataReturnMode

st.set_page_config(page_title="Gestión — ENI2025", layout="wide", initial_sidebar_state="collapsed")

# --- allow-list ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

# 👤 Login
user = google_login(allowed_emails=allowed_emails, allowed_domains=allowed_domains, redirect_page=None)
if not user:
    st.stop()

with st.sidebar:
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        logout()
        st.rerun()

# ================== GOOGLE SHEETS ==================
import json, re

SHEET_URL = os.environ.get("SHEET_URL", "").strip() or (st.secrets.get("SHEET_URL", "").strip() if hasattr(st, "secrets") else "")
SHEET_ID  = os.environ.get("SHEET_ID", "").strip()  or (st.secrets.get("SHEET_ID", "").strip()  if hasattr(st, "secrets") else "")
JSON_PATH = os.environ.get("GCP_SA_JSON_PATH", "eni2025-e19a99dfffd3.json")
TAB_NAME  = "GESTION ENI"   # <- pestaña única en Sheets

def _load_sa_info():
    try:
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            sa = st.secrets["gcp_service_account"]
            if isinstance(sa, str):   return json.loads(sa)
            if isinstance(sa, dict):  return dict(sa)
    except Exception: pass
    try:
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception: pass
    try:
        sa_env = os.environ.get("GCP_SA_JSON", "")
        if sa_env:
            return json.loads(sa_env)
    except Exception: pass
    return None

def _get_spreadsheet_id(s: str) -> str:
    s = (s or "").strip()
    if not s: return ""
    if re.match(r'^[A-Za-z0-9-_]{30,}$', s): return s
    m = re.search(r'/spreadsheets/d/([A-Za-z0-9-_]+)', s)
    return m.group(1) if m else s

def _gs_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception:
        st.error("Falta instalar dependencias: `pip install gspread google-auth`")
        return None
    sa_info = _load_sa_info()
    if not sa_info:
        st.warning("No encontré credenciales del Service Account.")
        return None
    if "private_key" in sa_info and isinstance(sa_info["private_key"], str) and "\\n" in sa_info["private_key"]:
        sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")
    try:
        creds = Credentials.from_service_account_info(sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        gc = gspread.authorize(creds)
        st.session_state["_sa_email"] = sa_info.get("client_email", "(sin email)")
        return gc
    except Exception as e:
        st.warning(f"No pude crear el cliente de Google: {e}")
        return None

def _open_sheet():
    gc = _gs_client()
    if gc is None: return None
    sid = _get_spreadsheet_id(SHEET_URL or SHEET_ID or "")
    if not sid:
        st.warning("Falta `SHEET_URL` o `SHEET_ID`.")
        return None
    try:
        sh = gc.open_by_key(sid)
        try:
            sh.worksheet(TAB_NAME)
        except Exception:
            sh.add_worksheet(title=TAB_NAME, rows=400, cols=60)
        return sh
    except Exception as e:
        st.warning(f"No pude abrir el Sheet (comparte con **{st.session_state.get('_sa_email','(sin email)')}**). Detalle: {e}")
        return None

# ---------- Config ----------
AREAS_OPC = ["Planeamiento", "Base de datos", "Metodología", "Consistencia"]
COMPLEJIDAD = ["Alta", "Media", "Baja"]
PRIORIDAD   = ["Alta", "Media", "Baja"]
ESTADO      = ["No iniciado", "En curso", "Terminado", "Cancelado", "Pausado"]
CUMPLIMIENTO= ["Entregado a tiempo", "Entregado con retraso", "No entregado", "En riesgo de retraso"]
SI_NO       = ["Sí", "No"]

COLS = [
    "Área", "Id", "Tarea", "Tipo", "Responsable", "Fase",
    "Complejidad", "Prioridad", "Estado",
    "Ts_creación", "Ts_en_curso", "Ts_terminado", "Ts_cancelado", "Ts_pausado",
    "Fecha inicio", "Vencimiento", "Fecha fin", "Duración", "Días hábiles",
    "Cumplimiento", "¿Generó alerta?", "Tipo de alerta", "¿Se corrigió?",
    "Fecha detectada", "Fecha corregida",
    "Evaluación", "Calificación"
]
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def now_ts(): return pd.Timestamp.now()

def parse_dt(s):
    s = (s or "").strip()
    v = pd.to_datetime(s, errors="coerce")
    return None if (not s or pd.isna(v)) else v

def combine_dt(date_obj, time_obj):
    """Convierte (date, time) en Timestamp; cualquiera puede ser None."""
    if date_obj is None and time_obj is None:
        return None
    if date_obj is None:
        date_obj = pd.Timestamp.now().date()
    if time_obj is None:
        time_obj = pd.Timestamp(0).time()
    return pd.Timestamp(
        year=date_obj.year, month=date_obj.month, day=date_obj.day,
        hour=time_obj.hour, minute=time_obj.minute
    )

def next_id(df):
    if df.empty or "Id" not in df.columns: return "G1"
    nums = []
    for x in df["Id"].astype(str):
        if x.startswith("G"):
            try: nums.append(int(x[1:]))
            except: pass
    return f"G{(max(nums)+1) if nums else 1}"

def business_days(d1, d2):
    if d1 is None or d2 is None: return None
    s, e = d1.date(), d2.date()
    if e < s: return 0
    return int(np.busday_count(s, e + pd.Timedelta(days=1), weekmask="Mon Tue Wed Thu Fri"))

def duration_days(d1, d2):
    if d1 is None or d2 is None: return None
    return (d2.date() - d1.date()).days

def export_excel(df, sheet="Tareas"):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name=sheet)
    return out.getvalue()

def blank_row():
    return {
        "Área": AREAS_OPC[0],
        "Id": "G1",
        "Tarea": "", "Tipo": "", "Responsable": "", "Fase": "",
        "Complejidad": "Media", "Prioridad": "Media", "Estado": "No iniciado",
        "Ts_creación": now_ts(), "Ts_en_curso": None, "Ts_terminado": None,
        "Ts_cancelado": None, "Ts_pausado": None,
        "Fecha inicio": None, "Vencimiento": None, "Fecha fin": None,
        "Duración": None, "Días hábiles": None,
        "Cumplimiento": "En riesgo de retraso",
        "¿Generó alerta?": "No", "Tipo de alerta": "",
        "¿Se corrigió?": "No", "Fecha detectada": None, "Fecha corregida": None,
        "Evaluación": "Pendiente de revisión",
        "Calificación": 0,
        "__DEL__": False,
    }

def _read_sheet_tab():
    sh = _open_sheet()
    if sh is None: return None
    try:
        ws = sh.worksheet(TAB_NAME)
        recs = ws.get_all_records()
        df = pd.DataFrame(recs) if recs else pd.DataFrame(columns=COLS)
        for c in COLS:
            if c not in df.columns: df[c] = None
        if "Calificación" in df.columns:
            df["Calificación"] = pd.to_numeric(df["Calificación"], errors="coerce").fillna(0).astype(int)
        if "Evaluación" in df.columns:
            df["Evaluación"] = df["Evaluación"].astype(str).replace({"": "Pendiente de revisión"})
        return df[COLS]
    except Exception:
        return pd.DataFrame(columns=COLS)

def _col_letters(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s or "A"

def _write_sheet_tab(df: pd.DataFrame):
    sh = _open_sheet()
    if sh is None: return False, "No se pudo abrir el Sheet."
    try:
        try:
            ws = sh.worksheet(TAB_NAME)
        except Exception:
            ws = sh.add_worksheet(title=TAB_NAME, rows=400, cols=max(26, len(COLS)))

        df_out = df.copy()
        for c in ["Fecha inicio","Vencimiento","Fecha fin","Ts_creación","Ts_en_curso","Ts_terminado","Ts_cancelado","Ts_pausado","Fecha detectada","Fecha corregida"]:
            if c in df_out.columns:
                s = pd.to_datetime(df_out[c], errors="coerce")
                df_out[c] = s.dt.strftime("%Y-%m-%d %H:%M").fillna("")
        if "Calificación" in df_out.columns:
            df_out["Calificación"] = pd.to_numeric(df_out["Calificación"], errors="coerce").fillna(0).astype(int)

        df_out = df_out.reindex(columns=COLS, fill_value="")
        values = [list(df_out.columns)] + df_out.astype(str).fillna("").values.tolist()
        nrows = len(values); ncols = len(COLS); end_col = _col_letters(ncols)
        a1_range = f"'{TAB_NAME}'!A1:{end_col}{nrows}"

        try:
            sh.values_clear(f"'{TAB_NAME}'!A:ZZ")
        except Exception:
            pass

        sh.values_update(
            a1_range,
            params={"valueInputOption": "USER_ENTERED"},
            body={"range": a1_range, "majorDimension": "ROWS", "values": values}
        )
        try:
            ws.resize(rows=max(nrows, 400), cols=max(ncols, 60))
        except Exception:
            pass
        return True, f"Subido a Sheets en pestaña “{TAB_NAME}” ({len(df_out)} filas)."
    except Exception as e:
        return False, f"Error escribiendo en Sheets: {e}"

def _save_local(df: pd.DataFrame):
    path = os.path.join(DATA_DIR, "tareas.csv")
    df.reindex(columns=COLS, fill_value=None).to_csv(path, index=False, encoding="utf-8-sig", mode="w")
    st.session_state["last_saved"] = now_ts()
    try: st.toast("💾 Guardado local", icon="💾")
    except: pass

# ---------- Estado inicial (RESTABLECIDO) ----------
if "df_main" not in st.session_state:
    base = _read_sheet_tab()
    if base is None or len(base) == 0:
        csv_path = os.path.join(DATA_DIR, "tareas.csv")
        base = pd.read_csv(csv_path) if os.path.exists(csv_path) else pd.DataFrame([], columns=COLS)
    for c in COLS:
        if c not in base.columns:
            base[c] = None
    if "__DEL__" not in base.columns:
        base["__DEL__"] = False
    base["__DEL__"] = base["__DEL__"].fillna(False).astype(bool)
    if "Calificación" in base.columns:
        base["Calificación"] = pd.to_numeric(base["Calificación"], errors="coerce").fillna(0).astype(int)
    st.session_state["df_main"] = base[COLS + ["__DEL__"]].copy()

# ---------- CSS (estilos + tabla legible) ----------
st.markdown("""
<style>
/* 1) Elimina las “tarjetas lilas” (fondo, borde, sombra) */
.form-card{
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 0 12px 0 !important;
}
/* 2) Título de sección en celeste suave */
.form-title{
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  background: #EEF6FF !important;
  border: 1px solid #DBE7FF !important;
  color: #1E3A8A !important;
  border-radius: 12px !important;
  padding: 10px 14px !important;
  font-weight: 900 !important;
  font-size: 1.05rem !important;
  margin: 0 0 10px 0 !important;
}
.form-title .plus{ color:#7C3AED!important; font-size:1.15rem!important; }
/* 3) Indicaciones sin rectángulo */
.help-strip{
  background: transparent !important;
  border: 0 !important;
  border-radius: 0 !important;
  padding: 0 !important;
  margin: 6px 0 10px 0 !important;
  color: inherit !important;
  line-height: 1.35 !important;
}
/* 4) Sidebar lila suave */
.stApp [data-testid="stSidebar"]{
  background: #F6F2FF !important;
  border-right: 1px solid #E8DEF8 !important;
}
.stApp [data-testid="stSidebar"] *{ color:#1E1B4B !important; }
.stApp [data-testid="stSidebar"] a{ color:#6B21A8 !important; text-decoration:none!important; }
.stApp [data-testid="stSidebar"] a:hover{ color:#7C3AED!important; text-decoration:underline!important; }
.stApp [data-testid="stSidebar"] .stButton > button{
  background:#F3E8FF!important; border:1px solid #E9D5FF!important; color:#4C1D95!important; border-radius:10px!important;
}
.stApp [data-testid="stSidebar"] .stButton > button:hover{ background:#E9D5FF!important; }
/* 5) AG Grid: que encabezados y celdas no se corten */
.ag-theme-balham .ag-header-cell-label{
  display:block !important;
  white-space: normal !important;
  line-height: 1.2 !important;
}
.ag-theme-balham .ag-header-cell-text{
  white-space: normal !important;
}
.ag-theme-balham .ag-cell{
  white-space: normal !important;
  word-break: break-word !important;
  line-height: 1.25 !important;
  padding-top: 6px !important;
  padding-bottom: 6px !important;
}
.ag-theme-balham .ag-row{ border-bottom: 1px solid #eef1f5 !important; }
.ag-theme-balham .ag-row-odd .ag-cell{ background: #FAFBFD !important; }
.ag-theme-balham .ag-row-hover .ag-cell{ background:#eef6ff!important; }
.ag-theme-balham .ag-row-selected .ag-cell{ background:#e6f0ff!important; }
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
    "💜 Planeamiento": "Planeamiento",
    "💖 Base de datos": "Base de datos",
    "🟧 Metodología": "Metodología",
    "🔷 Consistencia": "Consistencia",
}
EMO_COMPLEJIDAD = {"🔴 Alta": "Alta", "🟡 Media": "Media", "🟢 Baja": "Baja"}
EMO_PRIORIDAD   = {"🔥 Alta": "Alta", "✨ Media": "Media", "🍃 Baja": "Baja"}
EMO_ESTADO      = {"🍼 No iniciado": "No iniciado","⏳ En curso": "En curso","✅ Terminado": "Terminado","🛑 Cancelado": "Cancelado","⏸️ Pausado": "Pausado"}
EMO_SI_NO       = {"✅ Sí": "Sí", "🚫 No": "No"}

# ================== Formulario ==================
st.markdown('<div class="form-card">', unsafe_allow_html=True)
st.markdown('<div class="form-title"><span class="plus">➕</span><span class="secico">📝</span> Nueva tarea</div>', unsafe_allow_html=True)

st.markdown("""
<div class="help-strip">
  ✳️ <strong>Completa los campos principales</strong> para registrar una nueva tarea.
</div>
""", unsafe_allow_html=True)

with st.form("form_nueva_tarea", clear_on_submit=True):
    COLS_FORM = [1.1, 1.1, 2.4, 1.3, 1.3]
    r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(COLS_FORM)
    area = _opt_map(r1c1, "Área", EMO_AREA, "Planeamiento")
    fase = r1c2.text_input("Fase", placeholder="Etapa")
    tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea")
    tipo  = r1c4.text_input("Tipo", placeholder="Tipo o categoría")
    resp  = r1c5.text_input("Responsable", placeholder="Nombre")

    s2c1, s2c2, s2c3, s2c4, s2c5 = st.columns(COLS_FORM)
    estado = _opt_map(s2c1, "Estado", EMO_ESTADO, "No iniciado")
    compl  = _opt_map(s2c2, "Complejidad", EMO_COMPLEJIDAD, "Media")

    sub3a, sub3b, sub3c = s2c3.columns([0.7, 0.8, 1.5])
    prio   = _opt_map(sub3a, "Prioridad", EMO_PRIORIDAD, "Media")

    # Calendarios: Fecha + Hora
    fi_d = sub3b.date_input("Fecha inicio (fecha)", value=None)
    fi_t = sub3c.time_input("Hora inicio", value=None, step=60) if fi_d else None

    v_d  = s2c4.date_input("Vencimiento (fecha)", value=None)
    v_t  = s2c4.time_input("Hora vencimiento", value=None, step=60, label_visibility="collapsed") if v_d else None

    ff_d = s2c5.date_input("Fecha fin (fecha)", value=None)
    ff_t = s2c5.time_input("Hora fin", value=None, step=60, label_visibility="collapsed") if ff_d else None

    submitted = st.form_submit_button("Agregar y guardar")
    if submitted:
        df = st.session_state["df_main"].copy()
        new = blank_row()
        f_ini = combine_dt(fi_d, fi_t)
        f_ven = combine_dt(v_d,  v_t)
        f_fin = combine_dt(ff_d, ff_t)
        new.update({
            "Área": area, "Id": next_id(df), "Tarea": tarea, "Tipo": tipo,
            "Responsable": resp, "Fase": fase,
            "Complejidad": compl, "Prioridad": prio, "Estado": estado,
            "Fecha inicio": f_ini, "Vencimiento": f_ven, "Fecha fin": f_fin,
        })
        new["Duración"]     = duration_days(new["Fecha inicio"], new["Vencimiento"])
        new["Días hábiles"] = business_days(new["Fecha inicio"], new["Vencimiento"])

        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        st.session_state["df_main"] = df.copy()
        path_ok = os.path.join("data", "tareas.csv")
        os.makedirs("data", exist_ok=True)
        df.reindex(columns=COLS, fill_value=None).to_csv(path_ok, index=False, encoding="utf-8-sig", mode="w")
        ok, msg = _write_sheet_tab(df[COLS].copy())
        st.success(f"✔ Tarea agregada ({new['Id']}). {msg}") if ok else st.warning(f"Agregado localmente. {msg}")

st.markdown('</div>', unsafe_allow_html=True)

# ================== Nueva alerta ==================
st.markdown('<div class="form-card">', unsafe_allow_html=True)
st.markdown('<div class="form-title"><span class="plus">➕</span><span class="secico">⚠️</span> Nueva alerta</div>', unsafe_allow_html=True)

st.markdown("""
<div class="help-strip">
  ⚠️ <strong>Vincula una alerta</strong> a una tarea ya registrada.
</div>
""", unsafe_allow_html=True)

with st.form("form_nueva_alerta", clear_on_submit=True):
    # Fila: Colocar ID | Tarea (auto)
    df_ids = st.session_state["df_main"].copy()
    col_id, col_tarea = st.columns([1.0, 3.0])
    id_target = col_id.text_input("Colocar ID", value="", placeholder="Ej: G1")
    tarea_auto = ""
    if id_target:
        m = df_ids["Id"].astype(str) == str(id_target).strip()
        if m.any():
            tarea_auto = df_ids.loc[m, "Tarea"].astype(str).iloc[0]
    col_tarea.text_input("Tarea", value=tarea_auto, disabled=True)

    # Resto de campos
    c1, c2, c3, c4, c5 = st.columns([1.0, 1.6, 1.4, 1.0, 1.6])
    genero_alerta = _opt_map(c1, "¿Generó alerta?", EMO_SI_NO, "No")
    tipo_alerta   = c2.text_input("Tipo de alerta", placeholder="(opcional)")

    # Calendarios en alerta
    fa_d = c3.date_input("Fecha de alerta (fecha)", value=None)
    fa_t = c3.time_input("Hora alerta", value=None, step=60, label_visibility="collapsed") if fa_d else None

    corr_alerta   = _opt_map(c4, "¿Se corrigió la alerta?", EMO_SI_NO, "No")

    fc_d = c5.date_input("Fecha alerta corregida (fecha)", value=None)
    fc_t = c5.time_input("Hora alerta corregida", value=None, step=60, label_visibility="collapsed") if fc_d else None

    sub_alerta = st.form_submit_button("Vincular alerta a tarea")
    if sub_alerta:
        if not id_target or id_target not in st.session_state["df_main"]["Id"].astype(str).values:
            st.warning("ID no encontrado en el historial de tareas.")
        else:
            df = st.session_state["df_main"].copy()
            m = df["Id"].astype(str) == str(id_target)
            df.loc[m, "¿Generó alerta?"] = genero_alerta
            df.loc[m, "Tipo de alerta"]  = tipo_alerta
            df.loc[m, "Fecha detectada"] = combine_dt(fa_d, fa_t)
            df.loc[m, "¿Se corrigió?"]   = corr_alerta
            df.loc[m, "Fecha corregida"] = combine_dt(fc_d, fc_t)

            st.session_state["df_main"] = df.copy()
            _save_local(df[COLS].copy())
            ok, msg = _write_sheet_tab(df[COLS].copy())
            st.success(f"✔ Alerta vinculada a la tarea {id_target}. {msg}") if ok else st.warning(f"Actualizado localmente. {msg}")

st.markdown('</div>', unsafe_allow_html=True)

# ================== Historial ==================
st.subheader("📝 Tareas recientes")

# ---- FILA DE 3 FILTROS: Área, Estado, Responsable ----
df_view = st.session_state["df_main"].copy()

cA, cE, cR = st.columns([1, 1, 1.4])

area_sel   = cA.selectbox("Área", options=["Todas"] + AREAS_OPC, index=0)
estado_sel = cE.selectbox("Estado", options=["Todos"] + ESTADO, index=0)

responsables = sorted([x for x in df_view["Responsable"].astype(str).unique() if x and x != "nan"])
resp_sel = cR.selectbox("Responsable", options=["Todos"] + responsables, index=0)

# Aplicar filtros
if area_sel != "Todas":
    df_view = df_view[df_view["Área"] == area_sel]
if estado_sel != "Todos":
    df_view = df_view[df_view["Estado"] == estado_sel]
if resp_sel != "Todos":
    df_view = df_view[df_view["Responsable"].astype(str) == resp_sel]

for c in COLS:
    if c not in df_view.columns: df_view[c] = None
if "__DEL__" not in df_view.columns: df_view["__DEL__"] = False
df_view["__DEL__"] = df_view["__DEL__"].fillna(False).astype(bool)

for c in ["Fecha inicio","Vencimiento","Fecha fin"]:
    if c in df_view.columns: df_view[c] = pd.to_datetime(df_view[c], errors="coerce")

# === ORDEN DE COLUMNAS: Id primero, luego Área y el resto ===
grid_cols = ["Id", "Área"] + [c for c in COLS if c not in ("Id", "Área")]
df_view = df_view[grid_cols + ["__DEL__"]]

# === GRID OPTIONS ===
gob = GridOptionsBuilder.from_dataframe(df_view)

# que TODAS las columnas sean redimensionables, con wrap y alto automático
gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True)

gob.configure_grid_options(
    rowSelection="multiple",
    suppressRowClickSelection=True,
    domLayout="normal",
    rowHeight=38,
    headerHeight=72,           # ← más alto para títulos en 2–3 líneas
    wrapHeaderText=True,       # ← permitir saltos en encabezado
    autoHeaderHeight=True,     # ← calcular alto automáticamente
    enableRangeSelection=True,
    enableCellTextSelection=True,
    singleClickEdit=True,
    stopEditingWhenCellsLoseFocus=True,
    undoRedoCellEditing=True,
    enterMovesDown=True,
    getRowId=JsCode("function(p){ return (p.data && (p.data.Id || p.data['Id'])) + ''; }"),
)

gob.configure_selection("multiple", use_checkbox=True)

# Dejar Id y Área a la izquierda visibles
gob.configure_column("Id",   editable=False, width=110, pinned="left")
gob.configure_column("Área", editable=True,  width=160, pinned="left")

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
  else if(v==='Entregado con retraso'){bg='#00ACC1'}
  else if(v==='No entregado'){bg='#006064'}
  else if(v==='En riesgo de retraso'){bg='#0277BD'}
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
    gob.configure_column(c, editable=True, minWidth=colw[c], flex=fx, valueFormatter=fmt_dash)

for c in ["Complejidad", "Prioridad"]:
    gob.configure_column(c, editable=True, cellEditor="agSelectCellEditor",
                         cellEditorParams={"values": ["Alta","Media","Baja"]},
                         valueFormatter=flag_formatter, minWidth=colw[c], maxWidth=220, flex=1)

for c, vals in [("Estado", ESTADO), ("Cumplimiento", CUMPLIMIENTO), ("¿Generó alerta?", SI_NO),
                ("¿Se corrigió?", SI_NO), ("Evaluación", ["Aprobada","Desaprobada","Pendiente de revisión","Observada","Cancelada","Pausada"])]:
    gob.configure_column(c, editable=True, cellEditor="agSelectCellEditor",
                         cellEditorParams={"values": vals}, cellStyle=chip_style, valueFormatter=fmt_dash,
                         minWidth=colw.get(c, 120), maxWidth=260, flex=1)

gob.configure_column("Calificación", editable=True, valueFormatter=stars_fmt,
                     minWidth=colw["Calificación"], maxWidth=140, flex=0)

# Editor de fecha/hora
date_time_editor = JsCode("""
class DateTimeEditor{
  init(p){ this.eInput=document.createElement('input'); this.eInput.type='datetime-local';
    this.eInput.classList.add('ag-input'); this.eInput.style.width='100%';
    const v=p.value?new Date(p.value):null;
    if(v&&!isNaN(v.getTime())){ const pad=n=>String(n).padStart(2,'0');
      this.eInput.value=v.getFullYear()+'-'+pad(v.getMonth()+1)+'-'+pad(v.getDate())+'T'+pad(v.getHours())+':'+pad(v.getMinutes()); } }
  getGui(){return this.eInput} afterGuiAttached(){this.eInput.focus()} getValue(){return this.eInput.value} }""")

date_time_fmt = JsCode("""
function(p){ if(p.value===null||p.value===undefined) return '—';
  const d=new Date(String(p.value).trim()); if(isNaN(d.getTime())) return '—';
  const pad=n=>String(n).padStart(2,'0');
  return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes()); }""")

for c in ["Fecha inicio","Vencimiento","Fecha fin"]:
    gob.configure_column(c, editable=True, cellEditor=date_time_editor, valueFormatter=date_time_fmt,
                         minWidth=colw[c], maxWidth=200, flex=1)

dur_getter = JsCode("function(p){const s=p.data['Fecha inicio'],e=p.data['Vencimiento'];if(!s||!e)return null;const sd=new Date(s),ed=new Date(e);if(isNaN(sd.getTime()))return null;return Math.floor((ed-sd)/(1000*60*60*24));}")
bd_getter  = JsCode("function(p){const s=p.data['Fecha inicio'],e=p.data['Vencimiento'];if(!s||!e)return null;let sd=new Date(s),ed=new Date(e);if(isNaN(sd.getTime()))return null;if(ed<sd)return 0;sd=new Date(sd.getFullYear(),sd.getMonth(),sd.getDate());ed=new Date(ed.getFullYear(),ed.getMonth(),ed.getDate());let c=0;const one=24*60*60*1000;for(let t=sd.getTime();t<=ed.getTime();t+=one){const d=new Date(t).getDay();if(d!==0&&d!==6)c++;}return c;}")

gob.configure_column("Duración", editable=False, valueGetter=dur_getter, valueFormatter=fmt_dash, minWidth=colw["Duración"], maxWidth=130, flex=0)
gob.configure_column("Días hábiles", editable=False, valueGetter=bd_getter, valueFormatter=fmt_dash, minWidth=colw["Días hábiles"], maxWidth=140, flex=0)

# Tooltips en headers
for col in df_view.columns:
    gob.configure_column(col, headerTooltip=col)

grid = AgGrid(
    df_view, key="grid_historial", gridOptions=gob.build(), height=500,
    fit_columns_on_grid_load=True, data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
    update_mode=(GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED | GridUpdateMode.FILTERING_CHANGED | GridUpdateMode.SORTING_CHANGED | GridUpdateMode.SELECTION_CHANGED),
    allow_unsafe_jscode=True, theme="balham",
)

# Sincroniza ediciones por Id
if isinstance(grid, dict) and "data" in grid and grid["data"] is not None:
    try:
        edited = pd.DataFrame(grid["data"]).copy()
        base = st.session_state["df_main"].copy().set_index("Id")
        st.session_state["df_main"] = base.combine_first(edited.set_index("Id")).reset_index()
    except Exception:
        pass

# ---- Botones (más juntos y a la izquierda) ----
b1, b2, b3, _spacer = st.columns([0.18, 0.19, 0.20, 0.43])
with b1:
    sel_rows = grid.get("selected_rows", []) if isinstance(grid, dict) else []
    if st.button("🗑️ Borrar seleccionadas"):
        ids = pd.DataFrame(sel_rows)["Id"].astype(str).tolist() if sel_rows else []
        if ids:
            df0 = st.session_state["df_main"]
            st.session_state["df_main"] = df0[~df0["Id"].astype(str).isin(ids)].copy()
            st.success(f"Eliminadas {len(ids)} fila(s).")
        else:
            st.warning("No hay filas seleccionadas.")
with b2:
    try:
        xlsx_b = export_excel(st.session_state["df_main"][COLS], sheet=TAB_NAME)
        st.download_button("⬇️ Exportar Excel", data=xlsx_b, file_name="tareas.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        st.error(f"No pude generar Excel: {e}")
with b3:
    if st.button("💾 Guardar en Sheets"):
        df = st.session_state["df_main"][COLS].copy()
        _save_local(df.copy())
        ok, msg = _write_sheet_tab(df.copy())
        st.success(msg) if ok else st.warning(msg)
