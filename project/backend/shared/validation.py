"""
Validation utilities.

Shared validation utilities for common input validation tasks.
"""

import mimetypes
from typing import Optional, BinaryIO, List
from fastapi import UploadFile

from shared.errors import ValidationError


def validate_audio_file(
    file: BinaryIO,
    max_size_mb: int = 10
) -> None:
    """
    Validate an audio file.
    
    Args:
        file: File object to validate
        max_size_mb: Maximum file size in MB (default: 10)
        
    Raises:
        ValidationError: If file is invalid
    """
    # Check if file is None or empty
    if file is None:
        raise ValidationError("File is required")
    
    # Get file size
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_size == 0:
        raise ValidationError("File is empty")
    
    # Check file size
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise ValidationError(
            f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds maximum "
            f"of {max_size_mb} MB"
        )
    
    # Check MIME type
    # Try to read first bytes to detect type
    file.seek(0)
    header = file.read(12)
    file.seek(0)
    
    # Check for common audio file signatures
    valid_signatures = [
        b"ID3",  # MP3 with ID3 tag
        b"\xff\xfb",  # MP3 frame sync
        b"\xff\xf3",  # MP3 frame sync
        b"\xff\xf2",  # MP3 frame sync
        b"RIFF",  # WAV
        b"fLaC",  # FLAC
        b"OggS",  # OGG
    ]
    
    is_valid_audio = any(header.startswith(sig) for sig in valid_signatures)
    
    # Also check filename if available (must be a string path)
    if hasattr(file, "name") and file.name and isinstance(file.name, (str, bytes)):
        try:
            filename = file.name if isinstance(file.name, str) else str(file.name)
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type:
                valid_mime_types = [
                    "audio/mpeg",
                    "audio/mp3",
                    "audio/wav",
                    "audio/x-wav",
                    "audio/flac",
                    "audio/x-flac",
                    "audio/ogg",
                    "audio/vorbis"
                ]
                if mime_type in valid_mime_types:
                    is_valid_audio = True
        except (TypeError, AttributeError):
            # If filename is not a valid path, skip MIME type check
            pass
    
    if not is_valid_audio:
        raise ValidationError(
            "Invalid audio file format. Supported formats: MP3, WAV, FLAC, OGG"
        )


def validate_prompt(
    prompt: str,
    min_length: int = 50,
    max_length: int = 500
) -> None:
    """
    Validate a creative prompt.
    
    Args:
        prompt: Prompt string to validate
        min_length: Minimum length in characters (default: 50)
        max_length: Maximum length in characters (default: 500)
        
    Raises:
        ValidationError: If prompt is invalid
    """
    if not prompt:
        raise ValidationError("Prompt is required")
    
    if not isinstance(prompt, str):
        raise ValidationError("Prompt must be a string")
    
    prompt_length = len(prompt.strip())
    
    if prompt_length < min_length:
        raise ValidationError(
            f"Prompt must be at least {min_length} characters long "
            f"(current: {prompt_length})"
        )
    
    if prompt_length > max_length:
        raise ValidationError(
            f"Prompt must be at most {max_length} characters long "
            f"(current: {prompt_length})"
        )


def validate_file_size(
    file_size_bytes: int,
    max_size_bytes: int
) -> None:
    """
    Validate file size.
    
    Args:
        file_size_bytes: File size in bytes
        max_size_bytes: Maximum allowed size in bytes
        
    Raises:
        ValidationError: If file size exceeds maximum
    """
    if file_size_bytes < 0:
        raise ValidationError("File size cannot be negative")
    
    if file_size_bytes > max_size_bytes:
        max_size_mb = max_size_bytes / (1024 * 1024)
        file_size_mb = file_size_bytes / (1024 * 1024)
        raise ValidationError(
            f"File size ({file_size_mb:.2f} MB) exceeds maximum "
            f"of {max_size_mb:.2f} MB"
        )


def validate_reference_image(
    file: UploadFile,
    max_size_mb: int = 20,
    allowed_formats: Optional[List[str]] = None
) -> None:
    """
    Validate reference image file.
    
    Args:
        file: UploadFile object to validate
        max_size_mb: Maximum file size in MB (default: 20)
        allowed_formats: List of allowed MIME types (default: PNG, JPEG)
        
    Raises:
        ValidationError: If file is invalid
    """
    if allowed_formats is None:
        allowed_formats = ["image/png", "image/jpeg", "image/jpg"]
    
    if file is None:
        raise ValidationError("Image file is required")
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    if file_size == 0:
        raise ValidationError("Image file is empty")
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise ValidationError(
            f"Image file size ({file_size / (1024 * 1024):.2f} MB) exceeds maximum "
            f"of {max_size_mb} MB"
        )
    
    # Check MIME type
    if file.content_type:
        if file.content_type not in allowed_formats:
            raise ValidationError(
                f"Invalid image format. Supported formats: PNG, JPEG. "
                f"Received: {file.content_type}"
            )
    
    # Check file extension
    if file.filename:
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        valid_extensions = ['png', 'jpg', 'jpeg']
        if ext not in valid_extensions:
            raise ValidationError(
                f"Invalid file extension. Supported: {', '.join(valid_extensions)}. "
                f"Received: {ext}"
            )
    
    # Check image signature (first bytes)
    file.file.seek(0)
    header = file.file.read(12)
    file.file.seek(0)
    
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    # JPEG signature: FF D8 FF
    valid_signatures = [
        b"\x89PNG\r\n\x1a\n",  # PNG
        b"\xff\xd8\xff",  # JPEG
    ]
    
    is_valid_image = any(header.startswith(sig) for sig in valid_signatures)
    
    if not is_valid_image:
        raise ValidationError(
            "Invalid image file format. File does not match PNG or JPEG signature. "
            "Supported formats: PNG, JPEG"
        )
