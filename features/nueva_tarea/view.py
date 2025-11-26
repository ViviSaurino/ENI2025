def render_nueva_tarea(user: dict | None = None):
    """Vista: ➕ Nueva tarea (parte superior)"""

    # ===== CSS =====
    st.markdown(
        """
    <style>
    /* ===== Quitar la “hoja” blanca gigante del centro ===== */
    section.main{
        background-color: transparent !important;
    }
    div[data-testid="block-container"]{
        background-color: transparent !important;
        box-shadow: none !important;
        border: none !important;
    }
    div[data-testid="block-container"] > div{
        background-color: transparent !important;
        box-shadow: none !important;
    }

    /* Ocultar el caption automático de Streamlit */
    section.main div[data-testid="stCaptionContainer"]:first-of-type{
        display:none !important;
    }

    /* ===== Banner superior NUEVA TAREA ===== */
    .nt-hero-wrapper{
      margin-left:0px;
      margin-right:0px;
      margin-top:-50px;
      margin-bottom:0;
    }
    .nt-hero{
      border-radius:8px;
      background:linear-gradient(90deg,#93C5FD 0%,#A855F7 100%);
      padding:10px 32px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      color:#FFFFFF;
      box-shadow:none;
    }
    .nt-hero-left{
      display:flex;
      flex-direction:column;
      gap:4px;
    }
    .nt-hero-title{
      font-size:1.8rem;
      font-weight:700;
    }
    .nt-hero-right{
      flex:0 0 auto;
      display:flex;
      align-items:flex-end;
      justify-content:flex-end;
      padding-left:24px;
    }
    .nt-hero-img{
      display:block;
      height:160px;
      max-width:160px;
      transform: translateY(10px);
    }

    /* ===== Card del formulario (máx. 5 celdas por fila) ===== */
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel){
        background: transparent !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 20px 0 22px 0;
        margin-top: 16px;
        margin-bottom: 10px;
        border-top: 1px solid #E5E7EB !important;
        border-bottom: 1px solid #E5E7EB !important;
        border-left: none !important;
        border-right: none !important;
        margin-left: 8px;
        margin-right: 24px;
    }

    /* Inputs full width dentro del card */
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea{
      width:100% !important;
    }
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea>div{
      width:100% !important;
      max-width:none !important;
    }

    /* Tarjetas de pasos */
    .nt-steps-row{
      display:flex;
      flex-wrap:wrap;
      gap:12px;
      margin-top:4px;
      margin-bottom:16px;
    }
    .nt-step-card{
      flex:1 1 180px;
      min-width:180px;
      background:#FFFFFF;
      border-radius:8px;
      border:1px solid #E5E7EB;
      padding:20px 20px;
      min-height:70px;
      box-shadow:none;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:12px;
    }
    .nt-step-main{
      flex:1;
      display:flex;
      flex-direction:column;
      justify-content:center;
      align-items:flex-start;
      text-align:left;
    }
    .nt-step-label{
      font-size:0.88rem;
      font-weight:400;
      color:#111827;
      white-space: nowrap;
    }
    .nt-step-icon-slot{
      flex:0 0 auto;
      display:flex;
      align-items:center;
      justify-content:center;
    }
    .nt-step-icon{
      width:32px;
      height:32px;
      border-radius:10px;
      display:flex;
      align-items:center;
      justify-content:center;
      background: transparent;
      font-size:1.8rem;
      flex-shrink:0;
    }

    /* Botones */
    .nt-outbtn .stButton>button{
      min-height:38px !important;
      height:38px !important;
      border-radius:10px !important;
    }
    .nt-outbtn{
      margin-top: 6px;
    }

    /* Quitar rectángulo interno del form */
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel)
        > div[data-testid="stForm"],
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel)
        > form[data-testid="stForm"]{
        background: transparent !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        border: none !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
    }
    </style>
        """,
        unsafe_allow_html=True,
    )

    # ===== Datos =====
    if "AREAS_OPC" not in globals():
        globals()["AREAS_OPC"] = [
            "Jefatura",
            "Gestión",
            "Metodología",
            "Base de datos",
            "Capacitación",
            "Monitoreo",
            "Consistencia",
        ]
    st.session_state.setdefault("nt_visible", True)

    if st.session_state.get("nt_tipo", "").strip().lower() == "otros":
        st.session_state["nt_tipo"] = ""
    else:
        st.session_state.setdefault("nt_tipo", "")

    _NT_SPACE = 35
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # 👉 5 columnas iguales (mismo “ritmo” que las 5 tarjetas)
    COLS5 = [1, 1, 1, 1, 1]

    # ===== Banner superior “Nueva tarea” =====
    hero_b64 = _hero_img_base64()
    if hero_b64:
        hero_img_html = f'<img src="data:image/png;base64,{hero_b64}" alt="Nueva tarea" class="nt-hero-img">'
    else:
        hero_img_html = ""

    st.markdown(
        f"""
        <div class="nt-hero-wrapper">
          <div class="nt-hero">
            <div class="nt-hero-left">
              <div class="nt-hero-title">Nueva tarea</div>
            </div>
            <div class="nt-hero-right">
              {hero_img_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    if st.session_state.get("nt_visible", True):
        if st.session_state.pop("nt_added_ok", False):
            st.success("Agregado a Tareas recientes")

    # ===== Indicaciones en tarjetas =====
    st.markdown(
        """
    <div class="nt-steps-row">
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">1. Llena los datos</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">📝</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">2. Pulsa “Agregar”</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">➕</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">3. Revisa tu tarea</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">🕑</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">4. Graba</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">💾</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">5. Sube a Sheets</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">📤</span></div>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    # ===== Bloque del formulario =====
    with st.container():
        st.markdown(
            '<span id="nt-card-sentinel" style="display:none"></span>',
            unsafe_allow_html=True,
        )

        # ---------- Responsable & Área desde ACL ----------
        _acl = st.session_state.get("acl_user", {}) or {}
        display_name_txt = (
            _acl.get("display")
            or st.session_state.get("user_display_name", "")
            or _acl.get("name", "")
            or (st.session_state.get("user") or {}).get("name", "")
            or ""
        )
        if not str(st.session_state.get("nt_resp", "")).strip():
            st.session_state["nt_resp"] = display_name_txt

        _area_acl = (
            _acl.get("area")
            or _acl.get("Área")
            or _acl.get("area_name")
            or ""
        ).strip()
        area_fixed = _area_acl if _area_acl else (AREAS_OPC[0] if AREAS_OPC else "")
        st.session_state["nt_area"] = area_fixed

        # ---------- Fase ----------
        FASES = [
            "Capacitación",
            "Post-capacitación",
            "Pre-consistencia",
            "Consistencia",
            "Operación de campo",
            "Implementación del sistema de monitoreo",
            "Uso del sistema de monitoreo",
            "Uso del sistema de capacitación",
            "Levantamiento en campo",
            "Otros",
        ]
        _fase_sel = st.session_state.get("nt_fase", None)
        _is_fase_otros = str(_fase_sel).strip() == "Otros"

        # ---------- Fecha/Hora ----------
        if st.session_state.get("fi_d", "___MISSING___") is None:
            st.session_state.pop("fi_d")
        if st.session_state.get("fi_t", "___MISSING___") is None:
            st.session_state.pop("fi_t")
        if "fi_d" not in st.session_state:
            if st.session_state.get("nt_skip_date_init", False):
                st.session_state.pop("nt_skip_date_init", None)
            else:
                st.session_state["fi_d"] = now_lima_trimmed().date()
        _sync_time_from_date()

        _t = st.session_state.get("fi_t")
        st.session_state["fi_t_view"] = _t.strftime("%H:%M") if _t else ""

        # ---------- ID preview ----------
        _df_tmp = (
            st.session_state.get("df_main", pd.DataFrame()).copy()
            if "df_main" in st.session_state
            else pd.DataFrame()
        )
        prefix = make_id_prefix(
            st.session_state.get("nt_area", area_fixed),
            st.session_state.get("nt_resp", ""),
        )
        id_preview = (
            next_id_by_person(
                _df_tmp,
                st.session_state.get("nt_area", area_fixed),
                st.session_state.get("nt_resp", ""),
            )
            if st.session_state.get("fi_d")
            else f"{prefix}_"
        )

        # ========== LAYOUT CON MÁXIMO 5 CAMPOS POR FILA ==========

        if _is_fase_otros:
            # ----- FILA 1 (5 campos) -----
            r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(COLS5, gap="medium")
            r1c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
            r1c2.selectbox("Fase", options=FASES, key="nt_fase",
                           index=FASES.index("Otros"))
            r1c3.text_input("Otros (especifique)", key="nt_fase_otro",
                            placeholder="Describe la fase")
            r1c4.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
            r1c5.text_input("Detalle de tarea",
                            placeholder="Información adicional (opcional)",
                            key="nt_detalle")

            # ----- FILA 2 (5 campos) -----
            r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(COLS5, gap="medium")
            r2c1.text_input("Responsable", key="nt_resp", disabled=True)
            r2c2.selectbox("Ciclo de mejora",
                           options=["1", "2", "3", "+4"],
                           index=0,
                           key="nt_ciclo_mejora")
            r2c3.text_input("Tipo de tarea",
                            key="nt_tipo",
                            placeholder="Escribe el tipo de tarea")
            r2c4.text_input("Estado actual",
                            value="No iniciado",
                            disabled=True,
                            key="nt_estado_view")
            r2c5.selectbox("Complejidad",
                           options=["🟢 Baja", "🟡 Media", "🔴 Alta"],
                           index=0,
                           key="nt_complejidad")

            # ----- FILA 3 (hasta 5, usamos 4) -----
            r3c1, r3c2, r3c3, r3c4, _ = st.columns(COLS5, gap="medium")
            r3c1.selectbox("Duración",
                           options=[f"{i} día" if i == 1 else f"{i} días"
                                    for i in range(1, 6)],
                           index=0,
                           key="nt_duracion_label")
            r3c2.date_input("Fecha de registro",
                            key="fi_d",
                            on_change=_auto_time_on_date)
            _sync_time_from_date()
            r3c3.text_input("Hora de registro",
                            key="fi_t_view",
                            disabled=True,
                            help="Se asigna al elegir la fecha")
            r3c4.text_input("ID asignado",
                            value=id_preview,
                            disabled=True,
                            key="nt_id_preview")

        else:
            # ----- FILA 1 (5 campos) -----
            r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(COLS5, gap="medium")
            r1c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
            r1c2.selectbox("Fase",
                           options=FASES,
                           index=None,
                           placeholder="Selecciona una fase",
                           key="nt_fase")
            r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
            r1c4.text_input("Detalle de tarea",
                            placeholder="Información adicional (opcional)",
                            key="nt_detalle")
            r1c5.text_input("Responsable", key="nt_resp", disabled=True)

            # ----- FILA 2 (5 campos) -----
            r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(COLS5, gap="medium")
            r2c1.selectbox("Ciclo de mejora",
                           options=["1", "2", "3", "+4"],
                           index=0,
                           key="nt_ciclo_mejora")
            r2c2.text_input("Tipo de tarea",
                            key="nt_tipo",
                            placeholder="Escribe el tipo de tarea")
            r2c3.text_input("Estado actual",
                            value="No iniciado",
                            disabled=True,
                            key="nt_estado_view")
            r2c4.selectbox("Complejidad",
                           options=["🟢 Baja", "🟡 Media", "🔴 Alta"],
                           index=0,
                           key="nt_complejidad")
            r2c5.selectbox("Duración",
                           options=[f"{i} día" if i == 1 else f"{i} días"
                                    for i in range(1, 6)],
                           index=0,
                           key="nt_duracion_label")

            # ----- FILA 3 (3 campos + 2 vacíos) -----
            r3c1, r3c2, r3c3, r3c4, r3c5 = st.columns(COLS5, gap="medium")
            r3c1.date_input("Fecha de registro",
                            key="fi_d",
                            on_change=_auto_time_on_date)
            _sync_time_from_date()
            r3c2.text_input("Hora de registro",
                            key="fi_t_view",
                            disabled=True,
                            help="Se asigna al elegir la fecha")
            r3c3.text_input("ID asignado",
                            value=id_preview,
                            disabled=True,
                            key="nt_id_preview")
            # r3c4 y r3c5 quedan libres

    # ---------- Botones: volver + agregar ----------
    # (mantengo ratios antiguos, solo botones, no afecta filas del form)
    A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60
    left_spacer, col_back, col_add = st.columns(
        [A + Fw + T + D + R - C, C, C], gap="medium"
    )

    with col_back:
        st.markdown('<div class="nt-outbtn">', unsafe_allow_html=True)
        back = st.button(
            "⬅ Volver a Gestión de tareas",
            use_container_width=True,
            key="btn_volver_gestion",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with col_add:
        st.markdown('<div class="nt-outbtn">', unsafe_allow_html=True)
        submitted = st.button(
            "➕ Agregar", use_container_width=True, key="btn_agregar"
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if back:
        st.session_state["home_tile"] = ""
        display_name = st.session_state.get("user_display_name", "Usuario")
        try:
            st.experimental_set_query_params(auth="1", u=display_name)
        except Exception:
            pass
        st.rerun()

    if submitted:
        # 🔽 aquí va exactamente el mismo bloque de guardado que ya tienes
        # (no lo cambio para no tocar la lógica)
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

            df = _sanitize(df, COLS if COLS is not None else None)

            reg_fecha = st.session_state.get("fi_d")
            reg_hora_obj = st.session_state.get("fi_t")
            try:
                reg_hora_txt = (
                    reg_hora_obj.strftime("%H:%M") if reg_hora_obj is not None else ""
                )
            except Exception:
                reg_hora_txt = str(reg_hora_obj) if reg_hora_obj is not None else ""

            fase_sel = st.session_state.get("nt_fase", "")
            fase_otro = (st.session_state.get("nt_fase_otro", "") or "").strip()
            if str(fase_sel).strip() == "Otros":
                fase_final = f"Otros — {fase_otro}" if fase_otro else "Otros"
            else:
                fase_final = fase_sel

            base_row = blank_row()
            if not isinstance(base_row, dict):
                base_row = {}

            new = dict(base_row)
            new.update(
                {
                    "Área": st.session_state.get("nt_area", area_fixed),
                    "Id": next_id_by_person(
                        df,
                        st.session_state.get("nt_area", area_fixed),
                        st.session_state.get("nt_resp", ""),
                    ),
                    "Tarea": st.session_state.get("nt_tarea", ""),
                    "Tipo": st.session_state.get("nt_tipo", ""),
                    "Responsable": st.session_state.get("nt_resp", ""),
                    "Fase": fase_final,
                    "Estado": "No iniciado",
                    "Fecha de registro": reg_fecha,
                    "Hora de registro": reg_hora_txt,
                    "Fecha Registro": reg_fecha,
                    "Hora Registro": reg_hora_txt,
                    "Fecha inicio": None,
                    "Hora de inicio": "",
                    "Fecha Terminado": None,
                    "Hora Terminado": "",
                    "Ciclo de mejora": st.session_state.get("nt_ciclo_mejora", ""),
                    "Detalle": st.session_state.get("nt_detalle", ""),
                }
            )

            if str(st.session_state.get("nt_tipo", "")).strip().lower() == "otros":
                new["Complejidad"] = st.session_state.get("nt_complejidad", "")
                lbl = st.session_state.get("nt_duracion_label", "")
                try:
                    _dur = int(str(lbl).split()[0])
                except Exception:
                    _dur = ""
                new["Duración (días)"] = _dur
                new["Duración"] = _dur

            df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
            df = _sanitize(df, COLS if COLS is not None else None)
            st.session_state["df_main"] = df.copy()

            def _persist_to_sheets(df_rows: pd.DataFrame):
                try:
                    ss_url, ws_name = _get_sheet_conf()
                    if upsert_rows_by_id is None or not ss_url:
                        return {"ok": False}
                    ids = (
                        df_rows["Id"].astype(str).tolist()
                        if "Id" in df_rows.columns
                        else []
                    )
                    res = upsert_rows_by_id(
                        ss_url=ss_url,
                        ws_name=ws_name,
                        df=df_rows,
                        ids=ids,
                    )
                    return res
                except Exception:
                    return {"ok": False}

            df_rows = pd.DataFrame([new])
            try:
                _ = _persist_to_sheets(df_rows.copy())
            except Exception:
                pass

            sheet = None
            try:
                url = st.secrets.get("gsheets_doc_url") or (
                    st.secrets.get("gsheets", {}) or {}
                ).get("spreadsheet_url")
                if url and callable(open_sheet_by_url):
                    try:
                        sheet = open_sheet_by_url(url)
                    except Exception:
                        sheet = None
            except Exception:
                sheet = None

            try:
                log_reciente_safe(
                    sheet,
                    tarea_nombre=new.get("Tarea", ""),
                    especialista=new.get("Responsable", ""),
                    detalle="Asignada",
                    id_val=new.get("Id", ""),
                    fecha_reg=reg_fecha,
                    hora_reg=reg_hora_txt,
                    area=new.get("Área", ""),
                    fase=new.get("Fase", ""),
                    tipo=new.get("Tipo", ""),
                    estado=new.get("Estado", ""),
                    ciclo_mejora=new.get("Ciclo de mejora", ""),
                    complejidad=new.get("Complejidad", ""),
                    duracion_dias=new.get("Duración (días)", ""),
                    duracion=new.get("Duración", ""),
                    link_archivo=new.get("Link de archivo", ""),
                )
            except Exception:
                pass

            for k in [
                "nt_area",
                "nt_fase",
                "nt_fase_otro",
                "nt_tarea",
                "nt_detalle",
                "nt_resp",
                "nt_ciclo_mejora",
                "nt_tipo",
                "nt_complejidad",
                "nt_duracion_label",
                "fi_d",
                "fi_t",
                "fi_t_view",
                "nt_id_preview",
            ]:
                st.session_state.pop(k, None)
            st.session_state["nt_skip_date_init"] = True
            st.session_state["nt_added_ok"] = True

            st.rerun()

        except Exception as e:
            st.error(f"No pude guardar la nueva tarea: {e}")

    gap = SECTION_GAP if "SECTION_GAP" in globals() else 30
    st.markdown(f"<div style='height:{gap}px;'></div>", unsafe_allow_html=True)

# ============================================================
#             VISTA UNIFICADA (NUEVA + RECIENTES)
# ============================================================
def render(user: dict | None = None):
    """
    Vista combinada:
    - Arriba: ➕ Nueva tarea
    - Abajo: 🕑 Tareas recientes
    """
    # Aseguramos que df_main esté inicializado antes de ambos bloques
    _bootstrap_df_main_hist()
    render_nueva_tarea(user=user)
    render_historial(user=user)
