#!/bin/bash
# Check backend logs for character reference fix diagnostics

if [ -z "$1" ]; then
    echo "Usage: ./check_character_fix_logs.sh <JOB_ID>"
    echo ""
    echo "Example: ./check_character_fix_logs.sh fdde43cf-b811-4b7f-8143-ed6aecd8f19e"
    exit 1
fi

JOB_ID="$1"
PROJECT_ROOT="/Users/user/Desktop/Github/VideoGen"
LOG_FILE="$PROJECT_ROOT/project/backend/logs/backend.log"

echo "======================================"
echo "CHARACTER FIX DIAGNOSTIC REPORT"
echo "Job ID: $JOB_ID"
echo "======================================"
echo ""

if [ ! -f "$LOG_FILE" ]; then
    echo "✗ ERROR: Log file not found at $LOG_FILE"
    exit 1
fi

echo "Searching logs for job $JOB_ID..."
echo ""

# Check if job appears in logs at all
JOB_COUNT=$(grep -c "$JOB_ID" "$LOG_FILE" 2>/dev/null || echo "0")

if [ "$JOB_COUNT" -eq "0" ]; then
    echo "✗ ERROR: Job ID $JOB_ID not found in logs"
    echo ""
    echo "Possible reasons:"
    echo "1. Job hasn't been processed yet"
    echo "2. Worker wasn't restarted after code changes"
    echo "3. Wrong job ID"
    echo ""
    echo "Recent jobs in log:"
    grep -o "job_id=[a-f0-9-]\{36\}" "$LOG_FILE" | tail -5 | sort -u
    exit 1
fi

echo "✓ Found $JOB_COUNT log entries for this job"
echo ""

# ============================================
# SECTION 1: Reference Generator Stage
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. REFERENCE GENERATOR (Module 5)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

REFGEN_CHECKPOINT=$(grep "$JOB_ID" "$LOG_FILE" | grep "SOLUTION 2 CHECKPOINT" | grep "reference_generator" | grep "character_references after adding uploads")

if [ -n "$REFGEN_CHECKPOINT" ]; then
    echo "✓ Found Reference Generator checkpoint"
    echo ""
    echo "$REFGEN_CHECKPOINT" | python3 -c "
import sys
import json
for line in sys.stdin:
    try:
        # Extract JSON portion
        if 'character_references after adding uploads' in line:
            # Try to find uploaded_count in the log
            if 'uploaded_count' in line:
                parts = line.split('uploaded_count')
                if len(parts) > 1:
                    # Extract the number after =
                    count_str = parts[1].split()[0].rstrip(',')
                    print(f'   Uploaded character count: {count_str}')
            if 'total_count' in line:
                parts = line.split('total_count')
                if len(parts) > 1:
                    count_str = parts[1].split()[0].rstrip(',')
                    print(f'   Total character count: {count_str}')
    except:
        pass
"
else
    echo "✗ No Reference Generator checkpoint found"
    echo "   This means the uploaded character wasn't properly integrated"
fi

echo ""

# ============================================
# SECTION 2: Prompt Generator Stage
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. PROMPT GENERATOR (Module 6)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

MAPPER_CHECKPOINT=$(grep "$JOB_ID" "$LOG_FILE" | grep "SOLUTION 2 CHECKPOINT" | grep "main character reference included")

if [ -n "$MAPPER_CHECKPOINT" ]; then
    echo "✓ Found Prompt Generator checkpoint"
    CLIP_COUNT=$(echo "$MAPPER_CHECKPOINT" | wc -l)
    echo "   Main character included in $CLIP_COUNT clips"
else
    echo "✗ No Prompt Generator checkpoint found"
    echo "   This means character references weren't mapped to clips"
fi

echo ""

# ============================================
# SECTION 3: Video Generator Stage
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. VIDEO GENERATOR (Module 7)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check SOLUTION 3 FIX logs
FIX_LOGS=$(grep "$JOB_ID" "$LOG_FILE" | grep "SOLUTION 3 FIX")

