from __future__ import annotations
import importlib
import os
import types
import streamlit as st

# ---------- Util opcional para portada ----------
def _find_hero_asset() -> str | None:
    candidates = ("hero.webm", "hero.mp4", "hero.gif",
                  "welcome_anim.webm", "welcome_anim.mp4", "welcome_anim.gif")
    for name in candidates:
        p = os.path.join("assets", name)
        if os.path.exists(p):
            return p
    return None

def render_bienvenida(on_login=None):
    st.markdown("""
    <style>
      .hero-wrap{margin-top:8px;padding:16px 18px 6px;border-radius:16px;
                 background:linear-gradient(180deg,rgba(187,146,255,.10) 0%,rgba(187,146,255,.02) 100%);
                 box-shadow:0 8px 30px rgba(143,110,255,.12);}
      .hero-title{font-size:36px;line-height:1.15;font-weight:800;margin:0 0 6px;}
      .hero-sub{color:#5b6470;margin-bottom:14px;}
      .hero-media{margin:8px 0 12px;border-radius:12px;overflow:hidden;}
      .hero-btn .stButton>button{height:42px;border-radius:10px;width:100%;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="hero-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">👋 Bienvenidos — ENI2025</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Plataforma unificada de <b>Gestión — ENI2025</b>.</div>',
        unsafe_allow_html=True,
    )
    hero = _find_hero_asset()
    if hero:
        st.markdown('<div class="hero-media">', unsafe_allow_html=True)
        if hero.endswith((".webm", ".mp4")):
            st.video(hero, autoplay=True, muted=True, loop=True)
        else:
            st.image(hero, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

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

# ---------- Loader genérico ----------
def _call_view(mod_path: str, candidates: tuple[str, ...], **kwargs):
    try:
        mod = importlib.import_module(mod_path)
    except Exception as e:
        st.warning(f"No pude importar `{mod_path}`.\n\n{e}")
        return

    fn = None
    for name in candidates:
        fn = getattr(mod, name, None)
        if isinstance(fn, (types.FunctionType, types.MethodType)):
            break
        fn = None

    if fn is None:
        nice = "`, `".join(candidates)
        st.info(f"El módulo `{mod_path}` no expone ninguna de estas funciones: `{nice}`.")
        return

    try:
        fn(**kwargs)
    except Exception as e:
        st.exception(e)

# ---------- Vista principal ----------
def render_all(user: dict | None = None):
    # Título (sin caption de sesión)
    st.subheader("🗂️ Gestión – ENI 2025")

    tabs = st.tabs([
        "➕ Nueva tarea",
        "🛠️ Editar estado",
        "🚨 Nueva alerta",
        "🧭 Prioridad",
        "📝 Evaluación",
        "🕑 Tareas recientes",
    ])

    with tabs[0]:
        with st.spinner("Cargando 'Nueva tarea'..."):
            _call_view(
                "features.nueva_tarea.view",
                ("render", "render_view", "main", "app", "render_section", "ui"),
                user=user
            )

    with tabs[1]:
        with st.spinner("Cargando 'Editar estado'..."):
            _call_view(
                "features.editar_tarea.view",
                ("render", "render_estado", "render_view", "main", "app", "ui"),
                user=user
            )

    with tabs[2]:
        with st.spinner("Cargando 'Nueva alerta'..."):
            _call_view(
                "features.nueva_alerta.view",
                ("render", "render_view", "main", "app", "ui"),
                user=user
            )

    with tabs[3]:
        with st.spinner("Cargando 'Prioridad'..."):
            _call_view(
                "features.prioridad.view",
                ("render", "render_view", "main", "app", "ui"),
                user=user
            )

    with tabs[4]:
        with st.spinner("Cargando 'Evaluación'..."):
            _call_view(
                "features.evaluacion.view",
                ("render", "render_view", "main", "app", "ui"),
                user=user
            )

    with tabs[5]:
        with st.spinner("Cargando 'Tareas recientes'..."):
            _call_view(
                "features.tareas.view",
                ("render", "render_recientes", "render_tabla", "render_view", "main", "app", "ui"),
                user=user
            )
