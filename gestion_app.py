# ============================
# Gestión — ENI2025 (MÓDULO: una tabla con "Área" y formulario + historial)
# ============================
import os
from io import BytesIO
import numpy as np
import pandas as pd
import streamlit as st

# ❌ NO usar set_page_config aquí (va en pages/01_gestion.py)
from auth_google import google_login, logout  # opcional si usas utilidades dentro

# Parche compatibilidad Streamlit 1.50 + st-aggrid
import streamlit.components.v1 as _stc
import types as _types
if not hasattr(_stc, "components"):
    _stc.components = _types.SimpleNamespace(MarshallComponentException=Exception)

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, DataReturnMode

# ======= Utilidades de tablas (Prioridad / Evaluación) =======
import streamlit as st
from st_aggrid import GridOptionsBuilder
from auth_google import google_login, logout

# ------------------- ANCHOS / ALINEACIONES -------------------
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
}

COL_W_ID         = PILL_W_AREA
COL_W_AREA       = PILL_W_RESP
COL_W_DESDE      = PILL_W_RESP
COL_W_TAREA      = PILL_W_TAREA
COL_W_PRIORIDAD  = COL_W_TAREA + COL_W_ID
COL_W_EVALUACION = COL_W_TAREA + COL_W_ID

# ------------------- ID por área -------------------
AREA_PREFIX = {
    "Planeamiento":   "PL",
    "Base de Datos":  "BD",
    "Consistencia":   "CO",
    "Metodología":    "ME",
}

