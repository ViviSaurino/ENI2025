# features/prioridad/view.py
from __future__ import annotations
import os
from datetime import date
import re
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

# ===== ACL helpers (solo visibilidad/alcance; edición se mantiene con _is_priority_editor) =====
try:
    from shared import apply_scope  # type: ignore
except Exception:
    def apply_scope(df, user=None):
        return df  # fallback no-op

def _get_display_name() -> str:
    """Nombre visible del usuario (para match con 'Responsable')."""
    acl_user = st.session_state.get("acl_user", {}) or {}
    return (
        acl_user.get("display")
        or st.session_state.get("user_display_name", "")
        or acl_user.get("name", "")
        or (st.session_state.get("user") or {}).get("name", "")
        or ""
    )

def _is_super_viewer(user: dict | None = None) -> bool:
    """
    Solo Vivi y Enrique (o flag can_edit_all_tabs) pueden ver TODAS las tareas
    en esta pestaña. El resto ve solo sus tareas.
    """
    acl_user = st.session_state.get("acl_user", {}) or {}
    if bool(acl_user.get("can_edit_all_tabs", False)):
        return True
    dn = (_get_display_name() or "").strip().lower()
    return dn.startswith("vivi") or dn.startswith("enrique")

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

# ====== ACL por correo (para edición de prioridad) ======
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
    """
    Lee lista de correos permitidos desde secrets:
      - acl.editor_emails (preferido)
      - editors.emails
      - editor_emails
    Fallbacks: PRIORITY_EDITORS (env) y lista fija (Vivi/Enrique).
    """
    allow: set[str] = set()
    try:
        allow = {
            *(str(x).strip().lower() for x in (
                st.secrets.get("acl", {}).get("editor_emails", [])
                or st.secrets.get("editors", {}).get("emails", [])
                or st.secrets.get("editor_emails", [])
                or []
            ) if str(x).strip())
        }
    except Exception:
        allow = set()
    if not allow:
        env = os.environ.get("PRIORITY_EDITORS", "")
        if env.strip():
            allow = {e.strip().lower() for e in env.split(",") if e.strip()}
    if not allow:
        allow = {
            "enrique.oyola@inei.gob.pe",
            "eoyolara@gmail.com",
            "viviansg18@gmail.com",
            "stephanysg1812@gmail.com",
        }
    return allow

def _is_priority_editor(user: dict | None = None) -> bool:
    """True solo si el email está en la lista de editores o tiene can_edit_all_tabs."""
    email, _ = _get_current_email_and_name(user)
    email = (email or "").strip().lower()
    acl_user = st.session_state.get("acl_user", {}) or {}
    can_all = bool(acl_user.get("can_edit_all_tabs", False))
    allow = _allowed_editors_from_secrets()
    return can_all or (bool(email) and email in allow)

# ===== Helpers =====
def _first_valid_date_series(df: pd.DataFrame) -> pd.Series:
    for col in ["Fecha inicio", "Fecha Vencimiento", "Fecha Registro", "Fecha"]:
        if col in df.columns:
            s = pd.to_datetime(df[col], errors="coerce")
            if s.notna().any():
                return s
    return pd.Series([], dtype="datetime64[ns]")

# Normalización y emojis
EMO_MAP = {
    "urgente": "🚨",
    "alto": "🔴", "alta": "🔴",
    "medio": "🟡", "media": "🟡",
    "bajo": "🔵", "baja": "🔵",
    "": ""
}
CHOICES_EDIT_EMO = ["", "🚨 Urgente", "🔴 Alto", "🟡 Medio", "🔵 Bajo"]

def _strip_emoji(txt: str) -> str:
    if not isinstance(txt, str):
        return ""
    return re.sub(r"^[^\w]*", "", txt).strip()

def _norm_pri(txt: str) -> str:
    """Devuelve una etiqueta canónica sin emoji: Urgente, Alto, Medio, Bajo."""
    t = (_strip_emoji(txt) or "").strip().lower()
    if t in ("alta", "alto"):
        return "Alto"
    if t in ("media", "medio"):
        return "Medio"
    if t in ("baja", "bajo"):
        return "Bajo"
    if t == "urgente":
        return "Urgente"
    # por defecto: Alto si viene vacío/indefinido en 'actual'
    return "Alto" if not t else t.title()

