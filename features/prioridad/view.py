# features/prioridad/view.py 
from __future__ import annotations
import os
from datetime import date
import re
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode, JsCode

# 👇 Upsert centralizado (utils/gsheets)
try:
    from utils.gsheets import upsert_rows_by_id, open_sheet_by_url, read_df_from_worksheet  # type: ignore
except Exception:
    upsert_rows_by_id = None
    open_sheet_by_url = None
    read_df_from_worksheet = None

# ===== ACL helpers (solo visibilidad/alcance) =====
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
    """True si el email está en la lista de editores o tiene can_edit_all_tabs."""
    email, _ = _get_current_email_and_name(user)
    email = (email or "").strip().lower()
    acl_user = st.session_state.get("acl_user", {}) or {}
    can_all = bool(acl_user.get("can_edit_all_tabs", False))
    allow = _allowed_editors_from_secrets()
    return can_all or (bool(email) and email in allow)


def _is_super_priority_editor(user: dict | None = None) -> bool:
    """
    Super-editor de prioridad:
      - Vivi
      - Enrique
      - o quien tenga can_edit_all=True / can_edit_all_tabs=True
      - o quien esté en la lista de correos permitidos.
    """
    acl_user = st.session_state.get("acl_user", {}) or {}
    flag = str(acl_user.get("can_edit_all", "")).strip().lower()
    if flag in {"1", "true", "yes", "si", "sí"}:
        return True
    if bool(acl_user.get("can_edit_all_tabs", False)):
        return True
    dn = (_get_display_name() or "").strip().lower()
    if dn.startswith("vivi") or dn.startswith("enrique"):
        return True
    return _is_priority_editor(user=user)


# ===== Helpers =====
def _first_valid_date_series(df: pd.DataFrame) -> pd.Series:
    for col in ["Fecha inicio", "Fecha Vencimiento", "Fecha Registro", "Fecha"]:
        if col in df.columns:
            s = pd.to_datetime(df[col], errors="coerce")
            if s.notna().any():
                return s
    return pd.Series([], dtype="datetime64[ns]")


# Normalización y emojis (nueva paleta con 'Sin asignar')
EMO_MAP = {
    "sin asignar": "⚪",
    "urgente": "🔥",
    "media": "🟡",
    "medio": "🟡",
    "baja": "🟢",
    "bajo": "🟢",
    "": "",
}
CHOICES_EDIT_EMO = ["⚪ Sin asignar", "🔥 Urgente", "🟡 Media", "🟢 Baja"]


def _strip_emoji(txt: str) -> str:
    if not isinstance(txt, str):
        return ""
    return re.sub(r"^[^\wÁÉÍÓÚáéíóúÜüÑñ]*", "", txt).strip()


