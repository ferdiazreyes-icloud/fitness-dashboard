import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# --- Page Config ---
st.set_page_config(
    page_title="Health Dashboard - Fernando",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Data Loading ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

@st.cache_data(ttl=3600)
def load_data():
    workouts = pd.read_csv(os.path.join(DATA_DIR, "workouts.csv"), parse_dates=["start_date", "end_date"])
    daily = pd.read_csv(os.path.join(DATA_DIR, "daily_health.csv"), parse_dates=["date"])
    body = pd.read_csv(os.path.join(DATA_DIR, "body_composition.csv"), parse_dates=["date"])
    activity = pd.read_csv(os.path.join(DATA_DIR, "activity_summary.csv"), parse_dates=["date"])
    weekly = pd.read_csv(os.path.join(DATA_DIR, "weekly_summary.csv"))
    vo2 = pd.read_csv(os.path.join(DATA_DIR, "vo2max.csv"), parse_dates=["date"])

    # Derived columns
    workouts["date"] = workouts["start_date"].dt.date
    workouts["week"] = workouts["start_date"].dt.isocalendar().week
    workouts["year"] = workouts["start_date"].dt.year
    workouts["year_month"] = workouts["start_date"].dt.to_period("M").astype(str)
    workouts["year_week"] = workouts["start_date"].dt.strftime("%Y-W%U")

    # Pace for running (min/km)
    mask = (workouts["activity_type"] == "Running") & (workouts["distance_km"] > 0)
    workouts.loc[mask, "pace_min_per_km"] = workouts.loc[mask, "duration_min"] / workouts.loc[mask, "distance_km"]

    daily["date_dt"] = daily["date"]
    daily["week"] = daily["date"].dt.isocalendar().week
    daily["year"] = daily["date"].dt.year

    return workouts, daily, body, activity, weekly, vo2

workouts, daily, body, activity, weekly, vo2 = load_data()

# --- Sidebar ---
st.sidebar.title("🏋️ Health Dashboard")
page = st.sidebar.radio("Página", [
    "📊 Resumen Semanal",
    "🏃 Running Analytics",
    "❤️ Tendencias de Salud",
    "⚖️ Composición Corporal",
    "📈 Métricas Acumuladas",
])

# Date range filter
min_date = workouts["start_date"].min().date()
max_date = workouts["start_date"].max().date()

st.sidebar.markdown("---")
st.sidebar.subheader("Filtro de fechas")
date_range = st.sidebar.date_input(
    "Rango",
    value=(max_date - timedelta(days=90), max_date),
    min_value=min_date,
    max_value=max_date,
)

if len(date_range) == 2:
    start_filter, end_filter = date_range
else:
    start_filter, end_filter = min_date, max_date

# Filter data
w_filtered = workouts[(workouts["start_date"].dt.date >= start_filter) & (workouts["start_date"].dt.date <= end_filter)]
d_filtered = daily[(daily["date"].dt.date >= start_filter) & (daily["date"].dt.date <= end_filter)]

# --- Color scheme ---
COLORS = {
    "Running": "#FF6B6B",
    "TraditionalStrengthTraining": "#4ECDC4",
    "FunctionalStrengthTraining": "#45B7D1",
    "Yoga": "#96CEB4",
    "HighIntensityIntervalTraining": "#FFEAA7",
    "CoreTraining": "#DDA0DD",
    "Cycling": "#74B9FF",
    "Walking": "#A0A0A0",
    "Cooldown": "#B0B0B0",
    "Boxing": "#E17055",
    "Other": "#CCCCCC",
}

# ============================================================
# PAGE: RESUMEN SEMANAL
# ============================================================
if page == "📊 Resumen Semanal":
    st.title("📊 Resumen Semanal")

    # Current vs previous week
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    prev_week_start = week_start - timedelta(days=7)

    this_week = workouts[(workouts["start_date"].dt.date >= week_start)]
    prev_week = workouts[(workouts["start_date"].dt.date >= prev_week_start) & (workouts["start_date"].dt.date < week_start)]

    col1, col2, col3, col4 = st.columns(4)

    def delta_str(current, previous):
        if previous == 0:
            return None
        pct = ((current - previous) / previous) * 100
        return f"{pct:+.0f}%"

    with col1:
        n = len(this_week)
        n_prev = len(prev_week)
        st.metric("Sesiones", n, delta_str(n, n_prev))
    with col2:
        km = this_week[this_week["activity_type"] == "Running"]["distance_km"].sum()
        km_prev = prev_week[prev_week["activity_type"] == "Running"]["distance_km"].sum()
        st.metric("Km Running", f"{km:.1f}", delta_str(km, km_prev))
    with col3:
        mins = this_week["duration_min"].sum()
        mins_prev = prev_week["duration_min"].sum()
        st.metric("Min Totales", f"{mins:.0f}", delta_str(mins, mins_prev))
    with col4:
        kcal = this_week["energy_kcal"].sum()
        kcal_prev = prev_week["energy_kcal"].sum()
        st.metric("Kcal", f"{kcal:.0f}", delta_str(kcal, kcal_prev))

    st.markdown("---")

    # Sessions this week table
    st.subheader("Sesiones esta semana")
    if len(this_week) > 0:
        display_cols = ["start_date", "activity_type", "duration_min", "distance_km", "energy_kcal", "hr_avg", "hr_max"]
        display_df = this_week[display_cols].copy()
        display_df.columns = ["Fecha", "Tipo", "Duración (min)", "Distancia (km)", "Kcal", "HR Avg", "HR Max"]
        display_df["Fecha"] = display_df["Fecha"].dt.strftime("%a %d %b %H:%M")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay sesiones esta semana todavía.")

    st.markdown("---")

    # Weekly trend chart
    st.subheader("Tendencia semanal")

    # Aggregate by year_week
    weekly_agg = w_filtered.groupby("year_week").agg(
        sessions=("id", "count"),
        total_min=("duration_min", "sum"),
        running_km=("distance_km", lambda x: x[w_filtered.loc[x.index, "activity_type"] == "Running"].sum()),
        total_kcal=("energy_kcal", "sum"),
    ).reset_index()

    tab1, tab2, tab3 = st.tabs(["Sesiones", "Minutos", "Kcal"])

    with tab1:
        fig = px.bar(weekly_agg, x="year_week", y="sessions", title="Sesiones por semana")
        fig.update_layout(xaxis_title="", yaxis_title="Sesiones", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with tab2:
        fig = px.bar(weekly_agg, x="year_week", y="total_min", title="Minutos por semana")
        fig.update_layout(xaxis_title="", yaxis_title="Minutos")
        st.plotly_chart(fig, use_container_width=True)
    with tab3:
        fig = px.bar(weekly_agg, x="year_week", y="total_kcal", title="Kcal por semana")
        fig.update_layout(xaxis_title="", yaxis_title="Kcal")
        st.plotly_chart(fig, use_container_width=True)

    # Breakdown by activity type
    st.subheader("Distribución por tipo de actividad")
    type_counts = w_filtered["activity_type"].value_counts().reset_index()
    type_counts.columns = ["Tipo", "Sesiones"]
    fig = px.pie(type_counts.head(8), values="Sesiones", names="Tipo",
                 color="Tipo", color_discrete_map=COLORS)
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE: RUNNING ANALYTICS
# ============================================================
elif page == "🏃 Running Analytics":
    st.title("🏃 Running Analytics")

    running = w_filtered[w_filtered["activity_type"] == "Running"].copy()

    if len(running) == 0:
        st.warning("No hay datos de running en el rango seleccionado.")
    else:
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Sesiones", len(running))
        with col2:
            st.metric("Km Totales", f"{running['distance_km'].sum():.1f}")
        with col3:
            avg_pace = running["pace_min_per_km"].mean()
            st.metric("Pace Promedio", f"{avg_pace:.1f} min/km" if pd.notna(avg_pace) else "N/A")
        with col4:
            st.metric("HR Promedio", f"{running['hr_avg'].mean():.0f} bpm")

        st.markdown("---")

        # Monthly pace evolution
        st.subheader("Evolución del Pace (min/km)")
        monthly_pace = running.groupby("year_month").agg(
            avg_pace=("pace_min_per_km", "mean"),
            runs=("id", "count"),
        ).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=monthly_pace["year_month"], y=monthly_pace["avg_pace"],
            mode="lines+markers", name="Pace promedio",
            line=dict(color="#FF6B6B", width=2),
        ))
        fig.update_layout(yaxis_title="min/km", xaxis_title="", yaxis_autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        # Running power evolution
        st.subheader("Potencia de Running (W)")
        power_data = running[running["run_avg_power_w"].notna()]
        if len(power_data) > 0:
            fig = px.scatter(power_data, x="start_date", y="run_avg_power_w",
                           size="distance_km", color="hr_avg",
                           color_continuous_scale="RdYlGn_r",
                           title="Potencia vs Tiempo (tamaño = distancia, color = HR)")
            fig.update_layout(xaxis_title="", yaxis_title="Watts")
            st.plotly_chart(fig, use_container_width=True)

        # Distance distribution
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribución de distancias")
            fig = px.histogram(running, x="distance_km", nbins=20,
                             color_discrete_sequence=["#FF6B6B"])
            fig.update_layout(xaxis_title="km", yaxis_title="Sesiones")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Km acumulados por mes")
            monthly_km = running.groupby("year_month")["distance_km"].sum().reset_index()
            fig = px.bar(monthly_km, x="year_month", y="distance_km",
                        color_discrete_sequence=["#FF6B6B"])
            fig.update_layout(xaxis_title="", yaxis_title="km")
            st.plotly_chart(fig, use_container_width=True)

        # Recent runs table
        st.subheader("Últimas sesiones")
        recent = running.sort_values("start_date", ascending=False).head(15)
        display = recent[["start_date", "duration_min", "distance_km", "pace_min_per_km",
                          "hr_avg", "hr_max", "run_avg_power_w", "run_avg_stride_m"]].copy()
        display.columns = ["Fecha", "Duración", "Km", "Pace", "HR Avg", "HR Max", "Power (W)", "Stride (m)"]
        display["Fecha"] = display["Fecha"].dt.strftime("%Y-%m-%d %H:%M")
        display["Pace"] = display["Pace"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "")
        st.dataframe(display, use_container_width=True, hide_index=True)


# ============================================================
# PAGE: TENDENCIAS DE SALUD
# ============================================================
elif page == "❤️ Tendencias de Salud":
    st.title("❤️ Tendencias de Salud")

    # VO2Max
    st.subheader("VO2Max")
    vo2_filtered = vo2[(vo2["date"].dt.date >= start_filter) & (vo2["date"].dt.date <= end_filter)]
    if len(vo2_filtered) > 0:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=vo2_filtered["date"], y=vo2_filtered["vo2max"],
            mode="lines+markers", name="VO2Max",
            line=dict(color="#2ECC71", width=2),
        ))
        fig.update_layout(yaxis_title="mL/min·kg", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Actual", f"{vo2_filtered['vo2max'].iloc[-1]:.1f}")
        with col2:
            st.metric("Máximo", f"{vo2_filtered['vo2max'].max():.1f}")
        with col3:
            st.metric("Promedio", f"{vo2_filtered['vo2max'].mean():.1f}")

    st.markdown("---")

    # Resting HR & HRV
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Resting Heart Rate")
        hr_data = d_filtered[d_filtered["resting_hr"].notna()]
        if len(hr_data) > 0:
            # Weekly rolling average
            hr_data = hr_data.sort_values("date")
            hr_data["rhr_7d"] = hr_data["resting_hr"].rolling(7, min_periods=3).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hr_data["date"], y=hr_data["resting_hr"],
                                    mode="markers", name="Diario", marker=dict(size=3, opacity=0.3, color="#E74C3C")))
            fig.add_trace(go.Scatter(x=hr_data["date"], y=hr_data["rhr_7d"],
                                    mode="lines", name="Media 7 días", line=dict(color="#E74C3C", width=2)))
            fig.update_layout(yaxis_title="bpm", xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("HRV (SDNN)")
        hrv_data = d_filtered[d_filtered["hrv_sdnn_ms"].notna()]
        if len(hrv_data) > 0:
            hrv_data = hrv_data.sort_values("date")
            hrv_data["hrv_7d"] = hrv_data["hrv_sdnn_ms"].rolling(7, min_periods=3).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hrv_data["date"], y=hrv_data["hrv_sdnn_ms"],
                                    mode="markers", name="Diario", marker=dict(size=3, opacity=0.3, color="#3498DB")))
            fig.add_trace(go.Scatter(x=hrv_data["date"], y=hrv_data["hrv_7d"],
                                    mode="lines", name="Media 7 días", line=dict(color="#3498DB", width=2)))
            fig.update_layout(yaxis_title="ms", xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Sleep
    st.subheader("Sueño")
    sleep_data = d_filtered[d_filtered["sleep_duration_hr"].notna() & (d_filtered["sleep_duration_hr"] > 0)]
    if len(sleep_data) > 0:
        sleep_data = sleep_data.sort_values("date")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=sleep_data["date"], y=sleep_data["sleep_deep_hr"], name="Deep", marker_color="#1a237e"))
        fig.add_trace(go.Bar(x=sleep_data["date"], y=sleep_data["sleep_rem_hr"], name="REM", marker_color="#4a148c"))
        fig.add_trace(go.Bar(x=sleep_data["date"], y=sleep_data["sleep_core_hr"], name="Core", marker_color="#7b1fa2"))
        fig.update_layout(barmode="stack", yaxis_title="Horas", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Promedio Total", f"{sleep_data['sleep_duration_hr'].mean():.1f} hr")
        with col2:
            st.metric("Promedio Deep", f"{sleep_data['sleep_deep_hr'].mean():.1f} hr")
        with col3:
            st.metric("Promedio REM", f"{sleep_data['sleep_rem_hr'].mean():.1f} hr")

    st.markdown("---")

    # SpO2
    st.subheader("Oxígeno en Sangre (SpO2)")
    spo2_data = d_filtered[d_filtered["spo2_pct"].notna()]
    if len(spo2_data) > 0:
        spo2_data = spo2_data.sort_values("date")
        fig = px.scatter(spo2_data, x="date", y="spo2_pct",
                        color_discrete_sequence=["#E74C3C"], opacity=0.5)
        fig.update_layout(yaxis_title="%", xaxis_title="", yaxis_range=[88, 101])
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE: COMPOSICIÓN CORPORAL
# ============================================================
elif page == "⚖️ Composición Corporal":
    st.title("⚖️ Composición Corporal")

    body_filtered = body[(body["date"].dt.date >= start_filter) & (body["date"].dt.date <= end_filter)]

    if len(body_filtered) == 0:
        st.warning("No hay datos de composición corporal en el rango seleccionado.")
    else:
        # KPIs (latest)
        latest = body_filtered.sort_values("date").iloc[-1]
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Peso", f"{latest['weight_kg']:.1f} kg")
        with col2:
            st.metric("IMC", f"{latest['bmi']:.1f}")
        with col3:
            if pd.notna(latest.get("body_fat_pct")):
                st.metric("% Grasa", f"{latest['body_fat_pct']:.1f}%")
        with col4:
            if pd.notna(latest.get("lean_mass_kg")):
                st.metric("Masa Magra", f"{latest['lean_mass_kg']:.1f} kg")

        st.markdown("---")

        # Weight trend
        st.subheader("Peso")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=body_filtered["date"], y=body_filtered["weight_kg"],
            mode="lines+markers", name="Peso",
            line=dict(color="#3498DB", width=2), marker=dict(size=4),
        ))
        fig.update_layout(yaxis_title="kg", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        # Body fat & lean mass
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("% Grasa Corporal")
            fat_data = body_filtered[body_filtered["body_fat_pct"].notna()]
            if len(fat_data) > 0:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=fat_data["date"], y=fat_data["body_fat_pct"],
                    mode="lines+markers", line=dict(color="#E74C3C", width=2), marker=dict(size=4),
                ))
                fig.update_layout(yaxis_title="%", xaxis_title="")
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Masa Magra")
            lean_data = body_filtered[body_filtered["lean_mass_kg"].notna()]
            if len(lean_data) > 0:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=lean_data["date"], y=lean_data["lean_mass_kg"],
                    mode="lines+markers", line=dict(color="#2ECC71", width=2), marker=dict(size=4),
                ))
                fig.update_layout(yaxis_title="kg", xaxis_title="")
                st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE: MÉTRICAS ACUMULADAS
