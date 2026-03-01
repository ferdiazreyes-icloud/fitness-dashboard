#!/usr/bin/env python3
"""
ETL: Apple Health Export XML → SQLite
Uses SAX streaming parser to handle the ~5 GB XML without loading it into RAM.
"""

import xml.sax
import xml.sax.handler
import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict

# --- Configuration ---
EXPORT_DATE = "2026-02-23"
MIN_DATE = "2017-01-01"  # Filter out absurd dates

# Source priority for deduplication (lower = higher priority)
SOURCE_PRIORITY = {
    "Apple Watch de FERNANDO": 1,
    "Apple Watch de FERNANDO A": 2,
    "iPhone 15 FADR": 3,
    "iPhone 13 FADR": 4,
    "iPhone 7p FADR": 5,
    "iPhone CBI": 6,
}

def clean_activity_type(raw_type):
    """Remove HK prefixes to get clean activity names."""
    return (raw_type
            .replace("HKWorkoutActivityType", "")
            .replace("HKQuantityTypeIdentifier", "")
            .replace("HKCategoryTypeIdentifier", "")
            .replace("HKDataType", ""))

def parse_datetime(dt_str):
    """Parse Apple Health datetime string like '2024-05-18 05:11:39 -0600'."""
    if not dt_str:
        return None
    try:
        # Remove timezone offset for SQLite storage (keep as-is, local time)
        parts = dt_str.rsplit(" ", 1)
        return parts[0] if len(parts) == 2 else dt_str
    except:
        return dt_str

def parse_date(dt_str):
    """Extract just the date part."""
    parsed = parse_datetime(dt_str)
    if parsed:
        return parsed[:10]
    return None


