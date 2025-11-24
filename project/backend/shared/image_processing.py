"""
Image processing utilities.

Utilities for processing user-uploaded reference images to match
the format of generated reference images (1024x1024 PNG).
"""

import io
from typing import Tuple
from PIL import Image
from shared.logging import get_logger

logger = get_logger("image_processing")


async def process_user_reference_image(
    image_bytes: bytes,
    target_size: Tuple[int, int] = (1024, 1024),
    target_format: str = "PNG"
) -> bytes:
    """
    Process user-uploaded image to match reference image format.
    
    - Resize to target_size (default: 1024x1024) maintaining aspect ratio
    - Center crop or pad to square format
    - Convert to target_format (default: PNG)
    - Optimize file size
    
    Args:
        image_bytes: Raw image bytes
        target_size: Target dimensions (width, height) - default: (1024, 1024)
        target_format: Target format - default: "PNG"
        
    Returns:
        Processed image bytes
        
    Raises:
        ValueError: If image cannot be processed
    """
    try:
        # Open image from bytes
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB if needed (for JPEG compatibility)
        if image.mode == "RGBA" and target_format == "JPEG":
            # Create white background
            rgb_image = Image.new("RGB", image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[3])  # Use alpha channel as mask
            image = rgb_image
        elif image.mode not in ("RGB", "RGBA"):
            # Convert to RGB/RGBA
            if image.mode == "P" and "transparency" in image.info:
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")
        
        # Calculate resize dimensions maintaining aspect ratio
        target_width, target_height = target_size
        original_width, original_height = image.size
        
        # Calculate scaling factor to fit within target size
        scale = min(target_width / original_width, target_height / original_height)
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)
        
        # Resize image
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Create square canvas with target size
        square_image = Image.new(image.mode, target_size, (255, 255, 255) if image.mode == "RGB" else (255, 255, 255, 0))
        
        # Calculate position to center the resized image
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2
        
        # Paste resized image onto square canvas
        square_image.paste(image, (x_offset, y_offset))
        
        # Convert to target format
        output = io.BytesIO()
        if target_format == "PNG":
            square_image.save(output, format="PNG", optimize=True)
        elif target_format == "JPEG":
            if square_image.mode == "RGBA":
                # Convert to RGB for JPEG
                rgb_image = Image.new("RGB", square_image.size, (255, 255, 255))
                rgb_image.paste(square_image, mask=square_image.split()[3] if square_image.mode == "RGBA" else None)
                square_image = rgb_image
            square_image.save(output, format="JPEG", quality=95, optimize=True)
        else:
            square_image.save(output, format=target_format, optimize=True)
        
        output.seek(0)
        return output.read()
        
    except Exception as e:
        logger.error(f"Failed to process image: {str(e)}", exc_info=e)
        raise ValueError(f"Failed to process image: {str(e)}") from e


def validate_image_dimensions(
    image_bytes: bytes,
    min_width: int = 512,
    min_height: int = 512,
    max_width: int = 2048,
    max_height: int = 2048
) -> Tuple[int, int]:
    """
    Validate image dimensions.
    
    Args:
        image_bytes: Raw image bytes
        min_width: Minimum width in pixels (default: 512)
        min_height: Minimum height in pixels (default: 512)
        max_width: Maximum width in pixels (default: 2048)
        max_height: Maximum height in pixels (default: 2048)
        
    Returns:
        Tuple of (width, height)
        
    Raises:
        ValueError: If dimensions are invalid
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size
        
        if width < min_width or height < min_height:
            raise ValueError(
                f"Image dimensions ({width}x{height}) are too small. "
                f"Minimum: {min_width}x{min_height}"
            )
        
        if width > max_width or height > max_height:
            raise ValueError(
                f"Image dimensions ({width}x{height}) are too large. "
                f"Maximum: {max_width}x{max_height}"
            )
        
        return (width, height)
        
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.error(f"Failed to validate image dimensions: {str(e)}", exc_info=e)
        raise ValueError(f"Failed to read image dimensions: {str(e)}") from e

