# features/prioridad/view.py
from __future__ import annotations
import os
import re
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode

# 👇 Upsert centralizado (utils/gsheets)
try:
    from utils.gsheets import upsert_rows_by_id  # type: ignore
except Exception:
    upsert_rows_by_id = None

# ================== Config & helpers base ==================
SECTION_GAP_DEF = globals().get("SECTION_GAP", 30)

def _save_local(df: pd.DataFrame):
    """Guardar localmente sin romper si la carpeta no existe."""
    try:
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")
    except Exception:
        pass

def _load_local_if_exists() -> pd.DataFrame | None:
    try:
        p = os.path.join("data", "tareas.csv")
        if os.path.exists(p):
            df = pd.read_csv(p, dtype=str, keep_default_na=False).fillna("")
            return df
    except Exception:
        pass
    return None

# ====== TZ helpers (solo para filtrar por fechas) ======
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None

def to_naive_local_series(s: pd.Series) -> pd.Series:
    ser = pd.to_datetime(s, errors="coerce", utc=False)
    try:
        raw = pd.Series(s, copy=False)
        mask_ms = raw.astype(str).str.fullmatch(r"\d{12,13}")
        if mask_ms.any():
            ser.loc[mask_ms] = pd.to_datetime(raw.loc[mask_ms].astype("int64"), unit="ms", utc=True)
    except Exception:
        pass
    try:
        if getattr(ser.dt, "tz", None) is not None:
            ser = (ser.dt.tz_convert(_TZ) if _TZ else ser).dt.tz_localize(None)
    except Exception:
        try:
            ser = ser.dt.tz_localize(None)
        except Exception:
            pass
    return ser

# ================== ACL (usa el mismo esquema global que Evaluación) ==================
def _current_email_from(user: dict | None) -> str:
    acl_user = st.session_state.get("acl_user", {}) or {}
    email_from_user = (user or {}).get("email") if isinstance(user, dict) else None
    return str(acl_user.get("email") or email_from_user or "").strip().lower()

def _allowed_emails_from_secrets() -> set[str]:
    allow = set(map(str.lower,
        (st.secrets.get("acl", {}).get("editor_emails", [])
         or st.secrets.get("editors", {}).get("emails", [])
         or st.secrets.get("editor_emails", [])
         or [])
    ))
    # Permite también configurar una lista específica para Prioridad (opcional)
    try:
        raw = st.secrets.get("priority_editors", None)
        extra = set()
        if isinstance(raw, (list, tuple)):
            extra = {str(x).strip().lower() for x in raw if str(x).strip()}
        elif isinstance(raw, str) and raw.strip():
            extra = {raw.strip().lower()}
        allow |= extra
    except Exception:
        pass
    # Fallback por variable de entorno (separada por comas)
    env = os.environ.get("PRIORITY_EDITORS", "")
    if env.strip():
        allow |= {e.strip().lower() for e in env.split(",") if e.strip()}
    return allow

def _is_editor(user: dict | None) -> bool:
    acl_user = st.session_state.get("acl_user", {}) or {}
    can_edit_all = bool(acl_user.get("can_edit_all_tabs", False))
    email = _current_email_from(user)
    allow = _allowed_emails_from_secrets()
    return can_edit_all or (email and email in allow)