class HealthDataHandler(xml.sax.handler.ContentHandler):
    """SAX handler that streams through the XML and collects structured data."""

    def __init__(self):
        super().__init__()

        # Current parsing state
        self.in_workout = False
        self.current_workout = None
        self.current_workout_stats = []
        self.current_workout_events = []
        self.current_workout_metadata = {}

        # Collected data
        self.workouts = []
        self.workout_stats_map = {}  # workout_index -> [stats]
        self.workout_events_map = {}  # workout_index -> [events]

        # Records aggregated by day
        self.daily_records = defaultdict(lambda: defaultdict(list))
        # Sleep records need special handling
        self.sleep_records = []

        # Body composition records
        self.body_comp = []

        # Activity summaries
        self.activity_summaries = []

        # VO2Max records (individual, not aggregated)
        self.vo2max_records = []

        # Counters for progress
        self.record_count = 0
        self.workout_count = 0

        # Record types we care about for daily aggregation
        self.daily_agg_types = {
            "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn_ms",
            "HKQuantityTypeIdentifierOxygenSaturation": "spo2_pct",
            "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate",
            "HKQuantityTypeIdentifierWalkingHeartRateAverage": "walking_hr_avg",
            "HKQuantityTypeIdentifierStepCount": "steps",
            "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_km",
            "HKQuantityTypeIdentifierFlightsClimbed": "flights_climbed",
            "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy_kcal",
            "HKQuantityTypeIdentifierBasalEnergyBurned": "basal_energy_kcal",
            "HKQuantityTypeIdentifierAppleExerciseTime": "exercise_min",
            "HKQuantityTypeIdentifierAppleStandTime": "stand_hours",
            "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "wrist_temp_c",
            "HKQuantityTypeIdentifierTimeInDaylight": "time_in_daylight_min",
        }

        # Types that should be summed (vs averaged)
        self.sum_types = {
            "steps", "distance_km", "flights_climbed",
            "active_energy_kcal", "basal_energy_kcal",
            "exercise_min", "stand_hours", "time_in_daylight_min"
        }

        # Body composition types
        self.body_comp_types = {
            "HKQuantityTypeIdentifierBodyMass",
            "HKQuantityTypeIdentifierBodyMassIndex",
            "HKQuantityTypeIdentifierBodyFatPercentage",
            "HKQuantityTypeIdentifierLeanBodyMass",
        }

    def startElement(self, name, attrs):
        if name == "Record":
            self._handle_record(attrs)
        elif name == "Workout":
            self._start_workout(attrs)
        elif name == "WorkoutStatistics" and self.in_workout:
            self._handle_workout_stat(attrs)
        elif name == "WorkoutEvent" and self.in_workout:
            self._handle_workout_event(attrs)
        elif name == "MetadataEntry" and self.in_workout:
            self._handle_workout_metadata(attrs)
        elif name == "ActivitySummary":
            self._handle_activity_summary(attrs)

    def endElement(self, name):
        if name == "Workout":
            self._end_workout()

    def _handle_record(self, attrs):
        self.record_count += 1
        if self.record_count % 1_000_000 == 0:
            print(f"  ... processed {self.record_count:,} records")

        record_type = attrs.get("type", "")
        value_str = attrs.get("value", "")
        start_date = attrs.get("startDate", "")
        end_date = attrs.get("endDate", "")
        source = attrs.get("sourceName", "")
        date = parse_date(start_date)

        if not date or date < MIN_DATE or date > EXPORT_DATE:
            return

        try:
            value = float(value_str) if value_str and value_str.replace(".", "").replace("-", "").isdigit() else None
        except (ValueError, TypeError):
            value = None

        # VO2Max — keep individual records
        if record_type == "HKQuantityTypeIdentifierVO2Max" and value is not None:
            self.vo2max_records.append({"date": date, "value": value, "source": source})

        # Body composition
        if record_type in self.body_comp_types and value is not None:
            field = clean_activity_type(record_type)
            self.body_comp.append({
                "date": date,
                "type": field,
                "value": value,
                "source": source
            })

        # Daily aggregation
        if record_type in self.daily_agg_types and value is not None:
            field_name = self.daily_agg_types[record_type]
            self.daily_records[date][field_name].append(value)

        # Sleep analysis — special handling
        if record_type == "HKCategoryTypeIdentifierSleepAnalysis":
            self.sleep_records.append({
                "date": date,
                "value": value_str,  # Category value like "HKCategoryValueSleepAnalysisAsleepDeep"
                "start": parse_datetime(start_date),
                "end": parse_datetime(end_date),
                "source": source
            })

    def _start_workout(self, attrs):
        self.in_workout = True
        self.current_workout = {
            "activity_type": clean_activity_type(attrs.get("workoutActivityType", "")),
            "start_date": parse_datetime(attrs.get("startDate", "")),
            "end_date": parse_datetime(attrs.get("endDate", "")),
            "duration_min": float(attrs.get("duration", 0)) if attrs.get("duration") else None,
            "distance_km": float(attrs.get("totalDistance", 0)) if attrs.get("totalDistance") else None,
            "energy_kcal": float(attrs.get("totalEnergyBurned", 0)) if attrs.get("totalEnergyBurned") else None,
            "source": attrs.get("sourceName", ""),
        }
        self.current_workout_stats = []
        self.current_workout_events = []
        self.current_workout_metadata = {}

    def _handle_workout_stat(self, attrs):
        stat_type = clean_activity_type(attrs.get("type", ""))
        self.current_workout_stats.append({
            "type": stat_type,
            "average": float(attrs["average"]) if attrs.get("average") else None,
            "minimum": float(attrs["minimum"]) if attrs.get("minimum") else None,
            "maximum": float(attrs["maximum"]) if attrs.get("maximum") else None,
            "sum": float(attrs["sum"]) if attrs.get("sum") else None,
            "unit": attrs.get("unit", ""),
        })

    def _handle_workout_event(self, attrs):
        self.current_workout_events.append({
            "type": attrs.get("type", "").replace("HKWorkoutEventType", ""),
            "date": parse_datetime(attrs.get("date", "")),
            "duration": float(attrs.get("duration", 0)) if attrs.get("duration") else None,
        })

    def _handle_workout_metadata(self, attrs):
        key = attrs.get("key", "")
        value = attrs.get("value", "")
        self.current_workout_metadata[key] = value

    def _end_workout(self):
        if self.current_workout:
            # Enrich workout with metadata
            md = self.current_workout_metadata
            self.current_workout["is_indoor"] = 1 if md.get("HKIndoorWorkout") == "1" else 0
            self.current_workout["weather_temp"] = float(md["HKWeatherTemperature"].split()[0]) if md.get("HKWeatherTemperature") else None
            self.current_workout["weather_humidity"] = float(md["HKWeatherHumidity"].split()[0]) if md.get("HKWeatherHumidity") else None
            self.current_workout["elevation_ascended"] = float(md["HKElevationAscended"].split()[0]) if md.get("HKElevationAscended") else None
            self.current_workout["elevation_descended"] = float(md["HKElevationDescended"].split()[0]) if md.get("HKElevationDescended") else None
            self.current_workout["avg_mets"] = float(md["HKAverageMETs"].split()[0]) if md.get("HKAverageMETs") else None

            # Extract HR from WorkoutStatistics
            for stat in self.current_workout_stats:
                if stat["type"] == "HeartRate":
                    self.current_workout["hr_avg"] = stat["average"]
                    self.current_workout["hr_max"] = stat["maximum"]
                    self.current_workout["hr_min"] = stat["minimum"]
                    break
            else:
                self.current_workout["hr_avg"] = None
                self.current_workout["hr_max"] = None
                self.current_workout["hr_min"] = None

            idx = len(self.workouts)
            self.workouts.append(self.current_workout)
            self.workout_stats_map[idx] = self.current_workout_stats
            self.workout_events_map[idx] = self.current_workout_events

            self.workout_count += 1
            if self.workout_count % 500 == 0:
                print(f"  ... processed {self.workout_count:,} workouts")

        self.in_workout = False
        self.current_workout = None
        self.current_workout_stats = []
        self.current_workout_events = []
        self.current_workout_metadata = {}

    def _handle_activity_summary(self, attrs):
        date = attrs.get("dateComponents", "")
        if not date or date < MIN_DATE or date > EXPORT_DATE:
            return
        self.activity_summaries.append({
            "date": date,
            "active_energy_kcal": float(attrs.get("activeEnergyBurned", 0)),
            "active_energy_goal": float(attrs.get("activeEnergyBurnedGoal", 0)),
            "move_time_min": float(attrs.get("appleMoveTime", 0)),
            "move_time_goal": float(attrs.get("appleMoveTimeGoal", 0)),
            "exercise_min": float(attrs.get("appleExerciseTime", 0)),
            "exercise_goal": float(attrs.get("appleExerciseTimeGoal", 0)),
            "stand_hours": int(float(attrs.get("appleStandHours", 0))),
            "stand_hours_goal": int(float(attrs.get("appleStandHoursGoal", 0))),
        })


