# features/historial/view.py
from __future__ import annotations

import os, re
from io import BytesIO
from datetime import date
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
        try: ser = ser.dt.tz_localize(None)
        except Exception: pass
    return ser

def _fmt_hhmm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)): return ""
    try:
        s = str(v).strip()
        if not s or s.lower() in {"nan","nat","none","null"}: return ""
        m = re.match(r"^(\d{1,2}):(\d{2})", s)
        if m: return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        d = pd.to_datetime(s, errors="coerce", utc=False)
        if pd.isna(d): return ""
        return f"{int(d.hour):02d}:{int(d.minute):02d}"
    except Exception:
        return ""

# --- Guardado local (fallback seguro) ---
try:
    from shared import save_local as _disk_save_local
except Exception:
    def _disk_save_local(df: pd.DataFrame):
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data","tareas.csv"), index=False, encoding="utf-8-sig")
def _save_local(df: pd.DataFrame):
    _disk_save_local(df.copy())
    st.session_state["_df_main_local_backup"] = df.copy()

# --- Google Sheets (opcional) ---
def _gsheets_client():
    if "gcp_service_account" not in st.secrets:
        raise KeyError("Falta 'gcp_service_account' en secrets.")
    url = (st.secrets.get("gsheets_doc_url")
           or (st.secrets.get("gsheets",{}) or {}).get("spreadsheet_url")
           or (st.secrets.get("sheets",{}) or {}).get("sheet_url"))
    if not url: raise KeyError("No se encontró URL de Sheets.")
    ws_name = (st.secrets.get("gsheets",{}) or {}).get("worksheet","TareasRecientes")
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(url)
    return ss, ws_name

def pull_user_slice_from_sheet(replace_df_main: bool = True):
    ss, ws_name = _gsheets_client()
    try: ws = ss.worksheet(ws_name)
    except Exception: return
    values = ws.get_all_values()
    if not values: return
    headers, rows = values[0], values[1:]
    df = pd.DataFrame(rows, columns=headers)
    for c in df.columns:
        if c.lower().startswith("fecha"): df[c] = to_naive_local_series(df[c])
    # limpia HTML en "Archivo"
    def _strip_html(x): return re.sub(r"<[^>]+>", "", str(x) if x is not None else "")
    for cc in [c for c in df.columns if "archivo" in c.lower()]: df[cc] = df[cc].map(_strip_html)
    if "N° de alerta" not in df.columns and "N° alerta" in df.columns:
        df.rename(columns={"N° alerta":"N° de alerta"}, inplace=True)
    if replace_df_main: st.session_state["df_main"] = df
    return df

def push_user_slice_to_sheet():
    ss, ws_name = _gsheets_client()
    try: ws = ss.worksheet(ws_name)
    except Exception:
        rows = str(max(1000, len(st.session_state["df_main"])+10))
        cols = str(max(26, len(st.session_state["df_main"].columns)+5))
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
    ws.clear(); ws.update("A1", [list(df_out.columns)] + df_out.values.tolist())

# ===== Exportación =====
def export_excel(df: pd.DataFrame, sheet_name: str = TAB_NAME) -> bytes:
    try:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as w: df.to_excel(w, index=False, sheet_name=sheet_name)
        return buf.getvalue()
    except Exception:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w: df.to_excel(w, index=False, sheet_name=sheet_name)
        return buf.getvalue()

