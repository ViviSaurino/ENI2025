# features/prioridad/view.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode

# Fallbacks seguros
SECTION_GAP_DEF = globals().get("SECTION_GAP", 30)

def _save_local(df: pd.DataFrame):
    """Guardar localmente sin romper si la carpeta no existe."""
    try:
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")
    except Exception:
        pass


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
    """Lee lista de correos permitidos desde secrets/env (prioridad_editors)."""
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
