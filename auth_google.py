# auth_google.py
import base64
import streamlit as st
from streamlit_oauth import OAuth2Component

# ================== Compatibilidad Streamlit (rerun & query params) ==================
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
    """
    Muestra login SOLO cuando no hay sesión.
    Tras autenticarse: borra por completo el UI del login y recarga/redirige.
    """
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

        # ====== ESTILOS y LAYOUT: sin scroll y alineado ======
        st.markdown("""
            <style>
            /* Pantalla completa y sin scroll */
            html, body { height:100%; overflow:hidden; }
            [data-testid="stAppViewContainer"]{ height:100vh; overflow:hidden; }

            /* Quitamos altura extra del main y paddings para ganar espacio útil */
            [data-testid="stMain"]{ height:100%; padding-top:0 !important; padding-bottom:0 !important; }
            .block-container{
              height:100%;
              max-width:1180px;
              padding-top:.2rem !important;
              padding-bottom:.2rem !important;
            }
            /* Oculta la barra superior de Streamlit (no imprescindible, pero ayuda) */
            header[data-testid="stHeader"]{ height:0; min-height:0; visibility:hidden; }

            :root{
              --gap: 2.4rem;
              --leftw: clamp(420px, 44vw, 560px);
              --controls-w: clamp(360px, 34vw, 520px);
              --pill-h: 46px;
              --btn-h: 48px;
            }

            .hero-area{
              min-height:100vh;
              display:flex;
              align-items:center;           /* centra verticalmente */
              overflow:hidden;               /* evita que aparezca scroll */
            }
            .row{
              width:100%;
              display:flex;
              align-items:center;
              justify-content:space-between; /* texto a la izq, imagen a la der */
              gap: var(--gap);
            }

            /* === Columna izquierda === */
            .left{ width:var(--leftw); max-width:var(--leftw); }
            .title{
              font-weight:900;
              color:#B38BE3;
              line-height:.92;
              letter-spacing:.4px;
              font-size: clamp(56px, 9vw, 96px); /* grande pero responsivo */
              margin: 0 0 18px 0;
            }
            .title .line{ display:block; }

            .equal-wrap{ width:var(--controls-w); max-width:var(--controls-w); }

            .pill{
              width:100% !important;
              height: var(--pill-h) !important;
              display:flex; align-items:center; justify-content:center;
              border-radius:12px; background:#EEF2FF; border:1px solid #DBE4FF;
              color:#2B4C7E; font-weight:800; letter-spacing:.2px; font-size:16px;
              margin:0 0 14px 0; box-sizing:border-box;
            }

            /* Botón Google con exactamente el mismo ancho de la pill */
            .google-btn,
            .google-btn > div,
            .google-btn .row-widget.stButton,
            .google-btn .stButton,
            .google-btn .stButton > div{
              width:100% !important; max-width:var(--controls-w) !important;
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

            /* === Columna derecha (imagen/video) === */
            .right{ flex:1 1 auto; display:flex; justify-content:center; }
            .hero-image, .hero-video{
              display:block;
              width: min(44vw, 560px);
              height:auto;
              max-height: 66vh;          /* clave: nunca más de ~2/3 del alto */
              object-fit:contain;
            }

            /* ====== Responsivo ====== */
            @media (max-width: 1200px){
              :root{ --gap: 2rem; }
              .hero-image, .hero-video{ max-height: 62vh; }
            }
            @media (max-width: 980px){
              .row{
                flex-direction:column;
                align-items:center;
                justify-content:flex-start;
                gap: 1.2rem;
              }
              .left{ width:100%; max-width:640px; }
              .equal-wrap{ max-width:640px; }
              .title{ font-size: clamp(44px, 12vw, 72px); margin-bottom: 10px; }
              .pill{ height:44px !important; margin-bottom:10px; }
              .hero-image, .hero-video{
                width: min(86vw, 560px);
                max-height: 40vh;          /* asegura que TODO quepa sin scroll */
              }
            }
            </style>
        """, unsafe_allow_html=True)

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
            # Fallback si aún no subiste assets
            fallback = "https://raw.githubusercontent.com/filipedeschamps/tabnews.com.br/main/public/apple-touch-icon.png"
            if vid:
                st.markdown(f'<video class="hero-video" src="{vid}" autoplay loop muted playsinline></video>', unsafe_allow_html=True)
            elif img:
                st.markdown(f'<img class="hero-image" src="{img}" alt="ENI 2025">', unsafe_allow_html=True)
            else:
                st.markdown(f'<img class="hero-image" src="{fallback}" alt="ENI 2025">', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div></div>', unsafe_allow_html=True)   # row + hero-area

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
