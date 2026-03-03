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

# --- Helpers ---
def normalize_exercise_name(name):
    """Normalize exercise names for matching between Strong and plan."""
    if pd.isna(name):
        return ""
    name = str(name)
    # Fix UTF-8 mojibake: â€™ → '
    name = name.replace("\u00e2\u20ac\u2122", "'")
    name = name.replace("\u2019", "'")
    name = name.strip()
    return name


def parse_rpe_target_max(val):
    """Parse RPE target string to max value. '7.5-8' → 8.0, '8' → 8.0."""
    if pd.isna(val) or str(val).strip() == "":
        return None
    val = str(val).strip()
    if "-" in val:
        parts = val.split("-")
        try:
            return max(float(parts[0]), float(parts[1]))
        except ValueError:
            return None
    try:
        return float(val)
    except ValueError:
        return None


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

    # Strong log (gym set-level data)
    strong_path = os.path.join(DATA_DIR, "strong_log.csv")
    if os.path.exists(strong_path):
        strong = pd.read_csv(strong_path)
        strong["date"] = pd.to_datetime(strong["date"])
        strong["date_only"] = strong["date"].dt.date
        strong["exercise_norm"] = strong["exercise"].apply(normalize_exercise_name)
        strong["week"] = strong["date"].dt.isocalendar().week
        strong["year"] = strong["date"].dt.year
        strong["year_week"] = strong["date"].dt.strftime("%Y-W%U")
        strong["volume_lb"] = strong["weight_lb"] * strong["reps"]
    else:
        strong = pd.DataFrame()

    # Training plan (weekly prescription)
    plan_path = os.path.join(DATA_DIR, "training_plan.csv")
    if os.path.exists(plan_path):
        plan = pd.read_csv(plan_path, on_bad_lines="skip")
        plan["fecha"] = pd.to_datetime(plan["fecha"])
        plan["date_only"] = plan["fecha"].dt.date
        plan["exercise_norm"] = plan["ejercicio"].apply(normalize_exercise_name)
        plan["rpe_target_max"] = plan["rpe_target"].apply(parse_rpe_target_max)
    else:
        plan = pd.DataFrame()

    return workouts, daily, body, activity, weekly, vo2, strong, plan

workouts, daily, body, activity, weekly, vo2, strong, plan = load_data()

