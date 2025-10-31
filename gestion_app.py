# gestion_app.py  (Inicio / router)
import streamlit as st
from auth_google import google_login, logout

st.set_page_config(
    page_title="Gestión — ENI2025",
    layout="wide",
    initial_sidebar_state="collapsed",   # colapsada al entrar (antes de login)
)

# --- Login (aquí va el gate) ---
allowed_emails  = st.secrets.get("auth", {}).get("allowed_emails", [])
allowed_domains = st.secrets.get("auth", {}).get("allowed_domains", [])

user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None
)
if not user:
    st.stop()

# --- Tras el login: redirigir a "Gestión de tareas" ---
# Requiere que el archivo exista con ese nombre:
#    pages/02_gestion_tareas.py
if not st.session_state.get("_routed_to_gestion_tareas"):
    st.session_state["_routed_to_gestion_tareas"] = True
    try:
        st.switch_page("pages/02_gestion_tareas.py")
    except Exception:
        # Si no existe ese archivo, mostramos un aviso y dejamos la página en pie
        st.warning(
            "No pude redirigirte a **Gestión de tareas**. "
            "Asegúrate de que el archivo exista como `pages/02_gestion_tareas.py`."
        )

# --- Sidebar minimal (sin page_link para evitar duplicados) ---
with st.sidebar:
    st.header("Inicio")
    st.markdown(f"**{user.get('name','')}**  \n{user.get('email','')}")
    if st.button("Cerrar sesión", use_container_width=True):
        logout()
        st.rerun()

# --- Contenido fallback (solo se ve si no pudo redirigir) ---
st.info(
    "Redirigiendo a **Gestión de tareas**… "
    "Si no ocurre automáticamente, selecciona *Gestión de tareas* en el menú lateral."
)
