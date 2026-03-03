#!/usr/bin/env python3
"""
Parse Strong app export (.xlsx or .csv) into a clean CSV for the health dashboard.
Normalizes column names, filters out rest timers, marks warmup sets.
"""

import pandas as pd
import sys
import os

def parse_strong(input_path, output_path):
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(input_path)
    else:
        df = pd.read_excel(input_path)

    # Normalize column names (Strong exports in Spanish)
    col_map = {
        "Fecha": "date",
        "Nombre de entrenamiento": "workout_name",
        "Duración": "duration",
        "Nombre del ejercicio": "exercise",
        "Orden de la serie": "set_order",
        "Peso": "weight_lb",
        "Rep.": "reps",
        "Distancia": "distance",
        "Segundos": "seconds",
        "Notas": "rpe_actual",  # Strong's "Notas" field has RPE when logged
        "Notas del entrenamiento": "workout_notes",
        "RPE": "rpe_column",
    }

    # Rename columns: exact match first, then fuzzy for encoding issues
    # Sort col_map by key length descending so "Notas del entrenamiento" matches before "Notas"
    sorted_map = sorted(col_map.items(), key=lambda x: len(x[0]), reverse=True)
    renamed = {}
    for orig_col in df.columns:
        # Try exact match first
        if orig_col in col_map:
            renamed[orig_col] = col_map[orig_col]
            continue
        # Fuzzy match for encoding issues (longest key first to avoid substring collisions)
        for es_name, en_name in sorted_map:
            if es_name.lower() in orig_col.lower():
                renamed[orig_col] = en_name
                break
    df = df.rename(columns=renamed)

    # Parse date
    df["date"] = pd.to_datetime(df["date"])
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")

    # Classify set type
    df["set_type"] = df["set_order"].apply(lambda x:
        "rest" if str(x).startswith("Temporizador") else
        "warmup" if str(x) == "P" else
        "working"
    )

    # Filter out rest timers
    df = df[df["set_type"] != "rest"].copy()

    # Convert set_order to numeric (warmup = 0)
    df["set_num"] = df["set_order"].apply(lambda x: 0 if str(x) == "P" else int(x) if str(x).isdigit() else 0)

    # Clean weight (0 = bodyweight)
    df["weight_lb"] = df["weight_lb"].fillna(0).astype(float)
    df["reps"] = df["reps"].fillna(0).astype(int)
    df["seconds"] = df["seconds"].fillna(0).astype(int)

    # RPE: check rpe_column first (from "RPE" header), then fall back to rpe_actual (from "Notas")
    if "rpe_column" in df.columns and df["rpe_column"].notna().any():
        df["rpe_actual"] = pd.to_numeric(df["rpe_column"], errors="coerce")
    elif "rpe_actual" in df.columns:
        df["rpe_actual"] = pd.to_numeric(df["rpe_actual"], errors="coerce")
    else:
        df["rpe_actual"] = pd.Series([None] * len(df), index=df.index)

    # Select and order output columns
    output = df[[
        "date_str", "workout_name", "exercise", "set_type", "set_num",
        "weight_lb", "reps", "seconds", "rpe_actual"
    ]].copy()
    output.columns = [
        "date", "workout_name", "exercise", "set_type", "set_num",
        "weight_lb", "reps", "seconds", "rpe_actual"
    ]

    output.to_csv(output_path, index=False)
    print(f"Parsed {len(output)} sets from {input_path}")
    print(f"  Working sets: {len(output[output['set_type'] == 'working'])}")
    print(f"  Warmup sets: {len(output[output['set_type'] == 'warmup'])}")
    print(f"  Dates: {output['date'].nunique()}")
    print(f"  Exercises: {output['exercise'].nunique()}")
    print(f"  Output: {output_path}")
    return output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_strong.py <input.xlsx|input.csv> [output.csv]")
        print("  input       - Strong app export file (.xlsx or .csv)")
        print("  output.csv  - Output path (default: data/strong_log.csv)")
        sys.exit(1)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir) if os.path.basename(script_dir) == "scripts" else script_dir
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(project_dir, "data", "strong_log.csv")
    parse_strong(input_path, output_path)
