# features/editar_estado/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    DataReturnMode,
    JsCode,
)

def render(user: dict | None = None):
    # ================== EDITAR ESTADO ==================
    st.session_state.setdefault("est_visible", True)  # siempre visible

    # ---------- Barra superior ----------
    st.markdown('<div class="topbar-eval">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">✏️&nbsp;&nbsp;Editar estado</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    # ---------- fin barra superior ----------

    if st.session_state["est_visible"]:

        # --- Contenedor + CSS local ---
        st.markdown('<div id="est-section">', unsafe_allow_html=True)
        st.markdown("""
        <style>
          #est-section .stButton > button { width: 100% !important; }
          /* Encabezados más legibles: permiten salto de línea y mayor altura */
          #est-section .ag-header-cell-label{
            font-weight: 400 !important;
            white-space: normal !important;   /* <-- permite que el título se parta en 2 líneas */
            line-height: 1.15 !important;
          }
          #est-section .ag-body-horizontal-scroll,
          #est-section .ag-center-cols-viewport { overflow-x: hidden !important; }
          .section-est .help-strip + .form-card{ margin-top: 6px !important; }
        </style>
        """, unsafe_allow_html=True)

        # ===== Wrapper UNIDO: help-strip + form-card =====
        st.markdown("""
        <div class="section-est">
          <div class="help-strip">
            🔷 <strong>Actualiza el estado</strong> de una tarea ya registrada usando los filtros
          </div>
          <div class="form-card">
        """, unsafe_allow_html=True)

        # Proporciones
        A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

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

            # Rango de fechas (siempre visible; por defecto = min–max del dataset)
            est_desde = c_desde.date_input("Desde", value=min_date, min_value=min_date, max_value=max_date, key="est_desde")
            est_hasta = c_hasta.date_input("Hasta", value=max_date, min_value=min_date, max_value=max_date, key="est_hasta")

            # Alineación del botón Buscar a la misma altura que los campos
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

            # aplicar rango (prioridad: Fecha inicio -> Fecha Registro -> Fecha)
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
            # Asegurar presencia de columnas usadas
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

            # Normalizaciones por estado
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

            # Inicializar finales
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

            # Respetar valores existentes
            fecha_estado_exist = pd.to_datetime(base["Fecha estado actual"], errors="coerce").dt.normalize()
            hora_estado_exist  = base["Hora estado actual"].astype(str)

            fecha_estado_final = fecha_estado_exist.where(fecha_estado_exist.notna(), fecha_from_estado)
            hora_estado_final  = hora_estado_exist.where(hora_estado_exist.str.strip() != "", hora_from_estado)

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

        # ========= editores y estilo seguro =========
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

        # --- AgGrid ---
        gob = GridOptionsBuilder.from_dataframe(df_view)
        gob.configure_grid_options(
            suppressMovableColumns=True,
            domLayout="normal",
            ensureDomOrder=True,
            rowHeight=38,
            headerHeight=60,               # <-- más alto para que el texto envuelto no se corte
            suppressHorizontalScroll=True
        )
        # Encabezados con salto de línea automático
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
                        base = st.session_state.get("df_main", pd.DataFrame()).copy()
                        if base.empty:
                            st.warning("No hay base para actualizar.")
                        else:
                            base["Id"] = base["Id"].astype(str)
                            cols_to_merge = ["Estado modificado","Fecha estado modificado","Hora estado modificado"]
                            for c in cols_to_merge:
                                if c not in base.columns:
                                    base[c] = ""
                            upd = grid_data[["Id"] + cols_to_merge].copy()
                            base = base.merge(upd, on="Id", how="left", suffixes=("", "_NEW"))
                            for c in cols_to_merge:
                                n = f"{c}_NEW"
                                if n in base.columns:
                                    base[c] = base[n].where(base[n].notna() & (base[n] != ""), base[c])
                                    base.drop(columns=[n], inplace=True)

                            st.session_state["df_main"] = base.copy()

                            # ======== PERSISTIR con maybe_save (sin ACL de edición; todos pueden) ========
                            def _persist(_df: pd.DataFrame):
                                try:
                                    os.makedirs("data", exist_ok=True)
                                    _df.to_csv(os.path.join("data","tareas.csv"), index=False, encoding="utf-8-sig")
                                    return {"ok": True, "msg": "Cambios guardados."}
                                except Exception as _e:
                                    return {"ok": False, "msg": f"Error al guardar: {_e}"}

                            maybe_save = st.session_state.get("maybe_save")
                            res = maybe_save(_persist, base.copy()) if callable(maybe_save) else _persist(base.copy())

                            if res.get("ok", False):
                                st.success(res.get("msg", "Cambios guardados."))
                                st.rerun()
                            else:
                                # Ej.: DRY-RUN o guardado deshabilitado por política
                                st.info(res.get("msg", "Guardado deshabilitado."))

                except Exception as e:
                    st.error(f"No pude guardar: {e}")

        # Cerrar form-card + section + contenedor
        st.markdown('</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
