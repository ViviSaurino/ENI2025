# ============================ 
# Gestión — ENI2025 (App única)
# ============================
import streamlit as st
import pandas as pd
from pathlib import Path

from auth_google import google_login, logout
from shared import (
    patch_streamlit_aggrid,
    inject_global_css,
    ensure_df_main,
)

# Ruta del logo (arriba, a la izquierda del sidebar)
LOGO_PATH = Path("assets/branding/eni2025_logo.png")

# ============ Config de página ============
st.set_page_config(
    page_title="Gestión — ENI2025",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ Parches/estilos globales ============
patch_streamlit_aggrid()
inject_global_css()

# 👉 Estilos específicos (banner + botón cerrar sesión + logo más a la izquierda)
st.markdown("""
<style>
  .eni-banner{
    margin:6px 0 14px;
    font-weight:400;  /* sin negrita */
    font-size:16px;
    color:#4B5563;
  }
  section[data-testid="stSidebar"] .stButton > button{
    background:#C7A0FF !important;
    color:#FFFFFF !important;
    border:none !important;
    border-radius:12px !important;  /* menos curvatura */
    font-weight:700 !important;
    box-shadow:0 6px 14px rgba(199,160,255,.35) !important;
  }
  section[data-testid="stSidebar"] .stButton > button:hover{ filter:brightness(0.95); }

  /* Logo un poco más a la izquierda */
  section[data-testid="stSidebar"] .eni-logo-wrap{ margin-left:-28px; }

  /* Radio de navegación: más compacto */
  .eni-nav label{ padding:6px 8px !important; }
</style>
""", unsafe_allow_html=True)

# ============ AUTENTICACIÓN ============
if "user" not in st.session_state:
    google_login()
    st.stop()

email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

# ============ Sidebar ============
with st.sidebar:
    # Logo
    if LOGO_PATH.exists():
        st.markdown("<div class='eni-logo-wrap'>", unsafe_allow_html=True)
        st.image(str(LOGO_PATH), width=120)
        st.markdown("</div>", unsafe_allow_html=True)

    # Banner
    st.markdown("<div class='eni-banner'>Esta es la plataforma unificada para gestión - ENI2025</div>", unsafe_allow_html=True)

    # Navegación (clicable) solicitada
    st.header("Secciones")
    nav_labels = [
        "🧰 Gestión de tareas",
        "🗂️ Kanban",
        "📅 Gantt",
        "📊 Dashboard",
    ]
    default_idx = nav_labels.index(st.session_state.get("nav_section", "🧰 Gestión de tareas"))
    nav_choice = st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False,
    )

    st.divider()
    st.markdown(f"**Usuario:** {email or '—'}")
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ============ UI principal ============
# Ruteo a vistas según la opción elegida en el sidebar
section = st.session_state.get("nav_section", "🧰 Gestión de tareas")

if section == "🧰 Gestión de tareas":
    st.title("🧰 Gestión de tareas")

    # Pestañas como las que pediste (en el área principal)
    tabs = st.tabs([
        "➕ Nueva tarea",
        "🛠️ Editar estado",
        "🚨 Nueva alerta",
        "🧭 Prioridad",
        "📝 Evaluación",
        "🕑 Tareas recientes",
    ])

    # ➕ Nueva tarea
    with tabs[0]:
        try:
            # Tu módulo actual de “Nueva tarea”
            from features.tasks.new_task import render as render_new_task
            render_new_task(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista 'Nueva tarea' no encontrada (features/tasks/new_task.py).")
            st.exception(e)

    # 🛠️ Editar estado
    with tabs[1]:
        try:
            from features.tasks.edit_state import render as render_edit_state
            render_edit_state(st.session_state.get("user"))
        except Exception:
            st.info("Vista 'Editar estado' pendiente (features/tasks/edit_state.py).")

    # 🚨 Nueva alerta
    with tabs[2]:
        try:
            from features.alerts.new import render as render_new_alert
            render_new_alert(st.session_state.get("user"))
        except Exception:
            st.info("Vista 'Nueva alerta' pendiente (features/alerts/new.py).")

    # 🧭 Prioridad
    with tabs[3]:
        try:
            from features.tasks.priority import render as render_priority
            render_priority(st.session_state.get("user"))
        except Exception:
            st.info("Vista 'Prioridad' pendiente (features/tasks/priority.py).")

    # 📝 Evaluación
    with tabs[4]:
        try:
            from features.tasks.evaluation import render as render_eval
            render_eval(st.session_state.get("user"))
        except Exception:
            st.info("Vista 'Evaluación' pendiente (features/tasks/evaluation.py).")

    # 🕑 Tareas recientes
    with tabs[5]:
        try:
            from features.tasks.recent import render as render_recent
            render_recent(st.session_state.get("user"))
        except Exception:
            st.info("Vista 'Tareas recientes' pendiente (features/tasks/recent.py).")

elif section == "🗂️ Kanban":
    st.title("🗂️ Kanban")
    try:
        from features.kanban.view import render as render_kanban
        render_kanban(st.session_state.get("user"))
    except Exception as e:
        st.info("Vista Kanban pendiente (features/kanban/view.py).")
        st.exception(e)

elif section == "📅 Gantt":
    st.title("📅 Gantt")
    try:
        from features.gantt.view import render as render_gantt
        render_gantt(st.session_state.get("user"))
    except Exception as e:
        st.info("Vista Gantt pendiente (features/gantt/view.py).")
        st.exception(e)

else:  # "📊 Dashboard"
    st.title("🧰 Gestión de tareas")  # <-- cambiado solo el título
    try:
        # Ya tenías este módulo
        from features.dashboard.view import render_all
        render_all(st.session_state.get("user"))
    except Exception as e:
        st.info("Vista Dashboard pendiente (features/dashboard/view.py).")
        st.exception(e)
