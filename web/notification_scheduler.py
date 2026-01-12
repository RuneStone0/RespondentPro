#!/usr/bin/env python3
"""
Notification functions for sending email notifications.
These functions are called by Cloud Scheduler via HTTP endpoints.
"""

import logging
import sys

# Import services
try:
    from .services.notification_service import (
        load_notification_preferences, should_send_weekly_notification,
        should_send_token_expiration_notification, get_visible_projects_count,
        mark_weekly_notification_sent, mark_token_expiration_notification_sent
    )
    from .services.email_service import send_weekly_summary_email, send_session_token_expired_email
    from .services.user_service import get_email_by_user_id
except ImportError:
    from services.notification_service import (
        load_notification_preferences, should_send_weekly_notification,
        should_send_token_expiration_notification, get_visible_projects_count,
        mark_weekly_notification_sent, mark_token_expiration_notification_sent
    )
    from services.email_service import send_weekly_summary_email, send_session_token_expired_email
    from services.user_service import get_email_by_user_id

# Create logger for this module
logger = logging.getLogger(__name__)

# Ensure logger is configured properly for Cloud Functions
# If no handlers exist, configure basic logging to stderr
if not logger.handlers and not logging.getLogger().handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
else:
    # Ensure logger propagates to root logger
    logger.propagate = True


def check_and_send_weekly_notifications():
    """
    Check and send weekly project summary notifications
    """
    logger.info("[Notifications] Starting weekly notifications check")
    try:
        # Import collections from db module
        try:
            from .db import users_collection
        except ImportError:
            from db import users_collection
        
        if users_collection is None:
            logger.warning("[Notifications] users_collection is None, skipping weekly notifications")
            return
        
        # Get all users (not just those with notification preferences)
        # This ensures new users get default preferences created
        users = users_collection.stream()
        users_list = list(users)
        user_count = len(users_list)
        logger.info(f"[Notifications] Found {user_count} user(s) to check for weekly notifications")
        
        if user_count == 0:
            logger.info("[Notifications] No users found, skipping weekly notifications")
            return
        
        processed_count = 0
        sent_count = 0
        
        for user_doc in users_list:
            user_id = user_doc.id
            if not user_id:
                logger.warning("[Notifications] Found user document without ID, skipping")
                continue
            
            processed_count += 1
            try:
                # Load preferences (this will auto-create defaults if they don't exist)
                load_notification_preferences(user_id, auto_create=True)
                
                # Check if notification should be sent
                if should_send_weekly_notification(user_id):
                    # Get user email
                    email = get_email_by_user_id(user_id)
                    if not email:
                        logger.warning(f"[Notifications] Skipping user {user_id}: no email found")
                        continue
                    
                    # Get visible projects count
                    project_count = get_visible_projects_count(user_id)
                    
                    # Send email
                    try:
                        send_weekly_summary_email(email, project_count)
                        logger.info(f"[Notifications] Sent weekly summary to {email} ({project_count} projects)")
                        sent_count += 1
                        
                        # Mark as sent
                        mark_weekly_notification_sent(user_id)
                    except Exception as e:
                        logger.error(f"[Notifications] Failed to send weekly summary to {email}: {e}", exc_info=True)
                        # Don't mark as sent if email failed
                else:
                    logger.debug(f"[Notifications] Weekly notification not needed for user {user_id}")
                        
            except Exception as e:
                logger.error(f"[Notifications] Error processing weekly notification for user {user_id}: {e}", exc_info=True)
                # Continue with next user
                continue
        
        logger.info(f"[Notifications] Weekly notifications check completed: {processed_count} users processed, {sent_count} notifications sent")
                
    except Exception as e:
        logger.error(f"[Notifications] Error checking weekly notifications: {e}", exc_info=True)


def check_and_send_token_expiration_notifications():
    """
    Check and send session token expiration notifications
    """
    logger.info("[Notifications] Starting token expiration notifications check")
    try:
        # Import collections from db module
        try:
            from .db import users_collection
        except ImportError:
            from db import users_collection
        
        if users_collection is None:
            logger.warning("[Notifications] users_collection is None, skipping token expiration notifications")
            return
        
        # Get all users (not just those with notification preferences)
        # This ensures new users get default preferences created
        users = users_collection.stream()
        users_list = list(users)
        user_count = len(users_list)
        logger.info(f"[Notifications] Found {user_count} user(s) to check for token expiration notifications")
        
        if user_count == 0:
            logger.info("[Notifications] No users found, skipping token expiration notifications")
            return
        
        processed_count = 0
        sent_count = 0
        
        for user_doc in users_list:
            user_id = user_doc.id
            if not user_id:
                logger.warning("[Notifications] Found user document without ID, skipping")
                continue
            
            processed_count += 1
            try:
                # Load preferences (this will auto-create defaults if they don't exist)
                load_notification_preferences(user_id, auto_create=True)
                
                # Check if notification should be sent
                if should_send_token_expiration_notification(user_id):
                    # Get user email
                    email = get_email_by_user_id(user_id)
                    if not email:
                        logger.warning(f"[Notifications] Skipping user {user_id}: no email found")
                        continue
                    
                    # Send email
                    try:
                        send_session_token_expired_email(email)
                        logger.info(f"[Notifications] Sent token expiration notification to {email}")
                        sent_count += 1
                        
                        # Mark as sent
                        mark_token_expiration_notification_sent(user_id)
                    except Exception as e:
                        logger.error(f"[Notifications] Failed to send token expiration notification to {email}: {e}", exc_info=True)
                        # Don't mark as sent if email failed
                else:
                    logger.debug(f"[Notifications] Token expiration notification not needed for user {user_id}")
                        
            except Exception as e:
                logger.error(f"[Notifications] Error processing token expiration notification for user {user_id}: {e}", exc_info=True)
                # Continue with next user
                continue
        
        logger.info(f"[Notifications] Token expiration notifications check completed: {processed_count} users processed, {sent_count} notifications sent")
                
    except Exception as e:
        logger.error(f"[Notifications] Error checking token expiration notifications: {e}", exc_info=True)
