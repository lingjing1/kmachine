from . import Document, Page, DocumentLoader
from pptx import Presentation
from .image_utils import image_to_base64_uri
from pptx.enum.shapes import MSO_SHAPE_TYPE
from .vision_utils import process_image_with_vision

class PptxLoader(DocumentLoader):
    """A loader for Microsoft PowerPoint (.pptx) files."""

    def load(self, source: str) -> Document:
        """
        Reads text and extracts images from a .pptx file on a slide-by-slide basis.
        
        Returns Document with structured_elements format using Vision LLM.
        """
        try:
            prs = Presentation(source)
            doc_pages = []

            for i, slide in enumerate(prs.slides):
                structured_elements = []

                for shape in slide.shapes:
                    # [NEW] 獲取元件位置資訊用於排序
                    # 某些元件可能沒有 top/left 屬性 (如 GroupShapes 的子元件)
                    shape_top = getattr(shape, 'top', 9999999)
                    shape_left = getattr(shape, 'left', 9999999)

                    # Recursive function to extract text from any shape
                    def extract_text(s):
                        text_content = []
                        if hasattr(s, "text") and s.text and s.text.strip():
                            text_content.append(s.text.strip())
                        
                        if s.has_table:
                            for row in s.table.rows:
                                row_text = []
                                for cell in row.cells:
                                    if cell.text_frame and cell.text:
                                        row_text.append(cell.text.strip())
                                if row_text:
                                    text_content.append(" | ".join(row_text))
                        
                        if s.shape_type == MSO_SHAPE_TYPE.GROUP:
                            for child in s.shapes:
                                child_text = extract_text(child)
                                if child_text:
                                    text_content.append(child_text)
                        
                        return "\n".join(text_content)

                    # Extract text
                    extracted_text = extract_text(shape)
                    if extracted_text:
                        structured_elements.append({
                            "type": "text",
                            "content": extracted_text,
                            "top": shape_top,
                            "left": shape_left
                        })
                    
                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        try:
                            # 濾除過小的圖片
                            if shape.width < 720000 or shape.height < 720000:
                                continue

                            image_bytes = shape.image.blob
                            base64_image_uri = image_to_base64_uri(image_bytes)
                            
                            if base64_image_uri:
                                vision_result = process_image_with_vision(image_bytes)
                                
                                structured_elements.append({
                                    "type": "image",
                                    "base64": base64_image_uri,
                                    "vision_description": vision_result["description"],
                                    "vision_tokens": vision_result["total_tokens"],
                                    "vision_cost": vision_result["cost"],
                                    "top": shape_top,
                                    "left": shape_left
                                })
                        except Exception as e:
                            print(f"Warning: Could not process an image on slide {i+1}: {e}")

                # [NEW] 根據垂直位置 (top) 排序，次要根據水平位置 (left)
                # 這可以確保標題在最上面，內文居中，頁碼在最下面
                sorted_elements = sorted(
                    structured_elements, 
                    key=lambda x: (x.get("top", 0), x.get("left", 0))
                )
                
                # 移除排序用的座標欄位
                final_elements = [
                    {k: v for k, v in el.items() if k not in ["top", "left"]}
                    for el in sorted_elements
                ]

                doc_pages.append(Page(
                    page_number=i + 1,
                    structured_elements=final_elements
                ))
            
            print(f"✅ Successfully loaded {len(doc_pages)} slides from PPTX")
            return Document(source=source, pages=doc_pages)
            
        except Exception as e:
            print(f"Error reading PPTX file: {str(e)}")
            raise e
