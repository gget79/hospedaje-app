from __future__ import annotations

from datetime import date
import streamlit as st
import pandas as pd

from core.models import Propietario, Departamento, ConceptoGasto, Gasto
from core.repositories import (
    PropietariosRepo, DepartamentosRepo, ConceptoGastosRepo, GastosRepo
)
from core.utils import filter_dataframe, moneda


# -----------------------------------------------------------
# Utilitarios locales (estado para “editar en formulario”)
# -----------------------------------------------------------
def _get_state(ns: str):
    key = f"_cat_state_{ns}"
    if key not in st.session_state:
        st.session_state[key] = {}
    return st.session_state[key]


# ===========================================================
#  PROPIETARIOS
# ===========================================================
def ui_cat_propietarios(repo_propietarios: PropietariosRepo):
    st.header("🧑‍💼 Catálogos → Propietarios")

    state = _get_state("propietarios")
    state.setdefault("codigo", None)
    state.setdefault("nombre", "")

    # ----------------- Formulario -----------------
    st.subheader("Formulario")
    colf1, colf2 = st.columns([3, 1])
    with colf1:
        nombre = st.text_input(
            "Nombre y apellido",
            value=state["nombre"],
            key="prop_input",
        )
    with colf2:
        modo = "Editar" if state["codigo"] else "Registrar"

    colA, colB = st.columns([1, 1])

    # GUARDAR
    if colA.button(f"💾 {modo} propietario", use_container_width=True):
        if not nombre.strip():
            st.warning("Ingresa el nombre.")
        else:
            if state["codigo"]:  # UPDATE
                repo_propietarios.db.run(
                    "UPDATE propietarios SET nombre=? WHERE codigo=?;",
                    (nombre.strip(), int(state["codigo"]))
                )
            else:  # INSERT
                repo_propietarios.insert(Propietario(nombre=nombre.strip()))

            # limpiar estado
            state["codigo"] = None
            state["nombre"] = ""

            st.rerun()

    # LIMPIAR
    if colB.button("🧹 Limpiar formulario", use_container_width=True):
        state["codigo"] = None
        state["nombre"] = ""
        st.rerun()

    st.divider()

    # ----------------- GRID -----------------
    st.subheader("Listado (editable)")
    df = repo_propietarios.list_all()
    if df.empty:
        st.info("No hay propietarios.")
        return

    df["codigo"] = df["codigo"].astype(int)
    df = df.sort_values("codigo").reset_index(drop=True)

    edited = st.data_editor(
        df,
        key="prop_grid",
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "codigo": st.column_config.NumberColumn("Código", disabled=True),
            "nombre": st.column_config.TextColumn("Nombre", max_chars=120)
        }
    )

    if st.button("⬆️ Guardar cambios (Propietarios)"):
        cambios = edited.merge(df, on="codigo", suffixes=("_new", "_old"))
        cambios = cambios[cambios["nombre_new"] != cambios["nombre_old"]]
        for _, r in cambios.iterrows():
            repo_propietarios.db.run(
                "UPDATE propietarios SET nombre=? WHERE codigo=?;",
                (r["nombre_new"].strip(), int(r["codigo"]))
            )
        if not cambios.empty:
            st.success(f"Se guardaron {len(cambios)} cambios.")
            st.rerun()
        else:
            st.info("No hay cambios para guardar.")

    # CARGAR AL FORMULARIO
    with st.expander("✏️ Editar una fila en el formulario"):
        sel = st.selectbox(
            "Selecciona fila",
            [f"{r['codigo']} - {r['nombre']}" for _, r in df.iterrows()],
            index=None
        )
        if st.button("Cargar"):
            if sel:
                cod = int(sel.split(" - ")[0])
                row = df[df["codigo"] == cod].iloc[0]
                state["codigo"] = cod
                state["nombre"] = row["nombre"]
                st.rerun()

    # ELIMINAR
    with st.expander("🗑️ Eliminar propietario"):
        usos = repo_propietarios.db.fetch_df("""
            SELECT p.codigo, p.nombre,
                   (SELECT COUNT(*) FROM departamentos d WHERE d.codPropietario = p.codigo) AS usados
            FROM propietarios p ORDER BY p.codigo;
        """)
        sel_del = st.selectbox(
            "Selecciona propietario",
            [f"{r.codigo} - {r.nombre} (usos: {r.usados})" for r in usos.itertuples()],
            index=None
        )
        seguro = st.checkbox("Confirmo la eliminación")
        if st.button("Eliminar", disabled=not (sel_del and seguro)):
            cod = int(sel_del.split(" - ")[0])
            reg = usos[usos["codigo"] == cod].iloc[0]
            if reg["usados"] > 0:
                st.error("No se puede eliminar: está asociado a departamentos.")
            else:
                repo_propietarios.db.run("DELETE FROM propietarios WHERE codigo=?;", (cod,))
                st.success("Propietario eliminado.")
                st.rerun()


