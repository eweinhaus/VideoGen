#!/bin/bash
# Check Railway logs for prompt generator LLM fallback issues

SERVICE="${1:-ravishing-analysis}"
JOB_ID="${2:-}"

echo "=========================================="
echo "Checking Prompt Generator LLM Status"
echo "=========================================="
echo ""

if [ -z "$JOB_ID" ]; then
    echo "Checking recent logs for prompt generator issues..."
    echo ""
    echo "Looking for:"
    echo "  - LLM fallback warnings"
    echo "  - LLM errors"
    echo "  - GPT-4o calls"
    echo ""
    
    railway logs --service "$SERVICE" --tail 500 | grep -iE "prompt_generator|LLM|gpt-4o|fallback|deterministic" --color=always | tail -50
    
    echo ""
    echo "=========================================="
    echo "To check a specific job, run:"
    echo "  ./check_prompt_generator_llm.sh $SERVICE <JOB_ID>"
    echo "=========================================="
else
    echo "Checking logs for job: $JOB_ID"
    echo ""
    
    echo "=== LLM Configuration ==="
    railway logs --service "$SERVICE" --tail 1000 | grep -iE "$JOB_ID.*prompt_generator.*use_llm|$JOB_ID.*PROMPT_GENERATOR" --color=always
    
    echo ""
    echo "=== LLM Call Attempts ==="
    railway logs --service "$SERVICE" --tail 1000 | grep -iE "$JOB_ID.*Calling LLM|$JOB_ID.*prompt optimization" --color=always
    
    echo ""
    echo "=== LLM Success/Failure ==="
    railway logs --service "$SERVICE" --tail 1000 | grep -iE "$JOB_ID.*Prompt optimization completed|$JOB_ID.*fallback|$JOB_ID.*LLM.*error|$JOB_ID.*LLM.*unavailable" --color=always
    
    echo ""
    echo "=== LLM Errors ==="
    railway logs --service "$SERVICE" --tail 1000 | grep -iE "$JOB_ID.*(RateLimit|Timeout|API.*error|invalid.*format)" --color=always
    
    echo ""
    echo "=== Metadata (llm_used) ==="
    railway logs --service "$SERVICE" --tail 1000 | grep -iE "$JOB_ID.*llm_used" --color=always
fi

