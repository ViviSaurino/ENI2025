# features/gantt/view.py
from __future__ import annotations

from datetime import datetime, timedelta, date
import pandas as pd
import streamlit as st

# ============================== #
# GANTT – Vista base sin librerías externas
# ============================== #

PALETTE = {
    "No iniciado": "#D6EAF8",   # celeste claro
    "En curso":    "#D5F5E3",   # verde claro
    "Terminado":   "#FCE6FF",   # rosado pastel
    "Pausado":     "#FEF3C7",   # amarillo pastel
    "Cancelado":   "#FDE2C5",   # naranja pastel
    "Eliminado":   "#FAD1D1",   # rojo pastel
}

BORDER = {
    "No iniciado": "#6EC1F2",
    "En curso":    "#48C774",
    "Terminado":   "#E89BEF",
    "Pausado":     "#F59E0B",
    "Cancelado":   "#FB923C",
    "Eliminado":   "#EF4444",
}

# ---------- Helpers robustos de fechas ----------
def _scalarize(x):
    """Si x es array/serie/DatetimeIndex, devuelve el primer elemento; si está vacío, None."""
    try:
        # Evitar tratar strings como iterables
        if isinstance(x, (str, bytes)):
            return x
        # Tipos típicos iterables de fecha
        if isinstance(x, (list, tuple, pd.Series, pd.DatetimeIndex)):
            return x[0] if len(x) else None
        # Objetos con interfaz de array
        if hasattr(x, "__iter__") and not isinstance(x, (pd.Timestamp, datetime, str, bytes)):
            try:
                return x[0]
            except Exception:
                return x
        return x
    except Exception:
        return x

def _to_ts(x):
    """Convierte a Timestamp escalar o NaT, aceptando arrays/series/listas."""
    try:
        x = _scalarize(x)
        if isinstance(x, (pd.Timestamp, datetime)):
            return pd.Timestamp(x)
        d = pd.to_datetime(x, errors="coerce")
        # Si por alguna razón quedó array-like, sácalo escalar
        if isinstance(d, (pd.DatetimeIndex, pd.Series)) or getattr(d, "ndim", 0) > 0:
            d = d[0] if len(d) else pd.NaT
        return d
    except Exception:
        return pd.NaT

def _to_dt_only(x):
    t = _to_ts(x)
    return t.normalize() if not pd.isna(t) else pd.NaT

def _first_notna(*vals):
    for v in vals:
        t = _to_ts(v)
        if not pd.isna(t):
            return t
    return pd.NaT

