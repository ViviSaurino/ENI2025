# pages/01_Gestión.py
import streamlit as st
from shared import ensure_login, init_data, sidebar_userbox
import gestion_app  # importa tu módulo

st.set_page_config(page_title="Gestión", layout="wide", initial_sidebar_state="expanded")

user = ensure_login()
sidebar_userbox(user)
init_data()

st.title("📋 Gestión")
gestion_app.render()
