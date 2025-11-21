"""
Caching helpers for character analysis backed by database.
"""

from typing import Any, Dict, Optional, Tuple
from shared.database import db


async def get_cached_analysis(image_hash: str) -> Optional[Dict[str, Any]]:
    """
    Return cached normalized analysis dict or None.
    """
    try:
        res = await (
            db.table("character_analyses")
            .select("normalized_analysis, analysis_version, used_cache, warnings")
            .eq("image_hash", image_hash)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            normalized = row.get("normalized_analysis")
            warnings = row.get("warnings") or []
            return {
                "analysis": normalized,
                "warnings": warnings,
                "used_cache": True,
            }
    except Exception:
        # Cache miss or error - fall through silently
        pass
    return None


async def store_cached_analysis(
    user_id: str,
    image_url: str,
    image_hash: str,
    normalized_analysis: Dict[str, Any],
    raw_provider_output: Dict[str, Any],
    provider: str,
) -> Tuple[bool, Optional[str]]:
    """
    Persist analysis. Returns (success, error_message).
    """
    try:
        await db.table("character_analyses").insert(
            {
                "user_id": user_id,
                "image_url": image_url,
                "image_hash": image_hash,
                "normalized_analysis": normalized_analysis,
                "raw_provider_output": raw_provider_output,
                "confidence_per_attribute": normalized_analysis.get("confidence_per_attribute", {}),
                "analysis_version": normalized_analysis.get("analysis_version", "v1"),
                "provider": provider,
                "used_cache": False,
                "warnings": [],
            }
        ).execute()
        return True, None
    except Exception as e:
        return False, str(e)


