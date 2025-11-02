# features/dashboard/view.py
import os
import streamlit as st

LILAC = "#B38BE3"
LILAC_50 = "#F6EEFF"

def _find_anim():
    """Devuelve (tipo, ruta) para la animación disponible en /assets."""
    candidates = [
        ("video", "assets/welcome_anim.webm"),
        ("video", "assets/welcome_anim.mp4"),
        ("gif",   "assets/welcome_anim.gif"),
    ]
    for kind, path in candidates:
        if os.path.exists(path):
            return kind, path
    return None, None

def render_bienvenida(on_login=None, user: dict | None = None):
    # ---- CSS específico de la portada lila ----
    st.markdown(f"""
    <style>
      .welcome-hero {{
        background: linear-gradient(180deg, {LILAC_50} 0%, #fff 64%);
        border: 1px solid #ECE6FF;
        border-radius: 18px;
        padding: 22px 28px;
        box-shadow: 0 10px 26px rgba(179,139,227,.18);
      }}
      .welcome-title {{
        font-size: 42px; line-height: 1.1; font-weight: 800; margin: 0 0 6px 0;
        color: #2B2730;
      }}
      .welcome-sub {{
        font-size: 16px; color: #4B4B57; margin-bottom: 14px;
      }}
      .welcome-cta .stButton > button {{
        width: 100%;
        height: 44px;
        border-radius: 10px;
        border: 2px solid {LILAC};
        background: white;
        color: {LILAC};
        font-weight: 700;
        transition: all .15s ease;
      }}
      .welcome-cta .stButton > button:hover {{
        background: {LILAC};
        color: white;
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(179,139,227,.35);
      }}
      .anim-wrap {{
        display: flex; align-items: center; justify-content: center;
      }}
      .anim-wrap video {{ width: 100%; border-radius: 14px; }}
      .anim-wrap img   {{ width: 100%; border-radius: 14px; }}
    </style>
    """, unsafe_allow_html=True)

    # ---- Layout de la portada ----
    st.markdown('<div class="welcome-hero">', unsafe_allow_html=True)
    c_text, c_anim = st.columns([1.05, 0.95])
    with c_text:
        st.markdown('<div class="welcome-title">👋 Bienvenidos — ENI2025</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="welcome-sub">Esta es la plataforma unificada de <b>Gestión — ENI2025</b>. '
            'Inicia sesión con tu correo autorizado para gestionar tareas, prioridades, evaluaciones y más.</div>',
            unsafe_allow_html=True
        )
        st.markdown('<div class="welcome-cta">', unsafe_allow_html=True)
        if st.button("Iniciar sesión con Google", use_container_width=True, key="welcome_login"):
            try:
                if callable(on_login):
                    on_login()
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo iniciar sesión: {e}")
        st.markdown('</div>', unsafe_allow_html=True)

    with c_anim:
        kind, path = _find_anim()
        st.markdown('<div class="anim-wrap">', unsafe_allow_html=True)
        if kind == "video":
            # autoplay, loop, muted, playsinline para que saluden sin sentir el corte
            st.markdown(
                f"""
                <video src="{path}" autoplay loop muted playsinline></video>
                """,
                unsafe_allow_html=True
            )
        elif kind == "gif":
            st.image(path)
        else:
            st.caption("💡 Coloca tu animación en `assets/welcome_anim.webm` (o .mp4 / .gif).")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