# =======================================================
#                       RENDER
# =======================================================
def render(user: dict | None = None):
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ====== Título + CSS fuerte para encabezados ======
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
    /* Celdas en una línea con '…' */
    .ag-theme-balham .ag-cell{
      white-space: nowrap !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
    }
    /* Encabezados legibles (una línea) y sin íconos ni fila de filtros */
    .ag-theme-balham .ag-header-cell-label{
      white-space: nowrap !important;
      line-height: 1.1 !important;
      overflow: visible !important;
      text-overflow: clip !important;
    }
    .ag-theme-balham .ag-header .ag-icon,
    .ag-theme-balham .ag-header-cell .ag-icon { display: none !important; }
    .ag-theme-balham .ag-floating-filter,
    .ag-theme-balham .ag-header-row.ag-header-row-column-filter { display: none !important; }
    </style>
    <div class="hist-title-pill">📝 Tareas recientes</div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ====== DATA BASE ======
    if "df_main" not in st.session_state or not isinstance(st.session_state["df_main"], pd.DataFrame):
        st.session_state["df_main"] = pd.DataFrame(columns=DEFAULT_COLS)
    df_all = st.session_state["df_main"].copy()

    # ===== Filtros externos =====
    with st.container():
        c1,c2,c3,c4,c5,c6 = st.columns([1.15,1.25,1.60,1.05,1.05,1.05], gap="medium")
        with c1:
            area_sel = st.selectbox("Área",
                options=["Todas"] + st.session_state.get("AREAS_OPC",
                    ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]),
                index=0, key="hist_area")
        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x!="nan"])
        with c2: fase_sel = st.selectbox("Fase", options=["Todas"]+fases_all, index=0, key="hist_fase")
        df_resp_src = df_all.copy()
        if area_sel!="Todas": df_resp_src = df_resp_src[df_resp_src["Área"]==area_sel]
        if fase_sel!="Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str)==fase_sel]
        responsables = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x!="nan"])
        with c3: resp_multi = st.multiselect("Responsable", options=responsables, default=[], key="hist_resp", placeholder="Selecciona responsable(s)")
        today = date.today()
        with c4: f_desde = st.date_input("Desde", value=today, key="hist_desde")
        with c5: f_hasta = st.date_input("Hasta", value=today, key="hist_hasta")
        with c6: hist_do_buscar = st.button("🔍 Buscar", use_container_width=True, key="hist_btn_buscar")

    show_deleted = st.toggle("Mostrar eliminadas (tachadas)", value=True, key="hist_show_deleted")

    # ---- Aplicar filtros ----
    df_view = df_all.copy()
    if "Fecha inicio" in df_view.columns: df_view["Fecha inicio"] = to_naive_local_series(df_view["Fecha inicio"])
    if hist_do_buscar:
        if area_sel!="Todas": df_view = df_view[df_view["Área"]==area_sel]
        if fase_sel!="Todas" and "Fase" in df_view.columns: df_view = df_view[df_view["Fase"].astype(str)==fase_sel]
        if resp_multi: df_view = df_view[df_view["Responsable"].astype(str).isin(resp_multi)]
        if f_desde is not None: df_view = df_view[df_view["Fecha inicio"].dt.date >= f_desde]
        if f_hasta is not None: df_view = df_view[df_view["Fecha inicio"].dt.date <= f_hasta]
    if not show_deleted and "Estado" in df_view.columns:
        df_view = df_view[df_view["Estado"].astype(str).str.strip()!="Eliminado"]

    # ===== Normalizaciones mínimas =====
    for need in ["Estado","Hora de inicio","Fecha Terminado","Hora Terminado"]:
        if need not in df_view.columns: df_view[need] = "" if "Hora" in need else pd.NaT
    if "Archivo" not in df_view.columns: df_view["Archivo"] = ""

    # ===== GRID =====
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
        "Link de descarga"
    ]
    hidden_cols = ["Archivo","__ts__","__SEL__","__DEL__","¿Eliminar?","Tipo de alerta",
                   "Fecha estado modificado","Hora estado modificado","Fecha estado actual","Hora estado actual",
                   "Fecha","Hora","Vencimiento"]

    for c in target_cols:
        if c not in df_view.columns: df_view[c] = ""

    df_grid = df_view.reindex(columns=list(dict.fromkeys(target_cols)) +
                              [c for c in df_view.columns if c not in target_cols + hidden_cols]).copy()
    df_grid = df_grid.loc[:, ~df_grid.columns.duplicated()].copy()
    df_grid["Id"] = df_grid["Id"].astype(str).fillna("")
    if "Link de descarga" not in df_grid.columns: df_grid["Link de descarga"] = ""

    # --- Quitar SOLO estas dos columnas ---
    for _col in ["Cumplimiento", "Evaluación"]:
        if _col in df_grid.columns:
            df_grid.drop(columns=[_col], inplace=True, errors="ignore")

    # ==== Opciones AG Grid ====
    gob = GridOptionsBuilder.from_dataframe(df_grid)

    # Sin filtros/menú/sort global + edición sólo en 2 columnas
    gob.configure_default_column(
        resizable=True, editable=False, filter=False, floatingFilter=False,
        sortable=False, suppressMenu=True, wrapText=False, autoHeight=False,
        cellStyle={"white-space":"nowrap","overflow":"hidden","textOverflow":"ellipsis"}
    )

    # widths mínimas para que SE LEA el encabezado (scroll horizontal)
    width_map = {
        "Id": 90, "Área": 140, "Fase": 180, "Responsable": 220,
        "Tarea": 280, "Detalle": 360, "Detalle de tarea": 360,
        "Tipo": 140, "Ciclo de mejora": 150, "Complejidad": 140, "Prioridad": 130,
        "Estado": 150, "Duración": 120,
        "Fecha Registro": 150, "Hora Registro": 130,
        "Fecha inicio": 150, "Hora de inicio": 130,
        "Fecha Vencimiento": 150, "Hora Vencimiento": 130,
        "Fecha Terminado": 150, "Hora Terminado": 130,
        "¿Generó alerta?": 160, "N° de alerta": 130,
        "Fecha de detección": 170, "Hora de detección": 150,
        "¿Se corrigió?": 140, "Fecha de corrección": 170, "Hora de corrección": 150,
        "Calificación": 140,
        "Fecha Pausado": 150, "Hora Pausado": 130,
        "Fecha Cancelado": 150, "Hora Cancelado": 130,
        "Fecha Eliminado": 150, "Hora Eliminado": 130,
        "Link de descarga": 260,
    }

    # Renombres de encabezado y edición habilitada en 2 columnas
    header_map = {
        "Detalle": "Detalle de tarea",
        "Fecha Vencimiento": "Fecha límite",
        "Hora Vencimiento": "Hora límite",
        "Fecha inicio": "Fecha de inicio",
        "Hora de inicio": "Hora de inicio",
        "Fecha Registro": "Fecha de registro",
        "Hora Registro": "Hora de registro",
    }

    for col in df_grid.columns:
        nice = header_map.get(col, col)
        gob.configure_column(
            col,
            headerName=nice,
            minWidth=width_map.get(nice, width_map.get(col, 120)),
            editable=(col in ["Tarea", "Detalle"]),  # SOLO estas dos
            suppressMenu=True
        )

    # Formato fecha (dd/mm/aaaa) en visibles
    date_only_fmt = JsCode(r"""
    function(p){
      const v = p.value;
      if(v===null || v===undefined) return '—';
      const s = String(v).trim(); if(!s || ['nan','nat','null'].includes(s.toLowerCase())) return '—';
      let y,m,d; const m1 = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if(m1){ y=+m1[1]; m=+m1[2]; d=+m1[3]; }
      else{ const dt = new Date(s); if(!isNaN(dt)){ y=dt.getFullYear(); m=dt.getMonth()+1; d=dt.getDate(); } }
      if(!y) return s.split(' ')[0];
      return String(d).padStart(2,'0') + '/' + String(m).padStart(2,'0') + '/' + y;
    }""")
    for col in ["Fecha Registro","Fecha inicio","Fecha Vencimiento","Fecha Terminado",
                "Fecha Pausado","Fecha Cancelado","Fecha Eliminado",
                "Fecha de detección","Fecha de corrección"]:
        if col in df_grid.columns:
            gob.configure_column(col, valueFormatter=date_only_fmt)

    # Link de descarga desde "Archivo"
    link_value_getter = JsCode(r"""
    function(p){
      const raw0 = (p && p.data && p.data['Archivo']!=null) ? String(p.data['Archivo']).trim() : '';
      if(!raw0) return '';
      const parts = raw0.split(/[\n,;|]+/).map(s=>s.trim()).filter(Boolean);
      for (let s of parts){ if(/^https?:\/\//i.test(s)) return s; }
      return '';
    }""")
    link_renderer = JsCode(r"""
    class LinkRenderer{
      init(params){
        const url = params && params.value ? String(params.value) : '';
        this.eGui = document.createElement('a');
        if(url){
          this.eGui.href = encodeURI(url); this.eGui.target = '_blank'; this.eGui.rel='noopener';
          this.eGui.textContent = url; this.eGui.style.textDecoration='underline';
        }else{ this.eGui.textContent = '—'; this.eGui.style.opacity='0.8'; }
      }
      getGui(){ return this.eGui; } refresh(){ return false; }
    }""")
    gob.configure_column("Link de descarga", valueGetter=link_value_getter,
                         cellRenderer=link_renderer, tooltipField="Link de descarga",
                         minWidth=width_map["Link de descarga"], flex=1)

    gob.configure_grid_options(
        domLayout="normal",
        rowHeight=34,
        headerHeight=64,
        enableRangeSelection=True,
        enableCellTextSelection=True,
        singleClickEdit=True,
        stopEditingWhenCellsLoseFocus=True,
        undoRedoCellEditing=False,
        ensureDomOrder=True,
        suppressMovableColumns=False,
        suppressHeaderVirtualisation=True,
    )

    grid_opts = gob.build()
    grid_opts["rememberSelection"] = True
    grid_opts["floatingFilter"] = False

    # === Render + persistencia de ediciones ===
    grid_resp = AgGrid(
        df_grid,
        key="grid_historial",
        gridOptions=grid_opts,
        theme="balham",
        height=500,
        fit_columns_on_grid_load=False,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=(GridUpdateMode.MODEL_CHANGED
                     | GridUpdateMode.FILTERING_CHANGED
                     | GridUpdateMode.SORTING_CHANGED
                     | GridUpdateMode.VALUE_CHANGED),
        allow_unsafe_jscode=True,
    )

    # Guardar ediciones en sesión
    try:
        edited = grid_resp["data"]
        if isinstance(edited, list):
            st.session_state["df_main"] = pd.DataFrame(edited)
        elif hasattr(grid_resp, "data"):
            st.session_state["df_main"] = pd.DataFrame(grid_resp.data)
    except Exception:
        pass

    # ===== Botonera =====
    st.markdown('<div style="padding:0 16px; border-top:2px solid #EF4444">', unsafe_allow_html=True)
    _sp, b_xlsx, b_sync, b_save_local, b_save_sheets = st.columns([4.9,1.6,1.4,1.4,2.2], gap="medium")

    with b_xlsx:
        try:
            base = st.session_state["df_main"].copy()
            for c in ["__SEL__","__DEL__","¿Eliminar?"]:
                if c in base.columns: base.drop(columns=[c], inplace=True, errors="ignore")
            xlsx_b = export_excel(base, sheet_name=TAB_NAME)
            st.download_button("⬇️ Exportar Excel", data=xlsx_b,
                               file_name="tareas.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception as e:
            st.warning(f"No pude generar Excel: {e}")

    with b_sync:
        if st.button("🔄 Sincronizar", use_container_width=True, key="btn_sync_sheet"):
            try: pull_user_slice_from_sheet(replace_df_main=True)
            except Exception as e: st.warning(f"No se pudo sincronizar: {e}")

    with b_save_local:
        if st.button("💾 Grabar", use_container_width=True):
            try: _save_local(st.session_state["df_main"].copy()); st.success("Datos grabados en data/tareas.csv.")
            except Exception as e: st.warning(f"No se pudo grabar localmente: {e}")

    with b_save_sheets:
        if st.button("📤 Subir a Sheets", use_container_width=True):
            try: push_user_slice_to_sheet(); st.success("Enviado a Google Sheets.")
            except Exception as e: st.warning(f"No se pudo subir a Sheets: {e}")

    st.markdown('</div>', unsafe_allow_html=True)
