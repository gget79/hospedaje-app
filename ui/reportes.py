from datetime import date, timedelta
import pandas as pd
import streamlit as st
from io import BytesIO

from core.db import Database
from core.utils import iso, moneda
from core.repositories import CajaRepo, DisponibilidadRepo, ReservasRepo


# =============== Reporte: RESERVAS =================
def ui_rep_reservas(db: Database):
    st.header("📊 Reportes → Reservas")
    c1, c2 = st.columns(2)
    with c1:
        f_ini = st.date_input("Desde", value=date(date.today().year, 1, 1))
    with c2:
        f_fin = st.date_input("Hasta", value=date.today())

    sql = """
    SELECT fecha, nombreCliente, departamento, fechaInicio, fechaFin, numeroNoches,
           valorNoche, totalEstadia, valorLimpieza, comision, numeroPersonas, estado
    FROM (
        SELECT r.fecha, r.nombreCliente, d.numero AS departamento, r.fechaInicio, r.fechaFin,
               r.numeroNoches, r.valorNoche, r.totalEstadia, r.valorLimpieza, r.comision,
               r.numeroPersonas, r.estado
        FROM reservas r
        JOIN departamentos d ON d.codigo = r.codigoDepartamento
    )
    WHERE date(fechaInicio) >= date(?) AND date(fechaFin) <= date(?)
    ORDER BY fechaInicio DESC;
    """
    df = db.fetch_df(sql, (iso(f_ini), iso(f_fin)))
    if df.empty:
        st.info("Sin datos en el rango seleccionado.")
        return

    # ── Métricas resumen arriba ──
    total       = float(pd.to_numeric(df["totalEstadia"],  errors="coerce").sum())
    limpieza    = float(pd.to_numeric(df["valorLimpieza"], errors="coerce").sum())
    comision    = float(pd.to_numeric(df["comision"],      errors="coerce").sum())
    total_pers  = int(pd.to_numeric(df["numeroPersonas"],  errors="coerce").sum())
    total_noch  = int(pd.to_numeric(df["numeroNoches"],    errors="coerce").sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Reservas",        len(df))
    c2.metric("Total estadías",  moneda(total))
    c3.metric("Limpieza",        moneda(limpieza))
    c4.metric("Noches vendidas", total_noch)
    c5.metric("Pasajeros",       total_pers)

    st.caption(f"Total general (estadía + limpieza): **{moneda(total + limpieza)}**  |  Comisiones: **{moneda(comision)}**")

    st.subheader("Detalle")
    # Renombrar columnas para mejor lectura
    df_show = df.rename(columns={
        "nombreCliente": "Cliente", "departamento": "Depto",
        "fechaInicio": "Inicio", "fechaFin": "Fin",
        "numeroNoches": "Noches", "valorNoche": "$/noche",
        "totalEstadia": "Total estadía", "valorLimpieza": "Limpieza",
        "comision": "Comisión", "numeroPersonas": "Personas", "estado": "Estado"
    })
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ── Exportar Excel ──
    buf = BytesIO()
    df_show.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "⬇️ Exportar Excel",
        data=buf.getvalue(),
        file_name=f"reservas_{f_ini}_{f_fin}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =============== Reporte: GASTOS =================
def ui_rep_gastos(db: Database):
    st.header("📊 Reportes → Gastos")
    c1, c2 = st.columns(2)
    with c1:
        f_ini = st.date_input("Desde", value=date(date.today().year, 1, 1))
    with c2:
        f_fin = st.date_input("Hasta", value=date.today())

    sql = """
    SELECT g.fecha, c.descripcion AS concepto, g.detalle, g.valor
    FROM gastos g
    JOIN conceptoGastos c ON c.codigo = g.codConcepto
    WHERE date(g.fecha) BETWEEN date(?) AND date(?)
    ORDER BY g.fecha DESC;
    """
    df = db.fetch_df(sql, (iso(f_ini), iso(f_fin)))
    if df.empty:
        st.info("Sin datos en el rango seleccionado.")
        return

    total = float(pd.to_numeric(df["valor"], errors="coerce").sum())
    prom  = float(pd.to_numeric(df["valor"], errors="coerce").mean())
    max_v = float(pd.to_numeric(df["valor"], errors="coerce").max())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gastos",    len(df))
    c2.metric("Total",     moneda(total))
    c3.metric("Promedio",  moneda(prom))
    c4.metric("Mayor gasto", moneda(max_v))

    st.subheader("Detalle")
    df_show = df.copy()
    df_show["valor"] = df_show["valor"].map(moneda)
    df_show = df_show.rename(columns={"concepto": "Concepto", "detalle": "Detalle", "valor": "Valor", "fecha": "Fecha"})
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    buf = BytesIO()
    df_show.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "⬇️ Exportar Excel",
        data=buf.getvalue(),
        file_name=f"gastos_{f_ini}_{f_fin}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =============== Reporte: DIARIO =================
def ui_rep_diario(db: Database):
    st.header("📒 Reportes → Diario (ingresos / egresos)")

    # --- Filtros ---
    c1, c2 = st.columns(2)
    fi = c1.date_input("Desde", value=date(date.today().year, 1, 1))
    ff = c2.date_input("Hasta", value=date.today())
    if fi > ff:
        st.warning("La fecha **Desde** no puede ser mayor que **Hasta**.")
        return

    # --- Multiselect de departamentos (default: SOLO el de numero == '7' si existe) ---
    deps = db.fetch_df("SELECT codigo, numero FROM departamentos ORDER BY numero;")
    if deps.empty:
        st.info("No hay departamentos cargados.")
        return

    # label -> (codigo, numero)
    opciones = []
    label_to_info = {}
    for _, row in deps.iterrows():
        codigo = int(row["codigo"])
        numero = str(row["numero"]).strip()
        label = f"{numero} (cod {codigo})"
        opciones.append(label)
        label_to_info[label] = (codigo, numero)

    # default = el/los cuyo numero == '7' (normalmente único)
    default_labels = [lbl for lbl, (cod, num) in label_to_info.items() if num == "7"]
    if not default_labels:
        default_labels = [opciones[0]]  # si no existe '7', toma el primero

    sel = st.multiselect("Departamentos", opciones, default=default_labels)
    sel_info = [label_to_info[s] for s in sel]   # lista de (codigo, numero)
    dep_codigos = [ci[0] for ci in sel_info]

    caja = CajaRepo(db)

    # --- Saldo inicial conforme a la nueva regla ---
    # Caso A) EXACTAMENTE un dpto y su numero=='7' -> usar base (tabla) + recálculo
    if len(sel_info) == 1 and sel_info[0][1] == "7":
        saldo_ini = caja.saldo_inicial_calculado(fi, sel_info[0][0])
        saldo_label = "Saldo inicial del período (Dpto 7)"
    # Caso B) Ninguno seleccionado (lo tratamos como 'Todos') -> acumulado sin base de TODOS
    elif len(sel_info) == 0:
        saldo_ini = caja.saldo_inicial_acumulado_sin_base(fi, None)  # MIXTO, todos
        saldo_label = "Saldo inicial del período (acumulado sin base: Todos)"
    # Caso C) Un solo dpto distinto de '7' -> acumulado sin base de ese dpto
    elif len(sel_info) == 1:
        code = sel_info[0][0]
        saldo_ini = caja.saldo_inicial_acumulado_sin_base(fi, code)
        saldo_label = f"Saldo inicial del período (acumulado sin base: Dpto {sel_info[0][1]})"
    # Caso D) Varios dptos -> suma de acumulados sin base por cada dpto
    else:
        total = 0.0
        for code, num in sel_info:
            total += caja.saldo_inicial_acumulado_sin_base(fi, code)
        saldo_ini = total
        saldo_label = "Saldo inicial del período (acumulado sin base: múltiple)"

    # --- Movimientos según selección (mantiene tus reglas) ---
    if len(dep_codigos) == 0:
        modo = caja._modo_por_dep(None)  # MIXTO
        movs = caja.movimientos_diario(fi, ff, None, modo)
    elif len(dep_codigos) == 1:
        code = dep_codigos[0]
        modo = caja._modo_por_dep(code)
        movs = caja.movimientos_diario(fi, ff, code, modo)
    else:
        # unión por dpto (gastos aparecerán sólo cuando el modo sea PROPIO, i.e., numero=='7')
        dfs = []
        for code, num in sel_info:
            modo = caja._modo_por_dep(code)
            dfi = caja.movimientos_diario(fi, ff, code, modo)
            if not dfi.empty:
                dfs.append(dfi)
        movs = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["fecha","tipo","detalle","ingreso","egreso"])
        if not movs.empty:
            movs["fecha"] = pd.to_datetime(movs["fecha"])
            movs = movs.sort_values(["fecha", "tipo"], ascending=[True, True]).reset_index(drop=True)

    # --- Estado de cuenta con saldo corrido ---
    rows = [{
        "fecha": pd.to_datetime(fi),
        "tipo": "Saldo inicial",
        "detalle": saldo_label,
        "ingreso": 0.0,
        "egreso": 0.0,
        "saldo": float(saldo_ini),
    }]
    saldo = float(saldo_ini)

    if not movs.empty:
        movs["ingreso"] = pd.to_numeric(movs["ingreso"], errors="coerce").fillna(0.0)
        movs["egreso"]  = pd.to_numeric(movs["egreso"],  errors="coerce").fillna(0.0)
        for _, r in movs.iterrows():
            ingreso, egreso = float(r["ingreso"]), float(r["egreso"])
            saldo += ingreso - egreso
            rows.append({
                "fecha": pd.to_datetime(r["fecha"]),
                "tipo": r["tipo"],
                "detalle": r.get("detalle", ""),
                "ingreso": ingreso,
                "egreso": egreso,
                "saldo": saldo
            })

    df = pd.DataFrame(rows)

    # --- Render ---
    df_fmt = df.copy()
    df_fmt["fecha"] = pd.to_datetime(df_fmt["fecha"]).dt.strftime("%Y-%m-%d")
    for col in ["ingreso", "egreso", "saldo"]:
        df_fmt[col] = df_fmt[col].map(moneda)

    st.subheader("Detalle (estado de cuenta)")
    st.dataframe(df_fmt, use_container_width=True, hide_index=True)

    # ── Métricas resumen ──
    ingresos_total = float(pd.to_numeric(df["ingreso"], errors="coerce").sum())
    egresos_total  = float(pd.to_numeric(df["egreso"],  errors="coerce").sum())
    saldo_final    = float(df["saldo"].iloc[-1]) if not df.empty else float(saldo_ini)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos",    moneda(ingresos_total))
    c2.metric("Egresos",     moneda(egresos_total))
    c3.metric("Saldo inicial", moneda(float(saldo_ini)))
    c4.metric("Saldo final", moneda(saldo_final),
              delta=f"{moneda(saldo_final - float(saldo_ini))}")

    # ── Exportar Excel ──
    buf = BytesIO()
    df_fmt.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "⬇️ Exportar Excel",
        data=buf.getvalue(),
        file_name=f"diario_{fi}_{ff}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =============== Reporte: DISPONIBILIDAD =================
