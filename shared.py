# ============================
# Utilidades compartidas (ENI2025)
# ============================
from __future__ import annotations
import os
from io import BytesIO
from datetime import datetime, date, time, timezone
import pandas as pd
import streamlit as st

# -------- Patch Streamlit + st-aggrid ----------
def patch_streamlit_aggrid():
    try:
        import streamlit.components.v1 as _stc
        import types as _types
        if not hasattr(_stc, "components"):
            _stc.components = _types.SimpleNamespace(MarshallComponentException=Exception)
    except Exception:
        pass

# --------- Zona horaria Lima ----------
try:
    import pytz
    LIMA_TZ = pytz.timezone("America/Lima")
except Exception:
    try:
        from zoneinfo import ZoneInfo
        LIMA_TZ = ZoneInfo("America/Lima")
    except Exception:
        LIMA_TZ = None

def now_lima_trimmed():
    """
    Devuelve datetime en hora de Lima, redondeado a minuto (sin tzinfo),
    robusto al timezone del servidor (convierte desde UTC).
    """
    try:
        if LIMA_TZ is None:
            return datetime.now().replace(second=0, microsecond=0)
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(LIMA_TZ)
        return now_local.replace(second=0, microsecond=0, tzinfo=None)
    except Exception:
        return datetime.now().replace(second=0, microsecond=0)

def combine_dt(d, t):
    if d in (None, "", pd.NaT):
        return pd.NaT
    if isinstance(d, str):
        d_parsed = pd.to_datetime(d, errors="coerce")
        if pd.isna(d_parsed):
            return pd.NaT
        d = d_parsed.date()
    elif isinstance(d, pd.Timestamp):
        d = d.date()
    elif isinstance(d, date):
        pass
    else:
        return pd.NaT

    if t in (None, "", "HH:mm", pd.NaT):
        return pd.Timestamp(datetime.combine(d, time(0, 0)))

    if isinstance(t, str):
        try:
            hh, mm = t.strip().split(":")
            t = time(int(hh), int(mm))
        except Exception:
            return pd.NaT
    elif isinstance(t, pd.Timestamp):
        t = time(t.hour, t.minute, t.second)
    elif isinstance(t, time):
        pass
    else:
        return pd.NaT

    try:
        return pd.Timestamp(datetime.combine(d, t))
    except Exception:
        return pd.NaT

# -------- Datos base / persistencia local --------
DATA_DIR = st.session_state.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Columnas base mínimas (no destructivo: luego preservamos extras)
COLS = st.session_state.get(
    "COLS",
    ["Id", "Área", "Responsable", "Tarea",
     "Estado", "Prioridad", "Evaluación", "Calificación",
     "Fase",
     "Fecha inicio",
     "Fecha Registro", "Hora Registro",
     "Fecha estado actual", "Hora estado actual",
     "__DEL__"]
)
TAB_NAME = st.session_state.get("TAB_NAME", "Tareas")
COLS_XLSX = [c for c in COLS if c not in ("__DEL__", "DEL")]

# Columnas de ALERTA que vamos a garantizar si la vista las usa
ALERT_COLS = [
    "¿Generó alerta?", "N° alerta",
    "Fecha de detección", "Hora de detección",
    "¿Se corrigió?",
    "Fecha de corrección", "Hora de corrección"
]

def _csv_path() -> str:
    """Ruta única de persistencia: data/tareas.csv"""
    return os.path.join(DATA_DIR, "tareas.csv")

def _read_csv_safe(path: str, cols: list[str]) -> pd.DataFrame:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame([], columns=cols)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except (pd.errors.EmptyDataError, ValueError):
        return pd.DataFrame([], columns=cols)
    # asegurar columnas mínimas
    for c in cols:
        if c not in df.columns:
            df[c] = None
    # ordenar: primero las conocidas, luego el resto (preserva extras)
    df = df[[c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]]
    return df

def read_local() -> pd.DataFrame:
    """Lee SIEMPRE desde data/tareas.csv (ruta única)."""
    return _read_csv_safe(_csv_path(), COLS)

