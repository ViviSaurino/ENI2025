# features/historial/view.py
from __future__ import annotations

import os
import re
from io import BytesIO
from datetime import datetime, date

import pandas as pd
import streamlit as st
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

# ================== Config base ==================
TAB_NAME = "Tareas"

DEFAULT_COLS = [
    "Id","Área","Fase","Responsable",
    "Tarea","Tipo","Detalle","Ciclo de mejora","Complejidad","Prioridad",
    "Estado","Duración",
    "Fecha Registro","Hora Registro",
    "Fecha inicio","Hora de inicio",
    "Fecha Vencimiento","Hora Vencimiento",
    "Fecha Terminado","Hora Terminado",
    "¿Generó alerta?","N° de alerta","Fecha de detección","Hora de detección",
    "¿Se corrigió?","Fecha de corrección","Hora de corrección",
    "Cumplimiento","Evaluación","Calificación",
    "Fecha Pausado","Hora Pausado",
    "Fecha Cancelado","Hora Cancelado",
    "Fecha Eliminado","Hora Eliminado",
    "Archivo"
]

# ====== TZ helpers ======
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None

def to_naive_local_series(s: pd.Series) -> pd.Series:
    ser = pd.to_datetime(s, errors="coerce", utc=False)
    try:
        if getattr(ser.dt, "tz", None) is not None:
            ser = (ser.dt.tz_convert(_TZ) if _TZ else ser).dt.tz_localize(None)
    except Exception:
        try:
            ser = ser.dt.tz_localize(None)
        except Exception:
            pass
    return ser

def _fmt_hhmm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        s = str(v).strip()
        if not s or s.lower() in {"nan","nat","none","null"}:
            return ""
        m = re.match(r"^(\d{1,2}):(\d{2})", s)
        if m:
            return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        d = pd.to_datetime(s, errors="coerce", utc=False)
        if pd.isna(d):
            return ""
        return f"{int(d.hour):02d}:{int(d.minute):02d}"
    except Exception:
        return ""

# --- Guardado local ---
try:
    from shared import save_local as _disk_save_local
except Exception:
    def _disk_save_local(df: pd.DataFrame):
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")

def _save_local(df: pd.DataFrame):
    _disk_save_local(df.copy())
    st.session_state["_df_main_local_backup"] = df.copy()

# --- Cliente GSheets ---
def _gsheets_client():
    if "gcp_service_account" not in st.secrets:
        raise KeyError("Falta 'gcp_service_account' en secrets.")
    url = st.secrets.get("gsheets_doc_url") or \
          (st.secrets.get("gsheets", {}) or {}).get("spreadsheet_url") or \
          (st.secrets.get("sheets", {}) or {}).get("sheet_url")
    if not url:
        raise KeyError("No se encontró URL de Sheets.")
    ws_name = (st.secrets.get("gsheets", {}) or {}).get("worksheet", "TareasRecientes")

    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(url)
    return ss, ws_name

def pull_user_slice_from_sheet(replace_df_main: bool = True):
    ss, ws_name = _gsheets_client()
    try:
        ws = ss.worksheet(ws_name)
    except Exception:
        return
    values = ws.get_all_values()
    if not values:
        return
    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    for c in df.columns:
        if c.lower().startswith("fecha"):
            df[c] = to_naive_local_series(df[c])

    # Limpieza de HTML residual en Archivo y variantes
    def _strip_html(x):
        s = str(x) if x is not None else ""
        return re.sub(r"<[^>]+>", "", s)
    for cc in [c for c in df.columns if "archivo" in c.lower()]:
        df[cc] = df[cc].map(_strip_html)

    # Unificar "N° alerta" -> "N° de alerta"
    if "N° de alerta" not in df.columns and "N° alerta" in df.columns:
        df.rename(columns={"N° alerta": "N° de alerta"}, inplace=True)
    dup_alert_cols = [c for c in df.columns if c.strip().lower() in {"n° alerta","n alerta","nº alerta"} and c != "N° de alerta"]
    for c in dup_alert_cols:
        df.drop(columns=c, inplace=True, errors="ignore")

    if replace_df_main:
        st.session_state["df_main"] = df
    return df

