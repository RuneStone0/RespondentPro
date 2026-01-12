#!/usr/bin/env python3
"""
Background cache refresh module
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from google.cloud.firestore_v1.base_query import FieldFilter
from .cache_manager import is_cache_fresh, refresh_project_cache
from .ai_analyzer import analyze_projects_batch

# Import services needed for fetching projects
try:
    from .services.respondent_service import create_respondent_session, verify_respondent_authentication
    from .services.project_service import fetch_all_respondent_projects
    from .services.user_service import get_email_by_user_id, update_session_key_status
except ImportError:
    from services.respondent_service import create_respondent_session, verify_respondent_authentication
    from services.project_service import fetch_all_respondent_projects
    from services.user_service import get_email_by_user_id, update_session_key_status

# Create logger for this module
logger = logging.getLogger(__name__)

# Ensure logger is configured properly for Cloud Functions
# If no handlers exist, configure basic logging to stderr
if not logger.handlers and not logging.getLogger().handlers:
    import sys
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
else:
    # Ensure logger propagates to root logger
    logger.propagate = True
    # Set level to INFO to ensure messages are visible
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)


def start_background_refresh(
    check_interval_hours: int = 1,
    cache_max_age_hours: int = 24
):
    """
    Start background thread to refresh caches
    
    Args:
        check_interval_hours: How often to check for stale caches (default: 1 hour)
        cache_max_age_hours: Maximum age of cache before refresh (default: 24 hours)
    """
    def refresh_loop():
        while True:
            try:
                refresh_stale_caches(cache_max_age_hours)
            except Exception as e:
                logger.error(f"Error in background cache refresh: {e}", exc_info=True)
            
            # Sleep for check_interval_hours
            time.sleep(check_interval_hours * 3600)
    
    thread = threading.Thread(target=refresh_loop, daemon=True)
    thread.start()
    return thread


def refresh_stale_caches(max_age_hours: int = 24):
    """
    Refresh all stale caches by fetching projects from Respondent.io API
    
    Args:
        max_age_hours: Maximum age of cache before refresh
    """
    try:
        # Import collections from db module
        try:
            from .db import projects_cache_collection, session_keys_collection
        except ImportError:
            from db import projects_cache_collection, session_keys_collection
        
        if projects_cache_collection is None or session_keys_collection is None:
            return
        
        # Get all cached users
        cached_users = projects_cache_collection.stream()
        
        # Convert to list to get count and allow iteration
        cached_users_list = list(cached_users)
        total_users = len(cached_users_list)
        
        logger.info(f"[Background Refresh] Found {total_users} cached user(s) to check")
        
        refreshed_count = 0
        error_count = 0
        skipped_fresh_count = 0
        skipped_no_user_id_count = 0
        
        for cache_doc in cached_users_list:
            cache_data = cache_doc.to_dict()
            user_id = cache_data.get('user_id')
            if not user_id:
                skipped_no_user_id_count += 1
                logger.debug(f"[Background Refresh] Skipping cache entry with no user_id")
                continue
            
            # Get user email for logging
            user_email = None
            try:
                user_email = get_email_by_user_id(str(user_id))
            except Exception:
                pass  # If we can't get email, just continue without it
            
            email_str = f" ({user_email})" if user_email else ""
            
            # Check if cache is stale
            cache_is_fresh = is_cache_fresh(projects_cache_collection, str(user_id), max_age_hours)
            if cache_is_fresh:
                skipped_fresh_count += 1
                logger.debug(f"[Background Refresh] Cache is fresh for user {user_id}{email_str}, skipping refresh")
                continue
            
            logger.info(f"[Background Refresh] Processing user {user_id}{email_str} (cache is stale)")
            try:
                # Get user's session keys
                query = session_keys_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
                docs = list(query)
                if not docs:
                    logger.warning(f"[Background Refresh] No session keys found for user {user_id}{email_str}, skipping")
                    continue
                
                config_doc = docs[0].to_dict()
                cookies = config_doc.get('cookies', {})
                profile_id = config_doc.get('profile_id')
                
                if not cookies.get('respondent.session.sid') or not profile_id:
                    logger.warning(f"[Background Refresh] Missing session keys or profile_id for user {user_id}{email_str}, skipping")
                    continue
                
                # Verify session is still valid
                logger.debug(f"[Background Refresh] Verifying session for user {user_id}{email_str} before refresh...")
                verification = verify_respondent_authentication(cookies)
                if not verification.get('success'):
                    logger.warning(f"[Background Refresh] Session invalid for user {user_id}{email_str}: {verification.get('message', 'Unknown error')}")
                    error_count += 1
                    continue
                
                # Create authenticated session
                req_session = create_respondent_session(cookies=cookies)
                
                # Fetch all projects (this will bypass cache since use_cache=False)
                logger.debug(f"[Background Refresh] Fetching projects for user {user_id}{email_str} (profile_id={profile_id})...")
                all_projects, total_count = fetch_all_respondent_projects(
                    session=req_session,
                    profile_id=profile_id,
                    page_size=50,
                    user_id=str(user_id),
                    use_cache=False,  # Force fresh fetch
                    cookies=cookies
                )
                
                # Update cache with fresh data
                if all_projects and len(all_projects) > 0:
                    refresh_project_cache(
                        projects_cache_collection,
                        str(user_id),
                        all_projects,
                        total_count
                    )
                    logger.info(f"[Background Refresh] Successfully refreshed cache for user {user_id}{email_str}: {len(all_projects)} projects")
                    refreshed_count += 1
                else:
                    logger.warning(f"[Background Refresh] No projects fetched for user {user_id}{email_str}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"[Background Refresh] Error refreshing cache for user {user_id}{email_str}: {e}", exc_info=True)
                error_count += 1
        
        # Log summary
        logger.info(
            f"[Background Refresh] Completed: {total_users} total users, "
            f"{refreshed_count} refreshed, {error_count} errors, "
            f"{skipped_fresh_count} skipped (fresh cache), "
            f"{skipped_no_user_id_count} skipped (no user_id)"
        )
                
    except Exception as e:
        logger.error(f"[Background Refresh] Error in refresh_stale_caches: {e}", exc_info=True)


def keep_sessions_alive():
    """
    Keep all user sessions alive by verifying authentication with Respondent.io API.
    This prevents session cookies from expiring due to inactivity.
    
    Runs verify_respondent_authentication() for each user in background threads,
    allowing the endpoint to return immediately while verifications run asynchronously.
    """
    try:
        logger.info("[Session Keep-Alive] Starting session keep-alive process...")
        
        # Import collections from db module
        try:
            from .db import session_keys_collection
        except ImportError:
            from db import session_keys_collection
        
        if session_keys_collection is None:
            logger.warning("[Session Keep-Alive] session_keys_collection not available, skipping")
            return
        
        # Get all users with session keys
        logger.info("[Session Keep-Alive] Fetching all user sessions from database...")
        all_sessions = session_keys_collection.stream()
        
        started_count = 0
        skipped_count = 0
        
        def verify_user_background(user_id, cookies):
            """Background task to verify a single user's authentication"""
            try:
                logger.info(f"[Session Keep-Alive] [Background] Starting verification for user {user_id}...")
                verification = verify_respondent_authentication(cookies)
                
                if verification.get('success'):
                    logger.info(f"[Session Keep-Alive] [Background] ✓ Session alive for user {user_id}")
                    # Update session key status - valid, with profile_id if available
                    update_session_key_status(
                        user_id, 
                        True, 
                        profile_id=verification.get('profile_id')
                    )
                else:
                    error_msg = verification.get('message', 'Unknown error')
                    logger.warning(f"[Session Keep-Alive] [Background] ✗ Session expired for user {user_id}: {error_msg}")
                    # Update session key status - invalid
                    update_session_key_status(user_id, False)
                    
            except Exception as e:
                logger.error(f"[Session Keep-Alive] [Background] Error verifying user {user_id}: {e}", exc_info=True)
                # Mark as invalid if there was an error
                try:
                    update_session_key_status(user_id, False)
                except Exception as update_error:
                    logger.error(f"[Session Keep-Alive] [Background] Error updating status for user {user_id}: {update_error}", exc_info=True)
        
        for session_doc in all_sessions:
            session_data = session_doc.to_dict()
            user_id = session_data.get('user_id')
            cookies = session_data.get('cookies', {})
            
            # Skip if missing required fields
            if not user_id or not cookies.get('respondent.session.sid'):
                skipped_count += 1
                logger.debug(f"[Session Keep-Alive] Skipping session for user {user_id} (missing user_id or session cookie)")
                continue
            
            # Skip invalid sessions (only skip if explicitly False, not if None/unknown)
            if session_data.get('is_valid') is False:
                skipped_count += 1
                logger.debug(f"[Session Keep-Alive] Skipping invalid session for user {user_id}")
                continue
            
            # Start background thread for this user's verification
            thread = threading.Thread(target=verify_user_background, args=(user_id, cookies))
            thread.daemon = True
            thread.start()
            started_count += 1
            logger.info(f"[Session Keep-Alive] Started background verification task for user {user_id} (task {started_count})")
        
        # Log summary of started tasks
        total = started_count + skipped_count
        if total > 0:
            logger.info(f"[Session Keep-Alive] Summary: Started {started_count} background verification task(s), {skipped_count} skipped (total: {total} sessions found)")
        else:
            logger.info("[Session Keep-Alive] No user sessions found in database")
                
    except Exception as e:
        logger.error(f"[Session Keep-Alive] Error in keep_sessions_alive: {e}", exc_info=True)

