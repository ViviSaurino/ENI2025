# features/historial/view.py
from __future__ import annotations

import os, re
from io import BytesIO
from datetime import date
import numpy as np
import pandas as pd
import streamlit as st
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

# ================== Config base ==================
TAB_NAME = "Tareas"
DEFAULT_COLS = [
    "Id","Área","Fase","Responsable",
    "Tarea","Tipo","Detalle","Ciclo de mejora","Complejidad","Prioridad",
    "Estado","Duración",
    "Fecha Registro","Hora Registro",
    "Fecha inicio","Hora de inicio",
    "Fecha Vencimiento","Hora Vencimiento",
    "Fecha Terminado","Hora Terminado",
    "¿Generó alerta?","N° alerta","Fecha de detección","Hora de detección",
    "¿Se corrigió?","Fecha de corrección","Hora de corrección",
    "Cumplimiento","Evaluación","Calificación",
    "Fecha Pausado","Hora Pausado",
    "Fecha Cancelado","Hora Cancelado",
    "Fecha Eliminado","Hora Eliminado",
    "Archivo"  # compat histórico
]

# ====== TZ helpers ======
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None

def to_naive_local_series(s: pd.Series) -> pd.Series:
    ser = pd.to_datetime(s, errors="coerce", utc=False)
    try:
        raw = pd.Series(s, copy=False)
        mask_ms = raw.astype(str).str.fullmatch(r"\d{12,13}")
        if mask_ms.any():
            ser.loc[mask_ms] = pd.to_datetime(raw.loc[mask_ms].astype("int64"), unit="ms", utc=True)
    except Exception:
        pass
    try:
        if getattr(ser.dt, "tz", None) is not None:
            ser = (ser.dt.tz_convert(_TZ) if _TZ else ser).dt.tz_localize(None)
    except Exception:
        try:
            ser = ser.dt.tz_localize(None)
        except Exception:
            pass
    return ser

def _fmt_hhmm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        s = str(v).strip()
        if not s or s.lower() in {"nan","nat","none","null"}:
            return ""
        m = re.match(r"^(\d{1,2}):(\d{2})", s)
        if m:
            return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        d = pd.to_datetime(s, errors="coerce", utc=False)
        if pd.isna(d):
            return ""
        return f"{int(d.hour):02d}:{int(d.minute):02d}"
    except Exception:
        return ""

# --- Guardado local (fallback seguro) ---
try:
    from shared import save_local as _disk_save_local
except Exception:
    def _disk_save_local(df: pd.DataFrame):
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data","tareas.csv"), index=False, encoding="utf-8-sig")

def _save_local(df: pd.DataFrame):
    _disk_save_local(df.copy())
    st.session_state["_df_main_local_backup"] = df.copy()

# --- Carga local ---
def _load_local_if_exists() -> pd.DataFrame | None:
    try:
        p = os.path.join("data", "tareas.csv")
        if os.path.exists(p):
            df = pd.read_csv(p, dtype=str, keep_default_na=False).fillna("")
            return df
    except Exception:
        pass
    return None

# --- Columna canónica de link ---
_LINK_CANON = "Link de archivo"

