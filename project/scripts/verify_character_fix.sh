#!/bin/bash
# Script to verify the character reference fix implementation
# This script helps trace uploaded character images through the pipeline

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}Character Reference Fix Verification Script${NC}"
echo -e "${BLUE}==================================================${NC}"
echo ""

# Check if log file or job ID is provided
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}Usage:${NC}"
    echo "  $0 <log_file>                  # Search in log file"
    echo "  $0 <log_file> <job_id>         # Search for specific job"
    echo ""
    echo -e "${YELLOW}Example:${NC}"
    echo "  $0 backend.log"
    echo "  $0 backend.log abc123-def-456"
    exit 1
fi

LOG_FILE=$1
JOB_ID=${2:-""}

if [ ! -f "$LOG_FILE" ]; then
    echo -e "${RED}Error: Log file '$LOG_FILE' not found${NC}"
    exit 1
fi

echo -e "${GREEN}Using log file: $LOG_FILE${NC}"
if [ -n "$JOB_ID" ]; then
    echo -e "${GREEN}Filtering by job ID: $JOB_ID${NC}"
fi
echo ""

# Function to search and display results
search_checkpoint() {
    local checkpoint=$1
    local description=$2
    local job_filter=$3
    
    echo -e "${BLUE}Checking: $description${NC}"
    
    if [ -n "$job_filter" ]; then
        results=$(grep "$checkpoint" "$LOG_FILE" | grep "$job_filter" || true)
    else
        results=$(grep "$checkpoint" "$LOG_FILE" || true)
    fi
    
    if [ -n "$results" ]; then
        echo -e "${GREEN}✓ Found ($checkpoint)${NC}"
        echo "$results" | head -3
        count=$(echo "$results" | wc -l | tr -d ' ')
        if [ "$count" -gt 3 ]; then
            echo -e "${YELLOW}... and $((count - 3)) more occurrences${NC}"
        fi
    else
        echo -e "${RED}✗ Not found ($checkpoint)${NC}"
    fi
    echo ""
}

# Stage 1: Reference Generator
echo -e "${YELLOW}===========================================${NC}"
echo -e "${YELLOW}STAGE 1: Reference Generator${NC}"
echo -e "${YELLOW}===========================================${NC}"
echo ""

search_checkpoint "uploaded_character_count" "Uploaded character count in final ReferenceImages" "$JOB_ID"
search_checkpoint "uploaded_character_verification" "Verification of uploaded character" "$JOB_ID"
search_checkpoint "uploaded_character_missing" "Warning if uploaded character missing" "$JOB_ID"

# Stage 2: Prompt Generator
echo -e "${YELLOW}===========================================${NC}"
echo -e "${YELLOW}STAGE 2: Prompt Generator${NC}"
echo -e "${YELLOW}===========================================${NC}"
echo ""

search_checkpoint "uploaded_character_identified" "Uploaded character identified" "$JOB_ID"
search_checkpoint "prompt_generator_index_built" "Reference index built" "$JOB_ID"
search_checkpoint "prompt_generator_clip_mapping" "Character references mapped to clips" "$JOB_ID"

# Stage 3: Video Generator (Process)
echo -e "${YELLOW}===========================================${NC}"
echo -e "${YELLOW}STAGE 3: Video Generator (Process)${NC}"
echo -e "${YELLOW}===========================================${NC}"
echo ""

search_checkpoint "reference_collection_start" "Reference collection started" "$JOB_ID"
search_checkpoint "image_url_prioritization" "Image URL prioritization (SOLUTION 3 FIX)" "$JOB_ID"
search_checkpoint "reference_collection_complete" "Reference collection complete" "$JOB_ID"
search_checkpoint "before_generate_video_clip" "Final verification before generation" "$JOB_ID"

# Stage 4: Video Generator (Generator)
echo -e "${YELLOW}===========================================${NC}"
echo -e "${YELLOW}STAGE 4: Video Generator (Generator)${NC}"
echo -e "${YELLOW}===========================================${NC}"
echo ""

search_checkpoint "generator_replicate_input_set" "Replicate input set" "$JOB_ID"
search_checkpoint "generator_replicate_api_input" "Final images passed to Replicate API" "$JOB_ID"

