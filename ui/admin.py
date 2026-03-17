from __future__ import annotations
from pathlib import Path
import streamlit as st
from core.db import Database
from core.models import Usuario
from core.repositories import PerfilUsuariosRepo, UsuariosRepo

from datetime import date
import pandas as pd
from core.repositories import CajaRepo
from core.utils import calcular_noches


def ui_admin_usuarios(repo_perfiles: PerfilUsuariosRepo, repo_usuarios: UsuariosRepo):
    st.header("👤 Administración → Usuarios")

    perfiles_df = repo_perfiles.list_all()
    perfiles = {row["descripcion"]: int(row["codigo"]) for _, row in perfiles_df.iterrows()}

    with st.form("form_usuario", clear_on_submit=True):
        col1, col2 = st.columns([2,1])
        with col1:
            nombre = st.text_input("Nombre del usuario")
        with col2:
            perfil_desc = st.selectbox("Perfil", options=list(perfiles.keys()) or ["(primero cargar perfiles demo)"])
        if st.form_submit_button("➕ Agregar usuario"):
            if not perfiles:
                st.error("No hay perfiles. Ve a **Base de datos** y carga datos demo.")
            elif not nombre.strip():
                st.warning("Ingresa el **nombre**.")
            else:
                repo_usuarios.insert(Usuario(nombre=nombre.strip(), codPerfil=perfiles[perfil_desc]))
                st.success(f"Usuario **{nombre}** agregado.")

    st.subheader("Usuarios registrados")
    st.dataframe(repo_usuarios.list_all(), use_container_width=True, hide_index=True)

