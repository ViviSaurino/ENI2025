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

# Hora Lima para sellado de cambios
try:
    from shared import now_lima_trimmed
except Exception:
    from datetime import datetime
    def now_lima_trimmed():
        return datetime.now().replace(second=0, microsecond=0)

# ========= Utilidades mínimas para zonas horarias (solo para Duración) =========
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None

def _to_naive_local_one(x):
    """
    Convierte un valor fecha/hora (string o Timestamp) a datetime *naive* en hora local.
    - Si viene con tz (p.ej. '2025-11-06T16:12:00-05:00'): convierte a local y elimina tz.
    - Si viene sin tz (naive): lo deja tal cual (se asume ya está en hora local).
    """
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return pd.NaT
    try:
        # Si ya es Timestamp
        if isinstance(x, pd.Timestamp):
            if x.tz is not None:
                d = x.tz_convert(_TZ or x.tz).tz_localize(None) if _TZ else x.tz_localize(None)
                return d
            return x  # ya es naive
        s = str(x).strip()
        if not s or s.lower() in {"nan", "nat", "none", "null"}:
            return pd.NaT
        # Detecta indicios de tz en el string (Z, +hh:mm, -hh:mm)
        if re.search(r'(Z|[+-]\d{2}:?\d{2})$', s):
            d = pd.to_datetime(s, errors="coerce", utc=True)
            if pd.isna(d):
                return pd.NaT
            if _TZ:
                d = d.tz_convert(_TZ)
            return d.tz_localize(None)
        # Caso naive: parse directo y se mantiene naive (local)
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT

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

# --- Cliente GSheets y upsert por Id (se mantiene igual que antes) ---
def _gsheets_client():
    if "gcp_service_account" not in st.secrets:
        raise KeyError("Falta 'gcp_service_account' en secrets.")
    url = st.secrets.get("gsheets_doc_url") or \
          (st.secrets.get("gsheets", {}) or {}).get("spreadsheet_url") or \
          (st.secrets.get("sheets", {}) or {}).get("sheet_url")
    if not url:
        raise KeyError("No se encontró 'gsheets_doc_url' ni '[gsheets].spreadsheet_url' ni '[sheets].sheet_url'.")
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
    col_map = {h: i+1 for i, h in enumerate(headers)}
    if "Id" not in col_map:
        st.info("La hoja seleccionada no tiene columna 'Id'; no se puede actualizar por Id.")
        return

    id_idx = col_map["Id"] - 1
    id_to_row = {}
    for r_i, row in enumerate(values[1:], start=2):
        if id_idx < len(row):
            id_to_row[str(row[id_idx]).strip()] = r_i

    cols_to_push = [
        "Estado",
        "Fecha estado actual",
        "Hora estado actual",
        "Duración",
        "Estado modificado",
        "Fecha estado modificado",
        "Hora estado modificado",
    ]
    cols_to_push = [c for c in cols_to_push if c in col_map]

    def _fmt_out(col, val):
        low = str(col).lower()
        if low.startswith("fecha"):
            d = _to_naive_local_one(val)
            return "" if pd.isna(d) else d.strftime("%Y-%m-%d")
        if low.startswith("hora"):
            return _fmt_hhmm(val)
        return "" if (val is None or (isinstance(val, float) and pd.isna(val))) else str(val)

    last_col_letter = _col_letter(len(headers))
    body = []
    ranges = []

    df_idx = df_base.set_index("Id")
    for _id in changed_ids:
        if _id not in df_idx.index:
            continue
        row_idx = id_to_row.get(str(_id))
        if not row_idx:
            new_row = []
            for h in headers:
                v = df_idx.loc[_id, h] if h in df_idx.columns else ""
                new_row.append(_fmt_out(h, v))
            values.append(new_row)
            ws.append_row(new_row, value_input_option="USER_ENTERED")
            continue

        current_row = values[row_idx-1].copy()
        if len(current_row) < len(headers):
            current_row += [""] * (len(headers) - len(current_row))

        for h in cols_to_push:
            v = df_idx.loc[_id, h] if h in df_idx.columns else ""
            current_row[col_map[h]-1] = _fmt_out(h, v)

        ranges.append(f"A{row_idx}:{last_col_letter}{row_idx}")
        body.append(current_row[:len(headers)])

    if body and ranges:
        data = [{"range": rng, "values": [vals]} for rng, vals in zip(ranges, body)]
        ws.batch_update({"valueInputOption": "USER_ENTERED", "data": data})

