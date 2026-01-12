#!/usr/bin/env python3
"""
Background cache refresh module
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from google.cloud.firestore_v1.base_query import FieldFilter
from .cache_manager import is_cache_fresh, refresh_project_cache, mark_projects_hidden_in_cache

# Import services needed for fetching projects
from .services.respondent_service import create_respondent_session, verify_respondent_authentication, get_profile_id_from_user_profiles
from .services.project_service import fetch_all_respondent_projects, hide_project_via_api
from .services.user_service import get_email_by_user_id, update_session_key_status, load_user_config, load_user_filters
from .services.filter_service import should_hide_project
from .preference_learner import record_project_hidden

# Create logger for this module
logger = logging.getLogger(__name__)


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
        from .db import projects_cache_collection, session_keys_collection
        
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
                
                if not cookies.get('respondent.session.sid'):
                    logger.warning(f"[Background Refresh] Missing session keys for user {user_id}{email_str}, skipping")
                    continue
                
                # Get profile_id from user_profiles collection (avoid extra API call)
                profile_id = get_profile_id_from_user_profiles(str(user_id))
                if not profile_id:
                    logger.warning(f"[Background Refresh] No profile_id found in user_profiles for user {user_id}{email_str}, skipping")
                    error_count += 1
                    continue
                
                # Verify session is still valid before fetching projects
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
        from .db import session_keys_collection
        
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
                    # Update session key status - valid
                    update_session_key_status(user_id, True)
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


def refresh_user_cache(user_id: str) -> Dict[str, Any]:
    """
    Refresh a single user's project cache by fetching fresh data from Respondent.io API
    and processing with filtering/AI-based hiding logic.
    
    This function:
    - Fetches all projects from Respondent.io API (bypassing cache)
    - Applies user filters and AI-based hiding if enabled
    - Updates the cache with fresh data
    
    Args:
        user_id: User ID to refresh cache for
        
    Returns:
        Dictionary with 'success' (bool) and 'error' (str, optional) keys
    """
    try:
        # Import collections from db module
        from .db import session_keys_collection, projects_cache_collection, hidden_projects_log_collection, user_preferences_collection, project_details_collection, ai_analysis_cache_collection
        
        if session_keys_collection is None:
            return {'success': False, 'error': 'session_keys_collection not available'}
        
        # Get user email for logging
        user_email = None
        try:
            user_email = get_email_by_user_id(str(user_id))
        except Exception:
            pass  # If we can't get email, just continue without it
        
        email_str = f" ({user_email})" if user_email else ""
        
        logger.info(f"[Cache Refresh] Starting refresh for user {user_id}{email_str}")
        
        # Get user's session keys
        query = session_keys_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if not docs:
            logger.warning(f"[Cache Refresh] No session keys found for user {user_id}{email_str}, skipping")
            return {'success': False, 'error': 'No session keys found'}
        
        config_doc = docs[0].to_dict()
        cookies = config_doc.get('cookies', {})
        
        # Check if session is valid - skip if is_valid is False
        if config_doc.get('is_valid') is False:
            logger.info(f"[Cache Refresh] Skipping user {user_id}{email_str} (session is invalid)")
            return {'success': False, 'error': 'Session is invalid'}
        
        if not cookies.get('respondent.session.sid'):
            logger.warning(f"[Cache Refresh] Missing session keys for user {user_id}{email_str}, skipping")
            return {'success': False, 'error': 'Missing session keys'}
        
        # Get profile_id from user_profiles collection (avoid extra API call)
        profile_id = get_profile_id_from_user_profiles(str(user_id))
        if not profile_id:
            logger.warning(f"[Cache Refresh] No profile_id found in user_profiles for user {user_id}{email_str}, skipping")
            return {'success': False, 'error': 'Profile ID not found'}
        
        # Verify session is still valid before fetching projects
        logger.debug(f"[Cache Refresh] Verifying session for user {user_id}{email_str} before refresh...")
        verification = verify_respondent_authentication(cookies)
        if not verification.get('success'):
            logger.warning(f"[Cache Refresh] Session invalid for user {user_id}{email_str}: {verification.get('message', 'Unknown error')}")
            return {'success': False, 'error': f"Session invalid: {verification.get('message', 'Unknown error')}"}
        
        # Create authenticated session
        req_session = create_respondent_session(cookies=cookies)
        
        # Fetch all projects (this will bypass cache since use_cache=False)
        logger.debug(f"[Cache Refresh] Fetching projects for user {user_id}{email_str} (profile_id={profile_id})...")
        all_projects, total_count = fetch_all_respondent_projects(
            session=req_session,
            profile_id=profile_id,
            page_size=50,
            user_id=str(user_id),
            use_cache=False,  # Force fresh fetch
            cookies=cookies
        )
        
        if not all_projects or len(all_projects) == 0:
            logger.warning(f"[Cache Refresh] No projects fetched for user {user_id}{email_str}")
            # Still update cache with empty list
            if projects_cache_collection is not None:
                refresh_project_cache(
                    projects_cache_collection,
                    str(user_id),
                    [],
                    0
                )
            return {'success': True, 'error': None}
        
        # Load user filters
        filters = load_user_filters(str(user_id))
        hide_using_ai = filters.get('hide_using_ai', False)
        hidden_count = 0
        hidden_project_ids = []
        errors = []
        
        # Check if AI-based hiding is enabled and hide matching projects
        if hide_using_ai:
            logger.info(f"[Cache Refresh] AI-based hiding is enabled, checking {len(all_projects)} projects")
            
            # Find projects that should be hidden based on AI preferences
            projects_to_hide = []
            for project in all_projects:
                if should_hide_project(
                    project,
                    filters,
                    project_details_collection=project_details_collection,
                    user_id=str(user_id),
                    user_preferences_collection=user_preferences_collection,
                    ai_analysis_cache_collection=ai_analysis_cache_collection
                ):
                    projects_to_hide.append(project)
            
            logger.info(f"[Cache Refresh] Found {len(projects_to_hide)} projects to hide based on AI preferences")
            
            # Hide each project via API
            for project in projects_to_hide:
                project_id = project.get('id')
                if project_id:
                    try:
                        success = hide_project_via_api(req_session, project_id)
                        if success:
                            hidden_count += 1
                            hidden_project_ids.append(project_id)
                            
                            # Log the hidden project
                            if hidden_projects_log_collection is not None and user_preferences_collection is not None:
                                record_project_hidden(
                                    hidden_projects_log_collection,
                                    user_preferences_collection,
                                    str(user_id),
                                    project_id,
                                    feedback_text=None,
                                    hidden_method='ai_auto'
                                )
                        else:
                            errors.append(project_id)
                            logger.warning(f"[Cache Refresh] Failed to hide project {project_id}")
                    except Exception as e:
                        errors.append(project_id)
                        logger.error(f"[Cache Refresh] Error hiding project {project_id}: {e}", exc_info=True)
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.1)
            
            # Update cache to mark projects as hidden
            if projects_cache_collection is not None and hidden_project_ids:
                mark_projects_hidden_in_cache(projects_cache_collection, str(user_id), hidden_project_ids)
                logger.info(f"[Cache Refresh] Marked {len(hidden_project_ids)} projects as hidden in cache")
            
            # Refresh cache from API to get updated project list after hiding
            if projects_cache_collection is not None and hidden_project_ids:
                try:
                    logger.info(f"[Cache Refresh] Refreshing cache after hiding {len(hidden_project_ids)} projects")
                    all_projects, total_count = fetch_all_respondent_projects(
                        session=req_session,
                        profile_id=profile_id,
                        page_size=50,
                        user_id=str(user_id),
                        use_cache=False,
                        cookies=cookies
                    )
                    logger.info(f"[Cache Refresh] Cache refreshed: {len(all_projects)} projects now in cache")
                except Exception as e:
                    logger.error(f"[Cache Refresh] Error refreshing cache after hiding: {e}", exc_info=True)
                    # Don't fail the whole operation if cache refresh fails
        
        # Update cache with fresh data
        if projects_cache_collection is not None:
            refresh_project_cache(
                projects_cache_collection,
                str(user_id),
                all_projects,
                total_count
            )
            logger.info(f"[Cache Refresh] Successfully refreshed cache for user {user_id}{email_str}: {len(all_projects)} projects")
        
        return {'success': True, 'error': None}
        
    except Exception as e:
        logger.error(f"[Cache Refresh] Error refreshing cache for user {user_id}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}