def push_user_slice_to_sheet():
    ss, ws_name = _gsheets_client()
    try:
        ws = ss.worksheet(ws_name)
    except Exception:
        rows = str(max(1000, len(st.session_state["df_main"]) + 10))
        cols = str(max(26, len(st.session_state["df_main"].columns) + 5))
        ws = ss.add_worksheet(title=ws_name, rows=rows, cols=cols)

    df_out = st.session_state["df_main"].copy()
    for c in df_out.columns:
        low = str(c).lower()
        if low.startswith("fecha"):
            ser = to_naive_local_series(df_out[c])
            df_out[c] = ser.dt.strftime("%Y-%m-%d").fillna("")
        elif low.startswith("hora"):
            df_out[c] = df_out[c].apply(_fmt_hhmm).astype(str)

    df_out = df_out.fillna("").astype(str)

    ws.clear()
    ws.update("A1", [list(df_out.columns)] + df_out.values.tolist())

# ===== Exportación =====
def export_excel(df: pd.DataFrame, sheet_name: str = TAB_NAME) -> bytes:
    try:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return buf.getvalue()
    except Exception:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return buf.getvalue()

# ===== Helpers Archivo =====
_EXT_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|png|jpe?g|csv|zip|rar)$", re.I)

def _pick_first_token(av: str) -> str:
    raw = (av or "").strip()
    if not raw:
        return ""
    parts = re.split(r"[\n,;|]+", raw)
    for p in parts:
        s = p.strip()
        if not s or s.lower() == "directorio":
            continue
        if s.lower().startswith(("http://","https://")) or _EXT_RE.search(s):
            return s
    return parts[0].strip()

