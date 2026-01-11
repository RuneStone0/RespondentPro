"""
Cloud Function for scheduled session keep-alive
Automatically scheduled by Firebase (runs every 8 hours)
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
from web.cache_refresh import keep_sessions_alive

# Create logger for this module
logger = logging.getLogger(__name__)


@scheduler_fn.on_schedule(schedule="0 */8 * * *", timezone="America/New_York")
def scheduled_session_keepalive(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Keep all user sessions alive by checking Respondent.io profile endpoints.
    Runs every 8 hours to prevent session expiration.
    """
    try:
        # Keep all sessions alive by checking profile endpoints
        keep_sessions_alive()
        logger.info("[Session Keep-Alive] Scheduled task completed successfully")
    except Exception as e:
        logger.error(f"[Session Keep-Alive] Error in scheduled task: {e}", exc_info=True)
        raise
