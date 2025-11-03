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
            return datetime.now().replace(second=0, microsecond=0)

    def _auto_time_on_date():
        # al elegir fecha, guardar hora local (minutos) en session_state
        now = _now_local()
        st.session_state["fi_t"] = now.time()

# ==========================================================================

def render(user: dict | None = None):
    """Vista: ➕ Nueva tarea"""

    # ===== CSS (oculta 'Sesión', inputs 100%, estilos y botón fuera del card) =====
    st.markdown("""
    <style>
      /* Ocultar el rótulo 'Sesión: ...' bajo el título (primer caption de la página) */
      section.main div[data-testid="stCaptionContainer"]:first-of-type{
        display:none !important;
      }

      /* Inputs al 100% solo dentro de este card */
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

      /* Píldora celeste con menos curvatura */
      .nt-pill{
        width:100%; height:38px; border-radius:12px;
        display:flex; align-items:center; justify-content:center;
        background:#A7C8F0; color:#ffffff; font-weight:700;
        box-shadow:0 6px 14px rgba(167,200,240,.35);
        user-select:none;
      }
      .nt-pill span{ display:inline-flex; gap:8px; align-items:center; }

      /* Tira de ayuda */
      .help-strip{
        background:#F3F8FF; border:1px dashed #BDD7FF; color:#0B3B76;
        padding:10px 12px; border-radius:10px; font-size:0.92rem;
      }

      /* Botón fuera del card: pequeño margen superior para respirito visual */
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

    # ===== espaciado uniforme entre bloques =====
    _NT_SPACE = 36  # pestañas↔píldora, píldora↔indicaciones, indicaciones↔sección

    # Espacio ENTRE pestañas y la píldora
    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    # ---------- Píldora (no interactiva) con el ancho de la columna “Área” ----------
    A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60
    c_pill, _, _, _, _, _ = st.columns([A, Fw, T, D, R, C], gap="medium")
    with c_pill:
        st.markdown('<div class="nt-pill"><span>📝 Nueva tarea</span></div>', unsafe_allow_html=True)

    # Espacio ENTRE píldora e indicaciones
    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    # ---------- Sección principal ----------
    if st.session_state.get("nt_visible", True):
        st.markdown("""
        <div class="help-strip">
          ✳️ Completa los campos obligatorios → pulsa <b>➕ Agregar</b> → revisa en <b>🕑 Tareas recientes</b> y confirma con <b>💾 Guardar cambios</b>.
        </div>
        """, unsafe_allow_html=True)

        # Espacio ENTRE indicaciones y la sección
        st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

        # ——— Campos dentro del card (rectángulo plomo) ———
        with st.container(border=True):
            st.markdown('<span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

            # FILA 1
            r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
            area = r1c1.selectbox("Área", options=AREAS_OPC, index=0, key="nt_area")
            FASES = ["Capacitación","Post-capacitación","Pre-consistencia","Consistencia","Operación de campo"]
            fase = r1c2.selectbox("Fase", options=FASES, index=None, placeholder="Selecciona una fase", key="nt_fase")
            tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
            r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
            r1c5.text_input("Responsable", placeholder="Nombre", key="nt_resp")
            ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")

            # FILA 2: base de estados/fecha/hora/ID (con llaves estables)
            if st.session_state.get("fi_d", "___MISSING___") is None:
                st.session_state.pop("fi_d")
            if st.session_state.get("fi_t", "___MISSING___") is None:
                st.session_state.pop("fi_t")

            r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns([A, Fw, T, D, R, C], gap="medium")

            # Tipo de tarea (con Producción didáctica y Otros)
            TIPOS_TAREA_OPC = ["— Selecciona —", "Producción didáctica", "Otros"]
            tipo_sel = r2c1.selectbox("Tipo de tarea", options=TIPOS_TAREA_OPC, index=0, key="nt_tipo")

            # Estado fijo
            r2c2.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")

            # Obtener hora desde session_state y sincronizar campo visible (valor inicial)
            _t = st.session_state.get("fi_t")
            _t_txt = ""
            if _t is not None:
                try:
                    _t_txt = _t.strftime("%H:%M")
                except Exception:
                    _t_txt = str(_t)
            st.session_state["fi_t_view"] = _t_txt  # base

            # Prepara ID preview una sola vez
            _df_tmp = st.session_state.get("df_main", pd.DataFrame()).copy() if "df_main" in st.session_state else pd.DataFrame()
            prefix = make_id_prefix(st.session_state.get("nt_area", area), st.session_state.get("nt_resp", ""))
            id_preview = (next_id_by_person(_df_tmp, st.session_state.get("nt_area", area),
                           st.session_state.get("nt_resp", "")) if st.session_state.get("fi_d") else f"{prefix}_")

            is_otros = (str(st.session_state.get("nt_tipo", "")).strip().lower() == "otros")

            if is_otros:
                # Orden: Tipo, Estado, Complejidad, Duración, Fecha, Hora
                comp_opc = ["🟢 Baja", "🟡 Media", "🔴 Alta"]
                r2c3.selectbox("Complejidad", options=comp_opc, index=0, key="nt_complejidad")

                dur_labels = [f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)]
                r2c4.selectbox("Duración", options=dur_labels, index=0, key="nt_duracion_label")

                # Fecha
                r2c5.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)
                # --- Fuerza hora local si la fecha es hoy, aunque no cambie ---
                try:
                    _sel = st.session_state.get("fi_d")
                    if _sel is not None:
                        _sel_date = _sel if hasattr(_sel, "year") and not hasattr(_sel, "hour") else _sel.date()
                        if _sel_date == _now_local().date():
                            st.session_state["fi_t"] = _now_local().time()
                except Exception:
                    pass
                # sincroniza vista antes de pintar
                _t2 = st.session_state.get("fi_t")
                try:
                    st.session_state["fi_t_view"] = _t2.strftime("%H:%M") if _t2 else ""
                except Exception:
                    st.session_state["fi_t_view"] = str(_t2) if _t2 else ""

                r2c6.text_input("Hora (auto)", key="fi_t_view", disabled=True,
                                help="Se asigna al elegir la fecha")

                # FILA 3: solo ID asignado
                r3c1, r3c2, r3c3, r3c4, r3c5, r3c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r3c1.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

            else:
                # Caso normal (dos filas): Tipo, Estado, Fecha, Hora, ID asignado, (vacío)
                r2c3.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)
                # --- Fuerza hora local si la fecha es hoy, aunque no cambie ---
                try:
                    _sel = st.session_state.get("fi_d")
                    if _sel is not None:
                        _sel_date = _sel if hasattr(_sel, "year") and not hasattr(_sel, "hour") else _sel.date()
                        if _sel_date == _now_local().date():
                            st.session_state["fi_t"] = _now_local().time()
                except Exception:
                    pass
                # sincroniza vista antes de pintar
                _t2 = st.session_state.get("fi_t")
                try:
                    st.session_state["fi_t_view"] = _t2.strftime("%H:%M") if _t2 else ""
                except Exception:
                    st.session_state["fi_t_view"] = str(_t2) if _t2 else ""

                r2c4.text_input("Hora (auto)", key="fi_t_view", disabled=True,
                                help="Se asigna al elegir la fecha")
                r2c5.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")
                # r2c6 vacío

        # ——— Botón fuera del card, a la derecha, con el mismo ancho que C (Ciclo de mejora) ———
        left_space, right_btn = st.columns([A + Fw + T + D + R, C], gap="medium")
        with right_btn:
            st.markdown('<div class="nt-outbtn">', unsafe_allow_html=True)
            submitted = st.button("➕ Agregar", use_container_width=True, key="btn_agregar")
            st.markdown('</div>', unsafe_allow_html=True)

        # ---------- Guardado ----------
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

                new = blank_row()
                new.update({
                    "Área": area,
                    "Id": next_id_by_person(df, area, st.session_state.get("nt_resp", "")),
                    "Tarea": st.session_state.get("nt_tarea", ""),
                    "Tipo": st.session_state.get("nt_tipo", ""),
                    "Responsable": st.session_state.get("nt_resp", ""),
                    "Fase": fase,
                    "Estado": "No iniciado",
                    "Fecha": reg_fecha, "Hora": reg_hora_txt,
                    "Fecha Registro": reg_fecha, "Hora Registro": reg_hora_txt,
                    "Fecha inicio": None, "Hora de inicio": "",
                    "Fecha Terminado": None, "Hora Terminado": "",
                    "Ciclo de mejora": ciclo_mejora,
                    "Detalle": st.session_state.get("nt_detalle", ""),
                })

                # Agregar extras solo si Tipo = Otros
                if is_otros:
                    new["Complejidad"] = st.session_state.get("nt_complejidad", "")
                    lbl = st.session_state.get("nt_duracion_label", "")
                    try:
                        new["Duración"] = int(str(lbl).split()[0])
                    except Exception:
                        new["Duración"] = ""

                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                df = _sanitize(df, COLS if "COLS" in globals() else None)
                st.session_state["df_main"] = df.copy()
                os.makedirs("data", exist_ok=True)
                df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig", mode="w")
                st.rerun()
            except Exception as e:
                st.error(f"No pude guardar la nueva tarea: {e}")

    # Separación vertical al final
    gap = SECTION_GAP if 'SECTION_GAP' in globals() else 30
    st.markdown(f"<div style='height:{gap}px;'></div>", unsafe_allow_html=True)
