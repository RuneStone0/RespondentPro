#!/usr/bin/env python3
"""
Background notification scheduler for sending email notifications
"""

import threading
import time
import logging
from datetime import datetime

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


def start_notification_scheduler(check_interval_hours: int = 1, token_check_interval_hours: int = 12):
    """
    Start background thread to send notifications
    
    Args:
        check_interval_hours: How often to check for weekly notifications (default: 1 hour)
        token_check_interval_hours: How often to check for token expiration (default: 12 hours)
    """
    last_token_check = datetime.utcnow()
    
    def notification_loop():
        nonlocal last_token_check
        while True:
            try:
                # Always check weekly notifications
                check_and_send_weekly_notifications()
                
                # Check token expiration only if enough time has passed
                time_since_last_token_check = (datetime.utcnow() - last_token_check).total_seconds() / 3600
                if time_since_last_token_check >= token_check_interval_hours:
                    check_and_send_token_expiration_notifications()
                    last_token_check = datetime.utcnow()
            except Exception as e:
                logger.error(f"Error in notification scheduler: {e}", exc_info=True)
            
            # Sleep for check_interval_hours
            time.sleep(check_interval_hours * 3600)
    
    thread = threading.Thread(target=notification_loop, daemon=True)
    thread.start()
    return thread


def check_and_send_weekly_notifications():
    """
    Check and send weekly project summary notifications
    """
    try:
        # Import collections from db module
        try:
            from .db import users_collection
        except ImportError:
            from db import users_collection
        
        if users_collection is None:
            return
        
        # Get all users (not just those with notification preferences)
        # This ensures new users get default preferences created
        users = users_collection.stream()
        
        for user_doc in users:
            user_id = user_doc.id
            if not user_id:
                continue
            
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
                        
                        # Mark as sent
                        mark_weekly_notification_sent(user_id)
                    except Exception as e:
                        logger.error(f"[Notifications] Failed to send weekly summary to {email}: {e}", exc_info=True)
                        # Don't mark as sent if email failed
                        
            except Exception as e:
                logger.error(f"[Notifications] Error processing weekly notification for user {user_id}: {e}", exc_info=True)
                # Continue with next user
                continue
                
    except Exception as e:
        logger.error(f"[Notifications] Error checking weekly notifications: {e}", exc_info=True)


def check_and_send_token_expiration_notifications():
    """
    Check and send session token expiration notifications
    """
    try:
        # Import collections from db module
        try:
            from .db import users_collection
        except ImportError:
            from db import users_collection
        
        if users_collection is None:
            return
        
        # Get all users (not just those with notification preferences)
        # This ensures new users get default preferences created
        users = users_collection.stream()
        
        for user_doc in users:
            user_id = user_doc.id
            if not user_id:
                continue
            
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
                        
                        # Mark as sent
                        mark_token_expiration_notification_sent(user_id)
                    except Exception as e:
                        logger.error(f"[Notifications] Failed to send token expiration notification to {email}: {e}", exc_info=True)
                        # Don't mark as sent if email failed
                        
            except Exception as e:
                logger.error(f"[Notifications] Error processing token expiration notification for user {user_id}: {e}", exc_info=True)
                # Continue with next user
                continue
                
    except Exception as e:
        logger.error(f"[Notifications] Error checking token expiration notifications: {e}", exc_info=True)
