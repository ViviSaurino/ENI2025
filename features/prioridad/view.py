# features/prioridad/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode

# 👇 Upsert centralizado (utils/gsheets)
try:
    from utils.gsheets import upsert_rows_by_id, open_sheet_by_url, read_df_from_worksheet  # type: ignore
except Exception:
    upsert_rows_by_id = None
    open_sheet_by_url = None
    read_df_from_worksheet = None

# Fallbacks seguros
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

# ====== ACL por correo: solo Vivi y Enrique editan ======
def _get_current_email_and_name(user: dict | None = None):
    """Devuelve (email, nombre) desde `user` o session_state."""
    cand = []
    if isinstance(user, dict):
        cand += [user.get("email"), user.get("mail"), user.get("user_email")]
        cand += [user.get("name"), user.get("username")]
    acl_user = st.session_state.get("acl_user", {}) or {}
    cand += [acl_user.get("email"), acl_user.get("mail"), st.session_state.get("user_email")]
    email = next((c for c in cand if isinstance(c, str) and "@" in c), None)

    name_cand = []
    if isinstance(user, dict):
        name_cand += [user.get("name"), user.get("username")]
    name_cand += [acl_user.get("name"), acl_user.get("username")]
    name = next((c for c in name_cand if isinstance(c, str) and c.strip()), "")
    return (email or "").strip(), name.strip()

def _allowed_editors_from_secrets() -> set[str]:
    """Lee lista de correos permitidos desde secrets/env (priority_editors)."""
    allow: set[str] = set()
    try:
        raw = st.secrets.get("priority_editors", None)
        if isinstance(raw, (list, tuple)):
            allow = {str(x).strip().lower() for x in raw if str(x).strip()}
        elif isinstance(raw, str):
            allow = {raw.strip().lower()} if raw.strip() else set()
    except Exception:
        pass
    # Fallback por variable de entorno (separada por comas)
    if not allow:
        env = os.environ.get("PRIORITY_EDITORS", "")
        if env.strip():
            allow = {e.strip().lower() for e in env.split(",") if e.strip()}
    return allow

def _is_priority_editor(user: dict | None = None) -> bool:
    """True solo si el email está en la lista de editores."""
    email, name = _get_current_email_and_name(user)
    allow = _allowed_editors_from_secrets()
    if allow:
        return bool(email) and email.lower() in allow
    # Fallback ultra-suave si no configuraron secrets/env aún:
    token = f"{email} {name}".lower()
    return any(x in token for x in ("enrique", "vivi"))  # ← reemplazar al configurar secrets

