
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


# ─────────────────────────────────────────────
#  Sección principal
# ─────────────────────────────────────────────
def ui_analisis_predictivo(db: Database):
    st.header("🤖 Análisis Predictivo de Reservas")
    st.caption(
        "Tendencias históricas, comparaciones entre períodos y proyecciones "
        "para anticipar demanda y optimizar decisiones."
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
            st.bar_chart(df_mes.set_index("periodo")["reservas"])
        with c2:
            st.markdown("**Ingresos por mes ($)**")
            st.bar_chart(df_mes.set_index("periodo")["ingresos"])

        st.markdown("**Noches vendidas por mes**")
        st.area_chart(df_mes.set_index("periodo")["noches"])

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
                st.bar_chart(df_proy.set_index("periodo")["reservas_proyectadas"])
            with c2:
                st.markdown("**Ingresos proyectados ($)**")
                st.bar_chart(df_proy.set_index("periodo")["ingresos_proyectados"])

            st.markdown("**Noches proyectadas**")
            st.line_chart(df_proy.set_index("periodo")["noches_proyectadas"])

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
