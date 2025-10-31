# =========================== PRIORIDAD ===============================

st.session_state.setdefault("pri_visible", True)
chev_pri = "▾" if st.session_state["pri_visible"] else "▸"

# ---------- Barra superior ----------
st.markdown('<div class="topbar-pri">', unsafe_allow_html=True)
c_toggle_p, c_pill_p = st.columns([0.028, 0.965], gap="medium")
with c_toggle_p:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_pri():
        st.session_state["pri_visible"] = not st.session_state["pri_visible"]
    st.button(chev_pri, key="pri_toggle_v2", help="Mostrar/ocultar", on_click=_toggle_pri)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill_p:
    st.markdown('<div class="form-title-pri">🧭&nbsp;&nbsp;Prioridad</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["pri_visible"]:

    # --- contenedor local + css ---
    st.markdown('<div id="pri-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #pri-section .stButton > button { width: 100% !important; }
      .section-pri .help-strip-pri + .form-card{ margin-top: 6px !important; }

      /* Evita efectos colaterales: solo dentro de PRIORIDAD */
      #pri-section .ag-body-horizontal-scroll,
      #pri-section .ag-center-cols-viewport { overflow-x: auto !important; }

      /* Header visible (altura fija) */
      #pri-section .ag-theme-alpine .ag-header,
      #pri-section .ag-theme-streamlit .ag-header{
        height: 44px !important; min-height: 44px !important;
      }

      /* Encabezados más livianos */
      #pri-section .ag-theme-alpine{ --ag-font-weight: 400; }
      #pri-section .ag-theme-streamlit{ --ag-font-weight: 400; }

      #pri-section .ag-theme-alpine .ag-header-cell-label,
      #pri-section .ag-theme-alpine .ag-header-cell-text,
      #pri-section .ag-theme-alpine .ag-header *:not(.ag-icon),
      #pri-section .ag-theme-streamlit .ag-header-cell-label,
      #pri-section .ag-theme-streamlit .ag-header-cell-text,
      #pri-section .ag-theme-streamlit .ag-header *:not(.ag-icon){
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Inter", "Helvetica Neue", Arial, sans-serif !important;
        font-weight: 400 !important;             /* normal */
        font-synthesis-weight: none !important;  /* sin negrita sintética */
        color: #1f2937 !important;
        opacity: 1 !important;
        visibility: visible !important;
      }

      /* Colores para prioridad (por clase) */
      #pri-section .pri-low   { color:#2563eb !important; }  /* 🔵 Baja */
      #pri-section .pri-med   { color:#ca8a04 !important; }  /* 🟡 Media */
      #pri-section .pri-high  { color:#dc2626 !important; }  /* 🔴 Alta */
    </style>
    """, unsafe_allow_html=True)


    # ===== Wrapper UNIDO: help-strip + form-card =====
    st.markdown("""
    <div class="section-pri">
      <div class="help-strip help-strip-pri" id="pri-help">
        🧭 <strong>Asigna o edita prioridades</strong> para varias tareas a la vez (solo jefatura)
      </div>
      <div class="form-card">
    """, unsafe_allow_html=True)

    # Proporciones
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
    if df_all.empty:
        df_all = pd.DataFrame(columns=["Id","Área","Fase","Responsable","Tarea","Fecha inicio","Prioridad"])

    # Asegurar columna Prioridad con default Media
    if "Prioridad" not in df_all.columns:
        df_all["Prioridad"] = "Media"
    df_all["Prioridad"] = df_all["Prioridad"].fillna("Media").replace({"": "Media"})

    # ===== FILTROS =====
    with st.form("pri_filtros_v2", clear_on_submit=False):
        c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

        AREAS_OPC = st.session_state.get(
            "AREAS_OPC",
            ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
        )
        pri_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0, key="pri_area")

        fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        pri_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="pri_fase")

        # Multiselección de responsables
        df_resp_src = df_all.copy()
        if pri_area != "Todas":
            df_resp_src = df_resp_src[df_resp_src.get("Área","").astype(str) == pri_area]
        if pri_fase != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == pri_fase]

        responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        pri_resp = c_resp.multiselect("Responsable", options=responsables_all, default=[], placeholder="Selecciona responsable(s)")

        # 🔁 Rango de fechas opcional (sin value=None)
        use_date_range = c_buscar.checkbox("Filtrar por fechas", value=False, key="pri_use_dates")
        if use_date_range:
            pri_desde = c_desde.date_input("Desde", key="pri_desde")
            pri_hasta = c_hasta.date_input("Hasta",  key="pri_hasta")
        else:
            pri_desde = pri_hasta = None
            with c_desde:
                st.caption("Desde")
                st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)
            with c_hasta:
                st.caption("Hasta")
                st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)

        with c_buscar:
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            pri_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

    # ===== Filtrado para la tabla =====
    df_filtrado = df_all.copy()
    if pri_do_buscar:
        if pri_area != "Todas":
            df_filtrado = df_filtrado[df_filtrado.get("Área","").astype(str) == pri_area]
        if pri_fase != "Todas" and "Fase" in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == pri_fase]
        if pri_resp:
            df_filtrado = df_filtrado[df_filtrado.get("Responsable","").astype(str).isin(pri_resp)]

        base_fecha_col = "Fecha inicio" if "Fecha inicio" in df_filtrado.columns else None
        if base_fecha_col:
            fcol = pd.to_datetime(df_filtrado[base_fecha_col], errors="coerce")
            if pri_desde is not None:
                df_filtrado = df_filtrado[fcol >= pd.to_datetime(pri_desde)]
            if pri_hasta is not None:
                df_filtrado = df_filtrado[fcol <= (pd.to_datetime(pri_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

    st.markdown("**Resultados**")

    # ===== DataFrame para la grilla (con columnas aunque esté vacío) =====
    cols_out = ["Id", "Responsable", "Tarea", "Prioridad actual", "Prioridad a ajustar"]
    if df_filtrado.empty:
        df_view = pd.DataFrame({c: pd.Series(dtype="str") for c in cols_out})
    else:
        tmp = df_filtrado.copy()
        for need in ["Id","Responsable","Tarea","Prioridad"]:
            if need not in tmp.columns:
                tmp[need] = ""
        prior_actual = tmp["Prioridad"].fillna("Media").replace({"": "Media"})
        df_view = pd.DataFrame({
            "Id": tmp["Id"].astype(str),
            "Responsable": tmp["Responsable"].astype(str).replace({"nan": ""}),
            "Tarea": tmp["Tarea"].astype(str).replace({"nan": ""}),
            "Prioridad actual": prior_actual.astype(str),
            "Prioridad a ajustar": prior_actual.astype(str)
        })[cols_out].copy()

    # ====== AG-GRID con columnDefs explícitos (muestra encabezados aunque no haya filas) ======
    from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode

    PRI_OPC_SHOW = ["🔵 Baja","🟡 Media","🔴 Alta"]
    PRI_MAP_TO_TEXT = {"🔵 Baja":"Baja","🟡 Media":"Media","🔴 Alta":"Alta",
                       "Baja":"Baja","Media":"Media","Alta":"Alta"}

    # Reglas de color sin JS (expresiones)
    cell_class_rules = {
        "pri-low":  "value == '🔵 Baja' || value == 'Baja'",
        "pri-med":  "value == '🟡 Media' || value == 'Media'",
        "pri-high": "value == '🔴 Alta' || value == 'Alta'",
    }

    col_defs = [
        {"field":"Id", "headerName":"ID", "editable": False, "flex":1.0, "minWidth":110},
        {"field":"Responsable", "headerName":"Responsable", "editable": False, "flex":1.6, "minWidth":160},
        {"field":"Tarea", "headerName":"Tarea", "editable": False, "flex":2.4, "minWidth":240,
         "wrapText": True, "autoHeight": True},
        {"field":"Prioridad actual", "headerName":"Prioridad actual", "editable": False,
         "flex":1.2, "minWidth":160, "cellClassRules": cell_class_rules},
        {"field":"Prioridad a ajustar", "headerName":"Prioridad a ajustar", "editable": True,
         "cellEditor":"agSelectCellEditor", "cellEditorParams":{"values": PRI_OPC_SHOW},
         "flex":1.2, "minWidth":180, "cellClassRules": cell_class_rules},
    ]

    grid_opts = {
        "columnDefs": col_defs,
        "defaultColDef": {
            "resizable": True,
            "wrapText": True,
            "autoHeight": True,
            "minWidth": 120,
            "flex": 1
        },
        "suppressMovableColumns": True,
        "domLayout": "normal",
        "ensureDomOrder": True,
        "rowHeight": 38,
        "headerHeight": 44,
        "suppressHorizontalScroll": True
    }

    # Encabezado más liviano DENTRO del iframe
    custom_css_pri = {
        ".ag-header-cell-text": {"font-weight": "500 !important"},
        ".ag-header-group-cell-label": {"font-weight": "500 !important"},
        ".ag-header-cell-label": {"font-weight": "500 !important"},
        ".ag-header": {"font-weight": "500 !important"},
    }

    grid_pri = AgGrid(
        df_view,
        gridOptions=grid_opts,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        fit_columns_on_grid_load=False,   # las columnas llenan por flex
        enable_enterprise_modules=False,
        reload_data=False,
        height=220,
        theme="alpine",
        custom_css=custom_css_pri,        # encabezado más liviano
        key="grid_prioridad",             # KEY ÚNICO
    )

    # ===== Guardar (actualiza Prioridad en df_main) =====
    _sp_pri, _btn_pri = st.columns([A+Fw+T_width+D+R, C], gap="medium")
    with _btn_pri:
        do_save_pri = st.button("🧭 Dar prioridad", use_container_width=True, key="pri_guardar_v1")

    if do_save_pri:
        try:
            edited = pd.DataFrame(grid_pri.get("data", []))
            if edited.empty:
                st.info("No hay filas para actualizar.")
            else:
                df_base = st.session_state.get("df_main", pd.DataFrame()).copy()
                if "Prioridad" not in df_base.columns:
                    df_base["Prioridad"] = "Media"

                cambios = 0
                for _, row in edited.iterrows():
                    id_row = str(row.get("Id", "")).strip()
                    if not id_row:
                        continue
                    valor_ui = str(row.get("Prioridad a ajustar", "Media")).strip()
                    nuevo = PRI_MAP_TO_TEXT.get(valor_ui, "Media")  # guardamos sin emoji
                    m = df_base["Id"].astype(str).str.strip() == id_row
                    if m.any():
                        df_base.loc[m, "Prioridad"] = nuevo
                        cambios += 1

                if cambios > 0:
                    st.session_state["df_main"] = df_base.copy()
                    _save_local(df_base.copy())
                    st.success(f"✔ Prioridades actualizadas: {cambios} fila(s).")
                    st.rerun()
                else:
                    st.info("No se detectaron cambios para guardar.")
        except Exception as e:
            st.error(f"No pude guardar los cambios de prioridad: {e}")

    # Cerrar wrappers
    st.markdown('</div></div>', unsafe_allow_html=True)  # cierra .form-card y .section-pri
    st.markdown('</div>', unsafe_allow_html=True)        # cierra #pri-section

    # Separación vertical
    st.markdown(f"<div style='height:{SECTION_GAP}px'></div>", unsafe_allow_html=True)
