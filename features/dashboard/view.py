# features/dashboard/view.py 
from __future__ import annotations
import importlib
import os
import types
import pandas as pd
import streamlit as st  # <-- IMPORT OK

# 🔐 ACL (para marcar modo editor / solo lectura en tabs específicas)
try:
    from features.security import acl
except Exception:
    acl = None  # Si aún no existe el módulo, no rompemos la vista.

# ======= Google Sheets (push/pull) =======
# Usa las utilidades creadas en utils/gsheets.py (fall-back seguro si no existen)
try:
    from utils.gsheets import open_sheet_by_url, read_df_from_worksheet, upsert_by_id
except Exception:
    open_sheet_by_url = None
    read_df_from_worksheet = None
    upsert_by_id = None

SHEET_TAB = "TareasRecientes"  # nombre de la pestaña en Google Sheets

def _ensure_user_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura columna UserEmail en el slice del usuario (sin pisar otras)."""
    out = df.copy()
    email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")
    if "UserEmail" not in out.columns:
        out["UserEmail"] = email
    return out

def push_user_slice_to_sheet():
    """App → Sheet (solo mis tareas; upsert por Id)."""
    if not (open_sheet_by_url and upsert_by_id):
        st.error("Faltan utilidades de Google Sheets. Verifica utils/gsheets.py.")
        return
    try:
        # URL del Sheet desde secrets (clave: gsheets_doc_url)
        url = st.secrets["gsheets_doc_url"]
        sh = open_sheet_by_url(url)

        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
        display_name = st.session_state.get("user_display_name", "") or ""
        email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

        # Filtra SOLO lo del usuario (prioriza UserEmail; si no existe, usa Responsable)
        if "UserEmail" in df_all.columns and email:
            df_user = df_all[df_all["UserEmail"] == email].copy()
        else:
            df_user = df_all[df_all["Responsable"] == display_name].copy()

        # Asegura columna UserEmail para trazabilidad en el Sheet
        df_user = _ensure_user_cols(df_user)

        # Upsert por Id en la pestaña SHEET_TAB
        res = upsert_by_id(sh, SHEET_TAB, df_user, id_col="Id")
        if res.get("ok"):
            st.success("✅ Subido al Sheet (App → Sheet).")
        else:
            st.error(res.get("msg", "Error al subir."))
    except KeyError:
        st.error("Falta `gsheets_doc_url` o credenciales en st.secrets.")
    except Exception as e:
        st.error(f"No pude subir al Sheet: {e}")

def pull_user_slice_from_sheet(replace_df_main: bool = True):
    """Sheet → App (trae TODO, filtra mis tareas y refleja en df_main)."""
    if not (open_sheet_by_url and read_df_from_worksheet):
        st.error("Faltan utilidades de Google Sheets. Verifica utils/gsheets.py.")
        return
    try:
        url = st.secrets["gsheets_doc_url"]
        sh = open_sheet_by_url(url)
        df_sheet = read_df_from_worksheet(sh, SHEET_TAB)

        display_name = st.session_state.get("user_display_name", "") or ""
        email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "")

        if not df_sheet.empty:
            if "UserEmail" in df_sheet.columns and email:
                df_user = df_sheet[df_sheet["UserEmail"] == email].copy()
            else:
                df_user = df_sheet[df_sheet["Responsable"] == display_name].copy()
        else:
            df_user = pd.DataFrame()

        if replace_df_main:
            st.session_state["df_main"] = df_user.copy()

        st.success("✅ Sincronizado desde Sheet (Sheet → App).")
        st.rerun()
    except KeyError:
        st.error("Falta `gsheets_doc_url` o credenciales en st.secrets.")
    except Exception as e:
        st.error(f"No pude sincronizar desde Sheet: {e}")

# ---------- Util: localizar la animación del héroe (se usa en portada si quisieras) ----------
def _find_hero_asset() -> str | None:
    candidates = ("hero.webm", "hero.mp4", "hero.gif",
                  "welcome_anim.webm", "welcome_anim.mp4", "welcome_anim.gif")
    for name in candidates:
        p = os.path.join("assets", name)
        if os.path.exists(p):
            return p
    return None

# ---------- Portada opcional (no usada si ya entras logueado) ----------
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
      .hero-note{font-size:12px;color:#8a8fa0;margin-top:6px;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="hero-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">👋 Bienvenidos — ENI2025</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Esta es la plataforma unificada de <b>Gestión — ENI2025</b>. '
        'Inicia sesión con tu correo autorizado para gestionar tareas, prioridades, evaluaciones y más.</div>',
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

# ---------- Loader genérico: importa un módulo y llama a su función principal ----------
def _call_view(mod_path: str, candidates: tuple[str, ...], **kwargs):
    """
    Intenta importar `mod_path` y ejecutar la primera función disponible
    en `candidates`. Si no existe, muestra un aviso amigable.
    """
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

# ---------- Vista principal: arma las 6 secciones en pestañas ----------
def render_all(user: dict | None = None):
    email = (user or {}).get("email") or st.session_state.get("user_email", "")

    # ⛔ Se elimina el subtítulo duplicado:
    # st.subheader("🗂️ Gestión – ENI 2025")

    if email:
        st.caption(f"Sesión: {email}")

    # === ACL flags (editor / solo lectura) ===
    user_acl = st.session_state.get("acl_user", {}) if isinstance(st.session_state.get("acl_user", {}), dict) else {}
    IS_EDITOR = bool(user_acl.get("can_edit_all_tabs", False))
    # Guardamos flags para que sub-vistas puedan leerlos sin romper firmas
    st.session_state["IS_EDITOR"] = IS_EDITOR
    # Columnas de solo lectura según ACL (si existe helper; si no, set vacío)
    readonly_cols = set()
    if acl and hasattr(acl, "get_readonly_cols"):
        try:
            readonly_cols = set(acl.get_readonly_cols(user_acl))
        except Exception:
            readonly_cols = set()
    st.session_state["READONLY_COLS"] = readonly_cols

    # Badge helper para indicar modo
    def _badge_readonly(msg: str = "🔒 Solo lectura. Puedes filtrar, pero no editar."):
        st.markdown(
            f"<div style='margin:2px 0 10px;padding:8px 10px;border-radius:10px;"
            f"background:#F1F5F9;color:#334155;font-size:13px;'>{msg}</div>",
            unsafe_allow_html=True
        )

    # ⛔ Se elimina el banner azul informativo:
    # st.info("La vista principal está lista para conectar tus tablas, filtros y gráficos.")

    tabs = st.tabs([
        "➕ Nueva tarea",
        "🛠️ Editar estado",
        "🚨 Nueva alerta",
        "🧭 Prioridad",
        "📝 Evaluación",
        "🕑 Tareas recientes",
    ])

    # 1) Nueva tarea
    with tabs[0]:
        with st.spinner("Cargando 'Nueva tarea'..."):
            _call_view(
                "features.nueva_tarea.view",
                ("render", "render_view", "main", "app", "render_section", "ui"),
                user=user
            )

    # 2) Editar estado  (en tu repo la carpeta es 'editar_tarea')
    with tabs[1]:
        with st.spinner("Cargando 'Editar estado'..."):
            _call_view(
                "features.editar_estado.view",
                ("render", "render_estado", "render_view", "main", "app", "ui"),
                user=user
            )

    # 3) Nueva alerta
    with tabs[2]:
        with st.spinner("Cargando 'Nueva alerta'..."):
            _call_view(
                "features.nueva_alerta.view",
                ("render", "render_view", "main", "app", "ui"),
                user=user
            )

    # 4) Prioridad (solo lectura para no-editores, pero con filtros)
    with tabs[3]:
        # Flag de solo lectura visible
        if not IS_EDITOR:
            _badge_readonly("🔒 Solo lectura en 'Prioridad'. Puedes filtrar, pero no editar ni guardar.")
        with st.spinner("Cargando 'Prioridad'..."):
            # Sub-vista leerá st.session_state['IS_EDITOR'] y ['READONLY_COLS'] si lo deseas
            _call_view(
                "features.prioridad.view",
                ("render", "render_view", "main", "app", "ui"),
                user=user
            )

    # 5) Evaluación (solo lectura para no-editores, pero con filtros)
    with tabs[4]:
        if not IS_EDITOR:
            _badge_readonly("🔒 Solo lectura en 'Evaluación'. Puedes filtrar, pero no editar ni guardar.")
        with st.spinner("Cargando 'Evaluación'..."):
            _call_view(
                "features.evaluacion.view",
                ("render", "render_view", "main", "app", "ui"),
                user=user
            )

    # 6) Tareas recientes — sub-vista
    with tabs[5]:
        with st.spinner("Cargando 'Tareas recientes'..."):
            _call_view(
                "features.historial.view",  # <- sub-vista con botones alineados
                ("render", "render_recientes", "render_tabla", "render_view", "main", "app", "ui"),
                user=user
            )
