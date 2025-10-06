# ============================
# Gestión — ENI2025 (estilo Monday, secciones apiladas)
# ============================
import os
from io import BytesIO
import base64
import numpy as np
import pandas as pd
import streamlit as st

# Botón HTML (solo para el menú Exportar)
import streamlit.components.v1 as components

# Parche compatibilidad Streamlit 1.50 + st-aggrid
import streamlit.components.v1 as _stc
import types as _types
if not hasattr(_stc, "components"):
    _stc.components = _types.SimpleNamespace(MarshallComponentException=Exception)

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, DataReturnMode

st.set_page_config(page_title="Gestión — ENI2025", layout="wide", initial_sidebar_state="collapsed")

# ---------- Config ----------
AREAS = {"Planeamiento": "P", "Base de datos": "BD", "Metodología": "M", "Consistencia": "C"}

COMPLEJIDAD = PRIORIDAD = ["Alta", "Media", "Baja"]
ESTADO = ["No iniciado", "En curso", "Terminado", "Cancelado", "Pausado"]
CUMPLIMIENTO = ["Entregado a tiempo", "Entregado con retraso", "No entregado", "En riesgo de retraso"]
SI_NO = ["Sí", "No"]
EVALUACION = ["Pendiente", "Aprobada", "Desaprobada", "Observada"]

COLS = [
    "Id","Tarea","Tipo","Responsable","Fase",
    "Complejidad","Prioridad","Estado",
    "Ts_creación","Ts_en_curso","Ts_terminado","Ts_cancelado","Ts_pausado",
    "Fecha inicio","Vencimiento","Fecha fin","Duración","Días hábiles",
    "Cumplimiento","¿Generó alerta?","Tipo de alerta","¿Se corrigió?","Fecha detectada","Fecha corregida",
    "Evaluación","Calificación"
]
EMPTY_DF = pd.DataFrame(columns=COLS)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# ---------- Utils ----------
def now_ts(): return pd.Timestamp.now()

def next_id(prefix, df):
    if df.empty or "Id" not in df.columns:
        return f"{prefix}1"
    nums = []
    for x in df["Id"].astype(str):
        if x.startswith(prefix):
            try:
                nums.append(int(x.replace(prefix, "")))
            except:
                pass
    return f"{prefix}{(max(nums)+1) if nums else 1}"

def to_dt(x):
    if x is None or (isinstance(x, float) and pd.isna(x)): return None
    v = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(v) else v

def business_days(d1, d2):
    d1 = to_dt(d1); d2 = to_dt(d2)
    if d1 is None or d2 is None: return None
    s = d1.date(); e = d2.date()
    if e < s: return 0
    return int(np.busday_count(s, e + pd.Timedelta(days=1), weekmask="Mon Tue Wed Thu Fri"))

def duration_days(d1, d2):
    d1 = to_dt(d1); d2 = to_dt(d2)
    if d1 is None or d2 is None: return None
    return (d2.date() - d1.date()).days

def export_excel(df, sheet="Gestion"):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name=sheet)
    return out.getvalue()

def export_pdf_from_df(df_export, title="Reporte"):
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
        styles = getSampleStyleSheet()
        story = [Paragraph(title, styles["Title"])]
        data = [list(df_export.columns)] + df_export.astype(str).values.tolist()
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
            ("TEXTCOLOR", (0,0), (-1,0), colors.black),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 9),
            ("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.Color(0.97,0.98,0.98), colors.white]),
            ("FONTSIZE", (0,1), (-1,-1), 8),
            ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ]))
        story.append(tbl)
        doc.build(story)
        return buf.getvalue()
    except Exception:
        return None

def new_row(prefix):
    return {
        "Id": f"{prefix}1", "Tarea": "", "Tipo": "", "Responsable": "", "Fase": "",
        "Complejidad": "Media", "Prioridad": "Media", "Estado": "No iniciado",
        "Ts_creación": now_ts(), "Ts_en_curso": None, "Ts_terminado": None,
        "Ts_cancelado": None, "Ts_pausado": None,
        "Fecha inicio": None, "Vencimiento": None, "Fecha fin": None,
        "Duración": None, "Días hábiles": None,
        "Cumplimiento": "En riesgo de retraso", "¿Generó alerta?": "No",
        "Tipo de alerta": "", "¿Se corrigió?": "No",
        "Fecha detectada": None, "Fecha corregida": None,
        "Evaluación": "Pendiente", "Calificación": 0,
    }

