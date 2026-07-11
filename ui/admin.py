from __future__ import annotations
from pathlib import Path
import streamlit as st
from core.db import Database
from core.models import Usuario
from core.repositories import PerfilUsuariosRepo, UsuariosRepo

from datetime import date, timedelta
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

def ui_admin_limpiar_bd_2(db: Database):
    st.header("🧨 Administración → Limpiar base de datos TRX")

    st.warning(
        "Esta acción **eliminará** las transacciones: **Reservas, Abonos, Gastos, "
        "Ajustes contables y Saldo inicial**. "
        "Se **conservarán** los catálogos (Propietarios, Departamentos, Conceptos) "
        "y los perfiles de usuario."
    )
    st.caption("También se reiniciarán los autoincrementos de las tablas limpiadas.")

    confirmar = st.checkbox("Sí, entiendo las consecuencias y deseo continuar")
    if st.button("🧹 Limpiar AHORA", disabled=not confirmar, type="primary"):
        try:
            db.clear_data_preserve_perfiles_2()
            st.success("Base de datos limpiada. Los perfiles y catálogos se han conservado.")
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


def ui_admin_ajustes_contables(db: Database, usuario_actual: str = ""):
    st.header("⚖️ Administración → Ajustes Contables")
    st.caption(
        "Registrá correcciones o movimientos manuales de caja. "
        "**Monto positivo** = ingreso extra. **Monto negativo** = egreso/descuento. "
        "Aparecen en el reporte Diario ordenados por fecha."
    )

    # ── Asegurar tabla ──
    db.db_run_safe("""
        CREATE TABLE IF NOT EXISTS ajustesContables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            monto REAL NOT NULL,
            concepto TEXT NOT NULL,
            detalle TEXT,
            usuario TEXT
        );
    """)

    # ── Feedback persistente ──
    if st.session_state.get("_ajuste_toast"):
        st.success(st.session_state.pop("_ajuste_toast"))

    # ── Estado del formulario ──
    S = st.session_state.setdefault("_ajuste_state", {})
    S.setdefault("edit_id", None)
    S.setdefault("fecha", date.today())
    S.setdefault("monto", 0.0)
    S.setdefault("concepto", "")
    S.setdefault("detalle", "")

    if S["edit_id"]:
        st.warning(f"✏️ Editando ajuste **#{S['edit_id']}** — modificá los campos y presioná Guardar.")

    # ── Formulario ──
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            S["fecha"] = st.date_input("Fecha", value=S["fecha"], key="aj_fecha")
        with c2:
            S["monto"] = st.number_input(
                "Monto (+ ingreso / − egreso)",
                value=float(S["monto"]),
                step=1.0,
                format="%.2f",
                key="aj_monto",
                help="Ingresá un valor positivo para registrar un ingreso, negativo para un egreso."
            )

        S["concepto"] = st.text_input(
            "Concepto", value=S["concepto"], key="aj_concepto",
            placeholder="Ej: Devolución, Cobro extra, Corrección de caja..."
        )
        S["detalle"] = st.text_input(
            "Detalle (opcional)", value=S["detalle"], key="aj_detalle"
        )

        # Indicador visual del tipo
        if S["monto"] > 0:
            st.success(f"✅ Se registrará como **INGRESO** de ${S['monto']:,.2f}")
        elif S["monto"] < 0:
            st.error(f"🔴 Se registrará como **EGRESO** de ${abs(S['monto']):,.2f}")
        else:
            st.info("Ingresá un monto distinto de cero.")

        b1, b2 = st.columns(2)
        guardar = b1.button("💾 Guardar ajuste", key="aj_guardar", use_container_width=True)
        limpiar = b2.button("🧹 Limpiar", key="aj_limpiar", use_container_width=True)

    if guardar:
        if not S["concepto"].strip():
            st.warning("El concepto es obligatorio.")
        elif S["monto"] == 0:
            st.warning("El monto no puede ser cero.")
        else:
            if S["edit_id"]:
                db.run(
                    "UPDATE ajustesContables SET fecha=?, monto=?, concepto=?, detalle=?, usuario=? WHERE id=?;",
                    (str(S["fecha"]), float(S["monto"]), S["concepto"].strip(),
                     S["detalle"].strip() or None, usuario_actual, int(S["edit_id"]))
                )
                st.session_state["_ajuste_toast"] = f"✅ Ajuste #{S['edit_id']} actualizado."
            else:
                db.run(
                    "INSERT INTO ajustesContables (fecha, monto, concepto, detalle, usuario) VALUES (?,?,?,?,?);",
                    (str(S["fecha"]), float(S["monto"]), S["concepto"].strip(),
                     S["detalle"].strip() or None, usuario_actual)
                )
                tipo = "ingreso" if S["monto"] > 0 else "egreso"
                st.session_state["_ajuste_toast"] = f"✅ Ajuste registrado como {tipo} de ${abs(S['monto']):,.2f}."

            S["edit_id"] = None
            S["fecha"] = date.today()
            S["monto"] = 0.0
            S["concepto"] = ""
            S["detalle"] = ""
            st.rerun()

    if limpiar:
        S["edit_id"] = None
        S["fecha"] = date.today()
        S["monto"] = 0.0
        S["concepto"] = ""
        S["detalle"] = ""
        st.rerun()

    # ── Listado ──
    st.subheader("Ajustes registrados")
    df = db.fetch_df(
        "SELECT id, fecha, monto, concepto, detalle, usuario FROM ajustesContables ORDER BY fecha DESC, id DESC;"
    )

    if df is None or df.empty:
        st.info("No hay ajustes registrados aún.")
        return

    # Columnas de presentación
    df_show = df.copy()
    df_show["tipo"] = df_show["monto"].apply(lambda m: "📈 Ingreso" if float(m) >= 0 else "📉 Egreso")
    df_show["monto_fmt"] = df_show["monto"].apply(lambda m: f"${abs(float(m)):,.2f}")

    # Acción
    df_show["Acción"] = "—"

    try:
        accion_col = st.column_config.SelectboxColumn(
            "Acción", options=["—", "✏️ Editar", "🗑️ Eliminar"]
        )
    except Exception:
        accion_col = st.column_config.TextColumn("Acción")

    edited = st.data_editor(
        df_show[["id", "fecha", "tipo", "monto_fmt", "concepto", "detalle", "usuario", "Acción"]],
        key="aj_grid",
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "id":        st.column_config.NumberColumn("N°", disabled=True),
            "fecha":     st.column_config.TextColumn("Fecha", disabled=True),
            "tipo":      st.column_config.TextColumn("Tipo", disabled=True),
            "monto_fmt": st.column_config.TextColumn("Monto", disabled=True),
            "concepto":  st.column_config.TextColumn("Concepto", disabled=True),
            "detalle":   st.column_config.TextColumn("Detalle", disabled=True),
            "usuario":   st.column_config.TextColumn("Usuario", disabled=True),
            "Acción":    accion_col,
        }
    )

    cA1, cA2 = st.columns([1, 4])
    with cA1:
        confirmar_del = st.checkbox("Confirmo eliminación", key="aj_confirm_del")
    with cA2:
        if st.button("⚡ Aplicar acciones", use_container_width=True, key="aj_aplicar"):
            act = edited[edited["Acción"].isin(["✏️ Editar", "🗑️ Eliminar"])].copy()
            if act.empty:
                st.info("No hay acciones seleccionadas.")
            else:
                dels = act[act["Acción"] == "🗑️ Eliminar"]
                if not dels.empty:
                    if not confirmar_del:
                        st.warning("Marcá 'Confirmo eliminación' para eliminar.")
                    else:
                        for _, r in dels.iterrows():
                            db.run("DELETE FROM ajustesContables WHERE id=?;", (int(r["id"]),))
                        st.session_state["_ajuste_toast"] = f"✅ {len(dels)} ajuste(s) eliminado(s)."
                        st.rerun()

                eds = act[act["Acción"] == "✏️ Editar"]
                if not eds.empty:
                    row_id = int(eds.iloc[-1]["id"])
                    orig = df[df["id"] == row_id].iloc[0]
                    S["edit_id"] = row_id
                    S["fecha"] = pd.to_datetime(orig["fecha"]).date()
                    S["monto"] = float(orig["monto"])
                    S["concepto"] = str(orig["concepto"] or "")
                    S["detalle"] = str(orig["detalle"] or "")
                    st.rerun()


