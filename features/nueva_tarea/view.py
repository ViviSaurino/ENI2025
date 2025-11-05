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
        SECTION_GAP,
        _auto_time_on_date,
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

    # --- Hora local America/Lima ---
    try:
        from zoneinfo import ZoneInfo
        _LIMA = ZoneInfo("America/Lima")
        def _now_local():
            return datetime.now(_LIMA).replace(second=0, microsecond=0)
    except Exception:
        # Fallback si zoneinfo no está disponible
        def _now_local():
            from datetime import datetime
            return datetime.now().replace(second=0, microsecond=0)

    def _auto_time_on_date():
        # al elegir fecha, guardar hora local (minutos) en session_state
        now = _now_local()
        st.session_state["fi_t"] = now.time()

    # forzar hora cuando la fecha seleccionada es HOY (aunque no cambie)
    def _sync_time_from_date():
        d = st.session_state.get("fi_d", None)
        if d is None:
            return
        try:
            d = pd.to_datetime(d).date()
        except Exception:
            return
        if d == _now_local().date():
            st.session_state["fi_t"] = _now_local().time()
            try:
                st.session_state["fi_t_view"] = st.session_state["fi_t"].strftime("%H:%M")
            except Exception:
                st.session_state["fi_t_view"] = str(st.session_state["fi_t"])

# ==========================================================================

