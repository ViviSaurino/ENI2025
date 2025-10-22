# auth_google.py
import base64
import streamlit as st
from streamlit_oauth import OAuth2Component

# ================== Compat (rerun & query params) ==================
def _safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

def _get_query_params():
    if hasattr(st, "query_params"):
        return dict(st.query_params)
    elif hasattr(st, "experimental_get_query_params"):
        return st.experimental_get_query_params()
    return {}

def _set_query_params(**kwargs):
    if hasattr(st, "query_params"):
        st.query_params.clear()
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
    login_ph = st.empty()

    u = st.session_state.get("user")
    if u and _is_allowed(u.get("email"), allowed_emails, allowed_domains):
        login_ph.empty()
        if redirect_page:
            _switch_page(redirect_page)
            st.stop()
        return u

    with login_ph.container():
        cfg = _get_oauth_cfg()
        oauth2 = OAuth2Component(
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
            authorize_endpoint=cfg["auth_uri"],
            token_endpoint=cfg["token_uri"],
        )

        # ====== CSS: sin scroll + alineado perfecto ======
        st.markdown("""
            <style>
            /* Aplastar header/toolbar en Streamlit Cloud (sin offsets raros) */
            header[data-testid="stHeader"]{
              height:0 !important;
              min-height:0 !important;
              padding:0 !important;
              box-shadow:none !important;
              border:none !important;
              background:transparent !important;
            }
            [data-testid="stToolbar"]{display:none !important;}
            #MainMenu{visibility:hidden;}
            footer{display:none !important;}

            html, body { height:100%; }
            [data-testid="stAppViewContainer"]{ height:100vh; }
            [data-testid="stAppViewContainer"] > .main { padding-top: 0 !important; }
            .block-container{
              max-width:1180px;
              padding-top:.25rem !important;
              padding-bottom:0 !important;
            }

            :root{
              --gap: 2.6rem;
              --col-left: clamp(420px, 46vw, 560px);
              --pill-h: 46px;
              --btn-h: 48px;
            }

            .hero-area{
              min-height:100vh;              /* todo en una pantalla */
              display:flex;
              align-items:center;
              overflow:hidden;               /* evita micro-scroll */
            }

            .row{
              width:100%;
              display:flex;
              align-items:center;
              justify-content:space-between;
              gap: var(--gap);
            }

            /* Izquierda */
            .left{ width: var(--col-left); max-width: var(--col-left); }
            .title{
              font-weight:900;
              color:#B38BE3;
              line-height:.95;
              letter-spacing:.4px;
              font-size: clamp(60px, 8vw, 92px);
              margin: 0 0 18px 0;
            }
            .title .line{ display:block; }

            .equal-wrap{ width:100%; max-width:520px; }

            .pill{
              width:100% !important;
              height: var(--pill-h) !important;
              display:flex; align-items:center; justify-content:center;
              border-radius:12px; background:#EEF2FF; border:1px solid #DBE4FF;
              color:#2B4C7E; font-weight:800; letter-spacing:.2px; font-size:16px;
              margin:0 0 16px 0; box-sizing:border-box;
            }

            /* Botón Google = mismo ancho que la pill */
            .google-btn,
            .google-btn > div,
            .google-btn .row-widget.stButton,
            .google-btn .stButton,
            .google-btn .stButton > div{
              width:100% !important; max-width:520px !important;
              margin:0 !important; padding:0 !important;
            }
            .google-btn .stButton > button{
              width:100% !important; height: var(--btn-h) !important;
              border-radius:12px !important; border:1px solid #D5DBEF !important;
              background:#fff !important; font-size:15px !important;
              box-sizing:border-box !important; padding:0 .95rem !important;
            }
            .google-btn .stButton > button:hover{
              border-color:#8B5CF6 !important;
              box-shadow:0 8px 22px rgba(139,92,246,.18) !important;
            }

            /* Derecha */
            .right{ flex: 1 1 auto; display:flex; justify-content:center; }
            .hero-image, .hero-video{
              display:block;
              width: min(44vw, 560px);
              height:auto;
              max-height: 62vh;             /* clave: no empuja hacia abajo */
              object-fit:contain;
            }

            /* Responsivo */
            @media (max-width: 1200px){
              :root{ --gap: 2rem; }
              .hero-image, .hero-video{ max-height: 60vh; }
            }
            @media (max-width: 980px){
              .row{
                flex-direction:column;
                align-items:center;
                justify-content:flex-start;
                gap: 1.2rem;
              }
              .left{ width:100%; max-width:680px; }
              .equal-wrap{ max-width:680px; }
              .title{ font-size: clamp(46px, 11vw, 72px); margin-bottom: 12px; }
              .pill{ height:44px !important; margin-bottom:12px; }
              .hero-image, .hero-video{
                width: min(86vw, 560px);
                max-height: 40vh;          /* entra sin scroll en móvil */
              }
            }
            </style>
        """, unsafe_allow_html=True)

        # --- Layout (usamos columns solo para ubicar el botón en su lado) ---
        st.markdown('<div class="hero-area"><div class="row">', unsafe_allow_html=True)

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
            fallback = "https://raw.githubusercontent.com/filipedeschamps/tabnews.com.br/main/public/apple-touch-icon.png"
            if vid:
                st.markdown(f'<video class="hero-video" src="{vid}" autoplay loop muted playsinline></video>', unsafe_allow_html=True)
            elif img:
                st.markdown(f'<img class="hero-image" src="{img}" alt="ENI 2025">', unsafe_allow_html=True)
            else:
                st.markdown(f'<img class="hero-image" src="{fallback}" alt="ENI 2025">', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div></div>', unsafe_allow_html=True)  # row + hero-area

    # ----- Si no hay resultado aún -----
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

    st.session_state["user"] = user

    login_ph.empty()
    if redirect_page:
        _switch_page(redirect_page)
        st.stop()
    else:
        _safe_rerun()

    return user


def logout():
    st.session_state.pop("user", None)
    _safe_rerun()