def aggregate_daily_health(handler):
    """Aggregate raw daily records into one row per day."""
    rows = []
    for date in sorted(handler.daily_records.keys()):
        day_data = handler.daily_records[date]
        row = {"date": date}
        for field_name in handler.daily_agg_types.values():
            values = day_data.get(field_name, [])
            if not values:
                row[field_name] = None
            elif field_name in handler.sum_types:
                row[field_name] = sum(values)
            else:
                row[field_name] = sum(values) / len(values)  # average
        rows.append(row)
    return rows


def aggregate_sleep(handler):
    """Aggregate sleep records into daily totals by stage."""
    from collections import defaultdict

    daily_sleep = defaultdict(lambda: {"total": 0, "deep": 0, "rem": 0, "core": 0})

    for rec in handler.sleep_records:
        if not rec["start"] or not rec["end"]:
            continue
        val = rec["value"] or ""
        try:
            start = datetime.strptime(rec["start"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(rec["end"], "%Y-%m-%d %H:%M:%S")
            duration_hr = (end - start).total_seconds() / 3600
        except:
            continue

        if duration_hr <= 0 or duration_hr > 24:
            continue

        # Assign sleep to the date it ended (morning of)
        sleep_date = end.strftime("%Y-%m-%d")

        if "AsleepDeep" in val:
            daily_sleep[sleep_date]["deep"] += duration_hr
            daily_sleep[sleep_date]["total"] += duration_hr
        elif "AsleepREM" in val:
            daily_sleep[sleep_date]["rem"] += duration_hr
            daily_sleep[sleep_date]["total"] += duration_hr
        elif "AsleepCore" in val or "Asleep" in val:
            daily_sleep[sleep_date]["core"] += duration_hr
            daily_sleep[sleep_date]["total"] += duration_hr
        elif "InBed" in val:
            # InBed includes all sleep stages, don't double count
            # Only use if we don't have stage breakdown
            pass

    return daily_sleep


def aggregate_body_composition(handler):
    """Group body comp records by date into single rows."""
    from collections import defaultdict

    by_date = defaultdict(dict)
    for rec in handler.body_comp:
        date = rec["date"]
        t = rec["type"]
        v = rec["value"]
        s = rec["source"]

        if t == "BodyMass":
            by_date[date]["weight_kg"] = v
        elif t == "BodyMassIndex":
            by_date[date]["bmi"] = v
        elif t == "BodyFatPercentage":
            by_date[date]["body_fat_pct"] = v * 100 if v < 1 else v  # Handle 0.xx vs xx format
        elif t == "LeanBodyMass":
            by_date[date]["lean_mass_kg"] = v

        by_date[date]["source"] = s

    rows = []
    for date in sorted(by_date.keys()):
        row = {"date": date, **by_date[date]}
        rows.append(row)
    return rows


def create_database(db_path):
    """Create SQLite database with schema."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.executescript("""
        DROP TABLE IF EXISTS workouts;
        DROP TABLE IF EXISTS workout_running_stats;
        DROP TABLE IF EXISTS workout_events;
        DROP TABLE IF EXISTS daily_health;
        DROP TABLE IF EXISTS body_composition;
        DROP TABLE IF EXISTS activity_summary;
        DROP TABLE IF EXISTS vo2max;
        DROP VIEW IF EXISTS weekly_summary;

        CREATE TABLE workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_type TEXT,
            start_date DATETIME,
            end_date DATETIME,
            duration_min REAL,
            distance_km REAL,
            energy_kcal REAL,
            hr_avg REAL,
            hr_max REAL,
            hr_min REAL,
            source TEXT,
            is_indoor INTEGER,
            weather_temp REAL,
            weather_humidity REAL,
            elevation_ascended REAL,
            elevation_descended REAL,
            avg_mets REAL
        );

        CREATE TABLE workout_running_stats (
            workout_id INTEGER REFERENCES workouts(id),
            avg_speed_kmh REAL,
            max_speed_kmh REAL,
            avg_power_w REAL,
            max_power_w REAL,
            avg_stride_m REAL,
            avg_ground_contact_ms REAL,
            avg_vertical_osc_cm REAL,
            step_count INTEGER,
            distance_km REAL
        );

        CREATE TABLE workout_events (
            workout_id INTEGER REFERENCES workouts(id),
            event_type TEXT,
            event_date DATETIME,
            duration REAL
        );

        CREATE TABLE daily_health (
            date DATE PRIMARY KEY,
            resting_hr REAL,
            hrv_sdnn_ms REAL,
            vo2max REAL,
            spo2_pct REAL,
            respiratory_rate REAL,
            walking_hr_avg REAL,
            steps INTEGER,
            distance_km REAL,
            flights_climbed INTEGER,
            active_energy_kcal REAL,
            basal_energy_kcal REAL,
            exercise_min REAL,
            stand_hours INTEGER,
            sleep_duration_hr REAL,
            sleep_deep_hr REAL,
            sleep_rem_hr REAL,
            sleep_core_hr REAL,
            wrist_temp_c REAL,
            time_in_daylight_min REAL
        );

        CREATE TABLE body_composition (
            date DATE,
            weight_kg REAL,
            bmi REAL,
            body_fat_pct REAL,
            lean_mass_kg REAL,
            source TEXT
        );

        CREATE TABLE activity_summary (
            date DATE PRIMARY KEY,
            active_energy_kcal REAL,
            active_energy_goal REAL,
            move_time_min REAL,
            move_time_goal REAL,
            exercise_min REAL,
            exercise_goal REAL,
            stand_hours INTEGER,
            stand_hours_goal INTEGER
        );

        CREATE TABLE vo2max (
            date DATE,
            value REAL,
            source TEXT
        );

        CREATE TABLE etl_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    conn.commit()
    return conn


def insert_workouts(conn, handler):
    """Insert workouts and their related stats/events."""
    c = conn.cursor()

    for idx, w in enumerate(handler.workouts):
        c.execute("""
            INSERT INTO workouts (activity_type, start_date, end_date, duration_min,
                distance_km, energy_kcal, hr_avg, hr_max, hr_min, source,
                is_indoor, weather_temp, weather_humidity, elevation_ascended,
                elevation_descended, avg_mets)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            w["activity_type"], w["start_date"], w["end_date"], w["duration_min"],
            w["distance_km"], w["energy_kcal"], w["hr_avg"], w["hr_max"], w["hr_min"],
            w["source"], w["is_indoor"], w["weather_temp"], w["weather_humidity"],
            w["elevation_ascended"], w["elevation_descended"], w["avg_mets"]
        ))
        workout_id = c.lastrowid

        # Running stats
        stats = handler.workout_stats_map.get(idx, [])
        if w["activity_type"] in ("Running", "Walking"):
            running_row = {}
            for stat in stats:
                t = stat["type"]
                if t == "RunningSpeed":
                    running_row["avg_speed_kmh"] = stat["average"]
                    running_row["max_speed_kmh"] = stat["maximum"]
                elif t == "RunningPower":
                    running_row["avg_power_w"] = stat["average"]
                    running_row["max_power_w"] = stat["maximum"]
                elif t == "RunningStrideLength":
                    running_row["avg_stride_m"] = stat["average"]
                elif t == "RunningGroundContactTime":
                    running_row["avg_ground_contact_ms"] = stat["average"]
                elif t == "RunningVerticalOscillation":
                    running_row["avg_vertical_osc_cm"] = stat["average"]
                elif t == "StepCount":
                    running_row["step_count"] = int(stat["sum"]) if stat["sum"] else None
                elif t == "DistanceWalkingRunning":
                    running_row["distance_km"] = stat["sum"]

            if running_row:
                c.execute("""
                    INSERT INTO workout_running_stats (workout_id, avg_speed_kmh,
                        max_speed_kmh, avg_power_w, max_power_w, avg_stride_m,
                        avg_ground_contact_ms, avg_vertical_osc_cm, step_count, distance_km)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    workout_id,
                    running_row.get("avg_speed_kmh"),
                    running_row.get("max_speed_kmh"),
                    running_row.get("avg_power_w"),
                    running_row.get("max_power_w"),
                    running_row.get("avg_stride_m"),
                    running_row.get("avg_ground_contact_ms"),
                    running_row.get("avg_vertical_osc_cm"),
                    running_row.get("step_count"),
                    running_row.get("distance_km"),
                ))

        # Workout events
        events = handler.workout_events_map.get(idx, [])
        for evt in events:
            c.execute("""
                INSERT INTO workout_events (workout_id, event_type, event_date, duration)
                VALUES (?,?,?,?)
            """, (workout_id, evt["type"], evt["date"], evt["duration"]))

    conn.commit()
    print(f"  Inserted {len(handler.workouts):,} workouts")