# ============================================================
elif page == "📈 Métricas Acumuladas":
    st.title("📈 Métricas Acumuladas")

    # Lifetime stats
    st.subheader("Totales de por vida")
    col1, col2, col3, col4 = st.columns(4)

    running_total = workouts[workouts["activity_type"] == "Running"]
    with col1:
        st.metric("Km Corridos (total)", f"{running_total['distance_km'].sum():,.0f}")
    with col2:
        st.metric("Horas de Entrenamiento", f"{workouts['duration_min'].sum() / 60:,.0f}")
    with col3:
        st.metric("Sesiones Totales", f"{len(workouts):,}")
    with col4:
        elev = workouts["elevation_ascended"].sum()
        st.metric("Metros de Ascenso", f"{elev:,.0f}" if pd.notna(elev) else "N/A")

    st.markdown("---")

    # YTD
    year_start = datetime(datetime.now().year, 1, 1).date()
    ytd = workouts[workouts["start_date"].dt.date >= year_start]
    ytd_running = ytd[ytd["activity_type"] == "Running"]

    st.subheader(f"Año {datetime.now().year} (YTD)")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Km Corridos", f"{ytd_running['distance_km'].sum():.0f}")
    with col2:
        st.metric("Horas Entrenamiento", f"{ytd['duration_min'].sum() / 60:.0f}")
    with col3:
        st.metric("Sesiones", len(ytd))
    with col4:
        strength = ytd[ytd["activity_type"].isin(["TraditionalStrengthTraining", "FunctionalStrengthTraining", "CoreTraining"])]
        st.metric("Sesiones Fuerza", len(strength))

    st.markdown("---")

    # Monthly breakdown chart
    st.subheader("Horas de entrenamiento por mes y tipo")
    monthly = w_filtered.copy()
    # Simplify activity types
    type_map = {
        "TraditionalStrengthTraining": "Fuerza",
        "FunctionalStrengthTraining": "Fuerza",
        "CoreTraining": "Core",
        "Running": "Running",
        "Walking": "Walking",
        "Cycling": "Cycling",
        "Yoga": "Yoga",
        "HighIntensityIntervalTraining": "HIIT",
        "Cooldown": "Recovery",
    }
    monthly["type_simple"] = monthly["activity_type"].map(type_map).fillna("Otro")
    monthly["hours"] = monthly["duration_min"] / 60

    monthly_hours = monthly.groupby(["year_month", "type_simple"])["hours"].sum().reset_index()
    fig = px.bar(monthly_hours, x="year_month", y="hours", color="type_simple",
                 title="Horas por mes y tipo",
                 color_discrete_map={
                     "Running": "#FF6B6B", "Fuerza": "#4ECDC4", "HIIT": "#FFEAA7",
                     "Yoga": "#96CEB4", "Core": "#DDA0DD", "Walking": "#A0A0A0",
                     "Cycling": "#74B9FF", "Recovery": "#B0B0B0", "Otro": "#CCCCCC",
                 })
    fig.update_layout(xaxis_title="", yaxis_title="Horas", barmode="stack")
    st.plotly_chart(fig, use_container_width=True)

    # Sessions heatmap by day of week
    st.subheader("Patrón semanal (sesiones por día)")
    w_filtered_copy = w_filtered.copy()
    w_filtered_copy["day_name"] = w_filtered_copy["start_date"].dt.day_name()
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_counts = w_filtered_copy["day_name"].value_counts().reindex(day_order).fillna(0)
    fig = px.bar(x=day_counts.index, y=day_counts.values,
                 labels={"x": "", "y": "Sesiones"},
                 color_discrete_sequence=["#4ECDC4"])
    st.plotly_chart(fig, use_container_width=True)

    # Average sleep
    st.subheader("Sueño promedio semanal")
    sleep = d_filtered[d_filtered["sleep_duration_hr"].notna() & (d_filtered["sleep_duration_hr"] > 0)].copy()
    if len(sleep) > 0:
        sleep["year_week"] = sleep["date"].dt.strftime("%Y-W%U")
        weekly_sleep = sleep.groupby("year_week")["sleep_duration_hr"].mean().reset_index()
        fig = px.bar(weekly_sleep, x="year_week", y="sleep_duration_hr",
                     color_discrete_sequence=["#7b1fa2"])
        fig.update_layout(xaxis_title="", yaxis_title="Horas promedio")
        st.plotly_chart(fig, use_container_width=True)


# --- Footer ---
st.sidebar.markdown("---")
st.sidebar.caption(f"Datos hasta: {workouts['start_date'].max().strftime('%Y-%m-%d')}")
st.sidebar.caption(f"Workouts: {len(workouts):,} | Días: {len(daily):,}")
