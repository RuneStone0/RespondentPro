#!/usr/bin/env python3
"""
Notification service for managing user notification preferences and sending notifications
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from google.cloud.firestore_v1.base_query import FieldFilter

# Create logger for this module
logger = logging.getLogger(__name__)

# Import database collections
try:
    from ..db import user_notifications_collection, projects_cache_collection, hidden_projects_log_collection, session_keys_collection
except ImportError:
    from web.db import user_notifications_collection, projects_cache_collection, hidden_projects_log_collection, session_keys_collection

# Import services
try:
    from .user_service import load_user_config, get_email_by_user_id
    from .respondent_auth_service import verify_respondent_authentication, create_respondent_session
    from .project_service import fetch_all_respondent_projects
    from ..cache_manager import get_cached_projects, is_cache_fresh
    from ..hidden_projects_tracker import is_project_hidden
except ImportError:
    from services.user_service import load_user_config, get_email_by_user_id
    from services.respondent_auth_service import verify_respondent_authentication, create_respondent_session
    from services.project_service import fetch_all_respondent_projects
    from cache_manager import get_cached_projects, is_cache_fresh
    from hidden_projects_tracker import is_project_hidden


def get_default_notification_preferences() -> Dict[str, Any]:
    """Get default notification preferences"""
    return {
        'weekly_project_summary': {
            'enabled': True,
            'day_of_week': 0,  # Sunday
            'last_sent': None
        },
        'session_token_expired': {
            'enabled': True,
            'last_sent': None
        }
    }


def load_notification_preferences(user_id: str, auto_create: bool = True) -> Dict[str, Any]:
    """
    Load user's notification preferences with defaults
    
    Args:
        user_id: User ID
        auto_create: If True, automatically create default preferences if they don't exist
        
    Returns:
        Dictionary with notification preferences
    """
    if user_notifications_collection is None:
        return get_default_notification_preferences()
    
    try:
        query = user_notifications_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if docs:
            prefs_doc = docs[0].to_dict()
            if 'notifications' in prefs_doc:
                # Merge with defaults to ensure all fields exist
                default_prefs = get_default_notification_preferences()
                notifications = prefs_doc['notifications']
            
            # Merge weekly_project_summary
            weekly = default_prefs['weekly_project_summary'].copy()
            if 'weekly_project_summary' in notifications:
                weekly.update(notifications['weekly_project_summary'])
            
            # Merge session_token_expired
            token_expired = default_prefs['session_token_expired'].copy()
            if 'session_token_expired' in notifications:
                token_expired.update(notifications['session_token_expired'])
            
            return {
                'weekly_project_summary': weekly,
                'session_token_expired': token_expired
            }
        
        # No preferences found - create defaults if auto_create is True
        if auto_create:
            default_prefs = get_default_notification_preferences()
            try:
                save_notification_preferences(user_id, default_prefs)
                logger.info(f"[Notifications] Created default preferences for user {user_id}")
            except Exception as save_error:
                logger.warning(f"[Notifications] Failed to auto-create preferences for user {user_id}: {save_error}")
        
        return get_default_notification_preferences()
    except Exception as e:
        logger.error(f"Error loading notification preferences: {e}", exc_info=True)
        return get_default_notification_preferences()


def save_notification_preferences(user_id: str, preferences: Dict[str, Any]) -> bool:
    """
    Save user's notification preferences
    
    Args:
        user_id: User ID
        preferences: Dictionary with notification preferences
        
    Returns:
        True if successful, False otherwise
    """
    if user_notifications_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    
    try:
        # Ensure we have the proper structure
        notifications = {
            'weekly_project_summary': preferences.get('weekly_project_summary', {}),
            'session_token_expired': preferences.get('session_token_expired', {})
        }
        
        # Find existing document or create new one
        query = user_notifications_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        
        update_data = {
            'user_id': str(user_id),
            'notifications': notifications,
            'updated_at': datetime.now(timezone.utc)
        }
        
        if docs:
            # Update existing document
            docs[0].reference.update(update_data)
        else:
            # Create new document
            update_data['created_at'] = datetime.now(timezone.utc)
            user_notifications_collection.add(update_data)
        
        return True
    except Exception as e:
        raise Exception(f"Failed to save notification preferences: {e}")


def get_visible_projects_count(user_id: str) -> int:
    """
    Count projects that aren't hidden for a user
    
    Args:
        user_id: User ID
        
    Returns:
        Count of visible projects (not hidden)
    """
    try:
        # Get user config to check if they have session keys
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            # User doesn't have credentials configured
            return 0
        
        # Try to get projects from cache first
        all_projects = []
        if projects_cache_collection is not None:
            cached = get_cached_projects(projects_cache_collection, user_id)
            if cached and cached.get('projects'):
                all_projects = cached['projects']
        
        # If no cache or cache is stale, try to fetch from API
        if not all_projects:
            try:
                # Verify authentication first
                verification = verify_respondent_authentication(
                    cookies=config.get('cookies', {})
                )
                
                if not verification.get('success'):
                    # Can't authenticate, return 0
                    return 0
                
                profile_id = verification.get('profile_id')
                if not profile_id:
                    return 0
                
                # Create session and fetch projects
                req_session = create_respondent_session(
                    cookies=config.get('cookies', {})
                )
                
                all_projects, _ = fetch_all_respondent_projects(
                    session=req_session,
                    profile_id=profile_id,
                    page_size=50,
                    user_id=user_id,
                    use_cache=True,
                    cookies=config.get('cookies', {})
                )
            except Exception as e:
                logger.error(f"Error fetching projects for notification count: {e}", exc_info=True)
                # If we can't fetch, return 0
                return 0
        
        # Filter out hidden projects
        if not all_projects:
            return 0
        
        visible_count = 0
        if hidden_projects_log_collection is not None:
            for project in all_projects:
                project_id = project.get('id')
                if project_id:
                    if not is_project_hidden(hidden_projects_log_collection, user_id, str(project_id)):
                        visible_count += 1
        else:
            # If we can't check hidden projects, return total count
            visible_count = len(all_projects)
        
        return visible_count
    except Exception as e:
        logger.error(f"Error getting visible projects count: {e}", exc_info=True)
        return 0


def check_session_token_validity(user_id: str) -> bool:
    """
    Verify session token validity
    
    Args:
        user_id: User ID
        
    Returns:
        True if token is valid, False otherwise
    """
    try:
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            # No credentials configured
            return False
        
        # Verify authentication
        verification = verify_respondent_authentication(
            cookies=config.get('cookies', {})
        )
        
        return verification.get('success', False)
    except Exception as e:
        logger.error(f"Error checking session token validity: {e}", exc_info=True)
        return False


def should_send_weekly_notification(user_id: str) -> bool:
    """
    Check if weekly notification should be sent today
    
    Args:
        user_id: User ID
        
    Returns:
        True if notification should be sent, False otherwise
    """
    try:
        prefs = load_notification_preferences(user_id)
        weekly_prefs = prefs.get('weekly_project_summary', {})
        
        if not weekly_prefs.get('enabled', True):
            return False
        
        # Check if today matches the selected day of week
        # weekday() returns Monday=0, Sunday=6
        # Our day_of_week uses Sunday=0, Monday=1, ..., Saturday=6
        today_weekday = datetime.now(timezone.utc).weekday()  # Monday=0, Sunday=6
        selected_day = weekly_prefs.get('day_of_week', 0)
        
        # Convert selected_day (Sunday=0) to weekday format (Monday=0, Sunday=6)
        # selected_day: 0=Sunday, 1=Monday, ..., 6=Saturday
        # weekday(): 0=Monday, 1=Tuesday, ..., 6=Sunday
        if selected_day == 0:  # Sunday -> weekday() = 6
            selected_weekday = 6
        else:  # Monday=1 -> weekday()=0, Tuesday=2 -> weekday()=1, etc.
            selected_weekday = selected_day - 1
        
        if today_weekday != selected_weekday:
            return False
        
        # Check if notification was already sent this week
        last_sent = weekly_prefs.get('last_sent')
        if last_sent:
            if isinstance(last_sent, str):
                # Parse string datetime
                try:
                    last_sent = datetime.fromisoformat(last_sent.replace('Z', '+00:00'))
                except:
                    last_sent = None
            
            if last_sent and isinstance(last_sent, datetime):
                # Check if last_sent was within the last 7 days
                # Ensure both datetimes are timezone-aware
                now = datetime.now(timezone.utc)
                if last_sent.tzinfo is None:
                    # If last_sent is naive, assume it's UTC
                    last_sent = last_sent.replace(tzinfo=timezone.utc)
                days_since_sent = (now - last_sent).days
                if days_since_sent < 7:
                    return False
        
        return True
    except Exception as e:
        logger.error(f"Error checking if weekly notification should be sent: {e}", exc_info=True)
        return False


def mark_weekly_notification_sent(user_id: str) -> bool:
    """
    Mark weekly notification as sent
    
    Args:
        user_id: User ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        prefs = load_notification_preferences(user_id)
        prefs['weekly_project_summary']['last_sent'] = datetime.now(timezone.utc)
        return save_notification_preferences(user_id, prefs)
    except Exception as e:
        logger.error(f"Error marking weekly notification as sent: {e}", exc_info=True)
        return False


