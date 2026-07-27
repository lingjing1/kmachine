import os
import json
import csv
import random
import argparse
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

def export_blind_samples(run_id, output_dir):
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    engine = create_engine(db_url)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT id, ablation_group, content_type, content, title
            FROM exp_generated_contents
            WHERE run_id = :run_id
        """), {"run_id": run_id})
        
        records = [dict(mapping) for mapping in res.mappings()]
        
    if not records:
        print(f"No records found for run_id: {run_id}")
        return
        
    print(f"Found {len(records)} records for run_id {run_id}.")
    
    # Shuffle records to randomize Sample_01, Sample_02, Sample_03
    random.shuffle(records)
    
    mapping_data = []
    
    for idx, record in enumerate(records, 1):
        sample_id = f"Sample_{idx:02d}"
        
        # Determine how to format content
        content_obj = record['content']
        markdown_text = f"# {sample_id}\n\n"
        
        if record['content_type'] == 'exam':
            # Extract questions
            if isinstance(content_obj, list):
                for block in content_obj:
                    q_type = block.get('type', 'unknown')
                    markdown_text += f"## {q_type}\n\n"
                    for q in block.get('questions', []):
                        markdown_text += f"**Q: {q.get('question_text', '')}**\n"
                        if 'options' in q:
                            for opt, text_val in q['options'].items():
                                markdown_text += f"- {opt}: {text_val}\n"
                        markdown_text += f"*Answer: {q.get('answer', '')}*\n\n"
        else:
            # Material
            if isinstance(content_obj, dict) and 'text' in content_obj:
                markdown_text += content_obj['text']
            elif isinstance(content_obj, str):
                markdown_text += content_obj
            else:
                markdown_text += json.dumps(content_obj, ensure_ascii=False, indent=2)
                
        # Save markdown
        md_path = os.path.join(output_dir, f"{sample_id}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_text)
            
        print(f"Exported {md_path}")
        
        mapping_data.append({
            "Sample_ID": sample_id,
            "Run_ID": run_id,
            "Ablation_Group": record['ablation_group'],
            "Original_DB_ID": record['id'],
            "Title": record['title']
        })
        
    # Save mapping CSV
    csv_path = os.path.join(output_dir, f"mapping_{run_id}.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Sample_ID", "Run_ID", "Ablation_Group", "Original_DB_ID", "Title"])
        writer.writeheader()
        writer.writerows(mapping_data)
        
    print(f"Exported mapping CSV: {csv_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Blind Samples for RQ1 Evaluation")
    parser.add_argument("--run_id", type=str, required=True, help="The run_id of the batch generation")
    parser.add_argument("--output_dir", type=str, default="./exports", help="Output directory for markdown and mapping files")
    
    args = parser.parse_args()
    export_blind_samples(args.run_id, args.output_dir)