# ===========================================================
#  DEPARTAMENTOS
# ===========================================================
def ui_cat_departamentos(repo_departamentos: DepartamentosRepo, repo_propietarios: PropietariosRepo):
    st.header("🏢 Catálogos → Departamentos")

    props_df = repo_propietarios.list_all()
    propietarios = {"(sin propietario)": None}
    propietarios |= {row["nombre"]: int(row["codigo"]) for _, row in props_df.iterrows()}

    state = _get_state("departamentos")
    for k, v in [
        ("codigo", None),
        ("numero", ""),
        ("torre", ""),
        ("piso", ""),
        ("propietario_nombre", "(sin propietario)"),
        ("propiedad", "Propio")
    ]:
        state.setdefault(k, v)

    st.subheader("Formulario")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        numero = st.text_input("Número", value=state["numero"], key="dep_num_input")
    with col2:
        torre = st.text_input("Torre", value=state["torre"])
    with col3:
        piso = st.text_input("Piso", value=state["piso"])
    with col4:
        propietario_nombre = st.selectbox(
            "Propietario",
            list(propietarios.keys()),
            index=list(propietarios.keys()).index(state["propietario_nombre"])
            if state["propietario_nombre"] in propietarios else 0
        )

    col5, _ = st.columns([1, 3])
    with col5:
        propiedad = st.selectbox(
            "Propiedad", ["Propio", "Ajeno"],
            index=(0 if state["propiedad"] == "Propio" else 1)
        )

    modo = "Editar" if state["codigo"] else "Registrar"

    c1, c2 = st.columns([1, 1])

    if c1.button(f"💾 {modo} departamento", use_container_width=True):
        if not numero.strip():
            st.warning("Ingresa el número del departamento.")
        else:
            if state["codigo"]:
                repo_departamentos.db.run("""
                    UPDATE departamentos
                    SET numero=?, torre=?, piso=?, codPropietario=?, esPropio=?
                    WHERE codigo=?;
                """, (
                    numero.strip(),
                    torre.strip() or None,
                    piso.strip() or None,
                    propietarios[propietario_nombre],
                    1 if propiedad == "Propio" else 0,
                    int(state["codigo"])
                ))
            else:
                repo_departamentos.insert(
                    Departamento(
                        numero=numero.strip(),
                        torre=torre.strip() or None,
                        piso=piso.strip() or None,
                        codPropietario=propietarios[propietario_nombre],
                        esPropio=1 if propiedad == "Propio" else 0
                    )
                )

            # limpiar
            state["codigo"] = None
            state["numero"] = ""
            state["torre"] = ""
            state["piso"] = ""
            state["propietario_nombre"] = "(sin propietario)"
            state["propiedad"] = "Propio"

            st.rerun()

    if c2.button("🧹 Limpiar formulario", use_container_width=True):
        state["codigo"] = None
        state["numero"] = ""
        state["torre"] = ""
        state["piso"] = ""
        state["propietario_nombre"] = "(sin propietario)"
        state["propiedad"] = "Propio"
        st.rerun()

    st.divider()

    # ----------------- GRID -----------------
    st.subheader("Listado (editable)")
    dfd = repo_departamentos.list_all()
    if dfd.empty:
        st.info("No hay departamentos registrados.")
        return

    dfd["codigo"] = dfd["codigo"].astype(int)
    dfd = dfd.sort_values("codigo").reset_index(drop=True)

    edited = st.data_editor(
        dfd,
        key="depto_grid",
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "codigo": st.column_config.NumberColumn("Código", disabled=True),
            "numero": st.column_config.TextColumn("Número", max_chars=20),
            "torre": st.column_config.TextColumn("Torre", max_chars=20),
            "piso": st.column_config.TextColumn("Piso", max_chars=20),
            "propiedad": st.column_config.TextColumn("Propiedad"),
            "propietario": st.column_config.TextColumn("Propietario"),
        }
    )

    if st.button("⬆️ Guardar cambios (Departamentos)"):
        base = dfd.merge(edited, on="codigo", suffixes=("_old", "_new"))
        cambios = []

        for _, r in base.iterrows():
            upd = {}

            if r["numero_old"] != r["numero_new"]:
                upd["numero"] = r["numero_new"]

            if (r["torre_old"] or "") != (r["torre_new"] or ""):
                upd["torre"] = r["torre_new"] or None

            if (r["piso_old"] or "") != (r["piso_new"] or ""):
                upd["piso"] = r["piso_new"] or None

            if r["propiedad_old"] != r["propiedad_new"]:
                upd["esPropio"] = 1 if str(r["propiedad_new"]).strip().lower() == "propio" else 0

            if (r["propietario_old"] or "") != (r["propietario_new"] or ""):
                nuevo = (r["propietario_new"] or "").strip()
                if nuevo == "":
                    upd["codPropietario"] = None
                else:
                    m = props_df[props_df["nombre"] == nuevo]
                    if m.empty:
                        st.error(f"Propietario '{nuevo}' no existe.")
                        st.stop()
                    upd["codPropietario"] = int(m["codigo"].iloc[0])

            if upd:
                cambios.append((int(r["codigo"]), upd))

        if not cambios:
            st.info("No hay cambios para guardar.")
        else:
            for cod, upd in cambios:
                setcols = ", ".join([f"{k}=?" for k in upd.keys()])
                vals = list(upd.values()) + [cod]
                repo_departamentos.db.run(
                    f"UPDATE departamentos SET {setcols} WHERE codigo=?;",
                    tuple(vals)
                )
            st.success(f"Se guardaron {len(cambios)} cambios.")
            st.rerun()

    # Cargar en formulario
    with st.expander("✏️ Editar una fila en el formulario"):
        opciones = [
            f"{r['codigo']} - Dep {r['numero']} ({r['propietario'] or 'sin propietario'})"
            for _, r in dfd.iterrows()
        ]
        sel = st.selectbox("Selecciona fila", opciones, index=None)
        if st.button("Cargar al formulario"):
            if sel:
                cod = int(sel.split(" - ")[0])
                row = dfd[dfd["codigo"] == cod].iloc[0]

                state["codigo"] = cod
                state["numero"] = row["numero"]
                state["torre"] = row["torre"] or ""
                state["piso"] = row["piso"] or ""
                state["propietario_nombre"] = row["propietario"] or "(sin propietario)"
                state["propiedad"] = row["propiedad"]
                st.rerun()

    # Eliminar
    with st.expander("🗑️ Eliminar departamento"):
        deps = repo_departamentos.db.fetch_df("""
            SELECT d.codigo, d.numero,
                   (SELECT COUNT(*) FROM reservas r WHERE r.codigoDepartamento = d.codigo) AS usados
            FROM departamentos d ORDER BY d.numero;
        """)
        sel_del = st.selectbox(
            "Selecciona departamento",
            [f"{r.codigo} - Dep {r.numero} (reservas: {r.usados})" for r in deps.itertuples()],
            index=None
        )
        seguro = st.checkbox("Confirmo la eliminación")
        if st.button("Eliminar", disabled=not (sel_del and seguro)):
            cod = int(sel_del.split(" - ")[0])
            row = deps[deps["codigo"] == cod].iloc[0]
            if row["usados"] > 0:
                st.error("No se puede eliminar: tiene reservas asociadas.")
            else:
                repo_departamentos.db.run("DELETE FROM departamentos WHERE codigo=?;", (cod,))
                st.success("Departamento eliminado.")
                st.rerun()


