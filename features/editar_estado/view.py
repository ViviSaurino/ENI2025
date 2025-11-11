# features/editar_estado/view.py
from __future__ import annotations
import os
import re
import pandas as pd
import streamlit as st
from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    DataReturnMode,
    JsCode,
)

# Hora Lima para sellado de cambios + ACL
try:
    from shared import now_lima_trimmed, apply_scope
except Exception:
    from datetime import datetime, timedelta
    # Fallback robusto: siempre hora Lima (UTC-5)
    def now_lima_trimmed():
        return (datetime.utcnow() - timedelta(hours=5)).replace(second=0, microsecond=0)
    # Fallback por si no carga shared (no filtra)
    def apply_scope(df, user=None, resp_col="Responsable"):
        return df

# ========= Utilidades mínimas para zonas horarias =========
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None

def _now_lima_trimmed_local():
    """Devuelve datetime (Lima) sin segundos/microsegundos."""
    from datetime import datetime, timedelta
    try:
        if _TZ:
            return datetime.now(_TZ).replace(second=0, microsecond=0)
        return (datetime.utcnow() - timedelta(hours=5)).replace(second=0, microsecond=0)
    except Exception:
        return now_lima_trimmed()

def _to_naive_local_one(x):
    """Convierte x a datetime naive en hora local; tolera strings/ tz."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return pd.NaT
    try:
        if isinstance(x, pd.Timestamp):
            if x.tz is not None:
                d = x.tz_convert(_TZ or x.tz).tz_localize(None) if _TZ else x.tz_localize(None)
                return d
            return x
        s = str(x).strip()
        if not s or s.lower() in {"nan", "nat", "none", "null"}:
            return pd.NaT
        if re.search(r'(Z|[+-]\d{2}:?\d{2})$', s):
            d = pd.to_datetime(s, errors="coerce", utc=True)
            if pd.isna(d):
                return pd.NaT
            if _TZ:
                d = d.tz_convert(_TZ)
            return d.tz_localize(None)
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT

def _fmt_hhmm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        s = str(v).strip()
        if not s or s.lower() in {"nan", "nat", "none", "null"}:
            return ""
        m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", s)
        if m:
            return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        d = pd.to_datetime(s, errors="coerce", utc=False)
        if pd.isna(d):
            return ""
        return f"{int(d.hour):02d}:{int(d.minute):02d}"
    except Exception:
        return ""

# ============== Helpers ACL (super editores y nombre visible) ==============
def _display_name() -> str:
    u = st.session_state.get("acl_user", {}) or {}
    return (
        u.get("display")
        or st.session_state.get("user_display_name", "")
        or u.get("name", "")
        or (st.session_state.get("user") or {}).get("name", "")
        or ""
    )

def _is_super_editor() -> bool:
    u = st.session_state.get("acl_user", {}) or {}
    flag = str(u.get("can_edit_all", "")).strip().lower()
    if flag in {"1", "true", "yes", "si", "sí"}:
        return True
    dn = _display_name().strip().lower()
    return dn.startswith("vivi") or dn.startswith("enrique")

# --- Cliente GSheets y upsert por Id ---
def _gsheets_client():
    if "gcp_service_account" not in st.secrets:
        raise KeyError("Falta 'gcp_service_account' en secrets.")
    url = (
        st.secrets.get("gsheets_doc_url")
        or (st.secrets.get("gsheets", {}) or {}).get("spreadsheet_url")
        or (st.secrets.get("sheets", {}) or {}).get("sheet_url")
    )
    if not url:
        raise KeyError("No se encontró URL de Sheets.")
    ws_name = (st.secrets.get("gsheets", {}) or {}).get("worksheet", "TareasRecientes")

    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(url)
    try:
        ws = ss.worksheet(ws_name)
    except Exception:
        ws = None
    return ss, ws, ws_name

def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def _sheet_upsert_estado_by_id(df_base: pd.DataFrame, changed_ids: list[str]):
    """Actualiza en Sheets por 'Id' estado/sellos y **Link de archivo** (si la hoja tiene esa columna)."""
    try:
        ss, ws, ws_name = _gsheets_client()
    except Exception as e:
        st.info(f"Sheets no configurado: {e}")
        return

    if ws is None:
        rows = str(max(1000, len(df_base) + 10))
        cols = str(max(26, len(df_base.columns) + 5))
        ws = ss.add_worksheet(title=ws_name, rows=rows, cols=cols)
        ws.update("A1", [list(df_base.columns)])

    values = ws.get_all_values() or []
    if not values:
        ws.update("A1", [list(df_base.columns)])
        values = ws.get_all_values()

    headers = values[0]
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    if "Id" not in col_map:
        st.info("La hoja seleccionada no tiene columna 'Id'; no se puede actualizar por Id.")
        return

    id_idx = col_map["Id"] - 1
    id_to_row = {}
    for r_i, row in enumerate(values[1:], start=2):
        if id_idx < len(row):
            id_to_row[str(row[id_idx]).strip()] = r_i

    base_push_cols = [
        "Estado", "Estado actual",
        "Fecha estado actual", "Hora estado actual",
        "Fecha inicio", "Hora de inicio",
        "Fecha Terminado", "Hora Terminado",
        "Link de archivo",
    ]
    cols_to_push = [c for c in base_push_cols if c in col_map]

    def _fmt_out(col, val):
        low = str(col).lower()
        if low.startswith("fecha"):
            d = _to_naive_local_one(val)
            return "" if pd.isna(d) else d.strftime("%Y-%m-%d")
        if low.startswith("hora"):
            return _fmt_hhmm(val)
        return "" if (val is None or (isinstance(val, float) and pd.isna(val))) else str(val)

    last_col_letter = _col_letter(len(headers))
    body, ranges = [], []

    # Evitar duplicados en df_base para el upsert
    if "Id" in df_base.columns:
        df_base = df_base.drop_duplicates(subset=["Id"], keep="last").copy()

    df_idx = df_base.set_index("Id")

    def _get_val(_id, h):
        if h in df_idx.columns:
            return df_idx.loc[_id, h]
        if h == "Estado actual" and "Estado" in df_idx.columns:
            return df_idx.loc[_id, "Estado"]
        return ""

    for _id in changed_ids:
        if _id not in df_idx.index:
            continue
        row_idx = id_to_row.get(str(_id))
        if not row_idx:
            new_row = []
            for h in headers:
                v = _get_val(_id, h)
                new_row.append(_fmt_out(h, v))
            values.append(new_row)
            ws.append_row(new_row, value_input_option="USER_ENTERED")
            continue

        current_row = values[row_idx - 1].copy()
        if len(current_row) < len(headers):
            current_row += [""] * (len(headers) - len(current_row))

        for h in cols_to_push:
            v = _get_val(_id, h)
            current_row[col_map[h] - 1] = _fmt_out(h, v)

        ranges.append(f"A{row_idx}:{last_col_letter}{row_idx}")
        body.append(current_row[: len(headers)])

    if body and ranges:
        data = [{"range": rng, "values": [vals]} for rng, vals in zip(ranges, body)]
        ws.batch_update({"valueInputOption": "USER_ENTERED", "data": data})

# ===============================================================================

def render(user: dict | None = None):
    # ================== EDITAR ESTADO ==================
    st.session_state.setdefault("est_visible", True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.session_state["est_visible"]:
        A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

        st.markdown('<div id="est-section">', unsafe_allow_html=True)
        st.markdown(
            """
        <style>
          #est-section .stButton > button { width: 100% !important; }
          #est-section .ag-header-cell-label{
            font-weight: 400 !important;
            white-space: normal !important;
            line-height: 1.15 !important;
          }
          #est-section .ag-body-horizontal-scroll,
          #est-section .ag-center-cols-viewport { overflow-x: hidden !important; }
          .section-est .help-strip + .form-card{ margin-top: 6px !important; }
          .est-pill{
            width:100%; height:38px; border-radius:12px;
            display:flex; align-items:center; justify-content:center;
            background:#A7C8F0; color:#ffffff; font-weight:700;
            box-shadow:0 6px 14px rgba(167,200,240,.35);
            user-select:none;
            margin: 4px 0 16px;
          }
          .est-pill span{ display:inline-flex; gap:8px; align-items:center; }
        </style>
        """,
            unsafe_allow_html=True,
        )

        c_pill, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with c_pill:
            st.markdown('<div class="est-pill"><span>✏️&nbsp;Editar estado</span></div>', unsafe_allow_html=True)

        st.markdown(
            """
        <div class="section-est">
          <div class="help-strip">
            🔷 <strong>Actualiza el estado</strong> de una tarea ya registrada usando los filtros
          </div>
          <div class="form-card">
        """,
            unsafe_allow_html=True,
        )

        # Base global
        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()

        # 🔐 ACL: primero apply_scope; en Editar estado, si NO eres super → ver solo tus tareas
        df_all = apply_scope(df_all, user=user)
        me = _display_name().strip()
        is_super = _is_super_editor()
        if not is_super and isinstance(df_all, pd.DataFrame) and "Responsable" in df_all.columns and me:
            try:
                mask = df_all["Responsable"].astype(str).str.contains(me, case=False, na=False)
                df_all = df_all[mask]
            except Exception:
                pass

        # ===== Rango por defecto (min–max del dataset) =====
        def _first_valid_date_series(df: pd.DataFrame) -> pd.Series:
            if df.empty:
                return pd.Series([], dtype="datetime64[ns]")
            pri = [
                "Fecha inicio","Fecha Registro","Fecha","Fecha Terminado"
            ]
            s_list = []
            for c in pri:
                if c in df.columns:
                    s_list.append(pd.to_datetime(df[c], errors="coerce"))
            if not s_list:
                return pd.Series([], dtype="datetime64[ns]")
            all_dates = pd.concat(s_list, ignore_index=True)
            return all_dates[all_dates.notna()]

        dates_all = _first_valid_date_series(df_all)
        if dates_all.empty:
            today = pd.Timestamp.today().normalize().date()
            min_date = today
            max_date = today
        else:
            min_date = dates_all.min().date()
            max_date = dates_all.max().date()

        # ===== FILTROS =====
        with st.form("est_filtros_v4", clear_on_submit=False):
            c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns(
                [A, Fw, T_width, D, R, C], gap="medium"
            )

            AREAS_OPC = (
                st.session_state.get(
                    "AREAS_OPC",
                    sorted(
                        [
                            x
                            for x in df_all.get("Área", pd.Series([], dtype=str))
                            .astype(str).unique()
                            if x and x != "nan"
                        ]
                    ),
                )
                or []
            )
            est_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0)

            fases_all = sorted(
                [
                    x
                    for x in df_all.get("Fase", pd.Series([], dtype=str))
                    .astype(str).unique()
                    if x and x != "nan"
                ]
            )
            est_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

            df_resp_src = df_all.copy()
            if est_area != "Todas" and "Área" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Área"].astype(str) == est_area]
            if est_fase != "Todas" and "Fase" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == est_fase]
            responsables_all = sorted(
                [
                    x
                    for x in df_resp_src.get("Responsable", pd.Series([], dtype=str))
                    .astype(str).unique()
                    if x and x != "nan"
                ]
            )
            est_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0)

            est_desde = c_desde.date_input(
                "Desde", value=min_date, min_value=min_date, max_value=max_date, key="est_desde"
            )
            est_hasta = c_hasta.date_input(
                "Hasta", value=max_date, min_value=min_date, max_value=max_date, key="est_hasta"
            )

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
                est_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

        # ===== Filtrado de tareas =====
        df_tasks = df_all.copy()
        if est_do_buscar:
            if est_area != "Todas" and "Área" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Área"].astype(str) == est_area]
            if est_fase != "Todas" and "Fase" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Fase"].astype(str) == est_fase]
            if est_resp != "Todos" and "Responsable" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Responsable"].astype(str) == est_resp]

            # rango: prioriza inicio/registro
            fcol = pd.to_datetime(df_tasks.get("Fecha inicio", pd.Series([], dtype=object)), errors="coerce")
            if fcol.isna().all():
                fcol = pd.to_datetime(df_tasks.get("Fecha Registro", pd.Series([], dtype=object)), errors="coerce")
            if est_desde:
                df_tasks = df_tasks[fcol >= pd.to_datetime(est_desde)]
            if est_hasta:
                df_tasks = df_tasks[fcol <= (pd.to_datetime(est_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

        # ===== Tabla "Resultados" =====
        st.markdown("**Resultados**")

        def _fmt_date_series(s: pd.Series) -> pd.Series:
            s = pd.to_datetime(s, errors="coerce")
            out = s.dt.strftime("%Y-%m-%d")
            return out.fillna("-")

        def _fmt_time_series(s: pd.Series) -> pd.Series:
            def _one(x):
                x = "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()
                if not x or x.lower() in {"nan", "nat", "none", "null", "-"}:
                    return "-"
                m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", x)
                if m:
                    return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
                try:
                    d = pd.to_datetime(x, errors="coerce")
                    if pd.isna(d):
                        return "-"
                    return f"{int(d.hour):02d}:{int(d.minute):02d}"
                except Exception:
                    return "-"
            return s.astype(str).map(_one)

        cols_out = [
            "Id",
            "Tarea",
            "Estado actual",
            "Fecha de registro",
            "Hora de registro",
            "Fecha inicio",
            "Hora de inicio",
            "Fecha terminada",
            "Hora terminada",
            "Link de archivo",
        ]

        df_view = pd.DataFrame(columns=cols_out)
        if not df_tasks.empty:
            base = df_tasks.copy()

            # columnas mínimas
            for need in [
                "Id", "Tarea", "Estado",
                "Fecha Registro", "Hora Registro",
                "Fecha inicio","Hora de inicio",
                "Fecha Terminado","Hora Terminado",
                "Link de archivo",
            ]:
                if need not in base.columns:
                    base[need] = ""

            # Estado automático para vista
            fr = pd.to_datetime(base["Fecha Registro"], errors="coerce")
            hr = base["Hora Registro"].astype(str)
            fi = pd.to_datetime(base["Fecha inicio"], errors="coerce")
            hi = base["Hora de inicio"].astype(str)
            ft = pd.to_datetime(base["Fecha Terminado"], errors="coerce")
            ht = base["Hora Terminado"].astype(str)

            est_now = pd.Series("No iniciado", index=base.index, dtype="object")
            est_now = est_now.mask(fi.notna() & ft.isna(), "En curso")
            est_now = est_now.mask(ft.notna(), "Terminado")

            link_col = base["Link de archivo"].astype(str).replace(
                {"nan": "-", "NaN": "-", "None": "-", "": "-"}
            )

            df_view = pd.DataFrame(
                {
                    "Id": base["Id"].astype(str),
                    "Tarea": base["Tarea"].astype(str).replace({"nan": "-", "NaN": "-", "": "-"}),
                    "Estado actual": est_now,
                    "Fecha de registro": _fmt_date_series(fr),
                    "Hora de registro": _fmt_time_series(hr),
                    "Fecha inicio": _fmt_date_series(fi),
                    "Hora de inicio": _fmt_time_series(hi),
                    "Fecha terminada": _fmt_date_series(ft),
                    "Hora terminada": _fmt_time_series(ht),
                    "Link de archivo": link_col,
                }
            )[cols_out].copy()

        # ========= editores y estilo =========
        estado_emoji_fmt = JsCode(
            """
        function(p){
          const v = String(p.value || '');
          const M = {
            "No iniciado":"🍼 No iniciado",
            "En curso":"🟣 En curso",
            "Terminado":"✅ Terminado"
          };
          return M[v] || v;
        }"""
        )

        estado_cell_style = JsCode(
            """
        function(p){
          const v = String(p.value || '');
          const S = {
            "No iniciado":{bg:"#E3F2FD", fg:"#0D47A1"},
            "En curso":   {bg:"#EDE7F6", fg:"#4A148C"},
            "Terminado":  {bg:"#E8F5E9", fg:"#1B5E20"},
          };
          const m = S[v]; if(!m) return {};
          return {backgroundColor:m.bg, color:m.fg, fontWeight:'600', textAlign:'center', borderRadius:'12px'};
        }"""
        )

        # Editor de fecha (calendar)
        date_editor = JsCode(
            """
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
        }"""
        )

        # Mostrar "-" en link vacío (pero permitimos editar texto)
        link_formatter = JsCode(
            """function(p){ const s=String(p.value||'').trim(); return s? s : '-'; }"""
        )

        # Al cambiar fecha → poner hora Lima y estado actual
        on_cell_changed = JsCode(
            f"""
        function(params){{
          const field = params.colDef.field;
          const pad = n => String(n).padStart(2,'0');
          const now = new Date();
          const utcMs = now.getTime() + now.getTimezoneOffset()*60000;
          const lima = new Date(utcMs - 5*60*60000);
          const hhmm = pad(lima.getHours()) + ':' + pad(lima.getMinutes());
          if (field === 'Fecha inicio') {{
            params.node.setDataValue('Hora de inicio', hhmm);
            params.node.setDataValue('Estado actual', 'En curso');
          }}
          if (field === 'Fecha terminada') {{
            params.node.setDataValue('Hora terminada', hhmm);
            params.node.setDataValue('Estado actual', 'Terminado');
          }}
        }}"""
        )

        # Editable condicional por rol y huella
        editable_start = JsCode(
            f"""
        function(p){{
          const SUPER = {str(is_super).lower()};
          if(SUPER) return true;
          const v = String(p.value||'').trim();
          return v === '-' || v === '';
        }}"""
        )
        editable_end = JsCode(
            f"""
        function(p){{
          const SUPER = {str(is_super).lower()};
          if(SUPER) return true;
          const v = String(p.value||'').trim();
          const hasStart = String(p.data['Fecha inicio']||'').trim() !== '' && String(p.data['Fecha inicio']||'').trim() !== '-';
          return (v === '' || v === '-') && hasStart;
        }}"""
        )

        gob = GridOptionsBuilder.from_dataframe(df_view)
        gob.configure_grid_options(
            suppressMovableColumns=True,
            domLayout="normal",
            ensureDomOrder=True,
            rowHeight=38,
            headerHeight=60,
            suppressHorizontalScroll=True,
        )
        gob.configure_default_column(wrapHeaderText=True, autoHeaderHeight=True)
        gob.configure_selection("single", use_checkbox=False)

        gob.configure_column("Estado actual", valueFormatter=estado_emoji_fmt, cellStyle=estado_cell_style, minWidth=170, editable=False)
        gob.configure_column("Fecha de registro", editable=False, minWidth=150)
        gob.configure_column("Hora de registro", editable=False, minWidth=140)
        gob.configure_column("Tarea", editable=False, minWidth=260)
        gob.configure_column("Id", editable=False, minWidth=110)

        gob.configure_column("Fecha inicio", editable=editable_start, cellEditor=date_editor, minWidth=160)
        gob.configure_column("Hora de inicio", editable=False, minWidth=140)
        gob.configure_column("Fecha terminada", editable=editable_end, cellEditor=date_editor, minWidth=170)
        gob.configure_column("Hora terminada", editable=False, minWidth=150)
        gob.configure_column("Link de archivo", editable=True, minWidth=260, valueFormatter=link_formatter)

        grid_opts = gob.build()
        grid_opts["onCellValueChanged"] = on_cell_changed.js_code

        grid = AgGrid(
            df_view,
            gridOptions=grid_opts,
            data_return_mode=DataReturnMode.AS_INPUT,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            fit_columns_on_grid_load=True,
            enable_enterprise_modules=False,
            reload_data=False,
            height=300,
            allow_unsafe_jscode=True,
            theme="balham",
        )

        # ===== Guardar cambios =====
        _, u2 = st.columns([A + Fw + T_width + D + R, C], gap="medium")
        with u2:
            if st.button("💾 Guardar", use_container_width=True, key="est_guardar_inline_v4"):
                try:
                    grid_data = pd.DataFrame(grid.get("data", []))
                    if grid_data.empty or "Id" not in grid_data.columns:
                        st.info("No hay cambios para guardar.")
                    else:
                        grid_data["Id"] = grid_data["Id"].astype(str)
                        g_i = grid_data.set_index("Id")

                        def norm(s: pd.Series) -> pd.Series:
                            s = s.fillna("").astype(str).str.strip()
                            # map "-" visual a vacío real
                            return s.replace(to_replace=r"^\-$", value="", regex=True)

                        fi_new = norm(g_i.get("Fecha inicio", pd.Series(index=g_i.index)))
                        hi_new = norm(g_i.get("Hora de inicio", pd.Series(index=g_i.index)))
                        ft_new = norm(g_i.get("Fecha terminada", pd.Series(index=g_i.index)))
                        ht_new = norm(g_i.get("Hora terminada", pd.Series(index=g_i.index)))
                        lk_new = norm(g_i.get("Link de archivo", pd.Series(index=g_i.index)))

                        ids_view = list(g_i.index)

                        full_before = st.session_state.get("df_main", pd.DataFrame()).copy()
                        if full_before.empty or "Id" not in full_before.columns:
                            st.warning("No hay base para actualizar.")
                            return
                        full_before["Id"] = full_before["Id"].astype(str)

                        # Subconjunto editable (si no eres súper)
                        base = full_before.copy()
                        me = _display_name().strip()
                        is_super = _is_super_editor()
                        if not is_super and "Responsable" in base.columns and me:
                            mask_me = base["Responsable"].astype(str).str.contains(me, case=False, na=False)
                            base = base[mask_me]

                        # Asegurar columnas en subset editable
                        for need in [
                            "Estado",
                            "Fecha Registro","Hora Registro",
                            "Fecha inicio","Hora de inicio",
                            "Fecha Terminado","Hora Terminado",
                            "Fecha estado actual","Hora estado actual",
                            "Link de archivo",
                        ]:
                            if need not in base.columns:
                                base[need] = ""

                        # Limitar ids a los presentes en base filtrada
                        ids_ok = [i for i in ids_view if i in set(base["Id"].astype(str))]

                        # Validación: fin sin inicio (no super) → no permitir
                        if not is_super:
                            # lookup actual de inicio + nuevos candidatos
                            cur_start = base.set_index("Id")["Fecha inicio"].astype(str).str.strip()
                            bad = [i for i in ids_ok if (ft_new.get(i, "") and not (cur_start.get(i, "") or fi_new.get(i, "")))]
                            if bad:
                                st.warning("No puedes registrar 'Fecha terminada' sin 'Fecha inicio' en algunas tareas.")
                                for i in bad:
                                    ft_new[i] = ""
                                    ht_new[i] = ""

                        # Sellos de hora actuales
                        local_now = _now_lima_trimmed_local()
                        h_now = local_now.strftime("%H:%M")

                        changed_ids: set[str] = set()

                        # === APLICAR CAMBIOS POR MAPEO (robusto con Ids duplicados en full_before) ===
                        full_updated = full_before.copy()
                        # Construir diccionarios Id -> valor actualizado
                        base_idx = base.copy().set_index("Id")
                        # asegurar índice único en los diccionarios tomando el último
                        base_idx = base_idx[~base_idx.index.duplicated(keep="last")]

                        for i in ids_ok:
                            # START
                            prev_fi = str(base_idx.at[i, "Fecha inicio"]) if i in base_idx.index else ""
                            prev_hi = str(base_idx.at[i, "Hora de inicio"]) if i in base_idx.index else ""
                            new_fi = fi_new.get(i, "")
                            new_hi = hi_new.get(i, "")

                            if is_super:
                                if new_fi != prev_fi:
                                    base_idx.at[i, "Fecha inicio"] = new_fi
                                    changed_ids.add(i)
                                if new_fi:
                                    if not new_hi:
                                        new_hi = h_now
                                    if new_hi != prev_hi:
                                        base_idx.at[i, "Hora de inicio"] = new_hi
                                        changed_ids.add(i)
                            else:
                                if (not prev_fi) and new_fi:
                                    base_idx.at[i, "Fecha inicio"] = new_fi
                                    base_idx.at[i, "Hora de inicio"] = (new_hi or h_now)
                                    changed_ids.add(i)

                            # FIN
                            prev_ft = str(base_idx.at[i, "Fecha Terminado"]) if i in base_idx.index else ""
                            prev_ht = str(base_idx.at[i, "Hora Terminado"]) if i in base_idx.index else ""
                            new_ft = ft_new.get(i, "")
                            new_ht = ht_new.get(i, "")

                            has_start_now = str(base_idx.at[i, "Fecha inicio"]) if i in base_idx.index else ""
                            has_start_now = bool(str(has_start_now).strip())

                            if is_super:
                                if new_ft != prev_ft:
                                    base_idx.at[i, "Fecha Terminado"] = new_ft
                                    changed_ids.add(i)
                                if new_ft:
                                    if not new_ht:
                                        new_ht = h_now
                                    if new_ht != prev_ht:
                                        base_idx.at[i, "Hora Terminado"] = new_ht
                                        changed_ids.add(i)
                            else:
                                if (not prev_ft) and new_ft and has_start_now:
                                    base_idx.at[i, "Fecha Terminado"] = new_ft
                                    base_idx.at[i, "Hora Terminado"] = (new_ht or h_now)
                                    changed_ids.add(i)

                            # LINK
                            prev_lk = str(base_idx.at[i, "Link de archivo"]) if i in base_idx.index else ""
                            new_lk = lk_new.get(i, "")
                            if new_lk != prev_lk:
                                base_idx.at[i, "Link de archivo"] = new_lk
                                changed_ids.add(i)

                            # Estado + sello actual
                            fi_eff = str(base_idx.at[i, "Fecha inicio"]) if i in base_idx.index else ""
                            ft_eff = str(base_idx.at[i, "Fecha Terminado"]) if i in base_idx.index else ""
                            if ft_eff.strip():
                                base_idx.at[i, "Estado"] = "Terminado"
                                base_idx.at[i, "Fecha estado actual"] = ft_eff
                                base_idx.at[i, "Hora estado actual"] = str(base_idx.at[i, "Hora Terminado"]).strip() or h_now
                            elif fi_eff.strip():
                                base_idx.at[i, "Estado"] = "En curso"
                                base_idx.at[i, "Fecha estado actual"] = fi_eff
                                base_idx.at[i, "Hora estado actual"] = str(base_idx.at[i, "Hora de inicio"]).strip() or h_now
                            else:
                                base_idx.at[i, "Estado"] = "No iniciado"
                                base_idx.at[i, "Fecha estado actual"] = str(base_idx.at[i, "Fecha Registro"]).strip()
                                base_idx.at[i, "Hora estado actual"] = str(base_idx.at[i, "Hora Registro"]).strip()

                        # Aplicar a TODA la base por mapeo (soporta Id duplicados)
                        if changed_ids:
                            cols_apply = [
                                "Estado",
                                "Fecha estado actual","Hora estado actual",
                                "Fecha inicio","Hora de inicio",
                                "Fecha Terminado","Hora Terminado",
                                "Link de archivo",
                            ]
                            for col in cols_apply:
                                if col not in full_updated.columns:
                                    full_updated[col] = ""
                                dic = base_idx[col].to_dict()
                                mask = full_updated["Id"].astype(str).isin(changed_ids)
                                full_updated.loc[mask, col] = full_updated.loc[mask, "Id"].astype(str).map(dic)

                        # Persistir en sesión
                        st.session_state["df_main"] = full_updated.copy()

                        # Guardado local
                        def _persist(_df: pd.DataFrame):
                            try:
                                os.makedirs("data", exist_ok=True)
                                _df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")
                                return {"ok": True, "msg": "Cambios guardados."}
                            except Exception as _e:
                                return {"ok": False, "msg": f"Error al guardar: {_e}"}

                        maybe_save = st.session_state.get("maybe_save")
                        res = maybe_save(_persist, full_updated.copy()) if callable(maybe_save) else _persist(full_updated.copy())

                        # Upsert a Sheets (solo ids cambiados)
                        try:
                            if changed_ids:
                                _sheet_upsert_estado_by_id(full_updated.copy(), sorted(changed_ids))
                        except Exception as ee:
                            st.info(f"Guardado local OK. No pude actualizar Sheets: {ee}")

                        if res.get("ok", False):
                            st.success(res.get("msg", "Cambios guardados."))
                            st.rerun()
                        else:
                            st.info(res.get("msg", "Guardado deshabilitado."))
                except Exception as e:
                    st.error(f"No pude guardar: {e}")

        st.markdown("</div></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
