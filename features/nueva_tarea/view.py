from __future__ import annotations
import re
from datetime import datetime

import pandas as pd
import streamlit as st

# ============================================================
# Utilidades mínimas desde shared (blank_row, IDs, COLS, hora Lima, log_reciente)
# ============================================================
try:
    from shared import (  # type: ignore
        blank_row,
        next_id_by_person,
        make_id_prefix,
        COLS,
        now_lima_trimmed,
        log_reciente,
    )
except Exception:
    # Fallbacks mínimos si no existe shared.py
    COLS = None
    log_reciente = None  # type: ignore

    def blank_row() -> dict:
        return {}

    def _clean3(s: str) -> str:
        s = (s or "").strip().upper()
        s = re.sub(r"[^A-Z0-9\s]+", "", s)
        return re.sub(r"\s+", "", s)[:3]

    def make_id_prefix(area: str, resp: str) -> str:
        a3 = _clean3(area)
        r = (resp or "").strip().upper()
        r_first = r.split()[0] if r.split() else r
        r3 = _clean3(r_first)
        if not a3 and not r3:
            return "GEN"
        return (a3 or "GEN") + (r3 or "")

    def next_id_by_person(df: pd.DataFrame, area: str, resp: str) -> str:
        prefix = make_id_prefix(area, resp)
        if "Id" in df.columns:
            ids = df["Id"].astype(str)
            mask = ids.str.startswith(prefix + "_")
            n = int(mask.sum()) + 1
        else:
            n = len(df.index) + 1
        return f"{prefix}_{n}"

    # --- Hora local America/Lima (fallback) ---
    try:
        from zoneinfo import ZoneInfo

        _LIMA = ZoneInfo("America/Lima")

        def now_lima_trimmed():
            return datetime.now(_LIMA).replace(second=0, microsecond=0)

    except Exception:  # pragma: no cover
        def now_lima_trimmed():
            return datetime.now().replace(second=0, microsecond=0)


# ============================================================
# Wrapper SEGURO para log_reciente de shared
# ============================================================
def log_reciente_safe(*args, **kwargs):
    """
    Envuelve shared.log_reciente:
    - Si existe y funciona, lo llama.
    - Si falla o no existe, no rompe ni muestra mensajes.
    """
    try:
        if callable(log_reciente):
            return log_reciente(*args, **kwargs)
    except Exception:
        # Silenciamos cualquier error interno del log
        pass


# ============================================================
# SOLO Google Sheets (para guardar df_main en la hoja principal)
# ============================================================
try:
    from utils.gsheets import upsert_rows_by_id, open_sheet_by_url  # type: ignore
except Exception:
    upsert_rows_by_id = None
    open_sheet_by_url = None


def _get_sheet_conf():
    ss_url = (
        st.secrets.get("gsheets_doc_url")
        or (st.secrets.get("gsheets", {}) or {}).get("spreadsheet_url")
        or (st.secrets.get("sheets", {}) or {}).get("sheet_url")
    )
    ws_name = (st.secrets.get("gsheets", {}) or {}).get("worksheet", "TareasRecientes")
    return ss_url, ws_name


SECTION_GAP = globals().get("SECTION_GAP", 30)


# --- helpers de hora para esta vista ---
if "_auto_time_on_date" not in globals():

    def _auto_time_on_date():
        now = now_lima_trimmed()
        st.session_state["fi_t"] = now.time()


if "_sync_time_from_date" not in globals():

    def _sync_time_from_date():
        d = st.session_state.get("fi_d", None)
        if d is None:
            return
        try:
            d = pd.to_datetime(d).date()
        except Exception:
            return
        if d == now_lima_trimmed().date():
            st.session_state["fi_t"] = now_lima_trimmed().time()
            try:
                st.session_state["fi_t_view"] = st.session_state["fi_t"].strftime(
                    "%H:%M"
                )
            except Exception:
                st.session_state["fi_t_view"] = str(st.session_state["fi_t"])