def should_send_token_expiration_notification(user_id: str) -> bool:
    """
    Check if token expiration notification should be sent
    
    Args:
        user_id: User ID
        
    Returns:
        True if notification should be sent, False otherwise
    """
    try:
        prefs = load_notification_preferences(user_id)
        token_prefs = prefs.get('session_token_expired', {})
        
        if not token_prefs.get('enabled', True):
            return False
        
        # Check if token is invalid
        if check_session_token_validity(user_id):
            # Token is valid, don't send notification
            return False
        
        # Token is invalid, check if we've sent notification recently (within 24 hours)
        last_sent = token_prefs.get('last_sent')
        if last_sent:
            if isinstance(last_sent, str):
                try:
                    last_sent = datetime.fromisoformat(last_sent.replace('Z', '+00:00'))
                except:
                    last_sent = None
            
            if last_sent and isinstance(last_sent, datetime):
                # Ensure both datetimes are timezone-aware
                now = datetime.now(timezone.utc)
                if last_sent.tzinfo is None:
                    # If last_sent is naive, assume it's UTC
                    last_sent = last_sent.replace(tzinfo=timezone.utc)
                hours_since_sent = (now - last_sent).total_seconds() / 3600
                if hours_since_sent < 24:
                    # Already sent within 24 hours, don't send again
                    return False
        
        return True
    except Exception as e:
        logger.error(f"Error checking if token expiration notification should be sent: {e}", exc_info=True)
        return False


def mark_token_expiration_notification_sent(user_id: str) -> bool:
    """
    Mark token expiration notification as sent
    
    Args:
        user_id: User ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        prefs = load_notification_preferences(user_id)
        prefs['session_token_expired']['last_sent'] = datetime.now(timezone.utc)
        return save_notification_preferences(user_id, prefs)
    except Exception as e:
        logger.error(f"Error marking token expiration notification as sent: {e}", exc_info=True)
        return False
