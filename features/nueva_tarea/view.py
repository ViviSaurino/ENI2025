from __future__ import annotations  

import os
import re
import base64
from io import BytesIO
from datetime import date, datetime
import time
import uuid

import numpy as np
import pandas as pd
import streamlit as st
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

# 👇 ACL: para filtrar vista (Vivi/Enrique ven todo, resto solo lo suyo)
try:
    from shared import apply_scope  # type: ignore
except Exception:
    def apply_scope(df, user=None):  # fallback no-op
        return df

# 👇 Upsert centralizado (utils/gsheets) — usado en distintas secciones
try:
    from utils.gsheets import upsert_rows_by_id, open_sheet_by_url  # type: ignore
except Exception:
    upsert_rows_by_id = None
    open_sheet_by_url = None

# 👇 Solo-lectura por usuario (si viene de ACL). Acepta nombres separados por coma.
def _split_list(s: str) -> set[str]:
    return {x.strip() for x in str(s or "").split(",") if x and x.strip()}


def _get_readonly_cols_from_acl(user_row: dict) -> set[str]:
    try:
        return _split_list((user_row or {}).get("read_only_cols", ""))
    except Exception:
        return set()


# 🔧 Identificar super editores (Vivi/Enrique)
def _display_name() -> str:
    u = st.session_state.get("acl_user", {}) or {}
    return (
        u.get("display")
        or st.session_state.get("user_display_name", "")
        or u.get("name", "")
        or (st.session_state.get("user") or {}).get("name", "")
        or ""
    )


def _is_super_editor() -> bool:
    u = st.session_state.get("acl_user", {}) or {}
    flag = str(u.get("can_edit_all", "")).strip().lower()
    if flag in {"1", "true", "yes", "si", "sí"}:
        return True
    dn = _display_name().strip().lower()
    return dn.startswith("vivi") or dn.startswith("enrique")


# ================== Config base ==================
TAB_NAME = "Tareas"
DEFAULT_COLS = [
    "Id", "Área", "Fase", "Responsable",
    "Tarea", "Tipo de tarea", "Detalle", "Ciclo de mejora", "Complejidad", "Prioridad",
    "Estado", "Duración",
    "Fecha Registro", "Hora Registro",
    "Fecha inicio", "Hora de inicio",
    "Fecha Terminado", "Hora Terminado",
    "Fecha Vencimiento", "Hora Vencimiento",
    "¿Generó alerta?", "N° alerta", "Fecha de detección", "Hora de detección",
    "¿Se corrigió?", "Fecha de corrección", "Hora de corrección",
    "Cumplimiento", "Evaluación", "Calificación",
    "Fecha Pausado", "Hora Pausado",
    "Fecha Cancelado", "Hora Cancelado",
    "Fecha Eliminado", "Hora Eliminado",
    "Archivo",
]

# ⬇️ NUEVO: intervalo de auto-pull configurable (segundos)
PULL_INTERVAL_SECS = int(st.secrets.get("hist_pull_secs", 30))

# ====== TZ helpers ======
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(st.secrets.get("local_tz", "America/Lima"))
except Exception:
    _TZ = None


def to_naive_local_series(s: pd.Series) -> pd.Series:
    # *** FIX: parser más tolerante (epoch ms/seg, serial Excel, dayfirst)
    ser = pd.to_datetime(s, errors="coerce", utc=False)
    try:
        raw = pd.Series(s, copy=False)

        # Epoch en milisegundos (12–13 dígitos)
        mask_ms = raw.astype(str).str.fullmatch(r"\d{12,13}")
        if mask_ms.any():
            ser.loc[mask_ms] = pd.to_datetime(raw.loc[mask_ms].astype("int64"), unit="ms", utc=True)

        # Epoch en segundos (10 dígitos)
        mask_s = raw.astype(str).str.fullmatch(r"\d{10}")
        if mask_s.any():
            ser.loc[mask_s] = pd.to_datetime(raw.loc[mask_s].astype("int64"), unit="s", utc=True)

        # Serial Excel (días desde 1899-12-30) — rango razonable 1982–2064 aprox.
        ser_isna = ser.isna()
        raw_num = pd.to_numeric(raw, errors="coerce")
        mask_excel = ser_isna & raw_num.notna() & raw_num.between(30000, 60000)
        if mask_excel.any():
            origin = pd.Timestamp("1899-12-30")
            ser.loc[mask_excel] = origin + pd.to_timedelta(raw_num.loc[mask_excel].astype(float), unit="D")

        # Reintento con dayfirst si aún queda NaT y hay separadores
        ser_isna2 = ser.isna()
        raw_str = raw.astype(str)
        mask_slash = ser_isna2 & raw_str.str.contains(r"[/-]", regex=True)
        if mask_slash.any():
            ser.loc[mask_slash] = pd.to_datetime(raw_str.loc[mask_slash], errors="coerce", dayfirst=True, utc=False)
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
        s = str(v).trim() if hasattr(v, "trim") else str(v).strip()
        if not s or s.lower() in {"nan", "nat", "none", "null"}:
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
    from shared import save_local as _disk_save_local  # type: ignore
except Exception:
    def _disk_save_local(df: pd.DataFrame):
        os.makedirs("data", exist_ok=True)
        df.to_csv(os.path.join("data", "tareas.csv"), index=False, encoding="utf-8-sig")


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


