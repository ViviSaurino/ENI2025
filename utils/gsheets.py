# utils/gsheets.py
import re
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import streamlit as st

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _get_client():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    return gspread.authorize(creds)

def open_sheet_by_url(url: str):
    gc = _get_client()
    return gc.open_by_url(url)

def read_df_from_worksheet(sh, ws_name: str) -> pd.DataFrame:
    try:
        ws = sh.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        return pd.DataFrame()
    recs = ws.get_all_records(numericise_ignore=["all"])
    return pd.DataFrame.from_records(recs) if recs else pd.DataFrame()

def write_df_full(sh, ws_name: str, df: pd.DataFrame):
    """Reescribe toda la pestaña (úsalo solo si lo necesitas)."""
    try:
        try:
            ws = sh.worksheet(ws_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=ws_name, rows="100", cols="26")
        ws.clear()
        set_with_dataframe(ws, df if df is not None else pd.DataFrame())
        return {"ok": True, "msg": "Escritura completada"}
    except Exception as e:
        return {"ok": False, "msg": f"Error al escribir: {e}"}

def upsert_by_id(sh, ws_name: str, df_user: pd.DataFrame, id_col: str = "Id"):
    """
    Lee la pestaña, hace upsert por 'Id' SOLO con las filas del usuario (df_user),
    y vuelve a escribir TODO (merge seguro para equipos pequeños).
    """
    try:
        base = read_df_from_worksheet(sh, ws_name)
        if base.empty:
            merged = df_user.copy()
        else:
            base = base.copy()
            # limpia duplicados de Id en base
            if id_col in base.columns:
                base = base.drop_duplicates(subset=[id_col], keep="last")

            # registros a actualizar (Ids que ya existen)
            if id_col in df_user.columns:
                common_ids = set(base[id_col]) & set(df_user[id_col])
                mask_update = base[id_col].isin(common_ids)
                # quita los que se actualizarán
                base_rest = base.loc[~mask_update].copy()
                # concatena el resto + versiones nuevas/actualizadas del usuario
                merged = pd.concat([base_rest, df_user], ignore_index=True)
            else:
                # si por algo df_user no trae Id, solo apéndalo
                merged = pd.concat([base, df_user], ignore_index=True)

        # Orden cronológico si existen estas columnas
        for c in ["Fecha Registro", "Fecha", "Hora Registro", "Hora"]:
            if c in merged.columns:
                # intenta convertir fechas/horas
                if "Fecha" in c:
                    merged[c] = pd.to_datetime(merged[c], errors="coerce").dt.date
                else:
                    merged[c] = merged[c].astype(str)

        # Escribe todo (sencillo y robusto para 1 hoja central)
        return write_df_full(sh, ws_name, merged)

    except Exception as e:
        return {"ok": False, "msg": f"Upsert falló: {e}"}

# ============================================================
#         NUEVO: Upsert por Id en lote, sin borrar nada
#         (para reutilizar desde Historial u otras vistas)
# ============================================================

def _a1_col(n: int) -> str:
    """Convierte índice 1-based a letra A1 (1->A, 26->Z, 27->AA)."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def _fmt_hhmm(value) -> str:
    """Normaliza hora a HH:MM; tolerante a strings y datetimes."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none", "null"}:
        return ""
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    try:
        d = pd.to_datetime(s, errors="coerce", utc=False)
        if pd.isna(d):
            return ""
        return f"{int(d.hour):02d}:{int(d.minute):02d}"
    except Exception:
        return ""

def _format_row_for_headers(row: pd.Series, headers: list[str]) -> list[str]:
    """Devuelve la fila alineada a headers, formateando Fecha*/Hora*."""
    out = []
    for c in headers:
        v = row.get(c, "")
        low = str(c).lower()
        if low.startswith("fecha"):
            ser = pd.to_datetime(pd.Series([v]), errors="coerce")
            x = ser.iloc[0]
            out.append("" if pd.isna(x) else pd.Timestamp(x).strftime("%Y-%m-%d"))
        elif low.startswith("hora"):
            out.append(_fmt_hhmm(v))
        else:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                out.append("")
            else:
                out.append(str(v))
    return out

def _ensure_worksheet(ss, ws_name: str, rows: int = 1000, cols: int = 26):
    """Abre o crea la pestaña."""
    try:
        ws = ss.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=ws_name, rows=str(rows), cols=str(cols))
    return ws