def _canonicalize_link_column(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    cols = list(df.columns)
    canon = None
    for c in cols:
        if c.strip().lower() == _LINK_CANON.strip().lower():
            canon = c; break
    if canon is None:
        pat = re.compile(r"link.*archivo|url.*archivo", re.I)
        variants = [c for c in cols if pat.search(str(c))]
        if variants:
            canon = variants[0]
    if canon is None:
        df[_LINK_CANON] = ""
        return df
    if canon != _LINK_CANON:
        df.rename(columns={canon: _LINK_CANON}, inplace=True)
    df[_LINK_CANON] = df[_LINK_CANON].astype(str)
    return df

_URL_RX = re.compile(r"https?://", re.I)

def _maybe_copy_archivo_to_link(df: pd.DataFrame) -> pd.DataFrame:
    if "Archivo" not in df.columns:
        return df
    df = _canonicalize_link_column(df)
    link = df[_LINK_CANON].astype(str)
    arch = df["Archivo"].astype(str)
    arch = arch.map(lambda x: re.sub(r"<[^>]+>", "", x or ""))
    mask = link.str.strip().eq("") & arch.str.contains(_URL_RX)
    if mask.any():
        df.loc[mask, _LINK_CANON] = arch.loc[mask].astype(str)
    return df

# --- Google Sheets (opcional) ---
def _gsheets_client():
    if "gcp_service_account" not in st.secrets:
        raise KeyError("Falta 'gcp_service_account' en secrets.")
    url = (st.secrets.get("gsheets_doc_url")
           or (st.secrets.get("gsheets",{}) or {}).get("spreadsheet_url")
           or (st.secrets.get("sheets",{}) or {}).get("sheet_url"))
    if not url:
        raise KeyError("No se encontró URL de Sheets.")
    ws_name = (st.secrets.get("gsheets",{}) or {}).get("worksheet","TareasRecientes")
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    ss = gc.open_by_url(url)
    return ss, ws_name

def pull_user_slice_from_sheet(replace_df_main: bool = True):
    ss, ws_name = _gsheets_client()
    try:
        ws = ss.worksheet(ws_name)
    except Exception:
        return
    values = ws.get_all_values()
    if not values:
        return
    headers, rows = values[0], values[1:]
    df = pd.DataFrame(rows, columns=headers)

    for c in df.columns:
        if c.lower().startswith("fecha"):
            df[c] = to_naive_local_series(df[c])

    # limpia HTML si hubiera en columnas de archivo
    def _strip_html(x): return re.sub(r"<[^>]+>", "", str(x) if x is not None else "")
    for cc in [c for c in df.columns if "archivo" in c.lower()]:
        df[cc] = df[cc].map(_strip_html)

    df = _canonicalize_link_column(df)

    # N° alerta único
    alerta_pat = re.compile(r"^\s*n[°º]?\s*(de\s*)?alerta\s*$", re.I)
    alerta_cols = [c for c in df.columns if alerta_pat.match(str(c))]
    if alerta_cols:
        keep = alerta_cols[0]
        if keep != "N° alerta":
            df.rename(columns={keep: "N° alerta"}, inplace=True)
        for c in alerta_cols[1:]:
            df.drop(columns=c, inplace=True, errors="ignore")

    # Merge por Id
    if "Id" in df.columns and isinstance(st.session_state.get("df_main"), pd.DataFrame) and "Id" in st.session_state["df_main"].columns:
        base = st.session_state["df_main"].copy()
        base["Id"] = base["Id"].astype(str); df["Id"] = df["Id"].astype(str)
        base = _canonicalize_link_column(base)
        all_cols = list(dict.fromkeys(list(base.columns) + list(df.columns)))
        base = base.reindex(columns=all_cols); df = df.reindex(columns=all_cols)
        base_idx = base.set_index("Id"); upd_idx = df.set_index("Id")
        base_idx.update(upd_idx)
        merged = base_idx.combine_first(upd_idx).reset_index()
        st.session_state["df_main"] = merged
    else:
        if replace_df_main:
            st.session_state["df_main"] = df
    return df

def push_user_slice_to_sheet():
    ss, ws_name = _gsheets_client()
    try:
        ws = ss.worksheet(ws_name)
    except Exception:
        rows = str(max(1000, len(st.session_state["df_main"]) + 10))
        cols = str(max(26, len(st.session_state["df_main"].columns) + 5))
        ws = ss.add_worksheet(title=ws_name, rows=rows, cols=cols)
    df_out = st.session_state["df_main"].copy()
    df_out = _canonicalize_link_column(df_out)
    for c in df_out.columns:
        low = str(c).lower()
        if low.startswith("fecha"):
            ser = to_naive_local_series(df_out[c])
            df_out[c] = ser.dt.strftime("%Y-%m-%d").fillna("")
        elif low.startswith("hora"):
            df_out[c] = df_out[c].apply(_fmt_hhmm).astype(str)
    df_out = df_out.fillna("").astype(str)
    ws.clear()
    ws.update("A1", [list(df_out.columns)] + df_out.values.tolist())

# ===== Exportación =====
def export_excel(df: pd.DataFrame, sheet_name: str = TAB_NAME) -> bytes:
    try:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
            df.to_excel(w, index=False, sheet_name=sheet_name)
        return buf.getvalue()
    except Exception:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=sheet_name)
        return buf.getvalue()