def ui_admin_bloqueos_depto(db: Database):
    st.header("🔒 Administración → Bloqueos de Departamento")
    st.caption(
        "Bloqueá un departamento por uso del dueño u otro motivo. "
        "Los días bloqueados aparecen en el calendario de disponibilidad como **🟠 Dueño**."
    )

    # Asegurar tabla
    db.db_run_safe("""
        CREATE TABLE IF NOT EXISTS bloqueosDepto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigoDepartamento INTEGER NOT NULL,
            fechaInicio TEXT NOT NULL,
            fechaFin TEXT NOT NULL,
            motivo TEXT NOT NULL DEFAULT 'Uso dueño'
        );
    """)

    # Feedback persistente
    if st.session_state.get("_bloqueo_toast"):
        st.success(st.session_state.pop("_bloqueo_toast"))

    # Cargar departamentos
    deps_df = db.fetch_df("SELECT codigo, numero FROM departamentos ORDER BY numero;")
    if deps_df.empty:
        st.warning("No hay departamentos registrados.")
        return

    dep_map = {f"Depto {r['numero']}": int(r["codigo"]) for _, r in deps_df.iterrows()}

    # Estado formulario
    S = st.session_state.setdefault("_bloqueo_state", {})
    S.setdefault("edit_id", None)
    S.setdefault("dep_label", list(dep_map.keys())[0])
    S.setdefault("f_ini", date.today())
    S.setdefault("f_fin", date.today())
    S.setdefault("motivo", "Uso dueño")

    if S["edit_id"]:
        st.warning(f"✏️ Editando bloqueo **#{S['edit_id']}**")

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            dep_label = st.selectbox(
                "Departamento",
                list(dep_map.keys()),
                index=list(dep_map.keys()).index(S["dep_label"]) if S["dep_label"] in dep_map else 0,
                key="bl_dep"
            )
        with c2:
            S["f_ini"] = st.date_input("Fecha inicio bloqueo", value=S["f_ini"], key="bl_fi")
        with c3:
            S["f_fin"] = st.date_input("Fecha fin bloqueo", value=S["f_fin"], key="bl_ff",
                                        help="El último día bloqueado es el anterior a esta fecha (igual que reservas).")

        S["motivo"] = st.text_input(
            "Motivo", value=S["motivo"], key="bl_motivo",
            placeholder="Uso dueño, Mantenimiento, Refacción..."
        )

        if S["f_ini"] < S["f_fin"]:
            dias = (S["f_fin"] - S["f_ini"]).days
            st.info(f"🔒 Se bloquearán **{dias} día(s)** del depto **{dep_label}** — del {S['f_ini']} al {S['f_fin'] - timedelta(days=1)}")
        else:
            st.warning("La fecha fin debe ser posterior a la fecha inicio.")

        b1, b2 = st.columns(2)
        guardar = b1.button("💾 Guardar bloqueo", key="bl_guardar", use_container_width=True)
        limpiar = b2.button("🧹 Limpiar", key="bl_limpiar", use_container_width=True)

    if guardar:
        if S["f_fin"] <= S["f_ini"]:
            st.error("La fecha fin debe ser posterior a la fecha inicio.")
        elif not S["motivo"].strip():
            st.warning("El motivo es obligatorio.")
        else:
            cod_dep = dep_map[dep_label]
            if S["edit_id"]:
                db.run(
                    "UPDATE bloqueosDepto SET codigoDepartamento=?, fechaInicio=?, fechaFin=?, motivo=? WHERE id=?;",
                    (cod_dep, str(S["f_ini"]), str(S["f_fin"]), S["motivo"].strip(), int(S["edit_id"]))
                )
                st.session_state["_bloqueo_toast"] = f"✅ Bloqueo #{S['edit_id']} actualizado."
            else:
                db.run(
                    "INSERT INTO bloqueosDepto (codigoDepartamento, fechaInicio, fechaFin, motivo) VALUES (?,?,?,?);",
                    (cod_dep, str(S["f_ini"]), str(S["f_fin"]), S["motivo"].strip())
                )
                dias = (S["f_fin"] - S["f_ini"]).days
                st.session_state["_bloqueo_toast"] = f"✅ Bloqueo registrado: {dep_label} por {dias} día(s)."

            S["edit_id"] = None
            S["dep_label"] = list(dep_map.keys())[0]
            S["f_ini"] = date.today()
            S["f_fin"] = date.today()
            S["motivo"] = "Uso dueño"
            st.rerun()

    if limpiar:
        S["edit_id"] = None
        S["dep_label"] = list(dep_map.keys())[0]
        S["f_ini"] = date.today()
        S["f_fin"] = date.today()
        S["motivo"] = "Uso dueño"
        st.rerun()

    # Listado
    st.subheader("Bloqueos activos")
    df_bl = db.fetch_df("""
        SELECT b.id, d.numero AS departamento, b.fechaInicio, b.fechaFin,
               b.motivo,
               (julianday(b.fechaFin) - julianday(b.fechaInicio)) AS dias
        FROM bloqueosDepto b
        JOIN departamentos d ON d.codigo = b.codigoDepartamento
        ORDER BY b.fechaInicio DESC, b.id DESC;
    """)

    if df_bl is None or df_bl.empty:
        st.info("No hay bloqueos registrados.")
        return

    df_bl["Acción"] = "—"
    try:
        accion_col = st.column_config.SelectboxColumn("Acción", options=["—", "✏️ Editar", "🗑️ Eliminar"])
    except Exception:
        accion_col = st.column_config.TextColumn("Acción")

    edited = st.data_editor(
        df_bl[["id", "departamento", "fechaInicio", "fechaFin", "dias", "motivo", "Acción"]],
        key="bl_grid",
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "id":           st.column_config.NumberColumn("N°", disabled=True),
            "departamento": st.column_config.TextColumn("Depto", disabled=True),
            "fechaInicio":  st.column_config.TextColumn("Inicio", disabled=True),
            "fechaFin":     st.column_config.TextColumn("Fin", disabled=True),
            "dias":         st.column_config.NumberColumn("Días", disabled=True),
            "motivo":       st.column_config.TextColumn("Motivo", disabled=True),
            "Acción":       accion_col,
        }
    )

    cA1, cA2 = st.columns([1, 4])
    with cA1:
        confirmar_del = st.checkbox("Confirmo eliminación", key="bl_confirm_del")
    with cA2:
        if st.button("⚡ Aplicar acciones", use_container_width=True, key="bl_aplicar"):
            act = edited[edited["Acción"].isin(["✏️ Editar", "🗑️ Eliminar"])].copy()
            if act.empty:
                st.info("No hay acciones seleccionadas.")
            else:
                dels = act[act["Acción"] == "🗑️ Eliminar"]
                if not dels.empty:
                    if not confirmar_del:
                        st.warning("Marcá 'Confirmo eliminación' para eliminar.")
                    else:
                        for _, r in dels.iterrows():
                            db.run("DELETE FROM bloqueosDepto WHERE id=?;", (int(r["id"]),))
                        st.session_state["_bloqueo_toast"] = f"✅ {len(dels)} bloqueo(s) eliminado(s)."
                        st.rerun()

                eds = act[act["Acción"] == "✏️ Editar"]
                if not eds.empty:
                    row_id = int(eds.iloc[-1]["id"])
                    orig = df_bl[df_bl["id"] == row_id].iloc[0]
                    dep_num = str(orig["departamento"])
                    dep_lbl = f"Depto {dep_num}"
                    S["edit_id"] = row_id
                    S["dep_label"] = dep_lbl if dep_lbl in dep_map else list(dep_map.keys())[0]
                    S["f_ini"] = pd.to_datetime(orig["fechaInicio"]).date()
                    S["f_fin"] = pd.to_datetime(orig["fechaFin"]).date()
                    S["motivo"] = str(orig["motivo"] or "Uso dueño")
                    st.rerun()
