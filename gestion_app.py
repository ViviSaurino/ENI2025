APP_PASSWORD = "Inei2025$"

def check_app_password() -> bool:
    """
    Portada tipo hero: BIENVENIDOS + píldora celeste + campo de contraseña.
    Si la contraseña es correcta, marca password_ok y crea un usuario genérico.
    """
    if st.session_state.get("password_ok", False):
        return True

    # Estilos
    st.markdown("""
    <style>
      .eni-hero-wrapper{
        max-width: 1200px;
        margin: 0 auto;          /* centra bloque izquierda + muñecos */
      }
      .eni-hero-title{
        font-size:96px;
        font-weight:800;
        color:#B38CFB;
        line-height:0.80;
        margin-bottom:10px;
      }
      .eni-hero-pill{
        display:block;
        padding:10px 22px;
        border-radius:999px;
        background-color:#E0ECFF;
        color:#2B3A67;
        font-weight:600;
        font-size:14px;
        letter-spacing:0.04em;
        margin-bottom:18px;
        text-align:center;
      }
    </style>
    """, unsafe_allow_html=True)

    # Margen superior sólo en la pantalla de login
    st.markdown("<div style='margin-top:8vh;'></div>", unsafe_allow_html=True)

    # Wrapper centrado
    st.markdown("<div class='eni-hero-wrapper'>", unsafe_allow_html=True)

    # Columnas generales (texto + muñecos)
    col1, col2 = st.columns([1.0, 1.0])

    # --------- Columna izquierda (título + formulario angosto) ----------
    with col1:
        st.markdown("<div class='eni-hero-title'>BIEN<br>VENIDOS</div>", unsafe_allow_html=True)

        # sub-columna angosta: aquí van píldora + input + botón
        form_col, _ = st.columns([0.45, 0.55])   # 0.45 ≈ ancho visual de "VENIDOS"
        with form_col:
            st.markdown("<div class='eni-hero-pill'>GESTIÓN DE TAREAS ENI 2025</div>", unsafe_allow_html=True)
            st.write("")
            pwd = st.text_input("Ingresa la contraseña", type="password", key="eni_pwd")
            if st.button("Ingresar", use_container_width=True):
                if pwd == APP_PASSWORD:
                    st.session_state["password_ok"] = True
                    st.session_state["user_email"] = "eni2025@app"
                    st.session_state["user"] = {"email": "eni2025@app"}
                    st.experimental_rerun()
                else:
                    st.error("Contraseña incorrecta. Vuelve a intentarlo 🙂")

    # --------- Columna derecha (muñequitos) ----------
    with col2:
        hero_video = Path("assets/hero.mp4")
        logo_img   = Path("assets/branding/eni2025_logo.png")

        if hero_video.exists():
            with open(hero_video, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode("utf-8")
            video_html = f"""
            <div style="margin-left:-80px; margin-top:-5px;">
              <video autoplay loop muted playsinline
                     style="width:100%;max-width:520px;
                            display:block;margin:0;">
                <source src="data:video/mp4;base64,{b64}" type="video/mp4">
              </video>
            </div>
            """
            st.markdown(video_html, unsafe_allow_html=True)
        elif logo_img.exists():
            st.image(str(logo_img), use_column_width=True)
        else:
            st.write("")

    st.markdown("</div>", unsafe_allow_html=True)  # cierre .eni-hero-wrapper

    return False
