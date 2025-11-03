# features/kanban/view.py
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List

import pandas as pd
import streamlit as st
from plotly import graph_objects as go

__all__ = ["render"]

# =========================
# Utilitarios
# =========================
def _to_date(v):
    if pd.isna(v):
        return pd.NaT
    try:
        return pd.to_datetime(v).normalize()
    except Exception:
        try:
            return pd.to_datetime(str(v), errors="coerce").normalize()
        except Exception:
            return pd.NaT

def _classify_estado(raw: str) -> str:
    s = (str(raw) or "").strip().lower()
    if s in {"en curso", "en progreso", "progreso"}:
        return "En curso"
    if s in {"terminado", "finalizado", "completado"}:
        return "Terminado"
    if s in {"pausado"}:
        return "Pausado"
    if s in {"cancelado"}:
        return "Cancelado"
    if s in {"eliminado", "borrado"}:
        return "Eliminado"
    return "No iniciado"

# =========================
# UI helpers
# =========================
def _emit_css():
    st.markdown(
        """
        <style>
        /* ===== Paleta pastel ===== */
        :root{
          /* principales */
          --blue-soft:#EAF4FF;   --blue-ac:#7BB5FF;
          --green-soft:#E9FFF5;  --green-ac:#6ED3B6;
          --pink-soft:#FFEAF4;   --pink-ac:#F6A6C1;
          /* secundarios (ver más) */
          --yellow-soft:#FFF8CC; --yellow-ac:#F7DA63;
          --orange-soft:#FFE9D6; --orange-ac:#FFBF8C;
          --red-soft:#FFE3E3;    --red-ac:#FF9AA2;
          --text-600:#374151; --text-500:#4B5563; --muted:#6B7280;
          --card:#FFFFFF; --border:rgba(0,0,0,.08); --shadow:0 1px 2px rgba(0,0,0,.06);
        }

        /* ===== Filtros ===== */
        .kan-filters [data-testid="column"]>div{ display:flex; align-items:end; }
        .kan-filters .stButton>button{ height:38px !important; border-radius:10px !important; }

        /* ===== Donut card ===== */
        .kan-donut{
          background:var(--card); border:1px solid var(--border);
          border-radius:14px; padding:12px; box-shadow:var(--shadow); margin-top:6px;
        }

        /* ===== Kanban ===== */
        .kan-row{ display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; }
        .kan-row--more{ margin-top:18px; }

        .kan-col{
          background:var(--col-bg); border:1px solid var(--border);
          border-radius:14px; padding:10px; box-shadow:var(--shadow);
          border-left:6px solid var(--col-ac);
        }
        .kan-col__head{
          display:flex; align-items:center; justify-content:space-between;
          padding:6px 6px 8px 6px;
        }
        .kan-col__title{ font-weight:700; color:var(--text-600); font-size:0.98rem; display:flex; gap:8px; align-items:center;}
        .kan-col__right{ display:flex; gap:8px; align-items:center; color:var(--muted); }
        .kan-col__pill{ background:#fff; border:1px solid var(--border); border-radius:999px; padding:2px 10px; font-size:.82rem; color:var(--text-500); }
        .kan-col__pct{ font-size:.82rem; opacity:.8; }

        .kan-card{
          background:#fff; border:1px solid var(--border);
          border-radius:12px; padding:10px 12px; margin:10px 4px 0 4px; box-shadow:var(--shadow);
        }
        .kan-card--empty{ color:#8a8f98; font-style:italic; text-align:center; padding:14px; }

        .chip{ display:inline-block; padding:3px 8px; border-radius:999px; font-size:.75rem;
               background:#f3f4f6; color:#4b5563; border:1px solid #e5e7eb; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def _column_header(title: str, icon: str, total: int, pct: float):
    st.markdown(
        f"""
        <div class="kan-col__head">
          <div class="kan-col__title">{icon} {title}</div>
          <div class="kan-col__right">
            <div class="kan-col__pill">{total}</div>
            <div class="kan-col__pct">{pct:.1f}%</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _render_col(title: str, icon: str, color_bg: str, color_ac: str, cards: List[Dict], pct: float):
    st.markdown(f'<div class="kan-col" style="--col-bg:{color_bg}; --col-ac:{color_ac};">', unsafe_allow_html=True)
    _column_header(title, icon, len(cards), pct)
    if not cards:
        st.markdown('<div class="kan-card kan-card--empty">Sin tareas</div>', unsafe_allow_html=True)
    else:
        for c in cards:
            title = (c.get("Tarea") or "").strip() or "(sin título)"
            resp = (c.get("Responsable") or "").strip()
            area = (c.get("Área") or "").strip()
            fase = (c.get("Fase") or "").strip()
            v_f = c.get("Fecha Vencimiento")
            v_h = c.get("Hora Vencimiento")
            venc_txt = ""
            if pd.notna(v_f):
                try:
                    venc_txt = f"{pd.to_datetime(v_f).date().isoformat()}"
                except Exception:
                    pass
            if isinstance(v_h, str) and re.match(r"^\\d{1,2}:\\d{2}$", v_h or ""):
                venc_txt = (venc_txt + f" · {v_h}").strip(" ·")
            meta = " · ".join([x for x in [resp, area or None, fase or None] if x])

            st.markdown(
                f"""
                <div class="kan-card">
                  <div style="font-weight:600; color:var(--text-600); margin-bottom:4px;">{title}</div>
                  <div style="font-size:.82rem; color:#6b7280; margin-bottom:6px;">{meta}</div>
                  <div class="chip">{venc_txt or "Sin vencimiento"}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

def _donut_chart(summary: Dict[str, int], palette: Dict[str, str]):
    total = sum(summary.values()) or 1
    labels = ["No iniciado", "En curso", "Terminado"]
    values = [summary.get(k, 0) for k in labels]
    colors = [palette[k] for k in labels]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors, line=dict(color="white", width=2)),
                textinfo="percent",
                hovertemplate="%{label}: %{value}<extra></extra>",
                sort=False,
            )
        ]
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="v", y=0.5, yanchor="middle", x=1.05),
        margin=dict(l=10, r=10, t=10, b=10),
        height=280,
        annotations=[
            dict(
                text=f"{total}<br>Tareas",
                x=0.5, y=0.5, font=dict(size=13, color="#111"),
                showarrow=False
            )
        ],
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)

# =========================
# Render principal
# =========================
def render(user: dict | None = None):
    _emit_css()

    st.markdown("<h2>📑 Kanban</h2>", unsafe_allow_html=True)

    # ------- Datos base -------
    if "df_main" in st.session_state and isinstance(st.session_state["df_main"], pd.DataFrame):
        df = st.session_state["df_main"].copy()
    else:
        df = pd.DataFrame(columns=[
            "Id","Área","Fase","Responsable","Tarea","Fecha inicio","Fecha Vencimiento","Hora Vencimiento","Estado"
        ])

    # Normalizar estado
    if "Estado" not in df.columns:
        df["Estado"] = ""
    df["__Estado__"] = df["Estado"].map(_classify_estado)

    # Columna de fecha para filtros
    date_col = "Fecha inicio" if "Fecha inicio" in df.columns else ("Fecha Registro" if "Fecha Registro" in df.columns else None)
    if date_col:
        df[date_col] = df[date_col].map(_to_date)

    # ------- Filtros -------
    with st.form("kanban_filters", clear_on_submit=False):
        st.markdown('<div class="kan-filters">', unsafe_allow_html=True)
        cA, cF, cR, cD, cH, cB = st.columns([1.8, 2.1, 3.0, 1.6, 1.4, 1.2], gap="medium", vertical_alignment="bottom")

        area_sel = cA.selectbox("Área", ["Todas"] + sorted([x for x in df.get("Área", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"]), index=0)
        fase_sel = cF.selectbox("Fase", ["Todas"] + sorted([x for x in df.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"]), index=0)

        df_r = df.copy()
        if area_sel != "Todas" and "Área" in df_r.columns:
            df_r = df_r[df_r["Área"] == area_sel]
        if fase_sel != "Todas" and "Fase" in df_r.columns:
            df_r = df_r[df_r["Fase"].astype(str) == fase_sel]
        resp_opts = ["Todos"] + sorted([x for x in df_r.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
        resp_sel = cR.selectbox("Responsable", resp_opts, index=0)

        f_desde = cD.date_input("Desde", value=None)
        f_hasta = cH.date_input("Hasta", value=None)

        do_search = cB.form_submit_button("🔎 Buscar", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    df_view = df.copy()
    if do_search:
        if area_sel != "Todas" and "Área" in df_view.columns:
            df_view = df_view[df_view["Área"] == area_sel]
        if fase_sel != "Todas" and "Fase" in df_view.columns:
            df_view = df_view[df_view["Fase"].astype(str) == fase_sel]
        if resp_sel != "Todos" and "Responsable" in df_view.columns:
            df_view = df_view[df_view["Responsable"].astype(str) == resp_sel]
        if date_col:
            if f_desde:
                df_view = df_view[df_view[date_col].dt.date >= f_desde]
            if f_hasta:
                df_view = df_view[df_view[date_col].dt.date <= f_hasta]

    # ------- Resumen por estado -------
    main_states = ["No iniciado", "En curso", "Terminado"]
    extra_states = ["Pausado", "Cancelado", "Eliminado"]

    counts = df_view["__Estado__"].value_counts().to_dict() if len(df_view) else {}
    total = sum(counts.get(s, 0) for s in main_states + extra_states) or 1

    # Paleta para donut y columnas principales
    palette_for_donut = {
        "No iniciado": "#B6D7FF",
        "En curso": "#6ED3B6",
        "Terminado": "#F6A6C1",
    }

    # ------- Dona arriba del tablero -------
    st.markdown('<div class="kan-donut">', unsafe_allow_html=True)
    st.markdown("**Distribución por estado (∑ principales)**")
    _donut_chart({k: counts.get(k, 0) for k in main_states}, palette_for_donut)
    st.markdown("</div>", unsafe_allow_html=True)

    # ------- Construcción de buckets -------
    buckets = {k: [] for k in main_states + extra_states}
    for _, row in df_view.iterrows():
        k = _classify_estado(row.get("Estado", ""))
        buckets.setdefault(k, [])
        buckets[k].append(row.to_dict())

    # ------- Kanban: 3 principales -------
    st.markdown('<div class="kan-row">', unsafe_allow_html=True)
    cols = st.columns(3)

    main_colors = {
        "No iniciado": ("var(--blue-soft)", "var(--blue-ac)", "⏳"),
        "En curso": ("var(--green-soft)", "var(--green-ac)", "🚀"),
        "Terminado": ("var(--pink-soft)", "var(--pink-ac)", "✅"),
    }

    for col, k in zip(cols, main_states):
        with col:
            bg, ac, ico = main_colors[k]
            pct = 100.0 * (counts.get(k, 0) / total) if total else 0.0
            _render_col(k, ico, bg, ac, buckets[k], pct)

    st.markdown("</div>", unsafe_allow_html=True)

    # ------- Ver más -------
    show_more = st.session_state.get("kanban_show_more", False)
    if st.button("Ver más" if not show_more else "Ocultar"):
        st.session_state["kanban_show_more"] = not show_more
        st.rerun()
    show_more = st.session_state.get("kanban_show_more", False)

    if show_more:
        st.markdown('<div class="kan-row kan-row--more">', unsafe_allow_html=True)
        cols2 = st.columns(3)
        extra_colors = {
            "Pausado": ("var(--yellow-soft)", "var(--yellow-ac)", "⏸️"),
            "Cancelado": ("var(--orange-soft)", "var(--orange-ac)", "🛑"),
            "Eliminado": ("var(--red-soft)", "var(--red-ac)", "🗑️"),
        }
        for col, k in zip(cols2, extra_states):
            with col:
                bg, ac, ico = extra_colors[k]
                pct = 100.0 * (counts.get(k, 0) / total) if total else 0.0
                _render_col(k, ico, bg, ac, buckets[k], pct)
        st.markdown("</div>", unsafe_allow_html=True)
