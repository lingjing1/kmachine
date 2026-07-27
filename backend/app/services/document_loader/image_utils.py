import base64
import io
from PIL import Image

def image_to_base64_uri(image_bytes: bytes) -> str:
    """Converts raw image bytes to a base64 encoded PNG data URI.
    Returns empty string if image is invalid or unsupported.
    """
    try:
        # Open the raw image data with Pillow
        raw_image = io.BytesIO(image_bytes)
        try:
            pil_image = Image.open(raw_image)
            # Verify format is supported by Vision LLM
            if pil_image.format not in ['PNG', 'JPEG', 'JPG', 'GIF', 'WEBP']:
                # Silently skip unsupported formats (e.g. SVG, ICO)
                return ""
        except Exception:
            # Cannot identify image file (e.g. SVG or corrupted)
            return ""

        # Convert to PNG and write to an in-memory buffer
        with io.BytesIO() as buffer:
            # Convert mode to RGB if necessary (e.g. for palette images)
            if pil_image.mode in ('P', 'RGBA') and pil_image.format == 'JPEG':
                 pil_image = pil_image.convert('RGB')
            
            pil_image.save(buffer, format="PNG")
            png_image_bytes = buffer.getvalue()

        # Encode the PNG bytes in base64
        base64_image = base64.b64encode(png_image_bytes).decode('utf-8')
        image_uri = f"data:image/png;base64,{base64_image}"
        return image_uri
    except Exception as e:
        print(f"Warning: Could not convert image to base64 URI: {e}")
        return ""
