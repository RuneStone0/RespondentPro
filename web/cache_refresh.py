#!/usr/bin/env python3
"""
Background cache refresh module
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional
from pymongo.collection import Collection
from .cache_manager import is_cache_fresh, refresh_project_cache
from .ai_analyzer import analyze_projects_batch

# Import services needed for fetching projects
try:
    from .services.respondent_auth_service import create_respondent_session, verify_respondent_authentication
    from .services.project_service import fetch_all_respondent_projects
except ImportError:
    from services.respondent_auth_service import create_respondent_session, verify_respondent_authentication
    from services.project_service import fetch_all_respondent_projects


def start_background_refresh(
    db,
    check_interval_hours: int = 1,
    cache_max_age_hours: int = 24
):
    """
    Start background thread to refresh caches
    
    Args:
        db: MongoDB database object
        check_interval_hours: How often to check for stale caches (default: 1 hour)
        cache_max_age_hours: Maximum age of cache before refresh (default: 24 hours)
    """
    def refresh_loop():
        while True:
            try:
                refresh_stale_caches(db, cache_max_age_hours)
            except Exception as e:
                print(f"Error in background cache refresh: {e}")
            
            # Sleep for check_interval_hours
            time.sleep(check_interval_hours * 3600)
    
    thread = threading.Thread(target=refresh_loop, daemon=True)
    thread.start()
    return thread


def refresh_stale_caches(db, max_age_hours: int = 24):
    """
    Refresh all stale caches by fetching projects from Respondent.io API
    
    Args:
        db: MongoDB database object
        max_age_hours: Maximum age of cache before refresh
    """
    try:
        projects_cache_collection = db['projects_cache']
        session_keys_collection = db['session_keys']
        
        # Get all cached users
        cached_users = projects_cache_collection.find({}, {'user_id': 1, 'cached_at': 1})
        
        refreshed_count = 0
        error_count = 0
        
        for cache_doc in cached_users:
            user_id = cache_doc.get('user_id')
            if not user_id:
                continue
            
            # Check if cache is stale
            if not is_cache_fresh(projects_cache_collection, str(user_id), max_age_hours):
                try:
                    # Get user's session keys
                    config_doc = session_keys_collection.find_one({'user_id': user_id})
                    if not config_doc:
                        print(f"[Background Refresh] No session keys found for user {user_id}, skipping")
                        continue
                    
                    cookies = config_doc.get('cookies', {})
                    profile_id = config_doc.get('profile_id')
                    
                    if not cookies.get('respondent.session.sid') or not profile_id:
                        print(f"[Background Refresh] Missing session keys or profile_id for user {user_id}, skipping")
                        continue
                    
                    # Verify session is still valid
                    print(f"[Background Refresh] Verifying session for user {user_id} before refresh...")
                    verification = verify_respondent_authentication(cookies)
                    if not verification.get('success'):
                        print(f"[Background Refresh] Session invalid for user {user_id}: {verification.get('message', 'Unknown error')}")
                        error_count += 1
                        continue
                    
                    # Create authenticated session
                    req_session = create_respondent_session(cookies=cookies)
                    
                    # Fetch all projects (this will bypass cache since use_cache=False)
                    print(f"[Background Refresh] Fetching projects for user {user_id} (profile_id={profile_id})...")
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
                        print(f"[Background Refresh] Successfully refreshed cache for user {user_id}: {len(all_projects)} projects")
                        refreshed_count += 1
                    else:
                        print(f"[Background Refresh] No projects fetched for user {user_id}")
                        error_count += 1
                        
                except Exception as e:
                    print(f"[Background Refresh] Error refreshing cache for user {user_id}: {e}")
                    import traceback
                    print(traceback.format_exc())
                    error_count += 1
        
        if refreshed_count > 0 or error_count > 0:
            print(f"[Background Refresh] Completed: {refreshed_count} refreshed, {error_count} errors")
                
    except Exception as e:
        print(f"[Background Refresh] Error in refresh_stale_caches: {e}")
        import traceback
        print(traceback.format_exc())