def _ensure_headers(ws, desired_headers: list[str]) -> list[str]:
    """
    Lee headers actuales y devuelve la lista final.
    Si faltan columnas de desired_headers, las agrega al final y actualiza A1.
    """
    headers = ws.row_values(1)
    if not headers:
        headers = list(desired_headers)
        ws.update("A1", [headers])
        return headers

    missing = [c for c in desired_headers if c not in headers]
    if missing:
        headers = headers + missing
        ws.update("A1", [headers])
    return headers

def upsert_rows_by_id(
    ss_url: str,
    ws_name: str,
    df: pd.DataFrame,
    ids: list[str] | set[str] | None,
    id_col: str = "Id",
) -> dict:
    """
    Upsert SOLO las filas con Id ∈ ids (o todas si ids=None) en la pestaña ws_name del spreadsheet ss_url,
    sin borrar datos de otros usuarios. Usa batch update por rangos.

    Retorna: {"ok": True/False, "updated": n, "inserted": m, "msg": str}
    """
    try:
        if df is None or df.empty:
            return {"ok": False, "updated": 0, "inserted": 0, "msg": "DataFrame vacío."}
        if id_col not in df.columns:
            return {"ok": False, "updated": 0, "inserted": 0, "msg": f"Falta columna '{id_col}'."}

        # Filtra por ids si se pasan
        df2 = df.copy()
        df2[id_col] = df2[id_col].astype(str).str.strip()
        if ids is not None:
            ids_norm = {str(x).strip() for x in ids if str(x).strip()}
            df2 = df2[df2[id_col].isin(ids_norm)].copy()
            if df2.empty:
                return {"ok": True, "updated": 0, "inserted": 0, "msg": "No hay Ids para actualizar."}

        # Abre SS/WS
        ss = open_sheet_by_url(ss_url)
        ws = _ensure_worksheet(ss, ws_name)

        # Headers: asegúrate de incluir todas las columnas presentes en df2
        desired_headers = list(df2.columns)
        if "Id" in desired_headers:
            # prioriza 'Id' como primera columna si no lo es
            desired_headers = ["Id"] + [c for c in desired_headers if c != "Id"]
        headers = _ensure_headers(ws, desired_headers)

        # Índice de columna 'Id'
        try:
            id_col_idx = headers.index(id_col) + 1
        except ValueError:
            # Si por alguna razón no existía, fuerza a que sea la primera
            headers = [id_col] + [c for c in headers if c != id_col]
            ws.update("A1", [headers])
            id_col_idx = 1

        last_col_letter = _a1_col(len(headers))

        # Mapa Id->número de fila existente (lee solo la columna Id)
        existing_ids_col = ws.col_values(id_col_idx)
        id_to_row = {}
        # existing_ids_col[0] es el header
        for i, v in enumerate(existing_ids_col[1:], start=2):
            if v:
                id_to_row[str(v).strip()] = i

        # Prepara updates/append
        update_data_ranges = []  # para values_batch_update
        appends = []
        df2 = df2.reindex(columns=headers).copy()  # garantiza orden de columnas
        for _, row in df2.iterrows():
            rid = str(row.get(id_col, "")).strip()
            if not rid:
                continue
            row_vals = _format_row_for_headers(row, headers)
            if rid in id_to_row:
                r = id_to_row[rid]
                rng = f"{ws_name}!A{r}:{last_col_letter}{r}"
                update_data_ranges.append({"range": rng, "values": [row_vals]})
            else:
                appends.append(row_vals)

        # Ejecuta batch update (updates)
        updated = 0
        if update_data_ranges:
            body = {
                "valueInputOption": "USER_ENTERED",
                "data": update_data_ranges,
            }
            ss.values_batch_update(body)
            updated = len(update_data_ranges)

        # Ejecuta appends
        inserted = 0
        if appends:
            ws.append_rows(appends, value_input_option="USER_ENTERED")
            inserted = len(appends)

        return {
            "ok": True,
            "updated": updated,
            "inserted": inserted,
            "msg": f"Upsert completado: {updated} actualizada(s), {inserted} insertada(s).",
        }

    except Exception as e:
        return {"ok": False, "updated": 0, "inserted": 0, "msg": f"Error en upsert_rows_by_id: {e}"}