# Critical Checks
echo -e "${YELLOW}===========================================${NC}"
echo -e "${YELLOW}CRITICAL CHECKS${NC}"
echo -e "${YELLOW}===========================================${NC}"
echo ""

# Check image_url_source
echo -e "${BLUE}Checking image_url_source values:${NC}"
if [ -n "$JOB_ID" ]; then
    scene_refs=$(grep "image_url_source.*scene_ref" "$LOG_FILE" | grep "$JOB_ID" | wc -l | tr -d ' ')
    char_refs=$(grep "image_url_source.*character_ref" "$LOG_FILE" | grep "$JOB_ID" | wc -l | tr -d ' ')
else
    scene_refs=$(grep "image_url_source.*scene_ref" "$LOG_FILE" | wc -l | tr -d ' ')
    char_refs=$(grep "image_url_source.*character_ref" "$LOG_FILE" | wc -l | tr -d ' ')
fi

if [ "$char_refs" -gt 0 ]; then
    echo -e "${GREEN}✓ Character references used: $char_refs clips${NC}"
else
    echo -e "${RED}✗ No character references used (expected at least 1)${NC}"
fi

if [ "$scene_refs" -gt 0 ]; then
    echo -e "${YELLOW}⚠ Scene references used as primary: $scene_refs clips${NC}"
    echo -e "${YELLOW}  (These clips did NOT use uploaded character as primary)${NC}"
fi
echo ""

# Check character_refs_added count
echo -e "${BLUE}Checking character_refs_added values:${NC}"
if [ -n "$JOB_ID" ]; then
    zero_refs=$(grep "character_refs_added.*0" "$LOG_FILE" | grep "$JOB_ID" | wc -l | tr -d ' ')
    nonzero_refs=$(grep "character_refs_added.*[1-9]" "$LOG_FILE" | grep "$JOB_ID" | wc -l | tr -d ' ')
else
    zero_refs=$(grep "character_refs_added.*0" "$LOG_FILE" | wc -l | tr -d ' ')
    nonzero_refs=$(grep "character_refs_added.*[1-9]" "$LOG_FILE" | wc -l | tr -d ' ')
fi

if [ "$nonzero_refs" -gt 0 ]; then
    echo -e "${GREEN}✓ Character references added to: $nonzero_refs clips${NC}"
else
    echo -e "${RED}✗ No character references added to any clips${NC}"
fi

if [ "$zero_refs" -gt 0 ]; then
    echo -e "${RED}✗ Zero character references in: $zero_refs clips${NC}"
fi
echo ""

# Summary
echo -e "${YELLOW}===========================================${NC}"
echo -e "${YELLOW}SUMMARY${NC}"
echo -e "${YELLOW}===========================================${NC}"
echo ""

if [ "$char_refs" -gt 0 ] && [ "$nonzero_refs" -gt 0 ] && [ "$zero_refs" -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ SUCCESS: Uploaded character appears to be in all clips!${NC}"
    echo -e "${GREEN}    - Character references used as primary: $char_refs clips${NC}"
    echo -e "${GREEN}    - Character references added: $nonzero_refs clips${NC}"
    echo -e "${GREEN}    - Zero character refs: $zero_refs clips${NC}"
elif [ "$scene_refs" -gt "$char_refs" ]; then
    echo -e "${RED}✗✗✗ FAILURE: Scene references dominate over character references${NC}"
    echo -e "${RED}    Scene refs: $scene_refs | Character refs: $char_refs${NC}"
    echo -e "${RED}    The fix may not be working correctly${NC}"
elif [ "$zero_refs" -gt 0 ]; then
    echo -e "${YELLOW}⚠⚠⚠ PARTIAL: Some clips missing character references${NC}"
    echo -e "${YELLOW}    Clips with character refs: $nonzero_refs${NC}"
    echo -e "${YELLOW}    Clips without character refs: $zero_refs${NC}"
else
    echo -e "${YELLOW}⚠⚠⚠ INCONCLUSIVE: Review logs manually${NC}"
    echo -e "${YELLOW}    Character refs: $char_refs | Scene refs: $scene_refs${NC}"
fi
echo ""

echo -e "${BLUE}Verification complete!${NC}"

