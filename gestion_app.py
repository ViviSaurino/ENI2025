            raw_auth = params.get("auth", [""])
            raw_u    = params.get("u", [""])
            auth_flag = raw_auth[0] if raw_auth else ""
            user_name_from_qs = raw_u[0] if raw_u else ""
        except Exception:
            auth_flag = ""
            user_name_from_qs = ""

    if user_name_from_qs:
        st.session_state["user_display_name"] = user_name_from_qs

    if auth_flag == "1":
        if not st.session_state.get("password_ok", False):
            st.session_state["password_ok"] = True
            st.session_state["user_email"] = "eni2025@app"
            st.session_state["user"] = {"email": "eni2025@app"}
        return True

    # ---- Pantalla de login ----
    st.markdown(
        """
    <style>
      /* Fondo BLANCO solo para el LOGIN */
      html, body, [data-testid="stAppViewContainer"]{
        background:#FFFFFF !important;
      }

      .eni-hero-title{
        font-size:77px;
        font-weight:900;
        color:#B38CFB;
        line-height:0.80;
        margin-bottom:10px;
      }
      .eni-hero-pill{
        display:inline-block;
        padding:10px 53px;
        border-radius:12px;
        background-color:#C0C2FF;
        border:1px solid #C0C2FF;
        color:#FFFFFF;
        font-weight:700;
        font-size:14px;
        letter-spacing:0.04em;
        margin-bottom:10px;
        white-space: nowrap;
      }
      [data-testid="stAppViewContainer"] .main .stButton > button{
        background:#8FD9C1 !important;
        color:#FFFFFF !important;
        border-radius:12px !important;
        border:1px solid #8FD9C1 !important;
        font-weight:900 !important;
        letter-spacing:0.04em !important;
        text-transform:uppercase !important;
      }
      [data-testid="stAppViewContainer"] .main .stButton > button:hover{
        filter:brightness(0.97);
      }
      .eni-login-form [data-testid="stSelectbox"]{
        margin-bottom:0.0rem !important;
      }
      .eni-login-form [data-testid="stTextInput"]{
        margin-top:-0.45rem !important;
      }
    </style>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
    <style>
      html, body, [data-testid="stAppViewContainer"], .main{
        overflow: hidden !important;
      }
    </style>
    """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='margin-top:7vh;'></div>", unsafe_allow_html=True)

    space_col, col1, col2 = st.columns([0.20, 0.55, 0.35])
    with space_col:
        st.write("")
    with col1:
        st.markdown("<div class='eni-hero-title'>BIEN<br>VENIDOS</div>", unsafe_allow_html=True)

        form_col, _ = st.columns([0.66, 0.60])
        with form_col:
            st.markdown("<div class='eni-login-form'>", unsafe_allow_html=True)
            st.markdown("<div class='eni-hero-pill'>GESTIÓN DE TAREAS ENI 2025</div>", unsafe_allow_html=True)
            st.write("")

            editor_options = [
                "Brayan Pisfil 😎",
                "Elizabet Cama 🌸",
                "Enrique Oyola 🧠",
                "Jaime Agreda 📘",
                "John Talla 🛠️",
                "Lucy Advíncula 🌈",
                "Stephane Grande 📊",
                "Tiffany Bautista ✨",
                "Vivian Saurino 💜",
                "Yoel Camizán 🚀",
            ]
            default_name = st.session_state.get("user_display_name", "")
            try:
                default_index = editor_options.index(default_name)
            except ValueError:
                default_index = 0

            editor_name = st.selectbox(
                "¿Quién está editando?",
                editor_options,
                index=default_index,
                key="editor_name_login",
            )
            st.session_state["user_display_name"] = editor_name

            pwd = st.text_input("Ingresa la contraseña", type="password", key="eni_pwd")

            if st.button("ENTRAR", use_container_width=True):
                if pwd == APP_PASSWORD:
                    st.session_state["password_ok"] = True
                    st.session_state["user_email"] = "eni2025@app"
                    st.session_state["user"] = {"email": "eni2025@app"}

                    name_lower = editor_name.lower()
                    is_vivi_login = any(t in name_lower for t in ("vivian", "vivi", "saurino"))
                    is_enrique_login = any(t in name_lower for t in ("enrique", "kike", "oyola"))
                    st.session_state["is_247_user"] = bool(is_vivi_login or is_enrique_login)

                    try:
                        st.query_params["auth"] = "1"
                        st.query_params["u"] = editor_name
                    except Exception:
                        st.experimental_set_query_params(auth="1", u=editor_name)

                    st.rerun()
                else:
                    st.error("Contraseña incorrecta. Vuelve a intentarlo 🙂")

            st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        hero_video = Path("assets/hero.mp4")
        logo_img   = Path("assets/branding/eni2025_logo.png")
        if hero_video.exists():
            with open(hero_video, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode("utf-8")
            video_html = f"""
            <div style="margin-left:-280px; margin-top:-120px;">
              <video autoplay loop muted playsinline
                     style="width:100%;max-width:460px;
                            display:block;margin:0;">
                <source src="data:video/mp4;base64,{b64}" type="video/mp4">
              </video>
            </div>
            """
            st.markdown(video_html, unsafe_allow_html=True)
        elif logo_img.exists():
            st.image(str(logo_img), use_column_width=True)
        else:
            st.write("")

    return False

if not check_app_password():
    st.stop()

# ============ AUTENTICACIÓN (usuario genérico) ============
email = st.session_state.get("user_email") or (st.session_state.get("user") or {}).get("email", "eni2025@app")

# ============ Carga de ROLES / ACL ============
try:
    if "roles_df" not in st.session_state:
        st.session_state["roles_df"] = acl.load_roles(ROLES_XLSX)
    user_acl = acl.find_user(st.session_state["roles_df"], email)
except Exception as _e:
    st.error("No pude cargar el archivo de roles. Verifica data/security/roles.xlsx.")
    st.stop()

def _to_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("true", "verdadero", "sí", "si", "1", "x", "y")

if user_acl is None:
    user_acl = {}

for _k in ("is_active", "can_edit_all_tabs"):
    if _k in user_acl:
        user_acl[_k] = _to_bool(user_acl[_k])

user_acl["is_active"] = True
user_acl["can_edit_all_tabs"] = True

try:
    _roles_df = st.session_state.get("roles_df")
    if isinstance(_roles_df, pd.DataFrame):
        mask_me = _roles_df["email"].astype(str).str.lower() == (email or "").lower()
        if mask_me.any():
            _roles_df.loc[mask_me, "is_active"] = True
            _roles_df.loc[mask_me, "can_edit_all_tabs"] = True
            st.session_state["roles_df"] = _roles_df
except Exception:
    pass

if not user_acl or not user_acl.get("is_active", False):
    st.error("No tienes acceso (usuario no registrado o inactivo).")
    st.stop()

st.session_state["acl_user"] = user_acl
st.session_state["user_display_name"] = (
    st.session_state.get("user_display_name")
    or user_acl.get("display_name", "Usuario")
)
st.session_state["user_dry_run"] = bool(user_acl.get("dry_run", False))
st.session_state["save_scope"] = user_acl.get("save_scope", "all")

# ========= Hook "maybe_save" + Google Sheets ==========
def _push_gsheets(df: pd.DataFrame):
    if "gsheets" not in st.secrets or "gcp_service_account" not in st.secrets:
        raise KeyError("Faltan 'gsheets' o 'gcp_service_account' en secrets.")
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(st.secrets["gsheets"]["spreadsheet_url"])
    ws_name = st.secrets["gsheets"].get("worksheet", "TareasRecientes")
    try:
        ws = ss.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        rows = str(max(1000, len(df) + 10))
        cols = str(max(26, len(df.columns) + 5))
        ws = ss.add_worksheet(title=ws_name, rows=rows, cols=cols)
    df_out = df.copy().fillna("").astype(str)
    values = [list(df_out.columns)] + df_out.values.tolist()
    ws.clear()
    ws.update("A1", values)

def _maybe_save_chain(persist_local_fn, df: pd.DataFrame):
    res = acl.maybe_save(user_acl, persist_local_fn, df)
    try:
        if st.session_state.get("user_dry_run", False):
            res["msg"] = res.get("msg", "") + " | DRY-RUN: no se sincronizó Google Sheets."
            return res
        _push_gsheets(df)
        res["msg"] = res.get("msg", "") + " | Sincronizado a Google Sheets."
    except Exception as e:
        res["msg"] = res.get("msg", "") + f" | GSheets error: {e}"
    return res

st.session_state["maybe_save"] = _maybe_save_chain

# ====== Logout local ======
def logout():
    for k in ("user", "user_email", "password_ok", "acl_user",
              "auth_ok", "nav_section", "roles_df", "home_tile", "user_display_name"):
        st.session_state.pop(k, None)
    try:
        st.experimental_set_query_params()
    except Exception:
        pass
    st.rerun()

# ====== Navegación / permisos ======
DEFAULT_SECTION = "Gestión de tareas"

TAB_KEY_BY_SECTION = {
    "Gestión de tareas": "tareas_recientes",
    "Kanban": "kanban",
    "Gantt": "gantt",
    "Dashboard": "dashboard",
}

TILE_TO_VIEW_MODULE = {
    "nueva_tarea": "features.nueva_tarea.view",
    "nueva_alerta": "features.nueva_alerta.view",
    "editar_estado": "features.editar_estado.view",
    "prioridad_evaluacion": "features.prioridad.view",
}

def render_if_allowed(tab_key: str, render_fn):
    if acl.can_see_tab(user_acl, tab_key):
        render_fn()
    else:
        st.warning("No tienes permiso para esta sección.")

# ============ Sidebar ============
with st.sidebar:
    if LOGO_PATH.exists():
        st.markdown("<div class='eni-logo-wrap'>", unsafe_allow_html=True)
        st.image(str(LOGO_PATH), width=120)
        st.markdown("</div>", unsafe_allow_html=True)

    nav_labels = ["Gestión de tareas", "Kanban", "Gantt", "Dashboard"]
    current_section = st.session_state.get("nav_section", DEFAULT_SECTION)
    if current_section not in nav_labels:
        current_section = DEFAULT_SECTION
    default_idx = nav_labels.index(current_section)

    st.radio(
        "Navegación",
        nav_labels,
        index=default_idx,
        label_visibility="collapsed",
        key="nav_section",
        horizontal=False,
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    if st.button("🔒 Cerrar sesión", use_container_width=True):
        logout()

# ============ Datos ============
ensure_df_main()

# ===== Tarjetas rápidas (HTML con <a>, como antes) =====
def _quick_card_link(title: str, subtitle: str, icon: str, tile_key: str) -> str:
    display_name = st.session_state.get("user_display_name", "Usuario")
    u_param = quote(display_name, safe="")
    card_class = f"eni-quick-card eni-quick-card--{tile_key}"
    return f"""
    <a href="?auth=1&u={u_param}&tile={tile_key}" target="_self" class="eni-quick-card-link">
      <div class="{card_class}">
        <div class="eni-quick-card-text">
          <div class="eni-quick-card-title">{title}</div>
          <p class="eni-quick-card-sub">{subtitle}</p>
        </div>
        <div class="eni-quick-card-icon">{icon}</div>
      </div>
    </a>
    """

# ===== leer parámetro de tarjeta seleccionada (tile) =====
tile_param = ""
try:
    params = st.query_params
    raw = params.get("tile", "")
    if isinstance(raw, list):
        tile_param = raw[0] if raw else ""
    else:
        tile_param = raw
except Exception:
    try:
        params = st.experimental_get_query_params()
        raw = params.get("tile", [""])
        tile_param = raw[0] if raw else ""
    except Exception:
        tile_param = ""

if tile_param:
    st.session_state["home_tile"] = tile_param

tile = st.session_state.get("home_tile", "")

section = st.session_state.get("nav_section", DEFAULT_SECTION)
tab_key = TAB_KEY_BY_SECTION.get(section, "tareas_recientes")

# ============ Contenido principal ============
if section == "Gestión de tareas":
    dn = st.session_state.get("user_display_name", "Usuario")

    # Nombre “limpio” sin emoji final
    parts = dn.split()
    if parts:
        last = parts[-1]
        if not any(ch.isalnum() for ch in last):
            dn_clean = " ".join(parts[:-1]) or dn
        else:
            dn_clean = dn
    else:
        dn_clean = dn

    # Iniciales para el círculo (VS, EO, etc.)
    name_parts_clean = dn_clean.split()
    initials = ""
    for p in name_parts_clean[:2]:
        if p:
            initials += p[0].upper()
    initials = initials or "VS"

    # ---- Topbar siempre igual ----
    st.markdown(
        f"""
        <div class="eni-main-topbar">
          <div class="eni-main-topbar-title">📋 Gestión de tareas</div>
          <div class="eni-main-topbar-user">
            <div class="eni-main-topbar-avatar">{initials}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ===== SI HAY TARJETA SELECCIONADA → SOLO FEATURE (como Kanban/Gantt) =====
    if tile:
        module_path = TILE_TO_VIEW_MODULE.get(tile)
        if module_path:
            try:
                view_module = importlib.import_module(module_path)
                render_fn = getattr(view_module, "render", None)
                if render_fn is None:
                    render_fn = getattr(view_module, "render_all", None)

                if callable(render_fn):
                    st.markdown('<div class="eni-view-wrapper">', unsafe_allow_html=True)
                    view_module_fn_user = st.session_state.get("user")
                    render_fn(view_module_fn_user)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info(
                        "Vista pendiente para esta tarjeta "
                        "(no se encontró función 'render' ni 'render_all')."
                    )
            except Exception as e:
                st.info("No se pudo cargar la vista para esta tarjeta.")
                st.exception(e)
        else:
            st.info("Todavía no hay una vista vinculada a esta tarjeta.")

    # ===== SIN TARJETA → Banner ENCABEZADO + 5 tarjetas en fila =====
    else:
        # --- Texto de bienvenida según nombre ---
        first_name = dn_clean.split()[0] if dn_clean else "Usuario"
        first_name_l = first_name.lower()
        
        # nombres que son de mujer aunque no terminen en "a"
        female_names = {"elizabet", "lucy", "tiffany", "vivian"}
        
        if first_name_l.endswith("a") or first_name_l in female_names:
            welcome_word = "Bienvenida"
        else:
            welcome_word = "Bienvenido"

        welcome_line1 = welcome_word
        welcome_line2 = dn_clean

        # --- Banner horizontal ENCABEZADO ---
        if HEADER_IMG_PATH.exists():
            try:
                with open(HEADER_IMG_PATH, "rb") as f:
                    data = f.read()
                b64_header = base64.b64encode(data).decode("utf-8")
                st.markdown(
                    f"""
                    <div class="eni-main-hero">
                      <div class="eni-main-hero-text">
                        <div class="eni-main-hero-welcome">{welcome_line1}</div>
                        <div class="eni-main-hero-name">{welcome_line2}</div>
                      </div>
                      <img src="data:image/png;base64,{b64_header}"
                           alt="ENI 2025 encabezado"
                           class="eni-main-hero-img" />
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            except Exception:
                # Fallback sencillo
                st.image(str(HEADER_IMG_PATH), use_column_width=True)
        else:
            st.caption("Plataforma de gestión ENI — 2025")

        # --- Grid 1×5 de tarjetas debajo del banner ---
        display_name = st.session_state.get("user_display_name", "Usuario")
        u_param = quote(display_name, safe="")

        cards_html = f"""
        <div class="eni-quick-grid-wrapper">
          <div class="eni-quick-grid">
            {_quick_card_link(
                "1. Nueva tarea",
                "Registra una nueva tarea y revísalas",
                "➕",
                "nueva_tarea",
            )}
            {_quick_card_link(
                "2. Editar estado",
                "Actualiza fases y fechas de las tareas",
                "✏️",
                "editar_estado",
            )}
            {_quick_card_link(
                "3. Nueva alerta",
                "Registra alertas y riesgos prioritarios de las tareas",
                "⚠️",
                "nueva_alerta",
            )}
            {_quick_card_link(
                "4. Prioridad",
                "Revisa los niveles de prioridad de las tareas",
                "⭐",
                "prioridad_evaluacion",
            )}
            {_quick_card_link(
                "5. Evaluación",
                "Revisa las evaluaciones y cumplimiento de las tareas",
                "📝",
                "nueva_tarea",
            )}
          </div>
        </div>
        """
        st.markdown(cards_html, unsafe_allow_html=True)

elif section == "Kanban":
    st.title("🗂️ Kanban")
    def _render_kanban():
        try:
            from features.kanban.view import render as render_kanban
            render_kanban(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista Kanban pendiente (features/kanban/view.py).")
            st.exception(e)
    render_if_allowed(tab_key, _render_kanban)

elif section == "Gantt":
    st.title("📅 Gantt")
    def _render_gantt():
        try:
            from features.gantt.view import render as render_gantt
            render_gantt(st.session_state.get("user"))
        except Exception as e:
            st.info("Vista Gantt pendiente (features/gantt/view.py).")
            st.exception(e)
    render_if_allowed(tab_key, _render_gantt)

else:
    st.title("📊 Dashboard")
    def _render_dashboard():
        st.caption("Próximamente: visualizaciones y KPIs del dashboard.")
        st.write("")
    render_if_allowed(tab_key, _render_dashboard)
