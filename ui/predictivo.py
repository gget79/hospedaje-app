
"""
Módulo: Análisis Predictivo de Reservas
Gráficos, tendencias, comparaciones y predicciones de demanda.
Usa solo librerías ya disponibles: pandas, streamlit, numpy, plotly.
"""
from __future__ import annotations

from datetime import date, timedelta
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from core.db import Database
from core.utils import moneda

# ─────────────────────────────────────────────
#  Config global para deshabilitar zoom con scroll en todos los gráficos
# ─────────────────────────────────────────────
_PLOTLY_CFG = {"scrollZoom": False, "displayModeBar": False}


_LAYOUT = dict(
    margin=dict(l=10, r=10, t=30, b=10),
    height=350,
    dragmode=False,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)

# Color para barras/puntos con valor 0 (resaltado)
_COLOR_ZERO = "rgba(220,53,69,0.55)"   # rojo semitransparente


def _colors_for(values, base_color: str) -> list:
    """Devuelve lista de colores: rojo para 0, base_color para el resto."""
    return [_COLOR_ZERO if v == 0 else base_color for v in values]


def _bar(series: pd.Series, title: str = "", color: str = "#1f77b4") -> go.Figure:
    """Gráfico de barras Plotly — barras en 0 resaltadas en rojo."""
    vals = list(series.values)
    fig = go.Figure(go.Bar(
        x=list(series.index.astype(str)),
        y=vals,
        marker_color=_colors_for(vals, color),
    ))
    fig.update_layout(title=title, **_LAYOUT)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _bar2(x, y1, y2, name1: str, name2: str, title: str = "",
          color1: str = "#1f77b4", color2: str = "#ff7f0e") -> go.Figure:
    """Gráfico de barras agrupadas (dos series) — barras en 0 resaltadas en rojo."""
    y1, y2 = list(y1), list(y2)
    fig = go.Figure([
        go.Bar(name=name1, x=[str(v) for v in x], y=y1,
               marker_color=_colors_for(y1, color1)),
        go.Bar(name=name2, x=[str(v) for v in x], y=y2,
               marker_color=_colors_for(y2, color2)),
    ])
    fig.update_layout(barmode="group", title=title, **_LAYOUT)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _line2(x, y1, y2, name1: str, name2: str, title: str = "",
           color1: str = "#1f77b4", color2: str = "#ff7f0e") -> go.Figure:
    """Gráfico de líneas (dos series)."""
    fig = go.Figure([
        go.Scatter(name=name1, x=[str(v) for v in x], y=list(y1),
                   mode="lines+markers", line_color=color1),
        go.Scatter(name=name2, x=[str(v) for v in x], y=list(y2),
                   mode="lines+markers", line_color=color2),
    ])
    fig.update_layout(title=title, **_LAYOUT)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _line1(series: pd.Series, title: str = "", color: str = "#1f77b4") -> go.Figure:
    """Gráfico de línea simple."""
    fig = go.Figure(go.Scatter(
        x=list(series.index.astype(str)),
        y=list(series.values),
        mode="lines+markers",
        line_color=color,
    ))
    fig.update_layout(title=title, **_LAYOUT)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _area1(series: pd.Series, title: str = "", color: str = "#1f77b4") -> go.Figure:
    """Gráfico de área simple."""
    fig = go.Figure(go.Scatter(
        x=list(series.index.astype(str)),
        y=list(series.values),
        mode="lines",
        fill="tozeroy",
        line_color=color,
        fillcolor="rgba(31,119,180,0.3)",
    ))
    fig.update_layout(title=title, **_LAYOUT)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


# ─────────────────────────────────────────────
#  Helper: completa los 12 meses de un año con 0
# ─────────────────────────────────────────────
TODOS_MESES = list(range(1, 13))   # 1..12


