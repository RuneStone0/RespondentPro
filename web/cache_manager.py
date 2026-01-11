#!/usr/bin/env python3
"""
Module for managing project cache in Firestore
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from google.cloud.firestore_v1.base_query import FieldFilter

# Create logger for this module
logger = logging.getLogger(__name__)

# Import users_collection for user_id resolution
try:
    from .db import users_collection
except ImportError:
    try:
        from web.db import users_collection
    except ImportError:
        users_collection = None


def resolve_user_id_for_query(user_id: str) -> tuple[str, Optional[str]]:
    """
    Resolve the user_id to use for queries, handling migration from old user_id to Firebase Auth UID.
    
    This function helps with the transition from the old system where user_id was a Firestore document ID
    to the new system where user_id is the Firebase Auth UID.
    
    Returns:
        tuple: (user_id_to_use, old_user_id_if_found)
        - user_id_to_use: The user_id to use for new queries (Firebase Auth UID)
        - old_user_id_if_found: The old Firestore document ID if found, None otherwise
    """
    # First, try direct lookup with the provided user_id (could be Firebase Auth UID)
    # If user_id is a Firebase Auth UID, check if there's a user document with that ID
    if users_collection:
        try:
            # Check if user_id is a Firebase Auth UID (document exists with that ID)
            user_doc = users_collection.document(str(user_id)).get()
            if user_doc.exists:
                # This is a Firebase Auth UID document, use it directly
                return str(user_id), None
            
            # Try to find user by firebase_uid field (for migrated users)
            firebase_uid_query = users_collection.where(filter=FieldFilter('firebase_uid', '==', str(user_id))).limit(1).stream()
            firebase_uid_docs = list(firebase_uid_query)
            if firebase_uid_docs:
                # Found user with this firebase_uid, return both IDs
                old_user_id = firebase_uid_docs[0].id
                return str(user_id), old_user_id
        except Exception as e:
            logger.error(f"Error resolving user_id: {e}", exc_info=True)
    
    # Fallback: use the provided user_id as-is
    return str(user_id), None


def query_with_user_id_fallback(collection, user_id: str, additional_filters=None):
    """
    Query a collection by user_id, trying both new Firebase Auth UID and old user_id format.
    
    Args:
        collection: Firestore collection to query
        user_id: User ID (Firebase Auth UID for new users)
        additional_filters: List of additional FieldFilter objects to apply
    
    Returns:
        List of document snapshots
    """
    current_user_id, old_user_id = resolve_user_id_for_query(user_id)
    
    # Build filters
    filters = [FieldFilter('user_id', '==', current_user_id)]
    if additional_filters:
        filters.extend(additional_filters)
    
    # Try with current user_id first
    query = collection
    for f in filters:
        query = query.where(filter=f)
    docs = list(query.limit(1000).stream())  # Use reasonable limit
    
    # If not found and we have old_user_id, try with that
    if not docs and old_user_id:
        filters_old = [FieldFilter('user_id', '==', old_user_id)]
        if additional_filters:
            filters_old.extend(additional_filters)
        query_old = collection
        for f in filters_old:
            query_old = query_old.where(filter=f)
        docs = list(query_old.limit(1000).stream())
        
        # If we found docs with old_user_id, migrate them
        if docs:
            logger.info(f"[Migration] Found {len(docs)} document(s) with old user_id {old_user_id}, migrating to {current_user_id}")
            for doc in docs:
                doc.reference.update({'user_id': current_user_id})
    
    return docs


def is_cache_fresh(
    collection,
    user_id: str,
    max_age_hours: int = 24
) -> bool:
    """
    Check if cache needs refresh, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID for new users)
        max_age_hours: Maximum age of cache in hours before refresh needed
        
    Returns:
        True if cache is fresh, False if refresh needed
    """
    try:
        # Resolve user_id
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Try with current user_id first
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).limit(1).stream()
        docs = list(query)
        
        # If not found and we have old_user_id, try that
        if not docs and old_user_id:
            query = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(1).stream()
            docs = list(query)
        
        if not docs:
            return False
        
        cache_doc = docs[0].to_dict()
        cached_at = cache_doc.get('cached_at')
        if not cached_at:
            return False
        
        # Ensure both datetimes are timezone-aware for comparison
        now = datetime.now(timezone.utc)
        
        # Convert cached_at to timezone-aware if it's naive
        if isinstance(cached_at, datetime):
            if cached_at.tzinfo is None:
                # Naive datetime - assume UTC
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            # If already timezone-aware, use as-is
        else:
            # Not a datetime object, can't compare
            return False
        
        # Check if cache is older than max_age_hours
        age = now - cached_at
        return age < timedelta(hours=max_age_hours)
    except Exception as e:
        logger.error(f"Error checking cache freshness: {e}", exc_info=True)
        return False


def get_cached_projects(collection, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached projects, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID for new users)
    
    Returns:
        Dictionary with cached projects data, or None if not found
    """
    try:
        # Resolve user_id - get both new and old user_id if available
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # First try with current user_id (Firebase Auth UID)
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).limit(1).stream()
        docs = list(query)
        if docs:
            cache_doc = docs[0].to_dict()
            if 'projects' in cache_doc:
                return {
                    'projects': cache_doc['projects'],
                    'cached_at': cache_doc.get('cached_at'),
                    'total_count': cache_doc.get('total_count', 0)
                }
        
        # If not found and we have an old_user_id, try with that
        if old_user_id:
            query = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(1).stream()
            docs = list(query)
            if docs:
                cache_doc = docs[0].to_dict()
                if 'projects' in cache_doc:
                    # Migrate cache to use new user_id
                    cache_doc['user_id'] = current_user_id
                    docs[0].reference.update({'user_id': current_user_id})
                    logger.info(f"[Cache Migration] Migrated projects cache from old user_id {old_user_id} to {current_user_id}")
                    return {
                        'projects': cache_doc['projects'],
                        'cached_at': cache_doc.get('cached_at'),
                        'total_count': cache_doc.get('total_count', 0)
                    }
        
        return None
    except Exception as e:
        logger.error(f"Error getting cached projects: {e}", exc_info=True)
        return None


