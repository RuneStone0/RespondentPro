#!/usr/bin/env python3
"""
Scheduled jobs routes for Cloud Scheduler
These endpoints are called by Google Cloud Scheduler to run periodic tasks.
"""

import logging
from flask import Blueprint, jsonify

# Create logger for this module
logger = logging.getLogger(__name__)

# Import the functions that will be called
try:
    from ..cache_refresh import refresh_stale_caches, keep_sessions_alive
    from ..notification_scheduler import (
        check_and_send_weekly_notifications,
        check_and_send_token_expiration_notifications
    )
except ImportError:
    from cache_refresh import refresh_stale_caches, keep_sessions_alive
    from notification_scheduler import (
        check_and_send_weekly_notifications,
        check_and_send_token_expiration_notifications
    )

bp = Blueprint('scheduled_jobs', __name__)


@bp.route('/scheduled/cache-refresh', methods=['GET'])
def scheduled_cache_refresh():
    """
    Refresh stale project caches by fetching fresh data from Respondent.io API.
    Called by Cloud Scheduler daily at 6:00 AM.
    """
    try:
        # Refresh stale caches (default max age: 24 hours)
        refresh_stale_caches(max_age_hours=24)
        logger.info("[Cache Refresh] Scheduled task completed successfully")
        return jsonify({
            'status': 'success',
            'message': 'Cache refresh completed successfully'
        }), 200
    except Exception as e:
        logger.error(f"[Cache Refresh] Error in scheduled task: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@bp.route('/scheduled/session-keepalive', methods=['GET'])
def scheduled_session_keepalive():
    """
    Keep all user sessions alive by verifying authentication with Respondent.io API.
    Called by Cloud Scheduler every 8 hours to prevent session expiration.
    
    Runs verify_respondent_authentication() for each user in background threads,
    allowing the endpoint to return immediately while verifications run asynchronously.
    """
    try:
        # Keep all sessions alive by verifying authentication (runs in background threads)
        keep_sessions_alive()
        logger.info("[Session Keep-Alive] Scheduled task started - background verifications running")
        return jsonify({
            'status': 'success',
            'message': 'Session keep-alive tasks started in background'
        }), 200
    except Exception as e:
        logger.error(f"[Session Keep-Alive] Error in scheduled task: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@bp.route('/scheduled/notifications', methods=['GET'])
def scheduled_notifications():
    """
    Check and send weekly project summary notifications and token expiration notifications.
    Called by Cloud Scheduler every Friday morning at 9:00 AM.
    """
    try:
        # Check weekly notifications
        check_and_send_weekly_notifications()
        
        # Check token expiration notifications
        check_and_send_token_expiration_notifications()
        
        logger.info("[Notifications] Scheduled task completed successfully")
        return jsonify({
            'status': 'success',
            'message': 'Notifications check completed successfully'
        }), 200
    except Exception as e:
        logger.error(f"[Notifications] Error in scheduled task: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