def save_local(df: pd.DataFrame):
    """Escribe SIEMPRE en data/tareas.csv (ruta única)."""
    try:
        df.to_csv(_csv_path(), index=False, encoding="utf-8-sig")
    except Exception:
        pass

def write_sheet_tab(df: pd.DataFrame):
    """Placeholder si luego conectas a Google Sheets."""
    return False, "No conectado a Google Sheets (fallback activo)"

def _ensure_defaults(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza default de columnas críticas SIN borrar ni reordenar otras columnas.
    """
    base = df.copy()

    # Asegurar columnas base si faltan
    ensure_map_str = {
        "Estado": "No iniciado",
        "Prioridad": "Media",
        "Evaluación": "Sin evaluar",
        "Fase": "",
        "Fecha inicio": "",
        "Fecha Registro": "",
        "Hora Registro": "",
        "Fecha estado actual": "",
        "Hora estado actual": "",
    }
    for c, v in ensure_map_str.items():
        if c not in base.columns:
            base[c] = v
        base[c] = base[c].fillna(v).replace({"nan": v})

    # Calificación numérica segura 0..5
    if "Calificación" not in base.columns:
        base["Calificación"] = 0
    base["Calificación"] = pd.to_numeric(base["Calificación"], errors="coerce").fillna(0).astype(int).clip(0, 5)

    # Columna de marca de eliminación
    if "__DEL__" not in base.columns:
        base["__DEL__"] = False
    base["__DEL__"] = base["__DEL__"].fillna(False).astype(bool)

    # ===== Defaults para ALERTAS =====
    if "¿Generó alerta?" not in base.columns:
        base["¿Generó alerta?"] = "No"
    base["¿Generó alerta?"] = base["¿Generó alerta?"].fillna("No").replace({"": "No"})

    # Preferimos "N° alerta". Si solo hay "Nº alerta", la usamos para poblarla.
    if "N° alerta" not in base.columns:
        if "Nº alerta" in base.columns:
            base["N° alerta"] = pd.to_numeric(base["Nº alerta"], errors="coerce").fillna(0).astype(int).clip(lower=0)
        else:
            base["N° alerta"] = 0
    base["N° alerta"] = pd.to_numeric(base["N° alerta"], errors="coerce").fillna(0).astype(int).clip(lower=0)

    for c in ["Fecha de detección", "Hora de detección", "Fecha de corrección", "Hora de corrección"]:
        if c not in base.columns:
            base[c] = ""
        base[c] = base[c].fillna("").replace({"nan": ""})

    if "¿Se corrigió?" not in base.columns:
        base["¿Se corrigió?" ] = "No"
    base["¿Se corrigió?" ] = base["¿Se corrigió?" ].fillna("No").replace({"": "No"})

    return base

def ensure_df_main():
    """
    Rehidrata st.session_state['df_main'] en este orden:
    1) data/tareas.csv (persistencia local de 'Grabar')
    2) Google Sheets pestaña 'TareasRecientes' (filtrando por usuario, EXCEPTO super_viewers)
    3) DataFrame vacío con columnas COLS
    Además hidrata flags ACL en st.session_state['acl_user'].
    """
    if "df_main" in st.session_state:
        # Asegura flags ACL aunque la DF ya exista
        hydrate_acl_flags()
        return

    # --- 1) Intento: archivo local ---
    base = read_local()

    # --- 2) Fallback: Google Sheets (solo si local está vacío) ---
    if base is None or base.empty:
        try:
            from utils.gsheets import open_sheet_by_url, read_df_from_worksheet  # type: ignore

            url = st.secrets.get("gsheets_doc_url")
            if not url:
                try:
                    url = st.secrets["gsheets"]["spreadsheet_url"]  # type: ignore
                except Exception:
                    url = None

            email = get_user_email()
            display_name = st.session_state.get("user_display_name", "") or ""
            user_obj = {"email": email, "display": display_name}

            if url and callable(open_sheet_by_url) and callable(read_df_from_worksheet):
                sh = open_sheet_by_url(url)
                ws_name = (st.secrets.get("gsheets", {}) or {}).get("worksheet", "TareasRecientes")
                df_sheet = read_df_from_worksheet(sh, ws_name)

                if isinstance(df_sheet, pd.DataFrame) and not df_sheet.empty:
                    if is_super_viewer(user_obj):
                        base = df_sheet.copy()
                    else:
                        if "UserEmail" in df_sheet.columns and email:
                            base = df_sheet[df_sheet["UserEmail"] == email].copy()
                        elif "Responsable" in df_sheet.columns and display_name:
                            base = df_sheet[df_sheet["Responsable"] == display_name].copy()
                        else:
                            base = df_sheet.iloc[0:0].copy()  # sin columnas relevantes, no mostrar
        except Exception:
            base = base if base is not None else pd.DataFrame()

    # --- 3) Último recurso: DF vacío con columnas ---
    if base is None or base.empty:
        base = pd.DataFrame([], columns=COLS)

    # Normalizaciones + defaults sin perder columnas adicionales
    base = base.loc[:, ~pd.Index(base.columns).duplicated()].copy()
    base = _ensure_defaults(base)

    # Mantener orden: columnas base conocidas primero, luego el resto
    keep_first = [c for c in COLS if c in base.columns]
    others = [c for c in base.columns if c not in keep_first]
    st.session_state["df_main"] = base[keep_first + others].copy()

    # Hidrata flags ACL
    hydrate_acl_flags()

# --------- Fila en blanco ----------
def blank_row():
    try:
        if "COLS" in globals() and COLS:
            cols = list(COLS)
        elif "df_main" in st.session_state and isinstance(st.session_state["df_main"], pd.DataFrame) and not st.session_state["df_main"].empty:
            cols = list(st.session_state["df_main"].columns)
        else:
            cols = ["Área","Id","Tarea","Tipo","Responsable","Fase","Estado","Fecha inicio","Ciclo de mejora","Detalle"]
        row = {c: None for c in cols}
        if "__DEL__" in row:
            row["__DEL__"] = False
        return row
    except Exception:
        return {"Área":None,"Id":None,"Tarea":None,"Tipo":None,"Responsable":None,"Fase":None,"Estado":None,"Fecha inicio":None,"Ciclo de mejora":None,"Detalle":None}

# --------- Exportar a Excel ----------
def export_excel(df: pd.DataFrame, filename: str = "ENI2025_tareas.xlsx", sheet_name: str = "Tareas", **kwargs) -> BytesIO:
    if "sheet" in kwargs and not sheet_name:
        sheet_name = kwargs.pop("sheet")
    else:
        kwargs.pop("sheet", None)

    buf = BytesIO()
    engine = None
    try:
        import xlsxwriter  # noqa
        engine = "xlsxwriter"
    except Exception:
        try:
            import openpyxl  # noqa
            engine = "openpyxl"
        except Exception:
            raise ImportError("Instala 'xlsxwriter' u 'openpyxl' para exportar a Excel.")

    with pd.ExcelWriter(buf, engine=engine) as xw:
        sheet = sheet_name or "Tareas"
        (df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)).to_excel(
            xw, sheet_name=sheet, index=False
        )
        try:
            if engine == "xlsxwriter":
                ws = xw.sheets[sheet]
                for i, col in enumerate(df.columns):
                    try:
                        maxlen = int(pd.Series(df[col]).astype(str).map(len).max())
                        maxlen = max(10, min(60, maxlen + 2))
                    except Exception:
                        maxlen = 12
                    ws.set_column(i, i, maxlen)
        except Exception:
            pass
    buf.seek(0)
    return buf

# --------- Catálogos y mapas ----------
AREAS_OPC = st.session_state.get(
    "AREAS_OPC",
    ["Jefatura","Gestión","Metodología","Base de datos","Capacitación","Monitoreo","Consistencia"]
)
FASES = ["Capacitación","Post-capacitación","Pre-consistencia","Consistencia","Operación de campo"]
EMO_AREA = {"😃 Jefatura":"Jefatura","✏️ Gestión":"Gestión","💻 Base de datos":"Base de datos","📈  Metodología":"Metodología","🔠 Monitoreo":"Monitoreo","🥇 Capacitación":"Capacitación","💾 Consistencia":"Consistencia"}
EMO_COMPLEJIDAD = {"🔴 Alta":"Alta","🟡 Media":"Media","🟢 Baja":"Baja"}
EMO_PRIORIDAD   = {"🔥 Alta":"Alta","✨ Media":"Media","🍃 Baja":"Baja"}
EMO_ESTADO      = {"🍼 No iniciado":"No iniciado","⏳ En curso":"En curso"}
SI_NO = ["Sí","No"]
CUMPLIMIENTO = ["Entregado a tiempo","Entregado con retraso","No entregado","En riesgo de retraso"]

# --------- IDs por área/persona ----------
import re
def _area_initial(area: str) -> str:
    if not area: return ""
    m = re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", str(area))
    return (m.group(0).upper() if m else "")

def _person_initials(nombre: str) -> str:
    if not nombre: return ""
    parts = [p for p in re.split(r"\s+", str(nombre).strip()) if p]
    if not parts: return ""
    import re as _re
    ini1 = _re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", parts[0])[:1].upper() if parts else ""
    ini2 = ""
    for p in parts[1:]:
        t = _re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", p)
        if t:
            ini2 = t[0].upper()
            break
    return f"{ini1}{ini2}"

def make_id_prefix(area: str, responsable: str) -> str:
    return f"{_area_initial(area)}{_person_initials(responsable)}"

def next_id_by_person(df: pd.DataFrame, area: str, responsable: str) -> str:
    prefix = make_id_prefix(area, responsable)
    if not prefix:
        return ""
    if "Id" not in df.columns or df.empty:
        seq = 1
    else:
        serie = df["Id"].astype(str).fillna("")
        seq = 1 + serie.str.startswith(prefix + "_").sum()
    return f"{prefix}_{seq}"

# --------- CSS global ----------
def inject_global_css():
    st.markdown("""