# ===============================================================================

def render(user: dict | None = None):
    # ================== EDITAR ESTADO ==================
    st.session_state.setdefault("est_visible", True)  # siempre visible

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.session_state["est_visible"]:

        # === Proporciones (igual que los filtros; A = ancho de "Área") ===
        A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

        # --- Contenedor + CSS local ---
        st.markdown('<div id="est-section">', unsafe_allow_html=True)
        st.markdown("""
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
        """, unsafe_allow_html=True)

        c_pill, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with c_pill:
            st.markdown('<div class="est-pill"><span>✏️&nbsp;Editar estado</span></div>', unsafe_allow_html=True)

        st.markdown("""
        <div class="section-est">
          <div class="help-strip">
            🔷 <strong>Actualiza el estado</strong> de una tarea ya registrada usando los filtros
          </div>
          <div class="form-card">
        """, unsafe_allow_html=True)

        # Base
        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()

        # ===== Rango por defecto (min–max del dataset) =====
        def _first_valid_date_series(df: pd.DataFrame) -> pd.Series:
            for col in ["Fecha inicio", "Fecha Registro", "Fecha"]:
                if col in df.columns:
                    s = pd.to_datetime(df[col], errors="coerce")
                    if s.notna().any():
                        return s
            return pd.Series([], dtype="datetime64[ns]")

        dates_all = _first_valid_date_series(df_all)
        if dates_all.empty:
            today = pd.Timestamp.today().normalize().date()
            min_date = today
            max_date = today
        else:
            min_date = dates_all.min().date()
            max_date = dates_all.max().date()

        # ===== FILTROS =====
        with st.form("est_filtros_v3", clear_on_submit=False):
            c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

            # Área
            AREAS_OPC = st.session_state.get(
                "AREAS_OPC",
                sorted([x for x in df_all.get("Área", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            ) or []
            est_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0)

            # Fase
            fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            est_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

            # Responsable
            df_resp_src = df_all.copy()
            if est_area != "Todas" and "Área" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Área"].astype(str) == est_area]
            if est_fase != "Todas" and "Fase" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == est_fase]
            responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            est_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0)

            # Rango de fechas
            est_desde = c_desde.date_input("Desde", value=min_date, min_value=min_date, max_value=max_date, key="est_desde")
            est_hasta = c_hasta.date_input("Hasta", value=max_date, min_value=min_date, max_value=max_date, key="est_hasta")

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

            if "Fecha inicio" in df_tasks.columns:
                fcol = pd.to_datetime(df_tasks["Fecha inicio"], errors="coerce")
            elif "Fecha Registro" in df_tasks.columns:
                fcol = pd.to_datetime(df_tasks["Fecha Registro"], errors="coerce")
            else:
                fcol = pd.to_datetime(df_tasks.get("Fecha", pd.Series([], dtype=str)), errors="coerce")

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
            for need in [
                "Id","Tarea","Estado",
                "Fecha Registro","Hora Registro","Fecha","Hora",
                "Fecha inicio","Hora de inicio",
                "Fecha Terminado","Hora Terminado",
                "Fecha Pausado","Hora Pausado",
                "Fecha Cancelado","Hora Cancelado",
                "Fecha Eliminado","Hora Eliminado",
                "Fecha estado actual","Hora estado actual",
                "Estado modificado","Fecha estado modificado","Hora estado modificado"
            ]:
                if need not in base.columns:
                    base[need] = ""

            base["Estado"] = base["Estado"].astype(str)
            base.loc[base["Estado"].str.strip().isin(["", "nan"]), "Estado"] = "No iniciado"

            def _date_norm(col_main, col_fb=None):
                s = pd.to_datetime(base[col_main], errors="coerce").dt.normalize()
                if col_fb:
                    s = s.fillna(pd.to_datetime(base[col_fb], errors="coerce").dt.normalize())
                return s

            def _time_norm(col_main, col_fb=None):
                s = _fmt_time(base[col_main])
                if col_fb:
                    s_fb = _fmt_time(base[col_fb])
                    s = s.where(s.str.strip() != "", s_fb)
                return s

            fr_noini = _date_norm("Fecha Registro", "Fecha")
            hr_noini = _time_norm("Hora Registro", "Hora")

            fr_enc   = _date_norm("Fecha inicio")
            hr_enc   = _time_norm("Hora de inicio")

            fr_fin   = _date_norm("Fecha Terminado")
            hr_fin   = _time_norm("Hora Terminado")

            fr_pau, hr_pau = _date_norm("Fecha Pausado"),  _time_norm("Hora Pausado")
            fr_can, hr_can = _date_norm("Fecha Cancelado"), _time_norm("Hora Cancelado")
            fr_eli, hr_eli = _date_norm("Fecha Eliminado"), _time_norm("Hora Eliminado")

            estado_now = base["Estado"].astype(str)

            fecha_from_estado = pd.Series(pd.NaT, index=base.index, dtype="datetime64[ns]")
            hora_from_estado  = pd.Series("", index=base.index, dtype="object")

            m0 = (estado_now == "No iniciado")
            m1 = (estado_now == "En curso")
            m2 = (estado_now == "Terminado")
            m3 = (estado_now == "Pausado")
            m4 = (estado_now == "Cancelado")
            m5 = (estado_now == "Eliminado")

            fecha_from_estado[m0] = fr_noini[m0]; hora_from_estado[m0] = hr_noini[m0]
            fecha_from_estado[m1] = fr_enc[m1];   hora_from_estado[m1] = hr_enc[m1]
            fecha_from_estado[m2] = fr_fin[m2];   hora_from_estado[m2] = hr_fin[m2]
            fecha_from_estado[m3] = fr_pau[m3];   hora_from_estado[m3] = hr_pau[m3]
            fecha_from_estado[m4] = fr_can[m4];   hora_from_estado[m4] = hr_can[m4]
            fecha_from_estado[m5] = fr_eli[m5];   hora_from_estado[m5] = hr_eli[m5]

            fecha_estado_exist = pd.to_datetime(base["Fecha estado actual"], errors="coerce").dt.normalize()
            hora_estado_exist  = base["Hora estado actual"].astype(str)

            fecha_estado_final = fecha_estado_exist.where(fecha_estado_exist.notna(), fecha_from_estado)
            hora_estado_final  = hora_estado_exist.where(hora_estado_exist.str.strip() != "", hora_from_estado)

            fecha_estado_final = fecha_estado_final.where(
                fecha_estado_final.notna(), pd.to_datetime(base.get("Fecha Registro"), errors="coerce").dt.normalize()
            )
            hora_reg_str = base.get("Hora Registro", pd.Series("", index=base.index)).astype(str)
            hora_estado_final = hora_estado_final.where(hora_estado_final.str.strip() != "", hora_reg_str)

            df_view = pd.DataFrame({
                "Id":   base["Id"].astype(str),
                "Tarea": base["Tarea"].astype(str),
                "Estado actual": estado_now,
                "Fecha estado actual": _fmt_date(fecha_estado_final),
                "Hora estado actual":  _fmt_time(hora_estado_final),
                "Estado modificado":       base["Estado modificado"].astype(str),
                "Fecha estado modificado": _fmt_date(base["Fecha estado modificado"]),
                "Hora estado modificado":  _fmt_time(base["Hora estado modificado"]),
            })[cols_out].copy()

        # ========= editores y estilo =========
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

        estado_emoji_fmt = JsCode("""
        function(p){
          const v = String(p.value || '');
          const M = {
            "En curso":"🟣 En curso",
            "Terminado":"✅ Terminado",
            "Pausado":"⏸️ Pausado",
            "Cancelado":"⛔ Cancelado",
            "Eliminado":"🗑️ Eliminado"
          };
          return M[v] || v;
        }""")

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

        gob = GridOptionsBuilder.from_dataframe(df_view)
        gob.configure_grid_options(
            suppressMovableColumns=True,
            domLayout="normal",
            ensureDomOrder=True,
            rowHeight=38,
            headerHeight=60,
            suppressHorizontalScroll=True
        )
        gob.configure_default_column(wrapHeaderText=True, autoHeaderHeight=True)
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
        gob.configure_column("Fecha estado modificado", editable=True, cellEditor=date_editor, minWidth=170)
        gob.configure_column("Hora estado modificado",  editable=False, minWidth=150)

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

        # ===== Guardar cambios =====
        u1, u2 = st.columns([A+Fw+T_width+D+R, C], gap="medium")
        with u2:
            if st.button("💾 Guardar", use_container_width=True, key="est_guardar_inline_v3"):
                try:
                    grid_data = pd.DataFrame(grid.get("data", []))
                    if grid_data.empty or "Id" not in grid_data.columns:
                        st.info("No hay cambios para guardar.")
                    else:
                        grid_data["Id"] = grid_data["Id"].astype(str)

                        changes = grid_data.loc[
                            grid_data["Estado modificado"].astype(str).str.strip() != "",
                            ["Id", "Estado modificado"]
                        ].copy()

                        base = st.session_state.get("df_main", pd.DataFrame()).copy()
                        if base.empty:
                            st.warning("No hay base para actualizar.")
                        else:
                            base["Id"] = base["Id"].astype(str)
                            if "Fecha estado actual" not in base.columns:
                                base["Fecha estado actual"] = ""
                            if "Hora estado actual" not in base.columns:
                                base["Hora estado actual"] = ""
                            if "Estado" not in base.columns:
                                base["Estado"] = "No iniciado"

                            ts = now_lima_trimmed()
                            f_now = pd.Timestamp(ts).strftime("%Y-%m-%d")
                            h_now = pd.Timestamp(ts).strftime("%H:%M")

                            b_i = base.set_index("Id")
                            c_i = changes.set_index("Id")
                            ids = b_i.index.intersection(c_i.index)

                            b_i.loc[ids, "Estado"] = c_i.loc[ids, "Estado modificado"].values
                            b_i.loc[ids, "Fecha estado actual"] = f_now
                            b_i.loc[ids, "Hora estado actual"] = h_now

                            # ===== Duración (ajuste robusto tz) =====
                            if "Duración" in b_i.columns and "Fecha Registro" in b_i.columns:
                                ts_naive = pd.Timestamp(ts)  # naive
                                def _mins_since(fr_val):
                                    d = _to_naive_local_one(fr_val)
                                    if pd.isna(d):
                                        return 0
                                    try:
                                        return int((ts_naive - d).total_seconds() / 60)
                                    except Exception:
                                        return 0
                                dur_min = b_i.loc[ids, "Fecha Registro"].apply(_mins_since)
                                try:
                                    b_i.loc[ids, "Duración"] = dur_min
                                except Exception:
                                    pass

                            # Limpiar auxiliares
                            for aux in ["Estado modificado","Fecha estado modificado","Hora estado modificado"]:
                                if aux in b_i.columns:
                                    b_i.loc[ids, aux] = ""

                            base = b_i.reset_index()
                            st.session_state["df_main"] = base.copy()

                            def _persist(_df: pd.DataFrame):
                                try:
                                    os.makedirs("data", exist_ok=True)
                                    _df.to_csv(os.path.join("data","tareas.csv"), index=False, encoding="utf-8-sig")
                                    return {"ok": True, "msg": "Cambios guardados."}
                                except Exception as _e:
                                    return {"ok": False, "msg": f"Error al guardar: {_e}"}

                            maybe_save = st.session_state.get("maybe_save")
                            res = maybe_save(_persist, base.copy()) if callable(maybe_save) else _persist(base.copy())

                            try:
                                _sheet_upsert_estado_by_id(base.copy(), list(ids))
                            except Exception as ee:
                                st.info(f"Guardado local OK. No pude actualizar Sheets: {ee}")

                            if res.get("ok", False):
                                st.success(res.get("msg", "Cambios guardados."))
                                st.rerun()
                            else:
                                st.info(res.get("msg", "Guardado deshabilitado."))

                except Exception as e:
                    st.error(f"No pude guardar: {e}")

        st.markdown('</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