def _resolve_local_path(val: str, row_id: str) -> tuple[str, str] | None:
    if not val:
        return None
    v = _pick_first_token(val)
    if not v:
        return None
    if v.lower().startswith(("http://", "https://")):
        return None
    if os.path.isabs(v) and os.path.isfile(v):
        return (v, os.path.basename(v))
    if os.path.isfile(v):
        return (v, os.path.basename(v))
    base = os.path.basename(v)
    candidates = [
        os.path.join("data", "files", row_id, base),
        os.path.join("data", "uploads", row_id, base),
        os.path.join("data", base),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return (p, os.path.basename(p))
    return None

# =======================================================
#                       RENDER
# =======================================================
def render(user: dict | None = None):
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # Alineaciones
    A_f, Fw_f, T_width_f, D_f, R_f, C_f = 1.80, 2.10, 3.00, 1.60, 1.40, 1.20

    # Título + estilos
    title_cA, _t2, _t3, _t4, _t5, _t6 = st.columns(
        [A_f, Fw_f, T_width_f, D_f, R_f, C_f],
        gap="medium",
        vertical_alignment="center"
    )
    with title_cA:
        st.markdown("""
        <style>
        :root{ --pill-salmon:#F28B85; }
        .hist-title-pill{
          display:flex; align-items:center; gap:8px;
          padding:10px 16px; width:100%;
          border-radius:10px; background: var(--pill-salmon);
          color:#fff; font-weight:600; font-size:1.10rem; line-height:1;
          box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06);
        }
        .hist-actions{ padding:0 16px; border-top:2px solid #EF4444; }
        .hist-actions .stButton > button{ height:38px!important; border-radius:10px!important; width:100%; }

        /* ===== Celdas en una línea (con ‘…’) ===== */
        .ag-theme-balham .ag-cell{
          white-space: nowrap !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
        }

        /* ===== Encabezados: multilinea y sin iconos (filtros/menú/sort) ===== */
        .ag-theme-balham .ag-header-cell-label{
          white-space: normal !important;
          line-height: 1.2 !important;
        }
        .ag-theme-balham .ag-header-cell .ag-icon,
        .ag-theme-balham .ag-floating-filter,
        .ag-theme-balham .ag-header-cell-menu-button{
          display: none !important;
        }
        </style>
        <div class="hist-title-pill">📝 Tareas recientes</div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ====== DATA BASE ======
    if "df_main" not in st.session_state or not isinstance(st.session_state["df_main"], pd.DataFrame):
        st.session_state["df_main"] = pd.DataFrame(columns=DEFAULT_COLS)

    df_all = st.session_state["df_main"].copy()

    TZ_DATE_COLS = [
        "Fecha estado modificado","Fecha estado actual","Fecha inicio",
        "Fecha Terminado","Fecha Registro","Fecha Vencimiento",
        "Fecha Pausado","Fecha Cancelado","Fecha Eliminado",
        "Fecha","Fecha de detección","Fecha de corrección"
    ]
    for c in [c for c in TZ_DATE_COLS if c in df_all.columns]:
        df_all[c] = to_naive_local_series(df_all[c])

    # ===== Filtros =====
    with st.container():
        W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BUSCAR = 1.15, 1.25, 1.60, 1.05, 1.05, 1.05
        cA, cF, cR, cD, cH, cB = st.columns(
            [W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BUSCAR],
            gap="medium", vertical_alignment="bottom"
        )
        with cA:
            area_sel = st.selectbox(
                "Área",
                options=["Todas"] + st.session_state.get(
                    "AREAS_OPC",
                    ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
                ),
                index=0, key="hist_area"
            )
        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        with cF:
            fase_sel = st.selectbox("Fase", options=["Todas"] + fases_all, index=0, key="hist_fase")

        df_resp_src = df_all.copy()
        if area_sel != "Todas":
            df_resp_src = df_resp_src[df_resp_src["Área"] == area_sel]
        if fase_sel != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == fase_sel]
        responsables = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])

        with cR:
            resp_multi = st.multiselect("Responsable", options=responsables, default=[], key="hist_resp",
                                        placeholder="Selecciona responsable(s)")
        today = date.today()
        with cD:
            f_desde = st.date_input("Desde", value=today, key="hist_desde")
        with cH:
            f_hasta = st.date_input("Hasta", value=today, key="hist_hasta")
        with cB:
            hist_do_buscar = st.button("🔍 Buscar", use_container_width=True, key="hist_btn_buscar")

    show_deleted = st.toggle("Mostrar eliminadas (tachadas)", value=True, key="hist_show_deleted")

    # ---- Aplicar filtros ----
    df_view = df_all.copy()
    df_view["Fecha inicio"] = to_naive_local_series(df_view.get("Fecha inicio"))

    if hist_do_buscar:
        if area_sel != "Todas":
            df_view = df_view[df_view["Área"] == area_sel]
        if fase_sel != "Todas" and "Fase" in df_view.columns:
            df_view = df_view[df_view["Fase"].astype(str) == fase_sel]
        if resp_multi:
            df_view = df_view[df_view["Responsable"].astype(str).isin(resp_multi)]
        if f_desde:
            df_view = df_view[df_view["Fecha inicio"].dt.date >= f_desde]
        if f_hasta:
            df_view = df_view[df_view["Fecha inicio"].dt.date <= f_hasta]

    if not show_deleted and "Estado" in df_view.columns:
        df_view = df_view[df_view["Estado"].astype(str).str.strip() != "Eliminado"]

    # Orden
    for c in ["Fecha estado modificado","Fecha estado actual","Fecha inicio"]:
        if c not in df_view.columns:
            df_view[c] = pd.NaT
    ts_mod = to_naive_local_series(df_view["Fecha estado modificado"])
    ts_act = to_naive_local_series(df_view["Fecha estado actual"])
    ts_ini = to_naive_local_series(df_view["Fecha inicio"])
    df_view["__ts__"] = ts_mod.combine_first(ts_act).combine_first(ts_ini)
    df_view = df_view.sort_values("__ts__", ascending=False, na_position="last")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ===== Normalizaciones mínimas =====
    if "Estado" not in df_view.columns:
        df_view["Estado"] = ""
    df_view["Estado"] = df_view["Estado"].apply(lambda s: "No iniciado" if str(s).strip() in {"","nan","NaN"} else s)
    if "Hora de inicio" not in df_view.columns: df_view["Hora de inicio"] = ""
    if "Fecha Terminado" not in df_view.columns: df_view["Fecha Terminado"] = pd.NaT
    if "Hora Terminado" not in df_view.columns: df_view["Hora Terminado"] = ""

    # === Columna Archivo (tomar alternativas si viene vacía) ===
    if "Archivo" not in df_view.columns:
        for alt in ["Archivo estado modificado","Archivo modificado","Archivo adjunto"]:
            if alt in df_view.columns:
                df_view["Archivo"] = df_view[alt]
                break
    else:
        if df_view["Archivo"].astype(str).str.strip().eq("").all():
            for alt in ["Archivo estado modificado","Archivo modificado","Archivo adjunto"]:
                if alt in df_view.columns and df_view[alt].astype(str).str.strip().ne("").any():
                    df_view["Archivo"] = df_view["Archivo"].where(
                        df_view["Archivo"].astype(str).str.strip().ne(""),
                        df_view[alt]
                    )
                    break

    # Unificar/ubicar "N° de alerta"
    if "N° de alerta" not in df_view.columns and "N° alerta" in df_view.columns:
        df_view.rename(columns={"N° alerta": "N° de alerta"}, inplace=True)
    to_drop_dups = [c for c in df_view.columns if c != "N° de alerta" and c.strip().lower() in {"n° alerta","n alerta","nº alerta"}]
    df_view.drop(columns=to_drop_dups, inplace=True, errors="ignore")

    # ========= GRID =========
    target_cols = [
        "Id","Área","Fase","Responsable",
        "Tarea","Tipo","Detalle","Ciclo de mejora","Complejidad","Prioridad",
        "Estado","Duración",
        "Fecha Registro","Hora Registro",
        "Fecha inicio","Hora de inicio",
        "Fecha Vencimiento","Hora Vencimiento",
        "Fecha Terminado","Hora Terminado",
        "¿Generó alerta?","N° de alerta","Fecha de detección","Hora de detección",
        "¿Se corrigió?","Fecha de corrección","Hora de corrección",
        "Cumplimiento","Evaluación","Calificación",
        "Fecha Pausado","Hora Pausado",
        "Fecha Cancelado","Hora Cancelado",
        "Fecha Eliminado","Hora Eliminado",
        "Link de descarga"   # última columna visible
    ]
    HIDDEN_COLS = [
        "Archivo",  # lo usamos para construir el link
        "¿Eliminar?","Estado modificado",
        "Fecha estado modificado","Hora estado modificado",
        "Fecha estado actual","Hora estado actual",
        "Tipo de alerta","Fecha","Hora","Vencimiento",
        "__ts__","__SEL__","__DEL__"
    ]
    for c in target_cols:
        if c not in df_view.columns:
            df_view[c] = ""

    df_grid = df_view.reindex(
        columns=list(dict.fromkeys(target_cols)) +
        [c for c in df_view.columns if c not in target_cols + HIDDEN_COLS]
    ).copy()
    df_grid = df_grid.loc[:, ~df_grid.columns.duplicated()].copy()
    df_grid["Id"] = df_grid["Id"].astype(str).fillna("")
    if "Link de descarga" not in df_grid.columns:
        df_grid["Link de descarga"] = ""

    gob = GridOptionsBuilder.from_dataframe(df_grid)
    # Horizontal y sin filtros/menú por defecto
    gob.configure_default_column(
        resizable=True, editable=False,
        wrapText=False, autoHeight=False,
        filter=False, floatingFilter=False, suppressMenu=True,
        cellStyle={"white-space":"nowrap","overflow":"hidden","textOverflow":"ellipsis"}
    )

    gob.configure_grid_options(
        domLayout="normal",
        rowHeight=34,
        wrapHeaderText=True, autoHeaderHeight=True, headerHeight=64,
        enableRangeSelection=True, enableCellTextSelection=True,
        singleClickEdit=False, stopEditingWhenCellsLoseFocus=True,
        undoRedoCellEditing=False, enterMovesDown=False,
        suppressMovableColumns=False,
        suppressHeaderVirtualisation=True,
    )

    # ----- Columnas base visibles -----
    gob.configure_column("Id", headerName="ID", editable=False, width=110, pinned="left",
                         suppressMovable=True, suppressSizeToFit=True, suppressMenu=True)
    gob.configure_column("Área", headerName="Área", editable=False, minWidth=160, pinned="left",
                         suppressMovable=True, suppressMenu=True)
    gob.configure_column("Fase", headerName="Fase", editable=False, minWidth=180, pinned="left",
                         suppressMovable=True, suppressMenu=True)
    gob.configure_column("Responsable", editable=False, minWidth=220, pinned="left",
                         suppressMovable=True, suppressMenu=True)
    gob.configure_column("Estado", headerName="Estado actual", minWidth=150, suppressMenu=True)
    gob.configure_column("Fecha Vencimiento", headerName="Fecha límite", minWidth=140, suppressMenu=True)
    gob.configure_column("Fecha inicio", headerName="Fecha de inicio", minWidth=140, suppressMenu=True)
    gob.configure_column("Fecha Terminado", headerName="Fecha Terminado", minWidth=150, suppressMenu=True)

    # ==== SOLO FECHA (dd/mm/aaaa) en columnas de fecha visibles ====
    date_only_fmt = JsCode(r"""
    function(p){
      const v = p.value;
      if(v===null || v===undefined) return '—';
      const s = String(v).trim();
      if(!s || s.toLowerCase()==='nan' || s.toLowerCase()==='nat' || s.toLowerCase()==='null') return '—';
      // intenta YYYY-MM-DD o ISO
      let y,m,d;
      const m1 = s.match(/^(\d{4})-(\d{2})-(\d{2})/); // 2025-11-06...
      if(m1){
        y = +m1[1]; m = +m1[2]; d = +m1[3];
      }else{
        // fallback: crea Date y toma componentes locales
        const dt = new Date(s);
        if(!isNaN(dt.getTime())){ y = dt.getFullYear(); m = dt.getMonth()+1; d = dt.getDate(); }
      }
      if(!y){ return s.split(' ')[0]; }
      const dd = String(d).padStart(2,'0');
      const mm = String(m).padStart(2,'0');
      return dd + '/' + mm + '/' + y;
    }
    """)
    for col in ["Fecha Registro","Fecha inicio","Fecha Vencimiento",
                "Fecha Terminado","Fecha Pausado","Fecha Cancelado",
                "Fecha Eliminado","Fecha de detección","Fecha de corrección"]:
        if col in df_grid.columns:
            gob.configure_column(col, valueFormatter=date_only_fmt, suppressMenu=True)

    # ==== Link de descarga (extrae el primer http/https de 'Archivo') ====
    link_value_getter = JsCode(r"""
    function(p){
      const raw0 = (p && p.data && p.data['Archivo'] != null) ? String(p.data['Archivo']).trim() : '';
      if(!raw0) return '';
      const parts = raw0.split(/[\n,;|]+/).map(s=>s.trim()).filter(Boolean);
      let url = '';
      for (let s of parts){
        if (/^https?:\/\//i.test(s)){ url = s; break; }
      }
      return url;
    }
    """)
    link_renderer = JsCode(r"""
    class LinkRenderer{
      init(params){
        const url = (params && params.value) ? String(params.value) : '';
        this.eGui = document.createElement('a');
        if(url){
          this.eGui.href = encodeURI(url);
          this.eGui.target = '_blank';
          this.eGui.rel = 'noopener';
          this.eGui.textContent = url;
          this.eGui.style.textDecoration = 'underline';
          this.eGui.style.color = '#0A66C2';
        }else{
          this.eGui.textContent = '—';
          this.eGui.style.opacity = '0.8';
        }
      }
      getGui(){ return this.eGui; }
      refresh(p){ return false; }
    }
    """)
    gob.configure_column(
        "Link de descarga",
        headerName="Link de descarga",
        minWidth=260, flex=1, suppressMenu=True,
        valueGetter=link_value_getter,
        cellRenderer=link_renderer,
        tooltipField="Link de descarga"
    )

    # Formatos cortos para demás columnas
    fmt_dash = JsCode("""
    function(p){
      if(p.value===null||p.value===undefined) return '—';
      const s=String(p.value).trim().toLowerCase();
      if(s===''||s==='nan'||s==='nat'||s==='none'||s==='null') return '—';
      return String(p.value);
    }""")
    for c in df_grid.columns:
        if c in ["Link de descarga","Id","Área","Fase","Responsable","Estado",
                 "Fecha Vencimiento","Fecha inicio","Fecha Terminado","¿Generó alerta?","N° de alerta",
                 "Fecha Registro","Fecha Pausado","Fecha Cancelado","Fecha Eliminado",
                 "Fecha de detección","Fecha de corrección"]:
            continue
        gob.configure_column(c, valueFormatter=fmt_dash, suppressMenu=True)

    # === Autosize eventos ===
    autosize_on_ready = JsCode("""
    function(params){
      const all = params.columnApi.getAllDisplayedColumns();
      const skip = all.filter(c => (c.getColId && c.getColId() !== 'Id'));
      params.columnApi.autoSizeColumns(skip, true);
      try{ params.columnApi.setColumnWidth('Id', 110); }catch(_){}
    }""")
    autosize_on_data = JsCode("""
    function(params){
      if (params.api && params.api.getDisplayedRowCount() > 0){
        const all = params.columnApi.getAllDisplayedColumns();
        const skip = all.filter(c => (c.getColId && c.getColId() !== 'Id'));
        params.columnApi.autoSizeColumns(skip, true);
        try{ params.columnApi.setColumnWidth('Id', 110); }catch(_){}
      }
    }""")

    grid_opts = gob.build()
    grid_opts["onGridReady"] = autosize_on_ready.js_code
    grid_opts["onFirstDataRendered"] = autosize_on_data.js_code
    grid_opts["onColumnEverythingChanged"] = autosize_on_data.js_code
    grid_opts["rememberSelection"] = True

    AgGrid(
        df_grid, key="grid_historial",
        gridOptions=grid_opts, height=500,
        fit_columns_on_grid_load=False,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=(GridUpdateMode.MODEL_CHANGED
                     | GridUpdateMode.FILTERING_CHANGED
                     | GridUpdateMode.SORTING_CHANGED),
        allow_unsafe_jscode=True, theme="balham",
    )

    # ===== Botonera =====
    left_spacer = A_f + Fw_f + T_width_f
    W_SHEETS = R_f + 0.8

    st.markdown('<div class="hist-actions">', unsafe_allow_html=True)
    _spacer, b_xlsx, b_sync, b_save_local, b_save_sheets = st.columns(
        [left_spacer, D_f, R_f, R_f, W_SHEETS], gap="medium"
    )

    with b_xlsx:
        try:
            df_xlsx = st.session_state["df_main"].copy()
            for c in ["__SEL__","__DEL__","¿Eliminar?"]:
                if c in df_xlsx.columns:
                    df_xlsx.drop(columns=[c], inplace=True, errors="ignore")
            xlsx_b = export_excel(df_xlsx, sheet_name=TAB_NAME)
            st.download_button(
                "⬇️ Exportar Excel", data=xlsx_b,
                file_name="tareas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except ImportError:
            st.error("No pude generar Excel: falta 'xlsxwriter' u 'openpyxl'.")
        except Exception as e:
            st.error(f"No pude generar Excel: {e}")

    with b_sync:
        if st.button("🔄 Sincronizar", use_container_width=True, key="btn_sync_sheet"):
            try:
                pull_user_slice_from_sheet(replace_df_main=True)
            except Exception as e:
                st.warning(f"No se pudo sincronizar: {e}")

    with b_save_local:
        if st.button("💾 Grabar", use_container_width=True):
            base = st.session_state["df_main"].copy()
            base["Id"] = base["Id"].astype(str)
            if "__DEL__" not in base.columns:
                base["__DEL__"] = False
            st.session_state["df_main"] = base.reset_index(drop=True)
            try:
                _save_local(st.session_state["df_main"].copy())
                st.success("Datos grabados en data/tareas.csv.")
            except Exception as e:
                st.warning(f"No se pudo grabar localmente: {e}")

    with b_save_sheets:
        if st.button("📤 Subir a Sheets", use_container_width=True):
            try:
                push_user_slice_to_sheet()
                st.success("Enviado a Google Sheets.")
            except Exception as e:
                st.warning(f"No se pudo subir a Sheets: {e}")

    st.markdown('</div>', unsafe_allow_html=True)
