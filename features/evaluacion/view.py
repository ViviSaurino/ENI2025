# features/evaluacion/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

# ✅ Upsert reutilizable (Google Sheets)
try:
    from utils.gsheets import upsert_rows_by_id  # type: ignore
except Exception:
    upsert_rows_by_id = None

# 🔐 Alcance/visibilidad (apply_scope) y helpers de identidad
try:
    from shared import apply_scope  # type: ignore
except Exception:
    def apply_scope(df, user=None):
        return df  # fallback no-op


def _get_display_name() -> str:
    acl_user = st.session_state.get("acl_user", {}) or {}
    return (
        acl_user.get("display")
        or st.session_state.get("user_display_name", "")
        or acl_user.get("name", "")
        or (st.session_state.get("user") or {}).get("name", "")
        or ""
    )


def _is_super_viewer(user: dict | None = None) -> bool:
    """Solo Vivi/Enrique o quien tenga can_edit_all_tabs pueden ver TODO."""
    acl_user = st.session_state.get("acl_user", {}) or {}
    if bool(acl_user.get("can_edit_all_tabs", False)):
        return True
    dn = (_get_display_name() or "").strip().lower()
    return dn.startswith("vivi") or dn.startswith("enrique")


# Fallback seguro para separación vertical
SECTION_GAP_DEF = globals().get("SECTION_GAP", 30)


def _save_local(df: pd.DataFrame):
    """Guardar CSV localmente sin romper si la carpeta no existe."""
    try:
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")
    except Exception:
        pass


