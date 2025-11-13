# features/nueva_alerta/view.py 
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode, JsCode

SECTION_GAP_DEF = globals().get("SECTION_GAP", 30)

# ==== ACL + hora Lima (compat con shared) ====
try:
    from shared import apply_scope, now_lima_trimmed
except Exception:
    def apply_scope(df, user=None, resp_col="Responsable"):
        return df
    from datetime import datetime, timedelta
    def now_lima_trimmed():
        return (datetime.utcnow() - timedelta(hours=5)).replace(second=0, microsecond=0)

# Hora Lima local sin segundos (robusto a secrets/local_tz)
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None


def _now_lima_trimmed_local():
    from datetime import datetime, timedelta
    try:
        if _TZ:
            return datetime.now(_TZ).replace(second=0, microsecond=0)
        return (datetime.utcnow() - timedelta(hours=5)).replace(second=0, microsecond=0)
    except Exception:
        return now_lima_trimmed()


def _save_local(df: pd.DataFrame):
    try:
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")
        return {"ok": True, "msg": "Cambios guardados."}
    except Exception as e:
        return {"ok": False, "msg": f"Error al guardar: {e}"}


def _display_name() -> str:
    """Nombre visible del usuario (para detectar Vivi / Enrique)."""
    u = st.session_state.get("acl_user", {}) or {}
    return (
        u.get("display")
        or st.session_state.get("user_display_name", "")
        or u.get("name", "")
        or (st.session_state.get("user") or {}).get("name", "")
        or ""
    )


def _is_super_alert_editor() -> bool:
    """Vivi, Enrique o quien tenga can_edit_all=True ven filtro Responsable y todas las tareas."""
    u = st.session_state.get("acl_user", {}) or {}
    flag = str(u.get("can_edit_all", "")).strip().lower()
    if flag in {"1", "true", "yes", "si", "sí"}:
        return True
    dn = _display_name().strip().lower()
    return dn.startswith("vivi") or dn.startswith("enrique")


