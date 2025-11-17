# features/editar_estado/view.py
from __future__ import annotations
import os
import re
import random
import pandas as pd
import streamlit as st
from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    DataReturnMode,
    JsCode,
)

# ======= Toggle: Upsert a Google Sheets (AHORA True por defecto si hay secrets) =======
DO_SHEETS_UPSERT = bool(st.secrets.get("edit_estado_upsert_to_sheets", True))

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
            return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        d = pd.to_datetime(s, errors="coerce", utc=False)
        if pd.isna(d):
            return ""
        return f"{int(d.hour):02d}:{int(d.minute):02d}"
    except Exception:
        return ""

# ============ Helpers de normalización y deduplicado ============
def _is_blank_str(x) -> bool:
    s = str(x).strip().lower()
    return s in {"", "-", "nan", "nat", "none", "null"}

def _canon_str(x) -> str:
    return "" if _is_blank_str(x) else str(x).strip()

def _dedup_keep_last_with_id(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra filas sin Id y quita duplicados por Id (conserva la última)."""
    if df is None or df.empty or "Id" not in df.columns:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    out["Id"] = out["Id"].astype(str).str.strip()
    mask_valid = ~out["Id"].str.lower().isin({"", "-", "nan", "none", "null"})
    out = out[mask_valid]
    out = out[~out["Id"].duplicated(keep="last")]
    return out

# ============== Helpers ACL ==============
def _display_name() -> str:
    u = st.session_state.get("acl_user", {}) or {}
    return (
        u.get("display")
        or st.session_state.get("user_display_name", "")
        or u.get("name", "")
        or (st.session_state.get("user") or {}).get("name", "")
        or ""
    )

def _user_email() -> str:
    u = st.session_state.get("acl_user", {}) or {}
    return (
        (u.get("email") or "").strip()
        or ((st.session_state.get("user") or {}).get("email") or "").strip()
    )

def _is_super_editor() -> bool:
    u = st.session_state.get("acl_user", {}) or {}
    flag = str(u.get("can_edit_all", "")).strip().lower()
    if flag in {"1", "true", "yes", "si", "sí"}:
        return True
    dn = _display_name().strip().lower()
    return dn.startswith("vivi") or dn.startswith("enrique")

def _gen_id() -> str:
    # yyyyMMddHHmmssSSS + 4 chars robustos
    from datetime import datetime, timedelta
    now = datetime.now(_TZ) if _TZ else (datetime.utcnow() - timedelta(hours=5))
    ts = now.strftime("%Y%m%d%H%M%S%f")[:-3]
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    rand4 = "".join(random.choice(alphabet) for _ in range(4))
    return f"{ts}-{rand4}"

# --- I/O local robusto (para persistencia entre sesiones) ---
def _load_local_if_exists() -> pd.DataFrame | None:
    try:
        p = os.path.join("data", "tareas.csv")
        if os.path.exists(p):
            df = pd.read_csv(p, dtype=str, keep_default_na=False).fillna("")
            return df
    except Exception:
        pass
    return None

def _save_local(df: pd.DataFrame) -> dict:
    try:
        os.makedirs("data", exist_ok=True)
        # escritura atómica simple
        tmp = os.path.join("data", "_tareas.tmp.csv")
        df.to_csv(tmp, index=False, encoding="utf-8-sig")
        os.replace(tmp, os.path.join("data", "tareas.csv"))
        return {"ok": True, "msg": "Cambios guardados."}
    except Exception as _e:
        return {"ok": False, "msg": f"Error al guardar: {_e}"}

# --- Upsert a Sheets usando helper de shared.py (sin _gsheets_client local) ---
try:
    # Helper genérico de upsert parcial por Id centralizado en shared.py
    from shared import sheet_upsert_by_id_partial as _shared_upsert_by_id_partial  # type: ignore
except Exception:
    _shared_upsert_by_id_partial = None  # fallback a no-op si no está disponible

def _sheet_upsert_estado_by_id(df_base: pd.DataFrame, changed_ids: list[str]):
    """
    Empuja SOLO las columnas de estado/fechas relevantes para los Id cambiados,
    usando el helper _shared_upsert_by_id_partial de shared.py.
    No define cliente local de Sheets.
    """
    if not DO_SHEETS_UPSERT or _shared_upsert_by_id_partial is None:
        return

    try:
        if df_base is None or df_base.empty or "Id" not in df_base.columns:
            return
        df_base = _dedup_keep_last_with_id(df_base.copy())
        if df_base.empty:
            return

        push_cols_base = [
            "Estado", "Estado actual",
            "Fecha estado actual", "Hora estado actual",
            "Fecha inicio", "Hora de inicio",
            "Fecha de inicio",
            "Fecha Terminado", "Hora Terminado",
            "Fecha terminada", "Hora terminada",
            "Fecha eliminada", "Hora eliminada",
            "Fecha cancelada", "Hora cancelada",
            "Fecha pausada", "Hora pausada",
            "Link de archivo",
            "Responsable", "OwnerEmail",
        ]

        ids_set = {str(x).strip() for x in (changed_ids or []) if str(x).strip()}
        if not ids_set:
            return

        df_rows = df_base[df_base["Id"].astype(str).isin(ids_set)].copy()
        keep_cols = ["Id"] + [c for c in push_cols_base if c in df_rows.columns]
        if not keep_cols:
            return
        df_rows = df_rows.reindex(columns=keep_cols)

        # Actualizamos todas las columnas elegibles para cada Id cambiado
        cell_diff_map = {str(rid): set(keep_cols) - {"Id"} for rid in df_rows["Id"].astype(str).tolist()}

        # Llamada al helper centralizado (maneja cliente y hoja internamente)
        _shared_upsert_by_id_partial(df_rows, cell_diff_map=cell_diff_map)
    except Exception as e:
        st.info(f"No pude ejecutar upsert a Sheets con el helper compartido: {e}")

# ===============================================================================
def render(user: dict | None = None):
    # 🔒 Refuerzo: si no hay df_main en sesión, cargar desde disco
    if ("df_main" not in st.session_state) or (not isinstance(st.session_state["df_main"], pd.DataFrame)) or st.session_state["df_main"].empty:
        df_local = _load_local_if_exists()
        if isinstance(df_local, pd.DataFrame) and not df_local.empty:
            st.session_state["df_main"] = df_local.copy()

    if st.session_state["est_visible"]:
        A, Fw, T_width, D, R, C = 1.80, 2.10, 3.00, 2.00, 2.00, 1.60

        # 👉 Div envoltorio de la sección (margen negativo para que suba)
        st.markdown(
            '<div id="est-section" style="margin-top:-32px;">',
            unsafe_allow_html=True,
        )

        st.markdown(
            """
        <style>
          #est-section .stButton > button { 
            width: 100% !important; 
          }

          #est-section .ag-header-cell-label{ 
            font-weight: 400 !important; 
            white-space: normal !important; 
            line-height: 1.15 !important; 
          }

          /* habilita scroll horizontal inferior */
          #est-section .ag-body-horizontal-scroll,
          #est-section .ag-center-cols-viewport { 
            overflow-x: auto !important; 
          }

          .section-est .help-strip + .form-card{ 
            margin-top: 2px !important; 
          }

          .est-pill{ 
            width:100%; 
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
            margin: 0 0 12px; 
          }

          .est-pill span{ 
            display:inline-flex; 
            gap:8px; 
            align-items:center; 
          }

          /* ===== Colores de encabezados por bloques (sin emojis en headers) ===== */
          /* Registro — lila */
          #est-section .ag-header-cell[col-id="Fecha de registro"],
          #est-section .ag-header-cell[col-id="Hora de registro"] { 
            background:#F5F3FF !important; 
          }

          /* Inicio — celeste muy claro */
          #est-section .ag-header-cell[col-id="Fecha de inicio"],
          #est-section .ag-header-cell[col-id="Hora de inicio"] { 
            background:#E0F2FE !important; 
          }

          /* Término — jade muy claro */
          #est-section .ag-header-cell[col-id="Fecha terminada"],
          #est-section .ag-header-cell[col-id="Hora terminada"] { 
            background:#D1FAE5 !important; 
          }

          /* Bloque Eliminada / Cancelada / Pausada — gris suave */
          #est-section .ag-header-cell[col-id="Fecha eliminada"],
          #est-section .ag-header-cell[col-id="Hora eliminada"],
          #est-section .ag-header-cell[col-id="Fecha cancelada"],
          #est-section .ag-header-cell[col-id="Hora cancelada"],
          #est-section .ag-header-cell[col-id="Fecha pausada"],
          #est-section .ag-header-cell[col-id="Hora pausada"] {
              background:#E5E7EB !important;
              color:#374151 !important;
          }

          /* Estado actual neutro (solo emojis en celdas) */
          #est-section .ag-header-cell[col-id="Estado actual"] { 
            background:#F3F4F6 !important; 
            color:#111827 !important; 
          }
        </style>
        """,
            unsafe_allow_html=True,
        )

        # ==== Título tipo "píldora" ====
        c_pill, _, _, _, _, _ = st.columns([A, Fw, T_width, D, R, C], gap="medium")
        with c_pill:
            st.markdown(
                '<div class="est-pill"><span>✏️&nbsp;Editar estado</span></div>',
                unsafe_allow_html=True,
            )

        # ==== Texto de ayuda + tarjeta contenedora ====
        st.markdown(
            """
        <div class="section-est">
          <div class="help-strip">
            <strong>Indicaciones:</strong> Usa los filtros para ubicar la tarea → ▶️ al registrar <em>fecha y hora de inicio</em> el estado pasa a “En curso” → ✅ al registrar <em>fecha y hora de término</em> pasa a “Terminada” → 💾 Guardar.<br>
            <strong>Importante:</strong> cada fecha y hora queda sellada al guardar; solo podrás completar el estado siguiente. Al finalizar, sube el enlace de Drive en <em>Link de archivo</em>.
          </div>
          <div class="form-card">
        """,
            unsafe_allow_html=True,
        )

        # Base global (LIMPIA y sin duplicados)
        df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
        df_all = _dedup_keep_last_with_id(df_all)

        # Alias...
        if "Tipo de tarea" not in df_all.columns and "Tipo" in df_all.columns:
            df_all["Tipo de tarea"] = df_all["Tipo"]
        if "Fecha de inicio" not in df_all.columns and "Fecha inicio" in df_all.columns:
            df_all["Fecha de inicio"] = df_all["Fecha inicio"]
        if "Fecha terminada" not in df_all.columns and "Fecha Terminado" in df_all.columns:
            df_all["Fecha terminada"] = df_all["Fecha Terminado"]
        if "Fecha de registro" not in df_all.columns and "Fecha Registro" in df_all.columns:
            df_all["Fecha de registro"] = df_all["Fecha Registro"]
        if "Hora de registro" not in df_all.columns and "Hora Registro" in df_all.columns:
            df_all["Hora de registro"] = df_all["Hora Registro"]
        for need in ["Fecha eliminada", "Hora eliminada",
                     "Fecha cancelada", "Hora cancelada",
                     "Fecha pausada", "Hora pausada"]:
            if need not in df_all.columns:
                df_all[need] = ""

        st.session_state["df_main"] = df_all.copy()

        # 🔐 ACL
        me = _display_name().strip()
        is_super = _is_super_editor()
        if not is_super:
            df_all = apply_scope(df_all, user=st.session_state.get("acl_user"))
            if isinstance(df_all, pd.DataFrame) and "Responsable" in df_all.columns and me:
                try:
                    mask = df_all["Responsable"].astype(str).str.contains(me, case=False, na=False)
                    df_all = df_all[mask]
                except Exception:
                    pass
        else:
            ver_todas = st.toggle("👀 Ver todas las tareas", value=True, key="est_ver_todas")
            if (not ver_todas) and isinstance(df_all, pd.DataFrame) and "Responsable" in df_all.columns and me:
                try:
                    mask = df_all["Responsable"].astype(str).str.contains(me, case=False, na=False)
                    df_all = df_all[mask]
                except Exception:
                    pass

        # Rango por defecto
        fr_all = pd.to_datetime(df_all.get("Fecha Registro", pd.Series([], dtype=object)), errors="coerce")
        if fr_all.notna().any():
            min_date = fr_all.min().date()
            max_date = fr_all.max().date()
        else:
            today = pd.Timestamp.today().normalize().date()
            min_date = max_date = today

        # ===== FILTROS =====
        estados_catalogo = ["No iniciado", "En curso", "Terminada", "Pausada", "Cancelada", "Eliminada"]

        with st.form("est_filtros_v4", clear_on_submit=False):
            if is_super:
                c_resp, c_fase, c_tipo, c_estado, c_desde, c_hasta, c_buscar = st.columns(
                    [Fw, Fw, T_width, D, D, R, C], gap="medium"
                )
                resp_all = sorted([x for x in df_all.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
                est_resp = c_resp.selectbox("Responsable", ["Todos"] + resp_all, index=0)
            else:
                c_fase, c_tipo, c_estado, c_desde, c_hasta, c_buscar = st.columns(
                    [Fw, T_width, D, D, R, C], gap="medium"
                )
                est_resp = "Todos"

            fases_all = sorted([x for x in df_all.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            est_fase = c_fase.selectbox("Fase", ["Todas"] + fases_all, index=0)

            tipos_all = sorted([x for x in df_all.get("Tipo de tarea", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
            est_tipo = c_tipo.selectbox("Tipo de tarea", ["Todos"] + tipos_all, index=0)

            estado_labels = {
                "No iniciado": "⏳ No iniciado",
                "En curso": "🟢 En curso",
                "Terminada": "✅ Terminada",
                "Pausada": "⏸️ Pausada",
                "Cancelada": "✖️ Cancelada",
                "Eliminada": "🗑️ Eliminada",
            }
            estado_opts_labels = ["Todos"] + [estado_labels[e] for e in estados_catalogo]
            sel_label = c_estado.selectbox("Estado actual", estado_opts_labels, index=0)
            est_estado = "Todos" if sel_label == "Todos" else [k for k, v in estado_labels.items() if v == sel_label][0]

            est_desde = c_desde.date_input("Desde", value=min_date, min_value=min_date, max_value=max_date, key="est_desde")
            est_hasta = c_hasta.date_input("Hasta", value=max_date, min_value=min_date, max_value=max_date, key="est_hasta")

            with c_buscar:
                st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
                est_do_buscar = st.form_submit_button("🔍 Buscar", use_container_width=True)

        # Filtrado
        df_tasks = df_all.copy()

        fi_eff = pd.to_datetime(df_tasks.get("Fecha de inicio", pd.Series([], dtype=object)), errors="coerce")
        ft_eff = pd.to_datetime(df_tasks.get("Fecha terminada", pd.Series([], dtype=object)), errors="coerce")
        fe_eff = pd.to_datetime(df_tasks.get("Fecha eliminada", pd.Series([], dtype=object)), errors="coerce")
        estado_calc = pd.Series("No iniciado", index=df_tasks.index, dtype="object")
        estado_calc = estado_calc.mask(fi_eff.notna() & ft_eff.isna() & fe_eff.isna(), "En curso")
        estado_calc = estado_calc.mask(ft_eff.notna() & fe_eff.isna(), "Terminada")
        estado_calc = estado_calc.mask(fe_eff.notna(), "Eliminada")
        if "Estado" in df_tasks.columns:
            saved = df_tasks["Estado"].astype(str).str.strip()
            estado_calc = saved.where(~saved.isin(["", "nan", "NaN", "None"]), estado_calc)
        df_tasks["_ESTADO_EFECTIVO_"] = estado_calc

        if est_do_buscar:
            if is_super and est_resp != "Todos" and "Responsable" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Responsable"].astype(str) == est_resp]
            if est_fase != "Todas" and "Fase" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Fase"].astype(str) == est_fase]
            if est_tipo != "Todos" and "Tipo de tarea" in df_tasks.columns:
                df_tasks = df_tasks[df_tasks["Tipo de tarea"].astype(str) == est_tipo]
            if est_estado != "Todos":
                df_tasks = df_tasks[df_tasks["_ESTADO_EFECTIVO_"].astype(str) == est_estado]

            fcol = pd.to_datetime(df_tasks.get("Fecha Registro", pd.Series([], dtype=object)), errors="coerce")
            if est_desde:
                df_tasks = df_tasks[fcol >= pd.to_datetime(est_desde)]
            if est_hasta:
                df_tasks = df_tasks[fcol <= (pd.to_datetime(est_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]

        # Solo con Id
        df_tasks = _dedup_keep_last_with_id(df_tasks)

        # ===== Tabla "Resultados" =====
        st.markdown("**Resultados**")

        def _fmt_date_series(s: pd.Series) -> pd.Series:
            s = pd.to_datetime(s, errors="coerce")
            out = s.dt.strftime("%Y-%m-%d")
            return out.fillna("-")

        def _fmt_time_series(s: pd.Series) -> pd.Series:
            def _one(x):
                x = "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()
                if not x or x.lower() in {"nan", "nat", "none", "null", "-"}:
                    return "-"
                m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", x)
                if m:
                    return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
                try:
                    d = pd.to_datetime(x, errors="coerce")
                    if pd.isna(d):
                        return "-"
                    return f"{int(d.hour):02d}:{int(d.minute):02d}"
                except Exception:
                    return "-"
            return s.astype(str).map(_one)

        def _coalesce_dt(base: pd.DataFrame, a: str, b: str) -> pd.Series:
            s1 = pd.to_datetime(base.get(a, pd.Series([], dtype=object)), errors="coerce")
            s2 = pd.to_datetime(base.get(b, pd.Series([], dtype=object)), errors="coerce")
            if len(s1) == 0:
                return s2
            if len(s2) == 0:
                return s1
            return s1.where(s1.notna(), s2)

        cols_out = [
            "Id","Tarea","Estado actual",
            "Fecha de registro","Hora de registro",
            "Fecha de inicio","Hora de inicio",
            "Fecha terminada","Hora terminada",
            "Link de archivo",
            "Fecha eliminada","Hora eliminada",
            "Fecha cancelada","Hora cancelada",
            "Fecha pausada","Hora pausada",
        ]

        df_view = pd.DataFrame(columns=cols_out)
        if not df_tasks.empty:
            base = df_tasks.copy()
            for need in [
                "Id","Tarea","Estado","Fecha Registro","Hora Registro",
                "Fecha inicio","Fecha de inicio","Hora de inicio",
                "Fecha Terminado","Fecha terminada","Hora Terminado",
                "Fecha eliminada","Hora eliminada",
                "Fecha cancelada","Hora cancelada",
                "Fecha pausada","Hora pausada",
                "Link de archivo",
                "Fecha de registro","Hora de registro"
            ]:
                if need not in base.columns:
                    base[need] = ""

            fr = pd.to_datetime(base["Fecha Registro"], errors="coerce")
            hr = base["Hora Registro"].astype(str)
            fi = _coalesce_dt(base, "Fecha inicio", "Fecha de inicio")
            hi = base["Hora de inicio"].astype(str)
            ft = _coalesce_dt(base, "Fecha Terminado", "Fecha terminada")
            ht = base["Hora Terminado"].astype(str)
            fe = pd.to_datetime(base["Fecha eliminada"], errors="coerce")
            he = base["Hora eliminada"].astype(str)
            fc = pd.to_datetime(base["Fecha cancelada"], errors="coerce")
            hc = base["Hora cancelada"].astype(str)
            fp = pd.to_datetime(base["Fecha pausada"], errors="coerce")
            hp = base["Hora pausada"].astype(str)

            est_now = pd.Series("No iniciado", index=base.index, dtype="object")
            est_now = est_now.mask(fi.notna() & ft.isna() & fe.isna(), "En curso")
            est_now = est_now.mask(ft.notna() & fe.isna(), "Terminada")
            est_now = est_now.mask(fe.notna(), "Eliminada")
            if "Estado" in base.columns:
                estado_guardado = base["Estado"].astype(str).str.strip()
                est_now = estado_guardado.where(~estado_guardado.isin(["", "nan", "NaN", "None"]), est_now)

            link_col = base["Link de archivo"].astype(str).replace({"nan":"-","NaN":"-","None":"-","": "-"})

            df_view = pd.DataFrame({
                "Id": base["Id"].astype(str),
                "Tarea": base["Tarea"].astype(str).replace({"nan":"-","NaN":"-","": "-"}),
                "Estado actual": est_now,
                "Fecha de registro": _fmt_date_series(fr),
                "Hora de registro": _fmt_time_series(hr),
                "Fecha de inicio": _fmt_date_series(fi),
                "Hora de inicio": _fmt_time_series(hi),
                "Fecha terminada": _fmt_date_series(ft),
                "Hora terminada": _fmt_time_series(ht),
                "Link de archivo": link_col,
                "Fecha eliminada": _fmt_date_series(fe),
                "Hora eliminada": _fmt_time_series(he),
                "Fecha cancelada": _fmt_date_series(fc),
                "Hora cancelada": _fmt_time_series(hc),
                "Fecha pausada": _fmt_date_series(fp),
                "Hora pausada": _fmt_time_series(hp),
            })[cols_out].copy()

        # ========= editores y estilo =========
        estado_emoji_fmt = JsCode("""
        function(p){
          const v = String(p.value || '');
          const M = {
            "No iniciado":"⏳ No iniciado",
            "En curso":"🟢 En curso",
            "Terminada":"✅ Terminada",
            "Pausada":"⏸️ Pausada",
            "Cancelada":"✖️ Cancelada",
            "Eliminada":"🗑️ Eliminada"
          };
          return M[v] || v;
        }""")

        estado_cell_style = JsCode("""
        function(p){
          return {fontWeight:'600', textAlign:'center'};
        }""")

        date_editor = JsCode("""
        class DateEditor{
          init(p){
            this.eInput = document.createElement('input');
            this.eInput.type = 'date';
            this.eInput.classList.add('ag-input');
            this.eInput.style.width = '100%';
            const v = (p.value || '').toString().trim();
            if (/^\\d{4}-\\d{2}-\\d{2}$/.test(v)) { this.eInput.value = v; }
            else {
              const d = new Date(v);
              if (!isNaN(d.getTime())){
                const pad=n=>String(n).padStart(2,'0');
                this.eInput.value = d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
              }
            }
          }
          getGui(){ return this.eInput }
          afterGuiAttached(){ this.eInput.focus() }
          getValue(){ return this.eInput.value }
        }""")

        link_formatter = JsCode("""function(p){ const s=String(p.value||'').trim(); return s? s : '-'; }""")

        on_cell_changed = JsCode(f"""
        function(params){{
          const field = params.colDef.field;
          const pad = n => String(n).padStart(2,'0');
          const now = new Date();
          const utcMs = now.getTime() + now.getTimezoneOffset()*60000;
          const lima = new Date(utcMs - 5*60*60000);
          const hhmm = pad(lima.getHours()) + ':' + pad(lima.getMinutes());
          if (field === 'Fecha de inicio') {{
            params.node.setDataValue('Hora de inicio', hhmm);
            params.node.setDataValue('Estado actual', 'En curso');
          }}
          if (field === 'Fecha terminada') {{
            params.node.setDataValue('Hora terminada', hhmm);
            params.node.setDataValue('Estado actual', 'Terminada');
          }}
          if (field === 'Fecha eliminada') {{
            params.node.setDataValue('Hora eliminada', hhmm);
            params.node.setDataValue('Estado actual', 'Eliminada');
          }}
        }}""")

        editable_start = JsCode(f"""
        function(p){{
          const SUPER = {str(is_super).lower()};
          if(SUPER) return true;
          const v = String(p.value||'').trim();
          return v === '-' || v === '';
        }}""")
        editable_end = JsCode(f"""
        function(p){{
          const SUPER = {str(is_super).lower()};
          if(SUPER) return true;
          const v = String(p.value||'').trim();
          const hasStart = String(p.data['Fecha de inicio']||'').trim() !== '' && String(p.data['Fecha de inicio']||'').trim() !== '-';
          return (v === '' || v === '-') && hasStart;
        }}""")
        editable_del = JsCode(f"""
        function(p){{
          const SUPER = {str(is_super).lower()};
          if(SUPER) return true;
          const v = String(p.value||'').trim();
          const hasEnd = String(p.data['Fecha terminada']||'').trim() !== '' && String(p.data['Fecha terminada']||'').trim() !== '-';
          return (v === '' || v === '-') && hasEnd;
        }}""")

        style_reg = {"backgroundColor": "#F5F3FF"}
        style_ini = {"backgroundColor": "#E0F2FE"}
        style_ter = {"backgroundColor": "#ECFDF5"}
        style_del = {"backgroundColor": "#F9FAFB"}

        gob = GridOptionsBuilder.from_dataframe(df_view)
        gob.configure_grid_options(
            suppressMovableColumns=True,
            domLayout="normal",
            ensureDomOrder=True,
            rowHeight=38,
            headerHeight=60,
            suppressHorizontalScroll=False
        )
        gob.configure_default_column(wrapHeaderText=True, autoHeaderHeight=True)
        gob.configure_selection("single", use_checkbox=False)

        gob.configure_column("Estado actual", headerName="⚙️ Estado actual", valueFormatter=estado_emoji_fmt, cellStyle=estado_cell_style, minWidth=170, editable=False)
        gob.configure_column("Fecha de registro", headerName="🕒 Fecha de registro", editable=False, minWidth=170, cellStyle=style_reg)
        gob.configure_column("Hora de registro", headerName="🕒 Hora de registro", editable=False, minWidth=150, cellStyle=style_reg)
        gob.configure_column("Tarea", headerName="📝 Tarea", editable=False, minWidth=320)
        gob.configure_column("Id", editable=False, minWidth=120)
        gob.configure_column("Fecha de inicio", headerName="▶️ Fecha de inicio", editable=editable_start, cellEditor=date_editor, minWidth=180, cellStyle=style_ini)
        gob.configure_column("Hora de inicio", headerName="▶️ Hora de inicio", editable=False, minWidth=160, cellStyle=style_ini)
        gob.configure_column("Fecha terminada", headerName="✅ Fecha terminada", editable=editable_end, cellEditor=date_editor, minWidth=190, cellStyle=style_ter)
        gob.configure_column("Hora terminada", headerName="✅ Hora terminada", editable=False, minWidth=160, cellStyle=style_ter)
        gob.configure_column("Link de archivo", headerName="🔗 Link de archivo", editable=True, minWidth=300, valueFormatter=link_formatter)
        gob.configure_column("Fecha eliminada", headerName="🗑️ Fecha eliminada", editable=editable_del, cellEditor=date_editor, minWidth=190, cellStyle=style_del)
        gob.configure_column("Hora eliminada", headerName="🗑️ Hora eliminada", editable=False, minWidth=160, cellStyle=style_del)
        gob.configure_column("Fecha cancelada", headerName="✖️ Fecha cancelada", editable=editable_start, cellEditor=date_editor, minWidth=190, cellStyle=style_del)
        gob.configure_column("Hora cancelada", headerName="✖️ Hora cancelada", editable=False, minWidth=160, cellStyle=style_del)
        gob.configure_column("Fecha pausada", headerName="⏸️ Fecha pausada", editable=editable_start, cellEditor=date_editor, minWidth=190, cellStyle=style_del)
        gob.configure_column("Hora pausada", headerName="⏸️ Hora pausada", editable=False, minWidth=160, cellStyle=style_del)

        grid_opts = gob.build()
        grid_opts["onCellValueChanged"] = on_cell_changed.js_code

        grid = AgGrid(
            df_view,
            gridOptions=grid_opts,
            data_return_mode=DataReturnMode.AS_INPUT,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            fit_columns_on_grid_load=False,
            enable_enterprise_modules=False,
            reload_data=False,
            height=430,
            allow_unsafe_jscode=True,
            theme="balham",
        )

        # ===== Guardar cambios =====
        _, u2 = st.columns([A + Fw + T_width + D + R, C], gap="medium")
        with u2:
            if st.button("💾 Guardar", use_container_width=True, key="est_guardar_inline_v4"):
                try:
                    grid_data = pd.DataFrame(grid.get("data", []))
                    if grid_data.empty or "Id" not in grid_data.columns:
                        st.info("No hay cambios para guardar.")
                    else:
                        # --- AJUSTE 1: Autogenerar Id si viene vacío en la vista
                        id_series = grid_data["Id"].astype(str).str.strip()
                        mask_blank_ids = id_series.str.lower().isin({"", "-", "nan", "none", "null"})
                        if mask_blank_ids.any():
                            for ridx in grid_data.index[mask_blank_ids]:
                                grid_data.at[ridx, "Id"] = _gen_id()

                        grid_data["Id"] = grid_data["Id"].astype(str)
                        g_i = grid_data.set_index("Id")

                        def norm(s: pd.Series) -> pd.Series:
                            t = s.fillna("").astype(str).str.strip()
                            return t.replace({"-": "", "NaT": "", "NAT": "", "nat": "", "NaN": "", "nan": "", "None": "", "none": ""})

                        fi_new_vis = norm(g_i.get("Fecha de inicio", pd.Series(index=g_i.index)))
                        hi_new      = norm(g_i.get("Hora de inicio", pd.Series(index=g_i.index)))
                        ft_new_vis  = norm(g_i.get("Fecha terminada", pd.Series(index=g_i.index)))
                        ht_new      = norm(g_i.get("Hora terminada", pd.Series(index=g_i.index)))
                        fe_new_vis  = norm(g_i.get("Fecha eliminada", pd.Series(index=g_i.index)))
                        he_new      = norm(g_i.get("Hora eliminada", pd.Series(index=g_i.index)))
                        fc_new_vis  = norm(g_i.get("Fecha cancelada", pd.Series(index=g_i.index)))
                        hc_new      = norm(g_i.get("Hora cancelada", pd.Series(index=g_i.index)))
                        fp_new_vis  = norm(g_i.get("Fecha pausada", pd.Series(index=g_i.index)))
                        hp_new      = norm(g_i.get("Hora pausada", pd.Series(index=g_i.index)))
                        lk_new      = norm(g_i.get("Link de archivo", pd.Series(index=g_i.index)))

                        ids_view = list(g_i.index)

                        full_before = st.session_state.get("df_main", pd.DataFrame()).copy()
                        if full_before.empty or "Id" not in full_before.columns:
                            st.warning("No hay base para actualizar.")
                            return
                        full_before["Id"] = full_before["Id"].astype(str)

                        base = full_before.copy()
                        me = _display_name().strip()
                        is_super = _is_super_editor()
                        if not is_super and "Responsable" in base.columns and me:
                            mask_me = base["Responsable"].astype(str).str.contains(me, case=False, na=False)
                            base = base[mask_me]

                        for need in [
                            "Estado","Fecha estado actual","Hora estado actual",
                            "Fecha Registro","Hora Registro",
                            "Fecha inicio","Fecha de inicio","Hora de inicio",
                            "Fecha Terminado","Fecha terminada","Hora Terminado",
                            "Fecha eliminada","Hora eliminada",
                            "Fecha cancelada","Hora cancelada",
                            "Fecha pausada","Hora pausada",
                            "Link de archivo",
                            "Fecha de registro","Hora de registro",
                            "OwnerEmail","Responsable"
                        ]:
                            if need not in base.columns:
                                base[need] = ""

                        new_ids = []
                        if mask_blank_ids.any():
                            tarea_by_newid = {row["Id"]: row.get("Tarea", "") for _, row in grid_data.iterrows()}
                            base_blank = base["Id"].astype(str).str.strip().isin({"", "-", "nan", "none", "null"})
                            if base_blank.any():
                                for idx_base in base.index[base_blank]:
                                    t_base = str(base.at[idx_base, "Tarea"] or "").strip()
                                    for nid, t_grid in tarea_by_newid.items():
                                        if not nid:
                                            continue
                                        if str(t_grid or "").strip() and t_base == str(t_grid).strip():
                                            base.at[idx_base, "Id"] = nid
                                            new_ids.append(nid)

                        base = _dedup_keep_last_with_id(base)
                        ids_ok = [i for i in ids_view if i in set(base["Id"].astype(str))]

                        if not is_super:
                            cur_start = base.groupby("Id", as_index=True)["Fecha inicio"].last().map(_canon_str)
                            cur_start_alias = base.groupby("Id", as_index=True)["Fecha de inicio"].last().map(_canon_str)
                            def _has_start(i):
                                return bool(_canon_str(cur_start.get(i,"")) or _canon_str(cur_start_alias.get(i,"")) or _canon_str(fi_new_vis.get(i,"")))
                            bad_term = [i for i in ids_ok if (_canon_str(ft_new_vis.get(i, "")) and not _has_start(i))]
                            if bad_term:
                                st.warning("No puedes registrar 'Fecha terminada' sin 'Fecha de inicio' en algunas tareas.")
                                for i in bad_term:
                                    ft_new_vis[i] = ""; ht_new[i] = ""

                            cur_end = base.groupby("Id", as_index=True)["Fecha terminada"].last().map(_canon_str)
                            cur_end_alias = base.groupby("Id", as_index=True)["Fecha Terminado"].last().map(_canon_str)
                            def _has_end(i):
                                return bool(_canon_str(cur_end.get(i,"")) or _canon_str(cur_end_alias.get(i,"")) or _canon_str(ft_new_vis.get(i,"")))
                            bad_del = [i for i in ids_ok if (_canon_str(fe_new_vis.get(i,"")) and not _has_end(i))]
                            if bad_del:
                                st.warning("No puedes registrar 'Fecha eliminada' sin 'Fecha terminada' en algunas tareas.")
                                for i in bad_del:
                                    fe_new_vis[i] = ""; he_new[i] = ""

                        h_now = _now_lima_trimmed_local().strftime("%H:%M")

                        changed_ids: set[str] = set()
                        full_updated = full_before.copy()

                        base_idx = base.copy().set_index("Id")
                        base_idx = base_idx[~base_idx.index.duplicated(keep="last")]

                        me_email = _user_email().strip().lower()
                        resp_alias = (st.secrets.get("resp_alias", {}) or {})
                        me_alias = resp_alias.get(me_email) or _display_name().strip() or me_email

                        if not is_super:
                            for i in ids_ok:
                                prev_owner = _canon_str(base_idx.at[i, "OwnerEmail"]) if i in base_idx.index else ""
                                prev_resp  = _canon_str(base_idx.at[i, "Responsable"]) if i in base_idx.index else ""
                                changed_local = False
                                if not prev_owner:
                                    base_idx.at[i, "OwnerEmail"] = me_email
                                    changed_local = True
                                if not prev_resp:
                                    base_idx.at[i, "Responsable"] = me_alias
                                    changed_local = True
                                if changed_local:
                                    changed_ids.add(i)

                        for i in ids_ok:
                            prev_fi  = _canon_str(base_idx.at[i, "Fecha inicio"]) if i in base_idx.index else ""
                            prev_fiA = _canon_str(base_idx.at[i, "Fecha de inicio"]) if i in base_idx.index else ""
                            prev_hi  = _canon_str(base_idx.at[i, "Hora de inicio"]) if i in base_idx.index else ""
                            new_fi   = _canon_str(fi_new_vis.get(i, ""))
                            new_hi   = _canon_str(hi_new.get(i, ""))

                            if is_super:
                                if new_fi != prev_fi or new_fi != prev_fiA:
                                    base_idx.at[i, "Fecha inicio"] = new_fi
                                    base_idx.at[i, "Fecha de inicio"] = new_fi
                                    changed_ids.add(i)
                                if new_fi:
                                    if not new_hi: new_hi = h_now
                                    if new_hi != prev_hi:
                                        base_idx.at[i, "Hora de inicio"] = new_hi; changed_ids.add(i)
                            else:
                                if (not prev_fi and not prev_fiA) and new_fi:
                                    base_idx.at[i, "Fecha inicio"] = new_fi
                                    base_idx.at[i, "Fecha de inicio"] = new_fi
                                    base_idx.at[i, "Hora de inicio"] = (new_hi or h_now)
                                    changed_ids.add(i)

                            prev_ft  = _canon_str(base_idx.at[i, "Fecha Terminado"]) if i in base_idx.index else ""
                            prev_ftA = _canon_str(base_idx.at[i, "Fecha terminada"]) if i in base_idx.index else ""
                            prev_ht  = _canon_str(base_idx.at[i, "Hora Terminado"]) if i in base_idx.index else ""
                            new_ft   = _canon_str(ft_new_vis.get(i, "")); new_ht  = _canon_str(ht_new.get(i, ""))

                            has_start_now = bool(_canon_str(base_idx.at[i, "Fecha inicio"]) or _canon_str(base_idx.at[i, "Fecha de inicio"]))

                            if is_super:
                                if new_ft != prev_ft or new_ft != prev_ftA:
                                    base_idx.at[i, "Fecha Terminado"] = new_ft
                                    base_idx.at[i, "Fecha terminada"] = new_ft
                                    changed_ids.add(i)
                                if new_ft:
                                    if not new_ht: new_ht = h_now
                                    if new_ht != prev_ht:
                                        base_idx.at[i, "Hora Terminado"] = new_ht; changed_ids.add(i)
                            else:
                                if (not prev_ft and not prev_ftA) and new_ft and has_start_now:
                                    base_idx.at[i, "Fecha Terminado"] = new_ft
                                    base_idx.at[i, "Fecha terminada"] = new_ft
                                    base_idx.at[i, "Hora Terminado"] = (new_ht or h_now)
                                    changed_ids.add(i)

                            # Eliminación
                            prev_fe  = _canon_str(base_idx.at[i, "Fecha eliminada"]) if i in base_idx.index else ""
                            prev_he  = _canon_str(base_idx.at[i, "Hora eliminada"]) if i in base_idx.index else ""
                            new_fe   = _canon_str(fe_new_vis.get(i, "")); new_he = _canon_str(he_new.get(i, ""))

                            has_end_now = bool(_canon_str(base_idx.at[i, "Fecha terminada"]) or _canon_str(base_idx.at[i, "Fecha Terminado"]))

                            if is_super:
                                if new_fe != prev_fe:
                                    base_idx.at[i, "Fecha eliminada"] = new_fe; changed_ids.add(i)
                                if new_fe:
                                    if not new_he: new_he = h_now
                                    if new_he != prev_he:
                                        base_idx.at[i, "Hora eliminada"] = new_he; changed_ids.add(i)
                            else:
                                if (not prev_fe) and new_fe and has_end_now:
                                    base_idx.at[i, "Fecha eliminada"] = new_fe
                                    base_idx.at[i, "Hora eliminada"] = (new_he or h_now)
                                    changed_ids.add(i)

                            # Cancelación
                            prev_fc  = _canon_str(base_idx.at[i, "Fecha cancelada"]) if i in base_idx.index else ""
                            prev_hc  = _canon_str(base_idx.at[i, "Hora cancelada"]) if i in base_idx.index else ""
                            new_fc   = _canon_str(fc_new_vis.get(i, "")); new_hc = _canon_str(hc_new.get(i, ""))

                            if is_super:
                                if new_fc != prev_fc:
                                    base_idx.at[i, "Fecha cancelada"] = new_fc; changed_ids.add(i)
                                if new_fc:
                                    if not new_hc: new_hc = h_now
                                    if new_hc != prev_hc:
                                        base_idx.at[i, "Hora cancelada"] = new_hc; changed_ids.add(i)
                            else:
                                if (not prev_fc) and new_fc:
                                    base_idx.at[i, "Fecha cancelada"] = new_fc
                                    base_idx.at[i, "Hora cancelada"] = (new_hc or h_now)
                                    changed_ids.add(i)

                            # Pausa
                            prev_fp  = _canon_str(base_idx.at[i, "Fecha pausada"]) if i in base_idx.index else ""
                            prev_hp  = _canon_str(base_idx.at[i, "Hora pausada"]) if i in base_idx.index else ""
                            new_fp   = _canon_str(fp_new_vis.get(i, "")); new_hp = _canon_str(hp_new.get(i, ""))

                            if is_super:
                                if new_fp != prev_fp:
                                    base_idx.at[i, "Fecha pausada"] = new_fp; changed_ids.add(i)
                                if new_fp:
                                    if not new_hp: new_hp = h_now
                                    if new_hp != prev_hp:
                                        base_idx.at[i, "Hora pausada"] = new_hp; changed_ids.add(i)
                            else:
                                if (not prev_fp) and new_fp:
                                    base_idx.at[i, "Fecha pausada"] = new_fp
                                    base_idx.at[i, "Hora pausada"] = (new_hp or h_now)
                                    changed_ids.add(i)

                            # Estado actual y sellos
                            fe_eff = _canon_str(base_idx.at[i, "Fecha eliminada"])
                            ft_eff2 = _canon_str(base_idx.at[i, "Fecha Terminado"]) or _canon_str(base_idx.at[i, "Fecha terminada"])
                            fi_eff2 = _canon_str(base_idx.at[i, "Fecha inicio"]) or _canon_str(base_idx.at[i, "Fecha de inicio"])
                            if fe_eff:
                                base_idx.at[i, "Estado"] = "Eliminada"
                                base_idx.at[i, "Fecha estado actual"] = fe_eff
                                base_idx.at[i, "Hora estado actual"] = _canon_str(base_idx.at[i, "Hora eliminada"]) or h_now
                            elif ft_eff2:
                                base_idx.at[i, "Estado"] = "Terminada"
                                base_idx.at[i, "Fecha estado actual"] = ft_eff2
                                base_idx.at[i, "Hora estado actual"] = _canon_str(base_idx.at[i, "Hora Terminado"]) or h_now
                            elif fi_eff2:
                                base_idx.at[i, "Estado"] = "En curso"
                                base_idx.at[i, "Fecha estado actual"] = fi_eff2
                                base_idx.at[i, "Hora estado actual"] = _canon_str(base_idx.at[i, "Hora de inicio"]) or h_now
                            else:
                                base_idx.at[i, "Estado"] = "No iniciado"
                                base_idx.at[i, "Fecha estado actual"] = _canon_str(base_idx.at[i, "Fecha Registro"]) or _canon_str(base_idx.at[i, "Fecha de registro"])
                                base_idx.at[i, "Hora estado actual"] = _canon_str(base_idx.at[i, "Hora Registro"]) or _canon_str(base_idx.at[i, "Hora de registro"])

                        if changed_ids:
                            cols_apply = [
                                "Estado","Fecha estado actual","Hora estado actual",
                                "Fecha inicio","Fecha de inicio","Hora de inicio",
                                "Fecha Terminado","Fecha terminada","Hora Terminado",
                                "Fecha eliminada","Hora eliminada",
                                "Fecha cancelada","Hora cancelada",
                                "Fecha pausada","Hora pausada",
                                "Link de archivo",
                                "OwnerEmail","Responsable",
                            ]
                            for col in cols_apply:
                                if col not in full_updated.columns:
                                    full_updated[col] = ""
                            for i in changed_ids:
                                if i in base_idx.index:
                                    for col in cols_apply:
                                        val = base_idx.at[i, col]
                                        full_updated.loc[full_updated["Id"].astype(str) == i, col] = val
                            full_updated = _dedup_keep_last_with_id(full_updated)

                        st.session_state["df_main"] = full_updated.copy()

                        maybe_save = st.session_state.get("maybe_save")
                        if callable(maybe_save):
                            try:
                                res = maybe_save(_save_local, full_updated.copy())
                                if not isinstance(res, dict):
                                    res = _save_local(full_updated.copy())
                            except Exception:
                                res = _save_local(full_updated.copy())
                        else:
                            res = _save_local(full_updated.copy())

                        try:
                            if DO_SHEETS_UPSERT and changed_ids:
                                _sheet_upsert_estado_by_id(full_updated.copy(), sorted(changed_ids))
                        except Exception as ee:
                            st.info(f"Guardado local OK. No pude actualizar Sheets: {ee}")

                        if res.get("ok", False):
                            st.success(res.get("msg", "Cambios guardados."))
                            st.rerun()
                        else:
                            st.info(res.get("msg", "Guardado deshabilitado."))
                except Exception as e:
                    st.error(f"No pude guardar: {e}")

        # cierra form-card + section-est
        st.markdown("</div></div>", unsafe_allow_html=True)
        # cierra est-section
        st.markdown("</div>", unsafe_allow_html=True)
