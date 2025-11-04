# features/security/acl.py
from __future__ import annotations

from datetime import datetime
import pandas as pd
import pytz

ROLES_PATH = "data/security/roles.xlsx"
TZ = "America/Lima"

_TRUE = {"true", "1", "si", "sí", "verdadero", "x", "y"}
_FALSE = {"false", "0", "no", "falso", ""}


def _to_bool(x) -> bool:
    s = str(x).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    # fallback: cualquier cosa distinta de los falsos explícitos
    return bool(s)


def load_roles(path: str = ROLES_PATH) -> pd.DataFrame:
    """
    Carga el Excel de roles aceptando:
      - Hoja 'acl_users' (preferida)
      - Hoja 'users' (compatibilidad)
      - En su defecto, la primera hoja del libro
    """
    xl = pd.ExcelFile(path)
    sheet = None
    if "acl_users" in xl.sheet_names:
        sheet = "acl_users"
    elif "users" in xl.sheet_names:
        sheet = "users"
    else:
        sheet = xl.sheet_names[0]

    df = xl.parse(sheet, dtype=str).fillna("")

    # Normalizamos columnas que deberían existir (si faltan, las creamos vacías)
    for c in [
        "person_id", "email", "display_name", "role", "can_edit_all_tabs",
        "allowed_tabs", "allowed_after_hours", "allowed_weekends",
        "is_active", "avatar_url", "dry_run", "save_scope",
        "read_only_cols",  # <-- NUEVO: columnas de solo lectura por usuario
    ]:
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
    if not em:
        return {}
    m = df[df["email"].str.strip().str.lower() == em]
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
    now = _now_lima()
    is_weekend = now.weekday() >= 5  # 5=sábado,6=domingo
    hour = now.hour

    allow_after = bool(user_row.get("allowed_after_hours", False))
    allow_weekend = bool(user_row.get("allowed_weekends", False))

    # Fines de semana
    if is_weekend and not allow_weekend:
        return (False, "Acceso restringido los fines de semana (no estás en la lista permitida).")

    # Horario laboral 08:00–17:00
    if not (8 <= hour < 17) and not allow_after:
        return (False, "Acceso fuera de horario (08:00–17:00). No estás habilitada/o para fuera de horario.")

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
    # Aquí simplemente ejecutamos.
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"ok": False, "msg": f"Error al guardar: {e}"}


# ===== NUEVO: soporte a columnas de solo-lectura por usuario =====

def _split_list(s: str) -> set[str]:
    """
    Convierte 'a, b, c' -> {'a','b','c'} (sin espacios vacíos).
    """
    return {x.strip() for x in str(s or "").split(",") if x and x.strip()}


def get_readonly_cols(user_row: dict) -> set[str]:
    """
    Devuelve el conjunto de columnas que deben ser solo-lectura para este usuario.
    Se alimenta desde la columna 'read_only_cols' del Excel de roles.
    """
    return _split_list(user_row.get("read_only_cols", ""))