def render(user: dict | None = None):
    st.session_state.setdefault("na_visible", True)

    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.session_state["na_visible"]:
        st.markdown('<div id="na-section">', unsafe_allow_html=True)
        st.markdown(
            """
        <style>
          #na-section .stButton > button { width: 100% !important; }
          .section-na .help-strip-na + .form-card{ margin-top: 6px !important; }

          #na-section .ag-header-cell-label{
            white-space: nowrap !important;
            line-height: 1.15 !important;
            font-weight: 400 !important;
          }
          #na-section .ag-header-cell-text{
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
          }
          #na-section .ag-body-horizontal-scroll,
          #na-section .ag-center-cols-viewport{
            overflow-x: auto !important;
          }

          /* Píldora local (celeste, mismo estilo que Editar estado/Nueva tarea) */
          .na-pill{
            width:100%; height:38px; border-radius:12px;
            display:flex; align-items:center; justify-content:center;
            background:#A7C8F0; color:#ffffff; font-weight:700;
            box-shadow:0 6px 14px rgba(167,200,240,.35);
            user-select:none;
            margin:4px 0 16px;
          }
          .na-pill span{ display:inline-flex; gap:8px; align-items:center; }
        </style>
        """,
            unsafe_allow_html=True,
        )

        c_pill, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with c_pill:
            st.markdown('<div class="na-pill"><span>⚠️&nbsp;Nueva alerta</span></div>', unsafe_allow_html=True)

        st.markdown(
            """
        <div class="section-na">
          <div class="help-strip help-strip-na" id="na-help">
            💡 <strong>Indicaciones:</strong> Cuando una tarea genere una alerta, regístrala en la tabla. 
            Consigna la fecha y hora de detección/corrección. Por último, especifica el tipo de alerta.
          </div>
          <div class="form-card">
        """,
            unsafe_allow_html=True,
        )

        # Base (filtrada por ACL)
        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
        df_all = apply_scope(df_all, user=user)

        # 🔒 Refuerzo local: si NO es super, solo ve sus propias tareas (Responsable)
        if not _is_super_alert_editor() and "Responsable" in df_all.columns:
            dn = _display_name().strip()
            if dn:
                df_all = df_all[df_all["Responsable"].astype(str).str.strip() == dn]

        # Alias de columnas para compatibilidad
        if "Tipo de tarea" not in df_all.columns and "Tipo" in df_all.columns:
            df_all["Tipo de tarea"] = df_all["Tipo"]

        # Estado efectivo (igual lógica que Editar estado)
        fi = pd.to_datetime(
            df_all.get("Fecha de inicio", df_all.get("Fecha inicio", pd.Series([], dtype=object))),
            errors="coerce",
        )
        ft = pd.to_datetime(
            df_all.get("Fecha terminada", df_all.get("Fecha Terminado", pd.Series([], dtype=object))),
            errors="coerce",
        )
        fe = pd.to_datetime(df_all.get("Fecha eliminada", pd.Series([], dtype=object)), errors="coerce")

        estado_calc = pd.Series("No iniciado", index=df_all.index, dtype="object")
        estado_calc = estado_calc.mask(fi.notna() & ft.isna() & fe.isna(), "En curso")
        estado_calc = estado_calc.mask(ft.notna() & fe.isna(), "Terminada")
        estado_calc = estado_calc.mask(fe.notna(), "Eliminada")
        if "Estado" in df_all.columns:
            saved = df_all["Estado"].astype(str).str.strip()
            estado_calc = saved.where(~saved.isin(["", "nan", "NaN", "None"]), estado_calc)
        df_all["_ESTADO_ALERTA_"] = estado_calc

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

        is_super = _is_super_alert_editor()
        estados_catalogo = ["No iniciado", "En curso", "Terminada", "Pausada", "Cancelada", "Eliminada"]

        # ===== FILTROS =====
        with st.form("na_filtros_v4", clear_on_submit=False):
            if is_super:
                # Responsable → Fase → Tipo de tarea → Estado actual → Desde → Hasta → Buscar
                c_resp, c_fase, c_tipo, c_estado, c_desde, c_hasta, c_buscar = st.columns(
                    [Fw, Fw, T_width, D, D, R, C], gap="medium"
                )
            else:
                # Fase → Tipo de tarea → Estado actual → Desde → Hasta → Buscar
                c_fase, c_tipo, c_estado, c_desde, c_hasta, c_buscar = st.columns(
                    [Fw, T_width, D, D, R, C], gap="medium"
                )
                c_resp = None  # no se usa, solo para tipado

            fases_all = sorted(
                [
                    x
                    for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique()
                    if x and x != "nan"
                ]
            )
            na_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

            tipos_all = sorted(
                [
                    x
                    for x in df_all.get("Tipo de tarea", pd.Series([], dtype=str)).astype(str).unique()
                    if x and x != "nan"
                ]
            )
            na_tipo = c_tipo.selectbox("Tipo de tarea", ["Todos"] + tipos_all, index=0)

            # Estado actual (labels con emoji, valor interno sin emoji)
            estado_labels = {
                "No iniciado": "⏳ No iniciado",
                "En curso": "▶️ En curso",
                "Terminada": "✅ Terminada",
                "Pausada": "⏸️ Pausada",
                "Cancelada": "✖️ Cancelada",
                "Eliminada": "🗑️ Eliminada",
            }
            estado_opts_labels = ["Todos"] + [estado_labels[e] for e in estados_catalogo]
            sel_label = c_estado.selectbox("Estado actual", estado_opts_labels, index=0)
            na_estado = (
                "Todos"
                if sel_label == "Todos"
                else [k for k, v in estado_labels.items() if v == sel_label][0]
            )

            if is_super:
                df_resp_src = df_all.copy()
                if na_fase != "Todas" and "Fase" in df_resp_src.columns:
                    df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == na_fase]
                if na_tipo != "Todos" and "Tipo de tarea" in df_resp_src.columns:
                    df_resp_src = df_resp_src[df_resp_src["Tipo de tarea"].astype(str) == na_tipo]
                responsables_all = sorted(
                    [
                        x
                        for x in df_resp_src.get("Responsable", pd.Series([], dtype=str))
                        .astype(str)
                        .unique()
                        if x and x != "nan"
                    ]
                )
                na_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0)
            else:
                na_resp = "Todos"

            na_desde = c_desde.date_input(
                "Desde", value=min_date, min_value=min_date, max_value=max_date, key="na_desde"
            )
            na_hasta = c_hasta.date_input(
                "Hasta", value=max_date, min_value=min_date, max_value=max_date, key="na_hasta"
            )

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
                na_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

        df_tasks = df_all.copy()
        if na_do_buscar:
            if is_super and na_resp != "Todos" and "Responsable" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Responsable"].astype(str) == na_resp]
            if na_fase != "Todas" and "Fase" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Fase"].astype(str) == na_fase]
            if na_tipo != "Todos" and "Tipo de tarea" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Tipo de tarea"].astype(str) == na_tipo]
            if na_estado != "Todos" and "_ESTADO_ALERTA_" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["_ESTADO_ALERTA_"].astype(str) == na_estado]

            if "Fecha inicio" in df_tasks.columns:
                fcol = pd.to_datetime(df_tasks["Fecha inicio"], errors="coerce")
            elif "Fecha Registro" in df_tasks.columns:
                fcol = pd.to_datetime(df_tasks["Fecha Registro"], errors="coerce")
            else:
                fcol = pd.to_datetime(
                    df_tasks.get("Fecha", pd.Series([], dtype=str)), errors="coerce"
                )

            if na_desde:
                mask_desde = fcol.isna() | (fcol >= pd.to_datetime(na_desde))
                df_tasks = df_tasks[mask_desde]
            if na_hasta:
                limite = pd.to_datetime(na_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                mask_hasta = fcol.isna() | (fcol <= limite)
                df_tasks = df_tasks[mask_hasta]

        st.markdown("**Resultados**")

        cols_out = [
            "Id",
            "Tarea",
            "¿Generó alerta?",
            "N° alerta",
            "Fecha de detección",
            "Hora de detección",
            "¿Se corrigió?",
            "Fecha de corrección",
            "Hora de corrección",
            "Tipo de alerta",
        ]

        df_view = pd.DataFrame(columns=cols_out)
        if not df_tasks.empty and "Id" in df_tasks.columns:
            df_tmp = df_tasks.dropna(subset=["Id"]).copy()
            alert_cols = [
                "¿Generó alerta?",
                "N° alerta",
                "Fecha de detección",
                "Hora de detección",
                "¿Se corrigió?",
                "Fecha de corrección",
                "Hora de corrección",
                "Tipo de alerta",
            ]
            for c in ["Tarea"] + alert_cols:
                if c not in df_tmp.columns:
                    df_tmp[c] = ""
            df_tmp["¿Generó alerta?"] = df_tmp["¿Generó alerta?"].replace("", "No")
            df_tmp["N° alerta"] = df_tmp["N° alerta"].replace([0, "0"], "")
            df_view = df_tmp[["Id", "Tarea"] + alert_cols].copy()

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

        si_no_formatter = JsCode(
            """
        function(p){
          const v = String(p.value || '');
          const M = {"Sí":"✅ Sí","No":"✖️ No","":"—"};
          return M[v] || v;
        }"""
        )

        # 🎨 Colores suaves: sin grises ni rojos
        si_no_style_genero = JsCode(
            """
        function(p){
          const base = {
            display:'flex', alignItems:'center', justifyContent:'center',
            height:'100%', padding:'0 10px', borderRadius:'12px',
            fontWeight:'600', textAlign:'center'
          };
          const v = String(p.value || '');
          if (v === 'Sí') return Object.assign({}, base, {backgroundColor:'#FEF9C3', color:'#92400E'});  // amarillo suave
          if (v === 'No') return Object.assign({}, base, {backgroundColor:'#DBEAFE', color:'#1E3A8A'});  // celeste suave
          return {};
        }"""
        )

        si_no_style_corrigio = JsCode(
            """
        function(p){
          const base = {
            display:'flex', alignItems:'center', justifyContent:'center',
            height:'100%', padding:'0 10px', borderRadius:'12px',
            fontWeight:'600', textAlign:'center'
          };
          const v = String(p.value || '');
          if (v === 'Sí') return Object.assign({}, base, {backgroundColor:'#DCFCE7', color:'#166534'});  // verde pastel
          if (v === 'No') return Object.assign({}, base, {backgroundColor:'#EDE9FE', color:'#4C1D95'});  // lila pastel
          return {};
        }"""
        )

        # ✅ Ajuste: sellos en hora Lima (UTC-5) al cambiar la fecha en el grid
        on_cell_changed = JsCode(
            """
        function(params){
          const pad = n => String(n).padStart(2,'0');
          const now = new Date();
          const utcMs = now.getTime() + now.getTimezoneOffset()*60000;
          const lima = new Date(utcMs - 5*60*60000); // Perú (sin DST)
          const hhmm = pad(lima.getHours()) + ':' + pad(lima.getMinutes());
          if (params.colDef.field === 'Fecha de detección'){
            params.node.setDataValue('Hora de detección', hhmm);
          }
          if (params.colDef.field === 'Fecha de corrección'){
            params.node.setDataValue('Hora de corrección', hhmm);
          }
        }"""
        )

        # Dejamos handlers vacíos (no usamos sizeColumnsToFit)
        on_ready_size = JsCode("function(p){}")
        on_first_size = JsCode("function(p){}")

        col_defs = [
            {"field": "Id", "headerName": "Id", "editable": False, "minWidth": 100},
            {
                "field": "Tarea",
                "headerName": "📝 Tarea",
                "editable": False,
                "minWidth": 220,
                "cellStyle": {
                    "whiteSpace": "nowrap",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                },
            },
            {
                "field": "¿Generó alerta?",
                "headerName": "¿Generó alerta?",
                "editable": True,
                "cellEditor": "agSelectCellEditor",
                "cellEditorParams": {"values": ["No", "Sí"]},
                "valueFormatter": si_no_formatter,
                "cellStyle": si_no_style_genero,
                "minWidth": 140,
            },
            {
                "field": "N° alerta",
                "headerName": "N° alerta",
                "editable": True,
                "cellEditor": "agSelectCellEditor",
                "cellEditorParams": {"values": ["1", "2", "3", "+4"]},
                "minWidth": 110,
            },
            {
                "field": "Fecha de detección",
                "headerName": "🔎 Fecha de detección",
                "editable": True,
                "cellEditor": date_editor,
                "minWidth": 200,
            },
            {
                "field": "Hora de detección",
                "headerName": "🔎 Hora de detección",
                "editable": False,
                "minWidth": 200,
            },
            {
                "field": "¿Se corrigió?",
                "headerName": "¿Se corrigió?",
                "editable": True,
                "cellEditor": "agSelectCellEditor",
                "cellEditorParams": {"values": ["No", "Sí"]},
                "valueFormatter": si_no_formatter,
                "cellStyle": si_no_style_corrigio,
                "minWidth": 140,
            },
            {
                "field": "Fecha de corrección",
                "headerName": "🛠️ Fecha de corrección",
                "editable": True,
                "cellEditor": date_editor,
                "minWidth": 200,
            },
            {
                "field": "Hora de corrección",
                "headerName": "🛠️ Hora de corrección",
                "editable": False,
                "minWidth": 200,
            },
            {
                "field": "Tipo de alerta",
                "headerName": "⚠️ Tipo de alerta",
                "editable": True,
                "minWidth": 180,
            },
        ]

        grid_opts = {
            "columnDefs": col_defs,
            "defaultColDef": {
                "resizable": True,
                "wrapText": False,
                "autoHeight": False,
                "wrapHeaderText": False,
                "autoHeaderHeight": False,
                "minWidth": 100,
            },
            "suppressMovableColumns": True,
            "domLayout": "normal",
            "ensureDomOrder": True,
            "rowHeight": 38,
            "headerHeight": 64,
            "suppressHorizontalScroll": False,
        }
        grid_opts["onCellValueChanged"] = on_cell_changed.js_code
        grid_opts["onGridReady"] = on_ready_size.js_code
        grid_opts["onFirstDataRendered"] = on_first_size.js_code

        grid = AgGrid(
            df_view,
            gridOptions=grid_opts,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            fit_columns_on_grid_load=False,
            enable_enterprise_modules=False,
            reload_data=False,
            height=420,  # tabla alta
            allow_unsafe_jscode=True,
            theme="balham",
        )

        _sp, _btn = st.columns([A + Fw + T_width + D + R, C], gap="medium")
        with _btn:
            if st.button("💾 Guardar", use_container_width=True):
                try:
                    df_edit = pd.DataFrame(grid["data"]).copy()
                    df_base = st.session_state.get("df_main", pd.DataFrame()).copy()

                    if (
                        df_edit.empty
                        or "Id" not in df_edit.columns
                        or df_base.empty
                        or "Id" not in df_base.columns
                    ):
                        st.info("No hay cambios para guardar.")
                    else:
                        alert_cols = [
                            "¿Generó alerta?",
                            "N° alerta",
                            "Fecha de detección",
                            "Hora de detección",
                            "¿Se corrigió?",
                            "Fecha de corrección",
                            "Hora de corrección",
                            "Tipo de alerta",
                        ]
                        for c in alert_cols:
                            if c not in df_base.columns:
                                df_base[c] = ""

                        cambios = 0
                        _now = _now_lima_trimmed_local()
                        h_now = _now.strftime("%H:%M")

                        for _, row in df_edit.iterrows():
                            id_row = str(row.get("Id", "")).strip()
                            if not id_row:
                                continue
                            m = df_base["Id"].astype(str).str.strip() == id_row
                            if not m.any():
                                continue

                            def _set(col_base, val):
                                if val is None:
                                    v = ""
                                else:
                                    v = str(val).strip()
                                if v != "":
                                    df_base.loc[m, col_base] = v
                                    return 1
                                return 0

                            # Set básicos (incluye Tipo de alerta)
                            cambios += _set("¿Generó alerta?", row.get("¿Generó alerta?"))
                            cambios += _set("N° alerta", row.get("N° alerta"))
                            cambios += _set("Fecha de detección", row.get("Fecha de detección"))
                            cambios += _set("Hora de detección", row.get("Hora de detección"))
                            cambios += _set("¿Se corrigió?", row.get("¿Se corrigió?"))
                            cambios += _set("Fecha de corrección", row.get("Fecha de corrección"))
                            cambios += _set("Hora de corrección", row.get("Hora de corrección"))
                            cambios += _set("Tipo de alerta", row.get("Tipo de alerta"))

                            # Si hay fecha y falta hora -> sellamos con hora Lima
                            if (
                                str(df_base.loc[m, "Fecha de detección"].iloc[0]).strip()
                                and str(df_base.loc[m, "Hora de detección"].iloc[0]).strip()
                                in {"", "nan", "NaN", "00:00"}
                            ):
                                df_base.loc[m, "Hora de detección"] = h_now
                                cambios += 1

                            if (
                                str(df_base.loc[m, "Fecha de corrección"].iloc[0]).strip()
                                and str(df_base.loc[m, "Hora de corrección"].iloc[0]).strip()
                                in {"", "nan", "NaN", "00:00"}
                            ):
                                df_base.loc[m, "Hora de corrección"] = h_now
                                cambios += 1

                        if cambios > 0:
                            st.session_state["df_main"] = df_base.copy()

                            def _persist(_df: pd.DataFrame):
                                return _save_local(_df)

                            maybe_save = st.session_state.get("maybe_save")
                            res = (
                                maybe_save(_persist, df_base.copy())
                                if callable(maybe_save)
                                else _persist(df_base.copy())
                            )

                            if res.get("ok", False):
                                st.success(f"✔ Cambios guardados: {cambios} actualización(es).")
                                st.rerun()
                            else:
                                st.info(res.get("msg", "Guardado deshabilitado."))
                        else:
                            st.info("No se detectaron cambios para guardar.")
                except Exception as e:
                    st.error(f"No pude guardar los cambios: {e}")

        st.markdown("</div></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='height:{SECTION_GAP_DEF}px'></div>", unsafe_allow_html=True)