def ui_admin_base_datos(db: Database, project_root: Path):
    st.header("🗄️ Administración → Base de datos")

    cols = st.columns(3)
    with cols[0]:
        st.metric("Ruta", str(db.db_path))
    with cols[1]:
        size = db.db_path.stat().st_size if db.db_path.exists() else 0
        st.metric("Tamaño", f"{size/1024:.1f} KB")
    with cols[2]:
        tablas = db.fetchall("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        st.metric("Tablas", str(len(tablas)))

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("🔧 Crear/Actualizar esquema"):
        db.initialize_schema()
        st.success("Esquema creado/actualizado correctamente.")

    if c2.button("🌱 Cargar perfiles demo"):
        for desc in ["Administrador", "Operador", "Consulta"]:
            db.run("INSERT OR IGNORE INTO perfilUsuarios (descripcion) VALUES (?);", (desc,))
        st.success("Perfiles demo cargados.")

    if db.db_path.exists():
        with open(db.db_path, "rb") as f:
            st.download_button("⬇️ Descargar BD", data=f.read(), file_name="hospedaje.db", mime="application/octet-stream")

    up = c4.file_uploader("📦 Restaurar .db (sobrescribe)", type=["db", "sqlite"])
    if up is not None:
        try:
            with open(db.db_path, "wb") as f:
                f.write(up.read())
            st.success("Base de datos restaurada. Recarga la app.")
        except Exception as e:
            st.error(f"Error restaurando BD: {e}")

    schema_file = project_root / "schema.sql"
    with st.expander("📜 Ver script de creación de BD (schema.sql)"):
        if schema_file.exists():
            st.code(schema_file.read_text(encoding="utf-8"), language="sql")
        else:
            st.warning("No se encontró `schema.sql` en la raíz del proyecto.")

def ui_admin_limpiar_bd(db: Database):
    st.header("🧨 Administración → Limpiar base de datos")

    st.warning(
        "Esta acción **eliminará** la información de **Usuarios, Propietarios, "
        "Departamentos, Conceptos de Gastos, Gastos y Reservas**. "
        "Se **conservarán** los registros de **perfilUsuarios**."
    )
    st.caption("También se reiniciarán los autoincrementos de las tablas limpiadas.")

    confirmar = st.checkbox("Sí, entiendo las consecuencias y deseo continuar")
    if st.button("🧹 Limpiar AHORA", disabled=not confirmar, type="primary"):
        try:
            db.clear_data_preserve_perfiles()
            st.success("Base de datos limpiada. Los perfiles se han conservado.")
        except Exception as e:
            st.error(f"Ocurrió un error al limpiar la base: {e}")

def ui_admin_saldo_inicial(db: Database):
    st.header("💰 Administración → Saldo inicial (una sola vez)")

    caja = CajaRepo(db)
    si = caja.get_saldo_inicial()

    # Si ya existe, solo mostramos y salimos
    if si:
        f, m = si
        st.success(f"Saldo inicial ya registrado: **{m:.2f}** con fecha **{f}**.")
        st.info("Por política, este valor se registra una sola vez. Si requieres cambios, realiza un ajuste manual vía movimientos.")
        return

    # --- Formulario: IMPORTANTE el submit_button DENTRO del with st.form(...)
    with st.form("form_saldo_inicial", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            f = st.date_input("Fecha del saldo inicial", value=date.today())
        with col2:
            m = st.number_input("Monto del saldo inicial", min_value=0.0, value=0.0, step=10.0)

        # 👇 ESTE botón debe estar dentro del with st.form
        guardar = st.form_submit_button("💾 Guardar saldo inicial", type="primary")

    # Manejo del submit FUERA del with (pero el botón se declara adentro)
    if guardar:
        if m <= 0:
            st.warning("El saldo inicial debe ser mayor que 0.")
        else:
            try:
                caja.set_saldo_inicial(f, m)
                st.success("Saldo inicial registrado.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al registrar saldo inicial: {e}")

def ui_admin_importar_excel(db: Database):
    st.header("📥 Administración → Importar Excel (Reservas y Gastos)")

    st.markdown("#### Plantilla esperada")
    with st.expander("📄 Reservas (.xlsx)"):
        st.write("""
        Columnas requeridas:
        fecha, idCliente, nombreCliente, ciudad, celular,
        departamento, fechaInicio, fechaFin,
        valorNoche, totalEstadia, valorLimpieza, comision,
        numeroPersonas, estado
        """)

    with st.expander("📄 Gastos (.xlsx)"):
        st.write("""
        Columnas requeridas:
        fecha, concepto, detalle, valor
        """)

    tab1, tab2 = st.tabs(["Importar Reservas", "Importar Gastos"])

    # ================================================================
    #   IMPORTAR RESERVAS
    # ================================================================
    with tab1:
        up_res = st.file_uploader("Archivo de reservas (.xlsx)", type=["xlsx"], key="up_res")

        if up_res is not None:
            try:
                # Siempre leer SOLO LA PRIMERA hoja
                df = pd.read_excel(up_res, engine="openpyxl", sheet_name=0)

                # Normalizar columnas
                df.columns = df.columns.str.strip()

                # Quitar totalmente filas duplicadas del Excel
                df = df.drop_duplicates().reset_index(drop=True)

                req_cols = {
                    "fecha","idCliente","nombreCliente","ciudad","celular",
                    "departamento","fechaInicio","fechaFin",
                    "valorNoche","valorLimpieza","comision",
                    "numeroPersonas","estado"
                }

                if not req_cols.issubset(df.columns):
                    st.error(f"Faltan columnas requeridas: {req_cols}")
                    return

                # Mapeo de depto
                deps = db.fetch_df("SELECT codigo, numero FROM departamentos;")
                dep_map = {str(r["numero"]).strip(): int(r["codigo"]) for _, r in deps.iterrows()}

                inserted = 0

                # Preparamos un set para evitar que pandas duplique por rarezas
                registros_unicos = set()

                for _, r in df.iterrows():

                    # Construir una clave única confiable para evitar duplicados en el ciclo
                    clave = (
                        str(r["nombreCliente"]).strip().lower(),
                        str(r["departamento"]).strip(),
                        str(r["fechaInicio"]).strip(),
                        str(r["fechaFin"]).strip(),
                    )

                    if clave in registros_unicos:
                        # YA PASÓ POR ESTA FILA → evitar doble inserción
                        continue
                    registros_unicos.add(clave)

                    # Departamento
                    codigoDepartamento = dep_map.get(str(r["departamento"]).strip())
                    if not codigoDepartamento:
                        st.warning(f"Depto no encontrado: {r['departamento']}. Fila omitida.")
                        continue

                    # Fechas
                    f_ini = pd.to_datetime(r["fechaInicio"]).date()
                    f_fin = pd.to_datetime(r["fechaFin"]).date()
                    noches = calcular_noches(f_ini, f_fin)

                    # Total estadía
                    if "totalEstadia" in df.columns and pd.notnull(r.get("totalEstadia")):
                        total_estadia = float(r["totalEstadia"])
                    else:
                        total_estadia = float(r.get("valorNoche", 0) or 0) * noches

                    # Validación en BD (evitar duplicados existentes)
                    dup = db.fetch_df(
                        """
                        SELECT numero FROM reservas
                        WHERE nombreCliente = ?
                          AND codigoDepartamento = ?
                          AND fechaInicio = ?
                          AND fechaFin = ?;
                        """,
                        (
                            str(r["nombreCliente"]).strip(),
                            int(codigoDepartamento),
                            str(f_ini),
                            str(f_fin),
                        )
                    )

                    if not dup.empty:
                        # Ya está en la BD, no insertar
                        continue

                    # INSERT seguro
                    db.run(
                        """
                        INSERT INTO reservas
                        (fecha, idCliente, nombreCliente, ciudad, celular, codigoDepartamento,
                         fechaInicio, fechaFin, numeroNoches, valorNoche, totalEstadia,
                         valorLimpieza, comision, numeroPersonas, estado, autorizacionSolicitada)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            str(pd.to_datetime(r["fecha"]).date()),
                            str(r.get("idCliente") or "").strip(),
                            str(r["nombreCliente"]).strip(),
                            str(r.get("ciudad") or "").strip(),
                            str(r.get("celular") or "").strip(),
                            int(codigoDepartamento),
                            str(f_ini),
                            str(f_fin),
                            int(noches),
                            float(r.get("valorNoche", 0) or 0),
                            float(total_estadia),
                            float(r["valorLimpieza"]),
                            float(r["comision"]),
                            int(r["numeroPersonas"]),
                            str(r["estado"]).strip(),
                            0
                        )
                    )
                    inserted += 1

                st.success(f"Reservas importadas correctamente: {inserted}")

            except Exception as e:
                st.error(f"Error al leer el Excel: {e}")

    # ================================================================
    #   IMPORTAR GASTOS
    # ================================================================
    with tab2:
        up_gas = st.file_uploader("Archivo de gastos (.xlsx)", type=["xlsx"], key="up_gas")
        if up_gas is not None:
            try:
                df = pd.read_excel(up_gas, engine="openpyxl", sheet_name=0)
                df.columns = df.columns.str.strip()
                df = df.drop_duplicates().reset_index(drop=True)

                req_cols = {"fecha", "concepto", "detalle", "valor"}
                if not req_cols.issubset(df.columns):
                    st.error(f"Faltan columnas: {req_cols}")
                    return

                inserted = 0
                for _, r in df.iterrows():
                    concepto = str(r["concepto"]).strip()

                    db.run("INSERT OR IGNORE INTO conceptoGastos (descripcion) VALUES (?);", (concepto,))
                    cod = db.fetchall("SELECT codigo FROM conceptoGastos WHERE descripcion = ?;", (concepto,))
                    if not cod:
                        continue

                    db.run(
                        "INSERT INTO gastos (fecha, detalle, valor, codConcepto) VALUES (?, ?, ?, ?);",
                        (
                            str(pd.to_datetime(r["fecha"]).date()),
                            str(r.get("detalle") or "").strip(),
                            float(r["valor"]),
                            int(cod[0][0])
                        )
                    )
                    inserted += 1

                st.success(f"Gastos importados: {inserted}")

            except Exception as e:
                st.error(f"Error al leer el Excel: {e}")