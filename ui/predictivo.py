
"""
Módulo: Análisis Predictivo de Reservas
Gráficos, tendencias, comparaciones y predicciones de demanda.
Usa solo librerías ya disponibles: pandas, streamlit, numpy.
"""
from __future__ import annotations

from datetime import date, timedelta
import numpy as np
import pandas as pd
import streamlit as st

from core.db import Database
from core.utils import moneda

# ─────────────────────────────────────────────
#  Helpers internos
# ─────────────────────────────────────────────
MESES_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def _cargar_reservas(db: Database) -> pd.DataFrame:
    sql = """
    SELECT r.numero, r.fecha, r.fechaInicio, r.fechaFin,
           r.numeroNoches, r.valorNoche, r.totalEstadia,
           r.valorLimpieza, r.comision, r.numeroPersonas,
           r.estado, d.numero AS departamento
    FROM reservas r
    JOIN departamentos d ON d.codigo = r.codigoDepartamento
    WHERE UPPER(r.estado) NOT IN ('CANCELADA','ANULADA')
    ORDER BY r.fechaInicio;
    """
    df = db.fetch_df(sql)
    if df.empty:
        return df
    for col in ["fecha", "fechaInicio", "fechaFin"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ["numeroNoches", "valorNoche", "totalEstadia",
                "valorLimpieza", "comision", "numeroPersonas"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["anio"] = df["fechaInicio"].dt.year
    df["mes"] = df["fechaInicio"].dt.month
    df["mes_nombre"] = df["mes"].map(MESES_ES)
    df["semana"] = df["fechaInicio"].dt.isocalendar().week.astype(int)
    df["ingreso_total"] = df["totalEstadia"] + df["valorLimpieza"]
    return df


def _regresion_lineal(x: np.ndarray, y: np.ndarray):
    """Devuelve (pendiente, intercepto) con mínimos cuadrados."""
    if len(x) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0
    A = np.vstack([x, np.ones(len(x))]).T
    m, b = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(m), float(b)


def _color_bar(valores: pd.Series, col_name: str) -> pd.DataFrame:
    """Devuelve un styler con barra de color proporcional."""
    return valores.to_frame(col_name)


def _graf(df_sorted: "pd.DataFrame", col, kind="bar"):
    """
    Grafica una columna de df_sorted respetando el orden cronológico.
    df_sorted debe tener columna 'periodo' y estar ordenado por [anio, mes].
    Usa CategoricalIndex para forzar el orden en st.bar/line/area_chart.
    """
    import pandas as pd
    periodos = df_sorted["periodo"].tolist()
    s = df_sorted.set_index("periodo")[col]
    s.index = pd.CategoricalIndex(s.index, categories=periodos, ordered=True)
    return s



# ─────────────────────────────────────────────
#  Sección principal
# ─────────────────────────────────────────────
def ui_analisis_predictivo_ingresos(db: Database):
    st.header("🤖 Análisis Predictivo — Ingresos")
    st.caption(
        "Tendencias históricas de reservas e ingresos, comparaciones entre períodos "
        "y proyecciones para anticipar demanda y optimizar decisiones."
    )

    df = _cargar_reservas(db)

    if df.empty:
        st.info("Aún no hay reservas registradas. Cargá datos para ver el análisis.")
        return

    anios_disponibles = sorted(df["anio"].unique().tolist())

    # ── Tabs principales ──────────────────────────────────────────────
    tabs = st.tabs([
        "📈 Tendencia general",
        "📅 Comparación mensual",
        "🔁 Año vs Año",
        "🏠 Por departamento",
        "👥 Perfil de huéspedes",
        "🔮 Proyección demanda",
        "💡 Recomendaciones",
    ])

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — TENDENCIA GENERAL
    # ══════════════════════════════════════════════════════════════════
    with tabs[0]:
        st.subheader("Reservas y facturación por mes (histórico completo)")

        df_mes = (
            df.groupby(["anio", "mes"])
            .agg(reservas=("numero", "count"),
                 noches=("numeroNoches", "sum"),
                 ingresos=("ingreso_total", "sum"),
                 personas=("numeroPersonas", "sum"))
            .reset_index()
        )
        df_mes["periodo"] = df_mes.apply(
            lambda r: f"{MESES_ES[int(r['mes'])]}-{int(r['anio'])}", axis=1
        )
        df_mes = df_mes.sort_values(["anio", "mes"])

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Reservas por mes**")
            st.bar_chart(_graf(df_mes, "reservas"))
        with c2:
            st.markdown("**Ingresos por mes ($)**")
            st.bar_chart(_graf(df_mes, "ingresos"))

        st.markdown("**Noches vendidas por mes**")
        st.area_chart(_graf(df_mes, "noches"))

        with st.expander("Ver tabla detallada"):
            df_show = df_mes[["periodo", "reservas", "noches", "ingresos", "personas"]].copy()
            df_show["ingresos"] = df_show["ingresos"].map(moneda)
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — COMPARACIÓN MENSUAL (mismo mes, distintos años)
    # ══════════════════════════════════════════════════════════════════
    with tabs[1]:
        st.subheader("Comparación del mismo mes entre años")

        mes_sel = st.selectbox(
            "Seleccioná el mes a comparar",
            options=list(MESES_ES.keys()),
            format_func=lambda m: MESES_ES[m],
            index=date.today().month - 1,
            key="pred_mes_comp"
        )

        df_comp = df[df["mes"] == mes_sel].groupby("anio").agg(
            reservas=("numero", "count"),
            noches=("numeroNoches", "sum"),
            ingresos=("ingreso_total", "sum"),
            personas=("numeroPersonas", "sum"),
            ticket_prom=("ingreso_total", "mean"),
        ).reset_index()

        if df_comp.empty:
            st.info(f"Sin datos para {MESES_ES[mes_sel]}.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Años con datos", len(df_comp))
            c2.metric("Mejor año (reservas)",
                      str(int(df_comp.loc[df_comp["reservas"].idxmax(), "anio"])))
            c3.metric("Mejor año (ingresos)",
                      str(int(df_comp.loc[df_comp["ingresos"].idxmax(), "anio"])))

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Reservas en {MESES_ES[mes_sel]} por año**")
                st.bar_chart(df_comp.set_index("anio")["reservas"])
            with c2:
                st.markdown(f"**Ingresos en {MESES_ES[mes_sel]} por año ($)**")
                st.bar_chart(df_comp.set_index("anio")["ingresos"])

            st.markdown("**Tabla comparativa**")
            df_comp2 = df_comp.copy()
            df_comp2["ingresos"] = df_comp2["ingresos"].map(moneda)
            df_comp2["ticket_prom"] = df_comp2["ticket_prom"].map(moneda)
            df_comp2.columns = ["Año", "Reservas", "Noches", "Ingresos",
                                 "Personas", "Ticket promedio"]
            st.dataframe(df_comp2, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — AÑO VS AÑO
    # ══════════════════════════════════════════════════════════════════
    with tabs[2]:
        st.subheader("Comparación año vs año")

        if len(anios_disponibles) < 2:
            st.info("Necesitás datos de al menos 2 años para esta comparación.")
        else:
            col1, col2 = st.columns(2)
            anio_a = col1.selectbox("Año A", anios_disponibles,
                                    index=len(anios_disponibles) - 2, key="pred_anio_a")
            anio_b = col2.selectbox("Año B", anios_disponibles,
                                    index=len(anios_disponibles) - 1, key="pred_anio_b")

            def resumen_anio(a):
                d = df[df["anio"] == a].groupby("mes").agg(
                    reservas=("numero", "count"),
                    ingresos=("ingreso_total", "sum"),
                    noches=("numeroNoches", "sum"),
                ).reset_index()
                d["mes_nombre"] = d["mes"].map(MESES_ES)
                return d.set_index("mes")

            da = resumen_anio(anio_a)
            db_ = resumen_anio(anio_b)
            todos_meses = sorted(set(da.index) | set(db_.index))

            comp = pd.DataFrame({"mes": todos_meses})
            comp["mes_nombre"] = comp["mes"].map(MESES_ES)
            comp[f"res_{anio_a}"] = comp["mes"].map(da["reservas"]).fillna(0).astype(int)
            comp[f"res_{anio_b}"] = comp["mes"].map(db_["reservas"]).fillna(0).astype(int)
            comp[f"ing_{anio_a}"] = comp["mes"].map(da["ingresos"]).fillna(0)
            comp[f"ing_{anio_b}"] = comp["mes"].map(db_["ingresos"]).fillna(0)
            comp[f"noc_{anio_a}"] = comp["mes"].map(da["noches"]).fillna(0).astype(int)
            comp[f"noc_{anio_b}"] = comp["mes"].map(db_["noches"]).fillna(0).astype(int)
            comp = comp.set_index("mes_nombre")

            st.markdown("**Reservas por mes**")
            st.bar_chart(comp[[f"res_{anio_a}", f"res_{anio_b}"]])

            st.markdown("**Ingresos por mes ($)**")
            st.bar_chart(comp[[f"ing_{anio_a}", f"ing_{anio_b}"]])

            st.markdown("**Noches vendidas por mes**")
            st.line_chart(comp[[f"noc_{anio_a}", f"noc_{anio_b}"]])

            # Variación %
            comp["var_reservas_%"] = np.where(
                comp[f"res_{anio_a}"] > 0,
                ((comp[f"res_{anio_b}"] - comp[f"res_{anio_a}"]) / comp[f"res_{anio_a}"] * 100).round(1),
                np.nan
            )
            comp["var_ingresos_%"] = np.where(
                comp[f"ing_{anio_a}"] > 0,
                ((comp[f"ing_{anio_b}"] - comp[f"ing_{anio_a}"]) / comp[f"ing_{anio_a}"] * 100).round(1),
                np.nan
            )

            with st.expander("Ver tabla con variación %"):
                st.dataframe(comp.reset_index(), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════
    # TAB 4 — POR DEPARTAMENTO
    # ══════════════════════════════════════════════════════════════════
    with tabs[3]:
        st.subheader("Rendimiento por departamento")

        df_dep = df.groupby("departamento").agg(
            reservas=("numero", "count"),
            noches=("numeroNoches", "sum"),
            ingresos=("ingreso_total", "sum"),
            personas=("numeroPersonas", "sum"),
            ticket_prom=("ingreso_total", "mean"),
        ).reset_index().sort_values("ingresos", ascending=False)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Reservas por departamento**")
            st.bar_chart(df_dep.set_index("departamento")["reservas"])
        with c2:
            st.markdown("**Ingresos por departamento ($)**")
            st.bar_chart(df_dep.set_index("departamento")["ingresos"])

        st.markdown("**Noches vendidas por departamento**")
        st.bar_chart(df_dep.set_index("departamento")["noches"])

        # Ocupación estimada (noches vendidas / días del período)
        dias_periodo = max((df["fechaFin"].max() - df["fechaInicio"].min()).days, 1)
        df_dep["ocupacion_%"] = (df_dep["noches"] / dias_periodo * 100).round(1).clip(upper=100)

        st.markdown("**Tasa de ocupación estimada (%)**")
        st.bar_chart(df_dep.set_index("departamento")["ocupacion_%"])

        with st.expander("Ver tabla completa"):
            df_dep2 = df_dep.copy()
            df_dep2["ingresos"] = df_dep2["ingresos"].map(moneda)
            df_dep2["ticket_prom"] = df_dep2["ticket_prom"].map(moneda)
            df_dep2.columns = ["Departamento", "Reservas", "Noches",
                                "Ingresos", "Personas", "Ticket prom.", "Ocupación %"]
            st.dataframe(df_dep2, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════
    # TAB 5 — PERFIL DE HUÉSPEDES
    # ══════════════════════════════════════════════════════════════════
    with tabs[4]:
        st.subheader("Perfil y comportamiento de huéspedes")

        # Estadía promedio
        avg_noches = df["numeroNoches"].mean()
        avg_personas = df["numeroPersonas"].mean()
        avg_ticket = df["ingreso_total"].mean()

        c1, c2, c3 = st.columns(3)
        c1.metric("Estadía promedio", f"{avg_noches:.1f} noches")
        c2.metric("Personas por reserva", f"{avg_personas:.1f}")
        c3.metric("Ticket promedio", moneda(avg_ticket))

        # Distribución de estadías
        st.markdown("**Distribución de duración de estadía (noches)**")
        hist_data = df["numeroNoches"].value_counts().sort_index()
        st.bar_chart(hist_data)

        # Ciudades de origen
        if "ciudad" in df.columns or True:
            sql_ciu = """
            SELECT ciudad, COUNT(*) as reservas
            FROM reservas
            WHERE ciudad IS NOT NULL AND ciudad != ''
              AND UPPER(estado) NOT IN ('CANCELADA','ANULADA')
            GROUP BY ciudad ORDER BY reservas DESC LIMIT 15;
            """
            df_ciu = db.fetch_df(sql_ciu)
            if not df_ciu.empty:
                st.markdown("**Top 15 ciudades de origen**")
                st.bar_chart(df_ciu.set_index("ciudad")["reservas"])

        # Día de la semana con más check-in
        df["dia_semana"] = df["fechaInicio"].dt.day_name()
        dias_orden = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dias_es = {"Monday":"Lunes","Tuesday":"Martes","Wednesday":"Miércoles",
                   "Thursday":"Jueves","Friday":"Viernes","Saturday":"Sábado","Sunday":"Domingo"}
        df_dias = df["dia_semana"].value_counts().reindex(dias_orden).fillna(0)
        df_dias.index = [dias_es[d] for d in df_dias.index]
        st.markdown("**Check-ins por día de la semana**")
        st.bar_chart(df_dias)

        # Mes más popular
        df_mes_pop = df.groupby("mes").agg(reservas=("numero","count")).reset_index()
        df_mes_pop["mes_nombre"] = df_mes_pop["mes"].map(MESES_ES)
        df_mes_pop = df_mes_pop.set_index("mes_nombre").sort_index()
        st.markdown("**Reservas por mes (todos los años)**")
        st.bar_chart(df_mes_pop["reservas"])

    # ══════════════════════════════════════════════════════════════════
    # TAB 6 — PROYECCIÓN DE DEMANDA
    # ══════════════════════════════════════════════════════════════════
    with tabs[5]:
        st.subheader("🔮 Proyección de demanda — próximos 6 meses")
        st.caption("Proyección basada en regresión lineal sobre datos históricos mensuales.")

        df_hist = (
            df.groupby(["anio", "mes"])
            .agg(reservas=("numero", "count"),
                 ingresos=("ingreso_total", "sum"),
                 noches=("numeroNoches", "sum"))
            .reset_index()
            .sort_values(["anio", "mes"])
        )
        df_hist["t"] = np.arange(len(df_hist))  # índice temporal

        if len(df_hist) < 3:
            st.info("Se necesitan al menos 3 meses de datos para proyectar.")
        else:
            # Regresión para reservas e ingresos
            m_res, b_res = _regresion_lineal(df_hist["t"].values, df_hist["reservas"].values)
            m_ing, b_ing = _regresion_lineal(df_hist["t"].values, df_hist["ingresos"].values)
            m_noc, b_noc = _regresion_lineal(df_hist["t"].values, df_hist["noches"].values)

            # Generar próximos 6 meses
            ultimo_anio = int(df_hist["anio"].iloc[-1])
            ultimo_mes = int(df_hist["mes"].iloc[-1])
            ultimo_t = int(df_hist["t"].iloc[-1])

            proyecciones = []
            for i in range(1, 7):
                t_fut = ultimo_t + i
                mes_fut = ((ultimo_mes - 1 + i) % 12) + 1
                anio_fut = ultimo_anio + ((ultimo_mes - 1 + i) // 12)
                res_pred = max(round(m_res * t_fut + b_res), 0)
                ing_pred = max(m_ing * t_fut + b_ing, 0)
                noc_pred = max(round(m_noc * t_fut + b_noc), 0)
                proyecciones.append({
                    "periodo": f"{MESES_ES[mes_fut]}-{anio_fut}",
                    "reservas_proyectadas": res_pred,
                    "ingresos_proyectados": ing_pred,
                    "noches_proyectadas": noc_pred,
                })

            df_proy = pd.DataFrame(proyecciones)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Reservas proyectadas**")
                st.bar_chart(_graf(df_proy, "reservas_proyectadas"))
            with c2:
                st.markdown("**Ingresos proyectados ($)**")
                st.bar_chart(_graf(df_proy, "ingresos_proyectados"))

            st.markdown("**Noches proyectadas**")
            st.line_chart(_graf(df_proy, "noches_proyectadas"))

            # Tabla
            df_proy2 = df_proy.copy()
            df_proy2["ingresos_proyectados"] = df_proy2["ingresos_proyectados"].map(moneda)
            df_proy2.columns = ["Período", "Reservas proyectadas",
                                 "Ingresos proyectados", "Noches proyectadas"]
            st.dataframe(df_proy2, use_container_width=True, hide_index=True)

            # Tendencia: crecimiento o caída
            tendencia = "📈 creciente" if m_res > 0 else "📉 decreciente"
            st.info(
                f"**Tendencia general:** {tendencia}  \n"
                f"Cada mes la demanda varía en promedio **{abs(m_res):.1f} reservas** "
                f"y **{moneda(abs(m_ing))}** en ingresos."
            )

            # Estacionalidad: meses pico históricos
            df_estac = df.groupby("mes").agg(reservas=("numero","count")).reset_index()
            mes_pico = int(df_estac.loc[df_estac["reservas"].idxmax(), "mes"])
            mes_bajo = int(df_estac.loc[df_estac["reservas"].idxmin(), "mes"])
            st.success(
                f"**Mes pico histórico:** {MESES_ES[mes_pico]}  \n"
                f"**Mes más bajo histórico:** {MESES_ES[mes_bajo]}"
            )

    # ══════════════════════════════════════════════════════════════════
    # TAB 7 — RECOMENDACIONES
    # ══════════════════════════════════════════════════════════════════
    with tabs[6]:
        st.subheader("💡 Recomendaciones basadas en los datos")

        # Calcular métricas para las recomendaciones
        df_mes_rec = df.groupby("mes").agg(
            reservas=("numero", "count"),
            ingresos=("ingreso_total", "sum"),
            noches=("numeroNoches", "sum"),
        ).reset_index()

        mes_pico = int(df_mes_rec.loc[df_mes_rec["reservas"].idxmax(), "mes"])
        mes_bajo = int(df_mes_rec.loc[df_mes_rec["reservas"].idxmin(), "mes"])
        avg_noches_rec = df["numeroNoches"].mean()
        avg_personas_rec = df["numeroPersonas"].mean()

        # Departamento más rentable
        df_dep_rec = df.groupby("departamento").agg(
            ingresos=("ingreso_total", "sum"),
            reservas=("numero", "count"),
        ).reset_index()
        dep_top = df_dep_rec.loc[df_dep_rec["ingresos"].idxmax(), "departamento"]
        dep_bajo = df_dep_rec.loc[df_dep_rec["ingresos"].idxmin(), "departamento"]

        # Ticket promedio
        ticket_prom = df["ingreso_total"].mean()
        ticket_max = df["ingreso_total"].max()

        # Tendencia últimos 3 meses vs 3 anteriores
        df_hist2 = df.groupby(["anio","mes"]).agg(reservas=("numero","count")).reset_index()
        df_hist2 = df_hist2.sort_values(["anio","mes"])
        if len(df_hist2) >= 6:
            ult3 = df_hist2["reservas"].iloc[-3:].mean()
            ant3 = df_hist2["reservas"].iloc[-6:-3].mean()
            tendencia_reciente = "creciendo" if ult3 > ant3 else "bajando"
            delta_pct = abs((ult3 - ant3) / ant3 * 100) if ant3 > 0 else 0
        else:
            tendencia_reciente = None

        st.markdown("### 📌 Resumen ejecutivo")

        recomendaciones = []

        recomendaciones.append(
            f"**Temporada alta:** El mes históricamente más demandado es **{MESES_ES[mes_pico]}**. "
            f"Asegurate de tener todos los departamentos disponibles y considerá aumentar tarifas un 10-15%."
        )
        recomendaciones.append(
            f"**Temporada baja:** **{MESES_ES[mes_bajo]}** es el mes con menos reservas. "
            f"Ideal para mantenimiento, limpieza profunda o promociones para atraer huéspedes."
        )
        recomendaciones.append(
            f"**Departamento estrella:** El depto **{dep_top}** genera los mayores ingresos. "
            f"Priorizá su mantenimiento y considerá replicar sus características en otros."
        )
        if dep_bajo != dep_top:
            recomendaciones.append(
                f"**Departamento a potenciar:** El depto **{dep_bajo}** tiene los menores ingresos. "
                f"Revisá su precio, fotos o descripción en plataformas de reserva."
            )
        recomendaciones.append(
            f"**Estadía promedio:** Los huéspedes se quedan en promedio **{avg_noches_rec:.1f} noches** "
            f"con **{avg_personas_rec:.1f} personas**. "
            f"Ofrecé descuentos por estadías de 5+ noches para aumentar ocupación."
        )
        recomendaciones.append(
            f"**Ticket promedio:** ${ticket_prom:,.2f}. El máximo registrado fue ${ticket_max:,.2f}. "
            f"Hay margen para paquetes premium (desayuno, traslados, etc.)."
        )
        if tendencia_reciente:
            recomendaciones.append(
                f"**Tendencia reciente:** La demanda está **{tendencia_reciente}** "
                f"un **{delta_pct:.1f}%** comparando los últimos 3 meses vs los 3 anteriores."
            )

        for i, rec in enumerate(recomendaciones, 1):
            st.markdown(f"{i}. {rec}")

        st.markdown("---")
        st.markdown("### 📊 KPIs clave")

        total_reservas = len(df)
        total_ingresos = df["ingreso_total"].sum()
        total_noches = df["numeroNoches"].sum()
        total_personas = df["numeroPersonas"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total reservas", total_reservas)
        c2.metric("Ingresos totales", moneda(total_ingresos))
        c3.metric("Noches vendidas", int(total_noches))
        c4.metric("Huéspedes totales", int(total_personas))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ticket promedio", moneda(ticket_prom))
        c2.metric("Estadía promedio", f"{avg_noches_rec:.1f} n.")
        c3.metric("Personas/reserva", f"{avg_personas_rec:.1f}")
        c4.metric("Mes pico", MESES_ES[mes_pico])


# =================================================================
#  ANÁLISIS PREDICTIVO — GASTOS
# =================================================================

def _cargar_gastos(db):
    sql = (
        "SELECT g.numero, g.fecha, g.valor, g.detalle, "
        "c.descripcion AS concepto "
        "FROM gastos g "
        "JOIN conceptoGastos c ON c.codigo = g.codConcepto "
        "ORDER BY g.fecha;"
    )
    df = db.fetch_df(sql)
    if df.empty:
        return df
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0)
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["mes_nombre"] = df["mes"].map(MESES_ES)
    return df


def ui_analisis_predictivo_gastos(db):
    st.header("\U0001f4b8 Análisis Predictivo \u2014 Gastos")
    st.caption("Tendencias, comparaciones y proyecciones de gastos para optimizar el control de costos.")

    df = _cargar_gastos(db)
    if df.empty:
        st.info("No hay gastos registrados aún.")
        return

    anios = sorted(df["anio"].unique().tolist())

    tabs = st.tabs([
        "\U0001f4c8 Tendencia general",
        "\U0001f4c5 Comparación mensual",
        "\U0001f501 Año vs Año",
        "\U0001f3f7\ufe0f Por concepto",
        "\U0001f52e Proyección gastos",
        "\U0001f4a1 Recomendaciones",
    ])

    with tabs[0]:
        st.subheader("Gastos por mes (histórico completo)")
        df_mes = (
            df.groupby(["anio", "mes"])
            .agg(total=("valor", "sum"), cantidad=("numero", "count"))
            .reset_index()
        )
        df_mes["periodo"] = df_mes.apply(
            lambda r: f"{MESES_ES[int(r['mes'])]}-{int(r['anio'])}", axis=1
        )
        df_mes = df_mes.sort_values(["anio", "mes"])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Gasto total por mes ($)**")
            st.bar_chart(_graf(df_mes, "total"))
        with c2:
            st.markdown("**Cantidad de gastos por mes**")
            st.bar_chart(_graf(df_mes, "cantidad"))
        st.markdown("**Evolución acumulada de gastos**")
        st.area_chart(_graf(df_mes, "total"))
        with st.expander("Ver tabla detallada"):
            df_show = df_mes[["periodo", "total", "cantidad"]].copy()
            df_show["total"] = df_show["total"].map(moneda)
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Comparación del mismo mes entre años")
        mes_sel = st.selectbox(
            "Mes a comparar", list(MESES_ES.keys()),
            format_func=lambda m: MESES_ES[m],
            index=pd.Timestamp.today().month - 1, key="gas_mes_comp"
        )
        df_comp = df[df["mes"] == mes_sel].groupby("anio").agg(
            total=("valor", "sum"), cantidad=("numero", "count"),
            promedio=("valor", "mean")).reset_index()
        if df_comp.empty:
            st.info(f"Sin datos para {MESES_ES[mes_sel]}.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Gasto total en {MESES_ES[mes_sel]} por año ($)**")
                st.bar_chart(df_comp.set_index("anio")["total"])
            with c2:
                st.markdown(f"**Cantidad de gastos en {MESES_ES[mes_sel]} por año**")
                st.bar_chart(df_comp.set_index("anio")["cantidad"])
            df_comp2 = df_comp.copy()
            df_comp2["total"] = df_comp2["total"].map(moneda)
            df_comp2["promedio"] = df_comp2["promedio"].map(moneda)
            df_comp2.columns = ["Año", "Total gastos", "Cantidad", "Promedio por gasto"]
            st.dataframe(df_comp2, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Comparación año vs año")
        if len(anios) < 2:
            st.info("Necesitás datos de al menos 2 años.")
        else:
            col1, col2 = st.columns(2)
            anio_a = col1.selectbox("Año A", anios, index=len(anios)-2, key="gas_anio_a")
            anio_b = col2.selectbox("Año B", anios, index=len(anios)-1, key="gas_anio_b")
            def res_gas(a):
                d = df[df["anio"] == a].groupby("mes").agg(total=("valor", "sum")).reset_index()
                return d.set_index("mes")
            da, db_ = res_gas(anio_a), res_gas(anio_b)
            todos = sorted(set(da.index) | set(db_.index))
            comp = pd.DataFrame({"mes": todos})
            comp["mes_nombre"] = comp["mes"].map(MESES_ES)
            comp[f"gas_{anio_a}"] = comp["mes"].map(da["total"]).fillna(0)
            comp[f"gas_{anio_b}"] = comp["mes"].map(db_["total"]).fillna(0)
            comp = comp.set_index("mes_nombre")
            st.markdown("**Gastos por mes ($)**")
            st.bar_chart(comp[[f"gas_{anio_a}", f"gas_{anio_b}"]])
            comp["var_%"] = np.where(
                comp[f"gas_{anio_a}"] > 0,
                ((comp[f"gas_{anio_b}"] - comp[f"gas_{anio_a}"]) / comp[f"gas_{anio_a}"] * 100).round(1),
                np.nan
            )
            with st.expander("Ver tabla con variación %"):
                st.dataframe(comp.reset_index(), use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("Gastos por concepto")
        df_conc = df.groupby("concepto").agg(
            total=("valor", "sum"), cantidad=("numero", "count"),
            promedio=("valor", "mean")).reset_index().sort_values("total", ascending=False)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Total por concepto ($)**")
            st.bar_chart(df_conc.set_index("concepto")["total"])
        with c2:
            st.markdown("**Frecuencia por concepto**")
            st.bar_chart(df_conc.set_index("concepto")["cantidad"])
        with st.expander("Ver tabla completa"):
            df_conc2 = df_conc.copy()
            df_conc2["total"] = df_conc2["total"].map(moneda)
            df_conc2["promedio"] = df_conc2["promedio"].map(moneda)
            df_conc2.columns = ["Concepto", "Total", "Cantidad", "Promedio"]
            st.dataframe(df_conc2, use_container_width=True, hide_index=True)

    with tabs[4]:
        st.subheader("\U0001f52e Proyección de gastos \u2014 próximos 6 meses")
        df_hist = (
            df.groupby(["anio", "mes"]).agg(total=("valor", "sum"))
            .reset_index().sort_values(["anio", "mes"])
        )
        df_hist["t"] = np.arange(len(df_hist))
        if len(df_hist) < 3:
            st.info("Se necesitan al menos 3 meses de datos.")
        else:
            m_g, b_g = _regresion_lineal(df_hist["t"].values, df_hist["total"].values)
            ultimo_anio = int(df_hist["anio"].iloc[-1])
            ultimo_mes = int(df_hist["mes"].iloc[-1])
            ultimo_t = int(df_hist["t"].iloc[-1])
            proy = []
            for i in range(1, 7):
                t_fut = ultimo_t + i
                mes_fut = ((ultimo_mes - 1 + i) % 12) + 1
                anio_fut = ultimo_anio + ((ultimo_mes - 1 + i) // 12)
                proy.append({
                    "periodo": f"{MESES_ES[mes_fut]}-{anio_fut}",
                    "gastos_proyectados": max(m_g * t_fut + b_g, 0)
                })
            df_proy = pd.DataFrame(proy)
            st.bar_chart(_graf(df_proy, "gastos_proyectados"))
            df_proy2 = df_proy.copy()
            df_proy2["gastos_proyectados"] = df_proy2["gastos_proyectados"].map(moneda)
            df_proy2.columns = ["Período", "Gastos proyectados"]
            st.dataframe(df_proy2, use_container_width=True, hide_index=True)
            tend = "\U0001f4c8 en aumento" if m_g > 0 else "\U0001f4c9 en descenso"
            st.info(f"**Tendencia de gastos:** {tend} \u2014 variación mensual promedio: {moneda(abs(m_g))}")

    with tabs[5]:
        st.subheader("\U0001f4a1 Recomendaciones de control de gastos")
        df_conc_rec = (
            df.groupby("concepto").agg(total=("valor", "sum"))
            .reset_index().sort_values("total", ascending=False)
        )
        conc_top = df_conc_rec.iloc[0]["concepto"] if not df_conc_rec.empty else "N/A"
        total_gastos = df["valor"].sum()
        prom_mensual = df.groupby(["anio", "mes"])["valor"].sum().mean()
        df_hist2 = (
            df.groupby(["anio", "mes"]).agg(total=("valor", "sum"))
            .reset_index().sort_values(["anio", "mes"])
        )
        tend_rec = None
        delta_pct = 0
        if len(df_hist2) >= 6:
            ult3 = df_hist2["total"].iloc[-3:].mean()
            ant3 = df_hist2["total"].iloc[-6:-3].mean()
            tend_rec = "aumentando" if ult3 > ant3 else "disminuyendo"
            delta_pct = abs((ult3 - ant3) / ant3 * 100) if ant3 > 0 else 0
        mes_gas_alto = int(df.groupby("mes")["valor"].sum().idxmax())
        recs = [
            f"**Concepto de mayor gasto:** {conc_top}. Revisá si hay oportunidad de negociar precios o reducir frecuencia.",
            f"**Gasto mensual promedio:** {moneda(prom_mensual)}. Usá este valor como presupuesto base.",
            f"**Total histórico de gastos:** {moneda(total_gastos)}.",
            f"**Mes de mayor gasto histórico:** {MESES_ES[mes_gas_alto]}. Planificá reservas de caja con anticipación.",
        ]
        if tend_rec:
            recs.append(f"**Tendencia reciente:** Los gastos están **{tend_rec}** un **{delta_pct:.1f}%** vs los 3 meses anteriores.")
        for i, r in enumerate(recs, 1):
            st.markdown(f"{i}. {r}")
        st.markdown("---")
        st.markdown("### \U0001f4ca KPIs de gastos")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total gastos", moneda(total_gastos))
        c2.metric("Promedio mensual", moneda(prom_mensual))
        c3.metric("Concepto top", conc_top[:15] if len(conc_top) > 15 else conc_top)
        c4.metric("Mes más caro", MESES_ES[mes_gas_alto])


# =================================================================
#  ANÁLISIS PREDICTIVO — INGRESOS VS GASTOS (COMBINADO)
# =================================================================

def ui_analisis_predictivo_combinado(db):
    st.header("\u2696\ufe0f Análisis Predictivo \u2014 Ingresos vs Gastos")
    st.caption(
        "Comparación directa entre ingresos y gastos para tomar decisiones "
        "informadas sobre rentabilidad, flujo de caja y planificación financiera."
    )

    df_res = _cargar_reservas(db)
    df_gas = _cargar_gastos(db)

    if df_res.empty and df_gas.empty:
        st.info("No hay datos suficientes para el análisis combinado.")
        return

    def _agg_ing(df):
        if df.empty:
            return pd.DataFrame(columns=["anio", "mes", "ingresos"])
        return df.groupby(["anio", "mes"]).agg(ingresos=("ingreso_total", "sum")).reset_index()

    def _agg_gas(df):
        if df.empty:
            return pd.DataFrame(columns=["anio", "mes", "gastos"])
        return df.groupby(["anio", "mes"]).agg(gastos=("valor", "sum")).reset_index()

    df_comb = pd.merge(_agg_ing(df_res), _agg_gas(df_gas), on=["anio", "mes"], how="outer").fillna(0)
    df_comb["periodo"] = df_comb.apply(
        lambda r: f"{MESES_ES[int(r['mes'])]}-{int(r['anio'])}", axis=1
    )
    df_comb["margen"] = df_comb["ingresos"] - df_comb["gastos"]
    df_comb["margen_%"] = np.where(
        df_comb["ingresos"] > 0,
        (df_comb["margen"] / df_comb["ingresos"] * 100).round(1), 0
    )
    df_comb = df_comb.sort_values(["anio", "mes"])

    tabs = st.tabs([
        "\U0001f4ca Ingresos vs Gastos",
        "\U0001f4b0 Rentabilidad mensual",
        "\U0001f501 Año vs Año",
        "\U0001f52e Proyección financiera",
        "\U0001f4a1 Decisiones clave",
    ])

    with tabs[0]:
        st.subheader("Ingresos vs Gastos por mes")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Ingresos ($)**")
            st.bar_chart(_graf(df_comb, "ingresos"))
        with c2:
            st.markdown("**Gastos ($)**")
            st.bar_chart(_graf(df_comb, "gastos"))
        st.markdown("**Comparación directa Ingresos vs Gastos**")
        st.line_chart(df_comb.set_index(pd.CategoricalIndex(df_comb["periodo"], categories=df_comb["periodo"].tolist(), ordered=True))[["ingresos", "gastos"]])
        with st.expander("Ver tabla"):
            df_show = df_comb[["periodo", "ingresos", "gastos", "margen", "margen_%"]].copy()
            for col in ["ingresos", "gastos", "margen"]:
                df_show[col] = df_show[col].map(moneda)
            df_show.columns = ["Período", "Ingresos", "Gastos", "Margen neto", "Margen %"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Rentabilidad mensual (margen neto)")
        st.markdown("**Margen neto por mes (Ingresos \u2212 Gastos)**")
        st.bar_chart(_graf(df_comb, "margen"))
        st.markdown("**Margen % sobre ingresos**")
        st.line_chart(_graf(df_comb, "margen_%"))
        mejor_mes = df_comb.loc[df_comb["margen"].idxmax(), "periodo"] if not df_comb.empty else "N/A"
        peor_mes  = df_comb.loc[df_comb["margen"].idxmin(), "periodo"] if not df_comb.empty else "N/A"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Margen total histórico", moneda(df_comb["margen"].sum()))
        c2.metric("Margen promedio mensual", moneda(df_comb["margen"].mean()))
        c3.metric("Mejor mes", mejor_mes)
        c4.metric("Peor mes", peor_mes)

    with tabs[2]:
        st.subheader("Comparación año vs año \u2014 Ingresos, Gastos y Margen")
        anios_comb = sorted(df_comb["anio"].unique().tolist())
        if len(anios_comb) < 2:
            st.info("Necesitás datos de al menos 2 años.")
        else:
            col1, col2 = st.columns(2)
            anio_a = col1.selectbox("Año A", anios_comb, index=len(anios_comb)-2, key="comb_anio_a")
            anio_b = col2.selectbox("Año B", anios_comb, index=len(anios_comb)-1, key="comb_anio_b")
            def res_comb(a):
                return df_comb[df_comb["anio"] == a].set_index("mes")[["ingresos", "gastos", "margen"]]
            da, db_ = res_comb(anio_a), res_comb(anio_b)
            todos = sorted(set(da.index) | set(db_.index))
            comp = pd.DataFrame({"mes": todos})
            comp["mes_nombre"] = comp["mes"].map(MESES_ES)
            for col in ["ingresos", "gastos", "margen"]:
                comp[f"{col}_{anio_a}"] = comp["mes"].map(da[col] if col in da.columns else pd.Series(dtype=float)).fillna(0)
                comp[f"{col}_{anio_b}"] = comp["mes"].map(db_[col] if col in db_.columns else pd.Series(dtype=float)).fillna(0)
            comp = comp.set_index("mes_nombre")
            st.markdown("**Ingresos**")
            st.bar_chart(comp[[f"ingresos_{anio_a}", f"ingresos_{anio_b}"]])
            st.markdown("**Gastos**")
            st.bar_chart(comp[[f"gastos_{anio_a}", f"gastos_{anio_b}"]])
            st.markdown("**Margen neto**")
            st.line_chart(comp[[f"margen_{anio_a}", f"margen_{anio_b}"]])

    with tabs[3]:
        st.subheader("\U0001f52e Proyección financiera \u2014 próximos 6 meses")
        df_c2 = df_comb.copy().reset_index(drop=True)
        df_c2["t"] = np.arange(len(df_c2))
        if len(df_c2) < 3:
            st.info("Se necesitan al menos 3 meses de datos.")
        else:
            m_i, b_i   = _regresion_lineal(df_c2["t"].values, df_c2["ingresos"].values)
            m_g2, b_g2 = _regresion_lineal(df_c2["t"].values, df_c2["gastos"].values)
            ultimo_anio = int(df_c2["anio"].iloc[-1])
            ultimo_mes  = int(df_c2["mes"].iloc[-1])
            ultimo_t    = int(df_c2["t"].iloc[-1])
            proy = []
            for i in range(1, 7):
                t_fut   = ultimo_t + i
                mes_fut = ((ultimo_mes - 1 + i) % 12) + 1
                anio_fut = ultimo_anio + ((ultimo_mes - 1 + i) // 12)
                ing_p = max(m_i * t_fut + b_i, 0)
                gas_p = max(m_g2 * t_fut + b_g2, 0)
                proy.append({"periodo": f"{MESES_ES[mes_fut]}-{anio_fut}",
                              "ingresos_proy": ing_p, "gastos_proy": gas_p,
                              "margen_proy": ing_p - gas_p})
            df_proy = pd.DataFrame(proy)
            st.markdown("**Ingresos vs Gastos proyectados**")
            st.line_chart(df_proy.set_index(pd.CategoricalIndex(df_proy["periodo"], categories=df_proy["periodo"].tolist(), ordered=True))[["ingresos_proy", "gastos_proy"]])
            st.markdown("**Margen neto proyectado**")
            st.bar_chart(_graf(df_proy, "margen_proy"))
            df_proy2 = df_proy.copy()
            for col in ["ingresos_proy", "gastos_proy", "margen_proy"]:
                df_proy2[col] = df_proy2[col].map(moneda)
            df_proy2.columns = ["Período", "Ingresos proy.", "Gastos proy.", "Margen proy."]
            st.dataframe(df_proy2, use_container_width=True, hide_index=True)
            tend_i = "\U0001f4c8 creciendo" if m_i  > 0 else "\U0001f4c9 bajando"
            tend_g = "\U0001f4c8 aumentando" if m_g2 > 0 else "\U0001f4c9 bajando"
            st.info(f"**Ingresos:** {tend_i} ({moneda(abs(m_i))}/mes)  \n**Gastos:** {tend_g} ({moneda(abs(m_g2))}/mes)")

    with tabs[4]:
        st.subheader("\U0001f4a1 Decisiones clave basadas en datos")
        total_ing  = df_comb["ingresos"].sum()
        total_gas  = df_comb["gastos"].sum()
        margen_tot = total_ing - total_gas
        ratio      = (total_gas / total_ing * 100) if total_ing > 0 else 0
        prom_ing_m = df_comb["ingresos"].mean()
        prom_gas_m = df_comb["gastos"].mean()
        meses_def  = df_comb[df_comb["margen"] < 0]
        meses_sup  = df_comb[df_comb["margen"] >= 0]
        recs = [
            f"**Rentabilidad global:** Por cada $100 de ingresos, gastás ${ratio:.1f}. "
            + ("✅ Margen saludable." if ratio < 60 else "⚠️ Revisá los gastos, el ratio es alto."),
            f"**Flujo promedio mensual:** Ingresos {moneda(prom_ing_m)} \u2014 Gastos {moneda(prom_gas_m)} \u2014 Margen {moneda(prom_ing_m - prom_gas_m)}.",
            f"**Meses en déficit:** {len(meses_def)} de {len(df_comb)}. "
            + (f"Períodos: {', '.join(meses_def['periodo'].tolist()[:5])}." if not meses_def.empty else "Ninguno. ✅"),
            f"**Meses en superávit:** {len(meses_sup)}. Usá esos excedentes para cubrir meses de baja demanda.",
        ]
        if not df_comb.empty:
            recs.append(f"**Mejor mes financiero:** {df_comb.loc[df_comb['margen'].idxmax(),'periodo']}. Analizá qué lo hizo exitoso y replicalo.")
            recs.append(f"**Mes más crítico:** {df_comb.loc[df_comb['margen'].idxmin(),'periodo']}. Planificá acciones preventivas para ese período.")
        for i, r in enumerate(recs, 1):
            st.markdown(f"{i}. {r}")
        st.markdown("---")
        st.markdown("### \U0001f4ca KPIs financieros globales")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ingresos totales", moneda(total_ing))
        c2.metric("Gastos totales", moneda(total_gas))
        c3.metric("Margen neto total", moneda(margen_tot))
        c4.metric("Ratio gasto/ingreso", f"{ratio:.1f}%")
