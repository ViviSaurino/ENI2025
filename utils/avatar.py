# utils/avatar.py
from __future__ import annotations
from pathlib import Path
import streamlit as st

def _resolve_avatar(link: str | None) -> str | None:
    """Acepta nombre simple, ruta relativa o URL. Busca en assets/avatars y assets/avatar."""
    if not link:
        return None
    s = str(link).strip()

    # URL directa
    if s.startswith(("http://", "https://")):
        return s

    p = Path(s)
    # Ruta relativa que ya apunta a un archivo
    if p.is_file():
        return str(p)

    # Si viene sin o con extensión, probamos variantes
    has_ext = p.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}
    candidates = [p] if has_ext else [Path(s + ext) for ext in (".png", ".webp", ".jpg", ".jpeg")]

    bases = [Path("."), Path("assets/avatars"), Path("assets/avatar"), Path("assets")]
    for base in bases:
        for name in candidates:
            cand = base / name
            if cand.is_file():
                return str(cand)
    return None

def _initials(name: str) -> str:
    parts = [p for p in str(name).strip().split() if p]
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()

def _render_initials_circle(name: str, size: int = 96):
    initials = _initials(name or "U")
    st.markdown(f"""
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
    """, unsafe_allow_html=True)

def show_avatar_above_greeting(link: str | None, size: int = 96, name_for_fallback: str = "Usuario"):
    # CSS una sola vez
    if "_avatar_css" not in st.session_state:
        st.session_state["_avatar_css"] = True
        st.markdown("""
        <style>
          .avatar-wrap{ display:flex; justify-content:center; margin-bottom:8px; }
          .avatar-wrap img{
            border-radius:9999px !important;   /* círculo */
            box-shadow:none !important;        /* sin borde */
            background:transparent !important; /* respeta PNG transparente */
          }
        </style>
        """, unsafe_allow_html=True)

    src = _resolve_avatar(link)
    if src:
        st.markdown('<div class="avatar-wrap">', unsafe_allow_html=True)
        st.image(src, width=size, output_format="PNG")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        _render_initials_circle(name_for_fallback, size=size)