# --- Sidebar ---
st.sidebar.title("🏋️ Health Dashboard")
page = st.sidebar.radio("Página", [
    "📊 Resumen Semanal",
    "🏃 Running Analytics",
    "🏋️ Fuerza Analytics",
    "🎯 Adherencia",
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
# PAGE: FUERZA ANALYTICS
# ============================================================
elif page == "🏋️ Fuerza Analytics":
    st.title("🏋️ Fuerza Analytics")

    if strong.empty:
        st.warning("No hay datos de Strong App. Asegúrate de que `data/strong_log.csv` exista.")
    else:
        # --- Exercise filter ---
        exercises = sorted(strong["exercise_norm"].unique())
        exercise_filter = st.selectbox("Ejercicio", ["Todos"] + exercises)

        if exercise_filter == "Todos":
            sf = strong.copy()
        else:
            sf = strong[strong["exercise_norm"] == exercise_filter].copy()

        working = sf[sf["set_type"] == "working"]

        # --- KPIs ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Sesiones Fuerza", sf["date_only"].nunique())
        with col2:
            vol = working["volume_lb"].sum()
            st.metric("Volumen Total (lb)", f"{vol:,.0f}")
        with col3:
            if len(working) > 0 and working["weight_lb"].max() > 0:
                pr_row = working.loc[working["weight_lb"].idxmax()]
                st.metric("PR Peso", f"{pr_row['weight_lb']:.0f} lb",
                          delta=pr_row["exercise_norm"] if exercise_filter == "Todos" else None)
            else:
                st.metric("PR Peso", "N/A")
        with col4:
            st.metric("Ejercicios Distintos", sf["exercise_norm"].nunique())

        st.markdown("---")

        # --- Tabs ---
        tab_prog, tab_vol, tab_rpe, tab_sess, tab_records = st.tabs(
            ["📈 Progresión", "📊 Volumen", "🎯 RPE", "💓 Sesiones", "🏆 Records"]
        )

        # ---- Tab: Progresión ----
        with tab_prog:
            st.subheader("Progresión de peso máximo por sesión")
            if exercise_filter == "Todos":
                # Top 5 exercises by total volume
                top5 = (working.groupby("exercise_norm")["volume_lb"]
                        .sum().nlargest(5).index.tolist())
                prog_data = (working[working["exercise_norm"].isin(top5)]
                             .groupby(["date_only", "exercise_norm"])["weight_lb"]
                             .max().reset_index())
                fig = px.line(prog_data, x="date_only", y="weight_lb",
                              color="exercise_norm", markers=True,
                              labels={"date_only": "", "weight_lb": "Peso (lb)",
                                      "exercise_norm": "Ejercicio"})
                fig.update_layout(xaxis_title="", yaxis_title="Peso (lb)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                prog_data = (working.groupby("date_only")["weight_lb"]
                             .max().reset_index())
                if len(prog_data) > 0:
                    prog_data["ma_5"] = prog_data["weight_lb"].rolling(5, min_periods=2).mean()
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=prog_data["date_only"], y=prog_data["weight_lb"],
                        mode="markers", name="Peso máx", marker=dict(size=7, color="#4ECDC4")))
                    fig.add_trace(go.Scatter(
                        x=prog_data["date_only"], y=prog_data["ma_5"],
                        mode="lines", name="Media móvil (5)",
                        line=dict(color="#FF6B6B", width=2)))
                    fig.update_layout(xaxis_title="", yaxis_title="Peso (lb)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay datos de working sets para este ejercicio.")

        # ---- Tab: Volumen ----
        with tab_vol:
            st.subheader("Volumen semanal (peso × reps)")
            vol_week = (working.groupby("year_week").agg(
                volume=("volume_lb", "sum"),
                sets=("reps", "count"),
                reps=("reps", "sum"),
            ).reset_index())

            fig = px.bar(vol_week, x="year_week", y="volume",
                         color_discrete_sequence=["#4ECDC4"],
                         labels={"year_week": "", "volume": "Volumen (lb)"})
            fig.update_layout(xaxis_title="", yaxis_title="Volumen (lb)")
            st.plotly_chart(fig, use_container_width=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Sets Totales", f"{len(working):,}")
            with col2:
                st.metric("Reps Totales", f"{working['reps'].sum():,}")
            with col3:
                avg_vol = vol_week["volume"].mean() if len(vol_week) > 0 else 0
                st.metric("Volumen Prom/Semana", f"{avg_vol:,.0f} lb")

        # ---- Tab: RPE ----
        with tab_rpe:
            st.subheader("RPE por sesión")
            rpe_data = working[working["rpe_actual"].notna()].copy()
            if len(rpe_data) > 0:
                rpe_session = (rpe_data.groupby("date_only")["rpe_actual"]
                               .mean().reset_index())
                rpe_session["ma_5"] = rpe_session["rpe_actual"].rolling(5, min_periods=2).mean()

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=rpe_session["date_only"], y=rpe_session["rpe_actual"],
                    mode="markers", name="RPE promedio sesión",
                    marker=dict(size=6, color="#FFEAA7")))
                fig.add_trace(go.Scatter(
                    x=rpe_session["date_only"], y=rpe_session["ma_5"],
                    mode="lines", name="Media móvil (5)",
                    line=dict(color="#E17055", width=2)))
                fig.update_layout(xaxis_title="", yaxis_title="RPE",
                                  yaxis_range=[5, 10])
                st.plotly_chart(fig, use_container_width=True)

                # RPE distribution histogram
                st.subheader("Distribución de RPE")
                fig = px.histogram(rpe_data, x="rpe_actual", nbins=15,
                                   color_discrete_sequence=["#E17055"],
                                   labels={"rpe_actual": "RPE"})
                fig.update_layout(xaxis_title="RPE", yaxis_title="Frecuencia")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos de RPE registrados en Strong.")

        # ---- Tab: Sesiones (HR from workouts.csv) ----
        with tab_sess:
            st.subheader("Frecuencia cardíaca en sesiones de fuerza")
            strength_types = ["TraditionalStrengthTraining", "FunctionalStrengthTraining", "CoreTraining"]
            strength_wo = w_filtered[w_filtered["activity_type"].isin(strength_types)].copy()

            if len(strength_wo) == 0:
                st.info("No hay sesiones de fuerza en Apple Health para el rango seleccionado.")
            else:
                # HR chart
                hr_cols = strength_wo[["start_date", "hr_avg", "hr_max"]].dropna(subset=["hr_avg"])
                if len(hr_cols) > 0:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=hr_cols["start_date"], y=hr_cols["hr_avg"],
                        mode="lines+markers", name="HR Avg",
                        line=dict(color="#E74C3C", width=2), marker=dict(size=4)))
                    fig.add_trace(go.Scatter(
                        x=hr_cols["start_date"], y=hr_cols["hr_max"],
                        mode="lines+markers", name="HR Max",
                        line=dict(color="#C0392B", width=1, dash="dot"), marker=dict(size=3)))
                    fig.update_layout(xaxis_title="", yaxis_title="BPM")
                    st.plotly_chart(fig, use_container_width=True)

                # Duration by type
                st.subheader("Duración por tipo de fuerza")
                dur_type = strength_wo.groupby("activity_type")["duration_min"].mean().reset_index()
                dur_type.columns = ["Tipo", "Duración Promedio (min)"]
                fig = px.bar(dur_type, x="Tipo", y="Duración Promedio (min)",
                             color_discrete_sequence=["#45B7D1"])
                st.plotly_chart(fig, use_container_width=True)

                # Summary metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Duración Prom", f"{strength_wo['duration_min'].mean():.0f} min")
                with col2:
                    hr_mean = strength_wo["hr_avg"].mean()
                    st.metric("HR Prom", f"{hr_mean:.0f} bpm" if pd.notna(hr_mean) else "N/A")
                with col3:
                    mets = strength_wo["avg_mets"].mean()
                    st.metric("METs Prom", f"{mets:.1f}" if pd.notna(mets) else "N/A")

        # ---- Tab: Records ----
        with tab_records:
            st.subheader("Records personales")
            if len(working) > 0:
                records = (working.groupby("exercise_norm").agg(
                    pr_lb=("weight_lb", "max"),
                    total_sets=("reps", "count"),
                    total_sessions=("date_only", "nunique"),
                ).reset_index())
                # Get PR date for each exercise
                pr_dates = (working.loc[working.groupby("exercise_norm")["weight_lb"]
                            .idxmax()][["exercise_norm", "date_only"]]
                            .rename(columns={"date_only": "pr_date"}))
                records = records.merge(pr_dates, on="exercise_norm", how="left")
                records = records.sort_values("pr_lb", ascending=False)
                records.columns = ["Ejercicio", "PR (lb)", "Sets Totales",
                                   "Sesiones", "Fecha PR"]

                st.dataframe(records, use_container_width=True, hide_index=True)

                # Top 15 exercises by frequency
                st.subheader("Top 15 ejercicios por frecuencia")
                top_freq = (working.groupby("exercise_norm")["date_only"].nunique()
                            .nlargest(15).reset_index())
                top_freq.columns = ["Ejercicio", "Sesiones"]
                fig = px.bar(top_freq, x="Sesiones", y="Ejercicio", orientation="h",
                             color_discrete_sequence=["#4ECDC4"])
                fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="Sesiones",
                                  yaxis_title="", height=500)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay working sets para mostrar records.")