# ==========================================================================

def render(user: dict | None = None):
    """Vista: ➕ Nueva tarea"""

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

    /* ===== Tarjeta blanca SOLO para el formulario (filtros) ===== */
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel){
        background:#FFFFFF;
        border-radius:14px;
        padding:20px 22px 22px 22px;
        margin-top:16px;
        margin-bottom:10px;
        box-shadow:0 20px 50px rgba(15,23,42,0.10);
        border:1px solid #E5E7EB;
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

    /* Pastilla “Nueva tarea” */
    .nt-pill{
      width:100%;
      height:38px;
      border-radius:12px;
      display:flex;
      align-items:center;
      justify-content:center;
      background:#A7C8F0;
      color:#ffffff;
      font-weight:700;
      box-shadow:0 6px 14px rgba(167,200,240,.35);
      user-select:none;
    }

    /* Franja de indicaciones */
    .help-strip{
      background:#FFFFFF;
      border:1px solid #E5E7EB;
      color:#0B3B76;
      padding:12px 14px;
      border-radius:14px;
      font-size:0.92rem;
      box-shadow:0 12px 30px rgba(15,23,42,0.06);
    }

    /* Botones de abajo */
    .nt-outbtn .stButton>button{
      min-height:38px !important;
      height:38px !important;
      border-radius:10px !important;
    }
    .nt-outbtn{
      margin-top: 6px;
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

    # Asegurar que "Tipo de tarea" no arranque con 'Otros' por cache previo
    if st.session_state.get("nt_tipo", "").strip().lower() == "otros":
        st.session_state["nt_tipo"] = ""
    else:
        st.session_state.setdefault("nt_tipo", "")

    _NT_SPACE = 36
    st.markdown(
        f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True
    )

    # anchos base
    A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    c_pill, _, _, _, _, _ = st.columns([A, Fw, T, D, R, C], gap="medium")
    with c_pill:
        st.markdown(
            '<div class="nt-pill"><span>📝 Nueva tarea</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True
    )

    if st.session_state.get("nt_visible", True):

        if st.session_state.pop("nt_added_ok", False):
            st.success("Agregado a Tareas recientes")

        # ===== Indicaciones (card blanco) =====
        st.markdown(
            """
        <div class="help-strip">
          <strong>Indicaciones:</strong> ✳️ Completa los campos obligatorios → pulsa <b>➕ Agregar</b> → revisa en <b>🕑 Tareas recientes</b> → confirma con <b>💾 Grabar</b> y <b>📤 Subir a Sheets</b>.
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True
        )

        # ===== Bloque de filtros / formulario (card blanco) =====
        with st.container(border=True):
            # sentinel solo para el CSS del card
            st.markdown(
                '<span id="nt-card-sentinel" style="display:none"></span>',
                unsafe_allow_html=True,
            )

            # ===== Responsable & Área desde ACL =====
            _acl = st.session_state.get("acl_user", {}) or {}
            _display_name = (
                _acl.get("display")
                or st.session_state.get("user_display_name", "")
                or _acl.get("name", "")
                or (st.session_state.get("user") or {}).get("name", "")
                or ""
            )
            if not str(st.session_state.get("nt_resp", "")).strip():
                st.session_state["nt_resp"] = _display_name

            _area_acl = (
                _acl.get("area")
                or _acl.get("Área")
                or _acl.get("area_name")
                or ""
            ).strip()
            area_fixed = (
                _area_acl if _area_acl else (AREAS_OPC[0] if AREAS_OPC else "")
            )
            st.session_state["nt_area"] = area_fixed  # para el resto del flujo

            # ===== Fases =====
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

            # ---------- FILA 1 ----------
            if _is_fase_otros:
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns(
                    [A, Fw, T, D, R, C], gap="medium"
                )
                r1c1.text_input(
                    "Área", value=area_fixed, key="nt_area_view", disabled=True
                )
                r1c2.selectbox(
                    "Fase",
                    options=FASES,
                    key="nt_fase",
                    index=FASES.index("Otros"),
                )
                r1c3.text_input(
                    "Otros (especifique)",
                    key="nt_fase_otro",
                    placeholder="Describe la fase",
                )
                r1c4.text_input(
                    "Tarea", placeholder="Describe la tarea", key="nt_tarea"
                )
                r1c5.text_input(
                    "Detalle de tarea",
                    placeholder="Información adicional (opcional)",
                    key="nt_detalle",
                )
                r1c6.text_input("Responsable", key="nt_resp", disabled=True)
            else:
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns(
                    [A, Fw, T, D, R, C], gap="medium"
                )
                r1c1.text_input(
                    "Área", value=area_fixed, key="nt_area_view", disabled=True
                )
                r1c2.selectbox(
                    "Fase",
                    options=FASES,
                    index=None,
                    placeholder="Selecciona una fase",
                    key="nt_fase",
                )
                r1c3.text_input(
                    "Tarea", placeholder="Describe la tarea", key="nt_tarea"
                )
                r1c4.text_input(
                    "Detalle de tarea",
                    placeholder="Información adicional (opcional)",
                    key="nt_detalle",
                )
                r1c5.text_input("Responsable", key="nt_resp", disabled=True)
                r1c6.selectbox(
                    "Ciclo de mejora",
                    options=["1", "2", "3", "+4"],
                    index=0,
                    key="nt_ciclo_mejora",
                )

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

            # ID preview
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

            # ---------- FILA 2 y FILA 3 ----------
            if _is_fase_otros:
                r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns(
                    [A, Fw, T, D, R, C], gap="medium"
                )
                r2c1.selectbox(
                    "Ciclo de mejora",
                    options=["1", "2", "3", "+4"],
                    index=0,
                    key="nt_ciclo_mejora",
                )
                r2c2.text_input(
                    "Tipo de tarea",
                    key="nt_tipo",
                    placeholder="Escribe el tipo de tarea",
                )
                r2c3.text_input(
                    "Estado actual",
                    value="No iniciado",
                    disabled=True,
                    key="nt_estado_view",
                )
                r2c4.selectbox(
                    "Complejidad",
                    options=["🟢 Baja", "🟡 Media", "🔴 Alta"],
                    index=0,
                    key="nt_complejidad",
                )
                r2c5.selectbox(
                    "Duración",
                    options=[
                        f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)
                    ],
                    index=0,
                    key="nt_duracion_label",
                )
                r2c6.date_input(
                    "Fecha de registro",
                    key="fi_d",
                    on_change=_auto_time_on_date,
                )
                _sync_time_from_date()

                r3c1, r3c2, _, _, _, _ = st.columns(
                    [A, Fw, T, D, R, C], gap="medium"
                )
                r3c1.text_input(
                    "Hora de registro (auto)",
                    key="fi_t_view",
                    disabled=True,
                    help="Se asigna al elegir la fecha",
                )
                r3c2.text_input(
                    "ID asignado",
                    value=id_preview,
                    disabled=True,
                    key="nt_id_preview",
                )
            else:
                r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns(
                    [A, Fw, T, D, R, C], gap="medium"
                )
                r2c1.text_input(
                    "Tipo de tarea",
                    key="nt_tipo",
                    placeholder="Escribe el tipo de tarea",
                )
                r2c2.text_input(
                    "Estado actual",
                    value="No iniciado",
                    disabled=True,
                    key="nt_estado_view",
                )
                r2c3.selectbox(
                    "Complejidad",
                    options=["🟢 Baja", "🟡 Media", "🔴 Alta"],
                    index=0,
                    key="nt_complejidad",
                )
                r2c4.selectbox(
                    "Duración",
                    options=[
                        f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)
                    ],
                    index=0,
                    key="nt_duracion_label",
                )
                r2c5.date_input(
                    "Fecha de registro",
                    key="fi_d",
                    on_change=_auto_time_on_date,
                )
                _sync_time_from_date()
                r2c6.text_input(
                    "Hora de registro",
                    key="fi_t_view",
                    disabled=True,
                    help="Se asigna al elegir la fecha",
                )

                r3c1, _, _, _, _, _ = st.columns(
                    [A, Fw, T, D, R, C], gap="medium"
                )
                r3c1.text_input(
                    "ID asignado",
                    value=id_preview,
                    disabled=True,
                    key="nt_id_preview",
                )

        # ---------- Botones: volver + agregar (misma altura) ----------
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

        # ------ Acción botón Volver ------
        if back:
            # limpiar selección de tarjeta y volver al home de Gestión de tareas
            st.session_state["home_tile"] = ""
            display_name = st.session_state.get("user_display_name", "Usuario")
            try:
                # dejamos solo auth y u en la URL (sin tile)
                st.experimental_set_query_params(auth="1", u=display_name)
            except Exception:
                pass
            st.rerun()

        # ------ Acción botón Agregar ------
        if submitted:
            try:
                df = st.session_state.get("df_main", pd.DataFrame()).copy()

                def _sanitize(
                    df_in: pd.DataFrame, target_cols=None
                ) -> pd.DataFrame:
                    df_out = df_in.copy()
                    if "DEL" in df_out.columns and "__DEL__" in df_out.columns:
                        df_out["__DEL__"] = df_out["__DEL__"].fillna(
                            False
                        ) | df_out["DEL"].fillna(False)
                        df_out = df_out.drop(columns=["DEL"])
                    elif "DEL" in df_out.columns:
                        df_out = df_out.rename(columns={"DEL": "__DEL__"})
                    df_out = df_out.loc[
                        :, ~pd.Index(df_out.columns).duplicated()
                    ].copy()
                    if not df_out.index.is_unique:
                        df_out = df_out.reset_index(drop=True)
                    if target_cols:
                        target = list(dict.fromkeys(list(target_cols)))
                        for c in target:
                            if c not in df_out.columns:
                                df_out[c] = None
                        ordered = [c for c in target] + [
                            c for c in df_out.columns if c not in target
                        ]
                        df_out = df_out.loc[:, ordered].copy()
                    return df_out

                df = _sanitize(df, COLS if COLS is not None else None)

                reg_fecha = st.session_state.get("fi_d")
                reg_hora_obj = st.session_state.get("fi_t")
                try:
                    reg_hora_txt = (
                        reg_hora_obj.strftime("%H:%M")
                        if reg_hora_obj is not None
                        else ""
                    )
                except Exception:
                    reg_hora_txt = (
                        str(reg_hora_obj) if reg_hora_obj is not None else ""
                    )

                # Fase final:
                fase_sel = st.session_state.get("nt_fase", "")
                fase_otro = (st.session_state.get("nt_fase_otro", "") or "").strip()
                if str(fase_sel).strip() == "Otros":
                    fase_final = (
                        f"Otros — {fase_otro}" if fase_otro else "Otros"
                    )
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
                        "Responsable": st.session_state.get(
                            "nt_resp", ""
                        ),
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
                        "Ciclo de mejora": st.session_state.get(
                            "nt_ciclo_mejora", ""
                        ),
                        "Detalle": st.session_state.get("nt_detalle", ""),
                    }
                )

                if str(st.session_state.get("nt_tipo", "")).strip().lower() == "otros":
                    new["Complejidad"] = st.session_state.get(
                        "nt_complejidad", ""
                    )
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

                # ======== Persistencia SOLO en Google Sheets (silenciosa) ========
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

                # ====== Log universal en Tareas recientes (usando shared.log_reciente) ======
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

                # limpiar campos
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
    st.markdown(
        f"<div style='height:{gap}px;'></div>", unsafe_allow_html=True
    )
