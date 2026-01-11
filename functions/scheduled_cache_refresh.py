"""
Cloud Function for scheduled cache refresh
Automatically scheduled by Firebase (runs daily at 6:00 AM)
"""

import logging

# Initialize Firebase Admin (if not already initialized)
import firebase_admin
try:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
except ValueError:
    # Already initialized - this is OK
    pass

from firebase_functions import scheduler_fn
from web.cache_refresh import refresh_stale_caches

# Create logger for this module
logger = logging.getLogger(__name__)


@scheduler_fn.on_schedule(schedule="every day 06:00", timezone="America/New_York")
def scheduled_cache_refresh(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Refresh stale project caches by fetching fresh data from Respondent.io API.
    Runs daily at 6:00 AM to keep caches up to date.
    """
    try:
        # Refresh stale caches (default max age: 24 hours)
        refresh_stale_caches(max_age_hours=24)
        logger.info("[Cache Refresh] Scheduled task completed successfully")
    except Exception as e:
        logger.error(f"[Cache Refresh] Error in scheduled task: {e}", exc_info=True)
        raise
