#!/usr/bin/env python3
"""
Scheduled jobs routes for Cloud Scheduler
These endpoints are called by Google Cloud Scheduler to run periodic tasks.
"""

import logging
import sys
import threading
from flask import Blueprint, jsonify
from google.cloud.firestore_v1.base_query import FieldFilter

# Create logger for this module
logger = logging.getLogger(__name__)

# Import the functions that will be called
try:
    from ..cache_refresh import refresh_stale_caches, keep_sessions_alive, refresh_user_cache
    from ..notification_scheduler import (
        check_and_send_weekly_notifications,
        check_and_send_token_expiration_notifications
    )
    from ..db import users_collection, session_keys_collection
    from ..services.user_service import get_email_by_user_id
except ImportError:
    from cache_refresh import refresh_stale_caches, keep_sessions_alive, refresh_user_cache
    from notification_scheduler import (
        check_and_send_weekly_notifications,
        check_and_send_token_expiration_notifications
    )
    from db import users_collection, session_keys_collection
    from services.user_service import get_email_by_user_id

bp = Blueprint('scheduled_jobs', __name__)


@bp.route('/scheduled/cache-refresh', methods=['GET'])
def scheduled_cache_refresh():
    """
    Refresh all users' project caches by fetching fresh data from Respondent.io API
    and processing with filtering/AI-based hiding logic.
    Called by Cloud Scheduler on a regular cadence.
    
    Runs refresh_user_cache() for each user in background threads,
    allowing the endpoint to return immediately while refreshes run asynchronously.
    Skips users where session_keys.is_valid is False.
    """
    try:
        logger.info("[Cache Refresh] Starting scheduled cache refresh for all users...")
        
        if users_collection is None:
            logger.warning("[Cache Refresh] users_collection not available, skipping")
            return jsonify({
                'status': 'error',
                'message': 'users_collection not available'
            }), 500
        
        if session_keys_collection is None:
            logger.warning("[Cache Refresh] session_keys_collection not available, skipping")
            return jsonify({
                'status': 'error',
                'message': 'session_keys_collection not available'
            }), 500
        
        # Get all users
        logger.info("[Cache Refresh] Fetching all users from database...")
        all_users = users_collection.stream()
        users_list = list(all_users)
        total_users = len(users_list)
        
        logger.info(f"[Cache Refresh] Found {total_users} user(s) to process")
        
        if total_users == 0:
            logger.info("[Cache Refresh] No users found, skipping")
            return jsonify({
                'status': 'success',
                'message': 'No users found to refresh'
            }), 200
        
        started_count = 0
        skipped_count = 0
        skip_reasons = {
            'no_session_keys': 0,
            'invalid_session': 0,
            'error_processing': 0
        }
        
        def refresh_user_background(user_id):
            """Background task to refresh a single user's cache"""
            try:
                logger.info(f"[Cache Refresh] [Background] Starting refresh for user {user_id}...")
                result = refresh_user_cache(user_id)
                if result.get('success'):
                    logger.info(f"[Cache Refresh] [Background] ✓ Successfully refreshed cache for user {user_id}")
                else:
                    error_msg = result.get('error', 'Unknown error')
                    logger.warning(f"[Cache Refresh] [Background] ✗ Failed to refresh cache for user {user_id}: {error_msg}")
            except Exception as e:
                logger.error(f"[Cache Refresh] [Background] Error refreshing cache for user {user_id}: {e}", exc_info=True)
        
        for user_doc in users_list:
            try:
                user_data = user_doc.to_dict()
                # Get Firebase Auth UID - for new users, document ID is the firebase_uid
                # For old users, firebase_uid is stored in the document
                firebase_uid = user_data.get('firebase_uid') or user_doc.id
                user_id = str(firebase_uid)
                
                # Get user email for logging
                user_email = None
                try:
                    user_email = get_email_by_user_id(user_id)
                except Exception:
                    pass  # If we can't get email, just continue without it
                
                email_str = f" ({user_email})" if user_email else ""
                
                # Check session_keys to see if session is valid
                session_query = session_keys_collection.where(filter=FieldFilter('user_id', '==', user_id)).limit(1).stream()
                session_docs = list(session_query)
                
                if not session_docs:
                    skipped_count += 1
                    skip_reasons['no_session_keys'] += 1
                    logger.info(f"[Cache Refresh] Skipping user {user_id}{email_str} - no session keys found")
                    continue
                
                session_data = session_docs[0].to_dict()
                
                # Skip if is_valid is False
                if session_data.get('is_valid') is False:
                    skipped_count += 1
                    skip_reasons['invalid_session'] += 1
                    logger.info(f"[Cache Refresh] Skipping user {user_id}{email_str} - session is invalid (is_valid=False)")
                    continue
                
                # Start background thread for this user's refresh
                thread = threading.Thread(target=refresh_user_background, args=(user_id,))
                thread.daemon = True
                thread.start()
                started_count += 1
                logger.info(f"[Cache Refresh] Started background refresh task for user {user_id}{email_str} (task {started_count})")
                
            except Exception as e:
                logger.error(f"[Cache Refresh] Error processing user {user_doc.id}: {e}", exc_info=True)
                skipped_count += 1
                skip_reasons['error_processing'] += 1
        
        # Log summary of started tasks with skip reasons
        skip_reasons_str = ", ".join([f"{count} {reason.replace('_', ' ')}" for reason, count in skip_reasons.items() if count > 0])
        if skip_reasons_str:
            logger.info(f"[Cache Refresh] Summary: Started {started_count} background refresh task(s), {skipped_count} skipped ({skip_reasons_str}) (total: {total_users} users found)")
        else:
            logger.info(f"[Cache Refresh] Summary: Started {started_count} background refresh task(s), {skipped_count} skipped (total: {total_users} users found)")
        
        return jsonify({
            'status': 'success',
            'message': f'Cache refresh started in background for {started_count} user(s), {skipped_count} skipped',
            'started': started_count,
            'skipped': skipped_count,
            'total': total_users
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
    logger.info("[Notifications] /scheduled/notifications endpoint called")
    try:
        # Check weekly notifications
        logger.info("[Notifications] Calling check_and_send_weekly_notifications()")
        check_and_send_weekly_notifications()
        
        # Check token expiration notifications
        logger.info("[Notifications] Calling check_and_send_token_expiration_notifications()")
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
