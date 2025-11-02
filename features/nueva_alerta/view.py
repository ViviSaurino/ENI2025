# features/nueva_alerta/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode, JsCode

# Fallbacks seguros (no alteran tu lógica existente)
SECTION_GAP_DEF = globals().get("SECTION_GAP", 30)

def _save_local(df: pd.DataFrame):
    """Guardar localmente sin romper si la carpeta no existe."""
    try:
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")
    except Exception:
        pass


def render(user: dict | None = None):
    # ================== Nueva alerta ==================

    st.session_state.setdefault("na_visible", True)
    chev3 = "▾" if st.session_state["na_visible"] else "▸"

    # ---------- Barra superior ----------
    st.markdown('<div class="topbar-na">', unsafe_allow_html=True)
    c_toggle3, c_pill3 = st.columns([0.028, 0.965], gap="medium")
    with c_toggle3:
        st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
        def _toggle_na():
            st.session_state["na_visible"] = not st.session_state["na_visible"]
        st.button(chev3, key="na_toggle_icon_v2", help="Mostrar/ocultar", on_click=_toggle_na)
        st.markdown('</div>', unsafe_allow_html=True)
    with c_pill3:
        st.markdown('<div class="form-title-na">&nbsp;&nbsp;⚠️&nbsp;&nbsp;Nueva alerta</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    # ---------- fin barra superior ----------

    if st.session_state["na_visible"]:

        # --- contenedor local + css ---
        st.markdown('<div id="na-section">', unsafe_allow_html=True)
        st.markdown("""
        <style>
          #na-section .stButton > button { width: 100% !important; }
          .section-na .help-strip-na + .form-card{ margin-top: 6px !important; }
        </style>
        """, unsafe_allow_html=True)

        # ===== Wrapper UNIDO: help-strip + form-card =====
        st.markdown("""
        <div class="section-na">
          <div class="help-strip help-strip-na" id="na-help">
            ⚠️ <strong>Vincula una alerta</strong> a una tarea ya registrada
          </div>
          <div class="form-card">
        """, unsafe_allow_html=True)

        # Proporciones (igual que Editar estado)
        A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

        # Base segura
        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()

        # ===== FILTROS =====
        with st.form("na_filtros_v3", clear_on_submit=False):
            c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

            AREAS_OPC = st.session_state.get(
                "AREAS_OPC",
                ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
            )
            na_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0)

            fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            na_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

            df_resp_src = df_all.copy()
            if na_area != "Todas" and "Área" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Área"].astype(str) == na_area]
            if na_fase != "Todas" and "Fase" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == na_fase]
            responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            na_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0)

            # Rango de fechas opcional (evita value=None)
            use_date_range = c_buscar.checkbox("Filtrar por fechas", value=False)
            if use_date_range:
                na_desde = c_desde.date_input("Desde")
                na_hasta = c_hasta.date_input("Hasta")
            else:
                na_desde = na_hasta = None
                with c_desde:
                    st.caption("Desde")
                    st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)
                with c_hasta:
                    st.caption("Hasta")
                    st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)

            with c_buscar:
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                na_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

        # ===== Filtrado de tareas =====
        df_tasks = df_all.copy()
        if na_do_buscar:
            if na_area != "Todas" and "Área" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Área"].astype(str) == na_area]
            if na_fase != "Todas" and "Fase" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Fase"].astype(str) == na_fase]
            if na_resp != "Todos" and "Responsable" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Responsable"].astype(str) == na_resp]
            if use_date_range and "Fecha inicio" in df_tasks.columns:
                fcol = pd.to_datetime(df_tasks["Fecha inicio"], errors="coerce")
                if na_desde:
                    df_tasks = df_tasks[fcol >= pd.to_datetime(na_desde)]
                if na_hasta:
                    df_tasks = df_tasks[fcol <= (pd.to_datetime(na_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

        # ===== Tabla =====
        st.markdown("**Resultados**")

        cols_out = [
            "Id", "Tarea",
            "¿Generó alerta?", "N° alerta",
            "Fecha de detección", "Hora de detección",
            "¿Se corrigió?", "Fecha de corrección", "Hora de corrección",
        ]

        # Data para la grilla (puede ser vacía)
        df_view = pd.DataFrame(columns=cols_out)
        if not df_tasks.empty and "Id" in df_tasks.columns:
            df_tmp = df_tasks.dropna(subset=["Id"]).copy()

            # Garantizar columnas de alerta
            alert_cols = ["¿Generó alerta?","N° alerta","Fecha de detección","Hora de detección",
                          "¿Se corrigió?","Fecha de corrección","Hora de corrección"]
            for c in ["Tarea"] + alert_cols:
                if c not in df_tmp.columns:
                    df_tmp[c] = ""

            # Prefiere valores existentes; usa defaults solo cuando están vacíos
            df_tmp["¿Generó alerta?"] = df_tmp["¿Generó alerta?"].replace("", "No")
            df_tmp["N° alerta"]       = df_tmp["N° alerta"].replace("", "1")

            df_view = df_tmp[["Id","Tarea"] + alert_cols].copy()
            df_view = df_view.rename(columns={})  # (reservado por si renombras algo luego)

        # ====== AG-GRID ======

        # editores de fecha
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

        # Sí/No con emoji
        si_no_formatter = JsCode("""
        function(p){
          const v = String(p.value || '');
          const M = {"Sí":"✅ Sí","No":"✖️ No","":"—"};
          return M[v] || v;
        }""")

        # estilos “pill”
        si_no_style_genero = JsCode("""
        function(p){
          const base = {
            display:'flex', alignItems:'center', justifyContent:'center',
            height:'100%', padding:'0 10px', borderRadius:'12px',
            fontWeight:'600', textAlign:'center'
          };
          const v = String(p.value || '');
          if (v === 'Sí') return Object.assign({}, base, {backgroundColor:'#FFF3E0', color:'#E65100'});
          if (v === 'No') return Object.assign({}, base, {backgroundColor:'#ECEFF1', color:'#37474F'});
          return {};
        }""")

        si_no_style_corrigio = JsCode("""
        function(p){
          const base = {
            display:'flex', alignItems:'center', justifyContent:'center',
            height:'100%', padding:'0 10px', borderRadius:'12px',
            fontWeight:'600', textAlign:'center'
          };
          const v = String(p.value || '');
          if (v === 'Sí') return Object.assign({}, base, {backgroundColor:'#E8F5E9', color:'#1B5E20'});
          if (v === 'No') return Object.assign({}, base, {backgroundColor:'#FFE0E0', color:'#B71C1C'});
          return {};
        }""")

        # al cambiar fecha, poner hora actual correspondiente
        on_cell_changed = JsCode("""
        function(params){
          const pad = n => String(n).padStart(2,'0');
          const now = new Date(); const hhmm = pad(now.getHours())+':'+pad(now.getMinutes());
          if (params.colDef.field === 'Fecha de detección'){
            params.node.setDataValue('Hora de detección', hhmm);
          }
          if (params.colDef.field === 'Fecha de corrección'){
            params.node.setDataValue('Hora de corrección', hhmm);
          }
        }""")

        # autosize para ocupar todo el ancho
        on_ready_size = JsCode("function(p){ p.api.sizeColumnsToFit(); }")
        on_first_size = JsCode("function(p){ p.api.sizeColumnsToFit(); }")

        col_defs = [
            {"field":"Id", "headerName":"Id", "editable": False, "pinned":"left", "flex":1.2, "minWidth":110},
            {"field":"Tarea", "headerName":"Tarea", "editable": False, "flex":3, "minWidth":200,
             "cellStyle": {"whiteSpace":"nowrap", "overflow":"hidden", "textOverflow":"ellipsis"}},

            {"field":"¿Generó alerta?", "headerName":"¿Generó alerta?",
             "editable": True, "cellEditor": "agSelectCellEditor",
             "cellEditorParams": {"values": ["No","Sí"]},
             "valueFormatter": si_no_formatter, "cellStyle": si_no_style_genero,
             "flex":1.2, "minWidth":140},

            {"field":"N° alerta", "headerName":"N° alerta",
             "editable": True, "cellEditor": "agSelectCellEditor",
             "cellEditorParams": {"values": ["1","2","3","+4"]},
             "flex":0.8, "minWidth":120},

            {"field":"Fecha de detección", "headerName":"Fecha de detección",
             "editable": True, "cellEditor": date_editor, "flex":1.2, "minWidth":150},

            {"field":"Hora de detección", "headerName":"Hora de detección",
             "editable": False, "flex":1.0, "minWidth":140},

            {"field":"¿Se corrigió?", "headerName":"¿Se corrigió?",
             "editable": True, "cellEditor": "agSelectCellEditor",
             "cellEditorParams": {"values": ["No","Sí"]},
             "valueFormatter": si_no_formatter, "cellStyle": si_no_style_corrigio,
             "flex":1.2, "minWidth":140},

            {"field":"Fecha de corrección", "headerName":"Fecha de corrección",
             "editable": True, "cellEditor": date_editor, "flex":1.2, "minWidth":150},

            {"field":"Hora de corrección", "headerName":"Hora de corrección",
             "editable": False, "flex":1.0, "minWidth":140},
        ]

        grid_opts = {
            "columnDefs": col_defs,
            "defaultColDef": {
                "resizable": True,
                "wrapText": False,
                "autoHeight": False,
                "minWidth": 110,
                "flex": 1
            },
            "suppressMovableColumns": True,
            "domLayout": "normal",
            "ensureDomOrder": True,
            "rowHeight": 38,
            "headerHeight": 36,
            "suppressHorizontalScroll": True,
            "onCellValueChanged": on_cell_changed,
            "onGridReady": on_ready_size,
            "onFirstDataRendered": on_first_size,
        }

        grid = AgGrid(
            df_view,
            gridOptions=grid_opts,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            fit_columns_on_grid_load=False,
            enable_enterprise_modules=False,
            reload_data=False,
            height=220,
            allow_unsafe_jscode=True,
            theme="balham",
        )

        # ===== Guardar (merge por Id en df_main) =====
        _sp, _btn = st.columns([A+Fw+T_width+D+R, C], gap="medium")
        with _btn:
            if st.button("💾 Guardar cambios", use_container_width=True):
                try:
                    df_edit = pd.DataFrame(grid["data"]).copy()
                    df_base = st.session_state.get("df_main", pd.DataFrame()).copy()

                    if df_edit.empty or "Id" not in df_edit.columns or df_base.empty or "Id" not in df_base.columns:
                        st.info("No hay cambios para guardar.")
                    else:
                        # Asegurar columnas de alerta en base
                        alert_cols = ["¿Generó alerta?","N° alerta","Fecha de detección","Hora de detección",
                                      "¿Se corrigió?","Fecha de corrección","Hora de corrección"]
                        for c in alert_cols:
                            if c not in df_base.columns:
                                df_base[c] = ""

                        cambios = 0
                        for _, row in df_edit.iterrows():
                            id_row = str(row.get("Id","")).strip()
                            if not id_row:
                                continue
                            m = df_base["Id"].astype(str).str.strip() == id_row
                            if not m.any():
                                continue

                            def _set(col_base, val):
                                v = "" if val is None else str(val).strip()
                                if v != "":
                                    df_base.loc[m, col_base] = v
                                    return 1
                                return 0

                            cambios += _set("¿Generó alerta?",     row.get("¿Generó alerta?"))
                            cambios += _set("N° alerta",           row.get("N° alerta"))
                            cambios += _set("Fecha de detección",  row.get("Fecha de detección"))
                            cambios += _set("Hora de detección",   row.get("Hora de detección"))
                            cambios += _set("¿Se corrigió?",       row.get("¿Se corrigió?"))
                            cambios += _set("Fecha de corrección", row.get("Fecha de corrección"))
                            cambios += _set("Hora de corrección",  row.get("Hora de corrección"))

                        if cambios > 0:
                            st.session_state["df_main"] = df_base.copy()
                            _save_local(df_base.copy())
                            st.success(f"✔ Cambios guardados: {cambios} actualización(es).")
                            st.rerun()
                        else:
                            st.info("No se detectaron cambios para guardar.")
                except Exception as e:
                    st.error(f"No pude guardar los cambios: {e}")

        # Cierra form-card + section-na y el contenedor local
        st.markdown('</div></div>', unsafe_allow_html=True)  # cierra .form-card y .section-na
        st.markdown('</div>', unsafe_allow_html=True)        # cierra #na-section

        # Separación vertical entre secciones
        st.markdown(f"<div style='height:{SECTION_GAP_DEF}px'></div>", unsafe_allow_html=True)