if [ -n "$FIX_LOGS" ]; then
    echo "✓ Found SOLUTION 3 FIX logs"
    echo ""
    
    # Count how many clips used character as primary
    CHAR_PRIMARY_COUNT=$(echo "$FIX_LOGS" | grep -c "main character (uploaded) as primary image_url")
    TOTAL_CLIPS=$(echo "$FIX_LOGS" | grep -o "clip [0-9]*" | wc -l)
    
    echo "   Clips using uploaded character as primary: $CHAR_PRIMARY_COUNT"
    echo "   Total clips processed: $TOTAL_CLIPS"
    echo ""
    
    if [ "$CHAR_PRIMARY_COUNT" -eq "$TOTAL_CLIPS" ]; then
        echo "   ✓ SUCCESS: All clips used uploaded character as primary image"
    elif [ "$CHAR_PRIMARY_COUNT" -gt "0" ]; then
        echo "   ⚠ PARTIAL: Only $CHAR_PRIMARY_COUNT/$TOTAL_CLIPS clips used character"
        echo ""
        echo "   Clips NOT using character:"
        echo "$FIX_LOGS" | grep -v "main character (uploaded)" | grep "clip [0-9]*"
    else
        echo "   ✗ FAILURE: No clips used uploaded character as primary"
    fi
else
    echo "✗ No SOLUTION 3 FIX logs found"
    echo "   This means:"
    echo "   1. Worker wasn't restarted after code changes, OR"
    echo "   2. This job was processed before the fix was deployed"
fi

echo ""

# ============================================
# SECTION 4: Generator.py (Replicate API calls)
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. REPLICATE API CALLS (generator.py)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

GENERATOR_LOGS=$(grep "$JOB_ID" "$LOG_FILE" | grep "SOLUTION 2 CHECKPOINT" | grep "generator.py")

if [ -n "$GENERATOR_LOGS" ]; then
    echo "✓ Found generator.py checkpoints"
    
    # Count face-heavy clips
    FACE_HEAVY_COUNT=$(echo "$GENERATOR_LOGS" | grep -c "is_face_heavy.*True")
    echo "   Face-heavy clips detected: $FACE_HEAVY_COUNT"
    
    # Check if character refs were sent to API
    CHAR_REF_SENT=$(echo "$GENERATOR_LOGS" | grep -c "character.*reference.*sent")
    echo "   Clips with character references sent to API: $CHAR_REF_SENT"
else
    echo "⚠ No generator.py checkpoints found"
fi

echo ""

# ============================================
# SUMMARY & RECOMMENDATIONS
# ============================================
echo "======================================"
echo "SUMMARY"
echo "======================================"
echo ""

# Determine overall status
if [ -n "$FIX_LOGS" ] && [ "$CHAR_PRIMARY_COUNT" -eq "$TOTAL_CLIPS" ] && [ "$TOTAL_CLIPS" -gt "0" ]; then
    echo "✓ STATUS: FIX IS WORKING"
    echo ""
    echo "The uploaded character is being used as the primary reference"
    echo "in all clips. If the character still doesn't appear in the"
    echo "final video, the issue is likely with:"
    echo "1. The Replicate API not honoring the reference image"
    echo "2. The reference image quality or format"
    echo "3. Model-specific limitations (try Veo 3.1 instead of Kling)"
elif [ -z "$FIX_LOGS" ]; then
    echo "✗ STATUS: FIX NOT ACTIVE"
    echo ""
    echo "Action required:"
    echo "1. Restart the worker: ./scripts/restart_and_test_character_fix.sh"
    echo "2. Generate a NEW video with a character upload"
    echo "3. Run this script again with the new job ID"
else
    echo "⚠ STATUS: PARTIAL FIX"
    echo ""
    echo "The fix is running but not working for all clips."
    echo "This requires deeper investigation."
    echo ""
    echo "Next steps:"
    echo "1. Review the full logs for this job:"
    echo "   grep '$JOB_ID' '$LOG_FILE' | grep 'SOLUTION' > /tmp/debug_$JOB_ID.log"
    echo "2. Check if character references are being downloaded correctly"
    echo "3. Verify the reference image URLs are valid"
fi

echo ""
echo "Full diagnostic logs saved to:"
echo "  grep '$JOB_ID' '$LOG_FILE' | grep 'SOLUTION' > /tmp/character_fix_$JOB_ID.log"
grep "$JOB_ID" "$LOG_FILE" | grep 'SOLUTION' > "/tmp/character_fix_$JOB_ID.log" 2>/dev/null || true
echo ""

