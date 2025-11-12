from __future__ import annotations
import os
import pandas as pd
import streamlit as st

# ====== utilidades (con fallbacks seguros) ======
try:
    from shared import (
        blank_row,
        next_id_by_person,
        make_id_prefix,
        COLS,
        # SECTION_GAP  # <- no se importa: no existe en shared por defecto
        now_lima_trimmed,
        log_reciente,
    )
except Exception:
    from datetime import datetime
    import re

    def blank_row() -> dict: return {}

    def _clean3(s: str) -> str:
        s = (s or "").strip().upper()
        s = re.sub(r"[^A-Z0-9\s]+", "", s)
        return re.sub(r"\s+", "", s)[:3]

    def make_id_prefix(area: str, resp: str) -> str:
        a3 = _clean3(area)
        r = (resp or "").strip().upper()
        r_first = r.split()[0] if r.split() else r
        r3 = _clean3(r_first)
        if not a3 and not r3: return "GEN"
        return (a3 or "GEN") + (r3 or "")

    def next_id_by_person(df: pd.DataFrame, area: str, resp: str) -> str:
        prefix = make_id_prefix(area, resp)
        return f"{prefix}_{len(df.index)+1}"

    COLS = None
    SECTION_GAP = 30

    # --- Hora local America/Lima (fallback) ---
    try:
        from zoneinfo import ZoneInfo
        _LIMA = ZoneInfo("America/Lima")
        def now_lima_trimmed():
            return datetime.now(_LIMA).replace(second=0, microsecond=0)
    except Exception:
        def now_lima_trimmed():
            return datetime.now().replace(second=0, microsecond=0)

    def log_reciente(sheet, tarea_nombre: str, especialista: str = "", detalle: str = "Asignada", tab_name: str = "TareasRecientes", **kwargs):
        """
        Fallback robusto:
        - Prioriza columnas nuevas: 'Fecha de registro' / 'Hora de registro'.
        - Soporta esquema antiguo: 'Fecha Registro' / 'Hora Registro'.
        - Soporta esquema legado: 'fecha' (timestamp).
        - Si existen en la hoja, también llena:
          'Área','Fase','Tipo','Estado','Ciclo de mejora','Complejidad',
          'Duración (días)','Duración','Link de archivo'.
        """
        try:
            from uuid import uuid4
            import pandas as _pd

            ts = now_lima_trimmed()
            # fecha/hora recibidas como kwargs (preferidas)
            fecha_in = kwargs.get("fecha_reg", None)
            hora_in  = kwargs.get("hora_reg", None)

            # Normalizar fecha
            try:
                if fecha_in is None or str(fecha_in).strip().lower() in {"", "nan", "nat", "none", "null"}:
                    fecha_txt = ts.strftime("%Y-%m-%d")
                else:
                    fecha_txt = pd.to_datetime(fecha_in).strftime("%Y-%m-%d")
            except Exception:
                fecha_txt = ts.strftime("%Y-%m-%d")

            # Normalizar hora → HH:MM
            def _fmt_hhmm(v) -> str:
                if v is None:
                    return ts.strftime("%H:%M")
                try:
                    s = str(v).strip()
                    if not s:
                        return ts.strftime("%H:%M")
                    m = re.match(r"^(\d{1,2}):(\d{2})", s)
                    if m:
                        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
                    d = pd.to_datetime(s, errors="coerce", utc=False)
                    if pd.isna(d):
                        return ts.strftime("%H:%M")
                    return f"{int(d.hour):02d}:{int(d.minute):02d}"
                except Exception:
                    return ts.strftime("%H:%M")

            hora_txt = _fmt_hhmm(hora_in)
            id_std = str(kwargs.get("id_val", "")) or uuid4().hex[:10].upper()

            # Extras potenciales
            extras = {
                "Área": kwargs.get("area", ""),
                "Fase": kwargs.get("fase", ""),
                "Tipo": kwargs.get("tipo", ""),
                "Estado": kwargs.get("estado", ""),
                "Ciclo de mejora": kwargs.get("ciclo_mejora", ""),
                "Complejidad": kwargs.get("complejidad", ""),
                "Duración (días)": kwargs.get("duracion_dias", kwargs.get("duracion", "")),
                "Duración": kwargs.get("duracion", kwargs.get("duracion_dias", "")),
                "Link de archivo": kwargs.get("link_archivo", ""),
            }

            # Filas modelo (nuevo / antiguo / legado)
            row_new = {
                "Id": id_std,
                "Fecha de registro": fecha_txt,
                "Hora de registro": hora_txt,
                "Acción": "Nueva tarea",
                "Tarea": tarea_nombre or "",
                "Responsable": (especialista or "").strip(),
                "Detalle": (detalle or "").strip(),
                **extras,
            }
            row_old = {
                "Id": id_std,
                "Fecha Registro": fecha_txt,
                "Hora Registro": hora_txt,
                "Acción": "Nueva tarea",
                "Tarea": tarea_nombre or "",
                "Responsable": (especialista or "").strip(),
                "Detalle": (detalle or "").strip(),
                **extras,
            }
            row_legacy = {
                "id": id_std,
                "fecha": f"{fecha_txt} {hora_txt}",
                "accion": "Nueva tarea",
                "tarea": tarea_nombre or "",
                "especialista": (especialista or "").strip(),
                "detalle": (detalle or "").strip(),
            }

            if sheet is None:
                return

            try:
                from utils.gsheets import read_df_from_worksheet, upsert_by_id  # type: ignore
            except Exception:
                read_df_from_worksheet = None
                upsert_by_id = None

            df_exist = None
            if callable(read_df_from_worksheet):
                try:
                    df_exist = read_df_from_worksheet(sheet, tab_name)
                except Exception:
                    df_exist = None

            # Construcción del payload según columnas existentes
            if isinstance(df_exist, _pd.DataFrame) and not df_exist.empty:
                cols = list(df_exist.columns)
                payload = {}
                for c in cols:
                    if c in row_new:
                        payload[c] = row_new[c]
                    elif c in row_old:
                        payload[c] = row_old[c]
                    elif c in row_legacy:
                        payload[c] = row_legacy[c]
                    else:
                        payload[c] = ""
                payload_df = _pd.DataFrame([payload], columns=cols)
            else:
                # Si la hoja está vacía, iniciamos con el esquema nuevo
                payload_df = _pd.DataFrame([row_new])

            if callable(upsert_by_id) and ("Id" in payload_df.columns or "id" in payload_df.columns):
                id_col = "Id" if "Id" in payload_df.columns else "id"
                upsert_by_id(sheet, tab_name, payload_df, id_col=id_col)
            else:
                ws = sheet.worksheet(tab_name)
                ws.append_rows(payload_df.astype(str).values.tolist())

            try:
                st.cache_data.clear()
            except Exception:
                pass
        except Exception:
            pass

