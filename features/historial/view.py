# features/historial/view.py
from __future__ import annotations

import os
import re
from io import BytesIO
from datetime import datetime, time, date

import pandas as pd
import streamlit as st
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

# ================== Helpers propios (sin importar Dashboard) ==================
TAB_NAME = "Tareas"

# Columnas mínimas para inicialización segura de df_main
DEFAULT_COLS = [
    "Id","Área","Fase","Responsable",
    "Tarea","Tipo","Detalle","Ciclo de mejora","Complejidad","Prioridad",
    "Estado","Duración",
    "Fecha Registro","Hora Registro",
    "Fecha inicio","Hora de inicio",
    "Fecha Vencimiento","Hora Vencimiento",
    "Fecha Terminado","Hora Terminado",
    "¿Generó alerta?","Fecha de detección","Hora de detección",
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
        if not s or s.lower() in {"nan", "nat", "none", "null"}:
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

def render(user: dict | None = None):
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # Alineaciones
    A_f, Fw_f, T_width_f, D_f, R_f, C_f = 1.80, 2.10, 3.00, 1.60, 1.40, 1.20

    # Título
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
        </style>
        <div class="hist-title-pill">📝 Tareas recientes</div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Estilos
    st.markdown("""
    <style>
    :root{
      --hist-pill:#F28B85;
      --hist-card-bg:#FFEDEB;
      --hist-card-bd:#F3B6B1;
      --hist-help-bg:#FFE7E6;
      --hist-help-border:#F3B6B1;
      --hist-help-text:#7A2E2A;
      --hist-pad-x:16px;
      --hist-border-w:2px; --hist-border-c:#EF4444;
      --muted-fg:#90A4AE;
    }
    #hist-card-anchor + div{
      background:var(--hist-card-bg)!important; border:1px solid var(--hist-card-bd)!important;
      border-radius:10px; padding:14px; box-shadow:0 0 0 1px rgba(0,0,0,0.02) inset; margin-bottom:6px;
    }
    .section-hist .help-strip-hist{
      background:var(--hist-help-bg)!important; color:var(--hist-help-text)!important;
      border:1px dashed var(--hist-help-border)!important; box-shadow:0 0 0 1px var(--hist-help-border) inset!important;
      border-radius:8px; padding:8px 12px; font-size:0.95rem;
    }
    #hist-card-anchor + div .form-card{ background:#fff; border:1px solid var(--hist-card-bd); border-radius:10px; padding:12px; margin-top:6px; }
    .form-card .field-wrap{ background:#F5F7FA; border:1px solid #E3E8EF; border-radius:10px; padding:6px 10px; box-shadow: inset 0 1px 0 rgba(0,0,0,0.02); }
    .form-card .field-wrap label{ margin-bottom:6px !important; }
    .hist-search .stButton>button{ height:38px!important; border-radius:10px!important; width:100%; }
    .ag-theme-balham .row-deleted .ag-cell {
      text-decoration: line-through; background-color:#FEE2E2 !important; color:#7F1D1D !important; opacity:.95;
    }
    .hist-actions{ padding-left:var(--hist-pad-x)!important; padding-right:var(--hist-pad-x)!important; border-top:var(--hist-border-w) solid var(--hist-border-c); }
    .hist-actions [data-testid="column"] > div{ display:flex; align-items:center; height:46px; }
    .hist-actions .stButton > button{ height:38px!important; border-radius:10px!important; width:100%; white-space:nowrap; }
    .ag-theme-balham .ag-header-cell.muted-col .ag-header-cell-label{ color:var(--muted-fg)!important; }
    .ag-theme-balham .ag-header, .ag-theme-balham .ag-header-cell,
    .ag-theme-balham .ag-header-cell-label, .ag-theme-balham .ag-header-cell-text{
      white-space:normal!important; overflow:visible!important; text-overflow:clip!important; line-height:1.2!important;
    }
    .ag-theme-balham .ag-pinned-left-header .ag-header-cell,
    .ag-theme-balham .ag-pinned-left-header .ag-header-cell-label,
    .ag-theme-balham .ag-pinned-left-header .ag-header-cell-text{
      white-space:normal!important; overflow:visible!important; text-overflow:clip!important; line-height:1.2!important;
    }
    </style>
    """, unsafe_allow_html=True)

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

    # ===== Card filtros =====
    st.markdown('<div id="hist-card-anchor"></div>', unsafe_allow_html=True)
    with st.container():
        st.markdown(
            """
            <div class="section-hist">
              <div class="help-strip-hist" id="hist-help">
                📌 <strong>Filtra y guarda tus tareas.</strong>
                “Tarea” y “Detalle” solo se editan para correcciones.
                <strong>Excel:</strong> opcional · <strong>Sheets:</strong> obligatorio para que el avance quede en el historial.
              </div>
              <div class="form-card">
            """,
            unsafe_allow_html=True
        )

        W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BUSCAR = 1.15, 1.25, 1.60, 1.05, 1.05, 1.05
        cA, cF, cR, cD, cH, cB = st.columns(
            [W_AREA, W_FASE, W_RESP, W_DESDE, W_HASTA, W_BUSCAR],
            gap="medium",
            vertical_alignment="bottom"
        )

        with cA:
            st.markdown('<div class="field-wrap">', unsafe_allow_html=True)
            area_sel = st.selectbox(
                "Área",
                options=["Todas"] + st.session_state.get(
                    "AREAS_OPC",
                    ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
                ),
                index=0, key="hist_area"
            )
            st.markdown('</div>', unsafe_allow_html=True)

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        with cF:
            st.markdown('<div class="field-wrap">', unsafe_allow_html=True)
            fase_sel = st.selectbox("Fase", options=["Todas"] + fases_all, index=0, key="hist_fase")
            st.markdown('</div>', unsafe_allow_html=True)

        df_resp_src = df_all.copy()
        if area_sel != "Todas":
            df_resp_src = df_resp_src[df_resp_src["Área"] == area_sel]
        if fase_sel != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == fase_sel]
        responsables = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])

        with cR:
            st.markdown('<div class="field-wrap">', unsafe_allow_html=True)
            resp_multi = st.multiselect(
                "Responsable",
                options=responsables,
                default=[],
                key="hist_resp",
                placeholder="Selecciona responsable(s)"
            )
            st.markdown('</div>', unsafe_allow_html=True)

        today = date.today()
        with cD:
            st.markdown('<div class="field-wrap">', unsafe_allow_html=True)
            f_desde = st.date_input("Desde", value=today, key="hist_desde")
            st.markdown('</div>', unsafe_allow_html=True)

        with cH:
            st.markdown('<div class="field-wrap">', unsafe_allow_html=True)
            f_hasta = st.date_input("Hasta",  value=today, key="hist_hasta")
            st.markdown('</div>', unsafe_allow_html=True)

        with cB:
            st.markdown('<div class="hist-search">', unsafe_allow_html=True)
            hist_do_buscar = st.button("🔍 Buscar", use_container_width=True, key="hist_btn_buscar")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("</div></div>", unsafe_allow_html=True)

    show_deleted = st.toggle("Mostrar eliminadas (tachadas)", value=True, key="hist_show_deleted")

    # ---- Filtros ----
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
    for c in ["Fecha estado modificado", "Fecha estado actual", "Fecha inicio"]:
        if c not in df_view.columns:
            df_view[c] = pd.NaT
    ts_mod = to_naive_local_series(df_view["Fecha estado modificado"])
    ts_act = to_naive_local_series(df_view["Fecha estado actual"])
    ts_ini = to_naive_local_series(df_view["Fecha inicio"])
    df_view["__ts__"] = ts_mod.combine_first(ts_act).combine_first(ts_ini)
    df_view = df_view.sort_values("__ts__", ascending=False, na_position="last")

    st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)

    # Fix duplicadas
    df_view = df_view.loc[:, ~df_view.columns.duplicated()].copy()
    df_view.columns = df_view.columns.astype(str)

    # Helpers
    def _to_date(v):
        if pd.isna(v): return pd.NaT
        if isinstance(v, (pd.Timestamp, datetime)): return pd.Timestamp(v).normalize()
        d = pd.to_datetime(str(v), errors="coerce")
        return d.normalize() if not pd.isna(d) else pd.NaT

    def _to_hhmm(v):
        return _fmt_hhmm(v)

    # Estado modificado → Estado
    if "Estado modificado" in df_view.columns:
        _em = df_view["Estado modificado"].astype(str).str.strip()
        mask_em = _em.notna() & _em.ne("") & _em.ne("nan")
        if "Estado" not in df_view.columns:
            df_view["Estado"] = ""
        df_view.loc[mask_em, "Estado"] = _em[mask_em]

    if "Estado" not in df_view.columns:
        df_view["Estado"] = ""
    df_view["Estado"] = df_view["Estado"].apply(lambda s: "No iniciado" if str(s).strip() in {"", "nan", "NaN"} else s)

    if "Fecha Registro" not in df_view.columns: df_view["Fecha Registro"] = pd.NaT
    if "Hora Registro"   not in df_view.columns: df_view["Hora Registro"]   = ""

    df_view["Fecha Registro"] = df_view["Fecha Registro"].apply(_to_date)
    df_view["Hora Registro"]  = df_view["Hora Registro"].apply(_to_hhmm)

    _fr_fb = to_naive_local_series(df_view["Fecha"]) if "Fecha" in df_view.columns else pd.Series(pd.NaT, index=df_view.index)
    _hr_fb = df_view["Hora"].apply(_to_hhmm) if "Hora" in df_view.columns else pd.Series([""]*len(df_view), index=df_view.index)

    mask_fr_missing = df_view["Fecha Registro"].isna()
    mask_hr_missing = (df_view["Hora Registro"].eq("")) | (df_view["Hora Registro"].eq("00:00"))
    df_view.loc[mask_fr_missing, "Fecha Registro"] = _fr_fb[mask_fr_missing].dt.normalize()
    df_view.loc[mask_hr_missing, "Hora Registro"]  = _hr_fb[mask_hr_missing]

    if "Hora de inicio" not in df_view.columns: df_view["Hora de inicio"] = ""
    if "Fecha Terminado" not in df_view.columns: df_view["Fecha Terminado"] = pd.NaT
    if "Hora Terminado" not in df_view.columns: df_view["Hora Terminado"] = ""

    if "Fecha terminado" in df_view.columns:
        _tmp_ft = to_naive_local_series(df_view["Fecha terminado"])
        df_view["Fecha Terminado"] = df_view["Fecha Terminado"].combine_first(_tmp_ft)
        df_view.drop(columns=["Fecha terminado"], inplace=True, errors="ignore")

    # Sellos de estado
    _mod  = to_naive_local_series(df_view.get("Fecha estado modificado"))
    _hmod = df_view["Hora estado modificado"].apply(_to_hhmm) if "Hora estado modificado" in df_view.columns else pd.Series([""]*len(df_view), index=df_view.index)

    _fact = to_naive_local_series(df_view.get("Fecha estado actual"))
    _hact = df_view["Hora estado actual"].apply(_to_hhmm) if "Hora estado actual" in df_view.columns else pd.Series([""]*len(df_view), index=df_view.index)

    if "Estado" in df_view.columns:
        _estado_norm = df_view["Estado"].astype(str).str.lower().str.strip()
        _en_curso  = _estado_norm.isin(["en curso","en progreso","progreso"])
        _terminado = _estado_norm.isin(["terminado","terminada","finalizado","finalizada","completado","completada"])

        _src_ini_dt = _mod.combine_first(_fact)
        _src_ini_tm = _hmod.where(_hmod != "", _src_ini_dt.dt.strftime("%H:%M")).where(lambda s: s != "", _hact)

        need_ini_dt = _en_curso & df_view["Fecha inicio"].isna()
        need_ini_tm = _en_curso & (df_view["Hora de inicio"].astype(str).str.strip() == "")
        df_view.loc[need_ini_dt, "Fecha inicio"]   = _src_ini_dt.dt.normalize()[need_ini_dt]
        df_view.loc[need_ini_tm, "Hora de inicio"] = _src_ini_tm[need_ini_tm]

        _src_fin_dt = _mod.combine_first(_fact)
        _src_fin_tm = _hmod.where(_hmod != "", _src_fin_dt.dt.strftime("%H:%M")).where(lambda s: s != "", _hact)

        need_fin_dt = _terminado & df_view["Fecha Terminado"].isna()
        need_fin_tm = _terminado & (df_view["Hora Terminado"].astype(str).str.strip() == "") if "Hora Terminado" in df_view.columns else False
        df_view.loc[need_fin_dt, "Fecha Terminado"] = _src_fin_dt[need_fin_dt]
        if "Hora Terminado" in df_view.columns:
            df_view.loc[need_fin_tm, "Hora Terminado"] = _src_fin_tm[need_fin_tm]

    # Vencimiento
    if "Fecha Vencimiento" not in df_view.columns: df_view["Fecha Vencimiento"] = pd.NaT
    if "Hora Vencimiento" not in df_view.columns:  df_view["Hora Vencimiento"]  = ""
    if "Vencimiento" in df_view.columns:
        _vdt = to_naive_local_series(df_view["Vencimiento"])
        mask_fv = df_view["Fecha Vencimiento"].isna()
        df_view.loc[mask_fv, "Fecha Vencimiento"] = _vdt.dt.normalize()[mask_fv]
        hv_from = _vdt.dt.strftime("%H:%M")
        hv_now = df_view["Hora Vencimiento"].astype(str).str.strip()
        mask_hv = hv_now.eq("") | hv_now.eq("00:00")
        df_view.loc[mask_hv, "Hora Vencimiento"] = hv_from[mask_hv]
    df_view["Fecha Vencimiento"] = df_view["Fecha Vencimiento"].apply(_to_date)
    df_view["Hora Vencimiento"]  = df_view["Hora Vencimiento"].apply(_to_hhmm)
    df_view.loc[df_view["Hora Vencimiento"] == "", "Hora Vencimiento"] = "17:00"

    # Orden y presencia de columnas
    target_cols = [
        "Id","Área","Fase","Responsable",
        "Tarea","Tipo","Detalle","Ciclo de mejora","Complejidad","Prioridad",
        "Estado","Duración",
        "Fecha Registro","Hora Registro",
        "Fecha inicio","Hora de inicio",
        "Fecha Vencimiento","Hora Vencimiento",
        "Fecha Terminado","Hora Terminado",
        "¿Generó alerta?","Fecha de detección","Hora de detección",
        "¿Se corrigió?","Fecha de corrección","Hora de corrección",
        "Cumplimiento","Evaluación","Calificación",
        "Fecha Pausado","Hora Pausado",
        "Fecha Cancelado","Hora Cancelado",
        "Fecha Eliminado","Hora Eliminado",
        "__SEL__","__DEL__",
        "Archivo"
    ]
    HIDDEN_COLS = [
        "¿Eliminar?","Estado modificado",
        "Fecha estado modificado","Hora estado modificado",
        "Fecha estado actual","Hora estado actual",
        "N° de alerta","Tipo de alerta","Fecha","Hora","Vencimiento",
        "__ts__","__DEL__","__SEL__"
    ]

    for c in target_cols:
        if c not in df_view.columns:
            df_view[c] = False if c in ["__SEL__","__DEL__"] else ""

    df_view["Duración"] = df_view["Duración"].astype(str).fillna("")
    df_grid = df_view.reindex(
        columns=list(dict.fromkeys(target_cols)) +
        [c for c in df_view.columns if c not in target_cols + HIDDEN_COLS]
    ).copy()
    df_grid = df_grid.loc[:, ~df_grid.columns.duplicated()].copy()
    df_grid["Id"] = df_grid["Id"].astype(str).fillna("")

    for tech_col in ["__SEL__", "__DEL__", "¿Eliminar?"]:
        if tech_col in df_grid.columns:
            df_grid.drop(columns=[tech_col], inplace=True, errors="ignore")

    # =============== GRID OPTIONS ===============
    gob = GridOptionsBuilder.from_dataframe(df_grid)
    gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True, editable=False)
    gob.configure_selection(selection_mode="multiple", use_checkbox=False)
    gob.configure_grid_options(
        rowSelection="multiple",
        rowMultiSelectWithClick=True,
        suppressRowClickSelection=False,
        domLayout="normal",
        rowHeight=30,
        wrapHeaderText=True, autoHeaderHeight=True, headerHeight=56,
        enableRangeSelection=True, enableCellTextSelection=True,
        singleClickEdit=False, stopEditingWhenCellsLoseFocus=True,
        undoRedoCellEditing=False, enterMovesDown=False,
        suppressMovableColumns=False,
        getRowId=JsCode("function(p){ return (p.data && (p.data.Id || p.data['Id'])) + ''; }"),
        suppressHeaderVirtualisation=True,
    )

    gob.configure_column("Id", headerName="ID", editable=False, minWidth=110, pinned="left", suppressMovable=True)
    gob.configure_column("Área", headerName="Área", editable=False, minWidth=160, pinned="left", suppressMovable=True)
    gob.configure_column("Fase", headerName="Fase", editable=False, minWidth=140, pinned="left", suppressMovable=True)
    gob.configure_column("Responsable", editable=False, minWidth=200, pinned="left", suppressMovable=True)
    gob.configure_column("Estado", headerName="Estado actual")
    gob.configure_column("Fecha Vencimiento", headerName="Fecha límite")
    gob.configure_column("Fecha inicio", headerName="Fecha de inicio")
    gob.configure_column("Fecha Terminado", headerName="Fecha Terminado")

    # ==== Archivo: renderer textual (sin DOM nodes) + estilo de link ====
    archivo_renderer = JsCode("""
    function(p){
      const raw = (p && p.value != null) ? String(p.value).trim() : '';
      if(!raw) return '—';
      return '📎 Descargar';  // El click se maneja abajo (onCellClicked)
    }
    """)
    if "Archivo" in df_grid.columns:
        gob.configure_column(
            "Archivo",
            headerName="Archivo",
            minWidth=170,
            flex=0,
            editable=False,
            cellRenderer=archivo_renderer,
            tooltipField="Archivo",
            cellStyle={"cursor":"pointer","textDecoration":"underline","color":"#0A66C2"}
        )

    # Fmt
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
         const s=String(p.value).trim(); if(/^\\d{4}-\\d{2}-\\d{2}$/.test(s)) return s;
         return '—';
      }
      const pad=n=>String(n).padStart(2,'0');
      return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
    }""")
    time_only_fmt = JsCode(r"""
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

    colw = {
        "Tarea":280, "Tipo":180, "Detalle":240, "Ciclo de mejora":140,
        "Complejidad":130, "Prioridad":130, "Estado":130, "Duración":110,
        "Fecha Registro":160, "Hora Registro":140,
        "Fecha inicio":160, "Hora de inicio":140,
        "Fecha Vencimiento":160, "Hora Vencimiento":140,
        "Fecha Terminado":160, "Hora Terminado":140,
        "¿Generó alerta?":150, "Fecha de detección":160, "Hora de detección":140,
        "¿Se corrigió?":140, "Fecha de corrección":160, "Hora de corrección":140,
        "Cumplimiento":180, "Evaluación":170, "Calificación":120,
        "Fecha Pausado":160, "Hora Pausado":140,
        "Fecha Cancelado":160, "Hora Cancelado":140,
        "Fecha Eliminado":160, "Hora Eliminado":140,
        "Archivo":170
    }

    for c, fx in [("Tarea",3), ("Tipo",1), ("Detalle",2), ("Ciclo de mejora",1), ("Complejidad",1), ("Prioridad",1), ("Estado",1),
                  ("Duración",1), ("Fecha Registro",1), ("Hora Registro",1),
                  ("Fecha inicio",1), ("Hora de inicio",1),
                  ("Fecha Vencimiento",1), ("Hora Vencimiento",1),
                  ("Fecha Terminado",1), ("Hora Terminado",1),
                  ("¿Generó alerta?",1), ("Fecha de detección",1), ("Hora de detección",1),
                  ("¿Se corrigió?",1), ("Fecha de corrección",1), ("Hora de corrección",1),
                  ("Cumplimiento",1), ("Evaluación",1), ("Calificación",0),
                  ("Fecha Pausado",1), ("Hora Pausado",1),
                  ("Fecha Cancelado",1), ("Hora Cancelado",1),
                  ("Fecha Eliminado",1), ("Hora Eliminado",1),
                  ("Archivo",0)]:
        if c in df_grid.columns:
            gob.configure_column(
                c,
                editable=False,
                minWidth=colw.get(c,120),
                flex=fx,
                valueFormatter=(
                    date_only_fmt if c in ["Fecha Registro","Fecha inicio","Fecha Vencimiento",
                                           "Fecha Pausado","Fecha Cancelado","Fecha Eliminado","Fecha Terminado"] else
                    time_only_fmt if c in ["Hora Registro","Hora de inicio","Hora Pausado","Hora Cancelado","Hora Eliminado",
                                           "Hora Terminado","Hora de detección","Hora de corrección","Hora Vencimiento"] else
                    date_time_fmt if c in ["Fecha de detección","Hora de corrección"] else
                    (None if c in ["Calificación","Prioridad","Archivo"] else fmt_dash)
                ),
                suppressMenu=True if c in ["Fecha Registro","Hora Registro","Fecha inicio","Hora de inicio",
                                           "Fecha Vencimiento","Hora Vencimiento",
                                           "Fecha Terminado","Fecha de detección","Hora de detección",
                                           "Fecha de corrección","Hora de corrección",
                                           "Fecha Pausado","Hora Pausado","Fecha Cancelado","Hora Cancelado",
                                           "Fecha Eliminado","Hora Eliminado"] else False,
                filter=False if c in ["Fecha Registro","Hora Registro","Fecha inicio","Hora de inicio",
                                      "Fecha Vencimiento","Hora Vencimiento",
                                      "Fecha Terminado","Fecha de detección","Hora de detección",
                                      "Fecha de corrección","Hora de corrección",
                                      "Fecha Pausado","Hora Pausado","Fecha Cancelado","Hora Cancelado",
                                      "Fecha Eliminado","Hora Eliminado"] else None
            )

    MUTED_CELL_STYLE = {"backgroundColor":"#ECEFF1","color":"#90A4AE"}
    for cc in ["Fecha Pausado","Hora Pausado","Fecha Cancelado","Hora Cancelado","Fecha Eliminado","Hora Eliminado"]:
        if cc in df_grid.columns:
            gob.configure_column(cc, headerClass="muted-col", cellStyle=MUTED_CELL_STYLE)

    for c_edit, w in [("Tarea", colw.get("Tarea", 280)),
                      ("Tipo", colw.get("Tipo", 180)),
                      ("Detalle", colw.get("Detalle", 240))]:
        if c_edit in df_grid.columns:
            gob.configure_column(c_edit, editable=True, minWidth=w)

    row_class_rules = {
        "row-deleted": JsCode("""
            function(params){
                const est = String((params.data && params.data['Estado']) || '').trim();
                const del = !!(params.data && params.data['__DEL__']);
                return (est === 'Eliminado') || del;
            }
        """).js_code
    }

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
    sync_selection = JsCode("""
    function(params){
      const selIds = new Set(params.api.getSelectedRows().map(r => String(r.Id||r['Id']||'')));
      const updates = [];
      params.api.forEachNode(n=>{
        const id = String((n.data && (n.data.Id||n.data['Id'])) || '');
        const flag = selIds.has(id);
        if(!!n.data.__SEL__ !== flag){
          const u = Object.assign({}, n.data);
          u.__SEL__ = flag;
          updates.push(u);
        }
      });
      if(updates.length){ params.api.applyTransaction({update: updates}); }
    }
    """)

    # >>> FIX: usar el valor REAL desde e.data['Archivo'] (no el texto renderizado)
    open_url_on_click = JsCode("""
    function(e){
      if(!e || !e.colDef || e.colDef.field !== 'Archivo') return;
      const raw = (e && e.data && e.data['Archivo'] != null) ? String(e.data['Archivo']).trim() : '';
      if(!raw) return;
      if(/^https?:\\/\\//i.test(raw)){
        try{ window.open(encodeURI(raw), '_blank', 'noopener'); }catch(err){}
      }else{
        try{
          const node = e.node;
          if(node && !node.isSelected()){
            node.setSelected(true, true);
          }
        }catch(err){}
      }
    }
    """)

    grid_opts = gob.build()
    grid_opts["rowClassRules"] = row_class_rules
    grid_opts["onGridReady"] = autosize_on_ready.js_code
    grid_opts["onFirstDataRendered"] = autosize_on_data.js_code
    grid_opts["onColumnEverythingChanged"] = autosize_on_data.js_code
    grid_opts["onSelectionChanged"] = sync_selection.js_code
    grid_opts["onCellClicked"] = open_url_on_click.js_code
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

    # Guarda última data del grid
    try:
        if isinstance(grid, dict) and "data" in grid and grid["data"] is not None:
            st.session_state["_grid_historial_latest"] = pd.DataFrame(grid["data"]).copy()
    except Exception:
        pass

    # Sincroniza edición de 3 campos
    if isinstance(grid, dict) and "data" in grid and grid["data"] is not None:
        try:
            edited = pd.DataFrame(grid["data"]).copy()
            edited["Id"] = edited["Id"].astype(str)
            base = st.session_state["df_main"].copy()
            base["Id"] = base["Id"].astype(str)
            b_i = base.set_index("Id")
            e_i = edited.set_index("Id")
            common = b_i.index.intersection(e_i.index)
            b_i.loc[common, ["Tarea", "Tipo", "Detalle"]] = e_i.loc[common, ["Tarea", "Tipo", "Detalle"]]
            st.session_state["df_main"] = b_i.reset_index()
        except Exception:
            pass

    # ===== Descarga de archivos (fila seleccionada) =====
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    sel_rows = []
    try:
        sel_rows = grid.get("selected_rows") or []
    except Exception:
        sel_rows = []
    if isinstance(sel_rows, pd.DataFrame):
        sel_rows = sel_rows.to_dict("records")

    def _resolve_local_path(val: str, row_id: str) -> tuple[str, str] | None:
        if not val:
            return None
        v = str(val).strip()
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

    has_any_download = False
    for r in sel_rows:
        rid = str(r.get("Id","")).strip()
        av  = str(r.get("Archivo","")).strip()
        if not rid or not av:
            continue
        if av.lower().startswith(("http://","https://")):
            st.link_button(f"📎 Abrir archivo ({rid})", av, use_container_width=False)
            has_any_download = True
        else:
            res = _resolve_local_path(av, rid)
            if res:
                path, fname = res
                try:
                    with open(path, "rb") as fh:
                        st.download_button(f"⬇️ Descargar ({rid}) — {fname}", fh.read(), file_name=fname, use_container_width=False)
                        has_any_download = True
                except Exception:
                    pass
    if (sel_rows and not has_any_download):
        st.info("La fila seleccionada tiene valor en “Archivo”, pero no encontré un archivo local ni URL válida.")

    # ---- Botonera ----
    left_spacer = A_f + Fw_f + T_width_f
    W_SHEETS = R_f + 0.8

    st.markdown('<div class="hist-actions">', unsafe_allow_html=True)
    _spacer, b_xlsx, b_sync, b_save_local, b_save_sheets = st.columns(
        [left_spacer, D_f, R_f, R_f, W_SHEETS], gap="medium"
    )

    with b_xlsx:
        try:
            df_xlsx = st.session_state["df_main"].copy()
            drop_cols = [c for c in ("__DEL__", "DEL", "__SEL__", "¿Eliminar?") if c in df_xlsx.columns]
            if drop_cols:
                df_xlsx.drop(columns=drop_cols, inplace=True, errors="ignore")
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