# ===========================================================
#  CONCEPTOS DE GASTOS
# ===========================================================
def ui_cat_conceptos_gastos(repo_conceptos: ConceptoGastosRepo):
    st.header("🧾 Catálogos → Conceptos de Gastos")

    state = _get_state("conceptos_gastos")
    state.setdefault("codigo", None)
    state.setdefault("descripcion", "")

    st.subheader("Formulario")
    col1, col2 = st.columns([3, 1])

    with col1:
        descripcion = st.text_input(
            "Descripción",
            value=state["descripcion"],
            key="cg_desc_input",
        )
    with col2:
        modo = "Editar" if state["codigo"] else "Registrar"

    colA, colB = st.columns([1, 1])

    if colA.button(f"💾 {modo} concepto", use_container_width=True):
        if not descripcion.strip():
            st.warning("Ingrese la descripción.")
        else:
            if state["codigo"]:
                repo_conceptos.db.run(
                    "UPDATE conceptoGastos SET descripcion=? WHERE codigo=?;",
                    (descripcion.strip(), int(state["codigo"]))
                )
            else:
                repo_conceptos.insert(ConceptoGasto(descripcion=descripcion.strip()))

            state["codigo"] = None
            state["descripcion"] = ""

            st.rerun()

    if colB.button("🧹 Limpiar formulario", use_container_width=True):
        state["codigo"] = None
        state["descripcion"] = ""
        st.rerun()

    st.divider()

    st.subheader("Listado (editable)")
    df = repo_conceptos.list_all()
    if df.empty:
        st.info("No hay conceptos.")
        return

    df["codigo"] = df["codigo"].astype(int)
    df = df.sort_values("codigo").reset_index(drop=True)

    edited = st.data_editor(
        df,
        key="conceptos_grid",
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "codigo": st.column_config.NumberColumn("Código", disabled=True),
            "descripcion": st.column_config.TextColumn("Descripción", max_chars=120),
        }
    )

    if st.button("⬆️ Guardar cambios (Conceptos de Gastos)"):
        base = df.merge(edited, on="codigo", suffixes=("_old", "_new"))
        cambios = base[base["descripcion_old"] != base["descripcion_new"]]

        if cambios.empty:
            st.info("No hay cambios para guardar.")
        else:
            for _, r in cambios.iterrows():
                repo_conceptos.db.run(
                    "UPDATE conceptoGastos SET descripcion=? WHERE codigo=?;",
                    (r["descripcion_new"].strip(), int(r["codigo"]))
                )
            st.success(f"Se guardaron {len(cambios)} cambio(s).")
            st.rerun()

    # EDITAR
    with st.expander("✏️ Editar una fila en el formulario"):
        opciones = [f"{r.codigo} - {r.descripcion}" for r in df.itertuples()]
        sel = st.selectbox("Selecciona fila", opciones, index=None)

        if st.button("Cargar al formulario"):
            if sel:
                cod = int(sel.split(" - ")[0])
                fila = df[df["codigo"] == cod].iloc[0]
                state["codigo"] = cod
                state["descripcion"] = fila["descripcion"]
                st.rerun()

    # ELIMINAR
    with st.expander("🗑️ Eliminar concepto"):
        c_counts = repo_conceptos.db.fetch_df("""
            SELECT c.codigo, c.descripcion,
                   (SELECT COUNT(*) FROM gastos g WHERE g.codConcepto = c.codigo) AS usados
            FROM conceptoGastos c
            ORDER BY c.codigo;
        """)

        sel_del = st.selectbox(
            "Selecciona concepto",
            [f"{r.codigo} - {r.descripcion} (gastos: {r.usados})" for r in c_counts.itertuples()],
            index=None
        )
        seguro = st.checkbox("Confirmo la eliminación")

        if st.button("Eliminar concepto", disabled=not (sel_del and seguro)):
            cod = int(sel_del.split(" - ")[0])
            fila = c_counts[c_counts["codigo"] == cod].iloc[0]

            if fila["usados"] > 0:
                st.error("No se puede eliminar: el concepto está asociado a gastos.")
            else:
                repo_conceptos.db.run("DELETE FROM conceptoGastos WHERE codigo=?;", (cod,))
                st.success("Concepto eliminado.")
                st.rerun()


