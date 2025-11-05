# utils/gsheets.py
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
