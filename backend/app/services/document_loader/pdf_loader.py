
import pdfplumber
import base64
import io
from PIL import Image
from . import Document, Page, DocumentLoader
from .vision_utils import process_image_with_vision
from .image_utils import image_to_base64_uri

class PdfLoader(DocumentLoader):
    """A loader for PDF files that extracts text and converts images to a web-safe format."""

    def load(self, source: str) -> Document:
        """Reads text and extracts/converts images from a PDF on a page-by-page basis."""

        doc_pages = []

        try:
            with pdfplumber.open(source) as pdf:
                for page_num, page in enumerate(pdf.pages):

                    # 處理文字
                    text_elements = []  # Added back
                    raw_lines = []
                    extracted_lines = page.extract_text_lines(keep_blank_chars=True)
                    if extracted_lines:
                        # 1. 找出頁面最左邊的文字作為基準 (Base Indentation)
                        # 過濾掉空行，確保基準準確
                        valid_x0s = [line['x0'] for line in extracted_lines if line['text'].strip()]
                        min_x0 = min(valid_x0s) if valid_x0s else 0
                        
                        for line in extracted_lines:
                            text = line['text']
                            if not text.strip():
                                raw_lines.append("")
                                continue
                                
                            # 2. 計算縮排
                            # 假設每個縮排層級約為 4-5 pt (通常字體寬度的一半到全部)
                            # 使用 6.0 作為除數比較保守，避免過度縮排，但足以觸發 2-space detection
                            indent_pixels = max(0, line['x0'] - min_x0)
                            num_spaces = int(indent_pixels / 4.0) 
                            
                            # 3. 加上前導空白
                            raw_lines.append(" " * num_spaces + text)
                    else:
                        raw_lines = []
                    
                    # ✅ 智能合併文字行，處理換行斷句問題
                    from .text_utils import smart_merge_lines
                    merged_text = smart_merge_lines(raw_lines)
                    
                    # 將合併後的段落分割成元素
                    for paragraph in merged_text.split('\n'):
                        if paragraph.strip():  # 跳過空行
                            text_elements.append({
                                "type": "text",
                                "content": paragraph,
                                "top": 0  # 合併後無法保留精確位置
                            })
                    
                    # 處理圖片
                    image_elements = []
                    for img in page.images:
                        # [NEW] 濾除過小的圖片（可能是商標、圖標或裝飾線條）
                        # 長寬均小於 80 點 (約 1 吋) 的圖片通常不是教學內容
                        width = img.get("width", 0)
                        height = img.get("height", 0)
                        if width < 80 or height < 80:
                            continue

                        image_data = img.get("stream").get_data() 
                        
                        if not image_data:
                            continue

                        base64_string = image_to_base64_uri(image_data)
                        vision_result = process_image_with_vision(image_data)

                        image_elements.append({
                            "type": "image",
                            "base64": base64_string,
                            "vision_description": vision_result["description"],
                            "vision_tokens": vision_result["total_tokens"],
                            "vision_cost": vision_result["cost"],
                            "top": img["top"]
                        })

                    # 依垂直位置排序並移除 top 欄位（一步完成）
                    structured_elements_for_this_page = [
                        {k: v for k, v in el.items() if k != "top"}
                        for el in sorted(text_elements + image_elements, key=lambda x: x["top"])
                    ]

                    # 建立新的 Page 物件
                    new_page_object = Page(
                        page_number=page_num + 1,
                        structured_elements=structured_elements_for_this_page
                    )
                    doc_pages.append(new_page_object)
                    
                print(f"Successfully read {len(doc_pages)} pages from {source}")
                return Document(source=source, pages=doc_pages)

        except Exception as e:
            print(f"Error reading PDF with pdfplumber: {str(e)}")
            raise e