def _completar_12_meses(df_agr: pd.DataFrame, col_anio: str, col_mes: str,
                         cols_valor: list, anio: int) -> pd.DataFrame:
    """
    Dado un DataFrame con columnas [col_anio, col_mes, ...cols_valor],
    devuelve un DataFrame con los 12 meses del año 'anio',
    rellenando con 0 los meses sin datos.
    """
    base = pd.DataFrame({col_mes: TODOS_MESES})
    filt = df_agr[df_agr[col_anio] == anio][[col_mes] + cols_valor]
    merged = base.merge(filt, on=col_mes, how="left").fillna(0)
    merged[col_anio] = anio
    for c in cols_valor:
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)
    return merged


def _pc(fig: go.Figure):
    """Atajo para st.plotly_chart con config global."""
    st.plotly_chart(fig, use_container_width=True, config=_PLOTLY_CFG)

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
           r.estado, d.numero AS departamento,
           d.codigo AS codigoDepartamento,
           COALESCE(d.esPropio, 1) AS esPropio
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
                "valorLimpieza", "comision", "numeroPersonas", "esPropio"]:
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

    # ── Selector de departamentos (aplica a tabs 1, 2 y 3) ──
    todos_deptos = sorted(df["departamento"].unique().tolist(),
                          key=lambda x: (len(str(x)), str(x)))
    dep_sel = st.multiselect(
        "🏠 Filtrar por departamento (aplica a Tendencia general, Comparación mensual y Año vs Año)",
        options=todos_deptos,
        default=todos_deptos,
        key="pred_dep_sel"
    )
    df_f = df[df["departamento"].isin(dep_sel)] if dep_sel else df

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
            df_f.groupby(["anio", "mes"])
            .agg(reservas=("numero", "count"),
                 noches=("numeroNoches", "sum"),
                 ingresos=("ingreso_total", "sum"),
                 personas=("numeroPersonas", "sum"))
            .reset_index()
        )

        # Completar todos los meses de cada año presente
        if not df_mes.empty:
            anios_pres = sorted(df_mes["anio"].unique())
            base_full = pd.DataFrame(
                [(a, m) for a in anios_pres for m in TODOS_MESES],
                columns=["anio", "mes"]
            )
            df_mes = base_full.merge(df_mes, on=["anio", "mes"], how="left").fillna(0)

        df_mes["periodo"] = df_mes.apply(
            lambda r: f"{MESES_ES[int(r['mes'])]}-{int(r['anio'])}", axis=1
        )
        df_mes = df_mes.sort_values(["anio", "mes"])

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Reservas por mes**")
            _pc(_bar(df_mes.set_index("periodo")["reservas"]))
        with c2:
            st.markdown("**Ingresos por mes ($)**")
            _pc(_bar(df_mes.set_index("periodo")["ingresos"], color="#ff7f0e"))

        st.markdown("**Noches vendidas por mes**")
        _pc(_area1(df_mes.set_index("periodo")["noches"], color="#2ca02c"))

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

        df_comp = df_f[df_f["mes"] == mes_sel].groupby("anio").agg(
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
                _pc(_bar(df_comp.set_index("anio")["reservas"]))
            with c2:
                st.markdown(f"**Ingresos en {MESES_ES[mes_sel]} por año ($)**")
                _pc(_bar(df_comp.set_index("anio")["ingresos"], color="#ff7f0e"))

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

            # Agregar datos por año/mes
            df_agr = (
                df_f.groupby(["anio", "mes"])
                .agg(reservas=("numero", "count"),
                     ingresos=("ingreso_total", "sum"),
                     noches=("numeroNoches", "sum"))
                .reset_index()
            )

            # Completar los 12 meses para cada año
            da = _completar_12_meses(df_agr, "anio", "mes",
                                      ["reservas", "ingresos", "noches"], anio_a)
            db_ = _completar_12_meses(df_agr, "anio", "mes",
                                       ["reservas", "ingresos", "noches"], anio_b)

            meses_nombres = [MESES_ES[m] for m in TODOS_MESES]

            comp = pd.DataFrame({"mes": TODOS_MESES, "mes_nombre": meses_nombres})
            comp[f"res_{anio_a}"]  = da["reservas"].values
            comp[f"res_{anio_b}"]  = db_["reservas"].values
            comp[f"ing_{anio_a}"]  = da["ingresos"].values
            comp[f"ing_{anio_b}"]  = db_["ingresos"].values
            comp[f"noc_{anio_a}"]  = da["noches"].values
            comp[f"noc_{anio_b}"]  = db_["noches"].values

            st.markdown("**Reservas por mes**")
            _pc(_bar2(meses_nombres,
                      comp[f"res_{anio_a}"].values,
                      comp[f"res_{anio_b}"].values,
                      str(anio_a), str(anio_b)))

            st.markdown("**Ingresos por mes ($)**")
            _pc(_bar2(meses_nombres,
                      comp[f"ing_{anio_a}"].values,
                      comp[f"ing_{anio_b}"].values,
                      str(anio_a), str(anio_b)))

            st.markdown("**Noches vendidas por mes**")
            _pc(_line2(meses_nombres,
                       comp[f"noc_{anio_a}"].values,
                       comp[f"noc_{anio_b}"].values,
                       str(anio_a), str(anio_b)))

            st.markdown("**Ingresos por mes — línea de tendencia ($)**")
            _pc(_line2(meses_nombres,
                       comp[f"ing_{anio_a}"].values,
                       comp[f"ing_{anio_b}"].values,
                       str(anio_a), str(anio_b)))

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
                st.dataframe(comp.drop(columns=["mes"]), use_container_width=True, hide_index=True)

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
            _pc(_bar(df_dep.set_index("departamento")["reservas"]))
        with c2:
            st.markdown("**Ingresos por departamento ($)**")
            _pc(_bar(df_dep.set_index("departamento")["ingresos"], color="#ff7f0e"))

        st.markdown("**Noches vendidas por departamento**")
        _pc(_bar(df_dep.set_index("departamento")["noches"], color="#2ca02c"))

        # Ocupación estimada (noches vendidas / días del período)
        dias_periodo = max((df["fechaFin"].max() - df["fechaInicio"].min()).days, 1)
        df_dep["ocupacion_%"] = (df_dep["noches"] / dias_periodo * 100).round(1).clip(upper=100)

        st.markdown("**Tasa de ocupación estimada (%)**")
        _pc(_bar(df_dep.set_index("departamento")["ocupacion_%"], color="#9467bd"))

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
        _pc(_bar(hist_data, color="#8c564b"))

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
                _pc(_bar(df_ciu.set_index("ciudad")["reservas"], color="#e377c2"))

        # Día de la semana con más check-in
        df["dia_semana"] = df["fechaInicio"].dt.day_name()
        dias_orden = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dias_es = {"Monday":"Lunes","Tuesday":"Martes","Wednesday":"Miércoles",
                   "Thursday":"Jueves","Friday":"Viernes","Saturday":"Sábado","Sunday":"Domingo"}
        df_dias = df["dia_semana"].value_counts().reindex(dias_orden).fillna(0)
        df_dias.index = [dias_es[d] for d in df_dias.index]
        st.markdown("**Check-ins por día de la semana**")
        _pc(_bar(df_dias, color="#7f7f7f"))

        # Mes más popular
        df_mes_pop = df.groupby("mes").agg(reservas=("numero","count")).reset_index()
        df_mes_pop["mes_nombre"] = df_mes_pop["mes"].map(MESES_ES)
        df_mes_pop = df_mes_pop.sort_values("mes")
        st.markdown("**Reservas por mes (todos los años)**")
        _pc(_bar(df_mes_pop.set_index("mes_nombre")["reservas"]))

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
                _pc(_bar(df_proy.set_index("periodo")["reservas_proyectadas"], color="#17becf"))
            with c2:
                st.markdown("**Ingresos proyectados ($)**")
                _pc(_bar(df_proy.set_index("periodo")["ingresos_proyectados"], color="#bcbd22"))

            st.markdown("**Noches proyectadas**")
            _pc(_line1(df_proy.set_index("periodo")["noches_proyectadas"], color="#d62728"))

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
        # Completar todos los meses de cada año presente
        if not df_mes.empty:
            anios_pres = sorted(df_mes["anio"].unique())
            base_full = pd.DataFrame(
                [(a, m) for a in anios_pres for m in TODOS_MESES],
                columns=["anio", "mes"]
            )
            df_mes = base_full.merge(df_mes, on=["anio", "mes"], how="left").fillna(0)

        df_mes["periodo"] = df_mes.apply(
            lambda r: f"{MESES_ES[int(r['mes'])]}-{int(r['anio'])}", axis=1
        )
        df_mes = df_mes.sort_values(["anio", "mes"])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Gasto total por mes ($)**")
            _pc(_bar(df_mes.set_index("periodo")["total"], color="#d62728"))
        with c2:
            st.markdown("**Cantidad de gastos por mes**")
            _pc(_bar(df_mes.set_index("periodo")["cantidad"], color="#9467bd"))
        st.markdown("**Evolución acumulada de gastos**")
        _pc(_area1(df_mes.set_index("periodo")["total"], color="#d62728"))
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
                _pc(_bar(df_comp.set_index("anio")["total"], color="#d62728"))
            with c2:
                st.markdown(f"**Cantidad de gastos en {MESES_ES[mes_sel]} por año**")
                _pc(_bar(df_comp.set_index("anio")["cantidad"], color="#9467bd"))
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

            df_agr_g = (
                df.groupby(["anio", "mes"])
                .agg(total=("valor", "sum"))
                .reset_index()
            )
            da  = _completar_12_meses(df_agr_g, "anio", "mes", ["total"], anio_a)
            db_ = _completar_12_meses(df_agr_g, "anio", "mes", ["total"], anio_b)
            meses_nombres = [MESES_ES[m] for m in TODOS_MESES]

            comp = pd.DataFrame({"mes": TODOS_MESES, "mes_nombre": meses_nombres})
            comp[f"gas_{anio_a}"] = da["total"].values
            comp[f"gas_{anio_b}"] = db_["total"].values

            st.markdown("**Gastos por mes ($)**")
            _pc(_bar2(meses_nombres,
                      comp[f"gas_{anio_a}"].values,
                      comp[f"gas_{anio_b}"].values,
                      str(anio_a), str(anio_b),
                      color1="#d62728", color2="#ff7f0e"))
            comp["var_%"] = np.where(
                comp[f"gas_{anio_a}"] > 0,
                ((comp[f"gas_{anio_b}"] - comp[f"gas_{anio_a}"]) / comp[f"gas_{anio_a}"] * 100).round(1),
                np.nan
            )
            with st.expander("Ver tabla con variación %"):
                st.dataframe(comp.drop(columns=["mes"]), use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("Gastos por concepto")
        df_conc = df.groupby("concepto").agg(
            total=("valor", "sum"), cantidad=("numero", "count"),
            promedio=("valor", "mean")).reset_index().sort_values("total", ascending=False)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Total por concepto ($)**")
            _pc(_bar(df_conc.set_index("concepto")["total"], color="#d62728"))
        with c2:
            st.markdown("**Frecuencia por concepto**")
            _pc(_bar(df_conc.set_index("concepto")["cantidad"], color="#9467bd"))
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
            _pc(_bar(df_proy.set_index("periodo")["gastos_proyectados"], color="#d62728"))
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

    # Completar los 12 meses de cada año presente en el combinado
    if not df_comb.empty:
        anios_pres = sorted(df_comb["anio"].unique().astype(int))
        base_full = pd.DataFrame(
            [(a, m) for a in anios_pres for m in TODOS_MESES],
            columns=["anio", "mes"]
        )
        df_comb = base_full.merge(df_comb, on=["anio", "mes"], how="left").fillna(0)

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
            _pc(_bar(df_comb.set_index("periodo")["ingresos"], color="#ff7f0e"))
        with c2:
            st.markdown("**Gastos ($)**")
            _pc(_bar(df_comb.set_index("periodo")["gastos"], color="#d62728"))
        st.markdown("**Comparación directa Ingresos vs Gastos**")
        _pc(_line2(
            df_comb["periodo"].tolist(),
            df_comb["ingresos"].values,
            df_comb["gastos"].values,
            "Ingresos", "Gastos",
        ))
        with st.expander("Ver tabla"):
            df_show = df_comb[["periodo", "ingresos", "gastos", "margen", "margen_%"]].copy()
            for col in ["ingresos", "gastos", "margen"]:
                df_show[col] = df_show[col].map(moneda)
            df_show.columns = ["Período", "Ingresos", "Gastos", "Margen neto", "Margen %"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Rentabilidad mensual (margen neto)")
        st.markdown("**Margen neto por mes (Ingresos − Gastos)**")
        _pc(_bar(df_comb.set_index("periodo")["margen"], color="#2ca02c"))
        st.markdown("**Margen % sobre ingresos**")
        _pc(_line1(df_comb.set_index("periodo")["margen_%"], color="#17becf"))
        mejor_mes = df_comb.loc[df_comb["margen"].idxmax(), "periodo"] if not df_comb.empty else "N/A"
        peor_mes  = df_comb.loc[df_comb["margen"].idxmin(), "periodo"] if not df_comb.empty else "N/A"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Margen total histórico", moneda(df_comb["margen"].sum()))
        c2.metric("Margen promedio mensual", moneda(df_comb["margen"].mean()))
        c3.metric("Mejor mes", mejor_mes)
        c4.metric("Peor mes", peor_mes)

    with tabs[2]:
        st.subheader("Comparación año vs año — Ingresos, Gastos y Margen")
        anios_comb = sorted(df_comb["anio"].unique().astype(int).tolist())
        if len(anios_comb) < 2:
            st.info("Necesitás datos de al menos 2 años.")
        else:
            col1, col2 = st.columns(2)
            anio_a = col1.selectbox("Año A", anios_comb, index=len(anios_comb)-2, key="comb_anio_a")
            anio_b = col2.selectbox("Año B", anios_comb, index=len(anios_comb)-1, key="comb_anio_b")

            # Completar 12 meses para cada año
            da  = _completar_12_meses(df_comb, "anio", "mes",
                                       ["ingresos", "gastos", "margen"], anio_a)
            db_ = _completar_12_meses(df_comb, "anio", "mes",
                                       ["ingresos", "gastos", "margen"], anio_b)
            meses_nombres = [MESES_ES[m] for m in TODOS_MESES]

            comp = pd.DataFrame({"mes": TODOS_MESES, "mes_nombre": meses_nombres})
            for col in ["ingresos", "gastos", "margen"]:
                comp[f"{col}_{anio_a}"] = da[col].values
                comp[f"{col}_{anio_b}"] = db_[col].values

            st.markdown("**Ingresos**")
            _pc(_bar2(meses_nombres,
                      comp[f"ingresos_{anio_a}"].values,
                      comp[f"ingresos_{anio_b}"].values,
                      str(anio_a), str(anio_b),
                      color1="#ff7f0e", color2="#1f77b4"))
            st.markdown("**Gastos**")
            _pc(_bar2(meses_nombres,
                      comp[f"gastos_{anio_a}"].values,
                      comp[f"gastos_{anio_b}"].values,
                      str(anio_a), str(anio_b),
                      color1="#d62728", color2="#e377c2"))
            st.markdown("**Margen neto**")
            _pc(_line2(meses_nombres,
                       comp[f"margen_{anio_a}"].values,
                       comp[f"margen_{anio_b}"].values,
                       str(anio_a), str(anio_b)))

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
            _pc(_line2(
                df_proy["periodo"].tolist(),
                df_proy["ingresos_proy"].values,
                df_proy["gastos_proy"].values,
                "Ingresos proy.", "Gastos proy.",
            ))
            st.markdown("**Margen neto proyectado**")
            _pc(_bar(df_proy.set_index("periodo")["margen_proy"], color="#2ca02c"))
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
