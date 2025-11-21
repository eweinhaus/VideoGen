"""
Clip Version Database Verification.

Provides utilities to verify clip version integrity in the database
after save operations. Ensures original and regenerated versions
are properly saved with different video URLs.
"""
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from shared.database import DatabaseClient
from shared.logging import get_logger
from shared.errors import ValidationError

logger = get_logger(__name__)


async def verify_clip_versions_after_save(
    job_id: UUID,
    clip_index: int,
    expected_original_url: Optional[str] = None,
    expected_latest_url: Optional[str] = None,
    expected_latest_version: Optional[int] = None
) -> Dict[str, any]:
    """
    Verify that clip versions are correctly saved in the database.
    
    This function performs comprehensive checks:
    1. Both original (v1) and regenerated versions exist
    2. Video URLs are different between versions
    3. is_current flags are set correctly (v1=False, latest=True)
    4. Optional URL matching against expected values
    
    Args:
        job_id: Job UUID
        clip_index: Clip index
        expected_original_url: Optional expected URL for version 1 (for validation)
        expected_latest_url: Optional expected URL for latest version (for validation)
        expected_latest_version: Optional expected version number for latest (for validation)
        
    Returns:
        Dict with verification results:
        {
            "success": bool,
            "message": str,
            "v1_url": str,
            "v1_is_current": bool,
            "v_latest_url": str,
            "v_latest_version": int,
            "v_latest_is_current": bool,
            "total_versions": int,
            "urls_different": bool
        }
        
    Raises:
        ValidationError: If critical integrity issues are found (same URLs, missing versions)
    """
    db = DatabaseClient()
    
    try:
        # Load all versions for this clip
        verification_result = await db.table("clip_versions").select(
            "version_number", "video_url", "is_current"
        ).eq(
            "job_id", str(job_id)
        ).eq(
            "clip_index", clip_index
        ).order("version_number", desc=False).execute()
        
        if not verification_result.data or len(verification_result.data) < 2:
            error_msg = (
                f"Insufficient versions in database: Expected at least 2 versions (original + regenerated), "
                f"found {len(verification_result.data) if verification_result.data else 0}. "
                f"Job: {job_id}, Clip: {clip_index}"
            )
            logger.error(
                "🚨 VERIFICATION FAILED: Insufficient versions",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "versions_count": len(verification_result.data) if verification_result.data else 0,
                    "expected_min": 2
                }
            )
            raise ValidationError(error_msg)
        
        versions_saved = verification_result.data
        
        # Find version 1 (original)
        v1 = next((v for v in versions_saved if v.get("version_number") == 1), None)
        if not v1:
            error_msg = (
                f"Missing original version (v1) in database. "
                f"Job: {job_id}, Clip: {clip_index}"
            )
            logger.error(
                "🚨 VERIFICATION FAILED: Original version (v1) not found",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "all_versions": [v.get("version_number") for v in versions_saved]
                }
            )
            raise ValidationError(error_msg)
        
        # Find latest version (highest version_number)
        v_latest = max(versions_saved, key=lambda v: v.get("version_number", 0))
        latest_version_number = v_latest.get("version_number")
        
        # Extract URLs
        v1_url = v1.get("video_url")
        v_latest_url = v_latest.get("video_url")
        
        # CRITICAL CHECK: URLs must be different
        if v1_url == v_latest_url:
            error_msg = (
                f"Database integrity violation: Original (v1) and regenerated (v{latest_version_number}) "
                f"have the SAME video_url! This indicates the original was overwritten. "
                f"Job: {job_id}, Clip: {clip_index}, URL: {v1_url}"
            )
            logger.error(
                "🚨 CRITICAL BUG: Original and regenerated versions have SAME video URL!",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "v1_url": v1_url,
                    "v_latest_url": v_latest_url,
                    "v1_is_current": v1.get("is_current"),
                    "v_latest_is_current": v_latest.get("is_current"),
                    "latest_version_number": latest_version_number
                }
            )
            raise ValidationError(error_msg)
        
        # Verify is_current flags
        v1_is_current = v1.get("is_current")
        v_latest_is_current = v_latest.get("is_current")
        
        integrity_warnings = []
        
        if v1_is_current != False:
            warning = f"Version 1 (original) has incorrect is_current flag: {v1_is_current} (expected False)"
            integrity_warnings.append(warning)
            logger.warning(
                "⚠️ Database integrity issue: Version 1 should have is_current=False",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "v1_is_current": v1_is_current
                }
            )
        
        if v_latest_is_current != True:
            warning = f"Latest version (v{latest_version_number}) has incorrect is_current flag: {v_latest_is_current} (expected True)"
            integrity_warnings.append(warning)
            logger.warning(
                "⚠️ Database integrity issue: Latest version should have is_current=True",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "version_number": latest_version_number,
                    "is_current": v_latest_is_current
                }
            )
        
        # Optional URL validation
        url_validation_issues = []
        
        if expected_original_url and v1_url != expected_original_url:
            issue = f"Version 1 URL mismatch: expected {expected_original_url}, got {v1_url}"
            url_validation_issues.append(issue)
            logger.warning(
                "⚠️ Version 1 URL does not match expected value",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "expected": expected_original_url,
                    "actual": v1_url
                }
            )
        
        if expected_latest_url and v_latest_url != expected_latest_url:
            issue = f"Latest version URL mismatch: expected {expected_latest_url}, got {v_latest_url}"
            url_validation_issues.append(issue)
            logger.warning(
                "⚠️ Latest version URL does not match expected value",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "expected": expected_latest_url,
                    "actual": v_latest_url,
                    "version_number": latest_version_number
                }
            )
        
        if expected_latest_version and latest_version_number != expected_latest_version:
            issue = f"Latest version number mismatch: expected v{expected_latest_version}, got v{latest_version_number}"
            url_validation_issues.append(issue)
            logger.warning(
                "⚠️ Latest version number does not match expected value",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "expected": expected_latest_version,
                    "actual": latest_version_number
                }
            )
        
        # Build success message
        success_msg = (
            f"✅ Verification passed: {len(versions_saved)} versions saved correctly. "
            f"Original (v1) and regenerated (v{latest_version_number}) have different URLs."
        )
        
        if integrity_warnings:
            success_msg += f" Warnings: {len(integrity_warnings)} integrity issues detected."
        
        if url_validation_issues:
            success_msg += f" Validation: {len(url_validation_issues)} URL mismatches."
        
        logger.info(
            success_msg,
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "total_versions": len(versions_saved),
                "v1_url": v1_url,
                "v1_is_current": v1_is_current,
                f"v{latest_version_number}_url": v_latest_url,
                f"v{latest_version_number}_is_current": v_latest_is_current,
                "urls_different": True,
                "integrity_warnings": integrity_warnings,
                "url_validation_issues": url_validation_issues
            }
        )
        
        return {
            "success": True,
            "message": success_msg,
            "v1_url": v1_url,
            "v1_is_current": v1_is_current,
            "v_latest_url": v_latest_url,
            "v_latest_version": latest_version_number,
            "v_latest_is_current": v_latest_is_current,
            "total_versions": len(versions_saved),
            "urls_different": True,
            "integrity_warnings": integrity_warnings,
            "url_validation_issues": url_validation_issues
        }
        
    except ValidationError:
        # Re-raise validation errors (integrity failures)
        raise
    except Exception as e:
        error_msg = f"Failed to verify clip versions: {str(e)}"
        logger.error(
            "⚠️ Verification failed due to exception",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        # Return failure instead of raising (non-critical verification failure)
        return {
            "success": False,
            "message": error_msg,
            "error": str(e),
            "error_type": type(e).__name__
        }


async def get_current_clip_version(
    job_id: UUID,
    clip_index: int
) -> Optional[Dict[str, any]]:
    """
    Get the current (latest) version for a clip.
    
    Args:
        job_id: Job UUID
        clip_index: Clip index
        
    Returns:
        Dict with current version data, or None if not found:
        {
            "version_number": int,
            "video_url": str,
            "thumbnail_url": str,
            "prompt": str,
            "user_instruction": str,
            "cost": float,
            "duration": float,
            "is_current": bool,
            "created_at": str
        }
    """
    db = DatabaseClient()
    
    try:
        result = await db.table("clip_versions").select("*").eq(
            "job_id", str(job_id)
        ).eq(
            "clip_index", clip_index
        ).eq(
            "is_current", True
        ).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        
        # Fallback: get highest version number
        result = await db.table("clip_versions").select("*").eq(
            "job_id", str(job_id)
        ).eq(
            "clip_index", clip_index
        ).order("version_number", desc=True).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            logger.warning(
                "No version marked as current, using highest version number",
                extra={
                    "job_id": str(job_id),
                    "clip_index": clip_index,
                    "version_number": result.data[0].get("version_number")
                }
            )
            return result.data[0]
        
        return None
        
    except Exception as e:
        logger.error(
            f"Failed to get current clip version: {e}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index
            },
            exc_info=True
        )
        return None


async def get_all_clip_versions(
    job_id: UUID,
    clip_index: int
) -> List[Dict[str, any]]:
    """
    Get all versions for a clip, ordered by version number.
    
    Args:
        job_id: Job UUID
        clip_index: Clip index
        
    Returns:
        List of version dicts, ordered by version_number ascending
    """
    db = DatabaseClient()
    
    try:
        result = await db.table("clip_versions").select("*").eq(
            "job_id", str(job_id)
        ).eq(
            "clip_index", clip_index
        ).order("version_number", desc=False).execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(
            f"Failed to get all clip versions: {e}",
            extra={
                "job_id": str(job_id),
                "clip_index": clip_index
            },
            exc_info=True
        )
        return []

