from . import Document, Page, DocumentLoader
from langchain_community.document_loaders import WebBaseLoader
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin
from PIL import Image
import io
from .image_utils import image_to_base64_uri
from .vision_utils import process_image_with_vision

class WebLoader(DocumentLoader):
    """A loader for web pages using LangChain's WebBaseLoader and BeautifulSoup for images."""

    def load(self, source: str) -> Document:
        """Loads a web page, uses Vision LLM on images, and returns structured_elements format."""
        try:
            # Configure Retry Strategy
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            http = requests.Session()
            http.mount("https://", adapter)
            http.mount("http://", adapter)

            # Simplified Headers to reduce WAF triggering
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            # Add timeout to prevent hanging
            response = http.get(source, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Use 'html.parser' first as it's more robust for malformed HTML than lxml
            # Pass response.content (bytes) to let BeautifulSoup detect encoding
            try:
                soup = BeautifulSoup(response.content, 'html.parser')
            except Exception:
                soup = BeautifulSoup(response.content, 'lxml')
            
            # Extract Title
            # Extract Title Priority: og:title -> h1 -> title
            title = None
            
            # 1. Try OpenCheck og:title (usually cleaner)
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
                
            # 2. Try h1 (if og:title missing or seems like site name)
            if not title:
                h1 = soup.find("h1")
                if h1:
                    title = h1.get_text(strip=True)
            
            # 3. Fallback to <title> tag
            if not title and soup.title and soup.title.string:
                title = soup.title.string.strip()
                
            # Post-processing: If title contains "|" or "-" and has long suffix, try to take the first part
            # But only if we suspect it's "Title | Site Name" pattern
            if title:
                for sep in [' | ', ' - ', ' — ']:
                    if sep in title:
                        parts = title.split(sep)
                        if len(parts) > 1:
                            # Heuristic: If first part is reasonably long, it's likely the title
                            # If og:title was used, it's usually correct, but sometimes also has site name
                            candidate = parts[0].strip()
                            if len(candidate) > 5:
                                title = candidate
                                break
            
            # Default title if still missing
            if not title:
                import uuid
                title = f"Web Content {str(uuid.uuid4())[:8]}"
            
            # Sanitize Title (remove NUL characters)
            if title:
                title = title.replace('\x00', '')

            # ✅ 優先保留主要內容
            main_content = None
            for selector in ['article', 'main', '[role="main"]', '.post-content', '.entry-content', '.article-content', '#content', '.qa-content']:
                main_content = soup.select_one(selector)
                if main_content:
                    # Keep the new soup focused on main content, but metadata (title) is already extracted
                    soup = BeautifulSoup(str(main_content), 'html.parser')
                    break
            
            # ✅ 進階噪音移除：除了腳本外，移除常見的側邊欄、廣告、留言區
            noise_selectors = [
                'script', 'style', 'noscript', 'iframe', 
                'nav', 'footer', 'header', 'aside',
                '.sidebar', '.left-side', '.right-side',
                '.comments', '.comment-list', '#comments',
                '.related-posts', '.recommended',
                '.share-buttons', '.social-share', '.social-media',
                '.advertisement', '.ads', '.ad-container',
                '.author-info', '.author-bio',
                '.cookie-consent', '.popup',
                '.contest-info-box', '.ir-article-info' # Specific to ithelp
            ]
            
            for selector in noise_selectors:
                for tag in soup.select(selector):
                    tag.decompose()

            # Extract text
            import bs4
            
            structured_elements = []
            current_text_buffer = []

            def is_valid_image(img_tag):
                # 1. Check for filtering classes/ids in parents
                # already largely handled by noise removal, but double check
                
                # 2. Check dimensions if available
                width = img_tag.get('width')
                height = img_tag.get('height')
                
                if width and height:
                    try:
                        w = int(width.replace('px', ''))
                        h = int(height.replace('px', ''))
                        if w < 50 or h < 50: # Skip small icons
                            return False
                        if w / h > 5 or h / w > 5: # Skip extreme aspect ratios (banners/dividers)
                            return False
                    except ValueError:
                        pass
                
                # 3. Check for obvious icon classes
                classes = img_tag.get('class', [])
                if isinstance(classes, list):
                    classes = ' '.join(classes)
                if 'icon' in classes.lower() or 'logo' in classes.lower() or 'avatar' in classes.lower():
                    return False
                    
                src = img_tag.get('src') or ''
                if 'icon' in src.lower() or 'logo' in src.lower():
                    return False

                return True

            def process_image_node(img_tag):
                img_src = img_tag.get('src') or img_tag.get('data-src')
                if not img_src:
                    return None
                
                # Handle relative URLs
                if not img_src.startswith('data:'):
                    if img_src.startswith('//'):
                        img_src = 'https:' + img_src
                    elif img_src.startswith('/'):
                        from urllib.parse import urlparse
                        base_url = f"{urlparse(source).scheme}://{urlparse(source).netloc}"
                        img_src = urljoin(base_url, img_src)
                    elif not img_src.startswith('http'):
                        img_src = urljoin(source, img_src)
                
                img_bytes = None
                try:
                    # 1. Get Image Bytes
                    if img_src.startswith('data:'):
                        import base64
                        if ',' in img_src:
                            header, encoded = img_src.split(',', 1)
                            if ';base64' in header:
                                img_bytes = base64.b64decode(encoded)
                    else:
                        headers_img = {"User-Agent": headers["User-Agent"]} 
                        img_response = http.get(img_src, headers=headers_img, timeout=10)
                        img_response.raise_for_status()
                        img_bytes = img_response.content

                    if not img_bytes:
                        return None

                    # 2. Process Image
                    try:
                        with Image.open(io.BytesIO(img_bytes)) as pil_img:
                            if pil_img.format not in ['PNG', 'JPEG', 'JPG', 'GIF', 'WEBP']:
                                return None
                            # Additional size check on actual image
                            w, h = pil_img.size
                            if w < 50 or h < 50:
                                return None
                    except Exception:
                        return None

                    # Convert and Analyze
                    base64_uri = image_to_base64_uri(img_bytes)
                    if not base64_uri:
                        return None
                    
                    vision_result = process_image_with_vision(img_bytes)
                    
                    return {
                        "type": "image",
                        "base64": base64_uri,
                        "vision_description": vision_result["description"],
                        "vision_tokens": vision_result["total_tokens"],
                        "vision_cost": vision_result["cost"]
                    }
                except Exception as img_error:
                    print(f"Warning: Failed to process image {img_src[:50]}... : {str(img_error)}")
                    return None

            def flush_text_buffer():
                if current_text_buffer:
                    text_content = "".join(current_text_buffer).strip()
                    if text_content:
                        # Sanitize Text Content (remove NUL characters)
                        text_content = text_content.replace('\x00', '')
                        structured_elements.append({
                            "type": "text",
                            "content": text_content
                        })
                    current_text_buffer.clear()

            # Strict filtering state
            self.stop_images = False
            
            def check_stop_section(node):
                """Check if we've entered a section where images should be ignored."""
                if self.stop_images: 
                    return True
                    
                # Check headers or specific divs
                if node.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'section']:
                    text = node.get_text(strip=True).lower()
                    
                    # Heuristic: headers that are short and contain specific keywords
                    # usually denote start of "junk" sections
                    if len(text) < 50:
                        stop_keywords = [
                            'related post', 'related article', 'read more', 'recommended', 
                            'you may also like', 'more from', 'latest posts', 'trending',
                            '延伸閱讀', '相關文章', '更多文章', '推薦閱讀', '熱門文章'
                        ]
                        if any(kw in text for kw in stop_keywords):
                            self.stop_images = True
                            return True
                return False

            def traverse_dom(node):
                if isinstance(node, bs4.NavigableString):
                    text = str(node)
                    if text.strip():
                        current_text_buffer.append(text)
                    elif '\n' in text:
                        # Preserve significant whitespace roughly
                        if current_text_buffer and not current_text_buffer[-1].endswith('\n'):
                             current_text_buffer.append(' ')
                    return

                # Check for section boundaries
                if check_stop_section(node):
                    pass

                if node.name == 'img':
                    # Skip images if we are in a stop section
                    if self.stop_images:
                        return

                    if is_valid_image(node):
                        img_data = process_image_node(node)
                        if img_data:
                            flush_text_buffer()
                            structured_elements.append(img_data)
                    return
                
                # Block elements - add newline before/after
                is_block = node.name in ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'article', 'section', 'br']
                
                if node.name == 'br':
                    current_text_buffer.append('\n')
                    return

                if is_block:
                    if current_text_buffer and not current_text_buffer[-1].endswith('\n'):
                        current_text_buffer.append('\n')
                
                for child in node.children:
                    traverse_dom(child)
                
                if is_block:
                    if current_text_buffer and not current_text_buffer[-1].endswith('\n'):
                        current_text_buffer.append('\n')

            # Start traversal on main_content or soup
            traverse_dom(soup)
            flush_text_buffer()
            
            single_page = Page(page_number=1, structured_elements=structured_elements)
            
            print(f"✅ Successfully read from URL: {source} (Title: {title})")
            return Document(source=source, pages=[single_page], metadata={"title": title})
            
        except Exception as e:
            print(f"Error reading URL {source}: {str(e)}")
            raise e
