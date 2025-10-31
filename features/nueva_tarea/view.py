# ================== Formulario (misma malla + hora inmediata) ==================

# Fallback suave si aún no existe (no altera nada cuando ya viene del módulo principal)
if "AREAS_OPC" not in globals():
    AREAS_OPC = ["Jefatura", "Gestión", "Metodología", "Base de datos", "Capacitación", "Monitoreo", "Consistencia"]

st.session_state.setdefault("nt_visible", True)
chev = "▾" if st.session_state.get("nt_visible", True) else "▸"

# ---------- Barra superior ----------
st.markdown('<div id="ntbar" class="topbar">', unsafe_allow_html=True)
c_toggle, c_pill = st.columns([0.028, 0.965], gap="medium")
with c_toggle:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_nt():
        st.session_state["nt_visible"] = not st.session_state.get("nt_visible", True)
    st.button(chev, key="nt_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_nt)
    st.markdown('</div>', unsafe_allow_html=True)
with c_pill:
    st.markdown('<div class="form-title">&nbsp;&nbsp;📝&nbsp;&nbsp;Nueva tarea</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state.get("nt_visible", True):

    # ===== Scope local para NO afectar otras secciones =====
    st.markdown('<div id="nt-section">', unsafe_allow_html=True)

    # ===== Indicaciones cortas (debajo de la píldora) =====
    st.markdown("""
    <div class="help-strip">
      ✳️ Completa: <strong>Área, Fase, Tarea, Responsable y Fecha</strong>. La hora es automática.
    </div>
    """, unsafe_allow_html=True)

    # ===== ESPACIADOR entre indicaciones y el card =====
    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

    submitted = False

    # ===== Card REAL que envuelve TODAS las celdas =====
    with st.container(border=True):
        # Sentinel para limitar estilos SOLO a este card
        st.markdown('<span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

        # CSS mínimo SOLO para inputs al 100% dentro de este card
        st.markdown("""
        <style>
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea{
            width:100% !important;
          }
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput > div,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea > div{
            width:100% !important; max-width:none !important;
          }
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid="stDateInput"] input,
          div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid^="stTimeInput"] input{
            width:100% !important;
          }
        </style>
        """, unsafe_allow_html=True)

        # Proporciones (tus originales)
        A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

        # ---------- FILA 1 ----------
        r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
        area = r1c1.selectbox("Área", options=AREAS_OPC, index=0, key="nt_area")
        FASES = ["Capacitación","Post-capacitación","Pre-consistencia","Consistencia","Operación de campo"]
        fase   = r1c2.selectbox("Fase", options=FASES, index=None, placeholder="Selecciona una fase", key="nt_fase")
        tarea  = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
        detalle= r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
        resp   = r1c5.text_input("Responsable", placeholder="Nombre", key="nt_resp")
        ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")

        # ---------- FILA 2 ----------
        c2_1, c2_2, c2_3, c2_4, c2_5, c2_6 = st.columns([A, Fw, T, D, R, C], gap="medium")
        tipo   = c2_1.text_input("Tipo de tarea", placeholder="Tipo o categoría", key="nt_tipo")

        # Estado fijo (sin lista): siempre "No iniciado"
        with c2_2:
            st.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")
        estado = "No iniciado"

        # --- FECHA/HORA: corrección para evitar None en date_input ---
        # Limpia claves inválidas antes de crear el widget (Streamlit no acepta None para date_input si la clave ya existe)
        if st.session_state.get("fi_d", "___MISSING___") is None:
            st.session_state.pop("fi_d")
        if st.session_state.get("fi_t", "___MISSING___") is None:
            st.session_state.pop("fi_t")

        # Fecha editable + callback inmediato (pone hora al elegir fecha)
        c2_3.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)

        # Hora auto (solo lectura)
        _t = st.session_state.get("fi_t"); _t_txt = ""
        if _t is not None:
            try:
                _t_txt = _t.strftime("%H:%M")
            except Exception:
                _t_txt = str(_t)
        c2_4.text_input("Hora (auto)", value=_t_txt, disabled=True,
                        help="Se asigna al elegir la fecha", key="fi_t_view")

        # ID preview
        _df_tmp = st.session_state.get("df_main", pd.DataFrame()).copy() if "df_main" in st.session_state else pd.DataFrame()
        prefix = make_id_prefix(st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp))
        if st.session_state.get("fi_d"):
            id_preview = next_id_by_person(_df_tmp, st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp))
        else:
            id_preview = f"{prefix}_" if prefix else ""
        c2_5.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

        # Botón
        with c2_6:
            st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
            submitted = st.button("➕ Agregar", use_container_width=True, key="btn_agregar")

    # Cierra scope local
    st.markdown("</div>", unsafe_allow_html=True)  # cierra #nt-section

    # ---------- Guardado ----------
    if submitted:
        try:
            df = st.session_state.get("df_main", pd.DataFrame()).copy()

            def _sanitize(df_in: pd.DataFrame, target_cols=None) -> pd.DataFrame:
                df_out = df_in.copy()
                if "DEL" in df_out.columns and "__DEL__" in df_out.columns:
                    df_out["__DEL__"] = df_out["__DEL__"].fillna(False) | df_out["DEL"].fillna(False)
                    df_out = df_out.drop(columns=["DEL"])
                elif "DEL" in df_out.columns:
                    df_out = df_out.rename(columns={"DEL": "__DEL__"})
                df_out = df_out.loc[:, ~pd.Index(df_out.columns).duplicated()].copy()
                if not df_out.index.is_unique:
                    df_out = df_out.reset_index(drop=True)
                if target_cols:
                    target = list(dict.fromkeys(list(target_cols)))
                    for c in target:
                        if c not in df_out.columns:
                            df_out[c] = None
                    ordered = [c for c in target] + [c for c in df_out.columns if c not in target]
                    df_out = df_out.loc[:, ordered].copy()
                return df_out

            df = _sanitize(df, COLS if "COLS" in globals() else None)

            # Armamos HH:MM seguro para registro
            reg_fecha = st.session_state.get("fi_d")
            reg_hora_obj = st.session_state.get("fi_t")
            try:
                reg_hora_txt = reg_hora_obj.strftime("%H:%M") if reg_hora_obj is not None else ""
            except Exception:
                reg_hora_txt = str(reg_hora_obj) if reg_hora_obj is not None else ""

            new = blank_row()
            new.update({
                "Área": area,
                "Id": next_id_by_person(df, area, st.session_state.get("nt_resp", "")),
                "Tarea": st.session_state.get("nt_tarea", ""),
                "Tipo": st.session_state.get("nt_tipo", ""),
                "Responsable": st.session_state.get("nt_resp", ""),
                "Fase": fase,
                "Estado": estado,                   # ← fijo: No iniciado
                # Marcas de REGISTRO que pide el historial
                "Fecha": reg_fecha,                 # respaldo simple (fallback)
                "Hora": reg_hora_txt,               # respaldo simple (fallback)
                "Fecha Registro": reg_fecha,        # registro explícito
                "Hora Registro": reg_hora_txt,      # registro explícito
                # Campos de inicio/fin (se llenan más adelante)
                "Fecha inicio": None,
                "Hora de inicio": "",
                "Fecha Terminado": None,
                "Hora Terminado": "",
                # Otros
                "Ciclo de mejora": ciclo_mejora,
                "Detalle": st.session_state.get("nt_detalle", ""),
            })

            df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)

            df = _sanitize(df, COLS if "COLS" in globals() else None)
            st.session_state["df_main"] = df.copy()
            os.makedirs("data", exist_ok=True)
            df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig", mode="w")

            st.success(f"✔ Tarea agregada (Id {new['Id']}).")
            st.rerun()
        except Exception as e:
            st.error(f"No pude guardar la nueva tarea: {e}")