# --- helpers de hora para esta vista (si no existen aún) ---
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
                st.session_state["fi_t_view"] = st.session_state["fi_t"].strftime("%H:%M")
            except Exception:
                st.session_state["fi_t_view"] = str(st.session_state["fi_t"])

# ==========================================================================

def render(user: dict | None = None):
    """Vista: ➕ Nueva tarea"""

    # ===== CSS =====
    st.markdown("""
    <style>
      section.main div[data-testid="stCaptionContainer"]:first-of-type{ display:none !important; }
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea{ width:100% !important; }
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput>div,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox>div,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput>div,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput>div,
      div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea>div{
        width:100% !important; max-width:none !important;
      }
      .nt-pill{
        width:100%; height:38px; border-radius:12px;
        display:flex; align-items:center; justify-content:center;
        background:#A7C8F0; color:#ffffff; font-weight:700;
        box-shadow:0 6px 14px rgba(167,200,240,.35);
        user-select:none;
      }
      .help-strip{
        background:#F3F8FF; border:1px dashed #BDD7FF; color:#0B3B76;
        padding:10px 12px; border-radius:10px; font-size:0.92rem;
      }
      .nt-outbtn .stButton>button{ min-height:38px !important; height:38px !important; border-radius:10px !important; }
      .nt-outbtn{ margin-top: 6px; }
    </style>
    """, unsafe_allow_html=True)

    # ===== Datos =====
    if "AREAS_OPC" not in globals():
        globals()["AREAS_OPC"] = [
            "Jefatura","Gestión","Metodología","Base de datos","Capacitación","Monitoreo","Consistencia"
        ]
    st.session_state.setdefault("nt_visible", True)

    _NT_SPACE = 36
    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    # anchos base
    A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    c_pill, _, _, _, _, _ = st.columns([A, Fw, T, D, R, C], gap="medium")
    with c_pill:
        st.markdown('<div class="nt-pill"><span>📝 Nueva tarea</span></div>', unsafe_allow_html=True)

    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    if st.session_state.get("nt_visible", True):

        if st.session_state.pop("nt_added_ok", False):
            st.success("Agregado a Tareas recientes")

        # ===== Indicaciones (una sola línea, con 📤) =====
        st.markdown("""
        <div class="help-strip">
          <strong>Indicaciones:</strong> ✳️ Completa los campos obligatorios → pulsa <b>➕ Agregar</b> → revisa en <b>🕑 Tareas recientes</b> → confirma con <b>💾 Grabar</b> y <b>📤 Subir a Sheets</b>.
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown('<span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

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

            _area_acl = (_acl.get("area") or _acl.get("Área") or _acl.get("area_name") or "").strip()
            area_fixed = _area_acl if _area_acl else (AREAS_OPC[0] if AREAS_OPC else "")
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
            _is_fase_otros = (str(_fase_sel).strip() == "Otros")

            # ---------- FILA 1 ----------
            if _is_fase_otros:
                # Orden y anchos para que "Otros, Tarea, Detalle, Responsable"
                # coincidan con los anchos de "Estado, Complejidad, Duración, Fecha"
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r1c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
                r1c2.selectbox("Fase", options=FASES, key="nt_fase", index=FASES.index("Otros"))
                r1c3.text_input("Otros (especifique)", key="nt_fase_otro", placeholder="Describe la fase")
                tarea = r1c4.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                r1c5.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
                r1c6.text_input("Responsable", key="nt_resp", disabled=True)
            else:
                # Layout original (con Área fijo)
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r1c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
                r1c2.selectbox("Fase", options=FASES, index=None, placeholder="Selecciona una fase", key="nt_fase")
                tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
                r1c5.text_input("Responsable", key="nt_resp", disabled=True)
                ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")

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
            _df_tmp = st.session_state.get("df_main", pd.DataFrame()).copy() if "df_main" in st.session_state else pd.DataFrame()
            prefix = make_id_prefix(st.session_state.get("nt_area", area_fixed), st.session_state.get("nt_resp", ""))
            id_preview = (next_id_by_person(
                _df_tmp,
                st.session_state.get("nt_area", area_fixed),
                st.session_state.get("nt_resp", "")
            ) if st.session_state.get("fi_d") else f"{prefix}_")

            # ---------- FILA 2 ----------
            if _is_fase_otros:
                # Ciclo, Tipo (editable), Estado, Complejidad, Duración, Fecha
                r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                ciclo_mejora = r2c1.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")
                # *** Cambio: tipo editable (en blanco por defecto) ***
                r2c2.text_input("Tipo de tarea", key="nt_tipo", placeholder="Escribe el tipo de tarea")
                r2c3.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")
                r2c4.selectbox("Complejidad", options=["🟢 Baja", "🟡 Media", "🔴 Alta"], index=0, key="nt_complejidad")
                r2c5.selectbox("Duración", options=[f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)], index=0, key="nt_duracion_label")
                r2c6.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date); _sync_time_from_date()

                # ---------- FILA 3 ----------
                r3c1, r3c2, r3c3, r3c4, r3c5, r3c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r3c1.text_input("Hora (auto)", key="fi_t_view", disabled=True, help="Se asigna al elegir la fecha")
                r3c2.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")
                # r3c3..r3c6 vacíos (alineación)
            else:
                # Layout original F2/F3 con tipo editable
                r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                # *** Cambio: tipo editable (en blanco por defecto) ***
                r2c1.text_input("Tipo de tarea", key="nt_tipo", placeholder="Escribe el tipo de tarea")
                r2c2.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")
                r2c3.selectbox("Complejidad", options=["🟢 Baja", "🟡 Media", "🔴 Alta"], index=0, key="nt_complejidad")
                r2c4.selectbox("Duración", options=[f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)], index=0, key="nt_duracion_label")
                r2c5.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date); _sync_time_from_date()
                r2c6.text_input("Hora (auto)", key="fi_t_view", disabled=True, help="Se asigna al elegir la fecha")

                r3c1, r3c2, r3c3, r3c4, r3c5, r3c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r3c1.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

        # ---------- Botón agregar ----------
        left_space, right_btn = st.columns([A + Fw + T + D + R, C], gap="medium")
        with right_btn:
            st.markdown('<div class="nt-outbtn">', unsafe_allow_html=True)
            submitted = st.button("➕ Agregar", use_container_width=True, key="btn_agregar")
            st.markdown('</div>', unsafe_allow_html=True)

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
                    df_out = df
