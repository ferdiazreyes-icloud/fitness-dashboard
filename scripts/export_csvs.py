#!/usr/bin/env python3
"""
Export SQLite health.db → CSVs for Streamlit dashboard.
"""

import sqlite3
import csv
import os
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR) == "scripts" else SCRIPT_DIR
DB_PATH = os.path.join(PROJECT_DIR, "health.db")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "data")


def export_table(conn, query, filename, out_dir, headers=None):
    """Export a SQL query to CSV."""
    filepath = os.path.join(out_dir, filename)
    c = conn.cursor()
    rows = c.execute(query).fetchall()

    if headers is None:
        headers = [desc[0] for desc in c.description]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"  {filename}: {len(rows):,} rows")
    return len(rows)


def main():
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    out_dir = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_DIR

    os.makedirs(out_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)

    print("Exporting CSVs...")

    # 1. Workouts with running stats joined
    export_table(conn, """
        SELECT
            w.id, w.activity_type, w.start_date, w.end_date,
            ROUND(w.duration_min, 1) as duration_min,
            ROUND(w.distance_km, 2) as distance_km,
            ROUND(w.energy_kcal, 0) as energy_kcal,
            ROUND(w.hr_avg, 0) as hr_avg,
            ROUND(w.hr_max, 0) as hr_max,
            ROUND(w.hr_min, 0) as hr_min,
            w.source, w.is_indoor,
            ROUND(w.weather_temp, 1) as weather_temp,
            ROUND(w.elevation_ascended, 0) as elevation_ascended,
            ROUND(w.elevation_descended, 0) as elevation_descended,
            ROUND(w.avg_mets, 2) as avg_mets,
            ROUND(r.avg_speed_kmh, 2) as run_avg_speed_kmh,
            ROUND(r.max_speed_kmh, 2) as run_max_speed_kmh,
            ROUND(r.avg_power_w, 0) as run_avg_power_w,
            ROUND(r.avg_stride_m, 2) as run_avg_stride_m,
            ROUND(r.avg_ground_contact_ms, 0) as run_ground_contact_ms,
            ROUND(r.avg_vertical_osc_cm, 1) as run_vertical_osc_cm,
            r.step_count as run_step_count
        FROM workouts w
        LEFT JOIN workout_running_stats r ON w.id = r.workout_id
        ORDER BY w.start_date
    """, "workouts.csv", out_dir)

    # 2. Daily health
    export_table(conn, """
        SELECT
            date,
            ROUND(resting_hr, 0) as resting_hr,
            ROUND(hrv_sdnn_ms, 1) as hrv_sdnn_ms,
            ROUND(vo2max, 2) as vo2max,
            ROUND(spo2_pct, 1) as spo2_pct,
            ROUND(respiratory_rate, 1) as respiratory_rate,
            ROUND(walking_hr_avg, 0) as walking_hr_avg,
            steps,
            ROUND(distance_km, 2) as distance_km,
            flights_climbed,
            ROUND(active_energy_kcal, 0) as active_energy_kcal,
            ROUND(basal_energy_kcal, 0) as basal_energy_kcal,
            ROUND(exercise_min, 0) as exercise_min,
            stand_hours,
            ROUND(sleep_duration_hr, 2) as sleep_duration_hr,
            ROUND(sleep_deep_hr, 2) as sleep_deep_hr,
            ROUND(sleep_rem_hr, 2) as sleep_rem_hr,
            ROUND(sleep_core_hr, 2) as sleep_core_hr,
            ROUND(wrist_temp_c, 2) as wrist_temp_c,
            ROUND(time_in_daylight_min, 0) as time_in_daylight_min
        FROM daily_health
        ORDER BY date
    """, "daily_health.csv", out_dir)

    # 3. Body composition
    export_table(conn, """
        SELECT
            date,
            ROUND(weight_kg, 1) as weight_kg,
            ROUND(bmi, 1) as bmi,
            ROUND(body_fat_pct, 1) as body_fat_pct,
            ROUND(lean_mass_kg, 1) as lean_mass_kg,
            source
        FROM body_composition
        ORDER BY date
    """, "body_composition.csv", out_dir)

    # 4. Activity summary
    export_table(conn, """
        SELECT * FROM activity_summary ORDER BY date
    """, "activity_summary.csv", out_dir)

    # 5. Weekly summary
    export_table(conn, """
        SELECT * FROM weekly_summary ORDER BY week
    """, "weekly_summary.csv", out_dir)

    # 6. VO2Max history
    export_table(conn, """
        SELECT date, ROUND(value, 2) as vo2max, source
        FROM vo2max ORDER BY date
    """, "vo2max.csv", out_dir)

    # Metadata
    meta = {
        "last_export": datetime.now().isoformat(),
        "db_path": db_path,
    }
    with open(os.path.join(out_dir, "last_update.json"), "w") as f:
        json.dump(meta, f, indent=2)

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
