"""
Cloud Function for scheduled test function
Automatically scheduled by Firebase (runs every 1 minute)
"""
# The Cloud Functions for Firebase SDK to set up triggers and logging.
from firebase_functions import scheduler_fn

# The Firebase Admin SDK to delete users.
import firebase_admin
from firebase_admin import auth

firebase_admin.initialize_app()

import logging

# Create logger for this module
logger = logging.getLogger(__name__)

@scheduler_fn.on_schedule(schedule="*/1 * * * *", timezone="America/New_York")
def test_scheduled_function(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Test scheduled function that runs every 1 minute.
    Logs a simple message to verify the scheduler is working.
    """
    try:
        logger.info("Hello from scheduled function")
    except Exception as e:
        logger.error(f"[Test Scheduled Function] Error in scheduled task: {e}", exc_info=True)
        raise

@scheduler_fn.on_schedule(schedule="every day 00:00")
def accountcleanup(event: scheduler_fn.ScheduledEvent) -> None:
    """Delete users who've been inactive for 30 days or more."""
    try:
        logger.info("[accountcleanup] Hello from scheduled function")
    except Exception as e:
        logger.error(f"[accountcleanup] Error in scheduled task: {e}", exc_info=True)
        raise
