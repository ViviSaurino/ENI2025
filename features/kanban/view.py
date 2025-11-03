# features/kanban/view.py
from __future__ import annotations

from datetime import datetime
import re
import pandas as pd
import streamlit as st

__all__ = ["render"]

# ====== Helpers ======
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
    if s in {"en curso", "en progreso"}:
        return "En curso"
    if s in {"terminado", "finalizado"}:
        return "Terminado"
    if s in {"pausado"}:
        return "Pausado"
    if s in {"cancelado"}:
        return "Cancelado"
    if s in {"eliminado", "borrado"}:
        return "Eliminado"
    return "No iniciado"


def _render_col(title: str, color_bg: str, cards: list[dict], accent: str | None = None):
    st.markdown(
        f"""
        <div class="kan-col" style="--col-bg:{color_bg}; --col-ac:{accent or 'transparent'};">
            <div class="kan-col__head">
                <div class="kan-col__title">{title}</div>
                <div class="kan-col__count">{len(cards)}</div>
            </div>
        """,
        unsafe_allow_html=True,
    )
    if not cards:
        st.markdown('<div class="kan-card kan-card--empty">Sin tareas</div>', unsafe_allow_html=True)
    else:
        for c in cards:
            title = (c.get("Tarea") or "").strip() or "(sin título)"
            resp = (c.get("Responsable") or "").strip()
            area = (c.get("Área") or "").strip()
            fase = (c.get("Fase") or "").strip()
            venc_f = c.get("Fecha Vencimiento")
            venc_h = c.get("Hora Vencimiento")
            venc_txt = ""
            if pd.notna(venc_f):
                venc_txt = f"{pd.to_datetime(venc_f).date().isoformat()}"
                if isinstance(venc_h, str) and re.match(r"^\\d{1,2}:\\d{2}$", venc_h or ""):
                    venc_txt += f" · {venc_h}"
            meta = " · ".join([x for x in [resp, area or None, fase or None] if x])
            chips = f'<span class="chip">{venc_txt}</span>' if venc_txt else ""
            st.markdown(
                f"""
                <div class="kan-card">
                  <div class="kan-card__title">{title}</div>
                  <div class="kan-card__meta">{meta}</div>
                  <div class="kan-card__chips">{chips}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def render(user: dict | None = None) -> None:
    # ===== CSS =====
    st.markdown(
        """
        <style>
        /* ----- Filtros (misma altura y alineados) ----- */
        .kan-filters .stButton>button{
            height:38px !important; border-radius:10px !important; margin-top:0 !important;
        }
        .kan-filters [data-testid="column"]>div{ display:flex; align-items:end; }

        /* ----- Paleta pastel solicitada ----- */
        :root{
          /* principales */
          --blue-soft:#EAF4FF;   /* celeste claro visible */
          --blue-ac:#B6D7FF;
          --green-soft:#E9FFF5;  /* verde claro */
          --green-ac:#A6F0CD;
          --pink-soft:#FFEAF4;   /* rosado claro */
          --pink-ac:#FFBEDA;

          /* secundarios (ver más) */
          --yellow-soft:#FFF8CC; /* pausado */
          --yellow-ac:#F7DA63;
          --orange-soft:#FFE9D6; /* cancelado */
          --orange-ac:#FFBF8C;
          --red-soft:#FFE3E3;    /* eliminado */
          --red-ac:#FF9AA2;
        }

        /* ----- Kanban layout ----- */
        .kan-row{
          display:grid; grid-template-columns:repeat(3, 1fr); gap:16px;
        }
        .kan-row--more{ margin-top:18px; }
        .kan-col{
          background:var(--col-bg);
          border-radius:14px; padding:10px;
          box-shadow:0 1px 2px rgba(0,0,0,.06);
          border:1px solid rgba(0,0,0,.06);
          border-left:6px solid var(--col-ac);   /* acento visible */
        }
        .kan-col__head{
          display:flex; align-items:center; justify-content:space-between;
          padding:4px 6px 8px 6px; font-weight:600;
        }
        .kan-col__title{ font-size:0.98rem; opacity:.85; }
        .kan-col__count{
          background:#fff; border-radius:999px; min-width:28px; height:24px; 
          display:grid; place-items:center; font-size:.8rem; padding:0 8px;
          box-shadow:0 1px 1px rgba(0,0,0,.05);
        }
        .kan-card{
          background:#fff; border-radius:12px; padding:10px 12px; margin:10px 4px 0 4px;
          box-shadow:0 1px 2px rgba(0,0,0,.05);
        }
        .kan-card--empty{
          color:#8a8f98; font-style:italic; text-align:center; padding:14px; margin:8px 4px 0 4px;
        }
        .kan-card__title{ font-size:.93rem; font-weight:600; margin-bottom:4px; }
        .kan-card__meta{ font-size:.82rem; color:#6b7280; margin-bottom:6px; }
        .kan-card__chips{ display:flex; gap:6px; flex-wrap:wrap; }
        .chip{
          display:inline-block; padding:3px 8px; border-radius:999px; font-size:.75rem;
          background:#f3f4f6; color:#4b5563; border:1px solid #e5e7eb;
        }
        .kan-toggle{ margin-top:6px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ===== Datos base =====
    if "df_main" in st.session_state and isinstance(st.session_state["df_main"], pd.DataFrame):
        df = st.session_state["df_main"].copy()
    else:
        df = pd.DataFrame(
            {
                "Id": [1, 2, 3, 4, 5, 6],
                "Área": ["Gestión", "Metodología", "Gestión", "Monitoreo", "Capacitación", "Gestión"],
                "Fase": ["Diseño", "Validación", "Diseño", "Ejecución", "Cierre", "Diseño"],
                "Responsable": ["Vivi", "Stephany", "Carmen", "Ketty", "Margot", "Vivi"],
                "Tarea": [
                    "Definir indicadores",
                    "Ajustar instrumento",
                    "Revisión ROF",
                    "Carga dashboard",
                    "Informe cierre",
                    "Reunión interna",
                ],
                "Fecha inicio": ["2025-10-01","2025-10-03","2025-10-10","2025-10-15","2025-10-20","2025-10-25"],
                "Fecha Vencimiento": ["2025-11-10"] * 6,
                "Hora Vencimiento": ["17:00"] * 6,
                "Estado": ["No iniciado", "En curso", "No iniciado", "Terminado", "Pausado", "Cancelado"],
            }
        )

    if "Estado" not in df.columns:
        df["Estado"] = ""
    df["__Estado__"] = df["Estado"].map(_classify_estado)

    date_col = "Fecha inicio" if "Fecha inicio" in df.columns else ("Fecha Registro" if "Fecha Registro" in df.columns else None)
    if date_col:
        df[date_col] = df[date_col].map(_to_date)

    # ===== FILTROS =====
    with st.form("kanban_filters", clear_on_submit=False):
        st.markdown('<div class="kan-filters">', unsafe_allow_html=True)
        cA, cF, cR, cD, cH, cB = st.columns([1.8, 2.1, 3.0, 1.6, 1.4, 1.2], gap="medium", vertical_alignment="bottom")

        area_sel = cA.selectbox("Área", ["Todas"] + sorted([x for x in df.get("Área", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"]), index=0)
        fase_sel = cF.selectbox("Fase", ["Todas"] + sorted([x for x in df.get("Fase", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"]), index=0)

        _df_r = df.copy()
        if area_sel != "Todas" and "Área" in _df_r.columns:
            _df_r = _df_r[_df_r["Área"] == area_sel]
        if fase_sel != "Todas" and "Fase" in _df_r.columns:
            _df_r = _df_r[_df_r["Fase"].astype(str) == fase_sel]
        resp_opts = ["Todos"] + sorted([x for x in _df_r.get("Responsable", pd.Series([], dtype=str)).astype(str).unique() if x and x != "nan"])
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

    # ===== KANBAN =====
    # (bg, accent)
    colors_primary = {
        "No iniciado": ("var(--blue-soft)", "var(--blue-ac)"),
        "En curso": ("var(--green-soft)", "var(--green-ac)"),
        "Terminado": ("var(--pink-soft)", "var(--pink-ac)"),
    }
    colors_more = {
        "Pausado": ("var(--yellow-soft)", "var(--yellow-ac)"),
        "Cancelado": ("var(--orange-soft)", "var(--orange-ac)"),
        "Eliminado": ("var(--red-soft)", "var(--red-ac)"),
    }

    buckets = {k: [] for k in list(colors_primary.keys()) + list(colors_more.keys())}
    for _, row in df_view.iterrows():
        k = _classify_estado(row.get("Estado", ""))
        buckets.setdefault(k, [])
        buckets[k].append(row.to_dict())

    st.markdown('<div class="kan-row">', unsafe_allow_html=True)
    cols = st.columns(3)
    for col, k in zip(cols, colors_primary.keys()):
        with col:
            bg, ac = colors_primary[k]
            _render_col(k, bg, buckets.get(k, []), accent=ac)
    st.markdown("</div>", unsafe_allow_html=True)

    show_more = st.session_state.get("kanban_show_more", False)
    if st.button("Ver más" if not show_more else "Ocultar", key="kan_show_more_btn"):
        st.session_state["kanban_show_more"] = not show_more
        st.rerun()
    show_more = st.session_state.get("kanban_show_more", False)

    if show_more:
        st.markdown('<div class="kan-row kan-row--more">', unsafe_allow_html=True)
        cols2 = st.columns(3)
        for col, k in zip(cols2, colors_more.keys()):
            with col:
                bg, ac = colors_more[k]
                _render_col(k, bg, buckets.get(k, []), accent=ac)
        st.markdown("</div>", unsafe_allow_html=True)