def insert_daily_health(conn, handler):
    """Insert aggregated daily health metrics."""
    c = conn.cursor()

    daily_rows = aggregate_daily_health(handler)
    sleep_data = aggregate_sleep(handler)

    # Merge VO2Max into daily
    vo2_by_date = {}
    for rec in handler.vo2max_records:
        d = rec["date"]
        if d not in vo2_by_date:
            vo2_by_date[d] = rec["value"]

    for row in daily_rows:
        date = row["date"]
        sleep = sleep_data.get(date, {})
        vo2 = vo2_by_date.get(date)

        c.execute("""
            INSERT OR REPLACE INTO daily_health
            (date, resting_hr, hrv_sdnn_ms, vo2max, spo2_pct, respiratory_rate,
             walking_hr_avg, steps, distance_km, flights_climbed, active_energy_kcal,
             basal_energy_kcal, exercise_min, stand_hours, sleep_duration_hr,
             sleep_deep_hr, sleep_rem_hr, sleep_core_hr, wrist_temp_c, time_in_daylight_min)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            date,
            row.get("resting_hr"),
            row.get("hrv_sdnn_ms"),
            vo2,
            row.get("spo2_pct"),
            row.get("respiratory_rate"),
            row.get("walking_hr_avg"),
            int(row["steps"]) if row.get("steps") else None,
            round(row["distance_km"], 3) if row.get("distance_km") else None,
            int(row["flights_climbed"]) if row.get("flights_climbed") else None,
            round(row["active_energy_kcal"], 1) if row.get("active_energy_kcal") else None,
            round(row["basal_energy_kcal"], 1) if row.get("basal_energy_kcal") else None,
            round(row["exercise_min"], 1) if row.get("exercise_min") else None,
            int(row["stand_hours"]) if row.get("stand_hours") else None,
            round(sleep.get("total", 0), 2) if sleep.get("total") else None,
            round(sleep.get("deep", 0), 2) if sleep.get("deep") else None,
            round(sleep.get("rem", 0), 2) if sleep.get("rem") else None,
            round(sleep.get("core", 0), 2) if sleep.get("core") else None,
            row.get("wrist_temp_c"),
            round(row["time_in_daylight_min"], 1) if row.get("time_in_daylight_min") else None,
        ))

    conn.commit()
    print(f"  Inserted {len(daily_rows):,} daily health rows")


def insert_body_composition(conn, handler):
    """Insert body composition data."""
    c = conn.cursor()
    rows = aggregate_body_composition(handler)

    for row in rows:
        c.execute("""
            INSERT INTO body_composition (date, weight_kg, bmi, body_fat_pct, lean_mass_kg, source)
            VALUES (?,?,?,?,?,?)
        """, (
            row["date"],
            row.get("weight_kg"),
            row.get("bmi"),
            row.get("body_fat_pct"),
            row.get("lean_mass_kg"),
            row.get("source"),
        ))

    conn.commit()
    print(f"  Inserted {len(rows):,} body composition rows")


def insert_activity_summaries(conn, handler):
    """Insert activity summaries."""
    c = conn.cursor()

    for row in handler.activity_summaries:
        c.execute("""
            INSERT OR REPLACE INTO activity_summary
            (date, active_energy_kcal, active_energy_goal, move_time_min, move_time_goal,
             exercise_min, exercise_goal, stand_hours, stand_hours_goal)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            row["date"], row["active_energy_kcal"], row["active_energy_goal"],
            row["move_time_min"], row["move_time_goal"],
            row["exercise_min"], row["exercise_goal"],
            row["stand_hours"], row["stand_hours_goal"],
        ))

    conn.commit()
    print(f"  Inserted {len(handler.activity_summaries):,} activity summaries")


