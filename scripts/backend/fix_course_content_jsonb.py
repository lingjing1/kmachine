
import sys
import os
import json
from sqlalchemy import text
from backend.app.utils.db_logger import engine

# Add project root to path
sys.path.insert(0, os.getcwd())

def fix_content_format():
    print("=== Fixing Course Contents JSONB Format ===")
    
    with engine.connect() as conn:
        try:
            # 1. Disable trigger first (autocommit/immediate)
            print("Disabling trigger 'trg_sync_question_bank_usage'...")
            conn.execute(text("ALTER TABLE course_contents DISABLE TRIGGER trg_sync_question_bank_usage"))
            conn.commit()

            # 2. Perform updates
            trans = conn.begin()
            try:
                # Select rows to fix - INCLUDE title
                query = """
                    SELECT id, title, content 
                    FROM course_contents 
                    WHERE content_type='material' 
                      AND source_type='text'
                """
                rows = conn.execute(text(query)).fetchall()
                
                updated_count = 0
                
                for row in rows:
                    content_val = row.content
                    
                    # Check if it needs fixing
                    # If it's a string, it means it's a JSON string in DB decoded as python string
                    # We want it to be a JSON object (python dict)
                    
                    if isinstance(content_val, str):
                        # It's a string, we need to parse it into the target structure
                        print(f"ID {row.id}: Parsing string content...")
                        
                        try:
                            # Simple Markdown Parser
                            lines = content_val.split('\n')
                            sections = []
                            current_section = None
                            
                            # Default first section if no header immediately found (or for content before first header)
                            # But typically our content has headers. Let's see.
                            
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                    
                                if line.startswith('## '):
                                    # Save previous section if exists
                                    if current_section:
                                        sections.append(current_section)
                                    
                                    # Start new section
                                    title_text = line[3:].strip() # Remove '## '
                                    current_section = {
                                        "section_title": title_text,
                                        "content_list": []
                                    }
                                elif line.startswith('- ') or line.startswith('* '):
                                    item_text = line[2:].strip()
                                    if current_section:
                                        current_section['content_list'].append(item_text)
                                    else:
                                        # Content before any header? Maybe put in a "General" section or similar
                                        # Or just create a default one
                                        current_section = {
                                            # Use title from row if available, or generic
                                            "section_title": "重點整理", 
                                            "content_list": [item_text]
                                        }
                                else:
                                    # Regular text line or other markdown. 
                                    # For now, if we are inside a section, maybe just append it?
                                    # Or if it's bold text etc. Let's treat non-list items as list items for simplicity 
                                    # if they look like paragraphs.
                                    if current_section:
                                        # Check if it's not a header marker
                                        if not line.startswith('#'): 
                                            current_section['content_list'].append(line)

                            # Append the last section
                            if current_section:
                                sections.append(current_section)
                                
                            if not sections:
                                # If parsing failed to find structure (e.g. short text), just wrap it
                                print(f"  > Warning: No structure found for ID {row.id}, falling back to single section.")
                                new_content = {
                                    "type": "summary_report",
                                    "title": row.title or "教材內容",
                                    "job_id": row.id + 1000, # Mock job_id based on row id
                                    "content": [{
                                        "section_title": "重點摘要",
                                        "content_list": [content_val]
                                    }],
                                    "display_type": "summary_report"
                                }
                            else:
                                new_content = {
                                    "type": "summary_report", # Standard type
                                    "title": row.title or "教材內容",
                                    "job_id": row.id + 1000, # Mock job_id based on row id
                                    "content": sections,
                                    "display_type": "summary_report"
                                }
                                
                        except Exception as parse_err:
                            print(f"  > Error parsing ID {row.id}: {parse_err}. Fallback to simple wrap.")
                            new_content = {"text": content_val}

                    elif content_val is None:
                         print(f"ID {row.id}: Content is None, skipping.")
                         continue
                    elif isinstance(content_val, dict):
                        if "text" not in content_val and "type" not in content_val:
                             # It is a dict but structure might be wrong? 
                             # But for now assume dict is 'suitable'. User implies current state (string) is bad.
                             print(f"ID {row.id}: Already a dict but structure unclear? {content_val.keys()}. Skipping.")
                             continue
                        else:
                            print(f"ID {row.id}: Already in correct format. Skipping.")
                            continue
                    else:
                        print(f"ID {row.id}: Unknown type {type(content_val)}. Skipping.")
                        continue
                    
                    if new_content:
                        # Update
                        # We utilize json.dumps for the parameter, although SQLAlchemy might handle dict automatically for JSONB 
                        # but safer to pass dict if using sqlalchemy with JSONB support, OR string if raw SQL
                        # Using text() with parameters usually handles auto-conversion if driver supports it.
                        # Since we are using execute with parameters, passing dict usually works for JSONB columns in psycopg2.
                        
                        update_stmt = text("UPDATE course_contents SET content = :content WHERE id = :id")
                        conn.execute(update_stmt, {"content": json.dumps(new_content), "id": row.id})
                        updated_count += 1

                print(f"Updated {updated_count} rows.")
                trans.commit()
                print("Update Transaction Committed.")
                
            except Exception as e:
                trans.rollback()
                print(f"Error during update: {e}")
                # Don't re-raise immediately, ensure we enable trigger first
            
        finally:
            # 3. Always Re-enable trigger
            print("Re-enabling trigger 'trg_sync_question_bank_usage'...")
            conn.execute(text("ALTER TABLE course_contents ENABLE TRIGGER trg_sync_question_bank_usage"))
            conn.commit()
            print("=== Fix Complete ===")

if __name__ == "__main__":
    fix_content_format()
