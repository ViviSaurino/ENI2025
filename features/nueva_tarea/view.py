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

    def _auto_time_on_date():
        now = datetime.now().replace(second=0, microsecond=0)
        st.session_state["fi_t"] = now.time()

# ==========================================================================

def render(user: dict | None = None):
    """Vista: ➕ Nueva tarea"""

    # ===== CSS: inputs 100%, ocultar 'Sesión', espaciados y botón Agregar más abajo =====
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

      /* Alinear el botón Agregar con la segunda fila usando espaciador (sin margin-top) */
      #nt-card .btn-agregar{ margin-top:0 !important; }
      #nt-card .btn-agregar .stButton>button{
        min-height:38px !important; height:38px !important; border-radius:10px !important;
      }
    </style>
    """, unsafe_allow_html=True)

    # ===== Datos =====
    if "AREAS_OPC" not in globals():
        globals()["AREAS_OPC"] = [
            "Jefatura","Gestión","Metodología","Base de datos","Capacitación","Monitoreo","Consistencia"
        ]
    st.session_state.setdefault("nt_visible", True)

    # ===== espaciado uniforme entre bloques =====
    _NT_SPACE = 36  # mismo valor para: pestañas↔píldora, píldora↔indicaciones, indicaciones↔sección

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

        submitted = False

        # Envoltorio con id="nt-card" para apuntar el CSS (container sin key)
        st.markdown('<div id="nt-card">', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

            # ---------- FILA 1 ----------
            r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
            area = r1c1.selectbox("Área", options=AREAS_OPC, index=0, key="nt_area")
            FASES = ["Capacitación","Post-capacitación","Pre-consistencia","Consistencia","Operación de campo"]
            fase = r1c2.selectbox("Fase", options=FASES, index=None, placeholder="Selecciona una fase", key="nt_fase")
            tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
            r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
            r1c5.text_input("Responsable", placeholder="Nombre", key="nt_resp")
            ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")

            # ---------- FILA 2 ----------
            c2_1, c2_2, c2_3, c2_4, c2_5, c2_6 = st.columns([A, Fw, T, D, R, C], gap="medium")
            c2_1.text_input("Tipo de tarea", placeholder="Tipo o categoría", key="nt_tipo")
            c2_2.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")

            if st.session_state.get("fi_d", "___MISSING___") is None:
                st.session_state.pop("fi_d")
            if st.session_state.get("fi_t", "___MISSING___") is None:
                st.session_state.pop("fi_t")

            c2_3.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)

            _t = st.session_state.get("fi_t")
            _t_txt = ""
            if _t is not None:
                try:
                    _t_txt = _t.strftime("%H:%M")
                except Exception:
                    _t_txt = str(_t)
            c2_4.text_input("Hora (auto)", value=_t_txt, disabled=True,
                            help="Se asigna al elegir la fecha", key="fi_t_view")

            _df_tmp = st.session_state.get("df_main", pd.DataFrame()).copy() if "df_main" in st.session_state else pd.DataFrame()
            prefix = make_id_prefix(st.session_state.get("nt_area", area), st.session_state.get("nt_resp", ""))
            id_preview = (next_id_by_person(_df_tmp, st.session_state.get("nt_area", area),
                           st.session_state.get("nt_resp", "")) if st.session_state.get("fi_d") else f"{prefix}_")
            c2_5.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

            # Botón Agregar (más abajo para alinear mediante espaciador)
            with c2_6:
                st.markdown('<div class="btn-agregar">', unsafe_allow_html=True)
                BTN_OFFSET_PX = 16  # ↑ ajusta este valor para afinar la alineación
                st.markdown(f"<div style='height:{BTN_OFFSET_PX}px'></div>", unsafe_allow_html=True)
                submitted = st.button("➕ Agregar", use_container_width=True, key="btn_agregar")
                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)  # cierra #nt-card

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
