from datetime import date
import pandas as pd
import streamlit as st

from core.models import Reserva
from core.repositories import ReservasRepo, DepartamentosRepo
from core.utils import calcular_noches, moneda, filter_dataframe


def ui_reservas(repo_reservas: ReservasRepo, repo_departamentos: DepartamentosRepo):
    st.header("📅 Reservas")

    # ===================== Carga de departamentos y mapeos =====================
    deps_df = repo_departamentos.list_all()
    if deps_df.empty:
        st.warning("Primero registra al menos un departamento.")
        return

    # numero -> codigo (int)  |  codigo -> numero (str)
    numero_to_codigo = {str(r["numero"]): int(r["codigo"]) for _, r in deps_df.iterrows()}
    codigo_to_numero = {int(r["codigo"]): str(r["numero"]) for _, r in deps_df.iterrows()}
    dep_opciones = sorted(numero_to_codigo.keys(), key=lambda x: (len(x), x))  # orden humano

    # ===================== Estado del formulario (alta/edición) =====================
    state_key = "_res_state"
    if state_key not in st.session_state:
        st.session_state[state_key] = {}
    R = st.session_state[state_key]
    # Defaults
    R.setdefault("edit_numero", None)                                 # PK de reservas.numero al editar
    R.setdefault("abono_para", None)                                  # N° de reserva seleccionada para abonar
    R.setdefault("fecha_reg", date.today())                           # r.fecha
    R.setdefault("id_cli", "")
    R.setdefault("nombre_cli", "")
    R.setdefault("ciudad", "")
    R.setdefault("celular", "")
    R.setdefault("dep_num", "7" if "7" in dep_opciones else dep_opciones[0])
    R.setdefault("f_ini", date.today())
    R.setdefault("f_fin", date.today())
    R.setdefault("valor_noche", 60.0)
    R.setdefault("valor_limpieza", 20.0)
    R.setdefault("comision", 0.0)
    R.setdefault("numero_personas", 1)
    R.setdefault("estado", "Pendiente")

    # ===================== Formulario arriba =====================
    st.subheader("Formulario")

    with st.form("form_reserva", clear_on_submit=False):
        # FILA 1
        c1, c2, c3 = st.columns(3)
        with c1:
            R["fecha_reg"] = st.date_input("Fecha de registro", value=R["fecha_reg"], key="r_fecha_reg")
        with c2:
            R["id_cli"] = st.text_input("ID Cliente (opcional)", value=R["id_cli"], key="r_id_cli")
        with c3:
            R["nombre_cli"] = st.text_input("Nombre del cliente", value=R["nombre_cli"], key="r_nombre_cli")

        # FILA 2
        c1, c2, c3 = st.columns(3)
        with c1:
            R["ciudad"] = st.text_input("Ciudad", value=R["ciudad"], key="r_ciudad")
        with c2:
            R["celular"] = st.text_input("Celular", value=R["celular"], key="r_celular")
        with c3:
            # Departamento por número visible
            idx_def = dep_opciones.index(R["dep_num"]) if R["dep_num"] in dep_opciones else 0
            R["dep_num"] = st.selectbox("Departamento", dep_opciones, index=idx_def, key="r_dep_num")

        # FILA 3
        c1, c2, c3 = st.columns(3)
        with c1:
            R["f_ini"] = st.date_input("Fecha inicio", value=R["f_ini"], key="r_f_ini")
        with c2:
            R["f_fin"] = st.date_input("Fecha fin", value=R["f_fin"], key="r_f_fin")
        with c3:
            # Editor tipo dinero (en grilla NumberColumn con formato; aquí number_input)
            R["valor_noche"] = st.number_input("Valor por noche", min_value=0.0, value=float(R["valor_noche"]), step=5.0, key="r_valor_noche")

        # FILA 4 (resumen + importes)
        noches = calcular_noches(R["f_ini"], R["f_fin"])
        total_estadia = noches * float(R["valor_noche"])

        c1, c2, c3 = st.columns(3)
        with c1:
            R["valor_limpieza"] = st.number_input("Valor limpieza", min_value=0.0, value=float(R["valor_limpieza"]), step=1.0, key="r_valor_limpieza")
        with c2:
            R["comision"] = st.number_input("Comisión (valor)", min_value=0.0, value=float(R["comision"]), step=1.0, key="r_comision")
        with c3:
            R["numero_personas"] = st.number_input("Número de personas", min_value=1, value=int(R["numero_personas"]), step=1, key="r_num_personas")

        # FILA 5 (estado)
        c1, _, _ = st.columns(3)
        with c1:
            R["estado"] = st.selectbox("Estado", ["Pendiente", "Confirmada", "Completada", "Cancelada"], index=["Pendiente","Confirmada","Completada","Cancelada"].index(R["estado"]))

        st.info(
            f"**Noches:** {noches} | "
            f"**Total estadía:** {moneda(total_estadia)} | "
            f"**Total aprox.:** {moneda(total_estadia + float(R['valor_limpieza']))}"
        )

        b1, b2 = st.columns([1, 1])
        guardar = b1.form_submit_button("💾 Guardar")
        limpiar = b2.form_submit_button("🧹 Limpiar")

    # Guardar (INSERT/UPDATE)
    if guardar:
        if not R["nombre_cli"].strip():
            st.warning("Ingresa el nombre del cliente.")
        elif R["f_fin"] < R["f_ini"]:
            st.error("La fecha fin no puede ser anterior a la fecha inicio.")
        else:
            noches = calcular_noches(R["f_ini"], R["f_fin"])
            total_estadia = noches * float(R["valor_noche"])
            cod_dep = numero_to_codigo[R["dep_num"]]

            if R["edit_numero"]:
                # UPDATE
                repo_reservas.db.run(
                    """
                    UPDATE reservas
                       SET fecha=?, idCliente=?, nombreCliente=?, ciudad=?, celular=?,
                           codigoDepartamento=?, fechaInicio=?, fechaFin=?, numeroNoches=?,
                           valorNoche=?, totalEstadia=?, valorLimpieza=?, comision=?,
                           numeroPersonas=?, estado=?
                     WHERE numero=?;
                    """,
                    (
                        str(R["fecha_reg"]),
                        R["id_cli"].strip() or None,
                        R["nombre_cli"].strip(),
                        R["ciudad"].strip() or None,
                        R["celular"].strip() or None,
                        int(cod_dep),
                        str(R["f_ini"]),
                        str(R["f_fin"]),
                        int(noches),
                        float(R["valor_noche"]),
                        float(total_estadia),
                        float(R["valor_limpieza"]),
                        float(R["comision"]),
                        int(R["numero_personas"]),
                        R["estado"],
                        int(R["edit_numero"])
                    )
                )
                st.success(f"Reserva #{R['edit_numero']} actualizada.")
            else:
                # INSERT
                repo_reservas.insert(Reserva(
                    fecha=R["fecha_reg"],
                    idCliente=R["id_cli"].strip() or None,
                    nombreCliente=R["nombre_cli"].strip(),
                    ciudad=R["ciudad"].strip() or None,
                    celular=R["celular"].strip() or None,
                    codigoDepartamento=int(cod_dep),
                    fechaInicio=R["f_ini"],
                    fechaFin=R["f_fin"],
                    numeroNoches=int(noches),
                    valorNoche=float(R["valor_noche"]),
                    totalEstadia=float(total_estadia),
                    valorLimpieza=float(R["valor_limpieza"]),
                    comision=float(R["comision"]),
                    numeroPersonas=int(R["numero_personas"]),
                    estado=R["estado"]
                ))
                st.success(f"Reserva registrada para {R['nombre_cli']} en depto {R['dep_num']}.")

            # Limpiar estado y recargar
            R["edit_numero"] = None
            R["id_cli"] = ""
            R["nombre_cli"] = ""
            R["ciudad"] = ""
            R["celular"] = ""
            R["dep_num"] = "7" if "7" in dep_opciones else dep_opciones[0]
            R["f_ini"] = date.today()
            R["f_fin"] = date.today()
            R["valor_noche"] = 60.0
            R["valor_limpieza"] = 20.0
            R["comision"] = 0.0
            R["numero_personas"] = 1
            R["estado"] = "Pendiente"
            R["fecha_reg"] = date.today()
            R["abono_para"] = None
            st.rerun()

    if limpiar:
        R["edit_numero"] = None
        R["id_cli"] = ""
        R["nombre_cli"] = ""
        R["ciudad"] = ""
        R["celular"] = ""
        R["dep_num"] = "7" if "7" in dep_opciones else dep_opciones[0]
        R["f_ini"] = date.today()
        R["f_fin"] = date.today()
        R["valor_noche"] = 60.0
        R["valor_limpieza"] = 20.0
        R["comision"] = 0.0
        R["numero_personas"] = 1
        R["estado"] = "Pendiente"
        R["fecha_reg"] = date.today()
        R["abono_para"] = None
        st.rerun()

    # ======================= EXPANDER ABONO (A1) =======================
    if R["abono_para"] is not None:
        with st.expander(f"💰 Registrar abono para la reserva #{R['abono_para']}", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                ab_fecha = st.date_input("Fecha del abono", value=date.today(), key="ab_fecha")
            with c2:
                ab_monto = st.number_input("Monto", min_value=0.0, value=0.0, step=1.0, key="ab_monto")
            ab_detalle = st.text_input("Detalle (opcional)", key="ab_detalle")

            if st.button("💾 Registrar abono"):
                if ab_monto <= 0:
                    st.warning("El monto debe ser mayor a cero.")
                else:
                    repo_reservas.insert_abono(
                        numero_reserva=int(R["abono_para"]),
                        fecha=ab_fecha,
                        monto=ab_monto,
                        detalle=ab_detalle
                    )
                    st.success("Abono registrado.")
                    R["abono_para"] = None
                    st.rerun()

    # ======================= LISTADO (con filtros + grid único) =======================
    st.subheader("Listado (editable + acciones)")
    df = repo_reservas.list_all()  # incluye 'departamento' visible

    if df.empty:
        st.info("No hay reservas registradas.")
        return

    # Asegurar tipos para fechas
    for col in ["fecha", "fechaInicio", "fechaFin"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Filtros por columna
    dff = filter_dataframe(df, title="Filtros de reservas")

    # Validación numérica previa
    for col in ["valorNoche", "totalEstadia", "valorLimpieza", "comision"]:
        if col in dff.columns:
            dff[col] = pd.to_numeric(dff[col], errors="coerce").fillna(0.0)
    if "numeroNoches" in dff.columns:
        dff["numeroNoches"] = pd.to_numeric(dff["numeroNoches"], errors="coerce").fillna(0).astype(int)
    if "numeroPersonas" in dff.columns:
        dff["numeroPersonas"] = pd.to_numeric(dff["numeroPersonas"], errors="coerce").fillna(1).astype(int)

    # >>> NUEVO: total abonado y saldo pendiente (col calculadas)
    dff["totalAbonos"] = dff["numero"].apply(lambda n: repo_reservas.total_abonos(int(n)))
    dff["saldoPendiente"] = dff["numero"].apply(lambda n: repo_reservas.saldo_pendiente(int(n)))

    # Columna de Acciones
    if "Acción" not in dff.columns:
        dff["Acción"] = "—"

    # Column configs
    estados_permitidos = ["Pendiente", "Confirmada", "Completada", "Cancelada"]

    # Intentamos usar SelectboxColumn (fallback a TextColumn si no disponible)
    try:
        estado_col = st.column_config.SelectboxColumn(
            "estado",
            options=estados_permitidos,
            help="Estado de la reserva",
        )
        accion_col = st.column_config.SelectboxColumn(
            "Acción",
            options=["—", "✏️ Editar", "💰 Abonar", "🗑️ Eliminar"],
            help="Selecciona acción por fila y luego 'Aplicar acciones (Reservas)'."
        )
    except Exception:
        estado_col = st.column_config.TextColumn("estado", help="Valores: Pendiente/Confirmada/Completada/Cancelada")
        accion_col = st.column_config.TextColumn("Acción", help="Escribe: ✏️ Editar / 💰 Abonar / 🗑️ Eliminar")

    # ---- evitar scroll horizontal en el grid ----    
    st.markdown("""
        <style>
            div[data-testid="stDataFrame"] table {
                width: 100% !important;
            }
            div[data-testid="stDataFrame"] th, 
            div[data-testid="stDataFrame"] td {
                white-space: nowrap;
            }
        </style>
    """, unsafe_allow_html=True)

    edited = st.data_editor(
        dff,
        key="res_grid",
        use_container_width=True,
        hide_index=True,
        num_rows=5,
        height=200, 
        column_config={
            "numero": st.column_config.NumberColumn("N°", disabled=True),
            "fecha": st.column_config.DateColumn("Fecha registro", disabled=True),
            "idCliente": st.column_config.TextColumn("ID Cliente"),
            "nombreCliente": st.column_config.TextColumn("Cliente", max_chars=120),
            "ciudad": st.column_config.TextColumn("Ciudad", max_chars=120),
            "celular": st.column_config.TextColumn("Celular", max_chars=120),
            "departamento": st.column_config.TextColumn("Departamento", disabled=True),
            "fechaInicio": st.column_config.DateColumn("Inicio"),
            "fechaFin": st.column_config.DateColumn("Fin"),
            "numeroNoches": st.column_config.NumberColumn("Noches", disabled=True, step=1),
            "valorNoche": st.column_config.NumberColumn("Valor noche", min_value=0.0, step=1.0, format="$ %.2f"),
            "totalEstadia": st.column_config.NumberColumn("Total estadía", disabled=True, format="$ %.2f"),
            "valorLimpieza": st.column_config.NumberColumn("Limpieza", min_value=0.0, step=1.0, format="$ %.2f"),
            "comision": st.column_config.NumberColumn("Comisión", min_value=0.0, step=1.0, format="$ %.2f"),
            "numeroPersonas": st.column_config.NumberColumn("Personas", min_value=1, step=1),
            "estado": estado_col,
            "totalAbonos": st.column_config.NumberColumn("Abonado", disabled=True, format="$ %.2f"),
            "saldoPendiente": st.column_config.NumberColumn("Saldo pendiente", disabled=True, format="$ %.2f"),
            "Acción": accion_col,
        },
    )

    # ======================= Guardar cambios in-line =======================
    if st.button("⬆️ Guardar cambios (Reservas)"):
        base = dff.merge(edited, on="numero", suffixes=("_old", "_new"))

        # Campos editables que vamos a vigilar
        campos = [
            "idCliente", "nombreCliente", "ciudad", "celular",
            "fechaInicio", "fechaFin", "valorNoche", "valorLimpieza",
            "comision", "numeroPersonas", "estado"
        ]

        # Normalizar tipos de fecha en el DF cambiado
        for col in ["fechaInicio_new", "fechaFin_new", "fechaInicio_old", "fechaFin_old"]:
            if col in base.columns:
                base[col] = pd.to_datetime(base[col], errors="coerce")

        # Detectar filas con cambios
        mask_cambio = False
        for c in campos:
            co, cn = f"{c}_old", f"{c}_new"
            if co in base.columns and cn in base.columns:
                mask_cambio = mask_cambio | (base[co].astype(str) != base[cn].astype(str))

        cambios = base[mask_cambio].copy()

        if cambios.empty:
            st.info("No hay cambios para guardar.")
        else:
            for _, r in cambios.iterrows():
                # datos nuevos
                fi = pd.to_datetime(r["fechaInicio_new"]).date() if pd.notna(r["fechaInicio_new"]) else None
                ff = pd.to_datetime(r["fechaFin_new"]).date() if pd.notna(r["fechaFin_new"]) else None
                if fi is None or ff is None:
                    st.error(f"La fila #{int(r['numero'])} tiene fechas inválidas.")
                    continue
                if ff < fi:
                    st.error(f"La fila #{int(r['numero'])} tiene 'Fin' anterior a 'Inicio'.")
                    continue

                noches = calcular_noches(fi, ff)
                total = noches * float(r["valorNoche_new"] or 0.0)

                repo_reservas.db.run(
                    """
                    UPDATE reservas
                       SET idCliente=?, nombreCliente=?, ciudad=?, celular=?,
                           fechaInicio=?, fechaFin=?, numeroNoches=?,
                           valorNoche=?, totalEstadia=?, valorLimpieza=?, comision=?,
                           numeroPersonas=?, estado=?
                     WHERE numero=?;
                    """,
                    (
                        str(r["idCliente_new"] or "") or None,
                        str(r["nombreCliente_new"] or ""),
                        str(r["ciudad_new"] or "") or None,
                        str(r["celular_new"] or "") or None,
                        str(fi),
                        str(ff),
                        int(noches),
                        float(r["valorNoche_new"] or 0.0),
                        float(total),
                        float(r["valorLimpieza_new"] or 0.0),
                        float(r["comision_new"] or 0.0),
                        int(r["numeroPersonas_new"] or 1),
                        str(r["estado_new"] or "Pendiente"),
                        int(r["numero"])
                    )
                )
            st.success(f"Se guardaron {len(cambios)} cambio(s).")
            st.rerun()

    # ======================= Acciones por fila (Editar / Abonar / Eliminar) =======================
    cA1, cA2 = st.columns([1, 5])
    with cA1:
        seguro_del = st.checkbox("Confirmo eliminación", value=False, help="Requerido para '🗑️ Eliminar'")
    with cA2:
        if st.button("⚡ Aplicar acciones (Reservas)", use_container_width=True):
            act = edited[edited["Acción"].isin(["✏️ Editar", "💰 Abonar", "🗑️ Eliminar"])].copy()
            if act.empty:
                st.info("No hay acciones seleccionadas.")
            else:
                # 1) Eliminar primero (si corresponde)
                dels = act[act["Acción"] == "🗑️ Eliminar"]
                if not dels.empty:
                    if not seguro_del:
                        st.warning("Marca 'Confirmo eliminación' para ejecutar eliminaciones.")
                    else:
                        for _, r in dels.iterrows():
                            repo_reservas.db.run("DELETE FROM reservas WHERE numero=?;", (int(r["numero"]),))
                        st.success(f"Eliminado(s): {len(dels)} reserva(s).")
                        st.rerun()

                # 2) Abonar (última marcada)
                abns = act[act["Acción"] == "💰 Abonar"]
                if not abns.empty:
                    r = abns.iloc[-1]
                    R["abono_para"] = int(r["numero"])
                    st.info(f"Abonar reserva #{R['abono_para']}")
                    st.rerun()

                # 3) Cargar para Editar (última marcada)
                eds = act[act["Acción"] == "✏️ Editar"]
                if not eds.empty:
                    r = eds.iloc[-1]
                    # Cargar en formulario
                    R["edit_numero"] = int(r["numero"])
                    R["fecha_reg"] = pd.to_datetime(r["fecha"]).date() if pd.notna(r["fecha"]) else date.today()
                    R["id_cli"] = str(r["idCliente"] or "")
                    R["nombre_cli"] = str(r["nombreCliente"] or "")
                    R["ciudad"] = str(r["ciudad"] or "")
                    R["celular"] = str(r["celular"] or "")
                    # departamento no editable desde grid → usamos el mostrado
                    dep_num_vis = str(r["departamento"])
                    R["dep_num"] = dep_num_vis if dep_num_vis in dep_opciones else (dep_opciones[0])
                    R["f_ini"] = pd.to_datetime(r["fechaInicio"]).date() if pd.notna(r["fechaInicio"]) else date.today()
                    R["f_fin"] = pd.to_datetime(r["fechaFin"]).date() if pd.notna(r["fechaFin"]) else date.today()
                    R["valor_noche"] = float(r["valorNoche"] or 0.0)
                    R["valor_limpieza"] = float(r["valorLimpieza"] or 0.0)
                    R["comision"] = float(r["comision"] or 0.0)
                    R["numero_personas"] = int(r["numeroPersonas"] or 1)
                    R["estado"] = str(r["estado"] or "Pendiente")
                    st.info(f"Fila #{R['edit_numero']} cargada en el formulario superior.")
                    st.rerun()