# ================== UI ==================
def render(user: dict | None = None):
    # =========================== PRIORIDAD ===============================
    st.session_state.setdefault("pri_visible", True)

    # Anchos de columnas (coherentes con otras secciones)
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    # ---------- Barra superior (wrapper del topbar) ----------
    st.markdown('<div class="topbar-pri"></div>', unsafe_allow_html=True)

    if st.session_state["pri_visible"]:
        IS_EDITOR = _is_editor(user)

        # --- contenedor local + css ---
        st.markdown('<div id="pri-section">', unsafe_allow_html=True)
        st.markdown(
            """
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
            color: #A7F3D0 !important;
            opacity: 1 !important;
            visibility: visible !important;
          }

          /* ===== Paleta jade ===== */
          :root{
            --pri-pill: #49BEA9;        /* jade pastel para la píldora */
            --pri-help-bg: #C8EBE5;     /* jade muy claro para franja */
            --pri-help-border: #A3DED3; /* borde jade claro */
            --pri-help-text: #0F766E;   /* texto verde legible */
          }

          /* Píldora jade pastel (mismo ancho que "Área") */
          .pri-pill{
            width:100%; height:38px; border-radius:12px;
            display:flex; align-items:center; justify-content:flex-start; gap:8px;
            background: var(--pri-pill); color:#fff; font-weight:600;
            padding: 8px 12px; box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06);
          }

          /* Franja de ayuda */
          .help-strip-pri{
            background: var(--pri-help-bg);
            border: 2px dotted var(--pri-help-border);
            color: var(--pri-help-text);
            border-radius: 10px; padding: 8px 12px;
            margin: 8px 0 12px 0;
          }
        </style>
        """,
            unsafe_allow_html=True,
        )

        # ===== Píldora SOLO ancho "Área" =====
        _pill_area, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with _pill_area:
            st.markdown('<div class="pri-pill">🏷️&nbsp;Prioridad</div>', unsafe_allow_html=True)

        # ===== Texto de ayuda =====
        st.markdown(
            '<div class="help-strip-pri">Edita la columna <b>Prioridad</b> (solo responsables autorizados). '
            'Luego presiona <b>🏷️ Dar prioridad</b> para guardar en <i>TareasRecientes</i>.</div>',
            unsafe_allow_html=True,
        )

        # ====== DATA BASE ======
        if "df_main" not in st.session_state or not isinstance(st.session_state["df_main"], pd.DataFrame):
            df_local = _load_local_if_exists()
            st.session_state["df_main"] = df_local if isinstance(df_local, pd.DataFrame) else pd.DataFrame()

        base = st.session_state["df_main"].copy()
        if base is None or base.empty:
            base = pd.DataFrame(columns=["Id","Área","Fase","Responsable","Tarea","Prioridad","Fecha Vencimiento","Hora Vencimiento"])

        # Asegurar columnas clave
        for c in ["Id","Área","Fase","Responsable","Tarea","Prioridad","Fecha Vencimiento","Hora Vencimiento"]:
            if c not in base.columns:
                base[c] = ""

        # ===== FILTROS (como la imagen) =====
        # Min/max de fecha (preferimos Fecha Vencimiento; fallback otras)
        def _first_valid_date_series(df: pd.DataFrame) -> pd.Series:
            for col in ["Fecha Vencimiento", "Fecha inicio", "Fecha Registro", "Fecha"]:
                if col in df.columns:
                    s = to_naive_local_series(df[col])
                    if s.notna().any():
                        return s
            return pd.Series([], dtype="datetime64[ns]")

        dates_all = _first_valid_date_series(base)
        if dates_all.empty:
            today = pd.Timestamp.today().normalize().date()
            min_date = today
            max_date = today
        else:
            min_date = dates_all.min().date()
            max_date = dates_all.max().date()

        with st.form("pri_filtros_v1", clear_on_submit=False):
            c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

            # Área
            areas_all = st.session_state.get(
                "AREAS_OPC",
                ["Jefatura", "Gestión", "Metodología", "Base de datos", "Monitoreo", "Capacitación", "Consistencia"],
            )
            area_sel = c_area.selectbox("Área", ["Todas"] + areas_all, index=0, key="pri_area")

            # Fase
            fases_all = sorted([x for x in base.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            fase_sel = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="pri_fase")

            # Responsable (multiselect con dependencia de área/fase)
            df_resp_src = base.copy()
            if area_sel != "Todas":
                df_resp_src = df_resp_src[df_resp_src.get("Área", "").astype(str) == area_sel]
            if fase_sel != "Todas" and "Fase" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == fase_sel]
            responsables_all = sorted(
                [x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"]
            )
            resp_multi = c_resp.multiselect("Responsable", options=responsables_all, default=[], placeholder="Selecciona responsable(s)")

            # Fechas (siempre visibles)
            f_desde = c_desde.date_input("Desde", value=min_date, min_value=min_date, max_value=max_date, key="pri_desde")
            f_hasta = c_hasta.date_input("Hasta", value=max_date, min_value=min_date, max_value=max_date, key="pri_hasta")

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
                do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

        # ===== Vista filtrada =====
        cols_order = ["Id","Área","Fase","Responsable","Tarea","Prioridad","Fecha Vencimiento","Hora Vencimiento"]
        view = base.reindex(columns=cols_order).copy()
        view["Id"] = view["Id"].astype(str)

        if do_buscar:
            if area_sel != "Todas":
                view = view[view.get("Área", "").astype(str) == area_sel]
            if fase_sel != "Todas" and "Fase" in view.columns:
                view = view[view["Fase"].astype(str) == fase_sel]
            if resp_multi:
                view = view[view.get("Responsable", "").astype(str).isin(resp_multi)]
            # rango de fechas sobre Fecha Vencimiento (si existe)
            if "Fecha Vencimiento" in view.columns:
                fv = to_naive_local_series(view["Fecha Vencimiento"])
                if f_desde is not None:
                    view = view[fv >= pd.to_datetime(f_desde)]
                if f_hasta is not None:
                    view = view[fv <= (pd.to_datetime(f_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

        # ===== Snapshot previo para detectar cambios en Prioridad =====
        try:
            st.session_state["_pri_prev"] = view[["Id", "Prioridad"]].copy()
        except Exception:
            st.session_state["_pri_prev"] = pd.DataFrame(columns=["Id", "Prioridad"])

        # ===== Grid (solo editar Prioridad y solo si IS_EDITOR) =====
        grid_options = {
            "columnDefs": [
                {"field": "Id", "headerName": "Id", "editable": False, "minWidth": 100},
                {"field": "Área", "headerName": "Área", "editable": False, "minWidth": 140},
                {"field": "Fase", "headerName": "Fase", "editable": False, "minWidth": 180},
                {"field": "Responsable", "headerName": "Responsable", "editable": False, "minWidth": 220},
                {"field": "Tarea", "headerName": "Tarea", "editable": False, "minWidth": 300},
                {
                    "field": "Prioridad",
                    "headerName": "Prioridad",
                    "editable": bool(IS_EDITOR),
                    "minWidth": 140,
                    "cellEditor": "agSelectCellEditor",
                    "cellEditorParams": {"values": ["", "Baja", "Media", "Alta"]},
                },
                {"field": "Fecha Vencimiento", "headerName": "Fecha límite", "editable": False, "minWidth": 150},
                {"field": "Hora Vencimiento", "headerName": "Hora límite", "editable": False, "minWidth": 130},
            ],
            "defaultColDef": {
                "sortable": False,
                "filter": False,
                "floatingFilter": False,
                "wrapText": False,
                "autoHeight": False,
                "resizable": True,
            },
        }

        grid_resp = AgGrid(
            view,
            key="grid_prioridad",
            gridOptions=grid_options,
            theme="streamlit",
            height=420,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=(
                GridUpdateMode.MODEL_CHANGED
                | GridUpdateMode.FILTERING_CHANGED
                | GridUpdateMode.SORTING_CHANGED
                | GridUpdateMode.VALUE_CHANGED
            ),
            allow_unsafe_jscode=True,
        )

        # Detectar cambios en Prioridad y consolidar en df_main
        try:
            edited = grid_resp["data"]
            new_df = None
            if isinstance(edited, list):
                new_df = pd.DataFrame(edited)
            elif hasattr(grid_resp, "data"):
                new_df = pd.DataFrame(grid_resp.data)

            changed_ids = set()
            try:
                prev = st.session_state.get("_pri_prev")
                if isinstance(prev, pd.DataFrame) and new_df is not None:
                    a = prev.copy()
                    b = new_df.reindex(columns=["Id", "Prioridad"]).copy()
                    a["Id"] = a["Id"].astype(str)
                    b["Id"] = b["Id"].astype(str)
                    prev_map = a.set_index("Id")
                    curr_map = b.set_index("Id")
                    common = prev_map.index.intersection(curr_map.index)
                    if len(common):
                        dif_mask = (
                            prev_map["Prioridad"].fillna("").astype(str).ne(
                                curr_map["Prioridad"].fillna("").astype(str)
                            )
                        )
                        changed_ids.update(common[dif_mask].tolist())
            except Exception:
                pass
            st.session_state["_pri_changed_ids"] = sorted(changed_ids)

            # Aplicar cambios a df_main (solo Prioridad)
            if new_df is not None and "Id" in new_df.columns:
                base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                if "Id" in base_full.columns:
                    base_full["Id"] = base_full["Id"].astype(str)
                    new_df["Id"] = new_df["Id"].astype(str)
                    base_idx = base_full.set_index("Id")
                    upd_idx = new_df.set_index("Id")
                    if "Prioridad" not in base_idx.columns:
                        base_idx["Prioridad"] = ""
                    base_idx.update(upd_idx[["Prioridad"]])
                    st.session_state["df_main"] = base_idx.reset_index()
                else:
                    st.session_state["df_main"] = new_df
                try:
                    _save_local(st.session_state["df_main"].copy())
                except Exception:
                    pass
        except Exception:
            pass

        # ===== ÚNICO botón =====
        st.markdown('<div style="padding:0 16px; border-top:2px solid #10B981; margin-top:8px;">', unsafe_allow_html=True)
        _spacer, b_action = st.columns([6.6, 1.8], gap="medium")
        with b_action:
            click = st.button("🏷️ Dar prioridad", use_container_width=True, disabled=not IS_EDITOR, key="btn_dar_prioridad")

        if click:
            try:
                ids = st.session_state.get("_pri_changed_ids", [])
                if not ids:
                    st.info("No hay cambios de 'Prioridad' para guardar.")
                else:
                    base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                    base_full["Id"] = base_full.get("Id", "").astype(str)
                    df_rows = base_full[base_full["Id"].isin(ids)].copy()

                    if upsert_rows_by_id is None:
                        _save_local(st.session_state["df_main"].copy())
                        st.warning("No se encontró utils.gsheets.upsert_rows_by_id. Se guardó localmente.")
                    else:
                        ss_url = (
                            st.secrets.get("gsheets_doc_url")
                            or (st.secrets.get("gsheets", {}) or {}).get("spreadsheet_url")
                            or (st.secrets.get("sheets", {}) or {}).get("sheet_url")
                        )
                        ws_name = (st.secrets.get("gsheets", {}) or {}).get("worksheet", "TareasRecientes")
                        res = upsert_rows_by_id(ss_url=ss_url, ws_name=ws_name, df=df_rows, ids=[str(x) for x in ids])
                        if res.get("ok"):
                            st.success(res.get("msg", "Actualizado."))
                        else:
                            st.warning(res.get("msg", "No se pudo actualizar."))
            except Exception as e:
                st.warning(f"No se pudo guardar prioridad: {e}")

        st.markdown("</div>", unsafe_allow_html=True)  # cierre de la botonera
        st.markdown("</div>", unsafe_allow_html=True)  # cierre de #pri-section

        # Separación final
        st.markdown(f"<div style='height:{SECTION_GAP_DEF}px'></div>", unsafe_allow_html=True)