# 🔧 FIX: siempre garantizar la columna canónica incluso con DF vacío
def _canonicalize_link_column(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return df
    if df.empty:
        if _LINK_CANON not in df.columns:
            df[_LINK_CANON] = ""
        return df
    cols = list(df.columns)
    canon = None
    for c in cols:
        if c.strip().lower() == _LINK_CANON.strip().lower():
            canon = c
            break
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


# 🔧 FIX: robusto si DF está vacío o falta la columna
def _maybe_copy_archivo_to_link(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return df
    df = _canonicalize_link_column(df)
    if _LINK_CANON not in df.columns:
        df[_LINK_CANON] = ""
    if "Archivo" not in df.columns:
        return df
    link = df[_LINK_CANON].astype(str)
    arch = df["Archivo"].astype(str)
    arch = arch.map(lambda x: re.sub(r"<[^>]+>", "", x or ""))
    mask = link.str.strip().eq("") & arch.str.contains(_URL_RX)
    if mask.any():
        df.loc[mask, _LINK_CANON] = arch.loc[mask].astype(str)
    return df


# ⬇️⬇️⬇️ NUEVO: helpers para asegurar Id en filas sin Id (p. ej., importadas de correo)
def _gen_ids(k: int, existing: set[str] | None = None) -> list[str]:
    pool = set(existing or set())
    out: list[str] = []
    while len(out) < k:
        cand = "T-" + uuid.uuid4().hex[:10].upper()
        if cand not in pool:
            pool.add(cand)
            out.append(cand)
    return out


def _ensure_row_ids(df: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    """
    Garantiza que todas las filas tengan 'Id'.
    Devuelve (df_con_id, set_de_ids_generados).
    """
    if df is None or df.empty:
        return df, set()
    df2 = df.copy()
    if "Id" not in df2.columns:
        df2["Id"] = ""
    df2["Id"] = df2["Id"].astype(str)

    def _is_empty_id(s: str) -> bool:
        s = (s or "").strip().lower()
        return s in {"", "nan", "none", "null"}

    mask = df2["Id"].map(lambda x: _is_empty_id(str(x)))
    n = int(mask.sum())
    new_ids: set[str] = set()
    if n > 0:
        existing = set(df2["Id"].astype(str).tolist())
        gen = _gen_ids(n, existing)
        df2.loc[mask, "Id"] = gen
        new_ids = set(gen)
    return df2, new_ids


# --- Google Sheets (opcional) ---
# ✅ Ajuste solicitado: usar SOLO el helper de shared.py (sin definir _gsheets_client local)
try:
    from shared import gsheets_client as _gsheets_client  # type: ignore
except Exception:
    _gsheets_client = None  # depender del helper central; no definir cliente local


def _gsheets_eval_name(default: str = "Evaluación") -> str:
    return (
        (st.secrets.get("gsheets", {}) or {}).get("worksheet_eval")
        or st.secrets.get("ws_eval_name")
        or default
    )


def pull_user_slice_from_sheet(replace_df_main: bool = True):
    if _gsheets_client is None:
        return
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

    def _strip_html(x):
        return re.sub(r"<[^>]+>", "", str(x) if x is not None else "")
    for cc in [c for c in df.columns if "archivo" in c.lower()]:
        df[cc] = df[cc].map(_strip_html)

    df = _canonicalize_link_column(df)

    alerta_pat = re.compile(r"^\s*n[°º]?\s*(de\s*)?alerta\s*$", re.I)
    alerta_cols = [c for c in df.columns if alerta_pat.match(str(c))]
    if alerta_cols:
        keep = alerta_cols[0]
        if keep != "N° alerta":
            df.rename(columns={keep: "N° alerta"}, inplace=True)
        for c in alerta_cols[1:]:
            df.drop(columns=c, inplace=True, errors="ignore")

    if "Id" in df.columns and isinstance(st.session_state.get("df_main"), pd.DataFrame) and "Id" in st.session_state["df_main"].columns:
        base = st.session_state["df_main"].copy()
        base["Id"] = base["Id"].astype(str)
        df["Id"] = df["Id"].astype(str)
        base = _canonicalize_link_column(base)
        all_cols = list(dict.fromkeys(list(base.columns) + list(df.columns)))
        base = base.reindex(columns=all_cols)
        df = df.reindex(columns=all_cols)
        base_idx = base.set_index("Id")
        upd_idx = df.set_index("Id")
        base_idx.update(upd_idx)
        merged = base_idx.combine_first(upd_idx).reset_index()
        st.session_state["df_main"] = merged
    else:
        if replace_df_main:
            st.session_state["df_main"] = df
    # *** NUEVO: baseline para reconstruir difs si se pierde el snapshot
    try:
        st.session_state["_hist_baseline"] = st.session_state["df_main"].copy()
    except Exception:
        pass
    return df


# ======== Upsert helpers ========
def _a1_col(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _format_outgoing_row(row: pd.Series, headers: list[str]) -> list[str]:
    out = []
    for c in headers:
        val = row.get(c, "")
        low = str(c).lower()
        if low.startswith("fecha"):
            ser = to_naive_local_series(pd.Series([val]))
            v = ser.iloc[0]
            out.append("" if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d"))
        elif low.startswith("hora"):
            out.append(_fmt_hhmm(val))
        else:
            out.append("" if val is None or (isinstance(val, float) and pd.isna(val)) else str(val))
    return out


def _format_single_cell(val, colname: str) -> str:
    low = str(colname).lower()
    if low.startswith("fecha"):
        ser = to_naive_local_series(pd.Series([val]))
        v = ser.iloc[0]
        return "" if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d")
    if low.startswith("hora"):
        return _fmt_hhmm(val)
    return "" if val is None or (isinstance(val, float) and pd.isna(val)) else str(val)


def _sheet_upsert_by_id_partial(
    df_rows: pd.DataFrame,
    cell_diff_map: dict[str, set[str]] | None = None,
    new_ids: set[str] | None = None,
) -> dict:
    """
    Actualiza solo las celdas modificadas por Id y columna; inserta filas completas si es Id nuevo.
    """
    if df_rows is None or df_rows.empty or "Id" not in df_rows.columns:
        return {"ok": False, "msg": "No hay filas con Id para actualizar."}
    if _gsheets_client is None:
        return {"ok": False, "msg": "No hay cliente de Sheets configurado."}

    ss, ws_name = _gsheets_client()
    try:
        ws = ss.worksheet(ws_name)
    except Exception:
        rows = str(max(1000, len(df_rows) + 10))
        cols = str(max(26, len(df_rows.columns) + 5))
        ws = ss.add_worksheet(title=ws_name, rows=rows, cols=cols)

    headers = ws.row_values(1)
    if not headers:
        headers = list(df_rows.columns)

    # Asegurar cabeceras completas
    new_cols = [c for c in df_rows.columns if c not in headers]
    if new_cols:
        headers = headers + new_cols
        ws.update("A1", [headers])

    try:
        id_col_idx = (headers.index("Id") + 1)
    except ValueError:
        headers = ["Id"] + [c for c in headers if c != "Id"]
        ws.update("A1", [headers])
        id_col_idx = 1

    existing_ids_col = ws.col_values(id_col_idx)
    id_to_row = {}
    for i, v in enumerate(existing_ids_col[1:], start=2):
        if v:
            id_to_row[str(v).strip()] = i

    col_to_idx = {c: i + 1 for i, c in enumerate(headers)}
    df_rows = df_rows.copy()
    df_rows["Id"] = df_rows["Id"].astype(str)

    updates_count = 0
    appends = []

    new_ids = set(new_ids or set())
    cell_diff_map = cell_diff_map or {}

    for _, row in df_rows.iterrows():
        rid = str(row.get("Id", "")).strip()
        if not rid:
            continue

        # Si es nuevo Id o no existe en hoja → append fila completa
        if (rid not in id_to_row) or (rid in new_ids):
            appends.append(_format_outgoing_row(row, headers))
            continue

        # Para existentes, actualizar solo columnas cambiadas
        diff_cols = set(cell_diff_map.get(rid, set()))
        if not diff_cols:
            continue

        r_idx = id_to_row[rid]
        for col in diff_cols:
            if col not in col_to_idx:
                headers.append(col)
                ws.update("A1", [headers])
                col_to_idx[col] = len(headers)
            c_idx = col_to_idx[col]
            a1 = f"{_a1_col(c_idx)}{r_idx}"
            value = _format_single_cell(row.get(col, ""), col)
            ws.update(a1, [[value]], value_input_option="USER_ENTERED")
            updates_count += 1

    if appends:
        ws.append_rows(appends, value_input_option="USER_ENTERED")

    msg = []
    if updates_count:
        msg.append(f"{updates_count} celda(s) actualizada(s)")
    if appends:
        msg.append(f"{len(appends)} fila(s) insertada(s)")
    return {"ok": True, "msg": "Upsert parcial: " + (", ".join(msg) if msg else "sin cambios.")}


# ⬇️ NUEVO: upsert a hoja de Evaluación SOLO columna "Cumplimiento" por Id
def _sheet_upsert_eval_cumpl(df_rows: pd.DataFrame) -> dict:
    if df_rows is None or df_rows.empty or "Id" not in df_rows.columns or "Cumplimiento" not in df_rows.columns:
        return {"ok": False, "msg": "No hay filas con Id y Cumplimiento para Evaluación."}
    if _gsheets_client is None:
        return {"ok": False, "msg": "No hay cliente de Sheets configurado."}

    ss, _ = _gsheets_client()
    ws_name = _gsheets_eval_name("Evaluación")
    import gspread
    try:
        ws = ss.worksheet(ws_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=ws_name, rows="2000", cols="10")
        ws.update("A1", [["Id", "Cumplimiento"]])

    headers = ws.row_values(1)
    if not headers:
        headers = ["Id", "Cumplimiento"]
        ws.update("A1", [headers])

    # buscar columna de cumplimiento (tolerante)
    def _norm(s):
        return re.sub(r'[^a-z]', '', (s or '').lower())
    cumpl_col_name = None
    for h in headers:
        if _norm(h).startswith("cumplimiento"):
            cumpl_col_name = h
            break
    if not cumpl_col_name:
        cumpl_col_name = "Cumplimiento"
        if cumpl_col_name not in headers:
            headers.append(cumpl_col_name)
            ws.update("A1", [headers])

    id_col_idx = (headers.index("Id") + 1)
    cumpl_col_idx = (headers.index(cumpl_col_name) + 1)

    existing_ids = ws.col_values(id_col_idx)
    id_to_row = {}
    for i, v in enumerate(existing_ids[1:], start=2):
        if v:
            id_to_row[str(v).strip()] = i

    to_append = []
    updates = 0
    for _, r in df_rows.iterrows():
        rid = str(r.get("Id", "")).strip()
        cv = str(r.get("Cumplimiento", "")).strip()
        if not rid:
            continue
        if rid in id_to_row:
            a1 = f"{_a1_col(cumpl_col_idx)}{id_to_row[rid]}"
            ws.update(a1, [[cv]], value_input_option="USER_ENTERED")
            updates += 1
        else:
            row_vals = [""] * len(headers)
            row_vals[id_col_idx - 1] = rid
            row_vals[cumpl_col_idx - 1] = cv
            to_append.append(row_vals)
    if to_append:
        ws.append_rows(to_append, value_input_option="USER_ENTERED")
    msg = []
    if updates:
        msg.append(f"{updates} actualización(es)")
    if to_append:
        msg.append(f"{len(to_append)} inserción(es)")
    return {"ok": True, "msg": "Evaluación: " + (", ".join(msg) if msg else "sin cambios.")}


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
    return "Sí" if s in {"1", "si", "sí", "true", "t", "y", "s", "x"} else "No"


# --- Suma de días hábiles (lun–vie) ---
def _add_business_days(start_dates: pd.Series, days: pd.Series) -> pd.Series:
    sd = pd.to_datetime(start_dates, errors="coerce").dt.date
    n = pd.to_numeric(days, errors="coerce").fillna(0).astype(int)
    ok = (~pd.isna(sd)) & (n > 0)
    out = pd.Series(pd.NaT, index=start_dates.index, dtype="datetime64[ns]")
    if ok.any():
        # 🔧 FIX: paréntesis correcto en dtype
        a = np.array(sd[ok], dtype="datetime64[D]")
        b = n[ok].to_numpy()
        res = np.busday_offset(a, b, weekmask="Mon Tue Wed Thu Fri")
        out.loc[ok] = pd.to_datetime(res)
    return out


# *** NUEVO: asegurar cálculo de Fecha límite/Hora límite y Cumplimiento en un df dado
def _ensure_deadline_and_compliance(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        df = df.copy()
        if "Hora Vencimiento" not in df.columns:
            df["Hora Vencimiento"] = ""
        if "Cumplimiento" not in df.columns:
            df["Cumplimiento"] = ""
        return _canonicalize_link_column(df)

    df = df.copy()
    # Fecha límite (solo con Duración + Fecha inicio)
    if ("Duración" in df.columns) and ("Fecha inicio" in df.columns):
        dur_num = pd.to_numeric(df["Duración"], errors="coerce")
        ok = dur_num.where(dur_num >= 1)
        fi = to_naive_local_series(df.get("Fecha inicio", pd.Series([], dtype=object)))
        fv_calc = _add_business_days(fi, ok.fillna(0))
        if "Fecha Vencimiento" not in df.columns:
            df["Fecha Vencimiento"] = pd.NaT
        mask_set = ~fv_calc.isna()
        df.loc[mask_set, "Fecha Vencimiento"] = fv_calc.loc[mask_set]

    # Hora límite (crear si falta)
    if "Hora Vencimiento" not in df.columns:
        df["Hora Vencimiento"] = ""
    hv = df["Hora Vencimiento"].map(_fmt_hhmm)
    mask_empty = hv.map(lambda x: (str(x).strip() if x is not None else "") == "")
    df["Hora Vencimiento"] = hv.mask(mask_empty, "17:00")

    # Cumplimiento
    fv = to_naive_local_series(df["Fecha Vencimiento"]) if "Fecha Vencimiento" in df.columns else pd.Series(
        pd.NaT, index=df.index, dtype="datetime64[ns]"
    )
    ft = to_naive_local_series(df["Fecha Terminado"]) if "Fecha Terminado" in df.columns else pd.Series(
        pd.NaT, index=df.index, dtype="datetime64[ns]"
    )
    today_ts = pd.Timestamp(date.today())
    fv_n = fv.dt.normalize()
    ft_n = ft.dt.normalize()
    has_fv = ~fv_n.isna()
    has_ft = ~ft_n.isna()
    delivered_on_time = has_fv & has_ft & (ft_n <= fv_n)
    delivered_late = has_fv & has_ft & (ft_n > fv_n)
    days_left = (fv_n - today_ts).dt.days
    no_delivered = has_fv & (~has_ft) & (days_left < 0)
    risk = has_fv & (~has_ft) & (days_left >= 1) & (days_left <= 2)

    out = pd.Series("", index=df.index, dtype="object")
    out[delivered_on_time] = "✅ Entregado a tiempo"
    out[delivered_late] = "⏰ Entregado fuera de tiempo"
    out[no_delivered] = "❌ No entregado"
    out[risk] = "⚠️ En riesgo de retrasos"
    df["Cumplimiento"] = out
    return _canonicalize_link_column(df)


# *** NUEVO: baseline diff (reconstrucción si no hay snapshot por edición)
def _derive_pending_from_baseline(
    curr: pd.DataFrame,
    base: pd.DataFrame,
    allowed_cols: set[str] | None = None,
):
    pend_ids, cell_diff, new_ids = set(), {}, set()
    if curr is None or curr.empty or "Id" not in curr.columns:
        return pend_ids, cell_diff, new_ids
    if base is None or base.empty or "Id" not in base.columns:
        # todo es nuevo
        new_ids = set(curr["Id"].astype(str).tolist())
        pend_ids = set(new_ids)
        return pend_ids, cell_diff, new_ids

    c = _canonicalize_link_column(curr.copy())
    b = _canonicalize_link_column(base.copy())
    c["Id"] = c["Id"].astype(str)
    b["Id"] = b["Id"].astype(str)
    c_idx = c.set_index("Id", drop=False)
    b_idx = b.set_index("Id", drop=False)

    cols = list(dict.fromkeys([x for x in c.columns if x in b.columns]))
    if allowed_cols:
        cols = [x for x in cols if x in allowed_cols or x == "Id"]

    # garantizar cálculo de derivados antes de comparar
    c_idx = _ensure_deadline_and_compliance(c_idx)
    b_idx = _ensure_deadline_and_compliance(b_idx)

    # nuevos
    for iid in c_idx.index:
        if iid not in b_idx.index:
            new_ids.add(iid)
            pend_ids.add(iid)

    common = c_idx.index.intersection(b_idx.index)
    if len(common):
        a = b_idx.loc[common, cols].fillna("").astype(str)
        d = c_idx.loc[common, cols].fillna("").astype(str)
        neq = a.ne(d)
        changed_any = neq.any(axis=1)
        ids_changed = changed_any[changed_any].index
        for rid in ids_changed:
            pend_ids.add(rid)
            diff_mask = neq.loc[rid].to_numpy()
            cols_changed = set(neq.columns[diff_mask].tolist())
            if allowed_cols:
                cols_changed = {x for x in cols_changed if x in allowed_cols}
            if cols_changed:
                cell_diff[str(rid)] = cols_changed
    return pend_ids, cell_diff, new_ids


# --- Bootstrap fuerte de df_main (garantiza que "pegue" en todas las pestañas) ---
def _bootstrap_df_main_hist():
    need = (
        "df_main" not in st.session_state
        or not isinstance(st.session_state["df_main"], pd.DataFrame)
        or st.session_state["df_main"].empty
    )
    if not need:
        # baseline si aún no existe
        st.session_state.setdefault("_hist_baseline", st.session_state["df_main"].copy())
        return

    df_local = _load_local_if_exists()
    if isinstance(df_local, pd.DataFrame) and not df_local.empty:
        st.session_state["df_main"] = df_local.copy()
        st.session_state["_hist_baseline"] = df_local.copy()
        return

    try:
        pull_user_slice_from_sheet(replace_df_main=True)
    except Exception:
        st.session_state["df_main"] = pd.DataFrame(columns=DEFAULT_COLS)
        st.session_state["_hist_baseline"] = st.session_state["df_main"].copy()


# =========================================================
#   VISTA: Historial / Tareas recientes
# =========================================================
def render_historial(user: dict | None = None):

    # ====== CSS (AJUSTES pedidos) ======
    st.markdown(
        """
    <style>
      :root{
        --pill-salmon:#F28B85;
        --card-border:#E5E7EB;
        --card-bg:#FFFFFF;

        /* Indicaciones (coral muy claro + trazo fino) */
        --hint-bg:#FFE7E3;
        --hint-border:#F28B85;
        --hint-color:#7F1D1D;

        /* Colores de bloques de fecha/hora (igual Editar estado) */
        --hdr-reg:#EDE9FE;   /* Registro: lila */
        --hdr-ini:#DCFCE7;   /* Inicio: verde */
        --hdr-ter:#E0F2FE;   /* Terminado: celeste */

        /* Separadores horizontales suaves (ajuste lila-azulado) */
        --row-sep:#C4B5FD;
      }

      .hist-card{
        border:0!important;
        background:transparent!important;
        border-radius:0!important;
        padding:0!important;
        margin:0 0 8px 0!important;
      }

      .hist-title-pill{
        display:inline-flex;
        align-items:center;
        gap:8px;
        padding:10px 16px;
        border-radius:10px;
        background: var(--pill-salmon);
        color:#fff;
        font-weight:600;
        font-size:1.05rem;
        line-height:1.1;
        box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06);
        margin-bottom:10px;
      }

      /* Indicaciones coral */
      .hist-hint{
        background:var(--hint-bg);
        border:1px dashed var(--hint-border);
        border-radius:10px;
        padding:10px 12px;
        color:var(--hint-color);
        margin: 2px 0 12px 0;
        font-size:0.95rem;
      }

      /* Ocultar input fantasma directamente debajo de la hint */
      .hist-hint + div[data-testid="stTextInput"]{ display:none!important; }
      .hist-hint + div:has(div[data-testid="stTextInput"]){ display:none!important; }
      .hist-hint + div:has(input[type="text"]){ display:none!important; }

      /* Marco con dos líneas (arriba y abajo) alrededor de los filtros */
      .hist-filters{
        border:0!important;
        background:transparent!important;
        border-radius:0!important;
        padding:0!important;
        margin:8px 0 10px 0 !important;
        box-shadow:
          inset 0 4px 0 var(--row-sep),
          inset 0 -4px 0 var(--row-sep);
      }

      /* Botón Buscar estilo lila */
      .hist-search .stButton>button{
        background:#6366F1;
        color:#FFFFFF;
        border:none;
        border-radius:999px;
        font-weight:600;
        box-shadow:0 2px 4px rgba(99,102,241,0.25);
      }
      .hist-search .stButton>button:hover{
        background:#4F46E5;
      }

      /* Bloque imagen + texto "Ahora revisa tus tareas" */
      .hist-hero{
        display:flex;
        align-items:center;
        gap:20px;
        margin:12px 0 4px 0;
      }
      .hist-hero-img img{
        max-width:220px;
        height:auto;
        display:block;
      }
      .hist-hero-text{
        font-size:1.1rem;
        font-weight:600;
        color:#4B5563;
        margin-top:30px;
      }

      /* Línea gris clarita debajo del bloque */
      .hist-hero-line{
        height:1px;
        width:100%;
        background:#E5E7EB;
        margin:0 0 26px 0;  /* 👉 prueba 24–28px hasta que te guste */
      }

      /* AG Grid base con líneas horizontales suaves */
      .ag-theme-balham .ag-cell{
        white-space:nowrap!important;
        overflow:hidden!important;
        text-overflow:ellipsis!important;
        border-top:2px solid var(--row-sep)!important;
        border-bottom:2px solid var(--row-sep)!important;
      }
      .ag-theme-balham .ag-header-cell{
        border-top:2px solid var(--row-sep)!important;
        border-bottom:2px solid var(--row-sep)!important;
      }
      .ag-theme-balham .ag-header-cell-label{
        white-space:nowrap!important;
        line-height:1.1!important;
        overflow:visible!important;
        text-overflow:clip!important;
      }
      .ag-theme-balham .ag-header .ag-icon,
      .ag-theme-balham .ag-header-cell .ag-icon,
      .ag-theme-balham .ag-header-cell-menu-button,
      .ag-theme-balham .ag-floating-filter,
      .ag-theme-balham .ag-header-row.ag-header-row-column-filter{
        display:none!important;
      }

      /* Encabezados coloreados (armonía con Editar estado) */
      .ag-theme-balham .ag-header-cell.hdr-registro{
        background:var(--hdr-reg)!important;
        border-radius:8px;
      }
      .ag-theme-balham .ag-header-cell.hdr-inicio{
        background:var(--hdr-ini)!important;
        border-radius:8px;
      }
      .ag-theme-balham .ag-header-cell.hdr-termino{
        background:var(--hdr-ter)!important;
        border-radius:8px;
      }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # ====== DATA BASE (bootstrap fuerte) ======
    _bootstrap_df_main_hist()
    if "df_main" not in st.session_state or not isinstance(st.session_state["df_main"], pd.DataFrame):
        st.session_state["df_main"] = pd.DataFrame(columns=DEFAULT_COLS)

    base0 = st.session_state["df_main"].copy()
    base0 = _canonicalize_link_column(base0)
    base1 = _maybe_copy_archivo_to_link(base0.copy())
    if not base0.equals(base1):
        st.session_state["df_main"] = base1.copy()
        try:
            _save_local(st.session_state["df_main"].copy())
        except Exception:
            pass

    # === Auto-sync pull (debounce configurable) ===
    try:
        last = float(st.session_state.get("_last_pull_hist", 0) or 0)
        if (time.time() - last) > PULL_INTERVAL_SECS:
            pull_user_slice_from_sheet(replace_df_main=False)
            st.session_state["_last_pull_hist"] = time.time()
    except Exception:
        pass

    # ===== Imagen + texto "Ahora revisa tus tareas" (AL INICIO, sobre pasos) =====
    try:
        _img_b64 = _hist_img_base64()
    except Exception:
        _img_b64 = ""

    if _img_b64:
        st.markdown(
            f"""
            <div class="hist-hero">
              <div class="hist-hero-img">
                <img src="data:image/png;base64,{_img_b64}" alt="Tareas recientes" />
              </div>
              <div class="hist-hero-text">
                Ahora revisa tus tareas
              </div>
            </div>
            <div class="hist-hero-line"></div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="hist-hero">
              <div class="hist-hero-text">
                Ahora revisa tus tareas
              </div>
            </div>
            <div class="hist-hero-line"></div>
            """,
            unsafe_allow_html=True,
        )


    # ===== Pasos (tarjetas tipo Nueva tarea) =====
    st.markdown(
        """
    <div class="nt-steps-row">
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">Opcional: Edita tu tarea</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">✏️</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">Opcional: Editar el detalle</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">📋</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">Obligatorio: Graba</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">💾</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">Obligatorio: Subir a Sheets</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">📤</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">Opcional: Descarga en Excel</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">⬇️</span></div>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # ===== Filtros =====
    st.markdown('<div class="hist-card">', unsafe_allow_html=True)
    df_all = st.session_state["df_main"].copy()

    super_editor = _is_super_editor()
    if super_editor:
        df_scope = df_all.copy()  # Vivi/Enrique ven todo
    else:
        df_scope = apply_scope(df_all.copy(), user=user)
        try:
            me = _display_name().strip()
            if isinstance(df_scope, pd.DataFrame) and "Responsable" in df_scope.columns and me:
                mask = df_scope["Responsable"].astype(str).str.lower().str.contains(me.lower())
                df_scope = df_scope[mask]
        except Exception:
            pass

    # Serie de fechas base (Fecha Registro preferente)
    if "Fecha Registro" in df_scope.columns:
        _fseries = to_naive_local_series(df_scope["Fecha Registro"])
    elif "Fecha inicio" in df_scope.columns:
        _fseries = to_naive_local_series(df_scope["Fecha inicio"])
    else:
        _fseries = to_naive_local_series(df_scope.get("Fecha", pd.Series([], dtype=object)))
    if _fseries.notna().any():
        _min_date = _fseries.min().date()
        _max_date = _fseries.max().date()
    else:
        _min_date = _max_date = date.today()

    # Catálogos para selects
    ESTADO_CHOICES = [
        ("Todos", ""), ("🟤 No iniciado", "no iniciado"), ("▶️ En curso", "en curso"),
        ("✅ Terminada", "terminada"), ("⏸️ Pausada", "pausada"),
        ("🛑 Cancelada", "cancelada"), ("🗑️ Eliminada", "eliminad"),
    ]
    PRIORIDAD_CHOICES = [("Todas", ""), ("🔴 Alta", "alta"), ("🟡 Media", "media"), ("🟢 Baja", "baja")]
    COMPLEJIDAD_CHOICES = [("Todas", ""), ("🔴 Alta", "alta"), ("🟡 Media", "media"), ("🟢 Baja", "baja")]
    CUMPL_CHOICES = [
        ("Todos", ""), ("✅ A tiempo", "a tiempo"), ("⏰ Fuera de tiempo", "fuera de tiempo"),
        ("❌ No entregado", "no entregado"), ("⚠️ En riesgo", "riesgo"),
    ]

    def _sel(label_value_list, label: str, key: str, index0: int = 0):
        labels = [x[0] for x in label_value_list]
        return st.selectbox(label, options=labels, index=index0, key=key)

    def _value_of(label_value_list, selected_label: str) -> str:
        for lab, val in label_value_list:
            if lab == selected_label:
                return val
        return ""

    COLS_5 = [1, 1, 1, 1, 1]
    hist_do_buscar = False  # se actualizará con el botón de abajo

    with st.container():
        # línea superior (misma variable de color; grosor acorde)
        st.markdown(
            '<div style="height:0; border-top:4px solid var(--row-sep); margin:0 0 8px 0;"></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="hist-filters">', unsafe_allow_html=True)

        if super_editor:
            responsables = sorted([
                x
                for x in df_scope.get("Responsable", pd.Series([], dtype=str)).astype(str).unique()
                if x and x != "nan"
            ])
            # Fila 1: 5 filtros
            r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(COLS_5, gap="medium")
            with r1c1:
                resp_multi = st.multiselect(
                    "Responsable",
                    options=responsables,
                    default=[],
                    key="hist_resp",
                    placeholder="Selecciona responsable(s)",
                )
            with r1c2:
                _est_lbl = _sel(ESTADO_CHOICES, "Estado actual", "hist_estado")
            with r1c3:
                _pri_lbl = _sel(PRIORIDAD_CHOICES, "Prioridad", "hist_prio")
            with r1c4:
                _com_lbl = _sel(COMPLEJIDAD_CHOICES, "Complejidad", "hist_comp")
            with r1c5:
                _cum_lbl = _sel(CUMPL_CHOICES, "Cumplimiento", "hist_cumpl")

            # Fila 2: solo fechas
            r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(COLS_5, gap="medium")
            with r2c1:
                f_desde = st.date_input("Desde", value=_min_date, key="hist_desde")
            with r2c2:
                f_hasta = st.date_input("Hasta", value=_max_date, key="hist_hasta")

        else:
            # Fila 1: 5 filtros
            r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(COLS_5, gap="medium")
            with r1c1:
                _est_lbl = _sel(ESTADO_CHOICES, "Estado actual", "hist_estado")
            with r1c2:
                _pri_lbl = _sel(PRIORIDAD_CHOICES, "Prioridad", "hist_prio")
            with r1c3:
                _com_lbl = _sel(COMPLEJIDAD_CHOICES, "Complejidad", "hist_comp")
            with r1c4:
                _cum_lbl = _sel(CUMPL_CHOICES, "Cumplimiento", "hist_cumpl")
            with r1c5:
                f_desde = st.date_input("Desde", value=_min_date, key="hist_desde")

            # Fila 2: Hasta
            r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(COLS_5, gap="medium")
            with r2c1:
                f_hasta = st.date_input("Hasta", value=_max_date, key="hist_hasta")

        st.markdown("</div>", unsafe_allow_html=True)
        # línea inferior (debajo de filtros)
        st.markdown(
            '<div style="height:0; border-bottom:4px solid var(--row-sep); margin:4px 0 10px 0;"></div>',
            unsafe_allow_html=True,
        )

    # ===== Botón Buscar debajo de la línea, esquina derecha =====
    with st.container():
        col_espacio, col_boton = st.columns([5, 0.6], gap="medium")
        with col_espacio:
            st.write("")  # relleno
        with col_boton:
            st.markdown('<div class="hist-search">', unsafe_allow_html=True)
            hist_do_buscar = st.button("🔍 Buscar", use_container_width=True, key="hist_btn_buscar")
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    show_deleted = st.toggle("Mostrar eliminadas (tachadas)", value=True, key="hist_show_deleted")

    # ---- Aplicar filtros ----
    df_view = df_scope.copy()
    df_view = _canonicalize_link_column(df_view)

    if "Fecha Registro" in df_view.columns:
        df_view["Fecha Registro"] = to_naive_local_series(df_view["Fecha Registro"])
    if "Fecha inicio" in df_view.columns:
        df_view["Fecha inicio"] = to_naive_local_series(df_view["Fecha inicio"])

    if hist_do_buscar:
        if super_editor and "resp_multi" in locals() and resp_multi:
            df_view = df_view[df_view["Responsable"].astype(str).isin(resp_multi)]

        _estado_val = _value_of(ESTADO_CHOICES, _est_lbl)
        if _estado_val:
            mask_est = df_view.get("Estado", pd.Series([], dtype=str)).astype(str).str.lower().str.contains(_estado_val)
            df_view = df_view[mask_est]

        _prio_val = _value_of(PRIORIDAD_CHOICES, _pri_lbl)
        if _prio_val:
            mask_pri = (
                df_view.get("Prioridad", pd.Series([], dtype=str)).astype(str).str.lower().str.contains(_prio_val)
            )
            df_view = df_view[mask_pri]

        _comp_val = _value_of(COMPLEJIDAD_CHOICES, _com_lbl)
        if _comp_val:
            mask_com = (
                df_view.get("Complejidad", pd.Series([], dtype=str)).astype(str).str.lower().str.contains(_comp_val)
            )
            df_view = df_view[mask_com]

        _cum_val = _value_of(CUMPL_CHOICES, _cum_lbl)
        if _cum_val:
            mask_cum = (
                df_view.get("Cumplimiento", pd.Series([], dtype=str)).astype(str).str.lower().str.contains(_cum_val)
            )
            df_view = df_view[mask_cum]

        # Incluir filas sin fecha
        if f_desde is not None and "Fecha Registro" in df_view.columns:
            mask = df_view["Fecha Registro"].isna() | (df_view["Fecha Registro"].dt.date >= f_desde)
            df_view = df_view[mask]
        if f_hasta is not None and "Fecha Registro" in df_view.columns:
            mask = df_view["Fecha Registro"].isna() | (df_view["Fecha Registro"].dt.date <= f_hasta)
            df_view = df_view[mask]

    if not show_deleted and "Estado" in df_view.columns:
        df_view = df_view[~df_view["Estado"].astype(str).str.lower().str.contains("eliminad")]

    # ===== Normalizaciones mínimas =====
    for need in ["Estado", "Hora de inicio", "Fecha Terminado", "Hora Terminado"]:
        if need not in df_view.columns:
            df_view[need] = "" if "Hora" in need else pd.NaT

    if "Tipo de tarea" not in df_view.columns and "Tipo" in df_view.columns:
        df_view["Tipo de tarea"] = df_view["Tipo"]

    # ✅ Copiar "Duración" desde variantes
    try:
        dur_candidates = (
            [c for c in df_view.columns if re.match(r"^\s*duraci[oó]n", str(c), flags=re.I)]
            + [c for c in df_view.columns if re.match(r"^\s*d[ií]as?$", str(c), flags=re.I)]
        )
        dur_candidates = list(dict.fromkeys(dur_candidates))
        if dur_candidates:
            if "Duración" not in df_view.columns:
                df_view["Duración"] = ""
            vacias = df_view["Duración"].astype(str).str.strip().isin(["", "nan", "none", "null"])
            for cand in dur_candidates:
                if vacias.any():
                    tmp = pd.to_numeric(df_view[cand], errors="coerce")
                    df_view.loc[vacias, "Duración"] = tmp.loc[vacias]
                    vacias = df_view["Duración"].isna() | (df_view["Duración"].astype(str).str.strip() == "")
                else:
                    break
    except Exception:
        pass

    # ===== GRID =====
    target_cols = [
        "Id", "Área", "Fase", "Responsable",
        "Tarea", "Tipo de tarea", "Detalle", "Ciclo de mejora", "Complejidad", "Prioridad",
        "Estado", "Duración",
        "Fecha Registro", "Hora Registro",
        "Fecha inicio", "Hora de inicio",
        "Fecha Terminado", "Hora Terminado",
        "Fecha Vencimiento", "Hora Vencimiento",
        "¿Generó alerta?", "N° alerta", "Fecha de detección", "Hora de detección",
        "¿Se corrigió?", "Fecha de corrección", "Hora de corrección",
        "Cumplimiento", "Evaluación", "Calificación",
        "Fecha Pausado", "Hora Pausado",
        "Fecha Cancelado", "Hora Cancelado",
        "Fecha Eliminado", "Hora Eliminado",
        _LINK_CANON,
        "Link de descarga",
    ]
    hidden_cols = [
        "Archivo", "__ts__", "__SEL__", "__DEL__", "¿Eliminar?", "Tipo de alerta",
        "Fecha estado modificado", "Hora estado modificado", "Fecha estado actual", "Hora estado actual",
        "Fecha", "Hora", "Vencimiento",
    ]

    for c in target_cols:
        if c not in df_view.columns:
            df_view[c] = ""

    df_grid = df_view.reindex(columns=list(dict.fromkeys(target_cols))).copy()
    df_grid = df_grid.loc[:, ~df_grid.columns.duplicated()].copy()

    # ===== Defaults SOLO visuales =====
    def _as_default_label(series: pd.Series, default_label: str) -> pd.Series:
        s = series.astype(str)
        nullish = s.str.strip().str.lower().isin(["", "none", "null", "nan", "nat"])
        return s.mask(nullish, default_label)

    if "Prioridad" in df_grid.columns:
        df_grid["Prioridad"] = _as_default_label(df_grid["Prioridad"], "Sin asignar")
    if "Evaluación" in df_grid.columns:
        df_grid["Evaluación"] = _as_default_label(df_grid["Evaluación"], "Sin evaluar")
    if "Calificación" in df_grid.columns:
        df_grid["Calificación"] = _as_default_label(df_grid["Calificación"], "Sin calificar")

    import unicodedata

    def _normcol_hist(x: str) -> str:
        s = unicodedata.normalize("NFD", str(x))
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", s).strip().lower()

    _seen = set()
    _keep = []
    for _c in df_grid.columns:
        _k = _normcol_hist(_c)
        if _k not in _seen:
            _seen.add(_k)
            _keep.append(_c)
    df_grid = df_grid[_keep]

    def _norm_match_key(name: str) -> str:
        s = _normcol_hist(name)
        s = re.sub(r"[^a-z0-9]", "", s)
        return s

    def _is_duracion_like(name: str) -> bool:
        n = _norm_match_key(name)
        return n == "duracion" or n == "duraicon" or n.startswith("duracion")

    dur_like_cols = [c for c in df_grid.columns if _is_duracion_like(c)]
    if len(dur_like_cols) > 1:
        keep_col = next((c for c in dur_like_cols if c.strip() == "Duración"), dur_like_cols[0])
        drop_cols = [c for c in dur_like_cols if c != keep_col]
        df_grid.drop(columns=drop_cols, inplace=True, errors="ignore")

    df_grid["Id"] = df_grid["Id"].astype(str).fillna("")
    if "Link de descarga" not in df_grid.columns:
        df_grid["Link de descarga"] = ""

    alerta_pat = re.compile(r"^\s*n[°º]?\s*(de\s*)?alerta\s*$", re.I)
    alerta_cols = [c for c in df_grid.columns if alerta_pat.match(str(c))]
    if alerta_cols:
        first = alerta_cols[0]
        if first != "N° alerta":
            df_grid.rename(columns={first: "N° alerta"}, inplace=True)
        for c in alerta_cols[1:]:
            df_grid.drop(columns=c, inplace=True, errors="ignore")

    for bcol in ["¿Generó alerta?", "¿Se corrigió?"]:
        if bcol in df_grid.columns:
            df_grid[bcol] = df_grid[bcol].map(_yesno)

    # === Duración → entero visual + Fecha límite (hábiles) ===
    if "Duración" in df_grid.columns:
        dur_num = pd.to_numeric(df_grid["Duración"], errors="coerce")
        ok = dur_num.where(dur_num >= 1)
        if "Fecha inicio" in df_grid.columns:
            fi = to_naive_local_series(df_grid.get("Fecha inicio", pd.Series([], dtype=object)))
            fv_calc = _add_business_days(fi, ok.fillna(0))
            mask_set = ~fv_calc.isna()
            if "Fecha Vencimiento" not in df_grid.columns:
                df_grid["Fecha Vencimiento"] = pd.NaT
            df_grid.loc[mask_set, "Fecha Vencimiento"] = fv_calc.loc[mask_set]
        dur_int = ok.round(0).astype("Int64")
        df_grid["Duración"] = dur_int.astype(str).replace({"<NA>": ""})

    if "Hora Vencimiento" not in df_grid.columns:
        df_grid["Hora Vencimiento"] = ""
    hv = df_grid["Hora Vencimiento"].map(_fmt_hhmm)
    mask_empty = hv.map(lambda x: (str(x).strip() if x is not None else "") == "")
    df_grid["Hora Vencimiento"] = hv.mask(mask_empty, "17:00")

    # === Cumplimiento (auto; crear si falta) ===
    if "Cumplimiento" not in df_grid.columns:
        df_grid["Cumplimiento"] = ""

    fv = (
        to_naive_local_series(df_grid["Fecha Vencimiento"])
        if "Fecha Vencimiento" in df_grid.columns
        else pd.Series(pd.NaT, index=df_grid.index, dtype="datetime64[ns]")
    )

    ft = (
        to_naive_local_series(df_grid["Fecha Terminado"])
        if "Fecha Terminado" in df_grid.columns
        else pd.Series(pd.NaT, index=df_grid.index, dtype="datetime64[ns]")
    )

    today_ts = pd.Timestamp(date.today())
    fv_n = fv.dt.normalize()
    ft_n = ft.dt.normalize()
    has_fv = ~fv_n.isna()
    has_ft = ~ft_n.isna()
    delivered_on_time = has_fv & has_ft & (ft_n <= fv_n)
    delivered_late = has_fv & has_ft & (ft_n > fv_n)
    days_left = (fv_n - today_ts).dt.days
    no_delivered = has_fv & (~has_ft) & (days_left < 0)
    risk = has_fv & (~has_ft) & (days_left >= 1) & (days_left <= 2)

    out = pd.Series("", index=df_grid.index, dtype="object")
    out[delivered_on_time] = "✅ Entregado a tiempo"
    out[delivered_late] = "⏰ Entregado fuera de tiempo"
    out[no_delivered] = "❌ No entregado"
    out[risk] = "⚠️ En riesgo de retrasos"
    df_grid["Cumplimiento"] = out


# ============================================================
# Utilidades mínimas desde shared (blank_row, IDs, COLS, hora Lima, log_reciente)
# ============================================================
try:
    from shared import (  # type: ignore
        blank_row,
        next_id_by_person,
        make_id_prefix,
        COLS,
        now_lima_trimmed,
        log_reciente,
    )
except Exception:
    COLS = None
    log_reciente = None  # type: ignore

    def blank_row() -> dict:
        return {}

    def _clean3(s: str) -> str:
        s = (s or "").strip().upper()
        s = re.sub(r"[^A-Z0-9\s]+", "", s)
        return re.sub(r"\s+", "", s)[:3]

    def make_id_prefix(area: str, resp: str) -> str:
        a3 = _clean3(area)
        r = (resp or "").strip().upper()
        r_first = r.split()[0] if r.split() else r
        r3 = _clean3(r_first)
        if not a3 and not r3:
            return "GEN"
        return (a3 or "GEN") + (r3 or "")

    def next_id_by_person(df: pd.DataFrame, area: str, resp: str) -> str:
        prefix = make_id_prefix(area, resp)
        if "Id" in df.columns:
            ids = df["Id"].astype(str)
            mask = ids.str.startswith(prefix + "_")
            n = int(mask.sum()) + 1
        else:
            n = len(df.index) + 1
        return f"{prefix}_{n}"

    # --- Hora local America/Lima (fallback) ---
    try:
        from zoneinfo import ZoneInfo

        _LIMA = ZoneInfo("America/Lima")

        def now_lima_trimmed():
            return datetime.now(_LIMA).replace(second=0, microsecond=0)

    except Exception:  # pragma: no cover
        def now_lima_trimmed():
            return datetime.now().replace(second=0, microsecond=0)


# ============================================================
# Wrapper SEGURO para log_reciente de shared
# ============================================================
def log_reciente_safe(*args, **kwargs):
    """
    Envuelve shared.log_reciente:
    - Si existe y funciona, lo llama.
    - Si falla o no existe, no rompe ni muestra mensajes.
    """
    try:
        if callable(log_reciente):
            return log_reciente(*args, **kwargs)
    except Exception:
        # Silenciamos cualquier error interno del log
        pass

# ============================================================
#   HELPER: imagen del banner "Nueva tarea"
# ============================================================
@st.cache_data
def _hero_img_base64() -> str:
    """
    Devuelve el PNG del banner en base64.
    Busca en la carpeta 'assets' con varios nombres posibles.
    """
    import base64
    from pathlib import Path

    assets_dir = Path("assets")
    candidatos = [
        "NUEVA_TAREA.png",   # <- tu archivo principal de Nueva tarea
        "nueva_tarea.png",
        "TAREA_NUEVA.png",
        "TAREA-NUEVA.png",
        "TAREA NUEVA.png",
        "tarea_nueva.png",
    ]
    for nombre in candidatos:
        ruta = assets_dir / nombre
        if ruta.exists():
            return base64.b64encode(ruta.read_bytes()).decode("utf-8")
    return ""


# ============================================================
#   HELPER: imagen del separador "Tareas recientes"
#   (ENI2025/assets/TAREAS_RECIENTES.png)
# ============================================================
@st.cache_data
def _hist_img_base64() -> str:
    """
    Devuelve el PNG del banner de 'Tareas recientes' en base64.
    Espera encontrarlo en la carpeta 'assets'.
    """
    import base64
    from pathlib import Path

    assets_dir = Path("assets")
    candidatos = [
        "TAREAS_RECIENTES.png",   # <- archivo que mencionaste
        "tareas_recientes.png",
        "TAREAS-RECIENTES.png",
        "TAREAS RECIENTES.png",
    ]
    for nombre in candidatos:
        ruta = assets_dir / nombre
        if ruta.exists():
            return base64.b64encode(ruta.read_bytes()).decode("utf-8")
    return ""

# ============================================================
#   HELPER: sincronizar hora a partir de la fecha de registro
# ============================================================
def _sync_time_from_date():
    """
    Asegura que exista una hora (fi_t) coherente con la fecha fi_d.
    Usa now_lima_trimmed() si está disponible; si no, datetime.now().
    Actualiza también fi_t_view (HH:MM).
    """
    d = st.session_state.get("fi_d", None)

    # Si no hay fecha, limpiamos hora
    if d is None:
        st.session_state["fi_t"] = None
        st.session_state["fi_t_view"] = ""
        return

    try:
        dt = now_lima_trimmed()
    except Exception:
        from datetime import datetime
        dt = datetime.now()

    t = dt.time().replace(second=0, microsecond=0)
    st.session_state["fi_t"] = t
    st.session_state["fi_t_view"] = t.strftime("%H:%M")


# ============================================================
#           VISTA SUPERIOR: ➕ NUEVA TAREA
# ============================================================
def render_nueva_tarea(user: dict | None = None):
    """Vista: ➕ Nueva tarea (parte superior)"""

    # ===== CSS =====
    st.markdown(
        """
    <style>
    /* ===== Quitar la “hoja” blanca gigante del centro ===== */
    section.main{
        background-color: transparent !important;
    }
    div[data-testid="block-container"]{
        background-color: transparent !important;
        box-shadow: none !important;
        border: none !important;
    }
    div[data-testid="block-container"] > div{
        background-color: transparent !important;
        box-shadow: none !important;
    }

    /* Ocultar el caption automático de Streamlit */
    section.main div[data-testid="stCaptionContainer"]:first-of-type{
        display:none !important;
    }

    /* ===== Banner superior “Nueva tarea” ===== */
    .nt-hero-wrapper{
      margin-left:0px;
      margin-right:0px;
      margin-top:-50px;
      margin-bottom:0;
    }
    .nt-hero{
      border-radius:8px;
      background:linear-gradient(90deg,#93C5FD 0%,#A855F7 100%);
      padding:10px 32px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      color:#FFFFFF;
      box-shadow:none;
    }
    .nt-hero-left{
      display:flex;
      flex-direction:column;
      gap:4px;
    }
    .nt-hero-title{
      font-size:1.8rem;
      font-weight:700;
    }
    .nt-hero-right{
      flex:0 0 auto;
      display:flex;
      align-items:flex-end;
      justify-content:flex-end;
      padding-left:24px;
    }
    .nt-hero-img{
      display:block;
      height:160px;
      max-width:160px;
      transform: translateY(10px);
    }

    /* Contenedor del formulario de NUEVA TAREA – sin tarjeta ni bordes */
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel){
      background: transparent !important;
      box-shadow: none !important;
      border-radius: 0 !important;
      border: none !important;
      padding: 0 !important;
      margin: -3px 0 10px 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) > div{
      background: transparent !important;
      box-shadow: none !important;
      border-radius: 0 !important;
      border: none !important;
    }
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) form[data-testid="stForm"]{
      background: transparent !important;
      box-shadow: none !important;
      border-radius: 0 !important;
      border: none !important;
      padding-left: 0 !important;
      padding-right: 0 !important;
    }

    /* Inputs full width dentro del formulario de Nueva tarea */
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stTextInput,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stSelectbox,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stDateInput,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stTimeInput,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stTextArea{
      width:100% !important;
    }
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stTextInput>div,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stSelectbox>div,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stDateInput>div,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stTimeInput>div,
    div[data-testid="stVerticalBlock"]:has(#nt-card-sentinel) .stTextArea>div{
      width:100% !important;
      max-width:none !important;
    }

    /* Tarjetas de pasos de indicaciones */
    .nt-steps-row{
      display:flex;
      flex-wrap:wrap;
      gap:12px;
      margin-top:4px;
      margin-bottom:16px;
    }
    .nt-step-card{
      flex:1 1 180px;
      min-width:180px;
      background:#FFFFFF;
      border-radius:8px;
      border:1px solid #E5E7EB;
      padding:20px 20px;
      min-height:70px;
      box-shadow:none;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:12px;
    }
    .nt-step-main{
      flex:1;
      display:flex;
      flex-direction:column;
      justify-content:center;
      align-items:flex-start;
      text-align:left;
    }
    .nt-step-label{
      font-size:0.88rem;
      font-weight:400;
      color:#111827;
      white-space: nowrap;
    }
    .nt-step-icon-slot{
      flex:0 0 auto;
      display:flex;
      align-items:center;
      justify-content:center;
    }
    .nt-step-icon{
      width:32px;
      height:32px;
      border-radius:10px;
      display:flex;
      align-items:center;
      justify-content:center;
      background: transparent;
      font-size:1.8rem;
      flex-shrink:0;
    }
    .nt-step-text{
      display:none !important;
    }

    /* ===== Línea lila-azul superior (encima de las celdas) ===== */
    .nt-top-line{
      height:2px;
      background:linear-gradient(90deg,#93C5FD 0%,#A855F7 100%);
      border-radius:999px;
      margin:12px 0 18px 0;
    }

    /* ===== Línea lila-azul inferior (encima de los botones) ===== */
    .nt-bottom-line{
      height:2px;
      background:linear-gradient(90deg,#93C5FD 0%,#A855F7 100%);
      border-radius:999px;
      margin:18px 0 0 0;
    }

    /* ===== Fila inferior de botones ===== */
    .nt-bottom-row{
      margin-top:12px;
    }

    /* ===== Botones: base y colores (jade / lila) ===== */
    .nt-bottom-row button{
      border-radius:999px !important;
      font-weight:600 !important;
      box-shadow:none !important;
      border:none !important;
    }
    /* Volver = primer botón (jade) */
    .nt-bottom-row button:first-of-type{
      background:#34D399 !important;
      color:#FFFFFF !important;
    }
    .nt-bottom-row button:first-of-type:hover{
      background:#10B981 !important;
    }
    /* Agregar = segundo botón (lila) */
    .nt-bottom-row button:last-of-type{
      background:#A855F7 !important;
      color:#FFFFFF !important;
    }
    .nt-bottom-row button:last-of-type:hover{
      background:#9333EA !important;
    }
    </style>
        """,
        unsafe_allow_html=True,
    )

    # ===== Datos =====
    global AREAS_OPC
    if "AREAS_OPC" not in globals():
        AREAS_OPC = [
            "Jefatura",
            "Gestión",
            "Metodología",
            "Base de datos",
            "Capacitación",
            "Monitoreo",
            "Consistencia",
        ]

    st.session_state.setdefault("nt_visible", True)

    # Asegurar que "Tipo de tarea" no arranque con 'Otros'
    if st.session_state.get("nt_tipo", "").strip().lower() == "otros":
        st.session_state["nt_tipo"] = ""
    else:
        st.session_state.setdefault("nt_tipo", "")

    _NT_SPACE = 35
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ===== Banner superior “Nueva tarea” =====
    hero_b64 = _hero_img_base64()
    hero_img_html = (
        f'<img src="data:image/png;base64,{hero_b64}" alt="Nueva tarea" class="nt-hero-img">'
        if hero_b64 else ""
    )
    st.markdown(
        f"""
        <div class="nt-hero-wrapper">
          <div class="nt-hero">
            <div class="nt-hero-left">
              <div class="nt-hero-title">Nueva tarea</div>
            </div>
            <div class="nt-hero-right">
              {hero_img_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # espacio entre banner y tarjetas de pasos
    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    if st.session_state.get("nt_visible", True):
        if st.session_state.pop("nt_added_ok", False):
            st.success("Agregado a Tareas recientes")

    # ===== Pasos =====
    st.markdown(
        """
    <div class="nt-steps-row">
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">1. Llena los datos</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">📝</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">2. Pulsa “Agregar”</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">➕</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">3. Revisa tu tarea</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">🕑</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">4. Graba</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">💾</span></div>
      </div>
      <div class="nt-step-card">
        <div class="nt-step-main"><div class="nt-step-label">5. Sube a Sheets</div></div>
        <div class="nt-step-icon-slot"><span class="nt-step-icon">📤</span></div>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # ===== Formulario =====
    COLS_5 = [1, 1, 1, 1, 1]

    volver_clicked = False
    submitted = False

    with st.form("form_nueva_tarea"):
        with st.container():
            st.markdown(
                '<span id="nt-card-sentinel" style="display:none"></span>',
                unsafe_allow_html=True,
            )

            # ----- Responsable & Área -----
            _acl = st.session_state.get("acl_user", {}) or {}
            display_name_txt = (
                _acl.get("display")
                or st.session_state.get("user_display_name", "")
                or _acl.get("name", "")
                or (st.session_state.get("user") or {}).get("name", "")
                or ""
            )
            if not str(st.session_state.get("nt_resp", "")).strip():
                st.session_state["nt_resp"] = display_name_txt

            _area_acl = (
                _acl.get("area")
                or _acl.get("Área")
                or _acl.get("area_name")
                or ""
            ).strip()
            area_fixed = _area_acl if _area_acl else (AREAS_OPC[0] if AREAS_OPC else "")
            st.session_state["nt_area"] = area_fixed

            # ----- Fases -----
            FASES = [
                "Capacitación",
                "Post-capacitación",
                "Pre-consistencia",
                "Consistencia",
                "Operación de campo",
                "Implementación del sistema de monitoreo",
                "Uso del sistema de monitoreo",
                "Uso del sistema de capacitación",
                "Levantamiento en campo",
                "Otros",
            ]
            _fase_sel = st.session_state.get("nt_fase", None)
            _is_fase_otros = str(_fase_sel).strip() == "Otros"

            # ===== Línea lila-azul ENCIMA de las celdas =====
            st.markdown('<div class="nt-top-line"></div>', unsafe_allow_html=True)

            # ---------- FILA 1 ----------
            if _is_fase_otros:
                c1, c2, c3, c4, c5 = st.columns(COLS_5, gap="medium")
                c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
                c2.selectbox("Fase", options=FASES, key="nt_fase", index=FASES.index("Otros"))
                c3.text_input("Otros (especifique)", key="nt_fase_otro", placeholder="Describe la fase")
                c4.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                c5.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
            else:
                c1, c2, c3, c4, c5 = st.columns(COLS_5, gap="medium")
                c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
                c2.selectbox(
                    "Fase",
                    options=FASES,
                    index=None,
                    placeholder="Selecciona una fase",
                    key="nt_fase",
                )
                c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                c4.text_input("Detalle de tarea", placeholder="Información adicional (opcional)", key="nt_detalle")
                c5.text_input("Responsable", key="nt_resp", disabled=True)

            # ----- Fecha/Hora base -----
            if st.session_state.get("fi_d", "___MISSING___") is None:
                st.session_state.pop("fi_d")
            if st.session_state.get("fi_t", "___MISSING___") is None:
                st.session_state.pop("fi_t")
            if "fi_d" not in st.session_state:
                if st.session_state.get("nt_skip_date_init", False):
                    st.session_state.pop("nt_skip_date_init", None)
                else:
                    st.session_state["fi_d"] = now_lima_trimmed().date()
            _sync_time_from_date()

            _t = st.session_state.get("fi_t")
            st.session_state["fi_t_view"] = _t.strftime("%H:%M") if _t else ""

            # ID preview
            _df_tmp = (
                st.session_state.get("df_main", pd.DataFrame()).copy()
                if "df_main" in st.session_state else pd.DataFrame()
            )
            prefix = make_id_prefix(
                st.session_state.get("nt_area", area_fixed),
                st.session_state.get("nt_resp", ""),
            )
            id_preview = (
                next_id_by_person(
                    _df_tmp,
                    st.session_state.get("nt_area", area_fixed),
                    st.session_state.get("nt_resp", ""),
                )
                if st.session_state.get("fi_d")
                else f"{prefix}_"
            )

            # ---------- FILA 2 ----------
            if _is_fase_otros:
                r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(COLS_5, gap="medium")
                r2c1.text_input("Responsable", key="nt_resp", disabled=True)
                r2c2.selectbox("Ciclo de mejora", options=["1", "2", "3", "+4"], index=0, key="nt_ciclo_mejora")
                r2c3.text_input("Tipo de tarea", key="nt_tipo", placeholder="Escribe el tipo de tarea")
                r2c4.text_input("Estado actual", value="No iniciado", disabled=True, key="nt_estado_view")
                r2c5.selectbox("Complejidad", options=["🟢 Baja", "🟡 Media", "🔴 Alta"], index=0, key="nt_complejidad")

                # ---------- FILA 3 (solo celdas) ----------
                r3c1, r3c2, r3c3, _, _ = st.columns(COLS_5, gap="medium")
                r3c1.selectbox(
                    "Duración",
                    options=[f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)],
                    index=0,
                    key="nt_duracion_label",
                )
                r3c2.date_input("Fecha de registro", key="fi_d")
                _sync_time_from_date()
                r3c3.text_input(
                    "Hora de registro (auto)",
                    key="fi_t_view",
                    disabled=True,
                    help="Se asigna al elegir la fecha",
                )

            else:
                r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(COLS_5, gap="medium")
                r2c1.selectbox("Ciclo de mejora", options=["1", "2", "3", "+4"], index=0, key="nt_ciclo_mejora")
                r2c2.text_input("Tipo de tarea", key="nt_tipo", placeholder="Escribe el tipo de tarea")
                r2c3.text_input("Estado actual", value="No iniciado", disabled=True, key="nt_estado_view")
                r2c4.selectbox("Complejidad", options=["🟢 Baja", "🟡 Media", "🔴 Alta"], index=0, key="nt_complejidad")
                r2c5.selectbox(
                    "Duración",
                    options=[f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)],
                    index=0,
                    key="nt_duracion_label",
                )

                # ---------- FILA 3 (solo celdas) ----------
                r3c1, r3c2, r3c3, _, _ = st.columns(COLS_5, gap="medium")
                r3c1.date_input("Fecha de registro", key="fi_d")
                _sync_time_from_date()
                r3c2.text_input(
                    "Hora de registro",
                    key="fi_t_view",
                    disabled=True,
                    help="Se asigna al elegir la fecha",
                )
                r3c3.text_input("ID asignado", value=id_preview, disabled=True, key="nt_id_preview")

            # ===== Línea lila-azul ENCIMA de los botones =====
            st.markdown('<div class="nt-bottom-line"></div>', unsafe_allow_html=True)

            # ===== Fila inferior de botones (derecha) =====
            bottom_left, bottom_right = st.columns([4, 1])

            with bottom_right:
                st.markdown('<div class="nt-bottom-row">', unsafe_allow_html=True)
                col_v, col_a = st.columns(2, gap="medium")

                with col_v:
                    volver_clicked = st.form_submit_button(
                        "⬅ Volver",
                        use_container_width=True,
                    )

                with col_a:
                    submitted = st.form_submit_button(
                        "➕ Agregar",
                        use_container_width=True,
                    )

                st.markdown("</div>", unsafe_allow_html=True)

    # ------ Acción botones fuera del form ------
    if volver_clicked:
        st.session_state["home_tile"] = ""
        display_name = st.session_state.get("user_display_name", "Usuario")
        try:
            st.experimental_set_query_params(auth="1", u=display_name)
        except Exception:
            pass
        st.rerun()

    if submitted and not volver_clicked:
        try:
            df = st.session_state.get("df_main", pd.DataFrame()).copy()
            # aquí va tu lógica de guardado
            pass
        except Exception as e:
            st.error(f"No pude guardar la nueva tarea: {e}")

    gap = SECTION_GAP if "SECTION_GAP" in globals() else 30
    st.markdown(f"<div style='height:{gap}px;'></div>", unsafe_allow_html=True)


# ============================================================
#             VISTA UNIFICADA (NUEVA + RECIENTES)
# ============================================================
def render(user: dict | None = None):
    """
    Vista combinada:
    - Arriba: ➕ Nueva tarea
    - Abajo: 🕑 Tareas recientes
    """
    _bootstrap_df_main_hist()
    render_nueva_tarea(user=user)
    render_historial(user=user)