def refresh_project_cache(
    collection,
    user_id: str,
    projects: List[Dict[str, Any]],
    total_count: int
) -> bool:
    """
    Store projects in cache
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID
        projects: List of project dictionaries
        total_count: Total number of projects
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cache_doc = {
            'user_id': str(user_id),
            'projects': projects,
            'total_count': total_count,
            'cached_at': datetime.now(timezone.utc),
            'last_updated': datetime.now(timezone.utc)
        }
        
        # Find existing document or create new one
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        
        if docs:
            docs[0].reference.update(cache_doc)
        else:
            collection.add(cache_doc)
        
        return True
    except Exception as e:
        logger.error(f"Error refreshing project cache: {e}", exc_info=True)
        return False


def get_cache_stats(collection, user_id: str) -> Dict[str, Any]:
    """
    Return cache statistics, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID for new users)
    
    Returns:
        Dictionary with cache statistics
    """
    try:
        # Resolve user_id
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Try with current user_id first
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).limit(1).stream()
        docs = list(query)
        
        # If not found and we have old_user_id, try that
        if not docs and old_user_id:
            query = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(1).stream()
            docs = list(query)
        
        if not docs:
            return {
                'exists': False,
                'cached_at': None,
                'last_updated': None,
                'total_count': 0
            }
        
        cache_doc = docs[0].to_dict()
        return {
            'exists': True,
            'cached_at': cache_doc.get('cached_at'),
            'last_updated': cache_doc.get('last_updated'),
            'total_count': cache_doc.get('total_count', 0)
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}", exc_info=True)
        return {
            'exists': False,
            'cached_at': None,
            'last_updated': None,
            'total_count': 0
        }


def mark_projects_hidden_in_cache(
    collection,
    user_id: str,
    project_ids: List[str]
) -> bool:
    """
    Mark projects as hidden in the cache by removing them from the cached projects list
    Handles migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID for new users)
        project_ids: List of project IDs to mark as hidden
    
    Returns:
        True if successful, False otherwise
    """
    try:
        if not project_ids:
            return True
        
        # Resolve user_id
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Try with current user_id first
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).limit(1).stream()
        docs = list(query)
        
        # If not found and we have old_user_id, try that
        if not docs and old_user_id:
            query = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(1).stream()
            docs = list(query)
        
        if not docs:
            return False
        
        cache_doc = docs[0].to_dict()
        if 'projects' not in cache_doc:
            return False
        
        # If we found cache with old_user_id, migrate it first
        if old_user_id and cache_doc.get('user_id') == old_user_id:
            docs[0].reference.update({'user_id': current_user_id})
            logger.info(f"[Cache Migration] Migrated projects cache from old user_id {old_user_id} to {current_user_id}")
        
        projects = cache_doc.get('projects', [])
        project_ids_set = set(str(pid) for pid in project_ids)
        
        # Filter out hidden projects
        filtered_projects = [
            p for p in projects 
            if str(p.get('id')) not in project_ids_set
        ]
        
        # Update cache with filtered projects
        docs[0].reference.update({
            'projects': filtered_projects,
            'total_count': len(filtered_projects),
            'last_updated': datetime.now(timezone.utc)
        })
        
        logger.info(f"[Cache] Marked {len(project_ids)} project(s) as hidden in cache for user {current_user_id}")
        return True
    except Exception as e:
        logger.error(f"Error marking projects as hidden in cache: {e}", exc_info=True)
        return False


def get_cached_project_details(collection, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached project details by project_id
    
    Args:
        collection: Firestore collection for project_details
        project_id: Project ID to look up
        
    Returns:
        Dictionary with cached project details (project data at root), or None if not found
    """
    try:
        if collection is None:
            return None
        query = collection.where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
        docs = list(query)
        if docs:
            cache_doc = docs[0].to_dict()
            if 'details' in cache_doc:
                return cache_doc['details']
        return None
    except Exception as e:
        logger.error(f"Error getting cached project details: {e}", exc_info=True)
        return None


def cache_project_details(collection, project_id: str, details: Dict[str, Any]) -> bool:
    """
    Store project details in cache
    
    Args:
        collection: Firestore collection for project_details
        project_id: Project ID
        details: Full project details dictionary from API
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if collection is None:
            return False
        cache_doc = {
            'project_id': str(project_id),
            'details': details,
            'cached_at': datetime.now(timezone.utc),
            'last_updated': datetime.now(timezone.utc)
        }
        
        # Find existing document or create new one
        query = collection.where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
        docs = list(query)
        
        if docs:
            docs[0].reference.update(cache_doc)
        else:
            collection.add(cache_doc)
        
        return True
    except Exception as e:
        logger.error(f"Error caching project details: {e}", exc_info=True)
        return False