# Guardar a CSV por área
def _save_area_df(area: str, df: pd.DataFrame):
    path = os.path.join(DATA_DIR, f"{area.replace(' ','_').lower()}.csv")
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    df_out = df[COLS].copy()
    df_out.to_csv(path, index=False, encoding="utf-8-sig", mode="w")
    st.session_state[f"last_saved_{area}"] = now_ts()
    try: st.toast(f"💾 Guardado: {area}", icon="💾")
    except: pass

def save_all_areas():
    for area in AREAS.keys():
        sk = f"df_{area}"
        if sk in st.session_state:
            _save_area_df(area, st.session_state[sk])

# ---------- Estado inicial ----------
for area, prefix in AREAS.items():
    state_key = f"df_{area}"
    if state_key not in st.session_state:
        csv_path = os.path.join(DATA_DIR, f"{area.replace(' ','_').lower()}.csv")
        if os.path.exists(csv_path):
            tmp = pd.read_csv(csv_path)
            for c in COLS:
                if c not in tmp.columns: tmp[c] = None
            for c in ["Fecha inicio", "Vencimiento", "Fecha fin"]:
                tmp[c] = pd.to_datetime(tmp[c], errors="coerce")
            st.session_state[state_key] = tmp[COLS].copy()
        else:
            rows = []
            for i in range(1, 4):
                r = new_row(prefix); r["Id"] = f"{prefix}{i}"
                rows.append(r)
            st.session_state[state_key] = pd.DataFrame(rows, columns=COLS)

# ---------- CSS ----------
st.markdown("""
<style>
.ag-theme-balham { --ag-row-height: 38px; --ag-header-height: 46px;
  --ag-background-color:#fff; --ag-header-background-color:#fff;
  --ag-row-background-color:#f7f8fa; --ag-odd-row-background-color:#f7f8fa;
  --ag-border-color:#eef1f5; }
.ag-header-cell-label { white-space: normal !important; }
.ag-body-horizontal-scroll-viewport { height: 14px !important; }
.ag-theme-balham .ag-cell{ background:var(--ag-row-background-color)!important; border-color:var(--ag-border-color)!important;
  display:block; white-space:normal!important; word-break:break-word; line-height:1.2; padding-top:6px; padding-bottom:6px; }
.ag-theme-balham .ag-row { border-bottom: 1px solid var(--ag-border-color)!important; }
.ag-theme-balham .ag-header,.ag-theme-balham .ag-header-row,.ag-theme-balham .ag-header-cell{
  background:var(--ag-header-background-color)!important; border-bottom:1px solid var(--ag-border-color)!important; }
.ag-theme-balham .ag-row-hover .ag-cell { background:#f2f6ff!important; }
.ag-theme-balham .ag-row-selected .ag-cell { background:#e8f0ff!important; }

.section-card{ border:1px solid #e9ecef; border-radius:16px; padding:18px; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.04); margin-bottom:18px; }
.section-title{ font-weight:800; font-size:1.6rem; line-height:1.1; margin:0; }

.infobar{ background:#f7fbff; border:1px solid #e3f0ff; border-radius:10px; padding:12px 14px; display:flex; align-items:center; justify-content:space-between; gap:12px; }
.infobar .left{ color:#0f2748; font-size:.95rem; }
.infobar kbd{background:#eef6ff;border:1px solid #d7e8ff;border-bottom-width:2px;border-radius:6px;padding:2px 6px;font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,"Liberation Mono","Courier New",monospace}

.btn{ padding:8px 14px; border:1px solid #e8e9ec; border-radius:10px; background:#fff; font-weight:600; color:#1f2937; text-decoration:none; display:inline-flex; align-items:center; cursor:pointer; }
.btn:hover{ background:#f7f8fa; }

.drop{ position:relative; display:inline-block; }
.drop>summary{ list-style:none; cursor:pointer; }
.drop>summary::-webkit-details-marker{ display:none; }
.drop .menu{ position:absolute; right:0; top:110%; background:#fff; border:1px solid #e8e9ec; border-radius:12px;
  padding:10px; box-shadow:0 12px 28px rgba(0,0,0,.12); display:grid; gap:10px; min-width:230px; z-index:10; }
.dl-btn{ display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:10px; border:1px solid #e8e9ec; text-decoration:none!important; color:#1f2937; font-weight:600; }
.dl-btn:hover{ background:#f7f8fa; }
.dl-btn .ico{ width:22px; height:22px; display:inline-block; background-size:cover; background-position:center; }

.ico-excel{ background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='%2300a651' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><polyline points='14 2 14 8 20 8'/><path d='M9 17l3-5 3 5'/><path d='M9 12l3 5 3-5'/></svg>"); }
.ico-csv{ background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='%230084ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><polyline points='14 2 14 8 20 8'/><text x='7' y='17' font-size='8' fill='%230084ff' font-family='monospace'>CSV</text></svg>"); }
.ico-pdf{ background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='%23e53935' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><polyline points='14 2 14 8 20 8'/><text x='7' y='17' font-size='8' fill='%23e53935' font-family='monospace'>PDF</text></svg>"); }
</style>
""", unsafe_allow_html=True)

