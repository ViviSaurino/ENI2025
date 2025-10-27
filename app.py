# app.py
import os, pandas as pd, streamlit as st
from shared import ensure_login, init_data, sidebar_userbox

st.set_page_config(page_title="Inicio — Gestión", layout="wide", initial_sidebar_state="expanded")

# ==== Login (1 sola vez aquí) ====
user = ensure_login()  # exige login y deja user en session_state["user"]
sidebar_userbox(user)  # cajita con nombre/correo + botón "Cerrar sesión"

# ==== Inicializa df_main si aún no existe ====
init_data()

# ==== Portada simple ====
st.title("👋 Bienvenida")
st.markdown("""
Selecciona una página en la barra lateral:
- **Gestión**: tu tablero de formularios, prioridad, evaluación e historial.
- **Kanban**: vista por columnas (No iniciado, En curso, Terminado, etc.) usando los datos de *Tareas recientes*.
""")
