# auth_google.py
# Autenticación Google OAuth2 para ENI2025 (portada + hero + botón)
# - Lee client_id/secret/redirect_uris de st.secrets["oauth_client"]
# - Elige redirect por st.secrets["active"] ('cloud' o 'local')
# - Permisos: st.secrets["auth"].allowed_emails / allowed_domains
# - Setea st.session_state["user"], ["user_email"], ["auth_ok"]

from __future__ import annotations
import base64
import os
import jwt
import requests
import streamlit as st
from streamlit_oauth import OAuth2Component

# ========== Config de layout ==========
LEFT_W = 320  # píxeles: ancho de título/píldora/botón en la portada

# ================== Utilidades base ==================
def _safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

def _get_query_params() -> dict:
    if hasattr(st, "query_params"):
        return dict(st.query_params)
    if hasattr(st, "experimental_get_query_params"):
        return st.experimental_get_query_params()
    return {}

def _set_query_params(**kwargs):
    if hasattr(st, "query_params"):
        st.query_params.clear()
        st.query_params.update({k: v for k, v in kwargs.items() if v is not None})
    elif hasattr(st, "experimental_set_query_params"):
        st.experimental_set_query_params(**kwargs)

def _clear_oauth_params():
    # Evita “rebote” tras login limpiando parámetros del callback
    qp = _get_query_params()
    for k in ("code", "state", "scope", "authuser", "prompt"):
        qp.pop(k, None)
    _set_query_params(**qp)

# -------------------- secrets / OAuth cfg --------------------
def _pick_redirect(redirects: list[str], active: str) -> str:
    """
    Elige el redirect según 'active' ('cloud'|'local'), pero permite
    forzarlo por query param: ?env=cloud | ?env=local (también ?mode=...).
    Por defecto prioriza cloud si no hay override.
    """
    # Posible override vía URL
    qp = _get_query_params()
    override = None
    for k in ("env", "ENV", "mode"):
        v = qp.get(k)
        if isinstance(v, list):
            v = v[0] if v else None
        if v:
            override = str(v).lower().strip()

    pref = (override or active or "cloud").lower()

    redirects = redirects or []
    cloud = next((u for u in redirects if "localhost" not in (u or "").lower()), None)
    local = next((u for u in redirects if "localhost"     in (u or "").lower()), None)

    # Si piden cloud => cloud; si piden local => local; luego fallbacks seguros
    return (cloud if pref == "cloud" else local) or cloud or local or "http://localhost:8501"

def _get_oauth_cfg():
    cfg = st.secrets.get("oauth_client", {})
    active_env = st.secrets.get("active", "cloud")

    cid = cfg.get("client_id", "")
    csec = cfg.get("client_secret", "")
    auth_uri = cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth")
    token_uri = cfg.get("token_uri", "https://oauth2.googleapis.com/token")
    redirects = cfg.get("redirect_uris") or []
    redirect_uri = _pick_redirect(redirects, active_env)

    return {
        "client_id": cid,
        "client_secret": csec,
        "auth_uri": auth_uri,
        "token_uri": token_uri,
        "redirect_uri": redirect_uri,
        "_has_creds": bool(cid and csec and redirects),
        "_active": active_env,
    }

def _get_allowed_from_secrets():
    auth = st.secrets.get("auth", {})
    return auth.get("allowed_emails", []), auth.get("allowed_domains", [])

# -------------------- permisos --------------------
def _is_allowed(email: str, allowed_emails, allowed_domains) -> bool:
    """
    Si NO hay filtros configurados (listas vacías), el modo es ABIERTO -> permite acceso.
    Si hay filtros, requiere match por email exacto o dominio.
    """
    allow_emails = {str(e).lower().strip() for e in (allowed_emails or [])}
    allow_domains = {str(d).lower().strip() for d in (allowed_domains or [])}

    if not allow_emails and not allow_domains:
        return True

    email = (email or "").lower().strip()
    if email in allow_emails:
        return True
    dom = email.split("@")[-1] if "@" in email else ""
    return dom in allow_domains