# ---------- Título ----------
st.title("📁 Gestión (ENI2025)")

# ============== FUNCIÓN RENDER (con FORM para guardado fiable) ==============
def render_area_block(area: str):
    prefix = AREAS[area]
    sk = f"df_{area}"

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown(f"<div class='section-title'>{area}</div>", unsafe_allow_html=True)

    # ------------- FORM: garantiza que el botón Guardar confirme la edición -------------
    with st.form(f"form_{area}", clear_on_submit=False):

        # --------- DF base para grid (lo que se ve en pantalla) ---------
        df = st.session_state[sk].copy()
        for c in COLS:
            if c not in df.columns:
                df[c] = None
        df = df[COLS]
        for c in ["Fecha inicio", "Vencimiento", "Fecha fin"]:
            df[c] = pd.to_datetime(df[c], errors="coerce")

        # ====== hotkeys dentro del grid ======
        grid_hotkeys_js = JsCode(f"""
        function(e){{
          const api = e.api, evt = e.event; if (!evt) return;
          function nextId(prefix){{ let max=0; api.forEachNode(n=>{{ const v=String((n.data&&n.data['Id'])||''); if(v.startsWith(prefix)){{ const num=parseInt(v.replace(prefix,''))||0; if(num>max) max=num; }} }}); return prefix + (max + 1); }}
          if (evt.key==='Enter' && evt.shiftKey) {{
            evt.preventDefault(); evt.stopPropagation();
            const defs=e.columnApi.getAllGridColumns().map(c=>c.getColDef().field);
            const row={{}}; defs.forEach(f=>row[f]=null);
            row['Id']=nextId('{prefix}'); row['Ts_creación']=new Date().toISOString();
            api.applyTransaction({{ add:[row] }});
          }}
          if (evt.key==='Delete') {{
            const sel=api.getSelectedRows(); if(sel&&sel.length){{ evt.preventDefault(); evt.stopPropagation(); api.applyTransaction({{ remove: sel }}); }}
          }}
        }}
        """)
        suppress_kbd = JsCode("function(params){ const e=params.event; if(!e) return false; return false; }")

        # ------------ CONFIG GRID ------------
        gob = GridOptionsBuilder.from_dataframe(df)
        gob.configure_grid_options(
            rowSelection="multiple",
            suppressRowClickSelection=True,
            domLayout="normal",
            rowHeight=38, headerHeight=46,
            wrapHeaderText=True, autoHeaderHeight=True,
            suppressSizeToFit=False, alwaysShowHorizontalScroll=False,
            enableRangeSelection=True, enableCellTextSelection=True,
            singleClickEdit=True, stopEditingWhenCellsLoseFocus=True,
            undoRedoCellEditing=True, enterMovesDown=True,
            onCellKeyDown=grid_hotkeys_js, suppressKeyboardEvent=suppress_kbd,
        )
        gob.configure_selection("multiple", use_checkbox=True)
        gob.configure_column(
            "Id", editable=False, width=110, minWidth=110, pinned="left",
            checkboxSelection=True, headerCheckboxSelection=True
        )

        colw = {
            "Tarea": 180, "Tipo": 140, "Responsable": 140, "Fase": 130,
            "Complejidad": 130, "Prioridad": 130, "Estado": 130,
            "Fecha inicio": 150, "Vencimiento": 150, "Fecha fin": 150,
            "Duración": 100, "Días hábiles": 110,
            "Cumplimiento": 160, "¿Generó alerta?": 130, "Tipo de alerta": 160,
            "¿Se corrigió?": 130, "Evaluación": 130, "Calificación": 120
        }

        # “Banderitas” con emojis en Complejidad / Prioridad
        flag_formatter = JsCode("""
        function(p){
          const v = String(p.value || '');
          if (v === 'Alta')  return '🔴 Alta';
          if (v === 'Media') return '🟡 Media';
          if (v === 'Baja')  return '🟢 Baja';
          return v || '—';
        }""")
        white_style = JsCode("function(){return {background:'#fff',textAlign:'left'};}")

        # Texto libre
        for c, fx in [("Tarea", 3), ("Tipo", 2), ("Tipo de alerta", 2), ("Responsable", 2), ("Fase", 1)]:
            gob.configure_column(c, editable=True, minWidth=colw[c], flex=fx, wrapText=True, autoHeight=True)

        # Selects con “banderas”
        for c in ["Complejidad", "Prioridad"]:
            gob.configure_column(
                c, editable=True, cellEditor="agSelectCellEditor",
                cellEditorParams={"values": ["Alta", "Media", "Baja"]},
                valueFormatter=flag_formatter, cellStyle=white_style,
                minWidth=colw[c], maxWidth=200, flex=1
            )

        # Chips rectangulares
        chip_style = JsCode("""
        function(p){
          const v = String(p.value || '');
          let bg = '#E0E0E0', fg = '#FFFFFF';
          if (v === 'No iniciado') { bg = '#90A4AE'; }
          else if (v === 'En curso') { bg = '#B388FF'; }
          else if (v === 'Terminado') { bg = '#FF6EC7'; }
          else if (v === 'Cancelado') { bg = '#FF2D95'; }
          else if (v === 'Pausado') { bg = '#7E57C2'; }
          else if (v === 'Entregado a tiempo') { bg = '#00C4B3'; }
          else if (v === 'Entregado con retraso') { bg = '#00ACC1'; }
          else if (v === 'No entregado') { bg = '#006064'; }
          else if (v === 'En riesgo de retraso') { bg = '#0277BD'; }
          else if (v === 'Pendiente') { bg = '#F6C90E'; fg = '#3D2C00'; }
          else if (v === 'Aprobada') { bg = '#FFA000'; }
          else if (v === 'Desaprobada') { bg = '#FF5C8A'; }
          else if (v === 'Observada') { bg = '#8D6E63'; }
          else if (v === 'Sí') { bg = '#FF8A80'; }
          else if (v === 'No') { bg = '#B0BEC5'; }
          return { backgroundColor:bg, color:fg, fontWeight:'600', textAlign:'center',
                   borderRadius:'6px', padding:'4px 10px' };
        }""")

        fmt_dash = JsCode("""
        function(p){ if(p.value===null||p.value===undefined) return '—';
          const s=String(p.value).trim().toLowerCase();
          if (s===''||s==='nan'||s==='nat'||s==='none'||s==='null') return '—';
          return String(p.value);
        }""")

        for c, vals in [
            ("Estado", ESTADO),
            ("Cumplimiento", CUMPLIMIENTO),
            ("¿Generó alerta?", SI_NO),
            ("¿Se corrigió?", SI_NO),
            ("Evaluación", EVALUACION),
        ]:
            gob.configure_column(
                c, editable=True, cellEditor="agSelectCellEditor",
                cellEditorParams={"values": vals},
                cellStyle=chip_style, valueFormatter=fmt_dash,
                minWidth=colw.get(c, 120), maxWidth=220, flex=1,
                wrapText=True, autoHeight=True
            )

        for c in ["Ts_creación", "Ts_en_curso", "Ts_terminado", "Ts_cancelado", "Ts_pausado", "Fecha detectada", "Fecha corregida"]:
            gob.configure_column(c, hide=True)

        # Fechas
        date_time_editor = JsCode("""
        class DateTimeEditor{
          init(p){ this.eInput=document.createElement('input'); this.eInput.type='datetime-local';
            this.eInput.classList.add('ag-input'); this.eInput.style.width='100%';
            const v=p.value?new Date(p.value):null;
            if(v&&!isNaN(v.getTime())){ const pad=n=>String(n).padStart(2,'0');
              this.eInput.value = v.getFullYear()+'-'+pad(v.getMonth()+1)+'-'+pad(v.getDate())+'T'+pad(v.getHours())+':'+pad(v.getMinutes()); }
          }
          getGui(){return this.eInput} afterGuiAttached(){this.eInput.focus()} getValue(){return this.eInput.value}
        }""")
        date_time_fmt = JsCode("""
        function(p){ if(p.value===null||p.value===undefined) return '—';
          const d=new Date(String(p.value).trim()); if(isNaN(d.getTime())) return '—';
          const pad=n=>String(n).padStart(2,'0');
          return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes());
        }""")
        for c in ["Fecha inicio", "Vencimiento", "Fecha fin"]:
            gob.configure_column(
                c, editable=True, cellEditor=date_time_editor,
                valueFormatter=date_time_fmt, minWidth=colw[c],
                maxWidth=180, flex=1, wrapText=True, autoHeight=True
            )

        dur_getter = JsCode("function(p){const s=p.data['Fecha inicio'],e=p.data['Vencimiento'];if(!s||!e)return null;const sd=new Date(s),ed=new Date(e);if(isNaN(sd.getTime())||isNaN(ed.getTime()))return null;return Math.floor((ed-sd)/(1000*60*60*24));}")
        bd_getter  = JsCode("function(p){const s=p.data['Fecha inicio'],e=p.data['Vencimiento'];if(!s||!e)return null;let sd=new Date(s),ed=new Date(e);if(isNaN(sd.getTime())||isNaN(ed.getTime()))return null;if(ed<sd)return 0;sd=new Date(sd.getFullYear(),sd.getMonth(),sd.getDate());ed=new Date(ed.getFullYear(),ed.getMonth(),ed.getDate());let c=0;const one=24*60*60*1000;for(let t=sd.getTime();t<=ed.getTime();t+=one){const d=new Date(t).getDay();if(d!==0&&d!==6)c++;}return c;}")

        gob.configure_column("Duración", editable=False, valueGetter=dur_getter,
                             valueFormatter=fmt_dash, minWidth=colw["Duración"], maxWidth=120, flex=0)
        gob.configure_column("Días hábiles", editable=False, valueGetter=bd_getter,
                             valueFormatter=fmt_dash, minWidth=colw["Días hábiles"], maxWidth=130, flex=0)
        gob.configure_column("Calificación", editable=True, cellEditor="agSelectCellEditor",
                             cellEditorParams={"values":[0,1,2,3,4,5]},
                             valueFormatter=JsCode("function(p){const n=Math.max(0,Math.min(5,Number(p.value||0)));return '★'.repeat(n)+'☆'.repeat(5-n);}"),
                             cellStyle=JsCode("function(){return {color:'#f2c200',fontWeight:'700',fontSize:'22px',letterSpacing:'2px',textAlign:'center'};}"),
                             minWidth=170, maxWidth=220, flex=0)

        grid = AgGrid(
            df,
            key=f"grid_{area}",
            gridOptions=gob.build(),
            height=450,
            fit_columns_on_grid_load=True,
            data_return_mode=DataReturnMode.AS_INPUT,
            update_mode=(GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED),
            allow_unsafe_jscode=True,
            theme="balham",
        )

        # Exportar: SIEMPRE desde el último estado guardado (no desde edición en curso)
        df_export = st.session_state[sk].copy()
        xlsx_b = export_excel(df_export, sheet=area.replace(" ", "_"))
        csv_b  = df_export.to_csv(index=False).encode("utf-8-sig")
        pdf_b  = export_pdf_from_df(df_export, title=f"Gestión ENI2025 — {area}")
        xlsx64 = base64.b64encode(xlsx_b).decode("utf-8")
        csv64  = base64.b64encode(csv_b).decode("utf-8")
        pdf64  = base64.b64encode(pdf_b).decode("utf-8") if pdf_b else None
        fname  = f"gestion_{area.replace(' ', '_').lower()}"
        excel_item = f"<a class='dl-btn' href='data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{xlsx64}' download='{fname}.xlsx'><span class='ico ico-excel'></span> Excel</a>"
        csv_item   = f"<a class='dl-btn' href='data:text/csv;base64,{csv64}' download='{fname}.csv'><span class='ico ico-csv'></span> CSV</a>"
        pdf_item   = (f"<a class='dl-btn' href='data:application/pdf;base64,{pdf64}' download='{fname}.pdf'><span class='ico ico-pdf'></span> PDF</a>"
                      if pdf64 else "<div class='dl-btn' style='opacity:.5;cursor:not-allowed'><span class='ico ico-pdf'></span> PDF (instala reportlab)</div>")
        dropdown_html = f"<details class='drop'><summary class='btn'>📤 Exportar ▾</summary><div class='menu'>{excel_item}{csv_item}{pdf_item}</div></details>"

        left_col, right_col = st.columns([0.62, 0.38])
        with left_col:
            st.markdown(
                "<div class='infobar'><div class='left'>Selecciona filas con el checkbox de la <b>1ª columna</b>. "
                "<kbd>Shift</kbd>+<kbd>Enter</kbd> nueva tarea · <kbd>Supr</kbd> eliminar</div></div>",
                unsafe_allow_html=True
            )
        with right_col:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown(dropdown_html, unsafe_allow_html=True)
            with c2:
                submitted = st.form_submit_button("💾 Guardar cambios")

    # -------------------- POST FORM: normalización y guardado (SIN AUTOGUARDADO) --------------------
    grid_resp = grid if isinstance(grid, dict) else {}
    base_state_df = st.session_state[sk].copy()
    new_df = pd.DataFrame(grid_resp.get("data", base_state_df))
    for c in ["Fecha inicio", "Vencimiento", "Fecha fin"]:
        new_df[c] = pd.to_datetime(new_df[c], errors="coerce")

    # Cálculos
    new_df["Duración"]     = new_df.apply(lambda r: duration_days(r["Fecha inicio"], r["Vencimiento"]), axis=1)
    new_df["Días hábiles"] = new_df.apply(lambda r: business_days(r["Fecha inicio"], r["Vencimiento"]), axis=1)

    # IDs faltantes
    if "Id" in new_df.columns:
        pref = AREAS[area]
        mask = new_df["Id"].astype(str).str.strip().isin(["", "nan", "None"])
        while mask.any():
            nxt = next_id(pref, new_df)
            idx = mask.idxmax()
            new_df.at[idx, "Id"] = nxt
            mask = new_df["Id"].astype(str).str.strip().isin(["", "nan", "None"])

    # Guardado explícito con el botón del form (única vía de guardado)
    if submitted:
        st.session_state[sk] = new_df.copy()
        _save_area_df(area, st.session_state[sk])
        st.toast(f"✅ Guardado: {area}", icon="✅")
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# Render de todas las áreas
for area in ["Planeamiento", "Base de datos", "Metodología", "Consistencia"]:
    render_area_block(area)