# Separación vertical
st.markdown(f"<div style='height:{SECTION_GAP if 'SECTION_GAP' in globals() else 30}px;'></div>", unsafe_allow_html=True)



# ================== EDITAR ESTADO (mismo layout que "Nueva alerta") ==================
st.session_state.setdefault("est_visible", True)
chev_est = "▾" if st.session_state["est_visible"] else "▸"

# ---------- Barra superior ----------
st.markdown('<div class="topbar-eval">', unsafe_allow_html=True)
c_est_toggle, c_est_pill = st.columns([0.028, 0.965], gap="medium")
with c_est_toggle:
    st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)
    def _toggle_est():
        st.session_state["est_visible"] = not st.session_state["est_visible"]
    st.button(chev_est, key="est_toggle_icon_v3", help="Mostrar/ocultar", on_click=_toggle_est)
    st.markdown('</div>', unsafe_allow_html=True)
with c_est_pill:
    st.markdown('<div class="form-title">&nbsp;&nbsp;✏️&nbsp;&nbsp;Editar estado</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
# ---------- fin barra superior ----------

if st.session_state["est_visible"]:

    # --- Contenedor + CSS local ---
    st.markdown('<div id="est-section">', unsafe_allow_html=True)
    st.markdown("""
    <style>
      #est-section .stButton > button { width: 100% !important; }
      #est-section .ag-header-cell-label{ font-weight: 400 !important; }
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

        # Responsable (dependiente de área/fase si existen)
        df_resp_src = df_all.copy()
        if est_area != "Todas" and "Área" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Área"].astype(str) == est_area]
        if est_fase != "Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == est_fase]
        responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        est_resp = c_resp.selectbox("Responsable", ["Todos"] + responsables_all, index=0)

        # Rango de fechas (opcional) — sin value=None (rompe)
        use_date_range = c_buscar.checkbox("Filtrar por fechas", value=False)
        if use_date_range:
            est_desde = c_desde.date_input("Desde")
            est_hasta = c_hasta.date_input("Hasta")
        else:
            est_desde, est_hasta = None, None
            # Mostrar labels “apagados” para mantener la malla
            with c_desde:
                st.caption("Desde")
                st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)
            with c_hasta:
                st.caption("Hasta")
                st.markdown("<div style='height:38px;border:1px dashed #e5e7eb;border-radius:8px;'></div>", unsafe_allow_html=True)

        with c_buscar:
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
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
        if use_date_range and "Fecha inicio" in df_tasks.columns:
            fcol = pd.to_datetime(df_tasks["Fecha inicio"], errors="coerce")
            if est_desde:
                df_tasks = df_tasks[fcol >= pd.to_datetime(est_desde)]
            if est_hasta:
                # incluir todo el día de "hasta"
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

        # Respetar valores existentes en "Fecha/Hora estado actual" si no están vacíos
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
        headerHeight=42,
        suppressHorizontalScroll=True
    )
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
    gob.configure_column("Fecha estado modificado", editable=True, cellEditor=date_editor, minWidth=160)
    gob.configure_column("Hora estado modificado",  editable=False, minWidth=140)

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

    # ===== Guardar cambios (actualiza la MISMA fila por Id) =====
    u1, u2 = st.columns([A+Fw+T_width+D+R, C], gap="medium")
    with u2:
        if st.button("💾 Guardar cambios", use_container_width=True, key="est_guardar_inline_v3"):
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
                        os.makedirs("data", exist_ok=True)
                        base.to_csv(os.path.join("data","tareas.csv"), index=False, encoding="utf-8-sig")
                        st.success("Cambios guardados. *Tareas recientes* se actualizará automáticamente.")
                        st.rerun()
            except Exception as e:
                st.error(f"No pude guardar: {e}")

    # Cerrar form-card + section + contenedor
    st.markdown('</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
