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
        # *** NUEVO: baseline si aún no existe
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


# =======================================================
#                 VISTA INFERIOR: TAREAS RECIENTES
# =======================================================
def render_historial(user: dict | None = None):
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

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

        /* Separadores horizontales suaves */
        --row-sep:#E5E7EB;
      }

      .hist-card{ border:0!important; background:transparent!important; border-radius:0!important; padding:0!important; margin:0 0 8px 0!important; }

      .hist-title-pill{
        display:inline-flex; align-items:center; gap:8px; padding:10px 16px;
        border-radius:10px; background: var(--pill-salmon); color:#fff;
        font-weight:600; font-size:1.05rem; line-height:1.1;
        box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06); margin-bottom:10px;
      }

      /* Indicaciones coral */
      .hist-hint{
        background:var(--hint-bg); border:1px dashed var(--hint-border);
        border-radius:10px; padding:10px 12px; color:var(--hint-color);
        margin: 2px 0 12px 0; font-size:0.95rem;
      }

      /* Ocultar input fantasma directamente debajo de la hint */
      .hist-hint + div[data-testid="stTextInput"]{ display:none!important; }
      .hist-hint + div:has(div[data-testid="stTextInput"]){ display:none!important; }
      .hist-hint + div:has(input[type="text"]){ display:none!important; }

      /* ✅ Marco con dos líneas (arriba y abajo) alrededor de los filtros */
      .hist-filters{
        border:0!important; background:transparent!important;
        border-radius:0!important;
        padding:0!important;
        margin:6px 0 8px 0 !important;
        box-shadow:
          inset 0 1px 0 var(--row-sep),
          inset 0 -1px 0 var(--row-sep);
      }

      /* Botón buscar del ancho de su celda (debajo de Hasta) */
      .hist-search .stButton>button{ width:100%; }

      /* AG Grid base con líneas horizontales suaves */
      .ag-theme-balham .ag-cell{
        white-space:nowrap!important; overflow:hidden!important; text-overflow:ellipsis!important;
        border-top:1px solid var(--row-sep)!important;
        border-bottom:1px solid var(--row-sep)!important;
      }
      .ag-theme-balham .ag-header-cell{
        border-top:1px solid var(--row-sep)!important;
        border-bottom:1px solid var(--row-sep)!important;
      }
      .ag-theme-balham .ag-header-cell-label{ white-space:nowrap!important; line-height:1.1!important; overflow:visible!important; text-overflow:clip!important; }
      .ag-theme-balham .ag-header .ag-icon, .ag-theme-balham .ag-header-cell .ag-icon, .ag-theme-balham .ag-header-cell-menu-button,
      .ag-theme-balham .ag-floating-filter, .ag-theme-balham .ag-header-row.ag-header-row-column-filter { display:none!important; }

      /* Encabezados coloreados (armonía con Editar estado) */
      .ag-theme-balham .ag-header-cell.hdr-registro{ background:var(--hdr-reg)!important; border-radius:8px; }
      .ag-theme-balham .ag-header-cell.hdr-inicio{   background:var(--hdr-ini)!important; border-radius:8px; }
      .ag-theme-balham .ag-header-cell.hdr-termino{  background:var(--hdr-ter)!important; border-radius:8px; }
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

    # ===== Píldora e indicaciones =====
    st.markdown('<div class="hist-title-pill">🕑 Tareas recientes</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hist-hint">Aquí puedes editar <b>Tarea</b> y <b>Detalle de tarea</b>. '
        'Opcional: descargar en Excel. <b>Obligatorio:</b> Grabar y después Subir a Sheets.</div>',
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

    with st.container():
        st.markdown(
            '<div style="height:0; border-top:1px solid var(--row-sep); margin:0 0 6px 0;"></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="hist-filters">', unsafe_allow_html=True)

        if super_editor:
            responsables = sorted([
                x
                for x in df_scope.get("Responsable", pd.Series([], dtype=str)).astype(str).unique()
                if x and x != "nan"
            ])
            c1, c2, c3, c4, c5, c6, c7 = st.columns([1.30, 1.20, 1.10, 1.10, 1.30, 1.00, 1.00], gap="medium")
            with c1:
                resp_multi = st.multiselect(
                    "Responsable",
                    options=responsables,
                    default=[],
                    key="hist_resp",
                    placeholder="Selecciona responsable(s)",
                )
            with c2:
                _est_lbl = _sel(ESTADO_CHOICES, "Estado actual", "hist_estado")
            with c3:
                _pri_lbl = _sel(PRIORIDAD_CHOICES, "Prioridad", "hist_prio")
            with c4:
                _com_lbl = _sel(COMPLEJIDAD_CHOICES, "Complejidad", "hist_comp")
            with c5:
                _cum_lbl = _sel(CUMPL_CHOICES, "Cumplimiento", "hist_cumpl")
            with c6:
                f_desde = st.date_input("Desde", value=_min_date, key="hist_desde")
            with c7:
                f_hasta = st.date_input("Hasta", value=_max_date, key="hist_hasta")
                st.markdown('<div class="hist-search">', unsafe_allow_html=True)
                hist_do_buscar = st.button("🔍 Buscar", use_container_width=True, key="hist_btn_buscar")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            c1, c2, c3, c4, c5, c6 = st.columns([1.20, 1.10, 1.10, 1.30, 1.00, 1.00], gap="medium")
            with c1:
                _est_lbl = _sel(ESTADO_CHOICES, "Estado actual", "hist_estado")
            with c2:
                _pri_lbl = _sel(PRIORIDAD_CHOICES, "Prioridad", "hist_prio")
            with c3:
                _com_lbl = _sel(COMPLEJIDAD_CHOICES, "Complejidad", "hist_comp")
            with c4:
                _cum_lbl = _sel(CUMPL_CHOICES, "Cumplimiento", "hist_cumpl")
            with c5:
                f_desde = st.date_input("Desde", value=_min_date, key="hist_desde")
            with c6:
                f_hasta = st.date_input("Hasta", value=_max_date, key="hist_hasta")
                st.markdown('<div class="hist-search">', unsafe_allow_html=True)
                hist_do_buscar = st.button("🔍 Buscar", use_container_width=True, key="hist_btn_buscar")
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown(
            '<div style="height:0; border-bottom:1px solid var(--row-sep); margin:2px 0 6px 0;"></div>',
            unsafe_allow_html=True,
        )

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
    fv = to_naive_local_series(df_grid["Fecha Vencimiento"]) if "Fecha Vencimiento" in df_grid.columns else pd.Series(
        pd.NaT, index=df_grid.index, dtype="datetime64[ns]"
    )
    ft = to_naive_local_series(df_grid["Fecha Terminado"]) if "Fecha Terminado" in df_grid.columns else pd.Series(
        pd.NaT, index=df_grid.index, dtype="datetime64[ns]"
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

    # ======= Snapshot / Detección de cambios =======
    editable_cols = set()

    gob = GridOptionsBuilder.from_dataframe(df_grid)
    gob.configure_default_column(
        resizable=True,
        editable=False,
        filter=False,
        floatingFilter=False,
        sortable=False,
        suppressMenu=True,
        wrapText=False,
        autoHeight=False,
        cellStyle={
            "white-space": "nowrap",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
        },
    )

    width_map = {
        "Id": 110,
        "Área": 140,
        "Fase": 180,
        "Responsable": 220,
        "Tarea": 280,
        "Detalle": 360,
        "Detalle de tarea": 360,
        "Tipo de tarea": 140,
        "Ciclo de mejora": 150,
        "Complejidad": 140,
        "Prioridad": 130,
        "Estado": 150,
        "Duración": 120,
        "Fecha Registro": 150,
        "Hora Registro": 130,
        "Fecha inicio": 150,
        "Hora de inicio": 130,
        "Fecha Vencimiento": 150,
        "Hora Vencimiento": 130,
        "Fecha Terminado": 150,
        "Hora Terminado": 130,
        "¿Generó alerta?": 160,
        "N° alerta": 130,
        "Fecha de detección": 170,
        "Hora de detección": 150,
        "¿Se corrigió?": 140,
        "Fecha de corrección": 170,
        "Hora de corrección": 150,
        "Cumplimiento": 200,
        "Evaluación": 150,
        "Calificación": 140,
        "Fecha Pausado": 150,
        "Hora Pausado": 130,
        "Fecha Cancelado": 150,
        "Hora Cancelado": 130,
        "Fecha Eliminado": 150,
        "Hora Eliminado": 130,
        "Link de descarga": 260,
        _LINK_CANON: 120,
    }

    header_map = {
        "Detalle": "Detalle de tarea",
        "Fecha Vencimiento": "Fecha límite",
        "Hora Vencimiento": "Hora límite",
        "Fecha inicio": "Fecha de inicio",
        "Hora de inicio": "Hora de inicio",
        "Fecha Registro": "Fecha de registro",
        "Hora Registro": "Hora de registro",
        "Fecha Terminado": "Fecha terminada",
        "Hora Terminado": "Hora terminada",
        "Fecha Eliminado": "Fecha eliminada",
        "Hora Eliminado": "Hora eliminada",
        "Fecha Cancelado": "Fecha cancelada",
        "Hora Cancelado": "Hora cancelada",
        "Fecha Pausado": "Fecha pausada",
        "Hora Pausado": "Hora pausada",
    }

    _acl_user = st.session_state.get("acl_user", {}) or {}
    _ro_acl = {re.sub(r"[^a-z0-9]", "", x.lower()) for x in _get_readonly_cols_from_acl(_acl_user)}

    def _normkey(x: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (x or "").lower())

    super_editor = _is_super_editor()
    _editable_base = (set(df_grid.columns) - {"Link de descarga", _LINK_CANON}) if super_editor else {"Tarea", "Detalle"}
    _header_map_norm = {_normkey(k): v for k, v in header_map.items()}

    cell_style_reg = JsCode("function(p){return {backgroundColor:'var(--hdr-reg)'};}")
    cell_style_ini = JsCode("function(p){return {backgroundColor:'var(--hdr-ini)'};}")
    cell_style_ter = JsCode("function(p){return {backgroundColor:'var(--hdr-ter)'};}")

    for col in df_grid.columns:
        nice = _header_map_norm.get(_normkey(col), header_map.get(col, col))
        col_is_editable = (
            (col in _editable_base)
            if super_editor
            else (
                (col in _editable_base)
                and (_normkey(col) not in _ro_acl)
                and (_normkey(nice) not in _ro_acl)
            )
        )

        hdr_class = None
        cellStyle = None
        if col in ("Fecha Registro", "Hora Registro"):
            hdr_class = "hdr-registro"
            cellStyle = cell_style_reg
        elif col in ("Fecha inicio", "Hora de inicio"):
            hdr_class = "hdr-inicio"
            cellStyle = cell_style_ini
        elif col in ("Fecha Terminado", "Hora Terminado"):
            hdr_class = "hdr-termino"
            cellStyle = cell_style_ter

        kwargs = dict(
            headerName=nice,
            minWidth=width_map.get(nice, width_map.get(col, 120)),
            editable=col_is_editable,
            suppressMenu=True,
            filter=False,
            floatingFilter=False,
            sortable=False,
        )
        if hdr_class:
            kwargs["headerClass"] = hdr_class
        if cellStyle:
            kwargs["cellStyle"] = cellStyle

        gob.configure_column(col, **kwargs)

    gob.configure_column(_LINK_CANON, hide=True)

    date_only_fmt = JsCode(
        r"""
    function(p){
      const v = p.value;
      if(v===null || v===undefined) return '—';
      const s = String(v).trim();
      if(!s || ['nan','nat','null'].includes(s.toLowerCase())) return '—';
      let y,m,d;
      const m1 = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if(m1){ y=+m1[1]; m=+m1[2]; d=+m1[3]; }
      if(!y && /^\d{12,13}$/.test(s)){
        const dt = new Date(Number(s));
        if(!isNaN(dt)){ y=dt.getFullYear(); m=dt.getMonth()+1; d=dt.getDate(); }
      }
      if(!y){
        const dt = new Date(s);
        if(!isNaN(dt)){ y=dt.getFullYear(); m=dt.getMonth()+1; d=dt.getDate(); }
      }
      if(!y) return s.split(' ')[0];
      return String(d).padStart(2,'0') + '/' + String(m).padStart(2,'0') + '/' + y;
    }"""
    )

    for col in [
        "Fecha Registro",
        "Fecha inicio",
        "Fecha Vencimiento",
        "Fecha Terminado",
        "Fecha Pausado",
        "Fecha Cancelado",
        "Fecha Eliminado",
        "Fecha de detección",
        "Fecha de corrección",
    ]:
        if col in df_grid.columns:
            nice = _header_map_norm.get(_normkey(col), header_map.get(col, col))
            hdr_class = None
            style = None
            if col == "Fecha Registro":
                hdr_class = "hdr-registro"
                style = cell_style_reg
            elif col == "Fecha inicio":
                hdr_class = "hdr-inicio"
                style = cell_style_ini
            elif col == "Fecha Terminado":
                hdr_class = "hdr-termino"
                style = cell_style_ter
            kwargs = dict(headerName=nice, valueFormatter=date_only_fmt)
            if hdr_class:
                kwargs["headerClass"] = hdr_class
            if style:
                kwargs["cellStyle"] = style
            gob.configure_column(col, **kwargs)

    link_value_getter = JsCode(
        r"""
    function(p){
      const text = String((p && p.data && p.data['Link de archivo']) || '').trim();
      if(!text) return '';
      const m = text.match(/https?:\/\/\S+/i);
      return m ? m[0].replace(/[),.]+$/, '') : '';
    }"""
    )
    link_renderer = JsCode(
        r"""
    class LinkRenderer{
      init(params){
        const url = (params && params.value) ? String(params.value) : '';
        this.eGui = document.createElement('a');
        if(url){
          this.eGui.href = encodeURI(url);
          this.eGui.target = '_blank';
          this.eGui.rel='noopener';
          this.eGui.textContent = url;
          this.eGui.style.textDecoration='underline';
        }else{
          this.eGui.textContent = '—';
          this.eGui.style.opacity='0.8';
        }
      }
      getGui(){ return this.eGui; }
      refresh(){ return false; }
    }"""
    )
    gob.configure_column(
        "Link de descarga",
        valueGetter=link_value_getter,
        cellRenderer=link_renderer,
        tooltipField="Link de descarga",
        minWidth=width_map["Link de descarga"],
        flex=1,
    )

    cumplimiento_style = JsCode(
        r"""
    function(p){
      const v = (p.value || '').toLowerCase();
      if(!v) return {};
      if(v.includes('a tiempo')){
        return {backgroundColor:'#DCFCE7', color:'#065F46', fontWeight:'600',
                borderRadius:'12px', padding:'4px 8px', textAlign:'center'};
      }
      if(v.includes('fuera de tiempo')){
        return {backgroundColor:'#FFE4E6', color:'#9F1239', fontWeight:'600',
                borderRadius:'12px', padding:'4px 8px', textAlign:'center'};
      }
      if(v.includes('no entregado')){
        return {backgroundColor:'#FEE2E2', color:'#7F1D1D', fontWeight:'600',
                borderRadius:'12px', padding:'4px 8px', textAlign:'center'};
      }
      if(v.includes('riesgo')){
        return {backgroundColor:'#FEF9C3', color:'#92400E', fontWeight:'600',
                borderRadius:'12px', padding:'4px 8px', textAlign:'center'};
      }
      return {};
    }"""
    )
    gob.configure_column("Cumplimiento", cellStyle=cumplimiento_style)

    gob.configure_column(
        "Fecha inicio",
        headerName=_header_map_norm.get(_normkey("Fecha inicio"), header_map.get("Fecha inicio", "Fecha inicio")),
        filter=False,
        floatingFilter=False,
        sortable=False,
        suppressMenu=True,
        cellStyle=cell_style_ini,
    )

    gob.configure_column("Calificación", type=["textColumn"])

    gob.configure_grid_options(
        domLayout="normal",
        rowHeight=34,
        headerHeight=64,
        enableRangeSelection=True,
        enableCellTextSelection=True,
        singleClickEdit=True,
        stopEditingWhenCellsLoseFocus=True,
        undoRedoCellEditing=False,
        ensureDomOrder=True,
        suppressMovableColumns=False,
        suppressHeaderVirtualisation=True,
    )

    grid_opts = gob.build()
    grid_opts["rememberSelection"] = True
    grid_opts["floatingFilter"] = False

    grid_resp = AgGrid(
        df_grid,
        key="grid_historial",
        gridOptions=grid_opts,
        theme="balham",
        height=500,
        fit_columns_on_grid_load=False,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=(
            GridUpdateMode.MODEL_CHANGED
            | GridUpdateMode.FILTERING_CHANGED
            | GridUpdateMode.SORTING_CHANGED
            | GridUpdateMode.VALUE_CHANGED
        ),
        allow_unsafe_jscode=True,
    )

    # === TRACKING de cambios ===
    base_cols = list(st.session_state.get("df_main", pd.DataFrame()).columns) or list(df_grid.columns)
    persist_cols = [c for c in df_grid.columns if c in base_cols]
    snap_cols = persist_cols
    st.session_state["_hist_cols"] = snap_cols

    prev = st.session_state.get("_hist_prev")

    try:
        edited = grid_resp["data"]
        new_df = pd.DataFrame(edited) if isinstance(edited, list) else pd.DataFrame(grid_resp.data)

        # *** NUEVO: asegurar derivados en el df editado ANTES de comparar/guardar
        new_df = _ensure_deadline_and_compliance(new_df)

        changed_ids_run = set()
        cell_diff_run: dict[str, set[str]] = {}
        new_only_ids_run = set()

        if isinstance(prev, pd.DataFrame) and new_df is not None:
            prev = _ensure_deadline_and_compliance(prev)  # *** NUEVO
            a = prev.reindex(columns=snap_cols).copy()
            b = new_df.reindex(columns=snap_cols).copy()
            if "Id" not in a.columns and "Id" in b.columns:
                a["Id"] = ""
            if "Id" not in b.columns and "Id" in a.columns:
                b["Id"] = ""
            a["Id"] = a["Id"].astype(str)
            b["Id"] = b["Id"].astype(str)
            prev_map = a.set_index("Id", drop=False)
            curr_map = b.set_index("Id", drop=False)

            for iid, row in curr_map.iterrows():
                if iid and iid != "nan" and iid not in prev_map.index:
                    new_only_ids_run.add(iid)
                    changed_ids_run.add(iid)

            common_ids = prev_map.index.intersection(curr_map.index)
            cols_to_cmp = [c for c in snap_cols if c != "Id"]
            if len(common_ids) and cols_to_cmp:
                prev_block = prev_map.loc[common_ids, cols_to_cmp].fillna("").astype(str)
                curr_block = curr_map.loc[common_ids, cols_to_cmp].fillna("").astype(str)
                neq = prev_block.ne(curr_block)
                changed_any = neq.any(axis=1)
                ids_changed = changed_any[changed_any].index
                changed_ids_run.update(ids_changed.tolist())
                for rid in ids_changed:
                    diff_mask = neq.loc[rid].to_numpy()
                    diff_cols = set(neq.columns[diff_mask].tolist())
                    # *** FIX: si cambian base, forzar derivados para subir
                    if {"Duración", "Fecha inicio"} & diff_cols:
                        diff_cols |= {"Fecha Vencimiento", "Hora Vencimiento"}
                    if {"Fecha Vencimiento", "Fecha Terminado"} & diff_cols:
                        diff_cols |= {"Cumplimiento"}
                    cell_diff_run[str(rid)] = diff_cols

        pend_ids = set(st.session_state.get("_hist_changed_ids", []) or [])
        pend_diff = {k: set(v) for k, v in (st.session_state.get("_hist_cell_diff", {}) or {}).items()}
        pend_new = set(st.session_state.get("_hist_new_ids", []) or [])

        pend_ids |= changed_ids_run
        pend_new |= new_only_ids_run
        for rid, cols in cell_diff_run.items():
            pend_diff[rid] = (pend_diff.get(rid, set())) | set(cols)

        st.session_state["_hist_changed_ids"] = sorted(pend_ids)
        st.session_state["_hist_cell_diff"] = {k: sorted(v) for k, v in pend_diff.items()}
        st.session_state["_hist_new_ids"] = sorted(pend_new)

        if new_df is not None:
            base = st.session_state.get("df_main", pd.DataFrame()).copy()
            base = _canonicalize_link_column(base)
            new_df = _canonicalize_link_column(new_df)
            if ("Id" in base.columns) and ("Id" in new_df.columns):
                base["Id"] = base["Id"].astype(str)
                new_df["Id"] = new_df["Id"].astype(str)
                base_idx = base.set_index("Id")
                new_idx = new_df.set_index("Id")
                cols_to_update = [c for c in new_idx.columns if c in base_idx.columns]
                base_idx.update(new_df[cols_to_update])
                st.session_state["df_main"] = base_idx.reset_index()
            else:
                st.session_state["df_main"] = new_df
            try:
                _save_local(st.session_state["df_main"].copy())
            except Exception:
                pass

            try:
                st.session_state["_hist_prev"] = new_df.reindex(columns=snap_cols).copy()
            except Exception:
                pass

    except Exception:
        pass

    # ===== Botonera =====
    st.markdown('<div style="padding:0 16px;">', unsafe_allow_html=True)
    _sp, b_sync, b_xlsx, b_save_local, b_save_sheets = st.columns([4.9, 1.4, 1.6, 1.4, 2.2], gap="medium")

    with b_xlsx:
        try:
            base = st.session_state["df_main"].copy()
            for c in ["__SEL__", "__DEL__", "¿Eliminar?"]:
                if c in base.columns:
                    base.drop(columns=[c], inplace=True, errors="ignore")
            xlsx_b = export_excel(base, sheet_name=TAB_NAME)
            st.download_button(
                "⬇️ Exportar Excel",
                data=xlsx_b,
                file_name="tareas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.warning(f"No pude generar Excel: {e}")

    with b_sync:
        if _is_super_editor():
            if st.button("🔄 Sincronizar", use_container_width=True, key="btn_sync_sheet"):
                try:
                    pull_user_slice_from_sheet(replace_df_main=False)
                    _save_local(st.session_state["df_main"].copy())
                except Exception as e:
                    st.warning(f"No se pudo sincronizar: {e}")

    with b_save_local:
        if st.button("💾 Grabar", use_container_width=True):
            try:
                _save_local(st.session_state["df_main"].copy())
                st.success("Datos grabados en data/tareas.csv.")
            except Exception as e:
                st.warning(f"No se pudo grabar localmente: {e}")

    with b_save_sheets:
        if st.button("📤 Subir a Sheets", use_container_width=True):
            try:
                # *** NUEVO: asegurar derivados y IDs ANTES de subir
                st.session_state["df_main"] = _ensure_deadline_and_compliance(
                    st.session_state.get("df_main", pd.DataFrame())
                )
                base_full = st.session_state.get("df_main", pd.DataFrame()).copy()

                # ⬇️ generar Id para filas sin Id (p. ej. tareas creadas desde correo)
                base_full, gen_ids = _ensure_row_ids(base_full)
                if gen_ids:
                    # persistir los nuevos Ids en sesión + disco
                    st.session_state["df_main"] = base_full.copy()
                    _save_local(base_full.copy())

                pend_ids = set(st.session_state.get("_hist_changed_ids", []) or [])
                pend_diff = dict(st.session_state.get("_hist_cell_diff", {}) or {})
                new_ids = set(st.session_state.get("_hist_new_ids", []) or {})

                # incluir Ids recién generados como "nuevos"
                new_ids |= set(map(str, gen_ids))

                # Fallback si no detectó cambios (reconstruir contra baseline)
                if (not pend_ids) and (not new_ids):
                    allowed = None if _is_super_editor() else {
                        "Tarea",
                        "Detalle",
                        "Detalle de tarea",
                        "Duración",
                        "Fecha inicio",
                        "Fecha Vencimiento",
                        "Hora Vencimiento",
                        "Cumplimiento",
                    }
                    base_line = st.session_state.get("_hist_baseline")
                    p_ids, p_diff, p_new = _derive_pending_from_baseline(
                        base_full, base_line, allowed_cols=allowed
                    )
                    pend_ids, pend_diff, new_ids = p_ids, {k: set(v) for k, v in p_diff.items()}, p_new | new_ids

                ids_to_push = set(pend_ids) | set(new_ids)
                if not ids_to_push:
                    st.info("No hay cambios detectados en la grilla para enviar.")
                else:
                    if base_full.empty or "Id" not in base_full.columns:
                        st.warning("No hay base para subir.")
                    else:
                        base_full["Id"] = base_full.get("Id", "").astype(str)

                        # 🔒 Usuarios no-super: restringir columnas permitidas
                        if not _is_super_editor():
                            me = _display_name().strip()
                            if "Responsable" in base_full.columns and me:
                                mask_mias = base_full["Responsable"].astype(str).str.contains(
                                    me, case=False, na=False
                                )
                                base_full = base_full[mask_mias]

                            ALLOWED_USER_COLS = {
                                "Tarea",
                                "Detalle",
                                "Detalle de tarea",
                                "Duración",
                                "Fecha inicio",
                                "Fecha Vencimiento",
                                "Hora Vencimiento",
                                "Cumplimiento",
                            }
                            filtered_cell_diff = {}
                            for rid, cols in pend_diff.items():
                                keep = {c for c in set(cols) if c in ALLOWED_USER_COLS}
                                if keep:
                                    filtered_cell_diff[str(rid)] = keep
                            pend_diff = filtered_cell_diff

                            ids_in_base = set(base_full["Id"].astype(str))
                            pend_ids = {
                                rid for rid in pend_ids if (rid in ids_in_base and ((rid in pend_diff) or (rid in new_ids)))
                            }
                            new_ids = {rid for rid in new_ids if rid in ids_in_base}
                            ids_to_push = set(pend_ids) | set(new_ids)

                            if not ids_to_push:
                                st.info(
                                    "No hay cambios permitidos para subir (solo 'Tarea', 'Detalle', 'Duración' y derivados de tus tareas)."
                                )
                                st.stop()

                        # ▶️ Upsert a TareasRecientes
                        df_rows = base_full[base_full["Id"].astype(str).isin(ids_to_push)].copy()
                        res = _sheet_upsert_by_id_partial(
                            df_rows,
                            cell_diff_map=pend_diff,
                            new_ids=new_ids,
                        )

                        # ▶️ Además, copiar Cumplimiento a Evaluación si cambió
                        ids_cumpl = {
                            rid
                            for rid, cols in (st.session_state.get("_hist_cell_diff", {}) or {}).items()
                            if "Cumplimiento" in set(cols)
                        }
                        if not ids_cumpl:
                            base_line = st.session_state.get("_hist_baseline")
                            if isinstance(base_line, pd.DataFrame):
                                cur = base_full.set_index("Id")
                                old = _ensure_deadline_and_compliance(base_line).set_index("Id")
                                common = cur.index.intersection(old.index)
                                if (
                                    len(common)
                                    and "Cumplimiento" in cur.columns
                                    and "Cumplimiento" in old.columns
                                ):
                                    ch = old.loc[common, "Cumplimiento"].astype(str) != cur.loc[
                                        common, "Cumplimiento"
                                    ].astype(str)
                                    ids_cumpl = set(common[ch])

                        if ids_cumpl:
                            try:
                                df_eval = base_full[
                                    base_full["Id"].astype(str).isin(ids_cumpl)
                                ][["Id", "Cumplimiento"]].copy()
                                res_eval = _sheet_upsert_eval_cumpl(df_eval)
                                if res_eval.get("ok"):
                                    st.success(res_eval.get("msg", "Evaluación actualizada."))
                                else:
                                    st.info(res_eval.get("msg", "No se pudo actualizar Evaluación."))
                            except Exception as ee:
                                st.info(f"No pude actualizar Evaluación: {ee}")

                        if res.get("ok"):
                            st.success(res.get("msg", "Actualizado."))
                            # limpiar pendientes
                            st.session_state["_hist_changed_ids"] = []
                            st.session_state["_hist_cell_diff"] = {}
                            st.session_state["_hist_new_ids"] = []
                            # *** NUEVO: baseline = estado actual tras subir
                            try:
                                st.session_state["_hist_baseline"] = base_full.copy()
                            except Exception:
                                pass
                            try:
                                st.session_state["_last_pull_hist"] = 0
                                pull_user_slice_from_sheet(replace_df_main=False)
                                _save_local(st.session_state["df_main"].copy())
                                st.rerun()
                            except Exception as e:
                                st.info(f"Actualizado. No pude refrescar desde Sheets: {e}")
                        else:
                            st.warning(res.get("msg", "No se pudo actualizar."))
            except Exception as e:
                st.warning(f"No se pudo subir a Sheets: {e}")

    st.markdown("</div>", unsafe_allow_html=True)


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
# SOLO configuración de Google Sheets para NUEVA TAREA
# ============================================================
def _get_sheet_conf():
    ss_url = (
        st.secrets.get("gsheets_doc_url")
        or (st.secrets.get("gsheets", {}) or {}).get("spreadsheet_url")
        or (st.secrets.get("sheets", {}) or {}).get("sheet_url")
    )
    ws_name = (st.secrets.get("gsheets", {}) or {}).get("worksheet", "TareasRecientes")
    return ss_url, ws_name


SECTION_GAP = globals().get("SECTION_GAP", 30)


# --- helpers de hora para esta vista ---
if "_auto_time_on_date" not in globals():

    def _auto_time_on_date():
        now = now_lima_trimmed()
        st.session_state["fi_t"] = now.time()


if "_sync_time_from_date" not in globals():

    def _sync_time_from_date():
        d = st.session_state.get("fi_d", None)
        if d is None:
            return
        try:
            d = pd.to_datetime(d).date()
        except Exception:
            return
        if d == now_lima_trimmed().date():
            st.session_state["fi_t"] = now_lima_trimmed().time()
            try:
                st.session_state["fi_t_view"] = st.session_state["fi_t"].strftime("%H:%M")
            except Exception:
                st.session_state["fi_t_view"] = str(st.session_state["fi_t"])


# ===== Helper imagen banner (base64) =====
def _hero_img_base64() -> str:
    """
    Carga ENI2025/assets/NUEVA_TAREA.png y la devuelve en base64.
    Si no la encuentra, devuelve '' (no rompe la app).
    """
    candidates = [
        os.path.join("assets", "NUEVA_TAREA.png"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "NUEVA_TAREA.png"),
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                with open(p, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            continue
    return ""


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

    /* ===== Banner superior tipo “Bienvenida” pero para NUEVA TAREA ===== */
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
      transform: translateY(10px);  /* ⬅️ Baja un poco la imagen dentro del banner */
    }

    /* ===== Tarjeta blanca SOLO para el formulario (filtros) ===== */
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel){
        background:#FFFFFF;
        border-radius:14px;
        padding:20px 22px 22px 22px;
        margin-top:16px;
        margin-bottom:10px;
        box-shadow:0 20px 50px rgba(15,23,42,0.10);
        border:1px solid #E5E7EB;

        /* 🔹 Mismo ancho horizontal que la cabecera */
        margin-left:8px;
        margin-right:24px;
        }

    /* Inputs full width dentro del card */
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea{
      width:100% !important;
    }
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextInput>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stSelectbox>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stDateInput>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTimeInput>div,
    div[data-testid="stVerticalBlock"]:has(> #nt-card-sentinel) .stTextArea>div{
      width:100% !important;
      max-width:none !important;
    }

    /* Pastilla “Nueva tarea” (ya no se usa visualmente, pero dejamos estilos por si acaso)
       .nt-pill{
         width:calc:100%;
         height:38px;
         border-radius:12px;
         display:flex;
         align-items:center;
         justify-content:center;
         background:#A7C8F0;
         color:#ffffff;
         font-weight:700;
         box-shadow:0 6px 14px rgba(167,200,240,.35);
         user-select:none;
       }

       div[data-testid="column"]:has(.nt-pill){
         flex: 1 1 100% !important;
         max-width: 100% !important;
       }

       div[data-testid="column"]:has(.nt-pill) ~ div[data-testid="column"]{
         display: none !important;
       }
    */

    /* Franja de indicaciones (ya no usada, pero dejamos el estilo por si la reutilizamos) */
    .help-strip{
      background:#FFFFFF;
      border:1px solid #E5E7EB;
      color:#0B3B76;
      padding:12px 14px;
      border-radius:14px;
      font-size:0.92rem;
      box-shadow:0 12px 30px rgba(15,23,42,0.06);
    }

    /* Tarjetas de pasos de indicaciones */
    .nt-steps-row{
      display:flex;
      flex-wrap:wrap;
      gap:12px;
      margin-top:4px;
      margin-bottom:16px;
    }

     /* Ocultar subtítulos de las tarjetas */
    .nt-step-text{
      display:none !important;
    }
    
    .nt-step-card{
      flex:1 1 180px;
      min-width:180px;
      background:#FFFFFF;
      border-radius:14px;
      border:1px solid #E5E7EB;
      padding:10px 14px;
      box-shadow:0 12px 30px rgba(15,23,42,0.04);
      
      display:flex;
      align-items:center;        /* ANTES: flex-start */
      justify-content:space-between; /* texto izq, icono der */
      gap:12px;
    }
    .nt-step-title{
      font-size:0.92rem;
      font-weight:400;           /* 👉 Sin negrita (antes 600) */
      color:#111827;
    }
    .nt-step-icon{
      width:32px;               
      height:32px;             
      border-radius:10px;
      display:flex;
      align-items:center;
      justify-content:center;
      background:#EEF2FF;
      font-size:1.8rem;          /* 👉 Icono más grande (antes 1.1rem) */
      flex-shrink:0;
    }
    .nt-step-text{
      font-size:0.80rem;
      color:#4B5563;
    }

    .nt-step-main{
      flex:1;
      display:flex;
      flex-direction:column;
      justify-content:center;
      align-items:flex-start;      /* izquierda */
      text-align:left;
    }

    /* Botones de abajo */
    .nt-outbtn .stButton>button{
      min-height:38px !important;
      height:38px !important;
      border-radius:10px !important;
    }
    .nt-outbtn{
      margin-top: 6px;
    }
    </style>
        """,
        unsafe_allow_html=True,
    )

    # ===== Datos =====
    if "AREAS_OPC" not in globals():
        globals()["AREAS_OPC"] = [
            "Jefatura",
            "Gestión",
            "Metodología",
            "Base de datos",
            "Capacitación",
            "Monitoreo",
            "Consistencia",
        ]
    st.session_state.setdefault("nt_visible", True)

    # Asegurar que "Tipo de tarea" no arranque con 'Otros' por cache previo
    if st.session_state.get("nt_tipo", "").strip().lower() == "otros":
        st.session_state["nt_tipo"] = ""
    else:
        st.session_state.setdefault("nt_tipo", "")

    _NT_SPACE = 20
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # anchos base
    A, Fw, T, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

    # ===== Banner superior “Nueva tarea” =====
    hero_b64 = _hero_img_base64()
    if hero_b64:
        hero_img_html = f'<img src="data:image/png;base64,{hero_b64}" alt="Nueva tarea" class="nt-hero-img">'
    else:
        hero_img_html = ""

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

    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True)

    if st.session_state.get("nt_visible", True):

        if st.session_state.pop("nt_added_ok", False):
            st.success("Agregado a Tareas recientes")

    # ===== Indicaciones en tarjetas (5 pasos con íconos) =====
    st.markdown(
        """
    <div class="nt-steps-row">
      <div class="nt-step-card">
        <div class="nt-step-main">
          <div class="nt-step-label">1. Completa los campos obligatorios</div>
          <div class="nt-step-icon-slot"><span class="nt-step-icon">✳️</span></div>
        </div>
      </div>

      <div class="nt-step-card">
        <div class="nt-step-main">
          <div class="nt-step-label">2. Pulsa “Agregar”</div>
          <div class="nt-step-icon-slot"><span class="nt-step-icon">➕</span></div>
        </div>
      </div>

      <div class="nt-step-card">
        <div class="nt-step-main">
          <div class="nt-step-label">3. Revisa en “Tareas recientes”</div>
          <div class="nt-step-icon-slot"><span class="nt-step-icon">🕑</span></div>
        </div>
      </div>

      <div class="nt-step-card">
        <div class="nt-step-main">
          <div class="nt-step-label">4. Grabar</div>
          <div class="nt-step-icon-slot"><span class="nt-step-icon">💾</span></div>
        </div>
      </div>

      <div class="nt-step-card">
        <div class="nt-step-main">
          <div class="nt-step-label">5. Subir a Sheets</div>
          <div class="nt-step-icon-slot"><span class="nt-step-icon">📤</span></div>
        </div>
      </div>

    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(f"<div style='height:{_NT_SPACE}px'></div>", unsafe_allow_html=True))

        # ===== Bloque de filtros / formulario (card blanco) =====
        with st.container(border=True):
            # sentinel solo para el CSS del card
            st.markdown(
                '<span id="nt-card-sentinel" style="display:none"></span>',
                unsafe_allow_html=True,
            )

            # ===== Responsable & Área desde ACL =====
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
            st.session_state["nt_area"] = area_fixed  # para el resto del flujo

            # ===== Fases =====
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

            # ---------- FILA 1 ----------
            if _is_fase_otros:
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r1c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
                r1c2.selectbox(
                    "Fase",
                    options=FASES,
                    key="nt_fase",
                    index=FASES.index("Otros"),
                )
                r1c3.text_input(
                    "Otros (especifique)",
                    key="nt_fase_otro",
                    placeholder="Describe la fase",
                )
                r1c4.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                r1c5.text_input(
                    "Detalle de tarea",
                    placeholder="Información adicional (opcional)",
                    key="nt_detalle",
                )
                r1c6.text_input("Responsable", key="nt_resp", disabled=True)
            else:
                r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r1c1.text_input("Área", value=area_fixed, key="nt_area_view", disabled=True)
                r1c2.selectbox(
                    "Fase",
                    options=FASES,
                    index=None,
                    placeholder="Selecciona una fase",
                    key="nt_fase",
                )
                r1c3.text_input("Tarea", placeholder="Describe la tarea", key="nt_tarea")
                r1c4.text_input(
                    "Detalle de tarea",
                    placeholder="Información adicional (opcional)",
                    key="nt_detalle",
                )
                r1c5.text_input("Responsable", key="nt_resp", disabled=True)
                r1c6.selectbox(
                    "Ciclo de mejora",
                    options=["1", "2", "3", "+4"],
                    index=0,
                    key="nt_ciclo_mejora",
                )

            # ---------- Fecha/Hora ----------
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
                if "df_main" in st.session_state
                else pd.DataFrame()
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

            # ---------- FILA 2 y FILA 3 ----------
            if _is_fase_otros:
                r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r2c1.selectbox(
                    "Ciclo de mejora",
                    options=["1", "2", "3", "+4"],
                    index=0,
                    key="nt_ciclo_mejora",
                )
                r2c2.text_input(
                    "Tipo de tarea",
                    key="nt_tipo",
                    placeholder="Escribe el tipo de tarea",
                )
                r2c3.text_input(
                    "Estado actual",
                    value="No iniciado",
                    disabled=True,
                    key="nt_estado_view",
                )
                r2c4.selectbox(
                    "Complejidad",
                    options=["🟢 Baja", "🟡 Media", "🔴 Alta"],
                    index=0,
                    key="nt_complejidad",
                )
                r2c5.selectbox(
                    "Duración",
                    options=[f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)],
                    index=0,
                    key="nt_duracion_label",
                )
                r2c6.date_input(
                    "Fecha de registro",
                    key="fi_d",
                    on_change=_auto_time_on_date,
                )
                _sync_time_from_date()

                r3c1, r3c2, _, _, _, _ = st.columns([A, Fw, T, D, R, C], gap="medium")
                r3c1.text_input(
                    "Hora de registro (auto)",
                    key="fi_t_view",
                    disabled=True,
                    help="Se asigna al elegir la fecha",
                )
                r3c2.text_input(
                    "ID asignado",
                    value=id_preview,
                    disabled=True,
                    key="nt_id_preview",
                )
            else:
                r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns([A, Fw, T, D, R, C], gap="medium")
                r2c1.text_input(
                    "Tipo de tarea",
                    key="nt_tipo",
                    placeholder="Escribe el tipo de tarea",
                )
                r2c2.text_input(
                    "Estado actual",
                    value="No iniciado",
                    disabled=True,
                    key="nt_estado_view",
                )
                r2c3.selectbox(
                    "Complejidad",
                    options=["🟢 Baja", "🟡 Media", "🔴 Alta"],
                    index=0,
                    key="nt_complejidad",
                )
                r2c4.selectbox(
                    "Duración",
                    options=[f"{i} día" if i == 1 else f"{i} días" for i in range(1, 6)],
                    index=0,
                    key="nt_duracion_label",
                )
                r2c5.date_input(
                    "Fecha de registro",
                    key="fi_d",
                    on_change=_auto_time_on_date,
                )
                _sync_time_from_date()
                r2c6.text_input(
                    "Hora de registro",
                    key="fi_t_view",
                    disabled=True,
                    help="Se asigna al elegir la fecha",
                )

                r3c1, _, _, _, _, _ = st.columns([A, Fw, T, D, R, C], gap="medium")
                r3c1.text_input(
                    "ID asignado",
                    value=id_preview,
                    disabled=True,
                    key="nt_id_preview",
                )

        # ---------- Botones: volver + agregar (misma altura) ----------
        left_spacer, col_back, col_add = st.columns(
            [A + Fw + T + D + R - C, C, C], gap="medium"
        )

        with col_back:
            st.markdown('<div class="nt-outbtn">', unsafe_allow_html=True)
            back = st.button(
                "⬅ Volver a Gestión de tareas",
                use_container_width=True,
                key="btn_volver_gestion",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col_add:
            st.markdown('<div class="nt-outbtn">', unsafe_allow_html=True)
            submitted = st.button(
                "➕ Agregar", use_container_width=True, key="btn_agregar"
            )
            st.markdown("</div>", unsafe_allow_html=True)

        # ------ Acción botón Volver ------
        if back:
            # limpiar selección de tarjeta y volver al home de Gestión de tareas
            st.session_state["home_tile"] = ""
            display_name = st.session_state.get("user_display_name", "Usuario")
            try:
                # dejamos solo auth y u en la URL (sin tile)
                st.experimental_set_query_params(auth="1", u=display_name)
            except Exception:
                pass
            st.rerun()

        # ------ Acción botón Agregar ------
        if submitted:
            try:
                df = st.session_state.get("df_main", pd.DataFrame()).copy()

                def _sanitize(df_in: pd.DataFrame, target_cols=None) -> pd.DataFrame:
                    df_out = df_in.copy()
                    if "DEL" in df_out.columns and "__DEL__" in df_out.columns:
                        df_out["__DEL__"] = df_out["__DEL__"].fillna(False) | df_out["DEL"].fillna(False)
                        df_out = df_out.drop(columns=["DEL"])
                    elif "DEL" in df_out.columns:
                        df_out = df_out.rename(columns={"DEL": "__DEL__"})
                    df_out = df_out.loc[:, ~pd.Index(df_out.columns).duplicated()].copy()
                    if not df_out.index.is_unique:
                        df_out = df_out.reset_index(drop=True)
                    if target_cols:
                        target = list(dict.fromkeys(list(target_cols)))
                        for c in target:
                            if c not in df_out.columns:
                                df_out[c] = None
                        ordered = [c for c in target] + [c for c in df_out.columns if c not in target]
                        df_out = df_out.loc[:, ordered].copy()
                    return df_out

                df = _sanitize(df, COLS if COLS is not None else None)

                reg_fecha = st.session_state.get("fi_d")
                reg_hora_obj = st.session_state.get("fi_t")
                try:
                    reg_hora_txt = (
                        reg_hora_obj.strftime("%H:%M") if reg_hora_obj is not None else ""
                    )
                except Exception:
                    reg_hora_txt = str(reg_hora_obj) if reg_hora_obj is not None else ""

                # Fase final:
                fase_sel = st.session_state.get("nt_fase", "")
                fase_otro = (st.session_state.get("nt_fase_otro", "") or "").strip()
                if str(fase_sel).strip() == "Otros":
                    fase_final = f"Otros — {fase_otro}" if fase_otro else "Otros"
                else:
                    fase_final = fase_sel

                base_row = blank_row()
                if not isinstance(base_row, dict):
                    base_row = {}

                new = dict(base_row)
                new.update(
                    {
                        "Área": st.session_state.get("nt_area", area_fixed),
                        "Id": next_id_by_person(
                            df,
                            st.session_state.get("nt_area", area_fixed),
                            st.session_state.get("nt_resp", ""),
                        ),
                        "Tarea": st.session_state.get("nt_tarea", ""),
                        "Tipo": st.session_state.get("nt_tipo", ""),
                        "Responsable": st.session_state.get("nt_resp", ""),
                        "Fase": fase_final,
                        "Estado": "No iniciado",
                        "Fecha de registro": reg_fecha,
                        "Hora de registro": reg_hora_txt,
                        "Fecha Registro": reg_fecha,
                        "Hora Registro": reg_hora_txt,
                        "Fecha inicio": None,
                        "Hora de inicio": "",
                        "Fecha Terminado": None,
                        "Hora Terminado": "",
                        "Ciclo de mejora": st.session_state.get("nt_ciclo_mejora", ""),
                        "Detalle": st.session_state.get("nt_detalle", ""),
                    }
                )

                if str(st.session_state.get("nt_tipo", "")).strip().lower() == "otros":
                    new["Complejidad"] = st.session_state.get("nt_complejidad", "")
                    lbl = st.session_state.get("nt_duracion_label", "")
                    try:
                        _dur = int(str(lbl).split()[0])
                    except Exception:
                        _dur = ""
                    new["Duración (días)"] = _dur
                    new["Duración"] = _dur

                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                df = _sanitize(df, COLS if COLS is not None else None)
                st.session_state["df_main"] = df.copy()

                # ======== Persistencia SOLO en Google Sheets (silenciosa) ========
                def _persist_to_sheets(df_rows: pd.DataFrame):
                    try:
                        ss_url, ws_name = _get_sheet_conf()
                        if upsert_rows_by_id is None or not ss_url:
                            return {"ok": False}
                        ids = (
                            df_rows["Id"].astype(str).tolist()
                            if "Id" in df_rows.columns
                            else []
                        )
                        res = upsert_rows_by_id(
                            ss_url=ss_url,
                            ws_name=ws_name,
                            df=df_rows,
                            ids=ids,
                        )
                        return res
                    except Exception:
                        return {"ok": False}

                df_rows = pd.DataFrame([new])
                try:
                    _ = _persist_to_sheets(df_rows.copy())
                except Exception:
                    pass

                # ====== Log universal en Tareas recientes (usando shared.log_reciente) ======
                sheet = None
                try:
                    url = st.secrets.get("gsheets_doc_url") or (
                        st.secrets.get("gsheets", {}) or {}
                    ).get("spreadsheet_url")
                    if url and callable(open_sheet_by_url):
                        try:
                            sheet = open_sheet_by_url(url)
                        except Exception:
                            sheet = None
                except Exception:
                    sheet = None

                try:
                    log_reciente_safe(
                        sheet,
                        tarea_nombre=new.get("Tarea", ""),
                        especialista=new.get("Responsable", ""),
                        detalle="Asignada",
                        id_val=new.get("Id", ""),
                        fecha_reg=reg_fecha,
                        hora_reg=reg_hora_txt,
                        area=new.get("Área", ""),
                        fase=new.get("Fase", ""),
                        tipo=new.get("Tipo", ""),
                        estado=new.get("Estado", ""),
                        ciclo_mejora=new.get("Ciclo de mejora", ""),
                        complejidad=new.get("Complejidad", ""),
                        duracion_dias=new.get("Duración (días)", ""),
                        duracion=new.get("Duración", ""),
                        link_archivo=new.get("Link de archivo", ""),
                    )
                except Exception:
                    pass

                # limpiar campos
                for k in [
                    "nt_area",
                    "nt_fase",
                    "nt_fase_otro",
                    "nt_tarea",
                    "nt_detalle",
                    "nt_resp",
                    "nt_ciclo_mejora",
                    "nt_tipo",
                    "nt_complejidad",
                    "nt_duracion_label",
                    "fi_d",
                    "fi_t",
                    "fi_t_view",
                    "nt_id_preview",
                ]:
                    st.session_state.pop(k, None)
                st.session_state["nt_skip_date_init"] = True
                st.session_state["nt_added_ok"] = True

                st.rerun()

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
    # Aseguramos que df_main esté inicializado antes de ambos bloques
    _bootstrap_df_main_hist()
    render_nueva_tarea(user=user)
    render_historial(user=user)
