# auth_google.py
import base64
import streamlit as st
from streamlit_oauth import OAuth2Component

# ========== Configuración de ancho maestro (un único lugar) ==========
LEFT_W = 320  # px -> ancho de VENIDOS + píldora + botón (mantener igual que --left-w)

# ================== Utilidades ==================
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

# -------------------- assets helpers ---------------------
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

# ================== LOGIN ==================
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

        # ====== CSS ======
        st.markdown(f"""
            <style>
            html, body {{ height:100%; overflow:hidden; }}
            header[data-testid="stHeader"]{{ height:0; min-height:0; visibility:hidden; }}
            footer, .stDeployButton,
            .viewerBadge_container__1QSob, .styles_viewerBadge__1yB5_, .viewerBadge_link__1S137 {{ display:none !important; }}

            [data-testid="stAppViewContainer"]{{ height:100vh; overflow:hidden; }}
            [data-testid="stMain"]{{ height:100%; padding-top:0 !important; padding-bottom:0 !important; }}

            /* 👉 Centrado vertical real del contenido */
            .block-container{{
              height:100vh;
              max-width:1280px;
              padding:0 16px !important;
              margin:0 auto !important;
              display:flex;
              flex-direction:column;
              justify-content:center;   /* centra vertical */
            }}

            /* 👇 Control maestro del ancho (VENIDOS + píldora + botón) */
            :root{{
              --left-w: {LEFT_W}px;  /* Mantener igual que LEFT_W arriba */
              --title-max: 40px;    /* ← súbelo/bájalo para limitar el tamaño máximo del título */
              --media-max: 640px;
            }}

            [data-testid="stHorizontalBlock"]{{ height:100%; }}
            [data-testid="column"] > div{{
              display:flex; flex-direction:column; justify-content:center;
            }}

            .left{{ width:var(--left-w); max-width:100%; }}

            /* ===== TÍTULO AJUSTADO AL ANCHO =====
               coef 0.38: toca este número para afinar el tamaño relativo al ancho
            */
            .title{{
              width:var(--left-w);
              max-width:var(--left-w);
              display:block;
              font-weight:900; color:#B38BE3;
              line-height:.92; letter-spacing:.4px;
              font-size: clamp(40px, calc(var(--left-w) * 0.38), var(--title-max)) !important;
              margin:0 0 18px 0;
              box-sizing:border-box;
            }}
            .title .line{{
              display:block;
              width:100%;
              word-break: break-word;
              overflow-wrap: anywhere;
            }}
            /* ===== FIN TÍTULO ===== */

            .cta{{ width:var(--left-w) !important; max-width:var(--left-w) !important; }}

            .pill{{
              width:var(--left-w) !important; max-width:var(--left-w) !important;
              height:46px; display:flex; align-items:center; justify-content:center;
              border-radius:12px; background:#EEF2FF; border:1px solid #DBE4FF;
              color:#2B4C7E; font-weight:800; letter-spacing:.2px; font-size:16px;
              margin:0 0 14px 0; box-sizing:border-box;
            }}

            /* Fuerza el widget de BOTÓN al mismo ancho sin estirarlo por flex */
            .left .row-widget.stButton{{ 
              width:var(--left-w) !important;
              max-width:var(--left-w) !important;
              align-self:flex-start !important;
              padding:0 !important;
              margin:0 !important;
              box-sizing:border-box !important;
            }}
            .left .row-widget.stButton > div{{ 
              width:100% !important;
              max-width:100% !important;
              padding:0 !important;
              margin:0 !important;
              display:block !important;
              box-sizing:border-box !important;
            }}
            .left .row-widget.stButton > div > button{{
              width:100% !important;
              min-width:0 !important;
              height:48px !important;
              border-radius:12px !important; border:1px solid #D5DBEF !important;
              background:#fff !important; font-size:15px !important;
              box-sizing:border-box !important; padding:0 .95rem !important;
            }}
            .left .row-widget.stButton > div > button:hover{{
              border-color:#8B5CF6 !important;
              box-shadow:0 8px 22px rgba(139,92,246,.18) !important;
            }}

            .right{{ display:flex; justify-content:center; }}
            .hero-media{{
              display:block; width:auto;
              max-width:min(var(--media-max), 45vw);
              max-height:62vh; height:auto; object-fit:contain;
            }}

            @media (max-width:980px){{
              .left{{ width:min(86vw, var(--left-w)); }}
              .title{{ width:min(86vw, var(--left-w)); font-size:clamp(32px, calc(var(--left-w) * 0.38), var(--title-max)) !important; }}
              .cta, .pill, .left .row-widget.stButton{{ width:min(86vw, var(--left-w)) !important; max-width:min(86vw, var(--left-w)) !important; }}
              .hero-media{{ max-width:min(86vw, var(--media-max)); max-height:40vh; }}
            }}
            </style>
        """, unsafe_allow_html=True)

        # --------- Layout: 2 columnas ----------
        col_left, col_right = st.columns([7, 5], gap="large")

        with col_left:
            st.markdown('<div class="left">', unsafe_allow_html=True)

            # Título
            st.markdown(
                '<div class="title"><span class="line">BIEN</span><span class="line">VENIDOS</span></div>',
                unsafe_allow_html=True
            )

            # Contenedor común (mismo ancho)
            st.markdown('<div class="cta">', unsafe_allow_html=True)

            # PÍLDORA (mismo ancho)
            st.markdown(
                f'<div class="pill" style="width:{LEFT_W}px !important;">GESTIÓN DE TAREAS ENI 2025</div>',
                unsafe_allow_html=True
            )

            # Botón (mismo ancho)
            st.markdown(f'<div style="width:{LEFT_W}px !important;">', unsafe_allow_html=True)

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

            st.markdown('</div>', unsafe_allow_html=True)  # wrapper del botón
            st.markdown('</div>', unsafe_allow_html=True)  # .cta
            st.markdown('</div>', unsafe_allow_html=True)  # .left

        with col_right:
            st.markdown('<div class="right">', unsafe_allow_html=True)
            vid = _video("assets/hero.mp4")
            img = _img("assets/hero.png")
            fallback = "https://raw.githubusercontent.com/filipedeschamps/tabnews.com.br/main/public/apple-touch-icon.png"
            if vid:
                st.markdown(f'<video class="hero-media" src="{vid}" autoplay loop muted playsinline></video>', unsafe_allow_html=True)
            elif img:
                st.markdown(f'<img class="hero-media" src="{img}" alt="ENI 2025">', unsafe_allow_html=True)
            else:
                st.markdown(f'<img class="hero-media" src="{fallback}" alt="ENI 2025">', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

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




