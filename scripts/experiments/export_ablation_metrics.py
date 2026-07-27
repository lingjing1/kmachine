import os
import sys
import argparse
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def export_metrics(output_file="ablation_metrics.csv"):
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    engine = create_engine(db_url)
    
    # Query generated_contents and generator_setting_logs to get RQ2 metrics
    query = """
    SELECT 
        gc.id as content_id,
        gc.job_id,
        gc.ablation_group,
        gc.action_type,
        gc.edit_duration_seconds,
        gc.edit_ratio,
        gc.levenshtein_distance,
        jsonb_array_length(gc.source_preview_logs) as source_preview_count,
        gc.created_at,
        gsl.duration_sec as generation_duration,
        gsl.action_config->'final_settings'->'params'->>'materialType' as material_type
    FROM generated_contents gc
    LEFT JOIN generator_setting_logs gsl ON gc.job_id = gsl.job_id
    WHERE gc.ablation_group IS NOT NULL
    ORDER BY gc.created_at DESC;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
        
    if df.empty:
        print("No ablation experiment data found in generated_contents.")
        return
        
    print(f"Found {len(df)} records with ablation groups.")
    
    # Calculate some summary stats
    summary = df.groupby('ablation_group').agg({
        'edit_ratio': ['mean', 'median', 'count'],
        'edit_duration_seconds': ['mean', 'median'],
        'levenshtein_distance': ['mean'],
        'source_preview_count': ['mean']
    }).round(4)
    
    print("\n--- Summary Statistics (RQ2) ---")
    print(summary)
    print("\n---------------------------------")
    
    # Save to CSV
    df.to_csv(output_file, index=False)
    print(f"Exported raw metrics to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Ablation Metrics for RQ2")
    parser.add_argument("--output", type=str, default="ablation_metrics.csv", help="Output CSV file path")
    args = parser.parse_args()
    
    export_metrics(args.output)