def _norm_pri(txt: str) -> str:
    """
    Devuelve una etiqueta canónica sin emoji:
    Sin asignar, Urgente, Media, Baja.
    """
    t = (_strip_emoji(txt) or "").strip().lower()

    if t in ("", "sin asignar", "sin prioridad", "ninguna"):
        return "Sin asignar"
    if t == "urgente":
        return "Urgente"
    if t in ("alta", "alto", "media", "medio"):
        # Mapeamos 'alto/alta' al nuevo nivel 'Media' para compatibilidad
        return "Media"
    if t in ("baja", "bajo"):
        return "Baja"

    # fallback: título
    return t.title()


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
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state["pri_visible"]:

        # === 🔐 ACL ===
        IS_EDITOR = _is_super_priority_editor(user=user)
        IS_SUPER_VIEWER = _is_super_viewer(user=user)

        # --- contenedor + css ---
        st.markdown('<div id="pri-section">', unsafe_allow_html=True)
        st.markdown(
            """
        <style>
          #pri-section .stButton > button { width: 100% !important; }
          #pri-section .ag-body-horizontal-scroll,
          #pri-section .ag-center-cols-viewport { overflow-x: auto !important; }

          #pri-section .ag-theme-balham .ag-header{
            height: 56px !important; min-height: 56px !important;
          }

          #pri-section .ag-theme-balham{
            --ag-font-size: 12px;
            --ag-font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Inter", "Helvetica Neue", Arial, sans-serif;
          }

          #pri-section .ag-theme-balham .ag-header-cell-label,
          #pri-section .ag-theme-balham .ag-header-cell-text{
            font-weight: 500 !important;
          }

          :root{
            --pri-pill: #A7F3D0;        /* más pastel */
            --pri-help-bg: #ECFDF5;
            --pri-help-border: #A7F3D0;
            --pri-help-text: #047857;
          }
          .pri-pill{
            width:100%; height:38px; border-radius:12px;
            display:flex; align-items:center; gap:8px;
            background: var(--pri-pill); color:#065F46; font-weight:600;
            padding: 8px 12px; box-shadow: inset 0 -2px 0 rgba(0,0,0,0.04);
          }
          .help-strip-pri{
            background: var(--pri-help-bg);
            border: 1px solid var(--pri-help-border);
            color: var(--pri-help-text);
            border-radius: 10px; padding: 8px 12px; margin: 8px 0 12px 0;
          }
        </style>
        """,
            unsafe_allow_html=True,
        )

        # ====== DATA BASE ======
        if "df_main" not in st.session_state or not isinstance(
            st.session_state["df_main"], pd.DataFrame
        ):
            df_local = _load_local_if_exists()
            st.session_state["df_main"] = (
                df_local if isinstance(df_local, pd.DataFrame) else pd.DataFrame()
            )

        # Píldora (mismo ancho que Fase)
        _pill_area, _, _, _, _, _ = st.columns([Fw, Fw, T_width, D, R, C], gap="medium")
        with _pill_area:
            st.markdown('<div class="pri-pill">🏷️&nbsp;Prioridad</div>', unsafe_allow_html=True)

        st.markdown(
            '<div class="help-strip-pri">💡 <b>Indicaciones:</b> Filtra tu tarea y revisa su prioridad. '
            "Todas las personas pueden ver este campo, pero solo responsables autorizados pueden "
            "editarlo y guardar cambios.</div>",
            unsafe_allow_html=True,
        )
        # 🔹 Un poco de espacio extra entre la píldora/ayuda y los filtros
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ====== BASE + ACL DE VISUALIZACIÓN ======
        df_all = st.session_state["df_main"].copy()
        if df_all is None or df_all.empty:
            df_all = pd.DataFrame(
                columns=["Id", "Área", "Fase", "Responsable", "Tarea", "Tipo de tarea", "Prioridad"]
            )

        # 🔒 VISIBILIDAD por usuario: solo Vivi/Enrique ven todo; el resto solo lo suyo.
        me = _get_display_name().strip()
        if not IS_SUPER_VIEWER:
            df_all = apply_scope(df_all, user=st.session_state.get("acl_user"))
            if "Responsable" in df_all.columns and me:
                df_all = df_all[
                    df_all["Responsable"].astype(str).str.contains(me, case=False, na=False)
                ]
        else:
            ver_todas = st.toggle("👀 Ver todas las tareas", value=True, key="pri_ver_todas")
            if (not ver_todas) and "Responsable" in df_all.columns and me:
                df_all = df_all[
                    df_all["Responsable"].astype(str).str.contains(me, case=False, na=False)
                ]

        if "Tipo de tarea" not in df_all.columns and "Tipo" in df_all.columns:
            df_all["Tipo de tarea"] = df_all["Tipo"]

        # ===== Estado actual calculado =====
        fi = pd.to_datetime(
            df_all.get("Fecha de inicio", df_all.get("Fecha inicio", pd.Series([], dtype=object))),
            errors="coerce",
        )
        ft = pd.to_datetime(
            df_all.get(
                "Fecha terminada", df_all.get("Fecha Terminado", pd.Series([], dtype=object))
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
            estado_calc = saved.where(~saved.isin(["", "nan", "NaN", "None"]), estado_calc)
        df_all["_ESTADO_PRI_"] = estado_calc

        estados_catalogo = [
            "No iniciado",
            "En curso",
            "Terminada",
            "Pausada",
            "Cancelada",
            "Eliminada",
        ]

        # ===== Rangos de fecha =====
        dates_all = _first_valid_date_series(df_all)
        if dates_all.empty:
            today = date.today()
            min_date = today
            max_date = today
        else:
            min_date = dates_all.min().date()
            max_date = dates_all.max().date()

        # ====== FILTROS ======
        with st.form("pri_filtros_v2", clear_on_submit=False):
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
            pri_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

            tipos_all = sorted(
                [
                    x
                    for x in df_all.get("Tipo de tarea", pd.Series([], dtype=str))
                    .astype(str)
                    .unique()
                    if x and x != "nan"
                ]
            )
            pri_tipo = c_tipo.selectbox("Tipo de tarea", ["Todos"] + tipos_all, index=0)

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
            pri_estado = (
                "Todos"
                if sel_label == "Todos"
                else [k for k, v in estado_labels.items() if v == sel_label][0]
            )

            if IS_SUPER_VIEWER:
                df_resp_src = df_all.copy()
                if pri_fase != "Todas" and "Fase" in df_resp_src.columns:
                    df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str) == pri_fase]
                if pri_tipo != "Todos" and "Tipo de tarea" in df_resp_src.columns:
                    df_resp_src = df_resp_src[
                        df_resp_src["Tipo de tarea"].astype(str) == pri_tipo
                    ]
                responsables_all = sorted(
                    [
                        x
                        for x in df_resp_src.get("Responsable", pd.Series([], dtype=str))
                        .astype(str)
                        .unique()
                        if x and x != "nan"
                    ]
                )
                pri_resp = c_resp.selectbox(
                    "Responsable", ["Todos"] + responsables_all, index=0
                )
            else:
                pri_resp = "Todos"

            pri_desde = c_desde.date_input(
                "Desde",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                key="pri_desde",
            )
            pri_hasta = c_hasta.date_input(
                "Hasta",
                value=max_date,
                min_value=min_date,
                max_value=max_date,
                key="pri_hasta",
            )

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
                pri_do_buscar = st.form_submit_button(
                    "🔍 Buscar", use_container_width=True
                )

        df_filtrado = df_all.copy()
        if pri_do_buscar:
            if IS_SUPER_VIEWER and pri_resp != "Todos" and "Responsable" in df_filtrado.columns:
                df_filtrado = df_filtrado[
                    df_filtrado["Responsable"].astype(str) == pri_resp
                ]
            if pri_fase != "Todas" and "Fase" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["Fase"].astype(str) == pri_fase]
            if pri_tipo != "Todos" and "Tipo de tarea" in df_filtrado.columns:
                df_filtrado = df_filtrado[
                    df_filtrado["Tipo de tarea"].astype(str) == pri_tipo
                ]
            if pri_estado != "Todos" and "_ESTADO_PRI_" in df_filtrado.columns:
                df_filtrado = df_filtrado[
                    df_filtrado["_ESTADO_PRI_"].astype(str) == pri_estado
                ]

            if "Fecha inicio" in df_filtrado.columns:
                fcol = pd.to_datetime(df_filtrado["Fecha inicio"], errors="coerce")
            elif "Fecha Vencimiento" in df_filtrado.columns:
                fcol = pd.to_datetime(df_filtrado["Fecha Vencimiento"], errors="coerce")
            elif "Fecha Registro" in df_filtrado.columns:
                fcol = pd.to_datetime(df_filtrado["Fecha Registro"], errors="coerce")
            else:
                fcol = pd.to_datetime(
                    df_filtrado.get("Fecha", pd.Series([], dtype=str)), errors="coerce"
                )

            if pri_desde is not None:
                df_filtrado = df_filtrado[
                    fcol.isna() | (fcol >= pd.to_datetime(pri_desde))
                ]
            if pri_hasta is not None:
                limite = (
                    pd.to_datetime(pri_hasta)
                    + pd.Timedelta(days=1)
                    - pd.Timedelta(seconds=1)
                )
                df_filtrado = df_filtrado[
                    fcol.isna() | (fcol <= limite)
                ]

        # 🔹 Espacio + subtítulo "Resultados" antes de la tabla
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        st.markdown("**Resultados**")
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # ====== Preparar vista: Prioridad ======
        base = df_filtrado.copy()
        for c in ["Id", "Responsable", "Fase", "Tipo de tarea", "Tarea", "Prioridad"]:
            if c not in base.columns:
                base[c] = ""

        cur_norm = base["Prioridad"].astype(str).map(_norm_pri)
        cur_disp = cur_norm.map(_display_with_emoji)
        # Por seguridad, si algo quedara vacío, mostramos "Sin asignar"
        cur_disp = cur_disp.mask(cur_disp.eq(""), _display_with_emoji("Sin asignar"))

        view = pd.DataFrame(
            {
                "Id": base["Id"].astype(str),
                "Responsable": base["Responsable"].astype(str),
                "Fase": base["Fase"].astype(str),
                "Tipo de tarea": base["Tipo de tarea"].astype(str),
                "Tarea": base["Tarea"].astype(str),
                "Prioridad": cur_disp,
            }
        )

        st.session_state["_pri_base_norm"] = dict(
            zip(view["Id"].astype(str), cur_norm.astype(str))
        )
        st.session_state["_pri_prev"] = view[["Id", "Prioridad"]].copy()

        # ===== Estilo colores para Prioridad =====
        priority_cell_style = JsCode(
            """
        function(p){
          const base = {
            display:'flex', alignItems:'center', justifyContent:'center',
            height:'100%', padding:'0 10px', borderRadius:'999px',
            fontWeight:'600', textAlign:'center'
          };
          const v = String(p.value || '');
          const clean = v.replace(/^[^A-Za-zÁÉÍÓÚáéíóúÜüÑñ]+/,'').trim().toLowerCase();
          if(!clean){ return {}; }
          if(clean === 'sin asignar'){
            return Object.assign({}, base, {backgroundColor:'#E5E7EB', color:'#374151'});
          }
          if(clean === 'urgente'){
            return Object.assign({}, base, {backgroundColor:'#FEE2E2', color:'#B91C1C'});
          }
          if(clean === 'media'){
            return Object.assign({}, base, {backgroundColor:'#FEF3C7', color:'#92400E'});
          }
          if(clean === 'baja'){
            return Object.assign({}, base, {backgroundColor:'#DCFCE7', color:'#166534'});
          }
          return base;
        }"""
        )

        # ===== GRID (estilo tipo Evaluación) =====
        if IS_EDITOR:
            col_defs = [
                {"field": "Id", "headerName": "Id", "editable": False, "minWidth": 80, "flex": 0},
                {
                    "field": "Responsable",
                    "headerName": "Responsable",
                    "editable": False,
                    "minWidth": 180,
                    "flex": 1,
                },
                {
                    "field": "Fase",
                    "headerName": "Fase",
                    "editable": False,
                    "minWidth": 130,
                    "flex": 1,
                },
                {
                    "field": "Tipo de tarea",
                    "headerName": "Tipo de tarea",
                    "editable": False,
                    "minWidth": 180,
                    "flex": 1,
                },
                {
                    "field": "Tarea",
                    "headerName": "📝 Tarea",
                    "editable": False,
                    "minWidth": 260,
                    "flex": 2,
                },
                {
                    "field": "Prioridad",
                    "headerName": "🏷️ Prioridad",
                    "editable": True,
                    "minWidth": 150,
                    "flex": 1,
                    "cellEditor": "agSelectCellEditor",
                    "cellEditorParams": {"values": CHOICES_EDIT_EMO},
                    "cellStyle": priority_cell_style,
                },
            ]
        else:
            col_defs = [
                {"field": "Id", "headerName": "Id", "editable": False, "minWidth": 80, "flex": 0},
                {
                    "field": "Fase",
                    "headerName": "Fase",
                    "editable": False,
                    "minWidth": 130,
                    "flex": 1,
                },
                {
                    "field": "Tipo de tarea",
                    "headerName": "Tipo de tarea",
                    "editable": False,
                    "minWidth": 180,
                    "flex": 1,
                },
                {
                    "field": "Tarea",
                    "headerName": "📝 Tarea",
                    "editable": False,
                    "minWidth": 260,
                    "flex": 2,
                },
                {
                    "field": "Prioridad",
                    "headerName": "🏷️ Prioridad",
                    "editable": False,
                    "minWidth": 150,
                    "flex": 1,
                    "cellStyle": priority_cell_style,
                },
            ]

        grid_options = {
            "columnDefs": col_defs,
            "defaultColDef": {
                "sortable": False,
                "filter": False,
                "floatingFilter": False,
                "wrapText": False,
                "autoHeight": False,
                "resizable": True,
            },
            "suppressMovableColumns": True,
            "domLayout": "normal",
            "ensureDomOrder": True,
            "rowHeight": 38,
            "headerHeight": 56,
            "suppressHorizontalScroll": False,
        }

        grid_resp = AgGrid(
            view,
            key="grid_prioridad",
            gridOptions=grid_options,
            theme="balham",
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

        # ===== Detectar cambios y preparar dif =====
        changed_ids: list[str] = []
        edits = grid_resp.get("data", [])
        new_df = (
            pd.DataFrame(edits)
            if isinstance(edits, list)
            else pd.DataFrame(grid_resp.data)
        )

        if IS_EDITOR and not new_df.empty:
            base_map = st.session_state.get("_pri_base_norm", {}) or {}
            new_df["Id"] = new_df["Id"].astype(str)

            new_df["__actual_norm"] = new_df["Id"].map(
                lambda x: _norm_pri(base_map.get(x, ""))
            )
            new_df["__nuevo_norm"] = new_df["Prioridad"].astype(str).map(_norm_pri)

            mask_changed = new_df["__nuevo_norm"].ne(new_df["__actual_norm"])
            changed_ids = new_df.loc[mask_changed, "Id"].astype(str).tolist()

            if changed_ids:
                base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                if "Id" in base_full.columns:
                    base_full["Id"] = base_full["Id"].astype(str)
                    upd_map = (
                        new_df.loc[mask_changed, ["Id", "__nuevo_norm"]]
                        .set_index("Id")["__nuevo_norm"]
                    )
                    base_full.loc[
                        base_full["Id"].isin(upd_map.index), "Prioridad"
                    ] = base_full["Id"].map(upd_map).fillna(
                        base_full.get("Prioridad")
                    )
                    st.session_state["df_main"] = base_full
                    try:
                        _save_local(base_full.copy())
                    except Exception:
                        pass

        st.session_state["_pri_changed_ids"] = changed_ids

        # ===== BOTÓN GUARDAR (solo Vivi / Enrique, sin raya verde) =====
        display_name_lc = (_get_display_name() or "").strip().lower()
        SHOW_BUTTON = display_name_lc.startswith("vivi") or display_name_lc.startswith("enrique")

        if SHOW_BUTTON:
            st.markdown(
                '<div style="padding:0 16px; margin-top:8px;">',
                unsafe_allow_html=True,
            )
            _spacer, b_action = st.columns([6.6, 1.8], gap="medium")
            with b_action:
                click = st.button(
                    "🏷️ Dar prioridad",
                    use_container_width=True,
                    disabled=not IS_EDITOR,
                    key="btn_dar_prioridad",
                )

            if click and IS_EDITOR:
                try:
                    ids = st.session_state.get("_pri_changed_ids", [])
                    if not ids:
                        st.info("No hay cambios de prioridad para guardar.")
                    else:
                        base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                        base_full["Id"] = base_full.get("Id", "").astype(str)
                        df_rows = base_full[base_full["Id"].isin(ids)].copy()

                        if upsert_rows_by_id is None:
                            _save_local(base_full.copy())
                            st.warning(
                                "No se encontró utils.gsheets.upsert_rows_by_id. "
                                "Se guardó localmente."
                            )
                        else:
                            ss_url = (
                                st.secrets.get("gsheets_doc_url")
                                or (st.secrets.get("gsheets", {}) or {}).get(
                                    "spreadsheet_url"
                                )
                                or (st.secrets.get("sheets", {}) or {}).get("sheet_url")
                            )
                            ws_name = (
                                (st.secrets.get("gsheets", {}) or {}).get(
                                    "worksheet", "TareasRecientes"
                                )
                            )
                            res = upsert_rows_by_id(
                                ss_url=ss_url,
                                ws_name=ws_name,
                                df=df_rows,
                                ids=[str(x) for x in ids],
                            )
                            if res.get("ok"):
                                st.success(res.get("msg", "Actualizado."))
                            else:
                                st.warning(res.get("msg", "No se pudo actualizar."))
                except Exception as e:
                    st.warning(f"No se pudo guardar prioridad: {e}")

            st.markdown("</div>", unsafe_allow_html=True)

        # Espacio final de sección
        st.markdown(
            f"<div style='height:{SECTION_GAP_DEF}px'></div>", unsafe_allow_html=True
        )
