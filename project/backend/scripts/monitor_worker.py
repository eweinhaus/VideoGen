#!/usr/bin/env python3
"""
Monitor worker status and queue health.

Shows:
- Queue length
- Jobs in queue
- Recent log entries
- Worker process status
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from shared.redis_client import RedisClient
from shared.database import DatabaseClient
from shared.logging import get_logger

logger = get_logger(__name__)


async def check_queue():
    """Check queue status."""
    redis_client = RedisClient()
    
    try:
        # Get queue length
        queue_length = await redis_client.client.llen("videogen:queue")
        
        # Get queued jobs (peek at first 5)
        queued_jobs = []
        if queue_length > 0:
            jobs_data = await redis_client.client.lrange("videogen:queue", 0, 4)
            for job_data in jobs_data:
                try:
                    job = json.loads(job_data)
                    queued_jobs.append({
                        "job_id": job.get("job_id"),
                        "user_id": job.get("user_id"),
                        "stop_at_stage": job.get("stop_at_stage")
                    })
                except json.JSONDecodeError:
                    pass
        
        return {
            "queue_length": queue_length,
            "queued_jobs": queued_jobs
        }
    except Exception as e:
        logger.error(f"Failed to check queue: {e}")
        return None


async def check_active_jobs():
    """Check active jobs from database."""
    db_client = DatabaseClient()
    
    try:
        result = await db_client.table("jobs").select("id, status, current_stage, progress, created_at").eq("status", "processing").execute()
        
        active_jobs = []
        if result.data:
            for job in result.data:
                active_jobs.append({
                    "job_id": job["id"],
                    "stage": job.get("current_stage"),
                    "progress": job.get("progress"),
                    "created_at": job.get("created_at")
                })
        
        return active_jobs
    except Exception as e:
        logger.error(f"Failed to check active jobs: {e}")
        return None


async def get_recent_logs(lines=20):
    """Get recent log entries."""
    log_file = backend_dir / "logs" / "app.log"
    
    if not log_file.exists():
        return ["No log file found"]
    
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]
            
            # Parse and format JSON logs
            formatted_logs = []
            for line in recent_lines:
                try:
                    log_entry = json.loads(line)
                    timestamp = log_entry.get("timestamp", "")
                    level = log_entry.get("level", "INFO")
                    module = log_entry.get("module", "")
                    message = log_entry.get("message", "")
                    job_id = log_entry.get("job_id", "")
                    
                    # Format timestamp (remove microseconds)
                    if timestamp:
                        timestamp = timestamp.split(".")[0].replace("T", " ").replace("Z", "")
                    
                    # Color code by level
                    if level == "ERROR":
                        level_str = f"\033[91m{level}\033[0m"  # Red
                    elif level == "WARNING":
                        level_str = f"\033[93m{level}\033[0m"  # Yellow
                    elif level == "INFO":
                        level_str = f"\033[92m{level}\033[0m"  # Green
                    else:
                        level_str = level
                    
                    formatted = f"[{timestamp}] {level_str} [{module}]"
                    if job_id:
                        formatted += f" [job:{job_id[:8]}]"
                    formatted += f" {message}"
                    
                    formatted_logs.append(formatted)
                except json.JSONDecodeError:
                    # Not a JSON log, just append as-is
                    formatted_logs.append(line.strip())
            
            return formatted_logs
    except Exception as e:
        return [f"Error reading logs: {e}"]


async def monitor():
    """Main monitoring function."""
    print("\033[2J\033[H")  # Clear screen
    print("=" * 80)
    print("VideoGen Worker Monitor")
    print("=" * 80)
    print()
    
    # Check queue
    print("\033[1m📋 Queue Status\033[0m")
    print("-" * 80)
    queue_status = await check_queue()
    if queue_status:
        print(f"  Queue length: {queue_status['queue_length']}")
        if queue_status['queued_jobs']:
            print(f"  Queued jobs:")
            for job in queue_status['queued_jobs']:
                print(f"    - {job['job_id']} (user: {job['user_id'][:8]})")
        else:
            print(f"  No jobs in queue")
    else:
        print("  \033[91mFailed to connect to Redis\033[0m")
    print()
    
    # Check active jobs
    print("\033[1m⚙️  Active Jobs\033[0m")
    print("-" * 80)
    active_jobs = await check_active_jobs()
    if active_jobs:
        for job in active_jobs:
            stage = job.get('stage', 'unknown')
            progress = job.get('progress', 0)
            created = job.get('created_at', '')
            print(f"  {job['job_id'][:8]}... | {stage} | {progress}% | created: {created}")
    elif active_jobs is not None:
        print("  No active jobs")
    else:
        print("  \033[91mFailed to connect to database\033[0m")
    print()
    
    # Check recent logs
    print("\033[1m📝 Recent Logs (last 20 entries)\033[0m")
    print("-" * 80)
    recent_logs = await get_recent_logs(20)
    for log_line in recent_logs:
        print(f"  {log_line}")
    print()
    
    print("=" * 80)
    print(f"Updated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("\033[1mWorker Status:\033[0m")
    print("  To start worker: ./scripts/start_worker.sh")
    print("  To check if running: ps aux | grep worker.py")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)

