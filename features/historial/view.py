# features/historial/view.py
from __future__ import annotations

import re
from io import BytesIO
from datetime import datetime, time

import pandas as pd
import streamlit as st
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

# ====== Soporte de exportación ======
TAB_NAME = "Tareas"

def export_excel(df: pd.DataFrame, sheet_name: str = TAB_NAME) -> bytes:
    """Devuelve un XLSX en bytes. Usa xlsxwriter y cae a openpyxl si no está."""
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
    # ================== Historial ==================

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ---- TÍTULO EN PÍLDORA (ajuste solicitado) ----
    st.markdown("""
    <style>
    /* ====== Píldora de título (tono IMAGEN 2) ====== */
    :root{
      --pill-coral:#F25F6A; /* coral/rosado cálido */
    }
    .hist-title-wrap{
      display:flex; align-items:center;
    }
    .hist-title-pill{
      display:inline-flex; align-items:center; gap:8px;
      padding:8px 14px;
      border-radius:14px; /* antes 9999px: ahora menos curvo */
      background: var(--pill-coral);
      color:#fff; font-weight:600; font-size:1.10rem; line-height:1;
      box-shadow: inset 0 -2px 0 rgba(0,0,0,0.08);
    }
    </style>
    <div class="hist-title-wrap">
      <span class="hist-title-pill">📝 Tareas recientes</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # --- Estilos globales (filas eliminadas, filtros/acciones y headers) ---
    st.markdown("""
    <style>
    /* Fila tachada (Eliminado) */
    .ag-theme-balham .row-deleted .ag-cell {
      text-decoration: line-through;
      background-color: #FEE2E2 !important;
      color: #7F1D1D !important;
      opacity: 0.95;
    }

    /* ===== Alineación exacta contenedor de acciones ===== */
    :root{
      --hist-pad-x: 16px;       /* padding lateral del contenedor de botones */
      --hist-border-w: 2px;     /* grosor de la línea superior (roja) */
      --hist-border-c: #EF4444; /* color de la línea */
    }
    .hist-actions{
      padding-left: var(--hist-pad-x) !important;
      padding-right: var(--hist-pad-x) !important;
      border-top: var(--hist-border-w) solid var(--hist-border-c);
    }
    /* Centrar verticalmente el contenido de cada columna de la franja de acciones */
    .hist-actions [data-testid="column"] > div{
      display: flex; align-items: center; height: 46px;
    }
    /* Botones de acciones: misma altura y ancho adaptable */
    .hist-actions .stButton > button{
      height: 38px !important;
      border-radius: 10px !important;
      width: 100%;
    }

    /* Alinear el botón Buscar con la fila de filtros (bájalo un poco más) */
    .hist-search .stButton > button{
      margin-top: 12px !important;
      height: 38px !important;
    }

    /* Encabezados gris tenue para columnas Pausado/Cancelado/Eliminado */
    :root{ --muted-bg:#ECEFF1; --muted-fg:#90A4AE; }
    .ag-theme-balham .ag-header-cell.muted-col .ag-header-cell-label{
      color: var(--muted-fg) !important;
    }

    /* === Mostrar encabezados completos (sin recorte) === */
    .ag-theme-balham .ag-header,
    .ag-theme-balham .ag-header-cell,
    .ag-theme-balham .ag-header-cell-label,
    .ag-theme-balham .ag-header-cell-text{
      white-space: normal !important;
      overflow: visible !important;
      text-overflow: clip !important;
      line-height: 1.2 !important;
    }
    /* También en columnas ancladas (Id, Área, Fase) */
    .ag-theme-balham .ag-pinned-left-header .ag-header-cell,
    .ag-theme-balham .ag-pinned-left-header .ag-header-cell-label,
    .ag-theme-balham .ag-pinned-left-header .ag-header-cell-text{
      white-space: normal !important;
      overflow: visible !important;
      text-overflow: clip !important;
      line-height: 1.2 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Base
    df_all = st.session_state["df_main"].copy()

    # ===== Proporciones de filtros =====
    A_f, Fw_f, T_width_f, D_f, R_f, C_f = 1.80, 2.10, 3.00, 1.60, 1.40, 1.20

    # ===== FILA DE 5 FILTROS + Buscar =====
    with st.form("hist_filtros_v1", clear_on_submit=False):
        cA, cF, cR, cD, cH, cB = st.columns(
            [A_f, Fw_f, T_width_f, D_f, R_f, C_f],
            gap="medium",
            vertical_alignment="bottom"
        )

        area_sel = cA.selectbox(
            "Área",
            options=["Todas"] + st.session_state.get(
                "AREAS_OPC",
                ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
            ),
            index=0, key="hist_area"
        )

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        fase_sel = cF.selectbox("Fase", options=["Todas"] + fases_all, index=0, key="hist_fase")

        df_resp_src = df_all.copy()
        if area_sel != "Todas":
            df_resp_src = df_resp_src[df_resp_src["Área"] == area_sel]
        if fase_sel != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == fase_sel]
        responsables = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        resp_sel = cR.selectbox("Responsable", options=["Todos"] + responsables, index=0, key="hist_resp")

        f_desde = cD.date_input("Desde", value=None, key="hist_desde")
        f_hasta = cH.date_input("Hasta",  value=None, key="hist_hasta")

        # 🔧 Botón alineado con la fila
        with cB:
            st.markdown('<div class="hist-search">', unsafe_allow_html=True)
            hist_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # Toggle mostrar/ocultar eliminadas
    show_deleted = st.toggle("Mostrar eliminadas (tachadas)", value=True, key="hist_show_deleted")

    # ---- Aplicar filtros sobre df_view SOLO si se presiona Buscar ----
    df_view = df_all.copy()
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

    # Ocultar eliminadas si el toggle está OFF
    if not show_deleted and "Estado" in df_view.columns:
        df_view = df_view[df_view["Estado"].astype(str).str.strip() != "Eliminado"]

    # ===== ORDEN POR RECIENTES =====
    for c in ["Fecha estado modificado", "Fecha estado actual", "Fecha inicio"]:
        if c not in df_view.columns:
            df_view[c] = pd.NaT

    ts_mod = pd.to_datetime(df_view["Fecha estado modificado"], errors="coerce")
    ts_act = pd.to_datetime(df_view["Fecha estado actual"], errors="coerce")
    ts_ini = pd.to_datetime(df_view["Fecha inicio"], errors="coerce")
    df_view["__ts__"] = ts_mod.combine_first(ts_act).combine_first(ts_ini)
    df_view = df_view.sort_values("__ts__", ascending=False, na_position="last")

    st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)

    # --- FIX: eliminar columnas duplicadas ---
    df_view = df_view.loc[:, ~df_view.columns.duplicated()].copy()
    df_view.columns = df_view.columns.astype(str)

    # ===== Helpers =====
    def _to_date(v):
        if pd.isna(v): return pd.NaT
        if isinstance(v, (pd.Timestamp, datetime)): return pd.Timestamp(v).normalize()
        d = pd.to_datetime(str(v), errors="coerce")
        return d.normalize() if not pd.isna(d) else pd.NaT

    def _to_hhmm(v):
        if v is None or (isinstance(v, float) and pd.isna(v)): return ""
        try:
            if isinstance(v, time):      return f"{v.hour:02d}:{v.minute:02d}"
            if isinstance(v, (pd.Timestamp, datetime)): return f"{v.hour:02d}:{v.minute:02d}"
            s = str(v).strip()
            if not s or s.lower() in {"nan","nat","none","null"}: return ""
            m = re.match(r"^(\d{1,2}):(\d{2})", s)
            if m: return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
            d = pd.to_datetime(s, errors="coerce")
            if not pd.isna(d): return f"{int(d.hour):02d}:{int(d.minute):02d}"
        except Exception:
            pass
        return ""

    # ===== Semántica de tiempos / estado =====
    if "Estado modificado" in df_view.columns:
        _em = df_view["Estado modificado"].astype(str).str.strip()
        mask_em = _em.notna() & _em.ne("") & _em.ne("nan")
        if "Estado" not in df_view.columns:
            df_view["Estado"] = ""
        df_view.loc[mask_em, "Estado"] = _em[mask_em]

    if "Fecha Registro" not in df_view.columns: df_view["Fecha Registro"] = pd.NaT
    if "Hora Registro"   not in df_view.columns: df_view["Hora Registro"]   = ""

    df_view["Fecha Registro"] = df_view["Fecha Registro"].apply(_to_date)
    df_view["Hora Registro"]  = df_view["Hora Registro"].apply(_to_hhmm)

    _fr_fb = pd.to_datetime(df_view["Fecha"], errors="coerce").dt.normalize() if "Fecha" in df_view.columns else pd.Series(pd.NaT, index=df_view.index)
    _hr_fb = df_view["Hora"].apply(_to_hhmm) if "Hora" in df_view.columns else pd.Series([""]*len(df_view), index=df_view.index)

    mask_fr_missing = df_view["Fecha Registro"].isna()
    mask_hr_missing = (df_view["Hora Registro"].eq("")) | (df_view["Hora Registro"].eq("00:00"))

    df_view.loc[mask_fr_missing, "Fecha Registro"] = _fr_fb[mask_fr_missing]
    df_view.loc[mask_hr_missing, "Hora Registro"]  = _hr_fb[mask_hr_missing]

    if "Hora de inicio" not in df_view.columns: df_view["Hora de inicio"] = ""
    if "Fecha Terminado" not in df_view.columns: df_view["Fecha Terminado"] = pd.NaT
    if "Hora Terminado" not in df_view.columns: df_view["Hora Terminado"] = ""

    if "Fecha terminado" in df_view.columns:
        _tmp_ft = pd.to_datetime(df_view["Fecha terminado"], errors="coerce")
        df_view["Fecha Terminado"] = df_view["Fecha Terminado"].combine_first(_tmp_ft)
        df_view.drop(columns=["Fecha terminado"], inplace=True, errors="ignore")

    _mod = pd.to_datetime(df_view.get("Fecha estado modificado"), errors="coerce")
    _hmod = df_view["Hora estado modificado"].apply(_to_hhmm) if "Hora estado modificado" in df_view.columns else pd.Series([""]*len(df_view), index=df_view.index)

    if "Estado" in df_view.columns:
        _en_curso   = df_view["Estado"].astype(str) == "En curso"
        _terminado  = df_view["Estado"].astype(str) == "Terminado"

        _h_ini = _hmod.where(_hmod != "", _mod.dt.strftime("%H:%M"))
        need_ini_dt = _en_curso & df_view["Fecha inicio"].isna()
        need_ini_tm = _en_curso & (df_view["Hora de inicio"].astype(str).str.strip() == "")
        df_view.loc[need_ini_dt, "Fecha inicio"]   = _mod.dt.normalize()[need_ini_dt]
        df_view.loc[need_ini_tm, "Hora de inicio"] = _h_ini[need_ini_tm]

        need_fin_dt = _terminado & df_view["Fecha Terminado"].isna()
        need_fin_tm = _terminado & (df_view["Hora Terminado"].astype(str).str.trim() == "") if "Hora Terminado" in df_view.columns else False
        df_view.loc[need_fin_dt, "Fecha Terminado"]      = _mod[need_fin_dt]
        if "Hora Terminado" in df_view.columns:
            df_view.loc[need_fin_tm, "Hora Terminado"] = _hmod.where(_hmod != "", _mod.dt.strftime("%H:%M"))[need_fin_tm]

    # 3.b) VENCIMIENTO
    if "Fecha Vencimiento" not in df_view.columns: df_view["Fecha Vencimiento"] = pd.NaT
    if "Hora Vencimiento" not in df_view.columns:  df_view["Hora Vencimiento"]  = ""

    if "Vencimiento" in df_view.columns:
        _vdt = pd.to_datetime(df_view["Vencimiento"], errors="coerce")
        mask_fv = df_view["Fecha Vencimiento"].isna()
        df_view.loc[mask_fv, "Fecha Vencimiento"] = _vdt.dt.normalize()[mask_fv]
        hv_from = _vdt.dt.strftime("%H:%M")
        hv_now = df_view["Hora Vencimiento"].astype(str).str.strip()
        mask_hv = hv_now.eq("") | hv_now.eq("00:00")
        df_view.loc[mask_hv, "Hora Vencimiento"] = hv_from[mask_hv]

    df_view["Fecha Vencimiento"] = df_view["Fecha Vencimiento"].apply(_to_date)
    df_view["Hora Vencimiento"]  = df_view["Hora Vencimiento"].apply(_to_hhmm)
    df_view.loc[df_view["Hora Vencimiento"] == "", "Hora Vencimiento"] = "17:00"

    # === ORDEN Y PRESENCIA DE COLUMNAS ===
    target_cols = [
        "Id","Área","Fase","Responsable",
        "Tarea","Tipo","Detalle","Ciclo de mejora","Complejidad","Prioridad",
        "Estado",
        "Duración",
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
        "__SEL__","__DEL__"
    ]

    # Ocultas en grid (no visibles)
    HIDDEN_COLS = [
        "¿Eliminar?",
        "Estado modificado",
        "Fecha estado modificado","Hora estado modificado",
        "Fecha estado actual","Hora estado actual",
        "N° de alerta","Tipo de alerta",
        "Fecha","Hora",
        "Vencimiento",
        "__ts__","__DEL__","__SEL__"
    ]

    # Asegurar columnas
    for c in target_cols:
        if c not in df_view.columns:
            if c in ["__SEL__","__DEL__"]:
                df_view[c] = False
            else:
                df_view[c] = ""

    df_view["Duración"] = df_view["Duración"].astype(str).fillna("")
    df_grid = df_view.reindex(columns=list(dict.fromkeys(target_cols)) + [c for c in df_view.columns if c not in target_cols + HIDDEN_COLS]).copy()
    df_grid = df_grid.loc[:, ~df_grid.columns.duplicated()].copy()
    df_grid["Id"] = df_grid["Id"].astype(str).fillna("")

    # Remueve por completo ¿Eliminar?
    if "¿Eliminar?" in df_grid.columns:
        df_grid.drop(columns=["¿Eliminar?"], inplace=True, errors="ignore")

    # ================= GRID OPTIONS =================
    # Por defecto TODO es de solo lectura; luego habilitamos solo Tarea, Tipo, Detalle.
    gob = GridOptionsBuilder.from_dataframe(df_grid)
    gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True, editable=False)
    gob.configure_selection(selection_mode="multiple", use_checkbox=False)
    gob.configure_grid_options(
        rowSelection="multiple",
        rowMultiSelectWithClick=True,
        suppressRowClickSelection=False,
        domLayout="normal",
        rowHeight=30,
        # Encabezados completos:
        wrapHeaderText=True,
        autoHeaderHeight=True,
        headerHeight=56,
        enableRangeSelection=True,
        enableCellTextSelection=True,
        singleClickEdit=False,        # doble clic para editar
        stopEditingWhenCellsLoseFocus=True,
        undoRedoCellEditing=False,
        enterMovesDown=False,
        suppressMovableColumns=False,
        getRowId=JsCode("function(p){ return (p.data && (p.data.Id || p.data['Id'])) + ''; }"),
        suppressHeaderVirtualisation=True,
    )

    # Encabezados de las 3 primeras columnas completos y anclados
    gob.configure_column("Id", headerName="ID", editable=False, minWidth=110, pinned="left", suppressMovable=True)
    gob.configure_column("Área", headerName="Área", editable=False, minWidth=160, pinned="left", suppressMovable=True)
    gob.configure_column("Fase", headerName="Fase", editable=False, minWidth=140, pinned="left", suppressMovable=True)
    gob.configure_column("Responsable", editable=False, minWidth=200, pinned="left", suppressMovable=True)

    # —— Mostrar como lectura (nombres legibles)
    gob.configure_column("Estado",            headerName="Estado actual")
    gob.configure_column("Fecha Vencimiento", headerName="Fecha límite")
    gob.configure_column("Fecha inicio",      headerName="Fecha de inicio")
    gob.configure_column("Fecha Terminado",   headerName="Fecha Terminado")

    # Ocultar columnas internas
    for ocultar in HIDDEN_COLS:
        if ocultar in df_grid.columns:
            gob.configure_column(ocultar, hide=True, suppressMenu=True, filter=False)

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
        "Tarea":280, "Tipo":180,
        "Detalle":240, "Ciclo de mejora":140, "Complejidad":130, "Prioridad":130,
        "Estado":130, "Duración":110, "Fecha Registro":160, "Hora Registro":140,
        "Fecha inicio":160, "Hora de inicio":140,
        "Fecha Vencimiento":160, "Hora Vencimiento":140,
        "Fecha Terminado":160, "Hora Terminado":140,
        "¿Generó alerta?":150, "Fecha de detección":160, "Hora de detección":140,
        "¿Se corrigió?":140, "Fecha de corrección":160, "Hora de corrección":140,
        "Cumplimiento":180, "Evaluación":170, "Calificación":120,
        "Fecha Pausado":160, "Hora Pausado":140,
        "Fecha Cancelado":160, "Hora Cancelado":140,
        "Fecha Eliminado":160, "Hora Eliminado":140
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
                  ("Fecha Eliminado",1), ("Hora Eliminado",1)]:
        if c in df_grid.columns:
            gob.configure_column(
                c,
                editable=False,  # <— por defecto, lectura
                minWidth=colw.get(c,120),
                flex=fx,
                valueFormatter=(
                    date_only_fmt if c in ["Fecha Registro","Fecha inicio","Fecha Vencimiento",
                                           "Fecha Pausado","Fecha Cancelado","Fecha Eliminado"] else
                    time_only_fmt if c in ["Hora Registro","Hora de inicio","Hora Pausado","Hora Cancelado","Hora Eliminado",
                                           "Hora Terminado","Hora de detección","Hora de corrección","Hora Vencimiento"] else
                    date_time_fmt if c in ["Fecha Terminado","Fecha de detección","Fecha de corrección"] else
                    (None if c in ["Calificación","Prioridad"] else fmt_dash)
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

    # —— Estilo gris para las 6 columnas (celdas y encabezado)
    MUTED_CELL_STYLE = {"backgroundColor":"#ECEFF1","color":"#90A4AE"}
    for cc in ["Fecha Pausado","Hora Pausado","Fecha Cancelado","Hora Cancelado","Fecha Eliminado","Hora Eliminado"]:
        if cc in df_grid.columns:
            gob.configure_column(cc, headerClass="muted-col", cellStyle=MUTED_CELL_STYLE)

    # === Habilitar edición SOLO en: Tarea, Tipo, Detalle ===
    # (doble clic para entrar a editar; todo lo demás queda bloqueado)
    for c_edit, w in [("Tarea", colw.get("Tarea", 280)),
                      ("Tipo", colw.get("Tipo", 180)),
                      ("Detalle", colw.get("Detalle", 240))]:
        if c_edit in df_grid.columns:
            gob.configure_column(c_edit, editable=True, minWidth=w)

    # ==== Reglas de clase por fila (tachado/pintado) ====
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

    grid_opts = gob.build()
    grid_opts["rowClassRules"] = row_class_rules
    grid_opts["onGridReady"] = autosize_on_ready.js_code
    grid_opts["onFirstDataRendered"] = autosize_on_data.js_code
    grid_opts["onColumnEverythingChanged"] = autosize_on_data.js_code
    grid_opts["onSelectionChanged"] = sync_selection.js_code
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

    # --- Sincroniza (actualiza df_main con lo editado; solo 3 campos son editables) ---
    if isinstance(grid, dict) and "data" in grid and grid["data"] is not None:
        try:
            edited = pd.DataFrame(grid["data"]).copy()
            edited["Id"] = edited["Id"].astype(str)

            base = st.session_state["df_main"].copy()
            base["Id"] = base["Id"].astype(str)

            # Merge seguro (mantiene todo; aplica cambios que vengan del grid)
            b_i = base.set_index("Id")
            e_i = edited.set_index("Id")
            common = b_i.index.intersection(e_i.index)
            b_i.loc[common, ["Tarea", "Tipo", "Detalle"]] = e_i.loc[common, ["Tarea", "Tipo", "Detalle"]]
            st.session_state["df_main"] = b_i.reset_index()
        except Exception:
            pass

    # ---- Botones alineados EXACTAMENTE bajo "Desde | Hasta | Buscar" ----
    left_spacer = A_f + Fw_f + T_width_f  # ocupa Área + Fase + Responsable

    st.markdown('<div class="hist-actions">', unsafe_allow_html=True)
    _spacer, b_xlsx, b_save_local, b_save_sheets = st.columns([left_spacer, D_f, R_f, C_f], gap="medium")

    with b_xlsx:
        try:
            df_xlsx = st.session_state["df_main"].copy()
            # Remueve columnas internas
            drop_cols = [c for c in ("__DEL__", "DEL", "__SEL__", "¿Eliminar?") if c in df_xlsx.columns]
            if drop_cols:
                df_xlsx.drop(columns=drop_cols, inplace=True, errors="ignore")
            cols_order = globals().get("COLS_XLSX", []) or [c for c in target_cols if c not in ["__SEL__","__DEL__"]]
            cols_order = [c for c in cols_order if c in df_xlsx.columns]
            if cols_order:
                df_xlsx = df_xlsx.reindex(columns=cols_order)
            xlsx_b = export_excel(df_xlsx, sheet_name=TAB_NAME)
            st.download_button(
                "⬇️ Exportar Excel", data=xlsx_b,
                file_name="tareas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except ImportError:
            st.error("No pude generar Excel: falta instalar 'xlsxwriter' u 'openpyxl' en el entorno.")
        except Exception as e:
            st.error(f"No pude generar Excel: {e}")

    with b_save_local:
        if st.button("💾 Grabar", use_container_width=True):
            base = st.session_state["df_main"].copy()
            base["Id"] = base["Id"].astype(str)
            if "__DEL__" not in base.columns:
                base["__DEL__"] = False

            if "Estado" in base.columns:
                mask_elim = base["Estado"].astype(str).str.strip() == "Eliminado"
                base["__DEL__"] = mask_elim | base["__DEL__"].astype(bool)

                if mask_elim.any():
                    now = pd.Timestamp.now()
                    if "Fecha Eliminado" in base.columns:
                        fe = pd.to_datetime(base["Fecha Eliminado"], errors="coerce")
                        base.loc[mask_elim & fe.isna(), "Fecha Eliminado"] = now.normalize()
                    if "Hora Eliminado" in base.columns:
                        he = base["Hora Eliminado"].astype(str).str.strip()
                        base.loc[mask_elim & ((he=='')|(he=='nan')|(he=='NaN')), "Hora Eliminado"] = now.strftime("%H:%M")

            st.session_state["df_main"] = base.reset_index(drop=True)

            # Si COLS no existe, evitamos romper
            try:
                df_save = st.session_state["df_main"][COLS].copy()  # noqa: F821
            except Exception:
                df_save = st.session_state["df_main"].copy()
            try:
                _save_local(df_save.copy())  # definida fuera
            except Exception:
                pass

            n_elim = int((st.session_state["df_main"].get("__DEL__", False)==True).sum()) if "__DEL__" in st.session_state["df_main"].columns else 0
            st.success("Datos grabados en la tabla local (CSV).")
            if n_elim:
                st.info(f"Filas con Estado='Eliminado' (tachadas): {n_elim}")

    with b_save_sheets:
        if st.button("📤 Subir a Sheets", use_container_width=True):
            df = st.session_state["df_main"].copy()
            cols_order = globals().get("COLS_XLSX", []) or [c for c in target_cols if c not in ["__SEL__","__DEL__"]]
            cols_order = [c for c in cols_order if c in df.columns]
            if cols_order:
                df = df.reindex(columns=cols_order)
            try:
                _save_local(df.copy())
            except Exception:
                pass
            try:
                ok, msg = _write_sheet_tab(df.copy())  # definida fuera
                st.success(msg) if ok else st.warning(msg)
            except Exception as e:
                st.warning(f"No se pudo subir a Sheets: {e}")