def _dia_corto_es(d: date) -> str:
    dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    return f"{dias[d.weekday()]} {d.day}-{meses[d.month-1]}"

def _inicio_semana_lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday=0

def _fin_semana_domingo(d: date) -> date:
    return _inicio_semana_lunes(d) + timedelta(days=6)

def _color_estado(val: str):
    if val == "Ocupado":
        return "color: red; font-weight: 700;"
    if val == "Dueño":
        return "color: orange; font-weight: 700;"
    if val == "Libre":
        return "color: green; font-weight: 700;"
    if val == "—":
        return "color: #999999;"
    return ""

def ui_rep_disponibilidad(db: Database):
    st.header("📅 Reportes → Disponibilidad por Departamento")

    usuario = st.session_state.get("usuario_actual", "__default__")

    deps = db.fetch_df("SELECT codigo, numero FROM departamentos ORDER BY numero;")
    opciones = [f"{row['numero']} (cod {int(row['codigo'])})" for _, row in deps.iterrows()]

    # ── Leer filtros persistidos desde BD ──
    import json
    try:
        f_ini_raw = db.get_preferencia(usuario, "disp_f_ini")
        f_ini_def = date.fromisoformat(f_ini_raw) if f_ini_raw else date(date.today().year, 1, 1)
    except Exception:
        f_ini_def = date(date.today().year, 1, 1)

    try:
        f_fin_raw = db.get_preferencia(usuario, "disp_f_fin")
        f_fin_def = date.fromisoformat(f_fin_raw) if f_fin_raw else date.today() + timedelta(days=30)
    except Exception:
        f_fin_def = date.today() + timedelta(days=30)

    try:
        sel_raw = db.get_preferencia(usuario, "disp_sel")
        sel_def = json.loads(sel_raw) if sel_raw else opciones
        sel_def = [s for s in sel_def if s in opciones]  # deptos eliminados
        if not sel_def:
            sel_def = opciones
    except Exception:
        sel_def = opciones

    # 1) Filtros — valores iniciales desde BD
    c1, c2 = st.columns(2)
    with c1:
        f_ini = st.date_input("Desde", value=f_ini_def, key="disp_f_ini")
    with c2:
        f_fin = st.date_input("Hasta", value=f_fin_def, key="disp_f_fin")

    sel = st.multiselect("Departamentos (opcional)", opciones, default=sel_def, key="disp_sel")

    # ── Guardar filtros en BD cada vez que cambian ──
    try:
        db.set_preferencia(usuario, "disp_f_ini", f_ini.isoformat())
        db.set_preferencia(usuario, "disp_f_fin", f_fin.isoformat())
        db.set_preferencia(usuario, "disp_sel", json.dumps(sel if sel else opciones))
    except Exception:
        pass

    if f_ini > f_fin:
        st.warning("La fecha **Desde** no puede ser mayor que **Hasta**.")
        return

    # ✅ Multiselect vacío = TODOS (codigos=None)
    if len(sel) == 0:
        codigos = None
    else:
        codigos = [int(item.split("cod")[-1].strip(" )")) for item in sel]

    # 2) Datos
    repo = DisponibilidadRepo(db)
    df = repo.disponibilidad_por_rango(f_ini, f_fin, codigos=codigos)

    if df.empty:
        st.info("Sin datos (no hay departamentos o rango sin días).")
        return

    # 3) Render SEMANAL
    st.subheader("Calendario de disponibilidad")

    df["estado"] = df["ocupado"].map(lambda x: "Dueño" if int(x) == 2 else ("Ocupado" if int(x) == 1 else "Libre"))
    departamentos = (
        df[["departamento"]].drop_duplicates().sort_values(
            by="departamento",
            key=lambda s: s.astype(str).str.extract(r"(\d+)").astype(float).fillna(0).iloc[:,0]
        )["departamento"].tolist()
    )

    actual = _inicio_semana_lunes(f_ini)
    semanas = []
    while actual <= f_fin:
        fin_semana = _fin_semana_domingo(actual)
        semanas.append((actual, fin_semana))
        actual = fin_semana + timedelta(days=1)

    excel_buffer = BytesIO()
    writer = pd.ExcelWriter(excel_buffer, engine="openpyxl")

    for i, (w_ini, w_fin) in enumerate(semanas, start=1):
        cols = []
        fechas_semana = [w_ini + timedelta(days=k) for k in range(7)]
        for d in fechas_semana:
            cols.append(_dia_corto_es(d))

        data = {"Departamento": departamentos}
        for d, col in zip(fechas_semana, cols):
            if d < f_ini or d > f_fin:
                data[col] = ["—"] * len(departamentos)
            else:
                mapa = df[df["fecha"] == d.isoformat()].set_index("departamento")["estado"].to_dict()
                data[col] = [mapa.get(dep, "Libre") for dep in departamentos]

        df_semana = pd.DataFrame(data)

        st.markdown(f"**Semana del {w_ini.strftime('%d-%b-%Y')} al {w_fin.strftime('%d-%b-%Y')}**")
        try:
            # pandas >= 2.1 usa .map(), versiones anteriores usan .applymap()
            styled = df_semana.style.map(_color_estado, subset=cols)
        except AttributeError:
            styled = df_semana.style.applymap(_color_estado, subset=cols)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        hoja = f"Sem_{w_ini.strftime('%Y%m%d')}_{w_fin.strftime('%Y%m%d')}"
        df_semana.to_excel(writer, index=False, sheet_name=hoja)

    writer.close()
    with st.expander("⬇️ Exportar"):
        nombre = f"disponibilidad_{f_ini.isoformat()}_{f_fin.isoformat()}.xlsx"
        st.download_button(
            "Descargar Excel",
            data=excel_buffer.getvalue(),
            file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# =============== Reporte: Reservas con saldo pendiente =================
def ui_rep_reservas_saldo_pendiente(db: Database):
    st.header("📊 Reportes → Reservas con saldo pendiente")

    repo = ReservasRepo(db)
    df = repo.reservas_con_saldo_pendiente()

    if df is None or df.empty:
        st.info("No existen reservas con saldo pendiente.")
        return

    # Formateo de columnas monetarias
    df2 = df.copy()
    for col in ["total", "abonado", "saldoPendiente"]:
        if col in df2.columns:
            df2[col] = pd.to_numeric(df2[col], errors="coerce").fillna(0.0)
            df2[col] = df2[col].map(moneda)

    st.subheader("Detalle")
    st.dataframe(df2, use_container_width=True, hide_index=True)

    st.subheader("Resumen")
    total_saldo = float(pd.to_numeric(df["saldoPendiente"], errors="coerce").fillna(0.0).sum())
    st.write(f"- **Reservas con saldo:** {len(df)}")
    st.write(f"- **Saldo pendiente total:** {moneda(total_saldo)}")


# =============== Reporte: Rentabilidad neta =================
def ui_rep_rentabilidad_neta(db: Database):
    st.header("💵 Reportes → Rentabilidad Neta")
    st.caption(
        "Ingreso real que te queda por reserva: estadía cobrada menos pago al dueño "
        "(solo deptos ajenos) más excedente de limpieza (aplica a todos)."
    )

    # ── Filtros ──
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            f_ini = st.date_input("Desde", value=date(date.today().year, 1, 1), key="rn_fi")
        with c2:
            f_fin = st.date_input("Hasta", value=date.today(), key="rn_ff")

        deps_df = db.fetch_df("SELECT codigo, numero FROM departamentos ORDER BY numero;")
        opciones_dep = ["Todos"] + [str(r["numero"]) for _, r in deps_df.iterrows()]
        dep_sel = st.multiselect(
            "Departamentos", opciones_dep[1:],
            default=opciones_dep[1:], key="rn_dep"
        )

        c1, c2 = st.columns(2)
        with c1:
            costo_limpieza = st.number_input(
                "Costo fijo de limpieza ($)",
                min_value=0.0, value=20.0, step=1.0, key="rn_costo_limp",
                help="Lo que pagás a quien limpia. El excedente cobrado sobre este valor es ingreso tuyo."
            )
        with c2:
            pago_dueno_std = st.number_input(
                "Pago estándar al dueño — deptos ajenos ($)",
                min_value=0.0, value=50.0, step=5.0, key="rn_pago_dueno",
                help="Valor por defecto que pagás al dueño. Podés ajustarlo reserva por reserva más abajo."
            )

    if f_ini > f_fin:
        st.warning("La fecha Desde no puede ser mayor que Hasta.")
        return

    # ── Cargar reservas con esPropio ──
    sql = """
    SELECT r.numero, r.fecha, r.fechaInicio, r.fechaFin,
           r.numeroNoches, r.totalEstadia, r.valorLimpieza, r.comision,
           r.nombreCliente, r.estado,
           d.numero AS departamento,
           COALESCE(d.esPropio, 1) AS esPropio
    FROM reservas r
    JOIN departamentos d ON d.codigo = r.codigoDepartamento
    WHERE date(r.fechaInicio) >= date(?) AND date(r.fechaInicio) <= date(?)
      AND UPPER(r.estado) NOT IN ('CANCELADA','ANULADA')
    ORDER BY r.fechaInicio ASC;
    """
    df = db.fetch_df(sql, (iso(f_ini), iso(f_fin)))

    if df is None or df.empty:
        st.info("Sin datos para el rango seleccionado.")
        return

    for col in ["totalEstadia", "valorLimpieza", "comision", "esPropio", "numeroNoches"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Filtro por departamento
    if dep_sel:
        df = df[df["departamento"].isin([str(d) for d in dep_sel])]

    if df.empty:
        st.info("Sin reservas para los filtros seleccionados.")
        return

    df["tipo"] = df["esPropio"].apply(lambda x: "Propio" if int(x) == 1 else "Ajeno")
    df["fechaInicio"] = pd.to_datetime(df["fechaInicio"], errors="coerce")

    # ── Sección 1: Deptos AJENOS — pago al dueño editable por reserva ──
    st.subheader("1️⃣ Pago al dueño — Departamentos ajenos")

    df_ajenos = df[df["tipo"] == "Ajeno"].copy()

    if df_ajenos.empty:
        st.info("No hay reservas de departamentos ajenos en el período.")
        pago_map = {}
    else:
        df_aj_edit = df_ajenos[["numero", "departamento", "fechaInicio",
                                 "nombreCliente", "totalEstadia", "valorLimpieza"]].copy()
        df_aj_edit["fechaInicio"] = df_aj_edit["fechaInicio"].dt.strftime("%Y-%m-%d")
        df_aj_edit["pago_dueno"] = pago_dueno_std
        df_aj_edit = df_aj_edit.rename(columns={
            "numero": "N° Reserva", "departamento": "Depto",
            "fechaInicio": "Fecha inicio", "nombreCliente": "Huésped",
            "totalEstadia": "Estadía cobrada", "valorLimpieza": "Limp. cobrada",
            "pago_dueno": "Pago al dueño ($)"
        })

        st.caption("Modificá el **Pago al dueño ($)** en las filas donde aplique un valor diferente (días festivos, etc.)")
        df_aj_editado = st.data_editor(
            df_aj_edit,
            key="rn_aj_editor",
            use_container_width=True,
            hide_index=True,
            column_config={
                "N° Reserva":      st.column_config.NumberColumn(disabled=True),
                "Depto":           st.column_config.TextColumn(disabled=True),
                "Fecha inicio":    st.column_config.TextColumn(disabled=True),
                "Huésped":         st.column_config.TextColumn(disabled=True),
                "Estadía cobrada": st.column_config.NumberColumn(disabled=True, format="$ %.2f"),
                "Limp. cobrada":   st.column_config.NumberColumn(disabled=True, format="$ %.2f"),
                "Pago al dueño ($)": st.column_config.NumberColumn(
                    min_value=0.0, step=5.0, format="$ %.2f",
                    help="Editá si pagaste un valor diferente en esta reserva."
                ),
            }
        )
        pago_map = dict(zip(
            df_aj_editado["N° Reserva"].astype(int),
            df_aj_editado["Pago al dueño ($)"].astype(float)
        ))

    # ── Sección 2: Excedente de limpieza — todos los deptos ──
    st.subheader("2️⃣ Excedente de limpieza — Todos los departamentos")
    st.caption(
        f"El excedente es el monto cobrado por encima de **${costo_limpieza:.0f}**. "
        "Aplica a propios y ajenos por igual."
    )

    df_limp = df[["numero", "departamento", "tipo",
                  df.columns[df.columns.tolist().index("fechaInicio")],
                  "nombreCliente", "valorLimpieza"]].copy()
    df_limp["fechaInicio"] = df_limp["fechaInicio"].dt.strftime("%Y-%m-%d")
    df_limp["excedente"] = df_limp["valorLimpieza"].apply(
        lambda v: max(float(v) - costo_limpieza, 0.0)
    )
    df_limp_show = df_limp.rename(columns={
        "numero": "N° Reserva", "departamento": "Depto", "tipo": "Tipo",
        "fechaInicio": "Fecha", "nombreCliente": "Huésped",
        "valorLimpieza": "Limp. cobrada", "excedente": "Excedente ($)"
    })

    # Mostrar solo filas con excedente o todas
    mostrar_exc = st.checkbox("Mostrar solo reservas con excedente de limpieza", value=False, key="rn_solo_exc")
    df_limp_disp = df_limp_show[df_limp_show["Excedente ($)"] > 0] if mostrar_exc else df_limp_show

    st.dataframe(
        df_limp_disp.style.format({"Limp. cobrada": "$ {:.2f}", "Excedente ($)": "$ {:.2f}"}),
        use_container_width=True, hide_index=True
    )

    # ── Cálculo final ──
    df["pago_dueno_ef"] = df.apply(
        lambda r: pago_map.get(int(r["numero"]), pago_dueno_std) if r["tipo"] == "Ajeno" else 0.0,
        axis=1
    )
    df["exc_limp"] = df["valorLimpieza"].apply(lambda v: max(float(v) - costo_limpieza, 0.0))
    df["ingreso_neto"] = df["totalEstadia"] - df["pago_dueno_ef"] + df["exc_limp"]

    # ── Sección 3: Resumen y totales ──
    st.markdown("---")
    st.subheader("3️⃣ Resumen de rentabilidad neta")

    # KPIs globales
    total_bruto  = df["totalEstadia"].sum()
    total_pagos  = df["pago_dueno_ef"].sum()
    total_exc    = df["exc_limp"].sum()
    total_neto   = df["ingreso_neto"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingreso bruto",  moneda(total_bruto))
    c2.metric("Pagos a dueños", moneda(total_pagos))
    c3.metric("Exc. limpieza",  moneda(total_exc))
    c4.metric("Ingreso NETO",   moneda(total_neto),
              delta=f"{(total_neto/total_bruto*100):.1f}% del bruto" if total_bruto else None)

    # Resumen por departamento
    df_res = df.groupby(["departamento", "tipo"]).agg(
        reservas=("numero", "count"),
        bruto=("totalEstadia", "sum"),
        pagos_dueno=("pago_dueno_ef", "sum"),
        exc_limp=("exc_limp", "sum"),
        neto=("ingreso_neto", "sum"),
        noches=("numeroNoches", "sum"),
    ).reset_index()
    df_res["neto_x_noche"] = (df_res["neto"] / df_res["noches"].replace(0, 1)).round(2)
    df_res = df_res.sort_values("neto", ascending=False)

    # Gráficos
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Ingreso neto por departamento ($)**")
        st.bar_chart(df_res.set_index("departamento")["neto"])
    with c2:
        st.markdown("**Neto por noche ($)**")
        st.bar_chart(df_res.set_index("departamento")["neto_x_noche"])

    st.markdown("**Bruto vs Neto por departamento**")
    st.bar_chart(df_res.set_index("departamento")[["bruto", "neto"]])

    # Tabla resumen
    df_res_show = df_res.copy()
    for col in ["bruto", "pagos_dueno", "exc_limp", "neto", "neto_x_noche"]:
        df_res_show[col] = df_res_show[col].map(moneda)
    df_res_show.columns = ["Depto", "Tipo", "Reservas", "Bruto",
                            "Pagos dueños", "Exc. limp.", "Neto", "Noches", "Neto/noche"]
    st.dataframe(df_res_show, use_container_width=True, hide_index=True)

    # Exportar Excel
    buf = BytesIO()
    df_res_show.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "⬇️ Exportar resumen Excel",
        data=buf.getvalue(),
        file_name=f"rentabilidad_neta_{f_ini}_{f_fin}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )