# ============================
# Vista principal: Gestión de tareas (ENI2025)
# ============================
import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

from shared import (
    blank_row, read_local, save_local, export_excel,
    AREAS_OPC, FASES, EMO_AREA, EMO_PRIORIDAD, EMO_ESTADO, EMO_COMPLEJIDAD,
)

# ---------- Estado de visibilidad (una vez) ----------
if "_ui_bootstrap" not in st.session_state:
    st.session_state["nt_visible"]  = True   # Nueva tarea
    st.session_state["ux_visible"]  = True   # Editar estado
    st.session_state["na_visible"]  = True   # Nueva alerta
    st.session_state["pri_visible"] = False  # Prioridad
    st.session_state["eva_visible"] = False  # Evaluación
    st.session_state["_ui_bootstrap"] = True

# ---------- Helpers UI ----------
def _chev(open_: bool) -> str:
    return "▾" if open_ else "▸"

def _section_toggle(key: str, title: str, pill_class: str = "form-title"):
    st.markdown('<div class="topbar" id="ntbar">', unsafe_allow_html=True)
    col_a, col_b = st.columns([0.03, 0.97], gap="small")
    with col_a:
        def _flip():
            st.session_state[key] = not st.session_state[key]
        st.button(_chev(st.session_state.get(key, True)), key=f"tgl_{key}", help="Mostrar/ocultar", on_click=_flip)
    with col_b:
        st.markdown(f'<div class="{pill_class}">{title}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ---------- Grids específicos ----------
COLUMN_WIDTHS = {
    "Id": 140, "Área": 180, "Responsable": 200, "Tarea": 320, "Desde": 160,
    "Prioridad": 200, "Evaluación": 180
}

def _grid_options_prioridad(df):
    gob = GridOptionsBuilder.from_dataframe(df, enableRowGroup=False, enableValue=False, enablePivot=False)
    gob.configure_grid_options(
        suppressMovableColumns=True,
        domLayout="normal",
        ensureDomOrder=True,
        rowHeight=38,
        headerHeight=42
    )
    for c in ("Id","Área","Responsable","Desde","Tarea"):
        if c in df.columns:
            gob.configure_column(c, width=COLUMN_WIDTHS.get(c, 140), editable=False)
    gob.configure_column(
        "Prioridad",
        width=COLUMN_WIDTHS["Prioridad"],
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": ["Urgente","Alta","Media","Baja"]}
    )
    gob.configure_grid_options(suppressColumnVirtualisation=False)
    return gob.build()

def _grid_options_evaluacion(df):
    gob = GridOptionsBuilder.from_dataframe(df, enableRowGroup=False, enableValue=False, enablePivot=False)
    gob.configure_grid_options(
        suppressMovableColumns=True,
        domLayout="normal",
        ensureDomOrder=True,
        rowHeight=38,
        headerHeight=42
    )
    for c in ("Id","Área","Responsable","Desde","Tarea"):
        if c in df.columns:
            gob.configure_column(c, width=COLUMN_WIDTHS.get(c, 140), editable=False)
    gob.configure_column(
        "Evaluación",
        width=COLUMN_WIDTHS["Evaluación"],
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": [5,4,3,2,1]}
    )
    gob.configure_grid_options(suppressColumnVirtualisation=False)
    return gob.build()

# ---------- Render principal ----------
def render():
    df = st.session_state.get("df_main", pd.DataFrame([]))

    # ============ Sección 1: Nueva tarea ============
    _section_toggle("nt_visible", "📝  Nueva tarea", "form-title")
    if st.session_state["nt_visible"]:
        st.markdown('<div class="form-card">', unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            area = st.selectbox("Área", list(EMO_AREA.keys()), index=1)
            tarea = st.text_input("Tarea")
        with c2:
            responsable = st.text_input("Responsable")
            prioridad = st.selectbox("Prioridad", list(EMO_PRIORIDAD.keys()), index=1)
        with c3:
            estado = st.selectbox("Estado", list(EMO_ESTADO.keys()), index=0)
            complejidad = st.selectbox("Complejidad", list(EMO_COMPLEJIDAD.keys()), index=1)

        col_save, col_export = st.columns([0.25, 0.75])
        with col_save:
            if st.button("➕ Agregar a la tabla", use_container_width=True, type="primary", key="btn_add_row"):
                new = blank_row()
                new.update({
                    "Área": EMO_AREA.get(area, area),
                    "Responsable": responsable or "",
                    "Tarea": tarea or "",
                    "Prioridad": EMO_PRIORIDAD.get(prioridad, prioridad),
                    "Evaluación": None,
                    "Fecha inicio": pd.Timestamp.now().normalize()
                })
                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                st.session_state["df_main"] = df
                save_local(df)
                st.success("Tarea agregada.")
        with col_export:
            if st.button("⬇️ Exportar Excel", use_container_width=True, key="btn_export"):
                xls = export_excel(st.session_state["df_main"])
                st.download_button("Descargar ENI2025_tareas.xlsx", data=xls, file_name="ENI2025_tareas.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.markdown('</div>', unsafe_allow_html=True)

    # ============ Sección 2: Editar estado ============
    _section_toggle("ux_visible", "✏️  Editar estado", "form-title-ux")
    if st.session_state["ux_visible"]:
        st.markdown('<div class="form-card">', unsafe_allow_html=True)
        st.info("Aquí pegas tu formulario completo de **Editar estado** (el que ya tenías).")
        st.markdown('</div>', unsafe_allow_html=True)

    # ============ Sección 3: Nueva alerta ============
    _section_toggle("na_visible", "🚨  Nueva alerta", "form-title-na")
    if st.session_state["na_visible"]:
        st.markdown('<div class="form-card">', unsafe_allow_html=True)
        st.info("Aquí pegas tu formulario completo de **Nueva alerta**.")
        st.markdown('</div>', unsafe_allow_html=True)

    # ============ Sección 4: Prioridad (grid editable) ============
    _section_toggle("pri_visible", "🧭  Prioridad", "form-title-pri")
    if st.session_state["pri_visible"]:
        st.markdown('<div class="form-card" id="prior-grid">', unsafe_allow_html=True)
        cols_needed = ["Id","Área","Responsable","Desde","Tarea","Prioridad"]
        show_df = df.copy()
        for c in cols_needed:
            if c not in show_df.columns:
                show_df[c] = None
        show_df = show_df[cols_needed]
        grid = AgGrid(
            show_df,
            gridOptions=_grid_options_prioridad(show_df),
            enable_enterprise_modules=False,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            fit_columns_on_grid_load=False,
            height=380
        )
        # persistir cambios en columna Prioridad
        edited = grid["data"]
        if not edited.equals(show_df):
            df["Prioridad"] = edited["Prioridad"]
            st.session_state["df_main"] = df
            save_local(df)
        st.markdown('</div>', unsafe_allow_html=True)

    # ============ Sección 5: Evaluación (grid editable) ============
    _section_toggle("eva_visible", "📊  Evaluación", "form-title-eval")
    if st.session_state["eva_visible"]:
        st.markdown('<div class="form-card" id="eval-grid">', unsafe_allow_html=True)
        cols_needed = ["Id","Área","Responsable","Desde","Tarea","Evaluación"]
        show_df = df.copy()
        for c in cols_needed:
            if c not in show_df.columns:
                show_df[c] = None
        show_df = show_df[cols_needed]
        grid = AgGrid(
            show_df,
            gridOptions=_grid_options_evaluacion(show_df),
            enable_enterprise_modules=False,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            fit_columns_on_grid_load=False,
            height=380
        )
        edited = grid["data"]
        if not edited.equals(show_df):
            df["Evaluación"] = edited["Evaluación"]
            st.session_state["df_main"] = df
            save_local(df)
        st.markdown('</div>', unsafe_allow_html=True)

    # ============ Sección 6: Tareas recientes / Historial ============
    st.subheader("📝 Tareas recientes")
    st.caption("Tabla solo lectura (ajústala a tu gusto).")
    st.dataframe(
        st.session_state["df_main"].drop(columns=[c for c in ("__DEL__",) if c in st.session_state["df_main"].columns]),
        use_container_width=True, height=380
    )

