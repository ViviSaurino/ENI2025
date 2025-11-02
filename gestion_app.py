# ============================
# Gestión — ENI2025 (App única)
# ============================
import os
import pandas as pd
import streamlit as st

# ---------------- Auth (Google) ----------------
try:
    from auth_google import google_login, logout
except Exception:
    # Fallback de desarrollo
    def google_login():
        st.session_state["auth_ok"] = True
        st.session_state["user_email"] = st.session_state.get("user_email", "dev@example.com")
        return {}
    def logout():
        for k in ("auth_ok","user_email","auth_user","google_user","g_user","email"):
            st.session_state.pop(k, None)

# ------------- Utilidades compartidas -------------
try:
    from shared import patch_streamlit_aggrid, inject_global_css, ensure_df_main
except Exception:
    # Fallbacks no-op para no romper el arranque si falta shared.py
    def patch_streamlit_aggrid(): pass
    def inject_global_css(): pass
    def ensure_df_main():
        os.makedirs("data", exist_ok=True)
        csv = os.path.join("data", "tareas.csv")
        if not os.path.exists(csv):
            st.session_state["df_main"] = pd.DataFrame([], columns=["Id","Área","Responsable","Tarea","Prioridad","Evaluación","Fecha inicio","__DEL__"])
            st.session_state["df_main"].to_csv(csv, index=False, encoding="utf-8-sig")
        else:
            try:
                st.session_state["df_main"] = pd.read_csv(csv, encoding="utf-8-sig")
            except Exception:
                st.session_state["df_main"] = pd.DataFrame([])

# ------------- Bienvenida (vista pública) -------------
try:
    # Si existe tu vista de bienvenida, úsala
    from features.dashboard.view import render_bienvenida
except Exception:
    # Fallback simple
    def render_bienvenida(user=None):
        st.title("👋 Bienvenidos — ENI2025")
        st.markdown(
            "Esta es la plataforma unificada para **Gestión — ENI2025**. "
            "Inicia sesión con tu correo autorizado para ver tus secciones."
        )

# ------------- Render de secciones (post-login) -------------
try:
    # En tu estructura, este módulo centraliza todas las sub-vistas (nueva tarea, editar, etc.)
    from features.sections import render_all
except Exception:
    def render_all():
        st.warning("No se encontró `features/sections.py`. Crea `render_all(st)` para cargar tus secciones.")

# ================= Config de página =================
st.set_page_config(
    page_title="Gestión — ENI2025",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= Estilos / parches globales =================
patch_streamlit_aggrid()
inject_global_css()

# ================= Helpers de autenticación =================
def _current_email() -> str | None:
    ss = st.session_state
    for k in ("user_email", "email"):
        if ss.get(k):
            return ss[k]
    for k in ("auth_user", "google_user", "g_user"):
        if isinstance(ss.get(k), dict) and ss[k].get("email"):
            return ss[k]["email"]
    return None

def _allowed(email: str | None) -> bool:
    if not email:
        return False
    conf = st.secrets.get("auth", {})
    allowed_emails  = set(conf.get("allowed_emails", []))
    allowed_domains = set(conf.get("allowed_domains", []))
    if email in allowed_emails:
        return True
    try:
        domain = email.split("@", 1)[1].lower()
        if domain in allowed_domains:
            return True
    except Exception:
        pass
    # Si no hay listas configuradas en secrets.toml, permitir (modo dev)
    return (not allowed_emails and not allowed_domains)

# ================= Vista pública (Bienvenida + Login) =================
# Muestra SIEMPRE la bienvenida primero
user_stub = {"email": _current_email() or ""}
render_bienvenida(user_stub)

email = _current_email()
if not (email and _allowed(email)):
    st.info("🔐 Inicia sesión con tu cuenta permitida para acceder a **Gestión — ENI2025**.")
    col1, col2 = st.columns([1, 2], gap="large")
    with col1:
        if st.button("Iniciar sesión con Google", use_container_width=True):
            try:
                google_login()
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo iniciar sesión: {e}")
    st.stop()

# ================= Sidebar (solo después de login) =================
with st.sidebar:
    st.header("Secciones")
    st.caption("App unificada (sin *pages*).")
    st.divider()
    st.markdown(f"**Usuario:** {email}")
    if st.button("Cerrar sesión", use_container_width=True):
        try:
            logout()
        finally:
            st.rerun()

# ================= Datos base =================
ensure_df_main()  # crea/carga st.session_state["df_main"]

# ================= UI principal (secciones) =================
# Aquí se dibujan: Nueva tarea, Editar estado, Nueva alerta, Prioridad, Evaluación, Historial, etc.
render_all()
