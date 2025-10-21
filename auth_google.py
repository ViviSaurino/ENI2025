# auth_google.py
import base64
import streamlit as st
from streamlit_oauth import OAuth2Component

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# ================== Compatibilidad Streamlit (rerun & query params) ==================
def _safe_rerun():
    """Usa st.rerun si existe; si no, cae a experimental_rerun en versiones antiguas."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

def _get_query_params():
    """Obtiene query params en forma de dict, compatible con versiones antiguas."""
    if hasattr(st, "query_params"):
        # st.query_params es un Mapping; lo convertimos a dict normal
        return dict(st.query_params)
    elif hasattr(st, "experimental_get_query_params"):
        return st.experimental_get_query_params()
    return {}

def _set_query_params(**kwargs):
    """Setea query params limpiamente, compatible con versiones antiguas."""
    if hasattr(st, "query_params"):
        st.query_params.clear()
        # filtra None
        st.query_params.update({k: v for k, v in kwargs.items() if v is not None})
    elif hasattr(st, "experimental_set_query_params"):
        st.experimental_set_query_params(**kwargs)

# -------------------- secrets --------------------
def _get_oauth_cfg():
    cfg = st.secrets.get("oauth_client", {})
    return {
        "client_id": cfg.get("client_id", ""),
        "client_secret": cfg.get("client_secret", ""),
        "auth_uri": cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth"),
        "token_uri": cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        "redirect_uri": (cfg.get("redirect_uris") or ["http://localhost:8501"])[0],
    }

def _is_allowed(email: str, allowed_emails, allowed_domains) -> bool:
    email = (email or "").lower().strip()
    if email in {e.lower().strip() for e in (allowed_emails or [])}:
        return True
    dom = email.split("@")[-1] if "@" in email else ""
    return dom in {d.lower().strip() for d in (allowed_domains or [])}

# -------------------- assets ---------------------
def _b64(path: str, mime: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"
    except Exception:
        return None

def _img(path: str) -> str | None:   return _b64(path, "image/png")
def _video(path: str) -> str | None: return _b64(path, "video/mp4")

# -------------------- navigation helper --------------------
def _switch_page(target: str):
    """Cambia de página (nombre visible o ruta) si hay multipágina."""
    if hasattr(st, "switch_page"):
        st.switch_page(target)
    else:
        _set_query_params(go=target)
        _safe_rerun()

# -------------------- login ----------------------
def google_login(
    allowed_emails=None,
    allowed_domains=None,
    redirect_page: str | None = None,
):
    """
    Muestra login SOLO cuando no hay sesión.
    Tras autenticarse: borra por completo el UI del login y recarga/redirige.
    """
    # Placeholder que contendrá TODA la portada de login
    login_ph = st.empty()

    # Si ya hay sesión válida: NO pintes login; borra si hubiera algo y devuelve
    u = st.session_state.get("user")
    if u and _is_allowed(u.get("email"), allowed_emails, allowed_domains):
        login_ph.empty()
        if redirect_page:
            _switch_page(redirect_page)
            st.stop()
        return u

    # ----- Render del login dentro del placeholder -----
    with login_ph.container():
        cfg = _get_oauth_cfg()
        oauth2 = OAuth2Component(
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
            authorize_endpoint=cfg["auth_uri"],
            token_endpoint=cfg["token_uri"],
        )

        st.markdown("""
            <style>
            html, body { height:100%; overflow:hidden; }
            [data-testid="stAppViewContainer"]{ height:100vh; overflow:hidden; }
            [data-testid="stMain"]{ height:100%; overflow:hidden; }
            .block-container{ height:100%; max-width:1180px; padding-top:.6rem; overflow:hidden; }

            .hero-area{ height:100%; display:flex; align-items:center; }

            :root{
              --leftw: 520px;
              --ctl-w: 320px;
              --row-gap: 2rem;
              --ctl-h: 41px;
            }

            .row{ width:100%; display:flex; gap:var(--row-gap); align-items:center; justify-content:center; }

            .left{ width:var(--leftw); margin-top: 25vh; }
            .title{ font-weight:900; color:#B38BE3; line-height:.9; letter-spacing:.5px; font-size:080px; margin:.2rem 0 .9rem 0; }
            .title .line{ display:block; }

            .equal-wrap{ width:var(--ctl-w); max-width:var(--ctl-w); min-width:var(--ctl-w); }

            .pill{
              width:var(--ctl-w)!important; max-width:var(--ctl-w)!important; min-width:var(--ctl-w)!important;
              height:var(--ctl-h)!important; display:flex; align-items:center; justify-content:center;
              border-radius:05px; background:#EEF2FF; border:0px solid #DBE4FF;
              color:#2B4C7E; font-weight:950; letter-spacing:.01px; text-transform:uppercase; font-size:19px;
              margin:0 0 01px 0; box-sizing:border-box;
            }

            .equal-wrap .google-btn,
            .equal-wrap .google-btn > div,
            .equal-wrap .google-btn .row-widget.stButton,
            .equal-wrap .google-btn .stButton,
            .equal-wrap .google-btn .stButton > div {
              width: var(--ctl-w)!important; max-width: var(--ctl-w)!important; min-width: var(--ctl-w)!important;
              margin:0!important; padding:0!important; display:block!important;
            }

            .equal-wrap .google-btn .stButton > button,
            .equal-wrap .google-btn button[data-testid="baseButton-secondary"],
            .equal-wrap .google-btn button[kind="secondary"],
            .equal-wrap .google-btn button {
              width: var(--ctl-w)!important; max-width: var(--ctl-w)!important; min-width: var(--ctl-w)!important;
              height: var(--ctl-h)!important; display:block!important; margin:0!important; padding:0 .95rem!important;
              border-radius:12px!important; border:1px solid #D5DBEF!important; background:#fff!important; font-size:14px!important;
              box-sizing:border-box!important;
            }

            .equal-wrap .google-btn .stButton > button:hover,
            .equal-wrap .google-btn button[data-testid="baseButton-secondary"]:hover,
            .equal-wrap .google-btn button[kind="secondary"]:hover,
            .equal-wrap .google-btn button:hover {
              border-color:#8B5CF6!important; box-shadow:0 8px 22px rgba(139,92,246,.20)!important;
            }

            .right{ max-width:520px; width:100%; }
            .hero-image, .hero-video{ width:100%; height:auto; object-fit:contain; display:block; max-height:90vh; }

            @media (max-width: 980px){
              :root{ --leftw: 320px; --ctl-w: 320px; --ctl-h: 42px; }
              .title{ font-size:80px; }
              .right .hero-image, .right .hero-video{ max-height:50vh; }
            }
            </style>
        """, unsafe_allow_html=True)

        st.markdown('<div class="hero-area">', unsafe_allow_html=True)
        st.markdown('<div class="row">', unsafe_allow_html=True)

        col_left, col_right = st.columns([1,1], gap="large")

        with col_left:
            st.markdown('<div class="left">', unsafe_allow_html=True)
            st.markdown('<div class="title"><span class="line">BIEN</span><span class="line">VENIDOS</span></div>', unsafe_allow_html=True)

            st.markdown('<div class="equal-wrap">', unsafe_allow_html=True)
            st.markdown('<div class="pill">GESTIÓN DE TAREAS ENI 2025</div>', unsafe_allow_html=True)

            st.markdown('<div class="google-btn">', unsafe_allow_html=True)
            result = None
            try:
                result = oauth2.authorize_button(
                    name="Continuar con Google",
                    icon="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                    pkce="S256",
                    use_container_width=False,
                    scopes=["openid","email","profile"],
                    redirect_uri=cfg["redirect_uri"],
                )
            except TypeError:
                try:
                    result = oauth2.authorize_button(
                        name="Continuar con Google",
                        icon="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                        pkce="S256",
                        use_container_width=False,
                        scope="openid email profile",
                        redirect_uri=cfg["redirect_uri"],
                    )
                except TypeError:
                    try:
                        result = oauth2.authorize_button(
                            name="Continuar con Google",
                            icon="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                            pkce="S256",
                            use_container_width=False,
                            scopes=["openid","email","profile"],
                            redirect_to=cfg["redirect_uri"],
                        )
                    except TypeError:
                        try:
                            result = oauth2.authorize_button(
                                name="Continuar con Google",
                                icon="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                                pkce="S256",
                                use_container_width=False,
                                scope="openid email profile",
                                redirect_to=cfg["redirect_uri"],
                            )
                        except TypeError:
                            result = oauth2.authorize_button(
                                name="Continuar con Google",
                                icon="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                                pkce="S256",
                                use_container_width=False,
                                scope="openid email profile",
                            )
            st.markdown('</div>', unsafe_allow_html=True)  # google-btn
            st.markdown('</div>', unsafe_allow_html=True)  # equal-wrap
            st.markdown('</div>', unsafe_allow_html=True)  # left

        with col_right:
            st.markdown('<div class="right">', unsafe_allow_html=True)
            vid = _video("assets/hero.mp4")
            img = _img("assets/hero.png")
            if vid:
                st.markdown(f'<video class="hero-video" src="{vid}" autoplay loop muted playsinline></video>', unsafe_allow_html=True)
            elif img:
                st.markdown(f'<img class="hero-image" src="{img}" alt="ENI 2025">', unsafe_allow_html=True)
            else:
                st.write("🖼️ Coloca tu video en `assets/hero.mp4` o imagen en `assets/hero.png`.")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)   # row
        st.markdown('</div>', unsafe_allow_html=True)   # hero-area

    # ----- Si no se obtuvo resultado del botón aún -----
    if not result:
        return None

    # ---------- Procesa token ----------
    token = result.get("token") if isinstance(result, dict) else result
    if not token:
        st.error("No se recibió el token de Google. Intenta nuevamente.")
        return None

    id_token = token.get("id_token", "") if isinstance(token, dict) else ""
    access_token = token.get("access_token", "") if isinstance(token, dict) else ""

    user = {"email":"", "name":"", "picture":""}

    if id_token:
        try:
            import jwt
            info = jwt.decode(id_token, options={"verify_signature": False})
            user.update(
                email=info.get("email",""),
                name=info.get("name", info.get("email","")),
                picture=info.get("picture",""),
            )
        except Exception:
            pass

    if access_token and not user["email"]:
        try:
            import requests
            r = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if r.ok:
                ui = r.json()
                user.update(
                    email=ui.get("email", user["email"]),
                    name=ui.get("name", user["name"] or ui.get("email","")),
                    picture=ui.get("picture", user["picture"]),
                )
        except Exception:
            pass

    if not _is_allowed(user.get("email"), allowed_emails, allowed_domains):
        st.error("Tu cuenta no está autorizada. Consulta con el administrador.")
        return None

    # Guarda sesión
    st.session_state["user"] = user

    # *** BORRA el login de la vista y navega/recarga ***
    login_ph.empty()
    if redirect_page:
        _switch_page(redirect_page)
        st.stop()
    else:
        # Mismo archivo/página: recarga para que SOLO se vea la gestión
        _safe_rerun()

    return user


def logout():
    st.session_state.pop("user", None)
    _safe_rerun()
