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

    # Incluye numeroPersonas y mantiene estado
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

    st.subheader("Detalle")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Resumen")
    total = float(pd.to_numeric(df["totalEstadia"], errors="coerce").sum())
    limpieza = float(pd.to_numeric(df["valorLimpieza"], errors="coerce").sum())
    comision = float(pd.to_numeric(df["comision"], errors="coerce").sum())
    total_personas = int(pd.to_numeric(df["numeroPersonas"], errors="coerce").sum())
    st.write(f"- **Reservas:** {len(df)}")
    st.write(f"- **Total estadías:** {moneda(total)}")
    st.write(f"- **Limpieza:** {moneda(limpieza)}")
    st.write(f"- **Comisiones:** {moneda(comision)}")
    st.write(f"- **Pasajeros (total):** {total_personas}")
    st.write(f"- **Total general (aprox.):** {moneda(total + limpieza)}")


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

    st.subheader("Detalle")
    df["valor"] = df["valor"].map(moneda)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Resumen")
    total = float(pd.to_numeric(df["valor"].str.replace("[\\$,]", "", regex=True), errors="coerce").sum())
    st.write(f"- **Gastos:** {len(df)}")
    st.write(f"- **Total:** {moneda(total)}")


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

    st.subheader("Resumen")
    ingresos_total = float(pd.to_numeric(df["ingreso"], errors="coerce").sum())
    egresos_total  = float(pd.to_numeric(df["egreso"],  errors="coerce").sum())
    st.write(f"- **Ingresos:** {moneda(ingresos_total)}")
    st.write(f"- **Egresos:** {moneda(egresos_total)}")
    st.write(f"- **Saldo inicial:** {moneda(float(saldo_ini))}")
    st.write(f"- **Saldo final:** {moneda(float(df['saldo'].iloc[-1]) if not df.empty else saldo_ini)}")


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
    if val == "Libre":
        return "color: green; font-weight: 700;"
    if val == "—":
        return "color: #999999;"  # gris para fuera de rango
    return ""

def ui_rep_disponibilidad(db: Database):
    st.header("📅 Reportes → Disponibilidad por Departamento")

    # 1) Filtros
    c1, c2 = st.columns(2)
    with c1:
        f_ini = st.date_input("Desde", value=date(date.today().year, 1, 1))
    with c2:
        f_fin = st.date_input("Hasta", value=date.today() + timedelta(days=30))

    if f_ini > f_fin:
        st.warning("La fecha **Desde** no puede ser mayor que **Hasta**.")
        return

    deps = db.fetch_df("SELECT codigo, numero FROM departamentos ORDER BY numero;")
    opciones = [f"{row['numero']} (cod {int(row['codigo'])})" for _, row in deps.iterrows()]
    sel = st.multiselect("Departamentos (opcional)", opciones, default=opciones)

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

    df["estado"] = df["ocupado"].map(lambda x: "Ocupado" if int(x) else "Libre")
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
        st.dataframe(
            df_semana.style.applymap(_color_estado, subset=cols),
            use_container_width=True,
            hide_index=True
        )

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