def render(user: dict | None = None):
    # --------- Título ----------
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    st.subheader("📅 Gantt")

    # --------- CSS ----------
    st.markdown("""
    <style>
      .gantt-wrap{ border:1px solid #E5E7EB; border-radius:12px; padding:10px 12px; background:#FFF; }
      .gantt-header{ display:grid; grid-template-columns: 260px 1fr; gap:10px; align-items:end; margin-bottom:6px; }
      .gantt-legend{ display:flex; gap:8px; flex-wrap:wrap; font-size:12px; color:#6B7280; }
      .gantt-chip{ display:inline-flex; align-items:center; gap:6px; padding:2px 8px; border-radius:999px; background:#F9FAFB; border:1px solid #E5E7EB; }
      .gantt-chip-dot{ width:10px; height:10px; border-radius:50%; display:inline-block; }
      .gantt-grid{ display:grid; grid-template-columns: 260px 1fr; gap:10px; }
      .gantt-left{ padding:6px 8px; }
      .gantt-time{ overflow-x:auto; padding-bottom:6px; }
      .gantt-days{ display:grid; gap:0; border-bottom:1px solid #E5E7EB; position:sticky; top:0; background:#FFF; z-index:2; }
      .gantt-day{ font-size:11px; color:#6B7280; text-align:center; padding:6px 0; border-left:1px solid #F3F4F6; }
      .gantt-month{ font-size:11px; color:#374151; font-weight:600; padding:4px 6px; border-left:1px solid #E5E7EB;
                    background:#F9FAFB; position:sticky; left:0; z-index:3; border-radius:6px 6px 0 0; }
      .gantt-rows{ display:grid; gap:8px; }
      .gantt-row{ display:grid; grid-template-columns: 260px 1fr; gap:10px; align-items:center; min-height:38px; }
      .gantt-label{ font-size:12px; color:#374151; background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:6px 8px;
                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .gantt-canvas{ position:relative; height:38px; background:linear-gradient(to right, #FAFAFA 1px, transparent 1px);
                     background-size: var(--cellW) 100%; border-radius:8px; border:1px dashed #F3F4F6; }
      .gantt-bar{ position:absolute; top:6px; height:26px; border-radius:8px; display:flex; align-items:center; gap:8px; padding:0 10px;
                  font-size:12px; color:#111827; border-left:4px solid var(--bd); background: var(--bg);
                  box-shadow: 0 1px 0 rgba(0,0,0,0.04), inset 0 0 0 1px rgba(0,0,0,0.03);
                  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .gantt-empty{ padding:24px; text-align:center; color:#6B7280; font-size:13px; border:1px dashed #E5E7EB; border-radius:12px; background:#FAFAFA; }
      .filters .stButton>button{ height:38px; }
    </style>
    """, unsafe_allow_html=True)

    # --------- Datos base ----------
    df_all = st.session_state.get("df_main", pd.DataFrame()).copy()
    if df_all.empty:
        df_all = pd.DataFrame(columns=[
            "Id","Área","Fase","Responsable","Tarea","Estado",
            "Fecha Registro","Fecha inicio","Fecha Vencimiento","Fecha Terminado"
        ])

    # --------- FILTROS ----------
    with st.form("gantt_filters", clear_on_submit=False):
        cA, cF, cR, cD, cH, cB = st.columns([1.8, 2.1, 3.0, 1.6, 1.4, 1.2], gap="medium")
        area = cA.selectbox(
            "Área", options=["Todas"] + sorted([x for x in df_all.get("Área", pd.Series(dtype=str)).astype(str).unique() if x and x!="nan"]),
            index=0
        )
        fase = cF.selectbox(
            "Fase", options=["Todas"] + sorted([x for x in df_all.get("Fase", pd.Series(dtype=str)).astype(str).unique() if x and x!="nan"]),
            index=0
        )
        df_src = df_all.copy()
        if area != "Todas":
            df_src = df_src[df_src["Área"].astype(str) == area]
        if fase != "Todas" and "Fase" in df_src.columns:
            df_src = df_src[df_src["Fase"].astype(str) == fase]
        reps = ["Todos"] + sorted([x for x in df_src.get("Responsable", pd.Series(dtype=str)).astype(str).unique() if x and x!="nan"])
        resp = cR.selectbox("Responsable", options=reps, index=0)

        d_from = cD.date_input("Desde", value=None)
        d_to   = cH.date_input("Hasta", value=None)

        with cB:
            st.markdown('<div class="filters">', unsafe_allow_html=True)
            do_search = st.form_submit_button("🔍 Buscar", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # --------- Filtrado ----------
    df = df_all.copy()
    if do_search:
        if area != "Todas":
            df = df[df["Área"].astype(str) == area]
        if fase != "Todas" and "Fase" in df.columns:
            df = df[df["Fase"].astype(str) == fase]
        if resp != "Todos":
            df = df[df["Responsable"].astype(str) == resp]

    # Derivar fechas inicio/fin (robusto a arrays)
    df["__ini__"] = df.apply(
        lambda r: _first_notna(
            r.get("Fecha inicio"), r.get("Fecha Registro"), r.get("Fecha"), r.get("Fecha estado actual")
        ),
        axis=1,
    )
    df["__fin__"] = df.apply(
        lambda r: _first_notna(
            r.get("Fecha Terminado"), r.get("Fecha Vencimiento"), r.get("Vencimiento"), r.get("Fecha inicio")
        ),
        axis=1,
    )

    # Forzar tipo datetime escalar y normalizar (¡clave para evitar el TypeError!)
    df["__ini__"] = pd.to_datetime(df["__ini__"].apply(_scalarize), errors="coerce").dt.normalize()
    df["__fin__"] = pd.to_datetime(df["__fin__"].apply(_scalarize), errors="coerce").dt.normalize()

    # Completar faltantes y asegurar fin >= inicio
    df.loc[df["__fin__"].isna(), "__fin__"] = df["__ini__"]
    df.loc[df["__ini__"].isna(), "__ini__"] = df["__fin__"]
    df["__fin__"] = df[["__ini__", "__fin__"]].max(axis=1)

    # Rango visible
    if d_from:
        start_view = pd.Timestamp(d_from)
    else:
        start_view = df["__ini__"].min()
    if d_to:
        end_view = pd.Timestamp(d_to)
    else:
        end_view = df["__fin__"].max()

    if pd.isna(start_view) or pd.isna(end_view):
        start_view = pd.Timestamp(date.today()).normalize()
        end_view = start_view + timedelta(days=6)
    if end_view < start_view:
        end_view = start_view

    # Inclusivo
    end_view_inc = end_view + timedelta(days=1)
    num_days = (end_view_inc - start_view).days
    days = [start_view + timedelta(days=i) for i in range(num_days)]

    # Solo tareas que pisan el rango (ya son Series datetime64[ns] → comparables)
    mask_overlap = (~df["__ini__"].isna()) & (~df["__fin__"].isna()) & \
                   (df["__fin__"] >= start_view) & (df["__ini__"] <= end_view)
    view = df.loc[mask_overlap].copy()

    # Leyenda / header
    st.markdown('<div class="gantt-wrap">', unsafe_allow_html=True)
    col_head_l, col_head_r = st.columns([1, 2], gap="small")
    with col_head_l:
        st.markdown("**Cronograma**")
        chips = []
        for k, bg in PALETTE.items():
            chips.append(
                f"<span class='gantt-chip'><span class='gantt-chip-dot' style='background:{bg}'></span>{k}</span>"
            )
        st.markdown(f"<div class='gantt-legend'>{''.join(chips)}</div>", unsafe_allow_html=True)
    with col_head_r:
        st.markdown(
            f"<div style='text-align:right; color:#6B7280; font-size:12px;'>"
            f"{len(view)} tareas en rango ({start_view.date()} – {end_view.date()})</div>",
            unsafe_allow_html=True
        )

    # Cabeceras de días/meses
    cell_px = 34
    days_cols = " ".join([f"{cell_px}px" for _ in days])

    months = []
    last_key, span = None, 0
    for d in days:
        key = (d.year, d.month)
        if key != last_key:
            if last_key is not None:
                months[-1]["span"] = span
            months.append({"label": pd.Timestamp(d).strftime("%b %Y"), "span": 1})
            last_key, span = key, 1
        else:
            span += 1
    if months:
        months[-1]["span"] = span

    header_html = [
        "<div class='gantt-time'>",
        f"<div class='gantt-days' style='grid-template-columns:{days_cols}; margin-left:260px;'>"
    ]
    for m in months:
        header_html.append(
            f"<div class='gantt-month' style='grid-column: span {m['span']};'>{m['label']}</div>"
        )
    header_html.append("</div>")
    header_html.append(
        f"<div class='gantt-days' style='grid-template-columns:{days_cols}; margin-left:260px;'>"
    )
    for d in days:
        header_html.append(f"<div class='gantt-day'>{d.strftime('%d')}</div>")
    header_html.append("</div></div>")
    st.markdown("".join(header_html), unsafe_allow_html=True)

    # Filas
    if view.empty:
        st.markdown("<div class='gantt-empty'>Sin tareas en el rango seleccionado.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    try:
        view = view.sort_values(["Área", "Responsable", "__ini__"], ascending=[True, True, True])
    except Exception:
        pass

    rows_html = ["<div class='gantt-rows'>"]
    for _, r in view.iterrows():
        label_left = f"{str(r.get('Responsable','')).strip()} — {str(r.get('Tarea','')).strip()}"
        estado = str(r.get("Estado", "No iniciado")).strip()
        bg = PALETTE.get(estado, "#E5E7EB")
        bd = BORDER.get(estado, "#9CA3AF")

        ini = max(r["__ini__"], start_view)
        fin = min(r["__fin__"], end_view)
        start_idx = (ini - start_view).days
        span_days = (fin - ini).days + 1

        left_html = f"<div class='gantt-label' title='{label_left}'>{label_left}</div>"
        canvas = (
            f"<div class='gantt-canvas' style='--cellW:{cell_px}px;'>"
            f"<div class='gantt-bar' "
            f"style='left:{start_idx*cell_px}px; width:{max(span_days,1)*cell_px - 6}px; --bg:{bg}; --bd:{bd};' "
            f"title='{estado} | {ini.date()} → {fin.date()}'>"
            f"{estado} · {ini.strftime('%Y-%m-%d')} → {fin.strftime('%Y-%m-%d')}"
            f"</div></div>"
        )
        rows_html.append(f"<div class='gantt-row'><div class='gantt-left'>{left_html}</div><div>{canvas}</div></div>")

    rows_html.append("</div>")
    st.markdown("".join(rows_html), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
