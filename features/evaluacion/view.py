# =========================== EVALUACIÓN ===============================
st.session_state.setdefault("eva_visible", True)
chev_eva = "▾" if st.session_state["eva_visible"] else "▸"

# ---------- Barra superior ----------
st.markdown('<div class="topbar-eval">', unsafe_allow_html=True)
c_toggle_e, c_pill_e = st.columns([0.028, 0.965], gap="medium")
with c_toggle_e:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_eva():
        st.session_state["eva_visible"] = not st.session_state["eva_visible"]
    st.button(chev_eva, key="eva_toggle_v2", help="Mostrar/ocultar", on_click=_toggle_eva)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill_e:
    st.markdown('<div class="form-title-eval">📝&nbsp;&nbsp;Evaluación</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["eva_visible"]:

    # --- contenedor local + css (botón, headers 600, colores y estrellas) ---
    st.markdown('<div id="eva-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #eva-section .stButton > button { width: 100% !important; }
      .section-eva .help-strip-eval + .form-card{ margin-top: 6px !important; }

      /* overflow horizontal visible SOLO aquí */
      #eva-section .ag-body-horizontal-scroll,
      #eva-section .ag-center-cols-viewport { overflow-x: auto !important; }

      /* headers más marcados SOLO aquí */
      #eva-section .ag-header .ag-header-cell-text{ font-weight: 600 !important; }

      /* clases de color por estado */
      #eva-section .eva-ok  { color:#16a34a !important; }
      #eva-section .eva-bad { color:#dc2626 !important; }
      #eva-section .eva-obs { color:#d97706 !important; }
    </style>
    """, unsafe_allow_html=True)

    # ===== Wrapper UNIDO: help-strip + form-card =====
    st.markdown("""
    <div class="section-eva">
      <div class="help-strip help-strip-eval" id="eva-help">
        📝 <strong>Registra/actualiza la evaluación</strong> de tareas filtradas.
      </div>
      <div class="form-card">
    """, unsafe_allow_html=True)

    # Anchos (consistentes)
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
    if df_all.empty:
        df_all = pd.DataFrame(columns=["Id","Área","Fase","Responsable","Tarea","Fecha inicio","Evaluación","Calificación"])

    # Asegura columnas base
    if "Evaluación" not in df_all.columns:
        df_all["Evaluación"] = "Sin evaluar"
    df_all["Evaluación"] = df_all["Evaluación"].fillna("Sin evaluar").replace({"": "Sin evaluar"})
    if "Calificación" not in df_all.columns:
        df_all["Calificación"] = 0
    df_all["Calificación"] = pd.to_numeric(df_all["Calificación"], errors="coerce").fillna(0).astype(int).clip(0,5)

    # ===== FILTROS =====
    with st.form("eva_filtros_v2", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

        AREAS_OPC = st.session_state.get(
            "AREAS_OPC",
            ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
        )
        eva_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0, key="eva_area")

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        eva_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="eva_fase")

        # Responsable MULTISELECCIÓN
        df_resp_src = df_all.copy()
        if eva_area != "Todas":
            df_resp_src = df_resp_src[df_resp_src.get("Área","").astype(str) == eva_area]
        if eva_fase != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == eva_fase]
        responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        eva_resp = c_resp.multiselect("Responsable", options=responsables_all, default=[], placeholder="Selecciona responsable(s)")

        # 🔁 Rango de fechas opcional
        use_date_range = c_buscar.checkbox("Filtrar por fechas", value=False, key="eva_use_dates")
        if use_date_range:
            eva_desde = c_desde.date_input("Desde", key="eva_desde")
            eva_hasta = c_hasta.date_input("Hasta",  key="eva_hasta")
        else:
            eva_desde = eva_hasta = None
            with c_desde:
                st.caption("Desde")
                st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)
            with c_hasta:
                st.caption("Hasta")
                st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)

        with c_buscar:
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            eva_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado para tabla =====
    df_filtrado = df_all.copy()
    if eva_do_buscar:
        if eva_area != "Todas":
            df_filtrado = df_filtrado[df_filtrado.get("Área","").astype(str) == eva_area]
        if eva_fase != "Todas" and "Fase" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == eva_fase]
        if eva_resp:
            df_filtrado = df_filtrado[df_filtrado.get("Responsable","").astype(str).isin(eva_resp)]
        base_fecha_col = "Fecha inicio" if "Fecha inicio" in df_filtrado.columns else None
        if base_fecha_col:
            fcol = pd.to_datetime(df_filtrado[base_fecha_col], errors="coerce")
            if use_date_range and (eva_desde is not None):
                df_filtrado = df_filtrado[fcol >= pd.to_datetime(eva_desde)]
            if use_date_range and (eva_hasta is not None):
                df_filtrado = df_filtrado[fcol <= (pd.to_datetime(eva_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    # ===== Tabla de Evaluación =====
    st.markdown("**Resultados**")

    # Mapeos de evaluación (con/sin emoji)
    EVA_OPC_SHOW = ["Sin evaluar", "🟢 Aprobado", "🔴 Desaprobado", "🟠 Observado"]
    EVA_TO_TEXT = {
        "🟢 Aprobado":"Aprobado", "🔴 Desaprobado":"Desaprobado", "🟠 Observado":"Observado",
        "Aprobado":"Aprobado","Desaprobado":"Desaprobado","Observado":"Observado",
        "Sin evaluar":"Sin evaluar","":"Sin evaluar"
    }
    TEXT_TO_SHOW = {"Aprobado":"🟢 Aprobado","Desaprobado":"🔴 Desaprobado","Observado":"🟠 Observado","Sin evaluar":"Sin evaluar"}

    cols_out = ["Id", "Responsable", "Tarea", "Evaluación actual", "Evaluación ajustada", "Calificación"]
    if df_filtrado.empty:
        df_view = pd.DataFrame({c: pd.Series(dtype="str") for c in cols_out})
    else:
        tmp = df_filtrado.dropna(subset=["Id"]).copy()
        for need in ["Responsable","Tarea","Evaluación","Calificación"]:
            if need not in tmp.columns:
                tmp[need] = ""
        eva_actual_txt = tmp["Evaluación"].fillna("Sin evaluar").replace({"": "Sin evaluar"}).astype(str)
        eva_ajustada_show = eva_actual_txt.apply(lambda v: TEXT_TO_SHOW.get(v, "Sin evaluar"))
        calif = pd.to_numeric(tmp.get("Calificación", 0), errors="coerce").fillna(0).astype(int).clip(0,5)

        df_view = pd.DataFrame({
            "Id": tmp["Id"].astype(str),
            "Responsable": tmp["Responsable"].astype(str).replace({"nan": ""}),
            "Tarea": tmp["Tarea"].astype(str).replace({"nan": ""}),
            "Evaluación actual": eva_actual_txt,
            "Evaluación ajustada": eva_ajustada_show,
            "Calificación": calif
        })[cols_out].copy()

    from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

    # Reglas de color
    eva_cell_rules = {
        "eva-ok":  "value == '🟢 Aprobado' || value == 'Aprobado'",
        "eva-bad": "value == '🔴 Desaprobado' || value == 'Desaprobado'",
        "eva-obs": "value == '🟠 Observado' || value == 'Observado'",
    }

    # Estrellas (0..5)
    stars_fmt = JsCode("""
      function(p){
        var n = parseInt(p.value||0);
        if (isNaN(n) || n < 0) n = 0;
        if (n > 5) n = 5;
        return '★'.repeat(n) + '☆'.repeat(5-n);
      }
    """)

    gob = GridOptionsBuilder.from_dataframe(df_view)
    gob.configure_default_column(resizable=True, wrapText=True, autoHeight=True, minWidth=120, flex=1)
    gob.configure_grid_options(
        suppressMovableColumns=True, domLayout="normal", ensureDomOrder=True,
        rowHeight=38, headerHeight=44, suppressHorizontalScroll=True
    )

    # Lectura
    for ro in ["Id", "Responsable", "Tarea", "Evaluación actual"]:
        gob.configure_column(ro, editable=False, cellClassRules=eva_cell_rules if ro=="Evaluación actual" else None)

    # Editable: Evaluación ajustada
    gob.configure_column(
        "Evaluación ajustada",
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": EVA_OPC_SHOW},
        cellClassRules=eva_cell_rules,
        flex=1.4, minWidth=180
    )

    # Editable: Calificación (0..5) + estrellas
    gob.configure_column(
        "Calificación",
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": [0,1,2,3,4,5]},
        valueFormatter=stars_fmt,
        flex=1.1, minWidth=160
    )

    # Ajuste flex
    gob.configure_column("Id",            flex=1.0, minWidth=110)
    gob.configure_column("Responsable",   flex=1.6, minWidth=160)
    gob.configure_column("Tarea",         flex=2.4, minWidth=260)
    gob.configure_column("Evaluación actual", flex=1.3, minWidth=160)

    # CSS dentro del iframe de AgGrid
    custom_css_eval = {
        ".ag-header-cell-text": {"font-weight": "600 !important"},
        ".ag-header-cell-label": {"font-weight": "600 !important"},
        ".ag-header-group-cell-label": {"font-weight": "600 !important"},
        ".ag-theme-alpine": {"--ag-font-weight": "600"},
        ".ag-header": {"font-synthesis-weight": "none !important"},

        ".eva-ok":  {"color": "#16a34a !important"},
        ".eva-bad": {"color": "#dc2626 !important"},
        ".eva-obs": {"color": "#d97706 !important"},
    }

    grid_eval = AgGrid(
        df_view,
        gridOptions=gob.build(),
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=False,   # usamos flex
        enable_enterprise_modules=False,
        allow_unsafe_jscode=True,
        reload_data=False,
        theme="alpine",
        height=300,
        custom_css=custom_css_eval,
        key="grid_evaluacion",  # KEY ÚNICO
    )

    # ===== Guardar cambios (merge por Id en df_main) =====
    _sp_eva, _btn_eva = st.columns([A+Fw+T_width+D+R, C], gap="medium")
    with _btn_eva:
        do_save_eva = st.button("💾 Guardar evaluación", use_container_width=True, key="eva_guardar_v1")

    if do_save_eva:
        try:
            edited = pd.DataFrame(grid_eval.get("data", []))
            if edited.empty or "Id" not in edited.columns:
                st.info("No hay filas para actualizar.")
            else:
                df_base = st.session_state.get("df_main", pd.DataFrame()).copy()
                if df_base.empty:
                    st.warning("No hay base para actualizar.")
                else:
                    # Asegurar columnas
                    if "Evaluación" not in df_base.columns:
                        df_base["Evaluación"] = "Sin evaluar"
                    if "Calificación" not in df_base.columns:
                        df_base["Calificación"] = 0

                    cambios = 0
                    for _, row in edited.iterrows():
                        id_row = str(row.get("Id","")).strip()
                        if not id_row:
                            continue
                        m = df_base["Id"].astype(str).str.strip() == id_row
                        if not m.any():
                            continue

                        # Mapear evaluación con/sin emoji -> texto limpio
                        eva_ui = str(row.get("Evaluación ajustada", "Sin evaluar")).strip()
                        eva_new = EVA_TO_TEXT.get(eva_ui, "Sin evaluar")

                        # Calificación segura 0..5
                        cal_new = row.get("Calificación", 0)
                        try:
                            cal_new = int(cal_new)
                        except Exception:
                            cal_new = 0
                        cal_new = max(0, min(5, cal_new))

                        # Aplicar
                        prev_eva = df_base.loc[m, "Evaluación"].iloc[0] if m.any() else None
                        prev_cal = df_base.loc[m, "Calificación"].iloc[0] if m.any() else None

                        if eva_new != prev_eva:
                            df_base.loc[m, "Evaluación"] = eva_new
                            cambios += 1
                        if cal_new != prev_cal:
                            df_base.loc[m, "Calificación"] = cal_new
                            cambios += 1

                    if cambios > 0:
                        st.session_state["df_main"] = df_base.copy()
                        _save_local(df_base.copy())
                        st.success(f"✔ Evaluaciones actualizadas: {cambios} cambio(s).")
                        st.rerun()
                    else:
                        st.info("No se detectaron cambios para guardar.")
        except Exception as e:
            st.error(f"No pude guardar la evaluación: {e}")

    # Cerrar wrappers
    st.markdown('</div></div>', unsafe_allow_html=True)  # cierra .form-card y .section-eva
    st.markdown('</div>', unsafe_allow_html=True)        # cierra #eva-section

    # Separación vertical
    st.markdown(f"<div style='height:{SECTION_GAP}px'></div>", unsafe_allow_html=True)