# -------------------- assets (hero/img) --------------------
def _b64(path: str, mime: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"
    except Exception:
        return None

def _img(path: str) -> str | None:   return _b64(path, "image/png")
def _video(path: str) -> str | None: return _b64(path, "video/mp4")

# -------------------- navegación --------------------
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
    """
    Renderiza la portada (hero + botón Google). Si el usuario inicia sesión y
    está autorizado, fija st.session_state["user"], ["user_email"], ["auth_ok"].
    """
    # Si no llegan listas, léelas de secrets
    if allowed_emails is None or allowed_domains is None:
        se_emails, se_domains = _get_allowed_from_secrets()
        if allowed_emails is None:
            allowed_emails = se_emails
        if allowed_domains is None:
            allowed_domains = se_domains

    # Sesión ya válida
    u = st.session_state.get("user")
    if u and _is_allowed(u.get("email"), allowed_emails, allowed_domains):
        st.session_state["user_email"] = u.get("email", "")
        st.session_state["auth_ok"] = True
        if redirect_page:
            _switch_page(redirect_page)
            st.stop()
        return u

    # -------------- UI / portada --------------
    cfg = _get_oauth_cfg()

    # CSS de portada (ajustes para no cortar "VENIDOS" y separar botón)
    st.markdown(f"""
    <style>
      html, body {{ height:100%; overflow:hidden; }}
      header[data-testid="stHeader"]{{ height:0; min-height:0; visibility:hidden; }}
      footer, .stDeployButton,
      .viewerBadge_container__1QSob, .styles_viewerBadge__1yB5_, .viewerBadge_link__1S137 {{ display:none !important; }}

      [data-testid="stAppViewContainer"]{{ height:100vh; overflow:hidden; }}
      [data-testid="stMain"]{{ height:100%; padding-top:0 !important; padding-bottom:0 !important; }}

      .block-container{{
        height:100vh; max-width:980px; padding:0 16px !important; margin:0 auto !important;
        display:flex; flex-direction:column; justify-content:center;
      }}
      [data-testid="stHorizontalBlock"]{{ height:100%; display:flex; align-items:center; gap: 8px !important; }}

      :root{{ --left-w:{LEFT_W}px; --title-max:82px; --media-max:1000px; --stack-gap:14px; --title-bottom:10px; }}
      .left{{ width:var(--left-w); max-width:100%; }}

      .title{{
        width:var(--left-w); max-width:var(--left-w);
        font-weight:930; color:#B38BE3;
        line-height:.92; letter-spacing:.10px;
        font-size: clamp(40px, calc(var(--left-w) * 0.38), var(--title-max)) !important;
        margin:0 0 var(--title-bottom) 0;
        word-break: keep-all;       /* no romper palabras */
        hyphens: none;              /* sin guiones automáticos */
      }}
      .title .line{{
        display:block; width:100%;
        white-space: nowrap;        /* cada línea del título en una sola fila */
      }}

      .cta{{ width:var(--left-w); display:flex; flex-direction:column; gap:var(--stack-gap); }}
      .pill{{
        width:var(--left-w); height:46px; display:flex; align-items:center; justify-content:center;
        border-radius:12px; background:#EEF2FF; border:1px solid #DBE4FF;
        color:#2B4C7E; font-weight:800; letter-spacing:.2px; font-size:16px;
        margin-bottom:4px;           /* pequeño colchón extra respecto al botón */
      }}

      .left .stButton > button{{
        width:var(--left-w); height:48px; border-radius:12px !important;
        border:1px solid #D5DBEF !important; background:#fff !important; font-size:15px !important;
      }}
      .left :is(button,[data-baseweb="button"]):hover,
      .left :is(button,[data-baseweb="button"]):focus,
      .left :is(button,[data-baseweb="button"]):active {{
        background:#60A5FA !important; border-color:#60A5FA !important; color:#fff !important;
        box-shadow:0 0 0 3px rgba(96,165,250,.35) !important, 0 8px 22px rgba(96,165,250,.25) !important;
      }}

      .right{{ display:flex; justify-content:center; }}
      .hero-media{{ display:block; max-width:min(var(--media-max), 45vw); max-height:60vh; height:auto; object-fit:contain; }}
      @media (max-width:980px){{
        .left{{ width:min(86vw, var(--left-w)); }}
        .title{{ width:min(86vw, var(--left-w)); font-size:clamp(32px, calc(var(--left-w) * 0.38), var(--title-max)) !important; }}
        .cta, .pill, .left .stButton>button{{ width:min(86vw, var(--left-w)) !important; }}
        .hero-media{{ max-width:min(86vw, var(--media-max)); max-height:40vh; }}
      }}
    </style>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([6, 6], gap="small")

    with col_left:
        st.markdown('<div class="left">', unsafe_allow_html=True)
        st.markdown('<div class="title"><span class="line">BIEN</span><span class="line">VENIDOS</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="cta">', unsafe_allow_html=True)
        st.markdown(f'<div class="pill">GESTIÓN DE TAREAS ENI 2025</div>', unsafe_allow_html=True)

        # Botón OAuth
        result = None
        if not cfg["_has_creds"]:
            st.error("Faltan credenciales en `st.secrets['oauth_client']` (client_id, client_secret, redirect_uris).")
        else:
            try:
                oauth2 = OAuth2Component(
                    client_id=cfg["client_id"],
                    client_secret=cfg["client_secret"],
                    authorize_endpoint=cfg["auth_uri"],
                    token_endpoint=cfg["token_uri"],
                )
            except Exception as e:
                st.error(f"No pude inicializar OAuth2Component: {e}")
                oauth2 = None

            if oauth2:
                # compat scopes/scope + redirect_uri/redirect_to
                try:
                    result = oauth2.authorize_button(
                        name="Continuar con Google",
                        icon="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                        pkce="S256",
                        use_container_width=False,
                        scopes=["openid", "email", "profile"],
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
                        result = oauth2.authorize_button(
                            name="Continuar con Google",
                            icon="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                            pkce="S256",
                            use_container_width=False,
                            scope="openid email profile",
                            redirect_to=cfg["redirect_uri"],
                        )

        st.markdown('</div>', unsafe_allow_html=True)  # .cta
        st.markdown('</div>', unsafe_allow_html=True)  # .left

    with col_right:
        st.markdown('<div class="right">', unsafe_allow_html=True)
        # Hero: prioriza MP4 -> PNG -> fallback remoto
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

    # Si no hay resultado aún (no clic), salimos
    if not result:
        return None

    # ---------- Procesar token ----------
    token = result.get("token") if isinstance(result, dict) else result
    if not token:
        st.error("No se recibió el token de Google. Intenta nuevamente.")
        return None

    id_token = token.get("id_token", "") if isinstance(token, dict) else ""
    access_token = token.get("access_token", "") if isinstance(token, dict) else ""

    user = {"email": "", "name": "", "picture": ""}

    if id_token:
        try:
            info = jwt.decode(id_token, options={"verify_signature": False})
            user.update(
                email=info.get("email", ""),
                name=info.get("name", info.get("email", "")),
                picture=info.get("picture", ""),
            )
        except Exception:
            pass

    if access_token and not user["email"]:
        try:
            r = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if r.ok:
                ui = r.json()
                user.update(
                    email=ui.get("email", user["email"]),
                    name=ui.get("name", user["name"] or ui.get("email", "")),
                    picture=ui.get("picture", user["picture"]),
                )
        except Exception:
            pass

    # Permisos
    if not _is_allowed(user.get("email"), allowed_emails, allowed_domains):
        st.error("Tu cuenta no está autorizada. Consulta con el administrador.")
        return None

    # Estado de sesión compatible con gestion_app.py
    st.session_state["user"] = user
    st.session_state["user_email"] = user.get("email", "")
    st.session_state["auth_ok"] = True

    _clear_oauth_params()
    if redirect_page:
        _switch_page(redirect_page)
        st.stop()
    else:
        _safe_rerun()

    return user


def logout():
    # Limpieza agresiva de claves para evitar residuos
    for k in ("user", "user_email", "auth_ok", "auth_user", "google_user", "g_user", "email"):
        st.session_state.pop(k, None)
    _clear_oauth_params()
    _safe_rerun()
