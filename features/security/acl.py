# features/security/acl.py
from __future__ import annotations

from datetime import datetime
import os
import pandas as pd
import pytz

# Ruta por defecto (permite override vía variable de entorno)
ROLES_PATH = os.getenv("ACL_ROLES_PATH", "data/security/roles.xlsx")
TZ = "America/Lima"

_TRUE = {"true", "1", "si", "sí", "verdadero", "x", "y"}
_FALSE = {"false", "0", "no", "falso", ""}

# Esquema esperado mínimo (para tolerar archivos vacíos o ausentes)
_EXPECTED_COLS = [
    "person_id", "email", "display_name", "role", "can_edit_all_tabs",
    "allowed_tabs", "allowed_after_hours", "allowed_weekends",
    "is_active", "avatar_url", "dry_run", "save_scope",
    "read_only_cols",
]

def _to_bool(x) -> bool:
    s = str(x).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    # fallback: cualquier cosa distinta de los falsos explícitos
    return bool(s)

def _empty_roles_df() -> pd.DataFrame:
    """DF vacío con columnas mínimas para no romper el flujo si falta el Excel."""
    df = pd.DataFrame([], columns=_EXPECTED_COLS)
    # Tipos razonables
    for c in ["can_edit_all_tabs", "allowed_after_hours", "allowed_weekends", "is_active", "dry_run"]:
        if c not in df.columns:
            df[c] = False
    if "save_scope" not in df.columns:
        df["save_scope"] = "all"
    if "read_only_cols" not in df.columns:
        df["read_only_cols"] = ""
    return df

def load_roles(path: str = ROLES_PATH) -> pd.DataFrame:
    """
    Carga el Excel de roles aceptando:
      - Hoja 'acl_users' (preferida)
      - Hoja 'users' (compatibilidad)
      - En su defecto, la primera hoja del libro

    Endurecido:
      - Si el archivo no existe o viene dañado, retorna DF vacío con columnas esperadas.
      - Normaliza columnas y tipos sin romper si faltan.
    """
    # Si no hay archivo, retornar estructura vacía tolerante
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return _empty_roles_df()

    try:
        xl = pd.ExcelFile(path)
        if "acl_users" in xl.sheet_names:
            sheet = "acl_users"
        elif "users" in xl.sheet_names:
            sheet = "users"
        else:
            sheet = xl.sheet_names[0]

        df = xl.parse(sheet, dtype=str).fillna("")
    except Exception:
        # Archivo inválido/ilegible
        return _empty_roles_df()

    # Asegurar todas las columnas esperadas
    for c in _EXPECTED_COLS:
        if c not in df.columns:
            df[c] = ""

    # Bools en español/inglés
    for c in ["can_edit_all_tabs", "allowed_after_hours", "allowed_weekends", "is_active", "dry_run"]:
        df[c] = df[c].map(_to_bool)

    # Normaliza allowed_tabs a cadena sin espacios en extremos
    df["allowed_tabs"] = df["allowed_tabs"].astype(str).map(lambda s: s.strip())

    # Normaliza save_scope
    df["save_scope"] = df["save_scope"].astype(str).str.lower().replace({"": "all"})

    # Asegura tipo string para read_only_cols (lista separada por comas)
    df["read_only_cols"] = df["read_only_cols"].astype(str)

    return df

def find_user(df: pd.DataFrame, email: str) -> dict:
    em = (email or "").strip().lower()
    if not em or not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    try:
        m = df[df["email"].astype(str).str.strip().str.lower() == em]
    except Exception:
        return {}
    if m.empty:
        return {}
    return m.iloc[0].to_dict()

def _now_lima() -> datetime:
    return datetime.now(pytz.timezone(TZ))

def can_access_now(user_row: dict) -> tuple[bool, str]:
    """
    Restringe por horario (8:00–17:00) y fines de semana,
    a menos que el usuario tenga las banderas de excepción.
    """
    try:
        now = _now_lima()
        is_weekend = now.weekday() >= 5  # 5=sábado, 6=domingo
        hour = now.hour

        allow_after = bool(user_row.get("allowed_after_hours", False))
        allow_weekend = bool(user_row.get("allowed_weekends", False))

        # Fines de semana
        if is_weekend and not allow_weekend:
            return (False, "Acceso restringido los fines de semana (no estás en la lista permitida).")

        # Horario laboral 08:00–17:00
        if not (8 <= hour < 17) and not allow_after:
            return (False, "Acceso fuera de horario (08:00–17:00). No estás habilitada/o para fuera de horario).")
        return (True, "")
    except Exception:
        # Ante cualquier problema de tz/fecha, mejor permitir
        return (True, "")

def _split_tabs(s: str) -> set[str]:
    # soporta 'ALL' y lista separada por comas
    t = (s or "").strip()
    if not t:
        return set()
    if t.upper() == "ALL":
        return {"ALL"}
    return {x.strip() for x in t.split(",") if x.strip()}

def can_see_tab(user_row: dict, tab_key: str) -> bool:
    if bool(user_row.get("can_edit_all_tabs", False)):
        return True
    tabs = _split_tabs(str(user_row.get("allowed_tabs", "")))
    if "ALL" in tabs:
        return True
    return tab_key in tabs

def maybe_save(user_row: dict, fn, *args, **kwargs):
    """
    Envoltura para persistencias:
      - Si dry_run=True -> no guarda.
      - Si save_scope='none' -> no guarda.
      - Si save_scope='self' y la acción no es del usuario, puedes filtrar afuera.
      - Si save_scope='all' -> guarda normal.
    """
    if bool(user_row.get("dry_run", False)):
        return {"ok": False, "msg": "DRY-RUN: cambios no persistidos."}

    scope = str(user_row.get("save_scope", "all")).lower()
    if scope in {"", "none"}:
        return {"ok": False, "msg": "Guardado deshabilitado por política (save_scope=none)."}

    # Para 'self', deja que cada vista valide que la fila pertenezca al usuario.
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"ok": False, "msg": f"Error al guardar: {e}"}

# ===== Soporte a columnas de solo lectura por usuario =====
def _split_list(s: str) -> set[str]:
    """Convierte 'a, b, c' -> {'a','b','c'} (sin espacios vacíos)."""
    return {x.strip() for x in str(s or "").split(",") if x and x.strip()}

def get_readonly_cols(user_row: dict) -> set[str]:
    """
    Devuelve el conjunto de columnas que deben ser solo-lectura para este usuario.
    Se alimenta desde la columna 'read_only_cols' del Excel de roles.
    """
    return _split_list(user_row.get("read_only_cols", ""))

# === Helper: hidratar st.session_state['acl_user'] desde el Excel de roles ===
def set_acl_user_from_roles(email: str) -> dict:
    """
    Carga la fila del usuario por email y actualiza st.session_state['acl_user']
    con 'display_name', 'area' y 'role' (sin tocar otros flags).
    """
    from streamlit import session_state as _ss  # import local y perezoso
    row = find_user(load_roles(), email) or {}

    _ss.setdefault("acl_user", {})
    _ss["acl_user"].update({
        "email": email or _ss["acl_user"].get("email", ""),
        "display_name": row.get("display_name", "") or _ss["acl_user"].get("display_name", ""),
        "area": row.get("area", "") or _ss["acl_user"].get("area", ""),
        "role": row.get("role", "") or _ss["acl_user"].get("role", ""),
    })
    return row
