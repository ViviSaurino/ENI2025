# features/nueva_tarea/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st

# ====== utilidades que ya tienes en shared; aquí con fallbacks suaves ======
try:
    # Si ya existen en tu proyecto, se importan desde shared
    from shared import (
        blank_row,
        next_id_by_person,
        make_id_prefix,
        COLS,
        SECTION_GAP,
        _auto_time_on_date,
    )
except Exception:
    # Fallbacks mínimos para no romper durante el acople
    from datetime import datetime

    def blank_row() -> dict:
        return {}

    def make_id_prefix(area: str, resp: str) -> str:
        a = (area or "").strip().upper().replace(" ", "")[:3]
        r = (resp or "").strip().upper().split()[0][:3]
        return (a + r) or "ID"

    def next_id_by_person(df: pd.DataFrame, area: str, resp: str) -> str:
        prefix = make_id_prefix(area, resp)
        n = len(df.index) + 1
        return f"{prefix}_{n}"

    COLS = None
    SECTION_GAP = 30

    def _auto_time_on_date():
        # Al elegir fecha, fija hora actual redondeada a minutos
        now = datetime.now().replace(second=0, microsecond=0)
        st.session_state["fi_t"] = now.time()

# ==========================================================================


def render(user: dict | None = None):
    """
    Render de la pestaña: ➕ Nueva tarea
    (Lógica intacta; solo se encapsuló en una función pública)
    """

    # ================== Formulario (misma malla + hora inmediata) ==================

    # Fallback suave si aún no existe (no altera nada cuando ya viene del módulo principal)
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
    chev = "▾" if st.session_state.get("nt_visible", True) else "▸"

    # ---------- Barra superior ----------
    st.markdown('<div id="ntbar" class="topbar">', unsafe_allow_html=True)
    c_toggle, c_pill = st.columns([0.028, 0.965], gap="medium")
    with c_toggle:
        st.markdown('<div class="toggle-icon">', unsafe_allow_html=True)

        def _toggle_nt():
            st.session_state["nt_visible"] = not st.session_state.get("nt_visible", True)

        st.button(chev, key="nt_toggle_icon", help="Mostrar/ocultar", on_click=_toggle_nt)
        st.markdown("</div>", unsafe_allow_html=True)
    with c_pill:
        st.markdown(
            '<div class="form-title">&nbsp;&nbsp;📝&nbsp;&nbsp;Nueva tarea</div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
    # ---------- fin barra superior ----------

    if st.session_state.get("nt_visible", True):
        # ===== Scope local para NO afectar otras secciones =====
        st.markdown('<div id="nt-section">', unsafe_allow_html=True)

        # ===== Indicaciones cortas (debajo de la píldora) =====
        st.markdown(
            """
        <div class="help-strip">
          ✳️ Completa: <strong>Área, Fase, Tarea, Responsable y Fecha</strong>. La hora es automática.
        </div>
        """,
            unsafe_allow_html=True,
        )

        # ===== ESPACIADOR entre indicaciones y el card =====
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

        submitted = False

        # ===== Card REAL que envuelve TODAS las celdas =====
        with st.container(border=True):
            # Sentinel para limitar estilos SOLO a este card
            st.markdown('<span id="nt-card-sentinel"></span>', unsafe_allow_html=True)

            # CSS mínimo SOLO para inputs al 100% dentro de este card
            st.markdown(
                """
            <style>
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea{
                width:100% !important;
              }
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput > div,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox > div,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput > div,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput > div,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea > div{
                width:100% !important; max-width:none !important;
              }
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid="stDateInput"] input,
              div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) [data-testid^="stTimeInput"] input{
                width:100% !important;
              }
            </style>
            """,
                unsafe_allow_html=True,
            )

            # Proporciones (tus originales)
            A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

            # ---------- FILA 1 ----------
            r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
            area = r1c1.selectbox("Área", options=AREAS_OPC, index=0, key="nt_area")
            FASES = [
                "Capacitación",
                "Post-capacitación",
                "Pre-consistencia",
                "Consistencia",
                "Operación de campo",
            ]
            fase = r1c2.selectbox(
                "Fase",
                options=FASES,
                index=None,
                placeholder="Selecciona una fase",
                key="nt_fase",
            )
            tarea = r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
            detalle = r1c4.text_input(
                "Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle"
            )
            resp = r1c5.text_input("Responsable", placeholder="Nombre", key="nt_resp")
            ciclo_mejora = r1c6.selectbox(
                "Ciclo de mejora", options=["1", "2", "3", "+4"], index=0, key="nt_ciclo_mejora"
            )

            # ---------- FILA 2 ----------
            c2_1, c2_2, c2_3, c2_4, c2_5, c2_6 = st.columns([A, Fw, T, D, R, C], gap="medium")
            tipo = c2_1.text_input("Tipo de tarea", placeholder="Tipo o categoría", key="nt_tipo")

            # Estado fijo (sin lista): siempre "No iniciado"
            with c2_2:
                st.text_input("Estado", value="No iniciado", disabled=True, key="nt_estado_view")
            estado = "No iniciado"

            # --- FECHA/HORA: corrección para evitar None en date_input ---
            # Limpia claves inválidas antes de crear el widget (Streamlit no acepta None para date_input si la clave ya existe)
            if st.session_state.get("fi_d", "___MISSING___") is None:
                st.session_state.pop("fi_d")
            if st.session_state.get("fi_t", "___MISSING___") is None:
                st.session_state.pop("fi_t")

            # Fecha editable + callback inmediato (pone hora al elegir fecha)
            c2_3.date_input("Fecha", key="fi_d", on_change=_auto_time_on_date)

            # Hora auto (solo lectura)
            _t = st.session_state.get("fi_t")
            _t_txt = ""
            if _t is not None:
                try:
                    _t_txt = _t.strftime("%H:%M")
                except Exception:
                    _t_txt = str(_t)
            c2_4.text_input(
                "Hora (auto)",
                value=_t_txt,
                disabled=True,
                help="Se asigna al elegir la fecha",
                key="fi_t_view",
            )

            # ID preview
            _df_tmp = (
                st.session_state.get("df_main", pd.DataFrame()).copy()
                if "df_main" in st.session_state
                else pd.DataFrame()
            )
            prefix = make_id_prefix(
                st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp)
            )
            if st.session_state.get("fi_d"):
                id_preview = next_id_by_person(
                    _df_tmp, st.session_state.get("nt_area", area), st.session_state.get("nt_resp", resp)
                )
            else:
                id_preview = f"{prefix}_" if prefix else ""
            c2_5.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

            # Botón
            with c2_6:
                st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)
                submitted = st.button("➕ Agregar", use_container_width=True, key="btn_agregar")

        # Cierra scope local
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

                # Armamos HH:MM seguro para registro
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
                        "Estado": estado,  # ← fijo: No iniciado
                        # Marcas de REGISTRO que pide el historial
                        "Fecha": reg_fecha,  # respaldo simple (fallback)
                        "Hora": reg_hora_txt,  # respaldo simple (fallback)
                        "Fecha Registro": reg_fecha,  # registro explícito
                        "Hora Registro": reg_hora_txt,  # registro explícito
                        # Campos de inicio/fin (se llenan más adelante)
                        "Fecha inicio": None,
                        "Hora de inicio": "",
                        "Fecha Terminado": None,
                        "Hora Terminado": "",
                        # Otros
                        "Ciclo de mejora": ciclo_mejora,
                        "Detalle": st.session_state.get("nt_detalle", ""),
                    }
                )

                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)

                df = _sanitize(df, COLS if "COLS" in globals() else None)
                st.session_state["df_main"] = df.copy()
                os.makedirs("data", exist_ok=True)
                df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig", mode="w")

                st.success(f"✔ Tarea agregada (Id {new['Id']}).")
                st.rerun()
            except Exception as e:
                st.error(f"No pude guardar la nueva tarea: {e}")

    # Separación vertical
    st.markdown(
        f"<div style='height:{SECTION_GAP if 'SECTION_GAP' in globals() else 30}px;'></div>",
        unsafe_allow_html=True,
    )
