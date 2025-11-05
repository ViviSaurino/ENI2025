# utils/avatar.py
from __future__ import annotations
from pathlib import Path
import streamlit as st

# -------------------------------------------------------------------
# Utilidades para resolver y renderizar avatares:
# - Acepta URL http(s), ruta relativa/absoluta o nombre simple
# - Si no hay extensión, prueba .png/.webp/.jpg/.jpeg en assets/
# - Fallback: círculo con iniciales
# - Helper extra: show_user_avatar_from_session(...)
# -------------------------------------------------------------------

_ASSET_DIRS = (
    Path("."),                # por si envías ruta relativa válida
    Path("assets/avatars"),
    Path("assets/avatar"),
    Path("assets"),           # último intento
)

_EXTS = (".png", ".webp", ".jpg", ".jpeg")


def _resolve_avatar(link: str | None) -> str | None:
    """
    Resuelve un 'link' hacia un archivo de imagen:
    - Si es URL http(s) ⇒ se usa tal cual.
    - Si es ruta existente ⇒ se usa.
    - Si es nombre simple (con o sin extensión) ⇒ busca en assets/.
    """
    if not link:
        return None

    s = str(link).strip()
    if not s:
        return None

    # URL directa
    if s.startswith(("http://", "https://")):
        return s

    p = Path(s)

    # Ruta que ya existe
    if p.is_file():
        return str(p)

    # Nombre simple: probar variantes de extensión en asset dirs
    has_ext = p.suffix.lower() in _EXTS
    candidates = [p] if has_ext else [Path(s + ext) for ext in _EXTS]

    for base in _ASSET_DIRS:
        for name in candidates:
            cand = base / name
            if cand.is_file():
                return str(cand)

    return None


def _initials(name: str) -> str:
    parts = [p for p in str(name or "").strip().split() if p]
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _render_initials_circle(name: str, size: int = 96):
    initials = _initials(name)
    st.markdown(
        f"""
        <div class="avatar-wrap">
          <div style="
            width:{size}px;height:{size}px;border-radius:9999px;
            display:flex;align-items:center;justify-content:center;
            background:#EDE9FE;color:#4C1D95;font-weight:700;
            font-family: system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial;
            font-size:{int(size*0.36)}px;">
            {initials}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_avatar_above_greeting(
    link: str | None,
    size: int = 96,
    name_for_fallback: str = "Usuario",
):
    """
    Muestra un avatar circular (sin borde) encima del saludo.
    - link: URL, ruta o nombre simple (se buscará en assets/avatars, assets/avatar, assets).
    - size: tamaño en px del lado del círculo.
    - name_for_fallback: se usa para iniciales si no hay imagen.
    """
    # CSS solo una vez por sesión
    if "_avatar_css" not in st.session_state:
        st.session_state["_avatar_css"] = True
        st.markdown(
            """
            <style>
              .avatar-wrap{ display:flex; justify-content:center; margin-bottom:8px; }
              .avatar-wrap img{
                border-radius:9999px !important;   /* círculo */
                box-shadow:none !important;        /* sin borde */
                background:transparent !important; /* respeta PNG transparente */
              }
            </style>
            """,
            unsafe_allow_html=True,
        )

    src = _resolve_avatar(link)
    if src:
        st.markdown('<div class="avatar-wrap">', unsafe_allow_html=True)
        st.image(src, width=size, output_format="PNG")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        _render_initials_circle(name_for_fallback, size=size)


# ------------------------------------------------------------
# Helper opcional: pinta usando los datos ya cargados en sesión
# (por ejemplo, st.session_state["acl_user"]["avatar_url"]).
# No rompe nada si no existe.
# ------------------------------------------------------------
def show_user_avatar_from_session(
    session_key: str = "acl_user",
    link_field: str = "avatar_url",
    name_field: str = "name",
    size: int = 135,
):
    acl = st.session_state.get(session_key, {}) or {}
    link = acl.get(link_field)
    name = acl.get(name_field, "Usuario")
    show_avatar_above_greeting(link, size=size, name_for_fallback=name)