def _display_with_emoji(label: str) -> str:
    """Agrega emoji a la etiqueta canónica."""
    key = (label or "").strip().lower()
    return f"{EMO_MAP.get(key, '')} {label}".strip()

def render(user: dict | None = None):
    # =========================== PRIORIDAD ===============================
    st.session_state.setdefault("pri_visible", True)

    # ---------- Barra superior ----------
    A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60
    st.markdown('<div class="topbar-pri">', unsafe_allow_html=True)
    c_pill_p, _ = st.columns([A, Fw + T_width + D + R + C], gap="medium")
    with c_pill_p:
        st.markdown("", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state["pri_visible"]:

        # === 🔐 ACL ===
        IS_EDITOR = _is_priority_editor(user=user)

        # --- contenedor + css ---
        st.markdown('<div id="pri-section">', unsafe_allow_html=True)
        st.markdown("""
        <style>
          #pri-section .stButton > button { width: 100% !important; }
          #pri-section .ag-body-horizontal-scroll,
          #pri-section .ag-center-cols-viewport { overflow-x: auto !important; }

          #pri-section .ag-theme-alpine .ag-header,
          #pri-section .ag-theme-streamlit .ag-header{
            height: 44px !important; min-height: 44px !important;
          }

          #pri-section .ag-theme-alpine{ --ag-font-weight: 400; }
          #pri-section .ag-theme-streamlit{ --ag-font-weight: 400; }

          #pri-section .ag-theme-alpine .ag-header-cell-label,
          #pri-section .ag-theme-alpine .ag-header-cell-text,
          #pri-section .ag-theme-streamlit .ag-header-cell-label,
          #pri-section .ag-theme-streamlit .ag-header-cell-text{
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Inter", "Helvetica Neue", Arial, sans-serif !important;
            font-weight: 400 !important; color: #A7F3D0 !important;
          }

          :root{
            --pri-pill: #49BEA9;
            --pri-help-bg: #C8EBE5;
            --pri-help-border: #A3DED3;
            --pri-help-text: #0F766E;
          }
          .pri-pill{
            width:100%; height:38px; border-radius:12px;
            display:flex; align-items:center; gap:8px;
            background: var(--pri-pill); color:#fff; font-weight:600;
            padding: 8px 12px; box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06);
          }
          .help-strip-pri{
            background: var(--pri-help-bg);
            border: 2px dotted var(--pri-help-border);
            color: var(--pri-help-text);
            border-radius: 10px; padding: 8px 12px; margin: 8px 0 12px 0;
          }
        </style>
        """, unsafe_allow_html=True)

        # ====== DATA BASE ======
        if "df_main" not in st.session_state or not isinstance(st.session_state["df_main"], pd.DataFrame):
            df_local = _load_local_if_exists()
            st.session_state["df_main"] = df_local if isinstance(df_local, pd.DataFrame) else pd.DataFrame()

        # Píldora
        _pill_area, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with _pill_area:
            st.markdown('<div class="pri-pill">🏷️&nbsp;Prioridad</div>', unsafe_allow_html=True)

        st.markdown(
            '<div class="help-strip-pri">Edita la columna <b>Prioridad a modificar</b> (solo responsables autorizados). '
            'Luego presiona <b>🏷️ Dar prioridad</b> para guardar en <i>TareasRecientes</i>.</div>',
            unsafe_allow_html=True
        )

        # ====== FILTROS ======
        df_all = st.session_state["df_main"].copy()
        if df_all is None or df_all.empty:
            df_all = pd.DataFrame(columns=["Id","Área","Fase","Responsable","Tarea","Prioridad"])

        # 🔒 VISIBILIDAD por usuario: solo Vivi/Enrique ven todo; el resto solo lo suyo.
        me = _get_display_name().strip()
        if not _is_super_viewer(user=user):
            # 1) Si tienes reglas externas, aplícalas
            df_all = apply_scope(df_all, user=st.session_state.get("acl_user"))
            # 2) Filtro por Responsable contiene mi nombre (case-insensitive)
            if "Responsable" in df_all.columns and me:
                df_all = df_all[df_all["Responsable"].astype(str).str.contains(me, case=False, na=False)]
        else:
            # Super viewer: toggle para ver todas o solo propias
            ver_todas = st.toggle("👀 Ver todas las tareas", value=True, key="pri_ver_todas")
            if (not ver_todas) and "Responsable" in df_all.columns and me:
                df_all = df_all[df_all["Responsable"].astype(str).str.contains(me, case=False, na=False)]

        dates_all = _first_valid_date_series(df_all)
        if dates_all.empty:
            today = date.today()
            min_date = today; max_date = today
        else:
            min_date = dates_all.min().date()
            max_date = dates_all.max().date()

        with st.form("pri_filtros_v1", clear_on_submit=False):
            c_area, c_fase, c_resp, c_desde, c_hasta, c_buscar = st.columns([A, Fw, T_width, D, R, C], gap="medium")

            AREAS_OPC = st.session_state.get(
                "AREAS_OPC",
                ["Jefatura", "Gestión", "Metodología", "Base de datos", "Monitoreo", "Capacitación", "Consistencia"],
            )
            pri_area = c_area.selectbox("Área", ["Todas"] + AREAS_OPC, index=0, key="pri_area")

            fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            pri_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0, key="pri_fase")

            df_resp_src = df_all.copy()
            if pri_area != "Todas":
                df_resp_src = df_resp_src[df_resp_src.get("Área", "").astype(str) == pri_area]
            if pri_fase != "Todas" and "Fase" in df_resp_src.columns:
                df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == pri_fase]
            responsables_all = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])

            pri_resp = c_resp.multiselect("Responsable", options=responsables_all, default=[], placeholder="Selecciona responsable(s)")
            pri_desde = c_desde.date_input("Desde", value=min_date, min_value=min_date, max_value=max_date, key="pri_desde")
            pri_hasta = c_hasta.date_input("Hasta",  value=max_date, min_value=min_date, max_value=max_date, key="pri_hasta")

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
                pri_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

        df_filtrado = df_all.copy()
        base_fecha_col = "Fecha inicio" if "Fecha inicio" in df_filtrado.columns else ("Fecha Vencimiento" if "Fecha Vencimiento" in df_filtrado.columns else None)
        if pri_do_buscar:
            if pri_area != "Todas":
                df_filtrado = df_filtrado[df_filtrado.get("Área", "").astype(str) == pri_area]
            if pri_fase != "Todas" and "Fase" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == pri_fase]
            if pri_resp:
                df_filtrado = df_filtrado[df_filtrado.get("Responsable", "").astype(str).isin(pri_resp)]
            if base_fecha_col:
                fcol = pd.to_datetime(df_filtrado[base_fecha_col], errors="coerce")
                if pri_desde is not None:
                    df_filtrado = df_filtrado[fcol >= pd.to_datetime(pri_desde)]
                if pri_hasta is not None:
                    df_filtrado = df_filtrado[fcol <= (pd.to_datetime(pri_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

        # ====== Preparar vista: Prioridad actual / a modificar ======
        base = df_filtrado.copy()
        for c in ["Id","Área","Fase","Responsable","Tarea","Prioridad"]:
            if c not in base.columns:
                base[c] = ""

        # Generar columnas nuevas
        cur_norm = base["Prioridad"].astype(str).map(_norm_pri)
        cur_disp = cur_norm.map(_display_with_emoji)
        cur_disp = cur_disp.mask(cur_disp.eq(""), _display_with_emoji("Alto"))  # por defecto 🔴 Alta

        view = pd.DataFrame({
            "Id": base["Id"].astype(str),
            "Área": base["Área"].astype(str),
            "Fase": base["Fase"].astype(str),
            "Responsable": base["Responsable"].astype(str),
            "Tarea": base["Tarea"].astype(str),
            "Prioridad actual": cur_disp,
            "Prioridad a modificar": ""  # editable
        })

        # Snapshot previo (para detectar cambios sobre 'a modificar')
        st.session_state["_pri_prev"] = view[["Id","Prioridad actual","Prioridad a modificar"]].copy()

        # ===== GRID =====
        grid_options = {
            "columnDefs": [
                {"field": "Id", "headerName": "Id", "editable": False, "minWidth": 100},
                {"field": "Área", "headerName": "Área", "editable": False, "minWidth": 140},
                {"field": "Fase", "headerName": "Fase", "editable": False, "minWidth": 180},
                {"field": "Responsable", "headerName": "Responsable", "editable": False, "minWidth": 220},
                {"field": "Tarea", "headerName": "Tarea", "editable": False, "minWidth": 300},
                {"field": "Prioridad actual", "headerName": "Prioridad actual", "editable": False, "minWidth": 160},
                {
                    "field": "Prioridad a modificar", "headerName": "Prioridad a modificar",
                    "editable": bool(IS_EDITOR), "minWidth": 190,
                    "cellEditor": "agSelectCellEditor",
                    "cellEditorParams": {"values": CHOICES_EDIT_EMO},
                },
            ],
            "defaultColDef": {
                "sortable": False, "filter": False, "floatingFilter": False,
                "wrapText": False, "autoHeight": False, "resizable": True,
            },
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

        # ===== Detectar cambios y preparar dif =====
        changed_ids = []
        edits = grid_resp.get("data", [])
        new_df = pd.DataFrame(edits) if isinstance(edits, list) else pd.DataFrame(grid_resp.data)

        if not new_df.empty:
            # normalizar ambos lados (actual vs a modificar)
            new_df["__actual_norm"] = new_df["Prioridad actual"].astype(str).map(_norm_pri)
            new_df["__nuevo_norm"] = new_df["Prioridad a modificar"].astype(str).map(_norm_pri)

            mask_changed = (new_df["__nuevo_norm"].astype(str).str.len() > 0) & (
                new_df["__nuevo_norm"].ne(new_df["__actual_norm"])
            )
            changed_ids = new_df.loc[mask_changed, "Id"].astype(str).tolist()

            # aplicar al df_main (solo en memoria, columna 'Prioridad')
            if changed_ids:
                base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                if "Id" in base_full.columns:
                    base_full["Id"] = base_full["Id"].astype(str)
                    upd_map = new_df.loc[mask_changed, ["Id","__nuevo_norm"]].set_index("Id")["__nuevo_norm"]
                    # Guardar sin emoji (etiqueta canónica)
                    base_full.loc[base_full["Id"].isin(upd_map.index), "Prioridad"] = base_full["Id"].map(upd_map).fillna(base_full.get("Prioridad"))
                    st.session_state["df_main"] = base_full
                    try:
                        _save_local(base_full.copy())
                    except Exception:
                        pass

        st.session_state["_pri_changed_ids"] = changed_ids

        # ===== ÚNICO BOTÓN =====
        st.markdown('<div style="padding:0 16px; border-top:2px solid #10B981; margin-top:8px;">', unsafe_allow_html=True)
        _spacer, b_action = st.columns([6.6, 1.8], gap="medium")
        with b_action:
            click = st.button("🏷️ Dar prioridad", use_container_width=True, disabled=not IS_EDITOR, key="btn_dar_prioridad")

        if click:
            try:
                ids = st.session_state.get("_pri_changed_ids", [])
                if not ids:
                    st.info("No hay cambios de prioridad para guardar.")
                else:
                    base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                    base_full["Id"] = base_full.get("Id","").astype(str)
                    df_rows = base_full[base_full["Id"].isin(ids)].copy()

                    if upsert_rows_by_id is None:
                        _save_local(base_full.copy())
                        st.warning("No se encontró utils.gsheets.upsert_rows_by_id. Se guardó localmente.")
                    else:
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
                st.warning(f"No se pudo guardar prioridad: {e}")

        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(f"<div style='height:{SECTION_GAP_DEF}px'></div>", unsafe_allow_html=True)