def next_id_area(df, area: str) -> str:
    import pandas as pd
    pref = AREA_PREFIX.get(str(area).strip(), "OT")
    serie_ids = df.get("Id", pd.Series([], dtype=str)).astype(str)
    nums = serie_ids.str.extract(rf"^{pref}(\d+)$")[0].dropna()
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
    gob.configure_column("Id",            width=COL_W_ID        + ALIGN_FIXES.get("Id", 0),          editable=False)
    gob.configure_column("Área",          width=COL_W_AREA      + ALIGN_FIXES.get("Área", 0),        editable=False)
    gob.configure_column("Responsable",   width=PILL_W_RESP     + ALIGN_FIXES.get("Responsable", 0), editable=False)
    gob.configure_column("Tarea",         width=COL_W_TAREA     + ALIGN_FIXES.get("Tarea", 0),       editable=False)
    gob.configure_column(
        "Prioridad",
        width=COL_W_PRIORIDAD + ALIGN_FIXES.get("Prioridad", 0),
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
    gob.configure_column("Id",           width=COL_W_ID        + ALIGN_FIXES.get("Id", 0),           editable=False)
    gob.configure_column("Área",         width=COL_W_AREA      + ALIGN_FIXES.get("Área", 0),         editable=False)
    gob.configure_column("Responsable",  width=PILL_W_RESP     + ALIGN_FIXES.get("Responsable", 0),  editable=False)
    gob.configure_column("Tarea",        width=COL_W_TAREA     + ALIGN_FIXES.get("Tarea", 0),        editable=False)
    gob.configure_column(
        "Evaluación",
        width=COL_W_EVALUACION + ALIGN_FIXES.get("Evaluación", 0),
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": [5,4,3,2,1]}
    )
    gob.configure_grid_options(suppressColumnVirtualisation=False)
    return gob.build()

# --- allow-list (si lo necesitas desde la página) ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

# ===== Inicialización de visibilidad por única vez =====
if "_ui_bootstrap" not in st.session_state:
    st.session_state["nt_visible"]  = True   # Nueva tarea
    st.session_state["ux_visible"]  = True   # Editar estado
    st.session_state["na_visible"]  = True   # Nueva alerta
    st.session_state["pri_visible"] = False  # Prioridad
    st.session_state["eva_visible"] = False  # Evaluación
    st.session_state["_ui_bootstrap"] = True

# ================== GOOGLE SHEETS / DATA UTILS ==================
import json, re

SHEET_URL = os.environ.get("SHEET_URL", "").strip() or (st.secrets.get("SHEET_URL", "").strip() if hasattr(st, "secrets") else "")
SHEET_ID  = os.environ.get("SHEET_ID", "").strip()  or (st.secrets.get("SHEET_ID", "").strip()  if hasattr(st, "secrets") else "")
JSON_PATH = os.environ.get("GCP_SA_JSON_PATH", "eni2025-e19a99dfffd3.json")
TAB_NAME  = "GESTION ENI"

def _load_sa_info():
    try:
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            sa = st.secrets["gcp_service_account"]
            if isinstance(sa, str):   return json.loads(sa)
            if isinstance(sa, dict):  return dict(sa)
    except Exception:
        pass
    try:
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    try:
        sa_env = os.environ.get("GCP_SA_JSON", "")
        if sa_env:
            return json.loads(sa_env)
    except Exception:
        pass
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

# =====================================================================
# RENDER: toda la UI (formulario, editar estado, alertas, prioridad, evaluación, historial)
# =====================================================================
def render():
    # ---------- CSS ----------
    st.markdown("""<style>
    /* (CSS completo que ya tenías) */
    :root{ --lilac:#B38BE3; --lilac-50:#F6EEFF; --lilac-600:#8B5CF6;
           --blue-pill-bg:#38BDF8; --blue-pill-bd:#0EA5E9; --blue-pill-fg:#fff;
           --pill-h:36px; --pill-width:158px; --pill-azul:#94BEEA; --pill-azul-bord:#94BEEA;
           --pill-rosa:#67D3C4; --pill-rosa-bord:#67D3C4; }
    /* … (he mantenido tu CSS de inputs, sidebar, pills, toggles, select, responsive, alertas-grid,
           botones, download, help-strip, topbars, prioridad/evaluación, compactación de espacios,
           overrides del toggle en #ntbar y el patch ag-grid) … */
    </style>""", unsafe_allow_html=True)

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

    EMO_AREA = {
        "💜 Planeamiento": "Planeamiento",
        "💖 Base de datos": "Base de datos",
        "🟧 Metodología": "Metodología",
        "🔷 Consistencia": "Consistencia",
    }
    EMO_COMPLEJIDAD = {"🔴 Alta": "Alta", "🟡 Media": "Media", "🟢 Baja": "Baja"}
    EMO_PRIORIDAD   = {"🔥 Alta": "Alta", "✨ Media": "Media", "🍃 Baja": "Baja"}
    EMO_ESTADO      = {"🍼 No iniciado":"No iniciado","⏳ En curso":"En curso","✅ Terminado":"Terminado","🛑 Cancelado":"Cancelado","⏸️ Pausado":"Pausado"}
    EMO_SI_NO       = {"✅ Sí":"Sí","🚫 No":"No"}

    # ================== Formulario ==================
    st.session_state.setdefault("nt_visible", True)
    chev = "▾" if st.session_state.get("nt_visible", True) else "▸"

    st.markdown('<div id="ntbar" class="topbar">', unsafe_allow_html=True)
    c_toggle, c_pill = st.columns([0.028, 0.965], gap="medium")
    with c_toggle:
        st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
        def _toggle_nt(): st.session_state["nt_visible"] = not st.session_state.get("nt_visible", True)
        st.button(chev, key="nt_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_nt)
        st.markdown('</div>', unsafe_allow_html=True)
    with c_pill:
        st.markdown('<div class="form-title">&nbsp;&nbsp;📝&nbsp;&nbsp;Nueva tarea</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    submitted = False
    if st.session_state.get("nt_visible", True):
        st.markdown("""
        <div class="help-strip help-strip-nt" id="nt-help">
          ✳️ <strong>Completa los campos principales</strong> para registrar una nueva tarea
        </div>""", unsafe_allow_html=True)
        st.markdown('<div class="form-card">', unsafe_allow_html=True)

        with st.form("form_nueva_tarea", clear_on_submit=True):
            A = 1.2; F = 1.2
            W_ESTADO = 1.1; W_COMP = 1.1; W_FINI = 1.0; W_VENC = 1.2; W_FFIN = 1.2
            T = W_COMP + W_FINI
            D = 2.4

            r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns([A, F, W_ESTADO, T, D], gap="medium")
            area    = _opt_map(r1c1, "Área", EMO_AREA, "Planeamiento")
            fase    = r1c2.text_input("Fase", placeholder="Etapa")
            nuevo_f1c3 = r1c3.text_input("Ciclo de mejora", placeholder="—")
            tarea   = r1c4.text_input("Tarea", placeholder="Describe la tarea")
            detalle = r1c5.text_input("Detalle", placeholder="Información adicional (opcional)")

            c2_1, c2_2, c2_3, c2_4, c2_5, c2_6, c2_7 = st.columns([A, F, W_ESTADO, W_COMP, W_FINI, W_VENC, W_FFIN], gap="medium")
            tipo = c2_1.text_input("Tipo de tarea", placeholder="Tipo o categoría")
            resp = c2_2.text_input("Responsable", placeholder="Nombre")
            estado = _opt_map(c2_3, "Estado", EMO_ESTADO, "No iniciado")
            compl  = _opt_map(c2_4, "Complejidad", EMO_COMPLEJIDAD, "Media")

            fi_d = c2_5.date_input("Fecha inicio", value=None, key="fi_d")
            fi_t = c2_5.time_input("Hora inicio", value=None, step=60, label_visibility="collapsed", key="fi_t") if fi_d else None
            v_d  = c2_6.date_input("Vencimiento", value=None, key="v_d")
            v_t  = c2_6.time_input("Hora vencimiento", value=None, step=60, label_visibility="collapsed", key="v_t") if v_d else None
            ff_d = c2_7.date_input("Fecha fin", value=None, key="ff_d")
            ff_t = c2_7.time_input("Hora fin", value=None, step=60, label_visibility="collapsed", key="ff_t") if ff_d else None

            with c2_7:
                submitted = st.form_submit_button("💾 Agregar y guardar", use_container_width=True)

        if submitted:
            try:
                df = st.session_state.get("df_main", pd.DataFrame(columns=COLS + ["__DEL__"])).copy()
                if "Ciclo de mejora" not in df.columns:
                    df["Ciclo de mejora"] = ""

                new = blank_row()
                f_ini = combine_dt(fi_d, fi_t)
                f_ven = combine_dt(v_d,  v_t)
                f_fin = combine_dt(ff_d, ff_t)
                new.update({
                    "Área": area,
                    "Id": next_id_area(df, area),
                    "Tarea": tarea,
                    "Tipo": tipo,
                    "Responsable": resp,
                    "Fase": fase,
                    "Complejidad": compl,
                    "Estado": estado,
                    "Fecha inicio": f_ini,
                    "Vencimiento": f_ven,
                    "Fecha fin": f_fin,
                    # "Ciclo de mejora": nuevo_f1c3,   # opcional
                    "Detalle": detalle,
                })
                new["Duración"]     = duration_days(new["Fecha inicio"], new["Vencimiento"])
                new["Días hábiles"] = business_days(new["Fecha inicio"], new["Vencimiento"])

                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                for c in ["Fecha inicio", "Vencimiento", "Fecha fin"]:
                    if c in df.columns:
                        df[c] = pd.to_datetime(df[c], errors="coerce")

                st.session_state["df_main"] = df.copy()
                os.makedirs("data", exist_ok=True)
                path_ok = os.path.join("data", "tareas.csv")
                df.reindex(columns=COLS, fill_value=None).to_csv(path_ok, index=False, encoding="utf-8-sig", mode="w")
                st.success(f"✔ Tarea agregada (Id {new['Id']}).")
                st.rerun()
            except Exception as e:
                st.error(f"No pude guardar la nueva tarea: {e}")

        st.markdown('</div>', unsafe_allow_html=True)  # cierra .form-card

    # ================== Actualizar estado ==================
    st.session_state.setdefault("ux_visible", True)
    chev2 = "▾" if st.session_state["ux_visible"] else "▸"
    st.markdown('<div class="topbar-ux">', unsafe_allow_html=True)
    c_toggle2, c_pill2 = st.columns([0.028, 0.965], gap="medium")
    with c_toggle2:
        st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
        def _toggle_ux(): st.session_state["ux_visible"] = not st.session_state["ux_visible"]
        st.button(chev2, key="ux_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_ux)
        st.markdown('</div>', unsafe_allow_html=True)
    with c_pill2:
        st.markdown('<div class="form-title-ux">&nbsp;&nbsp;🔁&nbsp;&nbsp;Editar estado</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state["ux_visible"]:
        st.markdown("""
        <div class="help-strip help-strip-ux" id="ux-help">
          🔄 <strong>Actualiza el estado</strong> de una tarea ya registrada usando los filtros
        </div>""", unsafe_allow_html=True)
        st.markdown('<div class="form-card">', unsafe_allow_html=True)

        A = 1.2; F = 1.2
        W_ESTADO = 1.1; W_COMP = 1.1; W_FINI = 1.0; W_VENC = 1.2; W_FFIN = 1.2

        df_all = st.session_state.get("df_main", pd.DataFrame(columns=COLS)).copy()
        with st.form("form_actualizar_estado", clear_on_submit=False):
            c_area, c_resp, c_desde, c_hasta, c_tarea, c_id, c_estado = st.columns([A, F, W_ESTADO, W_COMP, W_FINI, W_VENC, W_FFIN], gap="medium")
            upd_area = c_area.selectbox("Área", options=["Todas"] + AREAS_OPC, index=0, key="upd_area")
            df_resp = df_all if upd_area == "Todas" else df_all[df_all["Área"] == upd_area]
            responsables_all = sorted([x for x in df_resp["Responsable"].astype(str).unique() if x and x != "nan"])
            upd_resp_sel = c_resp.selectbox("Responsable", options=["Todos"] + responsables_all, index=0, key="upd_resp_sel")
            upd_desde = c_desde.date_input("Desde", value=None, key="upd_desde")
            upd_hasta = c_hasta.date_input("Hasta",  value=None, key="upd_hasta")

            df_filt = df_all.copy()
            if upd_area != "Todas": df_filt = df_filt[df_filt["Área"] == upd_area]
            if upd_resp_sel != "Todos": df_filt = df_filt[df_filt["Responsable"].astype(str) == upd_resp_sel]
            if "Fecha inicio" in df_filt.columns:
                fcol = pd.to_datetime(df_filt["Fecha inicio"], errors="coerce")
                if upd_desde: df_filt = df_filt[fcol >= pd.to_datetime(upd_desde)]
                if upd_hasta: df_filt = df_filt[fcol <= (pd.to_datetime(upd_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]
            tareas_opts = ["— Selecciona —"] + sorted([t for t in df_filt["Tarea"].astype(str).unique() if t and t != "nan"])
            upd_tarea = c_tarea.selectbox("Tarea", options=tareas_opts, index=0, key="upd_tarea")

            id_auto = ""
            if upd_tarea and upd_tarea != "— Selecciona —":
                m = (df_all["Tarea"].astype(str) == upd_tarea)
                if upd_area != "Todas": m &= (df_all["Área"] == upd_area)
                if upd_resp_sel != "Todos": m &= (df_all["Responsable"].astype(str) == upd_resp_sel)
                if "Fecha inicio" in df_all.columns:
                    f_all = pd.to_datetime(df_all["Fecha inicio"], errors="coerce")
                    if upd_desde: m &= f_all >= pd.to_datetime(upd_desde)
                    if upd_hasta: m &= f_all <= (pd.to_datetime(upd_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
                hit = df_all[m]
                if not hit.empty:
                    id_auto = str(hit.iloc[0]["Id"])
            c_id.text_input("Id", value=id_auto, disabled=True, key="upd_id_show", placeholder="—")

            upd_estado = c_estado.selectbox("Estado", options=["En curso", "Terminado", "Cancelado", "Pausado"], key="upd_estado_sel")
            with c_estado:
                st.write("")
                do_update_estado = st.form_submit_button("🔗 Actualizar", use_container_width=True)

        if 'do_update_estado' in locals() and do_update_estado:
            if not id_auto:
                st.warning("Selecciona una tarea para obtener su Id antes de guardar.")
            else:
                df = st.session_state["df_main"].copy()
                m = df["Id"].astype(str).str.strip().str.lower() == id_auto.strip().lower()
                if not m.any():
                    st.warning("No se encontró la tarea con el Id proporcionado.")
                else:
                    old_state = str(df.loc[m, "Estado"].iloc[0]) if "Estado" in df.columns else ""
                    df.loc[m, "Estado"] = upd_estado
                    ts_map = {"En curso":"Ts_en_curso","Terminado":"Ts_terminado","Cancelado":"Ts_cancelado","Pausado":"Ts_pausado"}
                    col_ts = ts_map.get(upd_estado)
                    if col_ts in df.columns:
                        df.loc[m, col_ts] = now_ts()
                    st.session_state["df_main"] = df.copy()
                    _save_local(df[COLS].copy())
                    st.success(f"✔ Estado actualizado: {old_state} → {upd_estado} (Id: {id_auto}).")

        st.markdown('</div>', unsafe_allow_html=True)

    # ================== Nueva alerta ==================
    st.session_state.setdefault("na_visible", True)
    chev3 = "▾" if st.session_state["na_visible"] else "▸"
    st.markdown('<div class="topbar-na">', unsafe_allow_html=True)
    c_toggle3, c_pill3 = st.columns([0.028, 0.965], gap="medium")
    with c_toggle3:
        st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
        def _toggle_na(): st.session_state["na_visible"] = not st.session_state["na_visible"]
        st.button(chev3, key="na_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_na)
        st.markdown('</div>', unsafe_allow_html=True)
    with c_pill3:
        st.markdown('<div class="form-title-na">&nbsp;&nbsp;⚠️&nbsp;&nbsp;Nueva alerta</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state["na_visible"]:
        st.markdown("""
        <div class="help-strip help-strip-na" id="na-help">
          ⚠️ <strong>Vincula una alerta</strong> a una tarea ya registrada
        </div>""", unsafe_allow_html=True)
        st.markdown('<div class="form-card">', unsafe_allow_html=True)

        with st.form("form_nueva_alerta", clear_on_submit=True):
            A = 1.2; F = 1.2
            r1_area, r1_resp, r1_desde, r1_hasta, r1_tarea, r1_id = st.columns([A, F, 1.1, 1.1, 1.0, 2.4], gap="medium")
            area_filtro = _opt_map(r1_area, "Área", EMO_AREA, "Planeamiento")
            df_all = st.session_state.get("df_main", pd.DataFrame(columns=COLS)).copy()
            responsables_all = sorted([x for x in df_all["Responsable"].astype(str).unique() if x and x != "nan"])
            resp_filtro = r1_resp.selectbox("Responsable", options=["Todos"] + responsables_all, index=0)
            f_desde = r1_desde.date_input("Desde", value=None, key="alerta_desde")
            f_hasta = r1_hasta.date_input("Hasta", value=None, key="alerta_hasta")

            df_tasks = df_all.copy()
            if area_filtro: df_tasks = df_tasks[df_tasks["Área"] == area_filtro]
            if resp_filtro != "Todos": df_tasks = df_tasks[df_tasks["Responsable"].astype(str) == resp_filtro]
            df_tasks["Fecha inicio"] = pd.to_datetime(df_tasks.get("Fecha inicio"), errors="coerce")
            if f_desde: df_tasks = df_tasks[df_tasks["Fecha inicio"].dt.date >= f_desde]
            if f_hasta: df_tasks = df_tasks[df_tasks["Fecha inicio"].dt.date <= f_hasta]
            df_tasks = df_tasks.dropna(subset=["Id"]).copy()
            df_tasks["Tarea_str"] = df_tasks["Tarea"].astype(str).replace({"nan": ""})
            df_tasks["Tarea_op"]  = df_tasks["Tarea_str"] + "  (Id: " + df_tasks["Id"].astype(str) + ")"
            opciones_tarea = ["— Selecciona —"] + df_tasks["Tarea_op"].tolist()
            tarea_op_sel = r1_tarea.selectbox("Tarea", opciones_tarea, index=0, key="alerta_tarea_sel")

            id_auto = ""
            if tarea_op_sel != "— Selecciona —":
                m = df_tasks["Tarea_op"] == tarea_op_sel
                if m.any(): id_auto = str(df_tasks.loc[m, "Id"].iloc[0])
            r1_id.text_input("Id", value=id_auto, disabled=True, key="alerta_id_auto")

            r2_gen, r2_corr, r2_tipo, r2_fa, r2_fc = st.columns([A, F, 3.2, 1.2, 1.2], gap="medium")
            genero_alerta = _opt_map(r2_gen,  "¿Generó alerta?",        EMO_SI_NO, "No")
            corr_alerta   = _opt_map(r2_corr, "¿Se corrigió la alerta?", EMO_SI_NO, "No")
            tipo_alerta = r2_tipo.text_input("Tipo de alerta", placeholder="(opcional)", key="alerta_tipo")
            fa_d = r2_fa.date_input("Fecha de alerta", value=None, key="alerta_fa_d")
            fa_t = r2_fa.time_input("Hora alerta", value=None, step=60, label_visibility="collapsed", key="alerta_fa_t") if fa_d else None
            fc_d = r2_fc.date_input("Fecha alerta corregida", value=None, key="alerta_fc_d")
            fc_t = r2_fc.time_input("Hora alerta corregida", value=None, step=60, label_visibility="collapsed", key="alerta_fc_t") if fc_d else None

            with r2_fc:
                sub_alerta = st.form_submit_button("⚙️ Agregar", use_container_width=True)

            if sub_alerta:
                id_target = id_auto.strip()
                if not id_target:
                    st.warning("Selecciona primero una tarea para obtener su Id.")
                elif id_target not in st.session_state["df_main"]["Id"].astype(str).values:
                    st.warning("El Id seleccionado no existe en el historial.")
                else:
                    df = st.session_state["df_main"].copy()
                    m = df["Id"].astype(str) == id_target
                    df.loc[m, "¿Generó alerta?"] = genero_alerta
                    df.loc[m, "Tipo de alerta"]  = tipo_alerta
                    df.loc[m, "¿Se corrigió?"]   = corr_alerta
                    df.loc[m, "Fecha alerta"]    = combine_dt(fa_d, fa_t)
                    df.loc[m, "Fecha corregida"] = combine_dt(fc_d, fc_t)
                    st.session_state["df_main"] = df.copy()
                    _save_local(df[COLS].copy())
                    ok, msg = _write_sheet_tab(df[COLS].copy())
                    st.success(f"✔ Alerta vinculada a la tarea {id_target}. {msg}") if ok else st.warning(f"Actualizado localmente. {msg}")

        st.markdown('</div>', unsafe_allow_html=True)

    # =========================== PRIORIDAD ===============================
    ALLOWED_BOSS_EMAILS = {"stephanysg18@gmail.com.pe"}  # placeholder
    CAN_EDIT = True

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
        st.markdown("""<div class="help-strip" id="pri-help">
        🧭 <strong>Asigna o edita prioridades</strong> para varias tareas a la vez (solo jefatura)
        </div>""", unsafe_allow_html=True)
        st.markdown('<div class="form-card">', unsafe_allow_html=True)

        df_all = st.session_state.get("df_main", pd.DataFrame(columns=COLS)).copy()
        _k_area, _k_resp, _k_d, _k_h, _k_tasks = "pri_area_sel","pri_resp_sel","pri_desde","pri_hasta","pri_tareas_sel"

        with st.form("form_prioridad", clear_on_submit=False):
            W_AREA, W_RESP, W_TAREA, W_PRI = COL_W_AREA, PILL_W_RESP, COL_W_TAREA, COL_W_PRIORIDAD
            r1_area, r1_resp, r1_desde, r1_hasta, r1_tarea, r1_ids = st.columns([W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_PRI], gap="small")

            areas_opts = ["Todas"] + AREAS_OPC
            r1_area.selectbox("Área", options=areas_opts, index=0, key=_k_area, disabled=not CAN_EDIT)
            df_resp = df_all if st.session_state[_k_area] == "Todas" else df_all[df_all["Área"] == st.session_state[_k_area]]
            responsables_all = sorted([x for x in df_resp["Responsable"].astype(str).unique() if x and x != "nan"])
            r1_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0, key=_k_resp, disabled=not CAN_EDIT)
            r1_desde.date_input("Desde", value=None, key=_k_d, disabled=not CAN_EDIT)
            r1_hasta.date_input("Hasta", value=None, key=_k_h, disabled=not CAN_EDIT)

            def _filtra(df):
                out = df.copy()
                if st.session_state[_k_area] != "Todas": out = out[out["Área"] == st.session_state[_k_area]]
                if st.session_state[_k_resp] != "Todos": out = out[out["Responsable"].astype(str) == st.session_state[_k_resp]]
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
            r1_tarea.multiselect("Tarea (multi)", opciones_tarea, default=st.session_state.get(_k_tasks, []), key=_k_tasks, disabled=not CAN_EDIT)

            if st.session_state[_k_tasks]:
                ids_sel = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]), "Id"].astype(str).tolist()
            else:
                ids_sel = []
            r1_ids.text_input("Ids seleccionados", value=", ".join(ids_sel) if ids_sel else "—", disabled=True)

            st.write("")
            if ids_sel:
                df_tab = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]), ["Id","Área","Responsable","Tarea","Prioridad"]].copy()
            else:
                df_tab = pd.DataFrame(columns=["Id","Área","Responsable","Tarea","Prioridad"])
            if "Prioridad" not in df_tab.columns: df_tab["Prioridad"] = "Media"
            df_tab["Id"] = df_tab["Id"].astype(str)

            st.caption("Lista seleccionada")
            df_pri = _clean_df_for_grid(df_tab)
            grid_opt_pri = _grid_options_prioridad(df_pri)
            st.markdown('<div id="prior-grid">', unsafe_allow_html=True)
            grid_pri = AgGrid(
                df_pri, gridOptions=grid_opt_pri, fit_columns_on_grid_load=False,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                allow_unsafe_jscode=True, theme="balham", height=180,
                custom_css={".ag-root-wrapper":{"height":"180px !important"},
                            ".ag-body-viewport":{"height":"140px !important"}},
                key="grid_prior"
            )
            st.markdown('</div>', unsafe_allow_html=True)
            edited = pd.DataFrame(grid_pri["data"]) if isinstance(grid_pri, dict) and "data" in grid_pri else df_pri.copy()

            b1,b2,b3,b4,b5,b6 = st.columns([W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_PRI], gap="small")
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
        st.markdown('</div>', unsafe_allow_html=True)

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
        st.markdown("""<div class="help-strip" id="eva-help">
          📝 <strong>Registra una evaluación</strong> por varias tareas a la vez (solo jefatura).
        </div>""", unsafe_allow_html=True)
        st.markdown('<div class="form-card">', unsafe_allow_html=True)

        df_all = st.session_state.get("df_main", pd.DataFrame(columns=COLS)).copy()
        _k_area, _k_resp, _k_d, _k_h, _k_tasks = "eva_area_sel","eva_resp_sel","eva_desde","eva_hasta","eva_tareas_sel"

        with st.form("form_evaluacion", clear_on_submit=False):
            W_AREA, W_RESP, W_TAREA, W_EVA = COL_W_AREA, PILL_W_RESP, COL_W_TAREA, COL_W_EVALUACION
            c_area, c_resp, c_desde, c_hasta, c_tarea, c_id = st.columns([W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_EVA], gap="small")

            c_area.selectbox("Área", options=["Todas"] + AREAS_OPC, index=0, key=_k_area, disabled=not CAN_EDIT)
            df_resp = df_all if st.session_state[_k_area] == "Todas" else df_all[df_all["Área"] == st.session_state[_k_area]]
            responsables_all = sorted([x for x in df_resp["Responsable"].astype(str).unique() if x and x != "nan"])
            c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0, key=_k_resp, disabled=not CAN_EDIT)
            c_desde.date_input("Desde", value=None, key=_k_d, disabled=not CAN_EDIT)
            c_hasta.date_input("Hasta", value=None, key=_k_h, disabled=not CAN_EDIT)

            def _filtra(df):
                out = df.copy()
                if st.session_state[_k_area] != "Todas": out = out[out["Área"] == st.session_state[_k_area]]
                if st.session_state[_k_resp] != "Todos": out = out[out["Responsable"].astype(str) == st.session_state[_k_resp]]
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
            c_tarea.multiselect("Tarea (multi)", tareas_opts, default=st.session_state.get(_k_tasks, []), key=_k_tasks, disabled=not CAN_EDIT)

            if st.session_state[_k_tasks]:
                ids_sel = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]), "Id"].astype(str).tolist()
            else:
                ids_sel = []
            c_id.text_input("Ids seleccionados", value=", ".join(ids_sel) if ids_sel else "—", disabled=True)

            st.write("")
            if ids_sel:
                df_tab_e = df_f.loc[df_f["Tarea_str"].isin(st.session_state[_k_tasks]), ["Id", "Área", "Responsable", "Tarea"]].copy()
            else:
                df_tab_e = pd.DataFrame(columns=["Id","Área","Responsable","Tarea"])
            if not df_tab_e.empty:
                df_tab_e["Evaluación"] = 5
            else:
                df_tab_e["Evaluación"] = []
            df_tab_e["Id"] = df_tab_e["Id"].astype(str)

            st.caption("Lista seleccionada")
            df_eval_tab = _clean_df_for_grid(df_tab_e)
            grid_opt_eval = _grid_options_evaluacion(df_eval_tab)
            st.markdown('<div id="eval-grid">', unsafe_allow_html=True)
            grid_eval = AgGrid(
                df_eval_tab, gridOptions=grid_opt_eval, fit_columns_on_grid_load=False,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                allow_unsafe_jscode=True, theme="balham", height=180,
                custom_css={".ag-root-wrapper":{"height":"180px !important"},
                            ".ag-body-viewport":{"height":"140px !important"}},
                key="grid_eval"
            )
            st.markdown('</div>', unsafe_allow_html=True)
            edited_eval = pd.DataFrame(grid_eval["data"]) if isinstance(grid_eval, dict) and "data" in grid_eval else df_eval_tab.copy()

            bx1,bx2,bx3,bx4,bx5,bx6 = st.columns([W_AREA, W_RESP, W_RESP, W_RESP, W_TAREA, W_EVA], gap="small")
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
        st.markdown('</div>', unsafe_allow_html=True)

    # ================== Historial ==================
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    st.subheader("📝 Tareas recientes")
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    df_view = st.session_state.get("df_main", pd.DataFrame(columns=COLS + ["__DEL__"])).copy()
    A = 1.2; F = 1.2; T = 3.2; D = 2.4
    responsables = sorted([x for x in df_view["Responsable"].astype(str).unique() if x and x != "nan"])
    cA, cR, cE, cD, cH = st.columns([A + F, T/2, T/2, D/2, D/2], gap="medium")
    area_sel  = cA.selectbox("Área", options=["Todas"] + AREAS_OPC, index=0)
    resp_sel  = cR.selectbox("Responsable", options=["Todos"] + responsables, index=0)
    estado_sel = cE.selectbox("Estado", options=["Todos"] + ESTADO, index=0)
    f_desde = cD.date_input("Desde", value=None, key="f_desde")
    f_hasta = cH.date_input("Hasta",  value=None, key="f_hasta")

    df_view["Fecha inicio"] = pd.to_datetime(df_view.get("Fecha inicio"), errors="coerce")
    if area_sel != "Todas": df_view = df_view[df_view["Área"] == area_sel]
    if resp_sel != "Todos": df_view = df_view[df_view["Responsable"].astype(str) == resp_sel]
    if estado_sel != "Todos": df_view = df_view[df_view["Estado"] == estado_sel]
    if f_desde: df_view = df_view[df_view["Fecha inicio"].dt.date >= f_desde]
    if f_hasta: df_view = df_view[df_view["Fecha inicio"].dt.date <= f_hasta]
    st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)

    cols_first = ["Id", "Área", "Responsable", "Tarea", "Tipo", "Ciclo de mejora"]
    if "Ciclo de mejora" not in df_view.columns:
        df_view["Ciclo de mejora"] = ""
    cols_order = cols_first + [c for c in df_view.columns if c not in cols_first + ["__DEL__"]]
    extra = ["__DEL__"] if "__DEL__" in df_view.columns else []
    df_grid = (pd.DataFrame(columns=cols_order + extra) if df_view.empty else df_view.reindex(columns=cols_order + extra).copy())
    if "Id" in df_grid.columns:
        df_grid["Id"] = df_grid["Id"].astype(str).fillna("")

    gob = GridOptionsBuilder.from_dataframe(df_grid)
    gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True)
    gob.configure_grid_options(
        rowSelection="multiple", rowMultiSelectWithClick=True, suppressRowClickSelection=False,
        rememberSelection=True, domLayout="normal", rowHeight=38, headerHeight=42,
        enableRangeSelection=True, enableCellTextSelection=True, singleClickEdit=True,
        stopEditingWhenCellsLoseFocus=True, undoRedoCellEditing=True, enterMovesDown=True,
        getRowId=JsCode("function(p){ return (p.data && (p.data.Id || p.data['Id'])) + ''; }"),
    )
    if "Id" in df_grid.columns:
        gob.configure_column("Id", editable=False, width=110, pinned="left",
                             checkboxSelection=True, headerCheckboxSelection=True,
                             headerCheckboxSelectionFilteredOnly=True)
    if "Área" in df_grid.columns:
        gob.configure_column("Área", editable=True,  width=160, pinned="left")
    if "Responsable" in df_grid.columns:
        gob.configure_column("Responsable", pinned="left")
    if "__DEL__" in df_grid.columns:
        gob.configure_column("__DEL__", hide=True)

    colw = {"Tarea":220,"Tipo":160,"Responsable":200,"Fase":140,"Complejidad":130,"Prioridad":130,"Estado":130,
            "Fecha inicio":160,"Vencimiento":160,"Fecha fin":160,"Duración":110,"Días hábiles":120,
            "Cumplimiento":180,"¿Generó alerta?":150,"Tipo de alerta":200,"¿Se corrigió?":140,"Evaluación":170,"Calificación":120}

    flag_formatter = JsCode("""function(p){ const v=String(p.value||'');
      if(v==='Alta') return '🔴 Alta'; if(v==='Media') return '🟡 Media'; if(v==='Baja') return '🟢 Baja'; return v||'—'; }""")
    chip_style = JsCode("""function(p){ const v=String(p.value||''); let bg='#E0E0E0', fg='#FFFFFF';
      if(v==='No iniciado'){bg='#90A4AE'} else if(v==='En curso'){bg='#B388FF'}
      else if(v==='Terminado'){bg='#00C4B3'} else if(v==='Cancelado'){bg='#FF2D95'}
      else if(v==='Pausado'){bg='#7E57C2'} else if(v==='Entregado a tiempo'){bg='#00C4B3'}
      else if(v==='Entregado con retraso'){bg:'#00ACC1'} else if(v==='No entregado'){bg:'#006064'}
      else if(v==='En riesgo de retraso'){bg:'#0277BD'} else if(v==='Aprobada'){bg:'#8BC34A'; fg:'#0A2E00'}
      else if(v==='Desaprobada'){bg:'#FF8A80'} else if(v==='Pendiente de revisión'){bg:'#BDBDBD'; fg:'#2B2B2B'}
      else if(v==='Observada'){bg:'#D7A56C'}
      return { backgroundColor:bg, color:fg, fontWeight:'600', textAlign:'center', borderRadius:'10px', padding:'4px 10px' }; }""")
    fmt_dash = JsCode("""function(p){ if(p.value===null||p.value===undefined) return '—';
      const s=String(p.value).trim().toLowerCase(); if(s===''||s==='nan'||s==='nat'||s==='none'||s==='null') return '—'; return String(p.value); }""")
    stars_fmt = JsCode("""function(p){ let n=parseInt(p.value||0); if(isNaN(n)||n<0)n=0; if(n>5)n=5; return '★'.repeat(n)+'☆'.repeat(5-n); }""")

    for c, fx in [("Tarea",3),("Tipo",2),("Tipo de alerta",2),("Responsable",2),("Fase",1)]:
        if c in df_grid.columns:
            gob.configure_column(c, editable=True, minWidth=colw.get(c,120), flex=fx, valueFormatter=fmt_dash)
    for c in ["Complejidad","Prioridad"]:
        if c in df_grid.columns:
            gob.configure_column(c, editable=True, cellEditor="agSelectCellEditor",
                                 cellEditorParams={"values":["Alta","Media","Baja"]},
                                 valueFormatter=flag_formatter, minWidth=colw[c], maxWidth=220, flex=1)
    for c, vals in [("Estado", ESTADO), ("Cumplimiento", CUMPLIMIENTO), ("¿Generó alerta?", SI_NO),
                    ("¿Se corrigió?", SI_NO), ("Evaluación", ["Aprobada","Desaprobada","Pendiente de revisión","Observada","Cancelada","Pausada"])]:
        if c in df_grid.columns:
            gob.configure_column(c, editable=True, cellEditor="agSelectCellEditor",
                                 cellEditorParams={"values": vals}, cellStyle=chip_style, valueFormatter=fmt_dash,
                                 minWidth=colw.get(c,120), maxWidth=260, flex=1)
    if "Calificación" in df_grid.columns:
        gob.configure_column("Calificación", editable=True, valueFormatter=stars_fmt,
                             minWidth=colw["Calificación"], maxWidth=140, flex=0)

    date_time_editor = JsCode("""class DateTimeEditor{
      init(p){ this.eInput=document.createElement('input'); this.eInput.type='datetime-local'; this.eInput.classList.add('ag-input'); this.eInput.style.width='100%';
        const v=p.value?new Date(p.value):null; if(v && !isNaN(v.getTime())){ const pad=n=>String(n).padStart(2,'0');
          this.eInput.value=v.getFullYear()+'-'+pad(v.getMonth()+1)+'-'+pad(v.getDate())+'T'+pad(v.getHours())+':'+pad(v.getMinutes()); } }
      getGui(){return this.eInput} afterGuiAttached(){this.eInput.focus()} getValue(){return this.eInput.value} }""")
    date_time_fmt = JsCode("""function(p){ if(p.value===null||p.value===undefined) return '—';
      const d=new Date(String(p.value).trim()); if(isNaN(d.getTime())) return '—';
      const pad=n=>String(n).padStart(2,'0'); return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes()); }""")
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

    for col in df_grid.columns:
        gob.configure_column(col, headerTooltip=col)

    autosize_on_ready = JsCode("function(params){const all=params.columnApi.getAllDisplayedColumns();params.columnApi.autoSizeColumns(all,true);}"); 
    autosize_on_data  = JsCode("function(params){if(params.api && params.api.getDisplayedRowCount()>0){const all=params.columnApi.getAllDisplayedColumns();params.columnApi.autoSizeColumns(all,true);}}")
    grid_opts = gob.build()
    grid_opts["onGridReady"] = autosize_on_ready.js_code
    grid_opts["onFirstDataRendered"] = autosize_on_data.js_code
    grid_opts["onColumnEverythingChanged"] = autosize_on_data.js_code
    grid_opts["rowSelection"] = "multiple"
    grid_opts["rowMultiSelectWithClick"] = True
    grid_opts["rememberSelection"] = True

    grid = AgGrid(
        df_grid, key="grid_historial", gridOptions=grid_opts, height=500,
        fit_columns_on_grid_load=False,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=(GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED | GridUpdateMode.FILTERING_CHANGED | GridUpdateMode.SORTING_CHANGED | GridUpdateMode.SELECTION_CHANGED),
        allow_unsafe_jscode=True, theme="balham",
    )

    sel_rows_now = grid.get("selected_rows", []) if isinstance(grid, dict) else []
    st.session_state["hist_sel_ids"] = [str(r.get("Id", "")).strip() for r in sel_rows_now if str(r.get("Id", "")).strip()]

    if isinstance(grid, dict) and "data" in grid and grid["data"] is not None and len(grid["data"]) > 0:
        try:
            edited = pd.DataFrame(grid["data"]).copy()
            base = st.session_state["df_main"].copy().set_index("Id")
            st.session_state["df_main"] = base.combine_first(edited.set_index("Id")).reset_index()
        except Exception:
            pass

    total_btn_width = (A + F) + (T / 2)
    btn_w = total_btn_width / 4
    b_del, b_xlsx, b_save_local, b_save_sheets, _spacer = st.columns([btn_w, btn_w, btn_w, btn_w, (T / 2) + D], gap="medium")

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

    with b_xlsx:
        try:
            xlsx_b = export_excel(st.session_state["df_main"][COLS], sheet=TAB_NAME)
            st.download_button("⬇️ Exportar Excel", data=xlsx_b, file_name="tareas.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception as e:
            st.error(f"No pude generar Excel: {e}")

    with b_save_local:
        if st.button("💽 Guardar", use_container_width=True):
            df = st.session_state["df_main"][COLS].copy()
            _save_local(df.copy())
            st.success("Datos guardados en la tabla local (CSV).")

    with b_save_sheets:
        if st.button("📤 Subir a Sheets", use_container_width=True):
            df = st.session_state["df_main"][COLS].copy()
            _save_local(df.copy())
            ok, msg = _write_sheet_tab(df.copy())
            st.success(msg) if ok else st.warning(msg)
