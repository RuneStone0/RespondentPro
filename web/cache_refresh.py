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
    Refresh all stale caches
    
    Args:
        db: MongoDB database object
        max_age_hours: Maximum age of cache before refresh
    """
    try:
        projects_cache_collection = db['projects_cache']
        session_keys_collection = db['session_keys']
        
        # Get all cached users
        cached_users = projects_cache_collection.find({}, {'user_id': 1, 'cached_at': 1})
        
        for cache_doc in cached_users:
            user_id = cache_doc.get('user_id')
            if not user_id:
                continue
            
            # Check if cache is stale
            if not is_cache_fresh(projects_cache_collection, user_id, max_age_hours):
                # Get user's session keys
                config_doc = session_keys_collection.find_one({'user_id': user_id})
                if not config_doc:
                    continue
                
                cookies = config_doc.get('cookies', {})
                profile_id = config_doc.get('profile_id')
                
                if not cookies.get('respondent.session.sid') or not profile_id:
                    continue
                
                # Refresh cache (this would need to call fetch_respondent_projects)
                # For now, just mark as needing refresh
                print(f"Cache for user {user_id} is stale and needs refresh")
                # Actual refresh would be done on next request or via separate endpoint
                
    except Exception as e:
        print(f"Error refreshing stale caches: {e}")

