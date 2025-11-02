# features/nueva_tarea/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st

# ====== utilidades (con fallbacks) ======
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
        n = len(df.index) + 1
        return f"{prefix}_{n}"

    COLS = None
    SECTION_GAP = 30

    def _auto_time_on_date():
        now = datetime.now().replace(second=0, microsecond=0)
        st.session_state["fi_t"] = now.time()

# ==========================================================================

def render(user: dict | None = None):
    """Vista: ➕ Nueva tarea"""

    # ---------- CSS “forzado” ----------
    st.markdown(
        """
        <style>
        :root{ --pill-h:38px; --pill-r:999px; }

        /* 1) Ocultar subtítulo duplicado (todos los h2) */
        .block-container h2{ display:none !important; }

        /* 2) Ocultar la franja azul informativa */
        .block-container .stAlert{ display:none !important; }

        /* 3) Toggle alineado con la fila de píldoras superior */
        #ntbar{
          display:flex; align-items:center; gap:10px;
          margin-top:-64px !important;   /* <- empuja hacia arriba con fuerza */
          margin-bottom:10px;
        }
        #ntbar .stButton > button{
          min-height: var(--pill-h) !important;
          height: var(--pill-h) !important;
          line-height: var(--pill-h) !important;
          padding: 0 14px !important;
          border-radius: var(--pill-r) !important;
        }

        /* 4) Inputs 100% en el card */
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea{ width:100% !important; }
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput > div,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox > div,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput > div,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput > div,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea > div{
          width:100% !important; max-width:none !important;
        }
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid="stDateInput"] input,
        div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid^="stTimeInput"] input{ width:100% !important; }

        /* 5) Tira de ayuda */
        .help-strip{
          background:#F3F8FF; border:1px dashed #BDD7FF; color:#0B3B76;
          padding:10px 12px; border-radius:10px; font-size:0.92rem;
        }

        /* 6) Alinear botón Agregar con la fila de campos */
        #nt-card .btn-agregar{ margin-top:28px; }
        #nt-card .btn-agregar .stButton > button{
          min-height:38px !important; height:38px !important; border-radius:10px !important;
        }

        /* Ajuste fino responsive */
        @media (max-width: 900px){ #ntbar{ margin-top:-48px !important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------- Datos auxiliares ----------
    if "AREAS_OPC" not in globals():
        globals()["AREAS_OPC"] = [
            "Jefatura", "Gestión", "Metodología", "Base de datos",
            "Capacitación", "Monitoreo", "Consistencia",
        ]

    st.session_state.setdefault("nt_visible", True)
    chev = "▾" if st.session_state.get("nt_visible", True) else "▸"

    # ---------- Barra solo con toggle (pegada a la fila de píldoras) ----------
    st.markdown('<div id="ntbar">', unsafe_allow_html=True)
    col_tg, _ = st.columns([0.08, 0.92], gap="small")
    with col_tg:
        def _toggle_nt():
            st.session_state["nt_visible"] = not st.session_state.get("nt_visible", True)
        st.button(chev, key="nt_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_nt)
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- Sección principal ----------
    if st.session_state.get("nt_visible", True):
        st.markdown('<div id="nt-section">', unsafe_allow_html=True)

        st.markdown(
            """
            <div class="help-strip">
              ✳️ Completa: <strong>Área, Fase, Tarea, Responsable y Fecha</strong>. La hora es automática.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

        submitted = False

        with st.container(border=True):
            st.markdown('<div id="nt-card"><span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

            A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

            # ------- FILA 1 -------
            r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
            area = r1c1.selectbox("Área", options=AREAS_OPC, index=0, key="nt_area")
            FASES = ["Capacitación","Post-capacitación","Pre-consistencia","Consistencia","Operación de campo"]
            fase = r1c2.selectbox("Fase", options=FASES, index=None, placeholder="Selecciona una fase", key="nt_fase")
            tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
            detalle = r1c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
            resp = r1c5.text_input("Responsable", placeholder="Nombre", key="nt_resp")
            ciclo_mejora = r1c6.selectbox("Ciclo de mejora", options=["1","2","3","+4"], index=0, key="nt_ciclo_mejora")

            # ------- FILA 2 -------
            c2_1, c2_2, c2_3, c2_4, c2_5, c2_6 = st.columns([A, Fw, T, D, R, C], gap="medium")
            tipo = c2_1.text_input("Tipo de tarea", placeholder="Tipo o categoría", key="nt_tipo")

            with c2_2:
                st.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")
            estado = "No iniciado"

            # Fecha/Hora
            if st.session_state.get("fi_d", "___MISSING___") is None:
                st.session_state.pop("fi_d")
            if st.session_state.get("fi_t", "___MISSING___") is None:
                st.session_state.pop("fi_t")

            c2_3.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)

            _t = st.session_state.get("fi_t")
            _t_txt = ""
            if _t is not None:
                try: _t_txt = _t.strftime("%H:%M")
                except Exception: _t_txt = str(_t)
            c2_4.text_input("Hora (auto)", value=_t_txt, disabled=True, help="Se asigna al elegir la fecha", key="fi_t_view")

            # ID preview
            _df_tmp = st.session_state.get("df_main", pd.DataFrame()).copy() if "df_main" in st.session_state else pd.DataFrame()
            prefix = make_id_prefix(st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp))
            if st.session_state.get("fi_d"):
                id_preview = next_id_by_person(_df_tmp, st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp))
            else:
                id_preview = f"{prefix}_" if prefix else ""
            c2_5.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

            # Botón Agregar (alineado)
            with c2_6:
                st.markdown('<div class="btn-agregar">', unsafe_allow_html=True)
                submitted = st.button("➕ Agregar", use_container_width=True, key="btn_agregar")
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)  # cierra #nt-card

        st.markdown("</div>", unsafe_allow_html=True)  # cierra #nt-section

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
                new.update(
                    {
                        "Área": area,
                        "Id": next_id_by_person(df, area, st.session_state.get("nt_resp", "")),
                        "Tarea": st.session_state.get("nt_tarea", ""),
                        "Tipo": st.session_state.get("nt_tipo", ""),
                        "Responsable": st.session_state.get("nt_resp", ""),
                        "Fase": fase,
                        "Estado": "No iniciado",
                        "Fecha": reg_fecha,
                        "Hora": reg_hora_txt,
                        "Fecha Registro": reg_fecha,
                        "Hora Registro": reg_hora_txt,
                        "Fecha inicio": None,
                        "Hora de inicio": "",
                        "Fecha Terminado": None,
                        "Hora Terminado": "",
                        "Ciclo de mejora": ciclo_mejora,
                        "Detalle": st.session_state.get("nt_detalle", ""),
                    }
                )

                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)

                df = _sanitize(df, COLS if "COLS" in globals() else None)
                st.session_state["df_main"] = df.copy()
                os.makedirs("data", exist_ok=True)
                df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig", mode="w")

                # OJO: la franja .stAlert está oculta por CSS; si quieres feedback visual inmediato, podemos usar st.toast
                st.rerun()
            except Exception as e:
                st.error(f"No pude guardar la nueva tarea: {e}")

    st.markdown(
        f"<div style='height:{SECTION_GAP if 'SECTION_GAP' in globals() else 30}px;'></div>",
        unsafe_allow_html=True,
    )