def render(user: dict | None = None):
    # =========================== EVALUACIÓN ===============================
    st.session_state.setdefault("eva_visible", True)

    # 🔐 ACL: SOLO Vivi y Enrique (por correo) o quien tenga can_edit_all_tabs
    acl_user = st.session_state.get("acl_user", {}) or {}
    email_from_user = (user or {}).get("email") if isinstance(user, dict) else None
    current_email = str(acl_user.get("email") or email_from_user or "").strip().lower()

    # Lista de correos permitidos (configurable por secrets); fallback: vacía
    allow_secret = set(
        map(
            str.lower,
            (
                st.secrets.get("acl", {}).get("editor_emails", [])
                or st.secrets.get("editors", {}).get("emails", [])
                or st.secrets.get("editor_emails", [])
                or []
            ),
        )
    )
    # Flag central
    can_edit_flag = bool(acl_user.get("can_edit_all_tabs", False))

    IS_EDITOR = can_edit_flag or (current_email in allow_secret)

    # Anchos (consistentes con las otras secciones)
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    # ---------- Barra superior (SIN botón mostrar/ocultar) ----------
    st.markdown('<div class="topbar-eval">', unsafe_allow_html=True)
    c_pill_e, _ = st.columns([A, Fw + T_width + D + R + C], gap="medium")
    with c_pill_e:
        st.markdown("", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    # ---------- fin barra superior ----------

    if st.session_state["eva_visible"]:

        # --- contenedor local + css (botón, headers 600, colores y estrellas) ---
        st.markdown('<div id="eva-section">', unsafe_allow_html=True)
        st.markdown(
            """
        <style>
          #eva-section .stButton > button { width: 100% !important; }
          .section-eva .help-strip-eval + .form-card{ margin-top: 6px !important; }

          /* Oculta la píldora pequeña del topbar SOLO aquí (por si se renderiza) */
          .topbar-eval .form-title-eval{ display:none !important; }

          /* overflow horizontal visible SOLO aquí */
          #eva-section .ag-body-horizontal-scroll,
          #eva-section .ag-center-cols-viewport { overflow-x: auto !important; }

          /* headers más marcados SOLO aquí */
          #eva-section .ag-header .ag-header-cell-text{ font-weight: 600 !important; }

          /* clases de color por estado */
          #eva-section .eva-ok  { color:#16a34a !important; }
          #eva-section .eva-bad { color:#dc2626 !important; }
          #eva-section .eva-obs { color:#d97706 !important; }

          /* ===== Paleta (más pastel) ===== */
          :root{
            --eva-pill: #FFE4C7;        /* Naranja aún más pastel */
            --eva-help-bg: #FFF7ED;     /* Naranja MUY claro */
            --eva-help-border: #FED7AA; /* Naranja claro para borde */
            --eva-help-text: #92400E;   /* Texto legible */
          }

          /* Píldora naranja (ancho igual a la columna "Área") */
          .eva-pill{
            width:100%; height:38px; border-radius:12px;
            display:flex; align-items:center; justify-content:center;
            background: var(--eva-pill);
            color:#ffffff; font-weight:700;
            box-shadow:0 6px 14px rgba(255,228,199,.35);
            user-select:none; margin:4px 0 16px;
          }
          .eva-pill span{ display:inline-flex; gap:8px; align-items:center; }

          /* Franja de indicaciones: forzar naranja (derrota estilos globales) */
          #eva-section .help-strip,
          #eva-section .help-strip-eval{
            background: var(--eva-help-bg) !important;
            background-image: none !important;
            color: var(--eva-help-text) !important;
            border: 1px dashed var(--eva-help-border) !important;
            box-shadow: 0 0 0 1px var(--eva-help-border) inset !important;
          }
        </style>
        """,
            unsafe_allow_html=True,
        )

        # ===== Píldora alineada al ancho de "Área" =====
        _pill, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with _pill:
            st.markdown(
                '<div class="eva-pill"><span>📝&nbsp;Evaluación</span></div>',
                unsafe_allow_html=True,
            )

        # ===== Wrapper UNIDO: help-strip + form-card =====
        st.markdown(
            f"""
        <div class="section-eva">
          <div class="help-strip help-strip-eval" id="eva-help"
               style="background: var(--eva-help-bg); color: var(--eva-help-text);
                      border:1px dashed var(--eva-help-border); box-shadow:0 0 0 1px var(--eva-help-border) inset;">
            📝 <strong>Registra/actualiza la evaluación</strong> de tareas filtradas (solo jefatura).
          </div>
          <div class="form-card">
        """,
            unsafe_allow_html=True,
        )

        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
        if df_all.empty:
            df_all = pd.DataFrame(
                columns=[
                    "Id",
                    "Área",
                    "Fase",
                    "Responsable",
                    "Tipo de tarea",
                    "Tarea",
                    "Estado",
                    "Fecha inicio",
                    "Evaluación",
                    "Calificación",
                    "Cumplimiento",
                    "Comentarios",
                ]
            )

        # 🔒 VISIBILIDAD por usuario: solo Vivi/Enrique ven todo; el resto solo lo suyo.
        IS_SUPER_VIEWER = _is_super_viewer(user=user)
        me = _get_display_name().strip()
        if not IS_SUPER_VIEWER:
            # 1) Reglas externas (si existen)
            df_all = apply_scope(df_all, user=st.session_state.get("acl_user"))
            # 2) Filtro por Responsable contiene mi nombre (case-insensitive)
            if "Responsable" in df_all.columns and me:
                df_all = df_all[
                    df_all["Responsable"].astype(str).str.contains(
                        me, case=False, na=False
                    )
                ]
        else:
            # Super viewer: toggle para ver todas o solo propias
            ver_todas = st.toggle(
                "👀 Ver todas las tareas", value=True, key="eva_ver_todas"
            )
            if (not ver_todas) and "Responsable" in df_all.columns and me:
                df_all = df_all[
                    df_all["Responsable"].astype(str).str.contains(
                        me, case=False, na=False
                    )
                ]

        # ✅ Asegura columnas base (por defecto, Evaluación = "Sin evaluar")
        if "Evaluación" not in df_all.columns:
            df_all["Evaluación"] = "Sin evaluar"
        df_all["Evaluación"] = (
            df_all["Evaluación"]
            .fillna("Sin evaluar")
            .replace({"": "Sin evaluar"})
            .astype(str)
        )
        if "Calificación" not in df_all.columns:
            df_all["Calificación"] = 0
        df_all["Calificación"] = (
            pd.to_numeric(df_all["Calificación"], errors="coerce")
            .fillna(0)
            .astype(int)
            .clip(0, 5)
        )
        if "Comentarios" not in df_all.columns:
            df_all["Comentarios"] = ""
        df_all["Comentarios"] = df_all["Comentarios"].fillna("").astype(str)
        if "Cumplimiento" not in df_all.columns:
            df_all["Cumplimiento"] = ""
        df_all["Cumplimiento"] = df_all["Cumplimiento"].fillna("").astype(str)
        if "Tipo de tarea" not in df_all.columns and "Tipo" in df_all.columns:
            df_all["Tipo de tarea"] = df_all["Tipo"].astype(str)
        if "Fase" not in df_all.columns:
            df_all["Fase"] = ""

        # ===== Estado actual calculado (para filtro) =====
        fi = pd.to_datetime(
            df_all.get(
                "Fecha de inicio",
                df_all.get("Fecha inicio", pd.Series([], dtype=object)),
            ),
            errors="coerce",
        )
        ft = pd.to_datetime(
            df_all.get(
                "Fecha terminada",
                df_all.get("Fecha Terminado", pd.Series([], dtype=object)),
            ),
            errors="coerce",
        )
        fe = pd.to_datetime(
            df_all.get("Fecha eliminada", pd.Series([], dtype=object)), errors="coerce"
        )

        estado_calc = pd.Series("No iniciado", index=df_all.index, dtype="object")
        estado_calc = estado_calc.mask(fi.notna() & ft.isna() & fe.isna(), "En curso")
        estado_calc = estado_calc.mask(ft.notna() & fe.isna(), "Terminada")
        estado_calc = estado_calc.mask(fe.notna(), "Eliminada")
        if "Estado" in df_all.columns:
            saved = df_all["Estado"].astype(str).str.strip()
            estado_calc = saved.where(
                ~saved.isin(["", "nan", "NaN", "None"]), estado_calc
            )
        df_all["_ESTADO_EVAL_"] = estado_calc

        estados_catalogo = [
            "No iniciado",
            "En curso",
            "Terminada",
            "Pausada",
            "Cancelada",
            "Eliminada",
        ]

        # ===== Rango por defecto (min–max del dataset) =====
        def _first_valid_date_series(df: pd.DataFrame) -> pd.Series:
            for col in ["Fecha inicio", "Fecha de inicio", "Fecha Registro", "Fecha"]:
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
        with st.form("eva_filtros_v2", clear_on_submit=False):
            if IS_SUPER_VIEWER:
                c_resp, c_fase, c_tipo, c_estado, c_desde, c_hasta, c_buscar = st.columns(
                    [Fw, Fw, T_width, D, D, R, C], gap="medium"
                )
            else:
                c_fase, c_tipo, c_estado, c_desde, c_hasta, c_buscar = st.columns(
                    [Fw, T_width, D, D, R, C], gap="medium"
                )
                c_resp = None

            fases_all = sorted(
                [
                    x
                    for x in df_all.get("Fase", pd.Series([], dtype=str))
                    .astype(str)
                    .unique()
                    if x and x != "nan"
                ]
            )
            eva_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

            tipos_all = sorted(
                [
                    x
                    for x in df_all.get("Tipo de tarea", pd.Series([], dtype=str))
                    .astype(str)
                    .unique()
                    if x and x != "nan"
                ]
            )
            eva_tipo = c_tipo.selectbox("Tipo de tarea", ["Todos"] + tipos_all, index=0)

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
            eva_estado = (
                "Todos"
                if sel_label == "Todos"
                else [k for k, v in estado_labels.items() if v == sel_label][0]
            )

            if IS_SUPER_VIEWER:
                df_resp_src = df_all.copy()
                if eva_fase != "Todas" and "Fase" in df_resp_src.columns:
                    df_resp_src = df_resp_src[
                        df_resp_src["Fase"].astype(str) == eva_fase
                    ]
                if eva_tipo != "Todos" and "Tipo de tarea" in df_resp_src.columns:
                    df_resp_src = df_resp_src[
                        df_resp_src["Tipo de tarea"].astype(str) == eva_tipo
                    ]
                responsables_all = sorted(
                    [
                        x
                        for x in df_resp_src.get(
                            "Responsable", pd.Series([], dtype=str)
                        )
                        .astype(str)
                        .unique()
                        if x and x != "nan"
                    ]
                )
                eva_resp = c_resp.selectbox(
                    "Responsable", ["Todos"] + responsables_all, index=0
                )
            else:
                eva_resp = "Todos"

            eva_desde = c_desde.date_input(
                "Desde",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                key="eva_desde",
            )
            eva_hasta = c_hasta.date_input(
                "Hasta",
                value=max_date,
                min_value=min_date,
                max_value=max_date,
                key="eva_hasta",
            )

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
                eva_do_buscar = st.form_submit_button(
                    "🔍 Buscar", use_container_width=True
                )

        # ===== Filtrado para tabla =====
        df_filtrado = df_all.copy()
        if eva_do_buscar:
            if IS_SUPER_VIEWER and eva_resp != "Todos" and "Responsable" in df_filtrado.columns:
                df_filtrado = df_filtrado[
                    df_filtrado["Responsable"].astype(str) == eva_resp
                ]
            if eva_fase != "Todas" and "Fase" in df_filtrado.columns:
                df_filtrado = df_filtrado[
                    df_filtrado["Fase"].astype(str) == eva_fase
                ]
            if eva_tipo != "Todos" and "Tipo de tarea" in df_filtrado.columns:
                df_filtrado = df_filtrado[
                    df_filtrado["Tipo de tarea"].astype(str) == eva_tipo
                ]
            if eva_estado != "Todos" and "_ESTADO_EVAL_" in df_filtrado.columns:
                df_filtrado = df_filtrado[
                    df_filtrado["_ESTADO_EVAL_"].astype(str) == eva_estado
                ]

            # Fecha base
            if "Fecha inicio" in df_filtrado.columns:
                fcol = pd.to_datetime(df_filtrado["Fecha inicio"], errors="coerce")
            elif "Fecha de inicio" in df_filtrado.columns:
                fcol = pd.to_datetime(df_filtrado["Fecha de inicio"], errors="coerce")
            elif "Fecha Vencimiento" in df_filtrado.columns:
                fcol = pd.to_datetime(df_filtrado["Fecha Vencimiento"], errors="coerce")
            elif "Fecha Registro" in df_filtrado.columns:
                fcol = pd.to_datetime(df_filtrado["Fecha Registro"], errors="coerce")
            else:
                fcol = pd.to_datetime(
                    df_filtrado.get("Fecha", pd.Series([], dtype=str)),
                    errors="coerce",
                )

            if eva_desde is not None:
                df_filtrado = df_filtrado[
                    fcol.isna() | (fcol >= pd.to_datetime(eva_desde))
                ]
            if eva_hasta is not None:
                limite = (
                    pd.to_datetime(eva_hasta)
                    + pd.Timedelta(days=1)
                    - pd.Timedelta(seconds=1)
                )
                df_filtrado = df_filtrado[
                    fcol.isna() | (fcol <= limite)
                ]

        # ===== Tabla de Evaluación =====
        st.markdown("**Resultados**")

        # Mapeos de evaluación (con/sin emoji)
        EVA_OPC_SHOW = ["Sin evaluar", "🟢 Aprobado", "🔴 Desaprobado", "🟠 Observado"]
        EVA_TO_TEXT = {
            "🟢 Aprobado": "Aprobado",
            "🔴 Desaprobado": "Desaprobado",
            "🟠 Observado": "Observado",
            "Aprobado": "Aprobado",
            "Desaprobado": "Desaprobado",
            "Observado": "Observado",
            "Sin evaluar": "Sin evaluar",
            "": "Sin evaluar",
        }
        TEXT_TO_SHOW = {
            "Aprobado": "🟢 Aprobado",
            "Desaprobado": "🔴 Desaprobado",
            "Observado": "🟠 Observado",
            "Sin evaluar": "Sin evaluar",
        }

        cols_out = [
            "Id",
            "Fase",
            "Tipo de tarea",
            "Tarea",
            "Evaluación",
            "Calificación",
            "Cumplimiento",
            "Comentarios",
        ]
        if df_filtrado.empty:
            df_view = pd.DataFrame({c: pd.Series(dtype="str") for c in cols_out})
        else:
            tmp = df_filtrado.copy()
            for need in [
                "Fase",
                "Tipo de tarea",
                "Tarea",
                "Evaluación",
                "Calificación",
                "Cumplimiento",
                "Comentarios",
            ]:
                if need not in tmp.columns:
                    tmp[need] = ""
            eva_actual_txt = (
                tmp["Evaluación"]
                .fillna("Sin evaluar")
                .replace({"": "Sin evaluar"})
                .astype(str)
            )
            eva_show = eva_actual_txt.apply(
                lambda v: TEXT_TO_SHOW.get(v, "Sin evaluar")
            )
            calif = (
                pd.to_numeric(tmp.get("Calificación", 0), errors="coerce")
                .fillna(0)
                .astype(int)
                .clip(0, 5)
            )
            cumplimiento = tmp.get("Cumplimiento", "").astype(str).fillna("")
            comentarios = tmp.get("Comentarios", "").astype(str).fillna("")
            fase = tmp.get("Fase", "").astype(str).fillna("")
            tipo_t = tmp.get("Tipo de tarea", "").astype(str).fillna("")

            df_view = pd.DataFrame(
                {
                    "Id": tmp["Id"].astype(str),
                    "Fase": fase,
                    "Tipo de tarea": tipo_t,
                    "Tarea": tmp["Tarea"].astype(str).replace({"nan": ""}),
                    "Evaluación": eva_show,
                    "Calificación": calif,
                    "Cumplimiento": cumplimiento,
                    "Comentarios": comentarios,
                }
            )[cols_out].copy()

        # Reglas de color
        eva_cell_rules = {
            "eva-ok": "value == '🟢 Aprobado' || value == 'Aprobado'",
            "eva-bad": "value == '🔴 Desaprobado' || value == 'Desaprobado'",
            "eva-obs": "value == '🟠 Observado' || value == 'Observado'",
        }

        # Estrellas (0..5)
        stars_fmt = JsCode(
            """
          function(p){
            var n = parseInt(p.value||0);
            if (isNaN(n) || n < 0) n = 0;
            if (n > 5) n = 5;
            if (n === 0) { return '—'; }
            return '★'.repeat(n) + '☆'.repeat(5-n);
          }
        """
        )

        gob = GridOptionsBuilder.from_dataframe(df_view)
        gob.configure_default_column(
            resizable=True,
            wrapText=False,      # ⬅️ una sola línea
            autoHeight=False,    # ⬅️ sin crecer en altura por texto
            minWidth=120,
            flex=1,
        )
        gob.configure_grid_options(
            suppressMovableColumns=True,
            domLayout="normal",
            ensureDomOrder=True,
            rowHeight=46,
            headerHeight=44,
            suppressHorizontalScroll=False,
        )

        # Lectura
        gob.configure_column("Id", editable=False, minWidth=80, flex=0.8)
        gob.configure_column("Fase", editable=False, minWidth=130, flex=1.2)
        gob.configure_column(
            "Tipo de tarea", editable=False, minWidth=180, flex=1.4
        )
        gob.configure_column(
            "Tarea",
            editable=False,
            minWidth=260,
            flex=2.0,
            headerName="📝 Tarea",
        )
        gob.configure_column(
            "Cumplimiento",
            editable=False,
            minWidth=160,
            flex=1.3,
            headerName="📊 Cumplimiento",
        )

        # 🔐 Editable (solo jefatura): Evaluación
        gob.configure_column(
            "Evaluación",
            editable=bool(IS_EDITOR),
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": EVA_OPC_SHOW},
            cellClassRules=eva_cell_rules,
            flex=1.4,
            minWidth=180,
            headerName="✅ Evaluación",
        )

        # 🔐 Editable (solo jefatura): Calificación (0..5) + estrellas
        gob.configure_column(
            "Calificación",
            editable=bool(IS_EDITOR),
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": [0, 1, 2, 3, 4, 5]},
            valueFormatter=stars_fmt,
            flex=1.1,
            minWidth=160,
            headerName="⭐ Calificación",
            filter=False,        # ⬅️ sin filtro en esta columna
        )

        # 🔐 Editable (solo jefatura): Comentarios (texto libre)
        gob.configure_column(
            "Comentarios",
            editable=bool(IS_EDITOR),
            flex=2.0,
            minWidth=240,
        )

        # CSS dentro del iframe de AgGrid
        custom_css_eval = {
            ".ag-header-cell-text": {"font-weight": "600 !important"},
            ".ag-header-cell-label": {"font-weight": "600 !important"},
            ".ag-header-group-cell-label": {"font-weight": "600 !important"},
            ".ag-theme-alpine": {"--ag-font-weight": "600"},
            ".ag-header": {"font-synthesis-weight": "none !important"},
            ".eva-ok": {"color": "#16a34a !important"},
            ".eva-bad": {"color": "#dc2626 !important"},
            ".eva-obs": {"color": "#d97706 !important"},
            ".ag-cell": {"white-space": "nowrap !important"},  # ⬅️ evita multi-línea
        }

        grid_eval = AgGrid(
            df_view,
            gridOptions=gob.build(),
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            fit_columns_on_grid_load=False,  # usamos flex
            enable_enterprise_modules=False,
            allow_unsafe_jscode=True,
            reload_data=False,
            theme="alpine",
            height=380,          # ⬅️ tabla un poco más alta
            custom_css=custom_css_eval,
            key="grid_evaluacion",  # KEY ÚNICO
        )

        # ===== 🔐 Acción: solo botón Evaluar =====
        _sp_eva, _btns_eva = st.columns(
            [A + Fw + T_width + D + R, C], gap="medium"
        )
        with _btns_eva:
            if IS_EDITOR:
                click_eval = st.button(
                    "✅ Evaluar", use_container_width=True, key="eva_guardar_v1"
                )
            else:
                click_eval = False

        if IS_EDITOR and click_eval:
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
                        if "Comentarios" not in df_base.columns:
                            df_base["Comentarios"] = ""

                        cambios = 0
                        changed_ids: set[str] = set()

                        for _, row in edited.iterrows():
                            id_row = str(row.get("Id", "")).strip()
                            if not id_row:
                                continue
                            m = df_base["Id"].astype(str).str.strip() == id_row
                            if not m.any():
                                continue

                            # Mapear evaluación con/sin emoji -> texto limpio
                            eva_ui = str(row.get("Evaluación", "Sin evaluar")).strip()
                            eva_new = EVA_TO_TEXT.get(eva_ui, "Sin evaluar")

                            # Calificación segura 0..5
                            cal_new = row.get("Calificación", 0)
                            try:
                                cal_new = int(cal_new)
                            except Exception:
                                cal_new = 0
                            cal_new = max(0, min(5, cal_new))

                            # Comentarios (texto)
                            com_new = str(row.get("Comentarios", "") or "").strip()

                            # Valores previos
                            prev_eva = (
                                df_base.loc[m, "Evaluación"].iloc[0] if m.any() else None
                            )
                            prev_cal = (
                                df_base.loc[m, "Calificación"].iloc[0]
                                if m.any()
                                else None
                            )
                            prev_com = (
                                str(df_base.loc[m, "Comentarios"].iloc[0])
                                if m.any()
                                else ""
                            )

                            any_change = False
                            if eva_new != prev_eva:
                                df_base.loc[m, "Evaluación"] = eva_new
                                any_change = True
                            if cal_new != prev_cal:
                                df_base.loc[m, "Calificación"] = cal_new
                                any_change = True
                            if com_new != prev_com:
                                df_base.loc[m, "Comentarios"] = com_new
                                any_change = True

                            if any_change:
                                cambios += 1
                                changed_ids.add(id_row)

                        if cambios > 0:
                            new_df = df_base.copy()
                            st.session_state["df_main"] = new_df

                            # Persistencia local
                            _save_local(new_df)

                            # 📤 Upsert a Google Sheets por Id (solo filas cambiadas)
                            try:
                                if upsert_rows_by_id is not None and changed_ids:
                                    ss_url = (
                                        st.secrets.get("gsheets_doc_url")
                                        or (
                                            st.secrets.get("gsheets", {}) or {}
                                        ).get("spreadsheet_url")
                                        or (
                                            st.secrets.get("sheets", {}) or {}
                                        ).get("sheet_url")
                                    )
                                    ws_name = (
                                        (st.secrets.get("gsheets", {}) or {}).get(
                                            "worksheet", "TareasRecientes"
                                        )
                                    )
                                    df_rows = new_df[
                                        new_df["Id"]
                                        .astype(str)
                                        .isin([str(x) for x in changed_ids])
                                    ].copy()
                                    res = upsert_rows_by_id(
                                        ss_url=ss_url,
                                        ws_name=ws_name,
                                        df=df_rows,
                                        ids=[str(x) for x in changed_ids],
                                    )
                                    if res.get("ok"):
                                        st.success(
                                            res.get(
                                                "msg",
                                                "Evaluaciones guardadas y subidas.",
                                            )
                                        )
                                    else:
                                        st.warning(
                                            res.get(
                                                "msg",
                                                "Guardado local ok, no se pudo subir a Sheets.",
                                            )
                                        )
                                else:
                                    st.success("Evaluaciones guardadas (local).")
                            except Exception as e:
                                st.warning(
                                    f"Guardado local ok, pero falló la subida a Sheets: {e}"
                                )

                            st.rerun()
                        else:
                            st.info("No se detectaron cambios para guardar.")
            except Exception as e:
                st.error(f"No pude guardar la evaluación: {e}")

        # Cerrar wrappers
        st.markdown("</div></div>", unsafe_allow_html=True)  # cierra .form-card y .section-eva
        st.markdown("</div>", unsafe_allow_html=True)        # cierra #eva-section

        # Separación vertical
        st.markdown(
            f"<div style='height:{SECTION_GAP_DEF}px'></div>", unsafe_allow_html=True
        )
