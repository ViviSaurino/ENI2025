# gestion_app.py  (Inicio / router)
import streamlit as st
from auth_google import google_login, logout

st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="collapsed",   # colapsada al entrar (antes de login)
)

# --- Login (gate aquí) ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None
)
if not user:
    st.stop()

# --- Tras el login: redirigir a "Gestión de tareas" (una sola vez por sesión) ---
# Requiere que exista: pages/02_gestion_tareas.py
if not st.session_state.get("_routed_to_gestion_tareas", False):
    st.session_state["_routed_to_gestion_tareas"] = True

    # Intentos robustos (algunas instalaciones resuelven por nombre, otras por ruta)
    _targets = (
        "pages/02_gestion_tareas.py",
        "02_gestion_tareas",
        "02 gestion tareas",
        "Gestión de tareas",
        "Gestion de tareas",
    )
    _switched = False
    for t in _targets:
        try:
            st.switch_page(t)
            _switched = True
            break
        except Exception:
            pass

    if not _switched:
        # Si no pudo, limpiamos la bandera para reintentar en el siguiente run
        st.session_state.pop("_routed_to_gestion_tareas", None)
        st.warning(
            "No pude redirigirte automáticamente a **Gestión de tareas**. "
            "Asegúrate de que exista `pages/02_gestion_tareas.py`."
        )

# --- Sidebar mínimo (sin page_link para evitar duplicados) ---
with st.sidebar:
    st.header("Inicio")
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        # Limpia flags locales de ruteo para que la próxima vez vuelva a redirigir
        for k in ("_routed_to_gestion_tareas",):
            st.session_state.pop(k, None)
        logout()
        st.rerun()

# --- Contenido fallback (solo se ve si no pudo redirigir) ---
st.info(
    "Redirigiendo a **Gestión de tareas**… "
    "Si no ocurre automáticamente, puedes entrar desde aquí:"
)
# Enlace directo por si falla la redirección automática
st.page_link("pages/02_gestion_tareas.py", label="Ir a Gestión de tareas", icon="🗂️")
