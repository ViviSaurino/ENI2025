# pages/02_Kanban.py
import os, pandas as pd, streamlit as st
from shared import ensure_login, init_data, sidebar_userbox, save_local

st.set_page_config(page_title="Kanban", layout="wide", initial_sidebar_state="expanded")

# ---- Auth + datos compartidos
user = ensure_login()
sidebar_userbox(user)
init_data()

st.title("🧩 Kanban")

dfk = st.session_state["df_main"].copy()
if dfk.empty:
    st.info("No hay tareas aún.")
    st.stop()

# Lanes por Estado (ajusta si usas otra lista)
LANES = ["No iniciado", "En curso", "Terminado", "Pausado", "Cancelado"]
if "Estado" not in dfk.columns:
    dfk["Estado"] = "No iniciado"

# Filtros rápidos
c1, c2 = st.columns([1,1])
areas = ["Todas"] + sorted([x for x in dfk["Área"].astype(str).unique() if x and x!="nan"])
area_f = c1.selectbox("Filtrar por área", areas, index=0)
resps = ["Todos"] + sorted([x for x in dfk["Responsable"].astype(str).unique() if x and x!="nan"])
resp_f = c2.selectbox("Filtrar por responsable", resps, index=0)

if area_f != "Todas":
    dfk = dfk[dfk["Área"].astype(str) == area_f]
if resp_f != "Todos":
    dfk = dfk[dfk["Responsable"].astype(str) == resp_f]

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
            col_df = col_df.sort_values(["Vencimiento","Id"], na_position="last")

        if col_df.empty:
            st.caption("—")
            continue

        for _, r in col_df.iterrows():
            id_ = str(r.get("Id",""))
            tit = str(r.get("Tarea","")).strip() or "—"
            res = str(r.get("Responsable","")).strip() or "—"
            ven = r.get("Vencimiento", "")
            ven_str = "—"
            try:
                if pd.notna(ven):
                    d = pd.to_datetime(ven, errors="coerce")
                    ven_str = d.strftime("%Y-%m-%d %H:%M") if pd.notna(d) else "—"
            except Exception:
                pass
            pr  = prio_chip(r.get("Prioridad",""))

            st.markdown(f"""
            <div class='kb-card'>
              <div class='kb-title'>{id_} · {tit}</div>
              <div class='kb-sub'>👤 {res}</div>
              <div class='kb-sub'>⏰ {ven_str}</div>
              {pr}
            </div>
            """, unsafe_allow_html=True)

            # Mover de estado (simple y estable)
            with st.form(f"mv_{id_}", clear_on_submit=True):
                new_state = st.selectbox("Mover a", LANES, index=LANES.index(lane), label_visibility="collapsed", key=f"sel_{id_}")
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
