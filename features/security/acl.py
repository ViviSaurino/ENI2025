# features/security/acl.py
from __future__ import annotations
from datetime import datetime
import pandas as pd
import pytz

ROLES_PATH = "data/security/roles.xlsx"
TZ = "America/Lima"

_TRUE = {"true","1","si","sí","verdadero","x","y"}

def _to_bool(x):
    return str(x).strip().lower() in _TRUE

def load_roles(path: str = ROLES_PATH) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="users", dtype=str).fillna("")
    # Booleans
    for c in ["can_edit_all_tabs","allowed_after_hours","allowed_weekends","is_active","dry_run"]:
        if c in df.columns:
            df[c] = df[c].map(_to_bool)
    # allowed_tabs -> lista
    if "allowed_tabs" in df.columns:
        def split_tabs(s):
            s = str(s).strip()
            if not s or s.upper() == "ALL":
                return ["ALL"]
            return [t.strip() for t in s.split(",") if t.strip()]
        df["allowed_tabs_list"] = df["allowed_tabs"].apply(split_tabs)
    else:
        df["allowed_tabs_list"] = [["ALL"]]*len(df)
    # save_scope normalizado
    if "save_scope" not in df.columns:
        df["save_scope"] = "all"
    df["save_scope"] = df["save_scope"].str.lower().replace({"": "all"})
    return df

def find_user(df: pd.DataFrame, email: str):
    if not email:
        return None
    m = df["email"].str.lower() == str(email).lower()
    if not m.any():
        return None
    return df[m].iloc[0].to_dict()

def now_pe():
    return datetime.now(pytz.timezone(TZ))

def can_access_now(u: dict) -> tuple[bool, str]:
    """Respeta allowed_after_hours y allowed_weekends (08:00–17:00 por defecto)."""
    if u is None:
        return False, "Usuario no registrado."
    if not u.get("is_active", False):
        return False, "Usuario inactivo."
    n = now_pe()
    # Fines de semana
    if not u.get("allowed_weekends", False) and n.weekday() >= 5:
        return False, "Bloqueado fines de semana."
    # Horario de oficina 08:00–17:00
    if not u.get("allowed_after_hours", False):
        if n.hour < 8 or n.hour >= 17:
            return False, "Bloqueado fuera de horario (08:00–17:00)."
    return True, ""

def can_see_tab(u: dict, tab_key: str) -> bool:
    tabs = u.get("allowed_tabs_list", ["ALL"])
    return "ALL" in tabs or tab_key in tabs or u.get("can_edit_all_tabs", False)

def is_dry_run(u: dict) -> bool:
    return bool(u.get("dry_run", False)) or (u.get("save_scope","all") == "none")

def maybe_save(u: dict, save_fn, *args, **kwargs):
    """Envuelve una función de guardado. Si es dry_run/none, no persiste."""
    if is_dry_run(u):
        return False, "Modo PRUEBA: no se guardó."
    return save_fn(*args, **kwargs)