<style>
:root{
  --lilac:#B38BE3; --lilac-50:#F6EEFF; --lilac-600:#8B5CF6;
  --blue-pill-bg:#38BDF8; --blue-pill-bd:#0EA5E9; --blue-pill-fg:#ffffff;
  --pill-h:36px; --pill-width:158px;
  --pill-azul:#94BEEA; --pill-azul-bord:#94BEEA;
  --pill-rosa:#67D3C4; --pill-rosa-bord:#67D3C4;
}
/* Sidebar */
[data-testid="stSidebar"]{ background:var(--lilac-50) !important; border-right:1px solid #ECE6FF !important; }
[data-testid="stSidebar"] a{ color:var(--lilac-600) !important; font-weight:600 !important; text-decoration:none !important; }
/* Espaciados */
.block-container h1{ margin-bottom:18px !important; }
.topbar, .topbar-ux, .topbar-na, .topbar-pri, .topbar-eval{ margin:12px 0 !important; }
.form-card{ margin-top:10px !important; margin-bottom:28px !important; }
/* Inputs */
.form-card [data-baseweb="input"] > div,
.form-card [data-baseweb="textarea"] > div,
.form-card [data-baseweb="select"] > div,
.form-card [data-baseweb="datepicker"] > div{
  min-height:44px !important; border-radius:12px !important; border:1px solid #E5E7EB !important; background:#fff !important;
}
/* Píldoras celestes */
.form-title,.form-title-ux,.form-title-na{
  display:inline-flex !important; align-items:center !important; gap:.5rem !important;
  padding:6px 12px !important; border-radius:12px !important; background:var(--pill-azul) !important;
  border:1px solid var(--pill-azul-bord) !important; color:#fff !important; font-weight:800 !important;
  margin:6px 0 10px 0 !important; width:var(--pill-width) !important; justify-content:center !important;
  box-shadow:0 6px 16px rgba(148,190,234,.3) !important; min-height:var(--pill-h) !important; height:var(--pill-h) !important;
}
/* SELECT más anchos en primera columna de filas 1 y 2 */
.form-card [data-baseweb="select"] > div{ min-width:240px !important; }
.form-card [data-testid="stHorizontalBlock"]:nth-of-type(1) > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width:300px !important; }
.form-card [data-testid="stHorizontalBlock"]:nth-of-type(2) > [data-testid="column"]:first-child [data-baseweb="select"] > div{ min-width:300px !important; }
/* Topbar layout */
.topbar, .topbar-ux, .topbar-na{ display:flex !important; align-items:center !important; gap:8px !important; }
topbar .stButton>button, .topbar-ux .stButton>button, .topbar-na .stButton>button{
  height:var(--pill-h) !important; padding:0 16px !important; border-radius:10px !important; display:inline-flex !important; align-items:center !important;
}
</style>
""", unsafe_allow_html=True)

# === ACL helper (Vivi/Enrique ven todo; el resto solo sus tareas) ===============
import re as _re, unicodedata as _ud
import pandas as _pd
import streamlit as _st

def _norm_txt(s: str) -> str:
    """lower, sin tildes, sin dobles espacios, sin HTML."""
    if s is None:
        return ""
    s = _re.sub(r"<[^>]+>", "", str(s)).strip().lower()
    s = _ud.normalize("NFD", s)
    s = "".join(ch for ch in s if _ud.category(ch) != "Mn")
    s = _re.sub(r"\s+", " ", s)
    return s

def get_user_email() -> str:
    return (
        str(_st.session_state.get("auth_email") or "") or
        str(_st.session_state.get("user_email") or "") or
        str((_st.session_state.get("user") or {}).get("email", "") or "")
    )

def alias_from_email(email: str) -> str:
    """
    Retorna alias/display para un email usando [resp_alias] de secrets.
    Si no existe, devuelve la parte local del correo (como fallback simple).
    """
    try:
        m = dict(_st.secrets.get("resp_alias", {}))
        if email in m:
            return m[email]
    except Exception:
        pass
    try:
        return (email or "").split("@", 1)[0]
    except Exception:
        return email or ""

def _user_tokens(user: dict | None = None) -> set[str]:
    """Tokens comparables: nombre, email, usuario (parte local), display."""
    u = {**(user or {}), **_st.session_state.get("user", {})}
    vals = {
        str(u.get("email", "")).strip(),
        str(_st.session_state.get("auth_email", "")).strip(),
        str(_st.session_state.get("user_email", "")).strip(),
        str(u.get("name", "")).strip(),
        str(u.get("username", "")).strip(),
        str(u.get("display", "")).strip(),
    }
    tokens = {_norm_txt(v) for v in vals if v}
    # agrega parte local del correo
    for v in list(vals):
        if isinstance(v, str) and "@" in v:
            tokens.add(_norm_txt(v.split("@", 1)[0]))
    return {t for t in tokens if t}

def is_super_viewer(user: dict | None = None) -> bool:
    """Lee super_viewers de secrets; si no hay, usa ['vivi', 'enrique'] como fallback."""
    sv = _st.secrets.get("super_viewers", ["vivi", "enrique"])
    sv = {_norm_txt(x) for x in sv}
    toks = _user_tokens(user)
    return any(t in sv for t in toks)

def can_edit_all_tabs(user: dict | None = None) -> bool:
    """
    True si el email del usuario está en [acl].editor_emails.
    Si no existe ese bloque, por compatibilidad: permite a super_viewers.
    """
    try:
        editors = list((_st.secrets.get("acl") or {}).get("editor_emails", []))
        editors_norm = {_norm_txt(x) for x in editors}
        toks = _user_tokens(user)
        if editors_norm:
            return any(t in editors_norm for t in toks)
    except Exception:
        pass
    # Fallback: super_viewers también editan todo
    return is_super_viewer(user)

def hydrate_acl_flags(user: dict | None = None):
    """
    Guarda flags ACL en st.session_state['acl_user'] para uso en vistas.
    Si existe features/security/acl.py:
      - Carga roles, ubica usuario y deriva permisos (can_edit_all_tabs, etc.).
      - Expone st.session_state['maybe_save'] = lambda fn,*a,**k: acl.maybe_save(user_row, fn, *a, **k)
      - Expone columnas de solo-lectura: st.session_state['acl_user']['read_only_cols'] (set)
    """
    # Identidad base
    u = user or {
        "email": get_user_email(),
        "display": _st.session_state.get("user_display_name", "") or "",
    }

    # Defaults (fallback a secrets)
    acl_out = {
        "email": u.get("email", ""),
        "display": u.get("display", ""),
        "is_super_viewer": is_super_viewer(u),
        "can_edit_all_tabs": can_edit_all_tabs(u),
    }
    read_only_cols = set()

    # Intento: consumir features/security/acl.py
    try:
        from features.security import acl as _acl  # type: ignore

        # Cargar roles y fila de usuario
        roles_df = _acl.load_roles()
        user_row = _acl.find_user(roles_df, acl_out["email"])

        if user_row:
            # can_edit_all_tabs desde roles tiene prioridad
            try:
                acl_out["can_edit_all_tabs"] = bool(user_row.get("can_edit_all_tabs", False))
            except Exception:
                pass

            # Guardar wrapper de persistencia según política
            def _maybe_save(fn, *args, **kwargs):
                return _acl.maybe_save(user_row, fn, *args, **kwargs)

            st.session_state["maybe_save"] = _maybe_save

            # Columnas de solo lectura
            try:
                read_only_cols = _acl.get_readonly_cols(user_row)
            except Exception:
                read_only_cols = set()

            # (Opcional) Mensaje de horario/fin de semana; no bloquea UI
            try:
                ok_now, msg = _acl.can_access_now(user_row)
                acl_out["access_now_ok"] = bool(ok_now)
                acl_out["access_now_msg"] = str(msg or "")
            except Exception:
                pass

            # Alias de display si está en roles (no pisa el que ya tengas)
            try:
                disp = (user_row.get("display_name") or "").strip()
                if disp:
                    acl_out["display"] = disp
            except Exception:
                pass

        else:
            # Si no hay coincidencia en roles, mantener fallback y limpiar maybe_save previo
            if "maybe_save" in st.session_state and not callable(st.session_state.get("maybe_save")):
                st.session_state.pop("maybe_save", None)

    except Exception:
        # Sin módulo ACL: si existía maybe_save de una sesión anterior, lo dejamos si es callable
        if "maybe_save" in st.session_state and not callable(st.session_state.get("maybe_save")):
            st.session_state.pop("maybe_save", None)

    # Persistir flags en session_state
    _st.session_state.setdefault("acl_user", {})
    _st.session_state["acl_user"].update(acl_out)
    if read_only_cols:
        _st.session_state["acl_user"]["read_only_cols"] = set(read_only_cols)

def _owns_name(cell_value: str, allowed: set[str]) -> bool:
    """¿El valor de 'Responsable' contiene alguno de los candidatos?"""
    nv = _norm_txt(cell_value)
    if not nv:
        return False
    # admite múltiples responsables separados por , ; / |
    parts = {_norm_txt(p) for p in _re.split(r"[,;/|]", nv) if p}
    # match exacto por token o substring tolerante
    return any((a in parts) or (a and a in nv) for a in allowed)

def apply_scope(df: _pd.DataFrame, user: dict | None = None, resp_col: str = "Responsable") -> _pd.DataFrame:
    """
    Si user ∈ super_viewers => df completo.
    Si no, filtra por 'Responsable'≈usuario (con alias opcional) y/o por columnas de correo.
    """
    if not isinstance(df, _pd.DataFrame) or df.empty:
        return df

    # 1) Super viewers
    if is_super_viewer(user):
        return df

    # 2) Identidad de usuario
    toks = _user_tokens(user)  # incluye email, parte local, nombre display (normalizados)
    # Alias opcional (secrets: [resp_alias])
    alias_raw = dict(_st.secrets.get("resp_alias", {}))
    alias_map = {_norm_txt(k): _norm_txt(v) for k, v in alias_raw.items()}

    allowed = set(toks)
    # Expande con alias si existen
    for t in list(toks):
        if t in alias_map:
            allowed.add(alias_map[t])

    if not allowed:
        # no sabemos quién es: no mostramos nada
        return df.iloc[0:0].copy()

    # 3) Columnas candidatas
    name_cols = [c for c in df.columns if _norm_txt(c) in {
        "responsable","responsables","responsable/a","asignado a","asignada a"
    }]
    mail_cols = [c for c in df.columns if _norm_txt(c) in {
        "correo","email","e-mail","useremail","user email"
    }]

    # 4) Construir máscara
    mask = _pd.Series(False, index=df.index)

    if name_cols:
        ser = df[name_cols[0]].astype(str).fillna("")
        mask = mask | ser.map(lambda v: _owns_name(v, allowed))

    # intenta por correo si hay columna y algún token parece correo/usuario
    if mail_cols:
        email_like = [t for t in allowed if "@" in t or t.isalnum()]
        if email_like:
            em = df[mail_cols[0]].astype(str).str.lower()
            for t in email_like:
                mask = mask | em.str.contains(_re.escape(t), na=False)

    # 5) Si no hay columnas relevantes, por seguridad no mostrar nada
    if not name_cols and not mail_cols:
        return df.iloc[0:0].copy()

    return df.loc[mask].copy()
# === fin ACL helper =============================================================

# === Historial / TareasRecientes (log universal de "Nueva tarea") ===============
def log_reciente(
    sheet,
    tarea_nombre: str,
    especialista: str = "",
    detalle: str = "Asignada",
    tab_name: str = "TareasRecientes",
    id_val: str | None = None,
):
    """
    Registra SIEMPRE (sin ACL) un evento de 'Nueva tarea' en la hoja `tab_name`.
    - Usa hora Lima (minutos, sin tzinfo).
    - Incluye columnas de identidad para visibilidad por usuario: 'Responsable' y 'UserEmail'.
    - Acepta `id_val` para persistir el Id de la tarea (además de un `id` interno de fila).
    - Se alinea a las columnas existentes si la hoja ya tiene un esquema propio.
    - Limpia el cache de Streamlit para que el Historial refleje el cambio al instante.
    """
    from uuid import uuid4
    import pandas as _pd_local

    _email = get_user_email()
    _ts = now_lima_trimmed().strftime("%Y-%m-%d %H:%M")
    tarea_txt = (tarea_nombre or "").strip()
    resp_txt = (especialista or "").strip()

    row = {
        # Row-id técnico para upsert/append en la hoja de historial
        "id": uuid4().hex[:10].upper(),
        # Id de la tarea del tablero (si existe)
        "Id": id_val or "",
        # Campos de control/visualización
        "fecha": _ts,
        "accion": "Nueva tarea",
        # Compatibilidad histórica (minúsculas) y nueva (Título con mayúscula)
        "tarea": tarea_txt,
        "Tarea": tarea_txt,
        # Identidad para filtros y visibilidad
        "especialista": resp_txt,   # legacy
        "Responsable": resp_txt,    # preferida
        "UserEmail": (_email or "").strip(),
        "detalle": (detalle or "").strip(),
    }

    try:
        # Intentar libs de Google Sheets si existen
        try:
            from utils.gsheets import read_df_from_worksheet, upsert_by_id  # type: ignore
        except Exception:
            read_df_from_worksheet = None
            upsert_by_id = None

        # Si no hay sheet, no hay a dónde escribir
        if sheet is None:
            raise RuntimeError("No se ha abierto el spreadsheet (sheet=None).")

        df_exist = None
        if callable(read_df_from_worksheet):
            try:
                df_exist = read_df_from_worksheet(sheet, tab_name)
            except Exception:
                df_exist = None

        if isinstance(df_exist, _pd_local.DataFrame) and not df_exist.empty:
            cols = list(df_exist.columns)
            payload = _pd_local.DataFrame([{c: row.get(c, "") for c in cols}], columns=cols)
        else:
            payload = _pd_local.DataFrame([row])

        if callable(upsert_by_id) and "id" in payload.columns:
            upsert_by_id(sheet, tab_name, payload, id_col="id")
        else:
            # Append simple
            ws = sheet.worksheet(tab_name)
            ws.append_rows(payload.astype(str).values.tolist())

        try:
            st.cache_data.clear()
        except Exception:
            pass

    except Exception as e:
        # No interrumpir el flujo del formulario: mostrar toast y continuar
        st.toast(f"No se pudo registrar en {tab_name}: {e}", icon="⚠️")
