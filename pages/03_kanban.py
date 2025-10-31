# pages/03_kanban.py
import streamlit as st
import pandas as pd
from auth_google import google_login
from shared import init_data, sidebar_userbox, save_local

st.set_page_config(
    page_title="Kanban — ENI2025",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Oculta nav nativo del sidebar
st.markdown("""
<style>
[data-testid="stSidebarNav"]{display:none!important;}
section[data-testid="stSidebar"] nav{display:none!important;}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{display:none!important;}
</style>
""", unsafe_allow_html=True)

# --- Guardia de login ---
auth_cfg = st.secrets.get("auth", {})
allowed_emails  = auth_cfg.get("allowed_emails", []) or None
allowed_domains = auth_cfg.get("allowed_domains", []) or None
user = google_login(
    allowed_emails=allowed_emails,
    allowed_domains=allowed_domains,
    redirect_page=None
)
if not user:
    st.stop()

# --- Sidebar FIJO y coherente ---
with st.sidebar:
    st.header("Secciones")
    st.page_link("pages/02_gestion_tareas.py", label="Gestión de tareas", icon="📁")
    st.page_link("pages/03_kanban.py",         label="Kanban",            icon="🧩")
    st.divider()
    sidebar_userbox(user)

# --- Datos + UI Kanban ---
init_data()
st.title("🧩 Kanban")

dfk = st.session_state["df_main"].copy()
if dfk.empty:
    st.info("No hay tareas aún.")
    st.stop()

LANES = ["No iniciado", "En curso", "Terminado", "Pausado", "Cancelado"]
if "Estado" not in dfk.columns:
    dfk["Estado"] = "No iniciado"

# Vencimiento compuesto si falta
if "Vencimiento" not in dfk.columns:
    fv = pd.to_datetime(dfk.get("Fecha Vencimiento"), errors="coerce")
    hv = dfk.get("Hora Vencimiento", "").astype(str).str.strip()

    def _hhmm_to_time(s: str):
        try:
            if not s or s.lower() in {"nan", "nat", "none", "null"}:
                return "17:00"
            hh, mm = s.split(":")[:2]
            return f"{int(hh):02d}:{int(mm):02d}"
        except Exception:
            return "17:00"

    hv_norm = hv.apply(_hhmm_to_time)
    dfk["Vencimiento"] = pd.to_datetime(
        fv.dt.strftime("%Y-%m-%d") + " " + hv_norm,
        errors="coerce"
    )

# Filtros
c1, c2 = st.columns([1, 1])
areas = ["Todas"] + sorted([x for x in dfk["Área"].astype(str).unique() if x and x != "nan"])
area_f = c1.selectbox("Filtrar por área", areas, index=0)
resps = ["Todos"] + sorted([x for x in dfk["Responsable"].astype(str).unique() if x and x != "nan"])
resp_f = c2.selectbox("Filtrar por responsable", resps, index=0)

if area_f != "Todas":
    dfk = dfk[dfk["Área"].astype(str) == area_f]
if resp_f != "Todos":
    dfk = dfk[dfk["Responsable"].astype(str) == resp_f]

# Estilos tarjetas
st.markdown("""
<style>
  .kb-card{border:1px solid #E5E7EB;border-radius:14px;padding:10px 12px;margin-bottom:10px;background:#fff}
  .kb-title{font-weight:700;margin:0 0 4px 0}
  .kb-sub{font-size:12px;color:#6B7280;margin:0 0 6px 0}
  .kb-tag{display:inline-block;border-radius:10px;padding:2px 8px;background:#F3F4F6;font-size:12px;margin-right:6px}
</style>
""", unsafe_allow_html=True)

def prio_chip(v):
    v = str(v or "").strip()
    color = {"Alta":"#FEE2E2", "Media":"#FEF9C3", "Baja":"#DCFCE7"}.get(v, "#E5E7EB")
    return f"<span class='kb-tag' style='background:{color}'>{v or '—'}</span>"

cols = st.columns(len(LANES), gap="large")

for i, lane in enumerate(LANES):
    with cols[i]:
        st.markdown(f"### {lane}")
        col_df = dfk[dfk["Estado"].astype(str) == lane].copy()
        if "Vencimiento" in col_df.columns:
            col_df["Vencimiento"] = pd.to_datetime(col_df["Vencimiento"], errors="coerce")
            col_df = col_df.sort_values(["Vencimiento", "Id"], na_position="last")
        else:
            col_df = col_df.sort_values(["Id"], na_position="last")

        if col_df.empty:
            st.caption("—")
            continue

        for _, r in col_df.iterrows():
            id_ = str(r.get("Id", ""))
            tit = (str(r.get("Tarea", "")).strip() or "—")
            res = (str(r.get("Responsable", "")).strip() or "—")

            ven_str = "—"
            ven = r.get("Vencimiento", None)
            try:
                d = pd.to_datetime(ven, errors="coerce")
                if pd.notna(d):
                    ven_str = d.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

            pr = prio_chip(r.get("Prioridad", ""))

            st.markdown(
                f"<div class='kb-card'>"
                f"<div class='kb-title'>{id_} · {tit}</div>"
                f"<div class='kb-sub'>👤 {res}</div>"
                f"<div class='kb-sub'>⏰ {ven_str}</div>"
                f"{pr}</div>",
                unsafe_allow_html=True
            )

            with st.form(f"mv_{id_}", clear_on_submit=True):
                new_state = st.selectbox(
                    "Mover a", LANES,
                    index=LANES.index(lane),
                    label_visibility="collapsed",
                    key=f"sel_{id_}"
                )
                moved = st.form_submit_button("Mover", use_container_width=True)

            if moved and new_state != lane:
                df = st.session_state["df_main"].copy()
                m = df["Id"].astype(str) == id_
                if m.any():
                    df.loc[m, "Estado"] = new_state
                    st.session_state["df_main"] = df.copy()
                    save_local()
                    st.success(f"Movida {id_} → {new_state}.")
                    st.rerun()