# ===========================================================
#  GASTOS  (Se mantiene igual)
# ===========================================================

# … (tu código de gastos continúa igual)


# ===========================================================
#  GASTOS  (Acciones en la misma grilla + validación + máscara dinero)
# ===========================================================
def ui_cat_gastos(repo_gastos: GastosRepo, repo_conceptos: ConceptoGastosRepo):
    st.header("🧾 Catálogos → Registro de Gastos")

    # ----------------- Formulario (alta) -----------------
    dfc = repo_conceptos.list_all()
    conceptos = {row["descripcion"]: int(row["codigo"]) for _, row in dfc.iterrows()} or {"(cree un concepto primero)": 0}

    state = _get_state("gastos")
    state.setdefault("edit_numero", None)   # para cargar una fila al form desde “Acción = Editar”
    state.setdefault("detalle", "")
    state.setdefault("valor", 0.0)
    state.setdefault("concepto_desc", list(conceptos.keys())[0] if conceptos else "(cree un concepto primero)")
    state.setdefault("fecha", date.today())

    st.subheader("Formulario")
    with st.form("form_gasto", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            fecha_f = st.date_input("Fecha", value=state["fecha"], key="g_form_fecha")
        with col2:
            concepto_desc_f = st.selectbox("Concepto", list(conceptos.keys()), index=list(conceptos.keys()).index(state["concepto_desc"]) if state["concepto_desc"] in conceptos else 0, key="g_form_concepto")
        with col3:
            valor_f = st.number_input("Valor", min_value=0.0, value=float(state["valor"]), step=1.0, key="g_form_valor")
        detalle_f = st.text_input("Detalle", value=state["detalle"], key="g_form_detalle")

        bcol1, bcol2, bcol3 = st.columns([1,1,2])
        with bcol1:
            guardar = st.form_submit_button("💾 Guardar")
        with bcol2:
            limpiar = st.form_submit_button("🧹 Limpiar")

    if guardar:
        if conceptos.get(concepto_desc_f, 0) == 0:
            st.error("Primero cree un **Concepto** en Catálogos → Conceptos de Gastos.")
        else:
            if state["edit_numero"]:
                # UPDATE de la fila cargada
                repo_gastos.db.run(
                    "UPDATE gastos SET fecha=?, codConcepto=?, detalle=?, valor=? WHERE numero=?;",
                    (str(fecha_f), int(conceptos[concepto_desc_f]), detalle_f.strip(), float(valor_f), int(state["edit_numero"]))
                )
                st.success(f"Gasto #{state['edit_numero']} actualizado.")
            else:
                # INSERT
                repo_gastos.insert(Gasto(
                    fecha=fecha_f, detalle=detalle_f.strip(), valor=valor_f, codConcepto=conceptos[concepto_desc_f]
                ))
                st.success("Gasto registrado.")

            # Limpiar estado del formulario
            state["edit_numero"] = None
            state["detalle"] = ""
            state["valor"] = 0.0
            state["concepto_desc"] = list(conceptos.keys())[0] if conceptos else state["concepto_desc"]
            state["fecha"] = date.today()
            st.rerun()

    if limpiar:
        state["edit_numero"] = None
        state["detalle"] = ""
        state["valor"] = 0.0
        state["concepto_desc"] = list(conceptos.keys())[0] if conceptos else state["concepto_desc"]
        state["fecha"] = date.today()
        st.rerun()

    st.divider()

    # ----------------- GRID ÚNICO (editable + acciones) -----------------
    st.subheader("Listado (editable + acciones)")
    df = repo_gastos.list_all()
    if df.empty:
        st.info("Aún no hay gastos registrados.")
        return

    # Normalización de fecha
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    # Filtros
    dff = filter_dataframe(df, title="Filtros de gastos")

    # Validación numérica para edición
    dff["valor"] = pd.to_numeric(dff["valor"], errors="coerce").fillna(0.0)

    # Columna de acciones dentro de la grilla (simula botón)
    if "Acción" not in dff.columns:
        dff["Acción"] = "—"

    # Render del data_editor con máscara dinero y acciones
    try:
        accion_col = st.column_config.SelectboxColumn(
            "Acción",
            options=["—", "✏️ Editar", "🗑️ Eliminar"],
            help="Selecciona acción por fila y luego pulsa 'Aplicar acciones'."
        )
    except Exception:
        # Fallback si la versión de Streamlit no tiene SelectboxColumn
        accion_col = st.column_config.TextColumn(
            "Acción",
            help="Escribe exactamente: '✏️ Editar' o '🗑️ Eliminar' y pulsa 'Aplicar acciones'."
        )
    
    st.markdown(
        """
        <style>
            div[data-testid="stDataFrame"] table {
                width: 100% !important;
            }
            div[data-testid="stDataFrame"] th,
            div[data-testid="stDataFrame"] td {
                white-space: nowrap;
            }
        </style>
        """,
        unsafe_allow_html=True
    )


    edited = st.data_editor(
        dff,
        key="gastos_grid",
        use_container_width=True,
        hide_index=True,
        num_rows=5,
        height=200, 
        column_config={
            "numero": st.column_config.NumberColumn("N°", disabled=True),
            "fecha": st.column_config.DateColumn("Fecha", disabled=True),
            "concepto": st.column_config.TextColumn("Concepto", disabled=True),
            "detalle": st.column_config.TextColumn("Detalle", max_chars=200),
            # Editor de dinero: máscara + validación numérica
            "valor": st.column_config.NumberColumn(
                "Valor",
                min_value=0.0,
                step=1.0,
                format="$ %.2f",
                help="Ingrese un valor numérico (se formatea como $)."
            ),
            "Acción": accion_col,
        },
    )

    # -------- Guardar cambios del grid (detalle/valor) --------
    if st.button("⬆️ Guardar cambios (Gastos)"):
        base = dff.merge(edited, on="numero", suffixes=("_old", "_new"))
        cambios = base[(base["detalle_old"] != base["detalle_new"]) | (base["valor_old"] != base["valor_new"])]
        if cambios.empty:
            st.info("No hay cambios para guardar.")
        else:
            for _, r in cambios.iterrows():
                repo_gastos.db.run(
                    "UPDATE gastos SET detalle=?, valor=? WHERE numero=?;",
                    (str(r["detalle_new"] or "").strip(), float(r["valor_new"] or 0.0), int(r["numero"]))
                )
            st.success(f"Se guardaron {len(cambios)} cambio(s).")
            st.rerun()

    # -------- Aplicar acciones por fila (Editar / Eliminar) --------
    colA1, colA2 = st.columns([1, 5])
    with colA1:
        seguro_del = st.checkbox("Confirmo eliminación", value=False, help="Requerido para ejecutar '🗑️ Eliminar'")
    with colA2:
        if st.button("⚡ Aplicar acciones (Gastos)", use_container_width=True):
            # Filas marcadas con acción
            act = edited[edited["Acción"].isin(["✏️ Editar", "🗑️ Eliminar"])].copy()
            if act.empty:
                st.info("No hay acciones seleccionadas.")
            else:
                # Ejecutar primero eliminaciones, luego ediciones (por claridad)
                # ELIMINAR
                dels = act[act["Acción"] == "🗑️ Eliminar"]
                if not dels.empty:
                    if not seguro_del:
                        st.warning("Marca 'Confirmo eliminación' para ejecutar eliminaciones.")
                    else:
                        for _, r in dels.iterrows():
                            repo_gastos.db.run("DELETE FROM gastos WHERE numero=?;", (int(r["numero"]),))
                        if len(dels) > 0:
                            st.success(f"Eliminado(s): {len(dels)} gasto(s).")
                            st.rerun()

                # EDITAR → cargar fila en el formulario de arriba
                eds = act[act["Acción"] == "✏️ Editar"]
                if not eds.empty:
                    # Tomamos la última seleccionada para no duplicar estados
                    r = eds.iloc[-1]
                    state["edit_numero"] = int(r["numero"])
                    state["detalle"] = str(r["detalle"] or "")
                    state["valor"] = float(r["valor"] or 0.0)
                    state["concepto_desc"] = str(r["concepto"])
                    # convertir fecha a date
                    try:
                        state["fecha"] = pd.to_datetime(r["fecha"]).date()
                    except Exception:
                        state["fecha"] = date.today()
                    st.info(f"Fila #{state['edit_numero']} cargada en el formulario superior.")
                    st.rerun()


# ==== EXPORTS & BACKWARD COMPATIBILITY ====================================

try:
    ui_cat_concepto_gastos = ui_cat_conceptos_gastos   # singular/plural
except NameError:
    pass

try:
    ui_cat_conceptos = ui_cat_conceptos_gastos         # sin "_gastos"
except NameError:
    pass

__all__ = [
    "ui_cat_propietarios",
    "ui_cat_departamentos",
    "ui_cat_conceptos_gastos",
    "ui_cat_gastos",
    "ui_cat_conceptos",
    "ui_cat_concepto_gastos",
]