def insert_vo2max(conn, handler):
    """Insert individual VO2Max records."""
    c = conn.cursor()
    for rec in handler.vo2max_records:
        c.execute("INSERT INTO vo2max (date, value, source) VALUES (?,?,?)",
                  (rec["date"], rec["value"], rec["source"]))
    conn.commit()
    print(f"  Inserted {len(handler.vo2max_records):,} VO2Max records")


def create_views(conn):
    """Create weekly summary view."""
    c = conn.cursor()
    c.executescript("""
        CREATE VIEW IF NOT EXISTS weekly_summary AS
        SELECT
            strftime('%Y-W%W', start_date) as week,
            MIN(date(start_date)) as week_start,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN activity_type = 'Running' THEN 1 ELSE 0 END) as running_sessions,
            SUM(CASE WHEN activity_type IN ('TraditionalStrengthTraining','FunctionalStrengthTraining','CoreTraining') THEN 1 ELSE 0 END) as strength_sessions,
            SUM(CASE WHEN activity_type = 'Yoga' THEN 1 ELSE 0 END) as yoga_sessions,
            SUM(CASE WHEN activity_type = 'HighIntensityIntervalTraining' THEN 1 ELSE 0 END) as hiit_sessions,
            ROUND(SUM(duration_min), 1) as total_min,
            ROUND(SUM(CASE WHEN activity_type = 'Running' THEN distance_km ELSE 0 END), 2) as running_km,
            ROUND(SUM(CASE WHEN activity_type = 'Cycling' THEN distance_km ELSE 0 END), 2) as cycling_km,
            ROUND(SUM(energy_kcal), 0) as total_kcal,
            ROUND(SUM(COALESCE(elevation_ascended, 0)), 0) as total_elevation_m,
            ROUND(AVG(hr_avg), 1) as avg_hr
        FROM workouts
        GROUP BY week
        ORDER BY week;
    """)
    conn.commit()
    print("  Created weekly_summary view")