def render(user: dict | None = None):
    """Vista: ➕ Nueva tarea"""

    # ===== CSS (oculta 'Sesión', inputs 100%, estilos y botón fuera del card) =====
    st.markdown("""
    <style>
      section.main div[data-testid="stCaptionContainer"]:first-of-type{
        display:none !important;
      }
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
      .nt-pill span{ display:inline-flex; gap:8px; align-items:center; }
      .help-strip{
        background:#F3F8FF; border:1px dashed #BDD7FF; color:#0B3B76;
        padding:10px 12px; border-radius:10px; font-size:0.92rem;
      }
      .nt-outbtn .stButton>button{
        min-height:38px !important; height:38px !important; border-radius:10px !important;
      }
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

    A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60
    c_pill, _, _, _, _, _ = st.columns([A, Fw, T, D, R, C], gap="medium")
    with c_pill:
        st.markdown('<div class="nt-pill"><span>📝 Nueva tarea</span></div>', unsafe_allow_html=True)

    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    if st.session_state.get("nt_visible", True):

        # >>> MENSAJE DE CONFIRMACIÓN TRAS AGREGAR
        if st.session_state.pop("nt_added_ok", False):
            st.success("Agregado a Tareas recientes")

        st.markdown("""
        <div class="help-strip">
          ✳️ Completa los campos obligatorios → pulsa <b>➕ Agregar</b> → revisa en <b>🕑 Tareas recientes</b> y confirma con <b>💾 Grabar</b>. Si deseas editar una tarea, dirígete a la sección <b>🕑 Tareas recientes</b>.
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown('<span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

            # ============================================================
            # AJUSTE: prellenar y bloquear "Responsable" y preferir área desde roles
            # ============================================================
            _acl = st.session_state.get("acl_user", {}) or {}
            _display_name = (
                _acl.get("display_name")
                or st.session_state.get("user_display_name", "")
                or _acl.get("name", "")
                or (st.session_state.get("user") or {}).get("name", "")
                or ""
            )
            if not str(st.session_state.get("nt_resp", "")).strip():
                st.session_state["nt_resp"] = _display_name

            _area_acl = (_acl.get("area") or _acl.get("Área") or _acl.get("area_name") or "").strip()
            if _area_acl and _area_acl not in AREAS_OPC:
                AREAS_OPC.insert(0, _area_acl)
            _default_area_idx = 0
            if _area_acl:
                try:
                    _default_area_idx = AREAS_OPC.index(_area_acl)
                except ValueError:
                    _default_area_idx = 0
            # ============================================================

            # ---------- FILA 1 ----------
            # Fase: añade nuevas opciones y campo adyacente si es "Otros"
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

            # Detectamos si 'Otros' está seleccionado para ajustar el layout
            _fase_sel = st.session_state.get("nt_fase", None)
            _is_fase_otros = (str(_fase_sel).strip() == "Otros")

            if _is_fase_otros:
                # Insertamos una columna adicional junto a "Fase" sin romper el resto
                r1c1, r1c2, r1c2b, r1c3, r1c4, r1c5, r1c6 = st.columns(
                    [A, Fw, 1.60, T, D, R, C], gap="medium"
                )
                area = r1c1.selectbox("Área", options=AREAS_OPC, index=_default_area_idx, key="nt_area")
                fase = r1c2.selectbox("Fase", options=FASES, key="nt_fase",
                                      index=FASES.index("Otros"))
                r1c2b.text_input("Otros (especifique)", key="nt_fase_otro", placeholder="Describe la fase")
                tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
                r1c5.text_input("Responsable", key="nt_resp", disabled=True)
                ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")
            else:
                # Layout original (6 columnas)
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                area = r1c1.selectbox("Área", options=AREAS_OPC, index=_default_area_idx, key="nt_area")
                fase = r1c2.selectbox("Fase", options=FASES, index=None,
                                      placeholder="Selecciona una fase", key="nt_fase")
                tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
                r1c5.text_input("Responsable", key="nt_resp", disabled=True)
                ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")

            # ---------- FILA 2 ----------
            if st.session_state.get("fi_d", "___MISSING___") is None:
                st.session_state.pop("fi_d")
            if st.session_state.get("fi_t", "___MISSING___") is None:
                st.session_state.pop("fi_t")

            # >>> INICIALIZA fi_d si no existe (para que hoy no dependa de on_change)
            if "fi_d" not in st.session_state:
                if st.session_state.get("nt_skip_date_init", False):
                    # mantenerla vacía solo en el primer render post-reset
                    st.session_state.pop("nt_skip_date_init", None)
                else:
                    st.session_state["fi_d"] = _now_local().date()

            # sincroniza hora si la fecha ya es hoy antes de pintar
            _sync_time_from_date()

            r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns([A, Fw, T, D, R, C], gap="medium")

            # === Tipo de tarea: SOLO "Otros" y fijo ===
            tipo_sel = r2c1.selectbox("Tipo de tarea", options=["Otros"], index=0, key="nt_tipo", disabled=True)

            r2c2.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")

            _t = st.session_state.get("fi_t")
            _t_txt = ""
            if _t is not None:
                try:
                    _t_txt = _t.strftime("%H:%M")
                except Exception:
                    _t_txt = str(_t)
            st.session_state["fi_t_view"] = _t_txt

            _df_tmp = st.session_state.get("df_main", pd.DataFrame()).copy() if "df_main" in st.session_state else pd.DataFrame()
            prefix = make_id_prefix(st.session_state.get("nt_area", area), st.session_state.get("nt_resp", ""))
            id_preview = (next_id_by_person(_df_tmp, st.session_state.get("nt_area", area),
                           st.session_state.get("nt_resp", "")) if st.session_state.get("fi_d") else f"{prefix}_")

            is_otros = (str(st.session_state.get("nt_tipo", "")).strip().lower() == "otros")

            if is_otros:
                comp_opc = ["🟢 Baja", "🟡 Media", "🔴 Alta"]
                r2c3.selectbox("Complejidad", options=comp_opc, index=0, key="nt_complejidad")

                dur_labels = [f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)]
                r2c4.selectbox("Duración", options=dur_labels, index=0, key="nt_duracion_label")

                r2c5.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)
                _sync_time_from_date()  # re-sincroniza tras el date_input

                r2c6.text_input("Hora (auto)", key="fi_t_view", disabled=True,
                                help="Se asigna al elegir la fecha")

                r3c1, r3c2, r3c3, r3c4, r3c5, r3c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r3c1.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

            else:
                r2c3.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)
                _sync_time_from_date()  # re-sincroniza tras el date_input

                r2c4.text_input("Hora (auto)", key="fi_t_view", disabled=True,
                                help="Se asigna al elegir la fecha")
                r2c5.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")
                # r2c6 vacío

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

                df = _sanitize(df, COLS if "COLS" in globals() else None)

                reg_fecha = st.session_state.get("fi_d")
                reg_hora_obj = st.session_state.get("fi_t")
                try:
                    reg_hora_txt = reg_hora_obj.strftime("%H:%M") if reg_hora_obj is not None else ""
                except Exception:
                    reg_hora_txt = str(reg_hora_obj) if reg_hora_obj is not None else ""

                # Fase final: si es "Otros", usamos lo escrito
                fase_sel = st.session_state.get("nt_fase", "")
                fase_otro = (st.session_state.get("nt_fase_otro", "") or "").strip()
                fase_final = fase_otro if str(fase_sel).strip() == "Otros" else fase_sel

                new = blank_row()
                new.update({
                    "Área": area,
                    "Id": next_id_by_person(df, area, st.session_state.get("nt_resp", "")),
                    "Tarea": st.session_state.get("nt_tarea", ""),
                    "Tipo": st.session_state.get("nt_tipo", ""),
                    "Responsable": st.session_state.get("nt_resp", ""),  # ← queda forzado al usuario logueado
                    "Fase": fase_final,
                    "Estado": "No iniciado",
                    "Fecha": reg_fecha, "Hora": reg_hora_txt,
                    "Fecha Registro": reg_fecha, "Hora Registro": reg_hora_txt,
                    "Fecha inicio": None, "Hora de inicio": "",
                    "Fecha Terminado": None, "Hora Terminado": "",
                    "Ciclo de mejora": st.session_state.get("nt_ciclo_mejora", ""),
                    "Detalle": st.session_state.get("nt_detalle", ""),
                })

                if str(st.session_state.get("nt_tipo", "")).strip().lower() == "otros":
                    new["Complejidad"] = st.session_state.get("nt_complejidad", "")
                    lbl = st.session_state.get("nt_duracion_label", "")
                    try:
                        new["Duración"] = int(str(lbl).split()[0])
                    except Exception:
                        new["Duración"] = ""

                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                df = _sanitize(df, COLS if "COLS" in globals() else None)
                st.session_state["df_main"] = df.copy()

                # ======== PERSISTENCIA controlada por ACL (respeta dry_run/save_scope) ========
                def _persist(_df: pd.DataFrame):
                    try:
                        os.makedirs("data", exist_ok=True)
                        _df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig", mode="w")
                        return {"ok": True, "msg": "Cambios guardados."}
                    except Exception as _e:
                        return {"ok": False, "msg": f"Error al guardar: {_e}"}

                maybe_save = st.session_state.get("maybe_save")
                res = maybe_save(_persist, df.copy()) if callable(maybe_save) else _persist(df.copy())
                if not res.get("ok", False):
                    # Ej.: DRY-RUN o guardado deshabilitado
                    st.info(res.get("msg", "Guardado deshabilitado."))

                # >>> LIMPIEZA DE CAMPOS + MENSAJE + SALTO DE ESTADO
                for k in [
                    "nt_area","nt_fase","nt_fase_otro","nt_tarea","nt_detalle","nt_resp",
                    "nt_ciclo_mejora","nt_tipo","nt_complejidad","nt_duracion_label",
                    "fi_d","fi_t","fi_t_view","nt_id_preview"
                ]:
                    st.session_state.pop(k, None)
                st.session_state["nt_skip_date_init"] = True   # deja fecha en blanco tras el reset
                st.session_state["nt_added_ok"] = True         # mensaje de confirmación

                st.rerun()

            except Exception as e:
                st.error(f"No pude guardar la nueva tarea: {e}")

    gap = SECTION_GAP if 'SECTION_GAP' in globals() else 30
    st.markdown(f"<div style='height:{gap}px;'></div>", unsafe_allow_html=True)
