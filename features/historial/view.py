# features/historial/view.py
from __future__ import annotations

import os, re
from io import BytesIO
from datetime import date
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

# 👇 Upsert centralizado (utils/gsheets)
try:
    from utils.gsheets import upsert_rows_by_id  # type: ignore
except Exception:
    upsert_rows_by_id = None  # fallback local más abajo

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

# ======== 🔁 Upsert por Id (fila a fila, sin clear) ========
def _a1_col(n: int) -> str:
    """1->A, 26->Z, 27->AA ..."""
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

def _sheet_upsert_by_id(df_rows: pd.DataFrame) -> dict:
    """
    Actualiza o inserta filas por Id en la pestaña configurada (sin borrar nada).
    df_rows: subconjunto con las filas a upsert (debe incluir 'Id').

    🔄 Ajuste solicitado: usa utils.gsheets.upsert_rows_by_id si está disponible.
    """
    if df_rows is None or df_rows.empty or "Id" not in df_rows.columns:
        return {"ok": False, "msg": "No hay filas con Id para actualizar."}

    # ⇨ Preferir helper centralizado
    if upsert_rows_by_id is not None:
        try:
            ss_url = (st.secrets.get("gsheets_doc_url")
                      or (st.secrets.get("gsheets",{}) or {}).get("spreadsheet_url")
                      or (st.secrets.get("sheets",{}) or {}).get("sheet_url"))
            ws_name = (st.secrets.get("gsheets",{}) or {}).get("worksheet","TareasRecientes")
            ids = df_rows["Id"].astype(str).tolist()
            return upsert_rows_by_id(ss_url=ss_url, ws_name=ws_name, df=df_rows, ids=ids)
        except Exception as e:
            return {"ok": False, "msg": f"Upsert falló: {e}"}

    # ⇨ Fallback local (por si no se pudo importar utils.gsheets)
    ss, ws_name = _gsheets_client()
    try:
        ws = ss.worksheet(ws_name)
    except Exception:
        # Crea hoja si no existe
        rows = str(max(1000, len(df_rows) + 10))
        cols = str(max(26, len(df_rows.columns) + 5))
        ws = ss.add_worksheet(title=ws_name, rows=rows, cols=cols)

    headers = ws.row_values(1)
    if not headers:
        headers = list(df_rows.columns)

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

    col_letter = _a1_col(id_col_idx)
    existing_ids_col = ws.col_values(id_col_idx)
    id_to_row = {}
    for i, v in enumerate(existing_ids_col[1:], start=2):
        if v:
            id_to_row[str(v).strip()] = i

    last_col_letter = _a1_col(len(headers))
    updates = []
    appends = []

    df_rows = df_rows.copy()
    df_rows["Id"] = df_rows["Id"].astype(str)

    for _, row in df_rows.iterrows():
        rid = str(row.get("Id", "")).strip()
        if not rid:
            continue
        row_values = _format_outgoing_row(row, headers)
        if rid in id_to_row:
            r = id_to_row[rid]
            rng = f"A{r}:{last_col_letter}{r}"
            updates.append((rng, [row_values]))
        else:
            appends.append(row_values)

    for rng, vals in updates:
        ws.update(rng, vals, value_input_option="USER_ENTERED")

    if appends:
        ws.append_rows(appends, value_input_option="USER_ENTERED")

    total = len(updates) + len(appends)
    return {"ok": True, "msg": f"Upsert completado (fallback): {total} fila(s) actualizada(s)/insertada(s)."}

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
    out = pd.Series(pd.NaT, index=start_dates.index, dtype="datetime64[ns]")
    if ok.any():
        a = np.array(sd[ok], dtype="datetime64[D]"])
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
    <style>
      :root{
        --pill-salmon:#F28B85;
        --card-border:#E5E7EB;
        --card-bg:#FFFFFF;
        --hint-bg:#FFE7E3;
        --hint-border:#F28B85;
      }
      .hist-card{ border:0 !important; background:transparent !important; border-radius:0 !important; padding:0 !important; margin:0 0 8px 0 !important; }
      .hist-title-pill{ display:inline-flex; align-items:center; gap:8px; padding:10px 16px; border-radius:10px; background: var(--pill-salmon); color:#fff; font-weight:600; font-size:1.05rem; line-height:1.1; box-shadow: inset 0 -2px 0 rgba(0,0,0,0.06); margin-bottom:10px; }
      .hist-hint{ background:var(--hint-bg); border:2px dotted var(--hint-border); border-radius:10px; padding:10px 12px; color:#7F1D1D; margin: 2px 0 12px 0; font-size:0.95rem; }
      .hist-hint + div[data-testid="stTextInput"]{ display:none !important; }
      .hist-hint + div:has(> div[data-testid="stTextInput"]){ display:none !important; }
      .hist-hint + div:has(input[type="text"]){ display:none !important; }
      .hist-search .stButton>button{ margin-top:8px; }
      .ag-theme-balham .ag-cell{ white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; }
      .ag-theme-balham .ag-header-cell-label{ white-space: nowrap !important; line-height: 1.1 !important; overflow: visible !important; text-overflow: clip !important; }
      .ag-theme-balham .ag-header .ag-icon, .ag-theme-balham .ag-header-cell .ag-icon, .ag-theme-balham .ag-header-cell-menu-button, .ag-theme-balham .ag-floating-filter, .ag-theme-balham .ag-header-row.ag-header-row-column-filter { display: none !important; }
    </style>
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

    # ===== Píldora arriba =====
    st.markdown('<div class="hist-title-pill">📝 Tareas recientes</div>', unsafe_allow_html=True)

    # ===== Indicaciones =====
    st.markdown(
        '<div class="hist-hint">Aquí puedes editar <b>Tarea</b> y <b>Detalle de tarea</b>. '
        'Opcional: descargar en Excel. <b>Obligatorio:</b> Grabar y después Subir a Sheets.</div>',
        unsafe_allow_html=True
    )

    # ===== Filtros =====
    st.markdown('<div class="hist-card">', unsafe_allow_html=True)

    # 👉 ALCANCE por usuario (ACL)
    df_all = st.session_state["df_main"].copy()
    df_scope = apply_scope(df_all.copy(), user=user)  # Vivi/Enrique ven todo; resto solo lo suyo

    with st.container():
        c1, c2, c3, c4, c5, c6 = st.columns([1.05, 1.10, 1.70, 1.05, 1.05, 0.90], gap="medium")
        with c1:
            area_sel = st.selectbox(
                "Área",
                options=["Todas"] + st.session_state.get(
                    "AREAS_OPC",
                    ["Jefatura","Gestión","Metodología","Base de datos","Monitoreo","Capacitación","Consistencia"]
                ),
                index=0, key="hist_area"
            )

        fases_all = sorted([x for x in df_scope.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x!="nan"])
        with c2:
            fase_sel = st.selectbox("Fase", options=["Todas"]+fases_all, index=0, key="hist_fase")

        df_resp_src = df_scope.copy()
        if area_sel!="Todas":
            df_resp_src = df_resp_src[df_resp_src.get("Área","").astype(str)==area_sel]
        if fase_sel!="Todas" and "Fase" in df_resp_src.columns:
            df_resp_src = df_resp_src[df_resp_src["Fase"].astype(str)==fase_sel]
        responsables = sorted([x for x in df_resp_src.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x!="nan"])
        with c3:
            resp_multi = st.multiselect("Responsable", options=responsables, default=[], key="hist_resp",
                                        placeholder="Selecciona responsable(s)")
        today = date.today()
        with c4:
            f_desde = st.date_input("Desde", value=today, key="hist_desde")
        with c5:
            f_hasta = st.date_input("Hasta", value=today, key="hist_hasta")
        with c6:
            st.markdown('<div class="hist-search">', unsafe_allow_html=True)
            hist_do_buscar = st.button("🔍 Buscar", use_container_width=True, key="hist_btn_buscar")
            st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    show_deleted = st.toggle("Mostrar eliminadas (tachadas)", value=True, key="hist_show_deleted")

    # ---- Aplicar filtros ----
    df_view = df_scope.copy()
    df_view = _canonicalize_link_column(df_view)
    if "Fecha inicio" in df_view.columns:
        df_view["Fecha inicio"] = to_naive_local_series(df_view["Fecha inicio"])
    if hist_do_buscar:
        if area_sel!="Todas":
            df_view = df_view[df_view.get("Área","").astype(str)==area_sel]
        if fase_sel!="Todas" and "Fase" in df_view.columns:
            df_view = df_view[df_view["Fase"].astype(str)==fase_sel]
        if resp_multi:
            df_view = df_view[df_view["Responsable"].astype(str).isin(resp_multi)]
        if f_desde is not None and "Fecha inicio" in df_view.columns:
            df_view = df_view[df_view["Fecha inicio"].dt.date >= f_desde]
        if f_hasta is not None and "Fecha inicio" in df_view.columns:
            df_view = df_view[df_view["Fecha inicio"].dt.date <= f_hasta]
    if not show_deleted and "Estado" in df_view.columns:
        df_view = df_view[df_view["Estado"].astype(str).str.strip()!="Eliminado"]

    # ===== Normalizaciones mínimas =====
    for need in ["Estado","Hora de inicio","Fecha Terminado","Hora Terminado"]:
        if need not in df_view.columns:
            df_view[need] = "" if "Hora" in need else pd.NaT

    # ===== GRID =====
    target_cols = [
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
        _LINK_CANON,
        "Link de descarga"
    ]
    hidden_cols = [
        "Archivo","__ts__","__SEL__","__DEL__","¿Eliminar?","Tipo de alerta",
        "Fecha estado modificado","Hora estado modificado","Fecha estado actual","Hora estado actual",
        "Fecha","Hora","Vencimiento"
    ]

    for c in target_cols:
        if c not in df_view.columns:
            df_view[c] = ""

    df_grid = df_view.reindex(
        columns=list(dict.fromkeys(target_cols)) + [c for c in df_view.columns if c not in target_cols + hidden_cols]
    ).copy()
    df_grid = df_grid.loc[:, ~df_grid.columns.duplicated()].copy()

    # --- Quitar columnas duplicadas por nombre “normalizado” ---
    import unicodedata, re as _re
    def _normcol_hist(x: str) -> str:
        s = unicodedata.normalize('NFD', str(x))
        s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
        return _re.sub(r'\s+', ' ', s).strip().lower()

    _seen = set(); _keep = []
    for _c in df_grid.columns:
        _k = _normcol_hist(_c)
        if _k not in _seen:
            _seen.add(_k); _keep.append(_c)
    df_grid = df_grid[_keep]
    # --- fin ajuste general ---

    # 🔧 Forzar una sola “Duración”
    def _norm_match_key(name: str) -> str:
        s = _normcol_hist(name)
        s = _re.sub(r'[^a-z0-9]', '', s)
        return s
    def _is_duracion_like(name: str) -> bool:
        n = _norm_match_key(name)
        return (n == "duracion" or n == "duraicon" or n.startswith("duracion"))
    dur_like_cols = [c for c in df_grid.columns if _is_duracion_like(c)]
    if len(dur_like_cols) > 1:
        keep_col = next((c for c in dur_like_cols if c.strip() == "Duración"), dur_like_cols[0])
        drop_cols = [c for c in dur_like_cols if c != keep_col]
        df_grid.drop(columns=drop_cols, inplace=True, errors="ignore")

    df_grid["Id"] = df_grid["Id"].astype(str).fillna("")
    if "Link de descarga" not in df_grid.columns:
        df_grid["Link de descarga"] = ""

    # --- Dedup/renombre de N° alerta ---
    alerta_pat = re.compile(r"^\s*n[°º]?\s*(de\s*)?alerta\s*$", re.I)
    alerta_cols = [c for c in df_grid.columns if alerta_pat.match(str(c))]
    if alerta_cols:
        first = alerta_cols[0]
        if first != "N° alerta":
            df_grid.rename(columns={first: "N° alerta"}, inplace=True)
        for c in alerta_cols[1:]:
            df_grid.drop(columns=c, inplace=True, errors="ignore")

    # === Ajuste 1: Sí/No ===
    for bcol in ["¿Generó alerta?","¿Se corrigió?"]:
        if bcol in df_grid.columns:
            df_grid[bcol] = df_grid[bcol].map(_yesno)

    # === Ajuste 2: Calificación = 0 por defecto ===
    if "Calificación" in df_grid.columns:
        df_grid["Calificación"] = pd.to_numeric(df_grid["Calificación"], errors="coerce").fillna(0)

    # === Ajuste 3: Duración válida + Fecha Vencimiento (días hábiles) ===
    if "Duración" in df_grid.columns:
        dur_num = pd.to_numeric(df_grid["Duración"], errors="coerce")
        ok = dur_num.where(dur_num.between(1,5))
        df_grid["Duración"] = ok.where(ok.between(1,5)).fillna("").astype(object)

        if "Fecha inicio" in df_grid.columns:
            fi = to_naive_local_series(df_grid.get("Fecha inicio", pd.Series([], dtype=object)))
            fv_calc = _add_business_days(fi, ok.fillna(0))
            mask_set = ~fv_calc.isna()
            if "Fecha Vencimiento" not in df_grid.columns:
                df_grid["Fecha Vencimiento"] = pd.NaT
            df_grid.loc[mask_set, "Fecha Vencimiento"] = fv_calc.loc[mask_set]

    # === Ajuste 4: Hora límite por defecto 17:00 ===
    if "Hora Vencimiento" in df_grid.columns:
        hv = df_grid["Hora Vencimiento"].apply(_fmt_hhmm).astype(str)
        df_grid["Hora Vencimiento"] = hv.mask(hv.str.strip()=="", "17:00")

    # === Ajuste 5: Cumplimiento automático ===
    if "Cumplimiento" in df_grid.columns:
        fv = to_naive_local_series(df_grid.get("Fecha Vencimiento", pd.Series([], dtype=object)))
        ft = to_naive_local_series(df_grid.get("Fecha Terminado", pd.Series([], dtype=object)))
        today_ts = pd.Timestamp(date.today())
        fv_n = fv.dt.normalize()
        ft_n = ft.dt.normalize()

        has_fv = ~fv_n.isna()
        has_ft = ~ft_n.isna()

        delivered_on_time = has_fv & has_ft & (ft_n <= fv_n)
        delivered_late    = has_fv & has_ft & (ft_n >  fv_n)

        days_left = (fv_n - today_ts).dt.days
        no_delivered = has_fv & (~has_ft) & (days_left < 0)
        risk         = has_fv & (~has_ft) & (days_left >= 1) & (days_left <= 2)

        out = pd.Series("", index=df_grid.index, dtype="object")
        out[delivered_on_time] = "✅ Entregado a tiempo"
        out[delivered_late]    = "⏰ Entregado fuera de tiempo"
        out[no_delivered]      = "❌ No entregado"
        out[risk]              = "⚠️ En riesgo de retrasos"
        df_grid["Cumplimiento"] = out

    # ======= Snapshot para detectar cambios en grilla (Tarea/Detalle) =======
    try:
        st.session_state["_hist_prev"] = df_grid[["Id","Tarea","Detalle"]].copy()
    except Exception:
        st.session_state["_hist_prev"] = pd.DataFrame(columns=["Id","Tarea","Detalle"])

    # ==== Opciones AG Grid ====
    gob = GridOptionsBuilder.from_dataframe(df_grid)
    gob.configure_default_column(
        resizable=True, editable=False, filter=False, floatingFilter=False,
        sortable=False, suppressMenu=True, wrapText=False, autoHeight=False,
        cellStyle={"white-space":"nowrap","overflow":"hidden","textOverflow":"ellipsis"}
    )

    width_map = {
        "Id": 90, "Área": 140, "Fase": 180, "Responsable": 220,
        "Tarea": 280, "Detalle": 360, "Detalle de tarea": 360,
        "Tipo": 140, "Ciclo de mejora": 150, "Complejidad": 140, "Prioridad": 130,
        "Estado": 150, "Duración": 120,
        "Fecha Registro": 150, "Hora Registro": 130,
        "Fecha inicio": 150, "Hora de inicio": 130,
        "Fecha Vencimiento": 150, "Hora Vencimiento": 130,
        "Fecha Terminado": 150, "Hora Terminado": 130,
        "¿Generó alerta?": 160, "N° alerta": 130,
        "Fecha de detección": 170, "Hora de detección": 150,
        "¿Se corrigió?": 140, "Fecha de corrección": 170, "Hora de corrección": 150,
        "Cumplimiento": 200, "Evaluación": 150, "Calificación": 140,
        "Fecha Pausado": 150, "Hora Pausado": 130,
        "Fecha Cancelado": 150, "Hora Cancelado": 130,
        "Fecha Eliminado": 150, "Hora Eliminado": 130,
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
    }

    for col in df_grid.columns:
        nice = header_map.get(col, col)
        gob.configure_column(
            col,
            headerName=nice,
            minWidth=width_map.get(nice, width_map.get(col, 120)),
            editable=(col in ["Tarea", "Detalle"]),
            suppressMenu=True,
            filter=False, floatingFilter=False, sortable=False
        )

    # Ocultamos "Link de archivo" pero disponible
    gob.configure_column(_LINK_CANON, hide=True)

    # Formato fecha (dd/mm/aaaa)
    date_only_fmt = JsCode(r"""
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
    }""")
    for col in ["Fecha Registro","Fecha inicio","Fecha Vencimiento","Fecha Terminado",
                "Fecha Pausado","Fecha Cancelado","Fecha Eliminado",
                "Fecha de detección","Fecha de corrección"]:
        if col in df_grid.columns:
            gob.configure_column(col, valueFormatter=date_only_fmt)

    # Link de descarga (lee SOLO de "Link de archivo")
    link_value_getter = JsCode(r"""
    function(p){
      const text = String((p && p.data && p.data['Link de archivo']) || '').trim();
      if(!text) return '';
      const m = text.match(/https?:\/\/\S+/i);
      return m ? m[0].replace(/[),.]+$/, '') : '';
    }""")
    link_renderer = JsCode(r"""
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
    }""")
    gob.configure_column("Link de descarga",
                         valueGetter=link_value_getter,
                         cellRenderer=link_renderer,
                         tooltipField="Link de descarga",
                         minWidth=width_map["Link de descarga"],
                         flex=1)

    # Cumplimiento: estilos por estado
    cumplimiento_style = JsCode(r"""
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
    }""")
    gob.configure_column("Cumplimiento", cellStyle=cumplimiento_style)

    # Sin menú/filtro en "Fecha inicio"
    gob.configure_column("Fecha inicio", filter=False, floatingFilter=False, sortable=False, suppressMenu=True)

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
        update_mode=(GridUpdateMode.MODEL_CHANGED
                     | GridUpdateMode.FILTERING_CHANGED
                     | GridUpdateMode.SORTING_CHANGED
                     | GridUpdateMode.VALUE_CHANGED),
        allow_unsafe_jscode=True,
    )

    # ===== Detectar cambios y persistir local =====
    try:
        edited = grid_resp["data"]
        new_df = None
        if isinstance(edited, list):
            new_df = pd.DataFrame(edited)
        elif hasattr(grid_resp, "data"):
            new_df = pd.DataFrame(grid_resp.data)

        # Calcula changed_ids comparando snapshot previo vs grilla actual (solo Tarea/Detalle)
        changed_ids = set()
        try:
            prev = st.session_state.get("_hist_prev")
            if isinstance(prev, pd.DataFrame) and new_df is not None:
                ccols = ["Id","Tarea","Detalle"]
                a = prev.reindex(columns=ccols).copy()
                b = new_df.reindex(columns=ccols).copy()
                a["Id"] = a["Id"].astype(str)
                b["Id"] = b["Id"].astype(str)
                prev_map = a.set_index("Id")
                curr_map = b.set_index("Id")
                common = prev_map.index.intersection(curr_map.index)
                if len(common):
                    dif_mask = (prev_map.loc[common, ["Tarea","Detalle"]].fillna("").astype(str)
                                .ne(curr_map.loc[common, ["Tarea","Detalle"]].fillna("").astype(str))).any(axis=1)
                    changed_ids.update(common[dif_mask].tolist())
                # nuevos Ids visibles en grilla
                new_only = [iid for iid in curr_map.index if iid not in prev_map.index and iid]
                changed_ids.update(new_only)
        except Exception:
            pass
        st.session_state["_hist_changed_ids"] = sorted(changed_ids)

        # Merge edición en df_main y guarda local
        if new_df is not None:
            base = st.session_state.get("df_main", pd.DataFrame()).copy()
            base = _canonicalize_link_column(base)
            new_df = _canonicalize_link_column(new_df)
            if ("Id" in base.columns) and ("Id" in new_df.columns):
                base["Id"] = base["Id"].astype(str)
                new_df["Id"] = new_df["Id"].astype(str)
                base_idx = base.set_index("Id")
                new_idx  = new_df.set_index("Id")
                cols_to_update = [c for c in new_idx.columns if c in base_idx.columns]
                base_idx.update(new_idx[cols_to_update])
                st.session_state["df_main"] = base_idx.reset_index()
            else:
                st.session_state["df_main"] = new_df
            try:
                _save_local(st.session_state["df_main"].copy())
            except Exception:
                pass
    except Exception:
        pass

    # ===== Botonera =====
    st.markdown('<div style="padding:0 16px; border-top:2px solid #EF4444">', unsafe_allow_html=True)
    _sp, b_xlsx, b_sync, b_save_local, b_save_sheets = st.columns([4.9, 1.6, 1.4, 1.4, 2.2], gap="medium")

    with b_xlsx:
        try:
            base = st.session_state["df_main"].copy()
            for c in ["__SEL__","__DEL__","¿Eliminar?"]:
                if c in base.columns:
                    base.drop(columns=[c], inplace=True, errors="ignore")
            xlsx_b = export_excel(base, sheet_name=TAB_NAME)
            st.download_button(
                "⬇️ Exportar Excel",
                data=xlsx_b,
                file_name="tareas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.warning(f"No pude generar Excel: {e}")

    with b_sync:
        if st.button("🔄 Sincronizar", use_container_width=True, key="btn_sync_sheet"):
            try:
                pull_user_slice_from_sheet(replace_df_main=False)  # merge por Id
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
                ids = st.session_state.get("_hist_changed_ids", [])
                if not ids:
                    st.info("No hay cambios detectados en la grilla para enviar.")
                else:
                    # Subconjunto por Id desde la base completa (no solo la vista)
                    base_full = st.session_state.get("df_main", pd.DataFrame()).copy()
                    base_full["Id"] = base_full.get("Id","").astype(str)
                    df_rows = base_full[base_full["Id"].isin(ids)].copy()
                    res = _sheet_upsert_by_id(df_rows)
                    if res.get("ok"):
                        st.success(res.get("msg","Actualizado."))
                    else:
                        st.warning(res.get("msg","No se pudo actualizar."))
            except Exception as e:
                st.warning(f"No se pudo subir a Sheets: {e}")

    st.markdown('</div>', unsafe_allow_html=True)