# ===== Normalizadores de visual =====
def _yesno(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "No"
    s = str(v).strip().lower()
    return "Sí" if s in {"1","si","sí","true","t","y","s","x"} else "No"

# --- Suma de días hábiles (lun–vie) ---
def _add_business_days(start_dates: pd.Series, days: pd.Series) -> pd.Series:
    sd = pd.to_datetime(start_dates, errors="coerce").dt.date
    n  = pd.to_numeric(days, errors="coerce").fillna(0).astype(int)
    ok = (~pd.isna(sd)) & (n > 0)
    out = pd.Series(pd.NaT, index=start_dates.index, dtype="datetime64[ns]"])
    if ok.any():
        a = np.array(sd[ok], dtype="datetime64[D]")
        b = n[ok].to_numpy()
        res = np.busday_offset(a, b, weekmask="Mon Tue Wed Thu Fri")
        out.loc[ok] = pd.to_datetime(res)
    return out

# =======================================================
#                       RENDER
# =======================================================
def render(user: dict | None = None):
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ====== CSS (píldora, aviso punteado y card SOLO para filtros) ======
    st.markdown("""
    <style>/* ... CSS idéntico ... */</style>
    """, unsafe_allow_html=True)

    # ====== DATA BASE ======
    if "df_main" not in st.session_state or not isinstance(st.session_state["df_main"], pd.DataFrame):
        df_local = _load_local_if_exists()
        if isinstance(df_local, pd.DataFrame) and not df_local.empty:
            st.session_state["df_main"] = df_local
        else:
            st.session_state["df_main"] = pd.DataFrame(columns=DEFAULT_COLS)

    # Canoniza link y copia desde 'Archivo' si es URL (para persistir)
    base0 = st.session_state["df_main"].copy()
    base0 = _canonicalize_link_column(base0)
    base1 = _maybe_copy_archivo_to_link(base0.copy())
    if not base0.equals(base1):
        st.session_state["df_main"] = base1.copy()
        try:
            _save_local(st.session_state["df_main"].copy())
        except Exception:
            pass

    # ==== DEDUPE PERSISTENTE DE 'Duración' EN DF_MAIN ====
    # (1) Normaliza nombres, (2) detecta columnas tipo "Duración" (incluye typos),
    # (3) consolida valores en "Duración", (4) elimina las demás y persiste.
    import unicodedata, re as _re
    def _normcol_persist(x: str) -> str:
        s = unicodedata.normalize('NFD', str(x))
        s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
        s = _re.sub(r'\s+', ' ', s).strip().lower()
        return s

    def _is_duration_like(name: str) -> bool:
        n = _normcol_persist(name)
        # variantes comunes: duracion, duraicon, duracon, duracíon, etc.
        if n in {"duracion", "duraicon", "duracon"}:
            return True
        # tolera errores de una letra: dura?on con i opcional
        if _re.fullmatch(r"dura(c|ci|cion|con|c?i?on)", n):
            return True
        # patrón más explícito
        if _re.fullmatch(r"durac(i|í)?on", n):
            return True
        return False

    base_fix = st.session_state["df_main"].copy()
    dur_cols = [c for c in base_fix.columns if _is_duration_like(c)]
    if len(dur_cols) > 1:
        keep = "Duración" if "Duración" in dur_cols else dur_cols[0]
        # coalesce: si keep está vacío y otra columna tiene valores, llénala
        for c in dur_cols:
            if c == keep:
                continue
            # mueve valores no vacíos
            mask_take = base_fix[keep].astype(str).str.strip().eq("") & base_fix[c].astype(str).str.strip().ne("")
            if mask_take.any():
                base_fix.loc[mask_take, keep] = base_fix.loc[mask_take, c]
        base_fix.drop(columns=[c for c in dur_cols if c != keep], inplace=True, errors="ignore")
        st.session_state["df_main"] = base_fix
        try:
            _save_local(base_fix)
        except Exception:
            pass
    # ==== FIN DEDUPE PERSISTENTE ====

    # ===== Píldora arriba =====
    st.markdown('<div class="hist-title-pill">📝 Tareas recientes</div>', unsafe_allow_html=True)

    # ===== Indicaciones =====
    st.markdown(
        '<div class="hist-hint">Aquí puedes editar <b>Tarea</b> y <b>Detalle de tarea</b>. '
        'Opcional: descargar en Excel. <b>Obligatorio:</b> Grabar y después Subir a Sheets.</div>',
        unsafe_allow_html=True
    )

    # ===== Card: filtros =====
    st.markdown('<div class="hist-card">', unsafe_allow_html=True)
    with st.container():
        c1, c2, c3, c4, c5, c6 = st.columns([1.05, 1.10, 1.70, 1.05, 1.05, 0.90], gap="medium")
        with c1:
            area_sel = st.selectbox(
                "Área",
                options=["Todas"] + st.session_state.get(
                    "AREAS_OPC",
                    ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
                ),
               
