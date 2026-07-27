import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

class ExperimentDataExporter:
    def __init__(self, db_url=None):
        if not db_url:
            load_dotenv()
            db_url = os.getenv("DATABASE_URL")
        
        self.engine = create_engine(db_url)
        print(f"Connected to database at {db_url.split('@')[-1]}")

    def get_teacher_report(self, days=7):
        """
        RQ1 & RQ2: Teacher quality and trust indicators.
        """
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # 1. Generation Settings (Preparation behaviors)
        prep_query = f"""
        SELECT 
            user_id, session_id, job_id, duration_sec, created_at,
            action_config->'final_settings'->'params'->>'materialType' as material_type,
            jsonb_array_length(action_config->'actions') as action_count
        FROM generator_setting_logs
        WHERE created_at >= '{since_date}'
        """
        
        # 2. Generated Contents (Accuracy & Edit behaviors)
        content_query = f"""
        SELECT 
            author_id, action_type, edit_duration_seconds, edit_ratio, 
            levenshtein_distance, created_at,
            jsonb_array_length(source_preview_logs) as source_preview_count
        FROM generated_contents
        WHERE created_at >= '{since_date}'
        """
        
        with self.engine.connect() as conn:
            df_prep = pd.read_sql(text(prep_query), conn)
            df_content = pd.read_sql(text(content_query), conn)
            
        return {"prep": df_prep, "content": df_content}

    def get_student_report(self, days=7):
        """
        RQ3 & RQ4: Student learning paths and engagement.
        """
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # 1. Reading Logs (Engagement)
        reading_query = f"""
        SELECT 
            user_id, unit_session_id, content_id, stay_duration_seconds, 
            max_scroll_depth, exit_action, created_at
        FROM material_reading_logs
        WHERE created_at >= '{since_date}'
        """
        
        # 2. Question Logs (Learning Outcome)
        question_query = f"""
        SELECT 
            student_id as user_id, unit_session_id, question_id, stage, correctness, answered_at
        FROM student_question_logs
        WHERE answered_at >= '{since_date}'
        """
        
        # 3. Learning Sessions (Flow)
        session_query = f"""
        SELECT 
            id as session_id, user_id, unit_id, started_at, last_active_at, is_completed
        FROM student_learning_sessions
        WHERE started_at >= '{since_date}'
        """
        
        with self.engine.connect() as conn:
            df_reading = pd.read_sql(text(reading_query), conn)
            df_questions = pd.read_sql(text(question_query), conn)
            df_sessions = pd.read_sql(text(session_query), conn)
            
        return {
            "reading": df_reading, 
            "questions": df_questions, 
            "sessions": df_sessions
        }

    def quick_status_check(self, days=7):
        """Prints a summary of data collected in the last N days."""
        t_data = self.get_teacher_report(days)
        s_data = self.get_student_report(days)
        
        print(f"\n=== Experiment Data Summary (Last {days} days) ===")
        print(f"Teacher Prep Logs: {len(t_data['prep'])}")
        print(f"AI Contents Generated: {len(t_data['content'])}")
        print(f"Student Reading Logs: {len(s_data['reading'])}")
        print(f"Student Questions Answered: {len(s_data['questions'])}")
        print(f"Active Learning Sessions: {len(s_data['sessions'])}")
        
        if len(t_data['content']) > 0:
            avg_edit = t_data['content']['edit_ratio'].mean()
            print(f"Teacher Avg Edit Ratio: {avg_edit:.2f}")

    def plot_student_engagement(self, days=30):
        """Example plotting function: Reading time vs Correctness."""
        data = self.get_student_report(days)
        df_reading = data['reading']
        df_questions = data['questions']
        
        if df_reading.empty or df_questions.empty:
            print("Not enough data to plot.")
            return

        # Simple aggregation by session
        reading_agg = df_reading.groupby('unit_session_id')['stay_duration_seconds'].sum()
        score_agg = df_questions.groupby('unit_session_id')['correctness'].mean()
        
        plot_df = pd.concat([reading_agg, score_agg], axis=1).dropna()
        
        if plot_df.empty:
            print("No overlapping sessions for plotting.")
            return

        plt.figure(figsize=(10, 6))
        plt.scatter(plot_df['stay_duration_seconds'], plot_df['correctness'], alpha=0.5)
        plt.title('Reading Time vs. Question Correctness')
        plt.xlabel('Total Reading Duration (sec)')
        plt.ylabel('Avg Correctness (%)')
        plt.grid(True)
        
        output_path = "/home/monica/Cook.ai/engagement_plot.png"
        plt.savefig(output_path)
        print(f"Plot saved to {output_path}")

if __name__ == "__main__":
    exporter = ExperimentDataExporter()
    exporter.quick_status_check(days=30) # Check last 30 days for testing
    # exporter.plot_student_engagement()
