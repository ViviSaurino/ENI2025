if section == "📘 Gestión de tareas":
    # Cabecera lila (sin círculo con inicial)
    dn = st.session_state.get("user_display_name", "Usuario")

    st.markdown(f"""
    <div class="eni-main-hero">
      <div class="eni-main-hero-left">
        <div class="eni-main-hero-left-title">Bienvenid@</div>
        <div class="eni-main-hero-left-name">{dn}</div>
        <p class="eni-main-hero-left-sub">
          A la plataforma unificada para gestión - ENI2025
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # 3 tarjetas fila 1
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        st.markdown(_quick_card("Nueva tarea", "Registrar una nueva tarea asignada."), unsafe_allow_html=True)
    with col_a2:
        st.markdown(_quick_card("Editar estado", "Actualizar fases y fechas de las tareas."), unsafe_allow_html=True)
    with col_a3:
        st.markdown(_quick_card("Nueva alerta", "Registrar alertas y riesgos prioritarios."), unsafe_allow_html=True)

    # 3 tarjetas fila 2
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        st.markdown(_quick_card("Prioridad", "Revisar y ajustar la prioridad de tareas."), unsafe_allow_html=True)
    with col_b2:
        st.markdown(_quick_card("Evaluación", "Calificar la evaluación de avances."), unsafe_allow_html=True)
    with col_b3:
        st.markdown(_quick_card("Cumplimiento", "Visualizar el nivel de cumplimiento."), unsafe_allow_html=True)

    # 1 tarjeta fila 3
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        _quick_card("Tareas recientes", "Resumen de las últimas tareas actualizadas."),
        unsafe_allow_html=True
    )