# ============================================================
# PAGE: ADHERENCIA
# ============================================================
elif page == "🎯 Adherencia":
    st.title("🎯 Adherencia — Plan vs Realidad")

    if plan.empty:
        st.warning("No hay plan de entrenamiento. Asegúrate de que `data/training_plan.csv` exista.")
    elif strong.empty:
        st.warning("No hay datos de Strong App para comparar con el plan.")
    else:
        # Check date overlap
        plan_dates = set(plan["date_only"].unique())
        strong_dates = set(strong["date_only"].unique())
        overlap_dates = plan_dates & strong_dates

        if len(overlap_dates) == 0:
            # No overlap — show plan only
            st.info(
                "📅 **Aún no hay overlap de fechas entre el plan y los datos de Strong.**\n\n"
                f"- Plan: {min(plan_dates)} a {max(plan_dates)}\n"
                f"- Strong: {min(strong_dates)} a {max(strong_dates)}\n\n"
                "Cuando actualices la exportación de Strong, se mostrarán las comparaciones "
                "plan vs realidad automáticamente."
            )

            st.markdown("---")
            st.subheader("📋 Plan semanal (referencia)")

            # Day display names (support with and without accents)
            day_display = {
                "lunes": "🟢 Lunes", "martes": "🟢 Martes",
                "miércoles": "🟢 Miércoles", "miercoles": "🟢 Miércoles",
                "jueves": "🟢 Jueves",
                "viernes": "🟢 Viernes",
                "sábado": "🟢 Sábado", "sabado": "🟢 Sábado",
                "domingo": "🟢 Domingo",
            }
            day_order = ["lunes", "martes", "miercoles", "miércoles",
                         "jueves", "viernes", "sabado", "sábado", "domingo"]

            # Group by week
            plan_wk = plan.copy()
            plan_wk["week_num"] = plan_wk["fecha"].dt.isocalendar().week.astype(int)
            plan_wk["week_start"] = plan_wk["fecha"] - pd.to_timedelta(
                plan_wk["fecha"].dt.weekday, unit="D")

            for wk_num in sorted(plan_wk["week_num"].unique()):
                wk_data = plan_wk[plan_wk["week_num"] == wk_num]
                wk_start = wk_data["week_start"].iloc[0].strftime("%d %b")
                wk_end = (wk_data["week_start"].iloc[0] + pd.Timedelta(days=6)).strftime("%d %b")
                st.markdown(f"#### 📅 Semana {wk_start} – {wk_end}")

                wk_days = wk_data["dia"].unique()
                for day in sorted(wk_days, key=lambda d: day_order.index(d.lower()) if d.lower() in day_order else 99):
                    day_label = day_display.get(day.lower(), day)
                    day_data = wk_data[wk_data["dia"] == day]

                    with st.expander(f"{day_label} — {day_data['sesion'].iloc[0] if 'sesion' in day_data.columns else ''}", expanded=False):
                        display = day_data[["ejercicio", "serie", "peso_lb", "reps",
                                            "rpe_target", "descanso_seg"]].copy()
                        display.columns = ["Ejercicio", "Series", "Peso (lb)", "Reps",
                                           "RPE Target", "Descanso (s)"]
                        st.dataframe(display, use_container_width=True, hide_index=True)

        else:
            # Has overlap — show full comparison
            overlap_min = min(overlap_dates)
            overlap_max = max(overlap_dates)

            st.success(f"Comparando datos del {overlap_min} al {overlap_max}")

            # Filter to overlap period
            plan_overlap = plan[plan["date_only"].isin(overlap_dates)].copy()
            strong_overlap = strong[strong["date_only"].isin(overlap_dates)].copy()

            # Merge plan vs strong
            plan_exercises = (plan_overlap.groupby(["date_only", "exercise_norm"]).agg(
                sets_plan=("serie", "count"),
                weight_plan=("peso_lb", "max"),
                reps_plan=("reps", "max"),
                rpe_plan=("rpe_target_max", "max"),
            ).reset_index())

            strong_exercises = (strong_overlap[strong_overlap["set_type"] == "working"]
                                .groupby(["date_only", "exercise_norm"]).agg(
                sets_real=("set_num", "count"),
                weight_real=("weight_lb", "max"),
                reps_real=("reps", "max"),
                rpe_real=("rpe_actual", "mean"),
            ).reset_index())

            comparison = plan_exercises.merge(
                strong_exercises,
                on=["date_only", "exercise_norm"],
                how="left",
            )

            # Classify status
            def classify_adherence(row):
                if pd.isna(row.get("sets_real")):
                    return "❌ No hecho"
                ratio = row["sets_real"] / row["sets_plan"] if row["sets_plan"] > 0 else 0
                if ratio >= 0.8:
                    return "✅ Completado"
                return "⚠️ Parcial"

            comparison["estado"] = comparison.apply(classify_adherence, axis=1)

            # KPIs
            total_exercises = len(comparison)
            completed = len(comparison[comparison["estado"] == "✅ Completado"])
            partial = len(comparison[comparison["estado"] == "⚠️ Parcial"])
            missed = len(comparison[comparison["estado"] == "❌ No hecho"])
            adherence_pct = ((completed + partial * 0.5) / total_exercises * 100
                             if total_exercises > 0 else 0)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("% Adherencia", f"{adherence_pct:.0f}%")
            with col2:
                plan_sessions = plan_overlap["date_only"].nunique()
                real_sessions = strong_overlap["date_only"].nunique()
                st.metric("Sesiones", f"{real_sessions}/{plan_sessions}")
            with col3:
                st.metric("Ejercicios", f"{completed}/{total_exercises}")
            with col4:
                rpe_diff = (comparison["rpe_real"].mean() - comparison["rpe_plan"].mean())
                st.metric("RPE Δ (Real − Plan)",
                          f"{rpe_diff:+.1f}" if pd.notna(rpe_diff) else "N/A")

            st.markdown("---")

            # Weekly traffic light
            st.subheader("Semáforo semanal")
            days_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            day_to_weekday = {
                "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
                "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
            }
            cols = st.columns(7)

            for i, day_name in enumerate(days_es):
                with cols[i]:
                    target_wd = day_to_weekday.get(day_name)
                    day_comp = comparison[
                        comparison["date_only"].apply(
                            lambda d, wd=target_wd: d.weekday() == wd
                        )
                    ]
                    if len(day_comp) == 0:
                        st.markdown(f"**{day_name[:3].title()}**\n\n⚪ Sin plan")
                    else:
                        done_ratio = len(day_comp[day_comp["estado"] == "✅ Completado"]) / len(day_comp)
                        if done_ratio >= 0.8:
                            emoji = "🟢"
                        elif done_ratio > 0:
                            emoji = "🟡"
                        else:
                            emoji = "🔴"
                        st.markdown(f"**{day_name[:3].title()}**\n\n{emoji} {done_ratio:.0%}")

            st.markdown("---")

            # Detail table
            st.subheader("Detalle de ejercicios")
            detail = comparison[["date_only", "exercise_norm", "weight_plan", "weight_real",
                                 "reps_plan", "reps_real", "rpe_plan", "rpe_real", "estado"]].copy()
            detail.columns = ["Fecha", "Ejercicio", "Peso Plan", "Peso Real",
                              "Reps Plan", "Reps Real", "RPE Plan", "RPE Real", "Estado"]
            detail = detail.sort_values(["Fecha", "Ejercicio"])
            st.dataframe(detail, use_container_width=True, hide_index=True)


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
if not strong.empty:
    st.sidebar.caption(f"Strong: {len(strong):,} sets | {strong['date_only'].nunique()} sesiones")
