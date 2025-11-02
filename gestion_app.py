# ============================
# Gestión — ENI2025 (App única)
# Portada SIEMPRE visible + login + contenido tras autenticación
# ============================
import os
import streamlit as st
import pandas as pd

# ---------- Config básica ----------
st.set_page_config(
    page_title="Gestión — ENI2025",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Auth (módulo) con fallback seguro ----------
try:
    from auth_google import google_login, logout
except Exception:
    def google_login():
        st.session_state["auth_ok"] = True
        st.session_state["user_email"] = st.session_state.get("user_email", "dev@example.com")
        return {}
    def logout():
        for k in ("auth_ok","user_email","auth_user","google_user","g_user","email"):
            st.session_state.pop(k, None)

# ---------- Utils compartidas (con fallbacks) ----------
def _noop(*a, **k): ...
try:
    from shared import patch_streamlit_aggrid, inject_global_css, ensure_df_main
except Exception:
    patch_streamlit_aggrid = _noop
    inject_global_css = _noop
    def ensure_df_main():
        if "df_main" not in st.session_state:
            st.session_state["df_main"] = pd.DataFrame([])

patch_streamlit_aggrid()
inject_global_css()

# ---------- CSS de portada (lila + layout) ----------
st.markdown("""
<style>
:root{
  --lila-50:#F6EEFF; --lila-200:#EDE7FF; --lila-400:#C7B8FF; --texto:#0F172A;
}
.block-container { padding-top: 2.0rem !important; }
.welcome-wrap{
  background: radial-gradient(1200px 120px at 20% 0, var(--lila-200) 0%, rgba(237,231,255,0) 100%);
  border-radius: 14px; padding: 12px 16px; box-shadow: 0 8px 28px rgba(100,72,255,0.08);
}
.welcome-title{
  font-size: clamp(28px, 3.2vw, 38px); font-weight: 800; color: var(--texto); margin: 6px 0 8px 0;
}
.welcome-sub{
  color:#475569; font-size: 14.5px; margin-bottom: 14px;
}
.login-btn .stButton>button{
  height:40px; border-radius:10px; border:1px solid #ef4444 !important;
  background: white !important; color:#ef4444 !important; font-weight:600;
  width:100%;
}
.hero-box{ margin-top: 6px; margin-bottom: 10px; }
.hero-box video, .hero-box img{ border-radius:12px; max-width:580px; width:100%; display:block; }
.side-note{ font-size:12px; color:#6b7280; }
.sidebar-email{ font-size:13px; color:#374151; }
</style>
""", unsafe_allow_html=True)

# ---------- Helpers de autenticación ----------
def _current_email() -> str | None:
    ss = st.session_state
    for k in ("user_email","email"):
        if ss.get(k): return ss[k]
    for k in ("auth_user","google_user","g_user"):
        if isinstance(ss.get(k), dict) and ss[k].get("email"):
            return ss[k]["email"]
    return None

def _allowed(email: str | None) -> bool:
    if not email: return False
    conf = st.secrets.get("auth", {})
    allowed_emails  = set(conf.get("allowed_emails", []))
    allowed_domains = set(conf.get("allowed_domains", []))
    if email in allowed_emails: return True
    # dominio
    try:
        dom = email.split("@", 1)[1].lower()
        if dom in allowed_domains: return True
    except Exception:
        pass
    # si no hay listas configuradas, permitir (modo abierto)
    return (not allowed_emails and not allowed_domains)

# ---------- Portada (siempre visible) ----------
def _hero_path() -> str | None:
    """Busca animación en assets/ con prioridad .webm > .mp4 > .gif."""
    base = "assets"
    for name in ("hero.webm", "hero.mp4", "hero.gif", "welcome_anim.webm", "welcome_anim.mp4", "welcome_anim.gif"):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None

def render_welcome():
    st.markdown('<div class="welcome-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="welcome-title">👋 Bienvenidos — ENI2025</div>', unsafe_allow_html=True)
    st.markdown(
        " <div class='welcome-sub'>Esta es la plataforma unificada de <strong>Gestión — ENI2025</strong>. "
        "Inicia sesión con tu correo autorizado para gestionar tareas, prioridades, evaluaciones y más.</div>",
        unsafe_allow_html=True
    )

    # Animación
    hero = _hero_path()
    if hero and hero.lower().endswith((".webm",".mp4")):
        # HTML para autoplay/loop/muted/inline sin controles
        st.markdown(
            f"""
            <div class="hero-box">
              <video src="{hero}" autoplay loop muted playsinline></video>
            </div>
            """,
            unsafe_allow_html=True
        )
    elif hero and hero.lower().endswith(".gif"):
        st.image(hero, use_container_width=False)
    else:
        st.markdown("<div class='side-note'>💡 Coloca tu animación en <code>assets/hero.webm</code> o <code>hero.mp4</code> o <code>hero.gif</code>.</div>", unsafe_allow_html=True)

    # Botón Login
    c1, c2, c3 = st.columns([1,1.2,1])
    with c2:
        st.markdown('<div class="login-btn">', unsafe_allow_html=True)
        if st.button("Iniciar sesión con Google", use_container_width=True):
            try:
                google_login()
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo iniciar sesión: {e}")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ---------- Contenido principal (solo si permitido) ----------
def render_main():
    # Sidebar
    with st.sidebar:
        st.header("Secciones")
        email = _current_email()
        st.markdown(f"<div class='sidebar-email'><strong>Usuario:</strong> {email or '—'}</div>", unsafe_allow_html=True)
        if st.button("Cerrar sesión", use_container_width=True):
            try:
                logout()
            finally:
                st.rerun()

    # Datos
    ensure_df_main()

    # Cargar tus secciones unificadas
    try:
        from features.tareas.sections import render_all as render_tareas_all
        render_tareas_all()
    except Exception as e:
        st.error("No se pudo cargar las secciones (features/tareas/sections.py).")
        st.exception(e)

# ---------- Flujo ----------
render_welcome()                       # SIEMPRE muestra portada
email = _current_email()
if _allowed(email):
    render_main()                      # Si está permitido, muestra la app completa
