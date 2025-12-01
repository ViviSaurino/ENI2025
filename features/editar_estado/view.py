# features/editar_estado/view.py
from __future__ import annotations
import os
import re
import random
import base64
from pathlib import Path
import pandas as pd
import streamlit as st
from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    DataReturnMode,
    JsCode,
)

# ✅ Asegurar que exista la clave en session_state
if "est_visible" not in st.session_state:
    st.session_state["est_visible"] = True   # así la vista se muestra por defecto

# ======= Toggle: Upsert a Google Sheets (AHORA True por defecto si hay secrets) =======
DO_SHEETS_UPSERT = bool(st.secrets.get("edit_estado_upsert_to_sheets", True))

# ===== Helper para imágenes del encabezado =====
def _img_b64(name: str) -> str:
    """
    Devuelve la imagen en base64 buscando en assets/ con extensiones comunes.
    Si no la encuentra, devuelve cadena vacía (no rompe la app).
    """
    try:
        base_dir = Path("assets")
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            p = base_dir / f"{name}{ext}"
            if p.exists():
                return base64.b64encode(p.read_bytes()).decode("utf-8")
    except Exception:
        pass
    return ""

# Hora Lima para sellado de cambios + ACL
try:
    from shared import now_lima_trimmed, apply_scope
except Exception:
    from datetime import datetime, timedelta
    def now_lima_trimmed():
        return (datetime.utcnow() - timedelta(hours=5)).replace(second=0, microsecond=0)
    def apply_scope(df, user=None, resp_col="Responsable"):
        return df

# ========= Utilidades mínimas para zonas horarias =========
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None

def _now_lima_trimmed_local():
    from datetime import datetime, timedelta
    try:
        if _TZ:
            return datetime.now(_TZ).replace(second=0, microsecond=0)
        return (datetime.utcnow() - timedelta(hours=5)).replace(second=0, microsecond=0)
    except Exception:
        return now_lima_trimmed()

def _to_naive_local_one(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return pd.NaT
    try:
        if isinstance(x, pd.Timestamp):
            if x.tz is not None:
                d = x.tz_convert(_TZ or x.tz).tz_localize(None) if _TZ else x.tz_localize(None)
                return d
            return x
        s = str(x).strip()
        if not s or s.lower() in {"nan", "nat", "none", "null"}:
            return pd.NaT
        if re.search(r'(Z|[+-]\d{2}:?\d{2})$', s):
            d = pd.to_datetime(s, errors="coerce", utc=True)
            if pd.isna(d):
                return pd.NaT
            if _TZ:
                d = d.tz_convert(_TZ)
            return d.tz_localize(None)
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT

def _fmt_hhmm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        s = str(v).strip()
        if not s or s.lower() in {"nan", "nat", "none", "null"}:
            return ""
        m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", s)
        if m:
