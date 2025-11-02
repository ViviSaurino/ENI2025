# features/dashboard/view.py
import os
import streamlit as st

# ---------- Util: localizar la animación del héroe ----------
def _find_hero_asset() -> str | None:
    candidates = ("hero.webm", "hero.mp4", "hero.gif",
                  "welcome_anim.webm", "welcome_anim.mp4", "welcome_anim.gif")
    for name in candidates:
        p = os.path.join("assets", name)
        if os.path.exists(p):
            return p
    return None

# ---------- Vista: Portada / Bienvenida ----------
def render_bienvenida(on_login=None):
    st.markdown("""
    <style>
      .hero-wrap{
        margin-top: 8px;
        padding: 16px 18px 6px 18px;
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(187,146,255,.10) 0%, rgba(187,146,255,.02) 100%);
        box-shadow: 0 8px 30px rgba(143, 110, 255, .12);
      }
      .hero-title{
        font-size: 36px; line-height: 1.15; font-weight: 800; margin: 0 0 6px 0;
      }
      .hero-sub{
        color: #5b6470; margin-bottom: 14px;
      }
      .hero-media{
        margin: 8px 0 12px 0;
        border-radius: 12px; overflow: hidden;
      }
      .hero-btn .stButton>button{
        height: 42px; border-radius: 10px; width: 100%;
      }
      .hero-note{ font-size: 12px; color: #8a8fa0; margin-top: 6px;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="hero-wrap">', unsafe_allow_html=True)

    # Título + bajada
    st.markdown('<div class="hero-title">👋 Bienvenidos — ENI2025</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Esta es la plataforma unificada de <b>Gestión — ENI2025</b>. '
        'Inicia sesión con tu correo autorizado para gestionar tareas, prioridades, evaluaciones y más.</div>',
        unsafe_allow_html=True,
    )

    # Animación (si existe)
    hero = _find_hero_asset()
    if hero:
        st.markdown('<div class="hero-media">', unsafe_allow_html=True)
        if hero.endswith((".webm", ".mp4")):
            st.video(hero, autoplay=True, muted=True, loop=True)
        else:
            st.image(hero, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Botón
    col = st.container()
    with col:
        st.markdown('<div class="hero-btn">', unsafe_allow_html=True)
        if st.button("Iniciar sesión con Google", use_container_width=True, type="primary"):
            if callable(on_login):
                try:
                    on_login()
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo iniciar sesión: {e}")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