def main():
    xml_path = sys.argv[1] if len(sys.argv) > 1 else "/sessions/zealous-beautiful-galileo/mnt/Apple Health/apple_health_export/exportar.xml"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "/sessions/zealous-beautiful-galileo/health.db"

    print(f"=== Apple Health ETL ===")
    print(f"Input:  {xml_path}")
    print(f"Output: {db_path}")
    print(f"XML size: {os.path.getsize(xml_path) / 1e9:.2f} GB")
    print()

    # Parse XML
    print("Phase 1: Parsing XML with SAX...")
    handler = HealthDataHandler()
    parser = xml.sax.make_parser()
    parser.setContentHandler(handler)

    start_time = datetime.now()
    parser.parse(xml_path)
    parse_time = (datetime.now() - start_time).total_seconds()

    print(f"\n  Parse complete in {parse_time:.0f}s")
    print(f"  Records processed: {handler.record_count:,}")
    print(f"  Workouts found: {handler.workout_count:,}")
    print(f"  Days with health data: {len(handler.daily_records):,}")
    print(f"  Body comp records: {len(handler.body_comp):,}")
    print(f"  Activity summaries: {len(handler.activity_summaries):,}")
    print(f"  VO2Max records: {len(handler.vo2max_records):,}")
    print(f"  Sleep records: {len(handler.sleep_records):,}")
    print()

    # Create database
    print("Phase 2: Creating SQLite database...")
    conn = create_database(db_path)

    # Insert data
    print("Phase 3: Inserting data...")
    insert_workouts(conn, handler)
    insert_daily_health(conn, handler)
    insert_body_composition(conn, handler)
    insert_activity_summaries(conn, handler)
    insert_vo2max(conn, handler)
    create_views(conn)

    # Store metadata
    c = conn.cursor()
    c.execute("INSERT INTO etl_metadata VALUES (?, ?)", ("last_etl_run", datetime.now().isoformat()))
    c.execute("INSERT INTO etl_metadata VALUES (?, ?)", ("export_date", EXPORT_DATE))
    c.execute("INSERT INTO etl_metadata VALUES (?, ?)", ("xml_path", xml_path))
    conn.commit()

    # Summary
    print("\n=== ETL Complete ===")
    db_size = os.path.getsize(db_path) / 1e6
    print(f"Database size: {db_size:.1f} MB")

    # Quick sanity checks
    print("\nSanity checks:")
    for table in ["workouts", "daily_health", "body_composition", "activity_summary", "vo2max"]:
        count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")

    conn.close()
    total_time = (datetime.now() - start_time).total_seconds()
    print(f"\nTotal time: {total_time:.0f}s")


if __name__ == "__main__":
    main()
