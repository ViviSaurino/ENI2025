# features/prioridad/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode

# Fallbacks seguros
SECTION_GAP_DEF = globals().get("SECTION_GAP", 30)

def _save_local(df: pd.DataFrame):
    """Guardar localmente sin romper si la carpeta no existe."""
    try:
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")
    except Exception:
        pass


def render(user: dict | None = None):
    # =========================== PRIORIDAD ===============================
    st.session_state.setdefault("pri_visible", True)

    # ---------- Barra superior (SIN botón mostrar/ocultar) ----------
    # La píldora queda a la izquierda y con el mismo ancho que "Área"
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60
    st.markdown('<div class="topbar-pri">', unsafe_allow_html=True)
    c_pill_p, _ = st.columns([A, Fw + T_width + D + R + C], gap="medium")
    with c_pill_p:
        st.markdown('<div class="form-title-pri">🧭&nbsp;&nbsp;Prioridad</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    # ---------- fin barra superior ----------

    if st.session_state["pri_visible"]:

        # === 🔐 ACL: solo jefatura/owner puede editar ===
        acl_user = st.session_state.get("acl_user", {}) or {}
        IS_EDITOR = bool(acl_user.get("can_edit_all_tabs", False))

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
            font-weight: 400 !important;
            font-synthesis-weight: none !important;
            color: #1f2937 !important;
            opacity: 1 !important;
            visibility: visible !important;
          }

          /* Colores para prioridad (por clase) */
          #pri-section .pri-low   { color:#2563eb !important; }  /* 🔵 Baja */
          #pri-section .pri-med   { color:#ca8a04 !important; }  /* 🟡 Media */
          #pri-section .pri-high  { color:#dc2626 !important; }  /* 🔴 Alta */

          /* Píldora jade (mismo ancho que "Área") */
          .pri-pill{
            width:100%; height:38px; border-radius:12px;
            display:flex; align-items:center; justify-content:center;
            background:#34D399; color:#ffffff; font-weight:700;
            box-shadow:0 6px 14px rgba(52,211,153,.35);
            user-select:none; margin:4px 0 16px;
          }
          .pri-pill span{ display:inline-flex; gap:8px; align-items:center; }
        </style>
        """, unsafe_allow_html=True)

        # ===== Píldora alineada al ancho de "Área" =====
        _pill, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with _pill:
            st.markdown('<div class="pri-pill"><span>🧭&nbsp;Prioridad</span></div>', unsafe_allow_html=True)

        # ===== Wrapper UNIDO: help-strip + form-card =====
        st.markdown("""
        <div class="section-pri">
          <div class="help-strip help-strip-pri" id="pri-help">
            🧭 <strong>Asigna o edita prioridades</strong> para varias tareas a la vez (solo jefatura)
          </div>
          <div class="form-card">
        """, unsafe_allow_html=True)

        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
        if df_all.empty:
            df_all = pd.DataFrame(columns=["Id","Área","Fase","Responsable","Tarea","Fecha inicio","Prioridad"])

        # Asegurar columna Prioridad con default Media
        if "Prioridad" not in df_all.columns:
            df_all["Prioridad"] = "Media"
        df_all["Prioridad"] = df_all["Prioridad"].fillna("Media").replace({"": "Media"})

        # ===== Rango de fechas por defecto (min–max del dataset) =====
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

            # 🗓️ Rango de fechas SIEMPRE visible (sin checkbox)
            pri_desde = c_desde.date_input("Desde", value=min_date, min_value=min_date, max_value=max_date, key="pri_desde")
            pri_hasta = c_hasta.date_input("Hasta",  value=max_date, min_value=min_date, max_value=max_date, key="pri_hasta")

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
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

        # ====== AG-GRID con columnDefs explícitos ======
        PRI_OPC_SHOW = ["🔵 Baja","🟡 Media","🔴 Alta"]
        PRI_MAP_TO_TEXT = {
            "🔵 Baja":"Baja","🟡 Media":"Media","🔴 Alta":"Alta",
            "Baja":"Baja","Media":"Media","Alta":"Alta"
        }

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
            # 🔐 editable condicionado por ACL
            {"field":"Prioridad a ajustar", "headerName":"Prioridad a ajustar", "editable": bool(IS_EDITOR),
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

        # ===== 🔐 Acciones y guardado condicional =====
        _sp_pri, _btns_pri = st.columns([A+Fw+T_width+D+R, C], gap="medium")
        with _btns_pri:
            if IS_EDITOR:
                c1, c2 = st.columns(2, gap="small")
                with c1:
                    st.button("⭐ Dar prioridad", use_container_width=True)
                with c2:
                    if st.button("💾 Guardar cambios", use_container_width=True, key="pri_guardar_v2"):
                        try:
                            edited = pd.DataFrame(grid_pri.get("data", []))
                            if edited.empty:
                                st.info("No hay filas para actualizar.")
                            else:
                                df_base = st.session_state.get("df_main", pd.DataFrame()).copy()
                                if "Prioridad" not in df_base.columns:
                                    df_base["Prioridad"] = "Media"

                                # Merge por Id
                                df_base["Id"] = df_base["Id"].astype(str)
                                edited["Id"] = edited["Id"].astype(str)

                                b_i = df_base.set_index("Id")
                                e_i = edited.set_index("Id")
                                common = b_i.index.intersection(e_i.index)

                                # Toma 'Prioridad a ajustar' (sin emoji)
                                if "Prioridad a ajustar" in e_i.columns:
                                    map_clean = {"🔵 Baja":"Baja","🟡 Media":"Media","🔴 Alta":"Alta"}
                                    src_vals = e_i["Prioridad a ajustar"].map(lambda v: map_clean.get(str(v), str(v)))
                                    b_i.loc[common, "Prioridad"] = src_vals.loc[common]

                                new_df = b_i.reset_index()
                                st.session_state["df_main"] = new_df

                                # Persistencia con políticas (dry_run/save_scope)
                                def _persist(df):
                                    _save_local(df)
                                    return {"ok": True, "msg": "Prioridades guardadas."}

                                maybe_save = st.session_state.get("maybe_save")
                                if callable(maybe_save):
                                    res = maybe_save(_persist, new_df)
                                else:
                                    _save_local(new_df)
                                    res = {"ok": True, "msg": "Prioridades guardadas (local)."}

                                st.success(res.get("msg", "Listo."))
                                st.rerun()
                        except Exception as e:
                            st.error(f"No pude guardar los cambios de prioridad: {e}")
            else:
                st.caption("🔒 Solo lectura. Puedes filtrar, pero no editar ni guardar.")

        # Cerrar wrappers
        st.markdown('</div></div>', unsafe_allow_html=True)  # cierra .form-card y .section-pri
        st.markdown('</div>', unsafe_allow_html=True)        # cierra #pri-section

        # Separación vertical
        st.markdown(f"<div style='height:{SECTION_GAP_DEF}px'></div>", unsafe_allow_html=True)