def render(user: dict | None = None):
    # =========================== PRIORIDAD ===============================
    st.session_state.setdefault("pri_visible", True)

    # ---------- Barra superior (SIN botón mostrar/ocultar) ----------
    # La píldora queda a la izquierda y con el mismo ancho que "Área"
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60
    st.markdown('<div class="topbar-pri">', unsafe_allow_html=True)
    c_pill_p, _ = st.columns([A, Fw + T_width + D + R + C], gap="medium")
    with c_pill_p:
        st.markdown("", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    # ---------- fin barra superior ----------

    if st.session_state["pri_visible"]:

        # === 🔐 ACL: SOLO Vivi y Enrique (por correo) pueden editar ===
        IS_EDITOR = _is_priority_editor(user=user)

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
            color: #A7F3D0 !important;
            opacity: 1 !important;
            visibility: visible !important;
          }

          /* Colores para prioridad (por clase) */
          #pri-section .pri-low   { color:#2563eb !important; }  /* 🔵 Baja */
          #pri-section .pri-med   { color:#ca8a04 !important; }  /* 🟡 Media */
          #pri-section .pri-high  { color:#dc2626 !important; }  /* 🔴 Alta */

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
            display:flex; align-items:center;
            justify-content:flex-start; gap:8px;
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
        """, unsafe_allow_html=True)

        # ====== DATA BASE ======
        if "df_main" not in st.session_state or not isinstance(st.session_state["df_main"], pd.DataFrame):
            df_local = _load_local_if_exists()
            if isinstance(df_local, pd.DataFrame) and not df_local.empty:
                st.session_state["df_main"] = df_local
            else:
                st.session_state["df_main"] = pd.DataFrame()

        # Píldora y ayuda
        st.markdown('<div class="pri-pill">🏷️ Prioridad</div>', unsafe_allow_html=True)
        st.markdown('<div class="help-strip-pri">Edita la columna <b>Prioridad</b> (solo responsables autorizados). Luego presiona <b>Grabar</b> y <b>Subir a Sheets</b>.</div>', unsafe_allow_html=True)

        # ====== Vista mínima enfocada en Prioridad ======
        base = st.session_state["df_main"].copy()
        if base is None or base.empty:
            base = pd.DataFrame(columns=["Id","Área","Fase","Responsable","Tarea","Prioridad","Fecha Vencimiento","Hora Vencimiento"])

        # Asegurar columnas clave
        for c in ["Id","Área","Fase","Responsable","Tarea","Prioridad","Fecha Vencimiento","Hora Vencimiento"]:
            if c not in base.columns:
                base[c] = ""

        # Orden sugerido de columnas
        cols = ["Id","Área","Fase","Responsable","Tarea","Prioridad","Fecha Vencimiento","Hora Vencimiento"]
        view = base.reindex(columns=cols).copy()
        view["Id"] = view["Id"].astype(str)

        # Snapshot previo para detectar cambios en Prioridad
        try:
            st.session_state["_pri_prev"] = view[["Id","Prioridad"]].copy()
        except Exception:
            st.session_state["_pri_prev"] = pd.DataFrame(columns=["Id","Prioridad"])

        # Grid simple (editable solo Prioridad y solo si IS_EDITOR)
        grid_options = {
            "columnDefs": [
                {"field": "Id", "headerName": "Id", "editable": False, "minWidth": 100},
                {"field": "Área", "headerName": "Área", "editable": False, "minWidth": 140},
                {"field": "Fase", "headerName": "Fase", "editable": False, "minWidth": 180},
                {"field": "Responsable", "headerName": "Responsable", "editable": False, "minWidth": 220},
                {"field": "Tarea", "headerName": "Tarea", "editable": False, "minWidth": 300},
                {
                    "field": "Prioridad", "headerName": "Prioridad",
                    "editable": bool(IS_EDITOR), "minWidth": 140,
                    "cellEditor": "agSelectCellEditor",
                    "cellEditorParams": {"values": ["", "Baja", "Media", "Alta"]}
                },
                {"field": "Fecha Vencimiento", "headerName": "Fecha límite", "editable": False, "minWidth": 150},
                {"field": "Hora Vencimiento", "headerName": "Hora límite", "editable": False, "minWidth": 130},
            ],
            "defaultColDef": {
                "sortable": False, "filter": False, "floatingFilter": False,
                "wrapText": False, "autoHeight": False, "resizable": True,
            }
        }

        grid_resp = AgGrid(
            view,
            key="grid_prioridad",
            gridOptions=grid_options,
            theme="streamlit",
            height=420,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=(GridUpdateMode.MODEL_CHANGED
                         | GridUpdateMode.FILTERING_CHANGED
                         | GridUpdateMode.SORTING_CHANGED
                         | GridUpdateMode.VALUE_CHANGED),
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
                    b = new_df.reindex(columns=["Id","Prioridad"]).copy()
                    a["Id"] = a["Id"].astype(str)
                    b["Id"] = b["Id"].astype(str)
                    prev_map = a.set_index("Id")
                    curr_map = b.set_index("Id")
                    common = prev_map.index.intersection(curr_map.index)
                    if len(common):
                        dif_mask = (prev_map["Prioridad"].fillna("").astype(str)
                                    .ne(curr_map["Prioridad"].fillna("").astype(str)))
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

        # ===== Botonera =====
        st.markdown('<div style="padding:0 16px; border-top:2px solid #10B981; margin-top:8px;">', unsafe_allow_html=True)
        _sp, b_xlsx, b_save_local, b_save_sheets = st.columns([5.2, 1.6, 1.4, 2.2], gap="medium")

        with b_xlsx:
            try:
                base_out = st.session_state["df_main"].copy()
                for c in ["__SEL__","__DEL__","¿Eliminar?"]:
                    if c in base_out.columns:
                        base_out.drop(columns=[c], inplace=True, errors="ignore")
                # Export simple
                from io import BytesIO
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
                    base_out.to_excel(w, index=False, sheet_name="Tareas")
                st.download_button(
                    "⬇️ Exportar Excel",
                    data=buf.getvalue(),
                    file_name="tareas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.warning(f"No pude generar Excel: {e}")

        with b_save_local:
            if st.button("💾 Grabar", use_container_width=True):
                try:
                    _save_local(st.session_state["df_main"].copy())
                    st.success("Datos grabados en data/tareas.csv.")
                except Exception as e:
                    st.warning(f"No se pudo grabar localmente: {e}")

        # ====== 📤 Subida a Sheets usando helper centralizado ======
        with b_save_sheets:
            if st.button("📤 Subir a Sheets", use_container_width=True, disabled=not IS_EDITOR):
                try:
                    ids = st.session_state.get("_pri_changed_ids", [])
                    if not ids:
                        st.info("No hay cambios de 'Prioridad' para enviar.")
                    else:
                        base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                        base_full["Id"] = base_full.get("Id","").astype(str)
                        df_rows = base_full[base_full["Id"].isin(ids)].copy()

                        if upsert_rows_by_id is None:
                            st.warning("No se encontró utils.gsheets.upsert_rows_by_id. Revisa dependencias.")
                        else:
                            # ✅ Ajuste solicitado: helper reutilizable
                            ss_url = (st.secrets.get("gsheets_doc_url")
                                      or (st.secrets.get("gsheets",{}) or {}).get("spreadsheet_url")
                                      or (st.secrets.get("sheets",{}) or {}).get("sheet_url"))
                            ws_name = (st.secrets.get("gsheets",{}) or {}).get("worksheet","TareasRecientes")
                            res = upsert_rows_by_id(ss_url=ss_url, ws_name=ws_name, df=df_rows, ids=[str(x) for x in ids])
                            if res.get("ok"):
                                st.success(res.get("msg", "Actualizado."))
                            else:
                                st.warning(res.get("msg", "No se pudo actualizar."))
                except Exception as e:
                    st.warning(f"No se pudo subir a Sheets: {e}")

        st.markdown('</div>', unsafe_allow_html=True)
