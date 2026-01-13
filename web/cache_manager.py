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

# Import users_collection and db for user_id resolution and batch operations
from .db import users_collection, db


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
    Check if cache needs refresh using new sub-collection structure.
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID)
        max_age_hours: Maximum age of cache in hours before refresh needed
        
    Returns:
        True if cache is fresh, False if refresh needed
    """
    try:
        # Resolve user_id
        current_user_id, _ = resolve_user_id_for_query(user_id)
        
        # Get parent document directly by user_id (document ID)
        parent_ref = collection.document(current_user_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            return False
        
        cache_doc = parent_doc.to_dict()
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
    Retrieve cached projects using new sub-collection structure.
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID)
    
    Returns:
        Dictionary with cached projects data, or None if not found
    """
    try:
        # Resolve user_id
        current_user_id, _ = resolve_user_id_for_query(user_id)
        logger.debug(f"[Cache] Getting cached projects for user_id={user_id}, resolved to current_user_id={current_user_id}")
        
        # Get parent document directly by user_id (document ID)
        parent_ref = collection.document(current_user_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            logger.debug(f"[Cache] Parent document does NOT exist for user_id={current_user_id}")
            return None
        
        parent_data = parent_doc.to_dict()
        
        # Get all projects from sub-collection
        projects_ref = parent_ref.collection('projects')
        project_docs = list(projects_ref.stream())
        
        # Convert documents to project dictionaries
        projects = [doc.to_dict() for doc in project_docs]
        
        if len(projects) == 0:
            logger.warning(f"[Cache] No projects found in sub-collection for user_id={current_user_id}, but parent document exists.")
        
        logger.debug(f"[Cache] Returning {len(projects)} projects for user_id={current_user_id}")
        
        return {
            'projects': projects,
            'cached_at': parent_data.get('cached_at'),
            'total_count': len(projects)
        }
    except Exception as e:
        logger.error(f"Error getting cached projects for user_id={user_id}: {e}", exc_info=True)
        return None


def get_cached_project(collection, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single cached project by ID using new sub-collection structure.
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID)
        project_id: Project ID to retrieve
    
    Returns:
        Project dictionary, or None if not found
    """
    try:
        # Resolve user_id
        current_user_id, _ = resolve_user_id_for_query(user_id)
        
        # Get parent document reference
        parent_ref = collection.document(current_user_id)
        
        # Get project document from sub-collection
        project_ref = parent_ref.collection('projects').document(str(project_id))
        project_doc = project_ref.get()
        
        if project_doc.exists:
            return project_doc.to_dict()
        
        return None
    except Exception as e:
        logger.error(f"Error getting cached project: {e}", exc_info=True)
        return None


def refresh_project_cache(
    collection,
    user_id: str,
    projects: List[Dict[str, Any]],
    total_count: int
) -> bool:
    """
    Store projects in cache using new sub-collection structure.
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID
        projects: List of project dictionaries
        total_count: Total number of projects
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Resolve user_id
        current_user_id, _ = resolve_user_id_for_query(user_id)
        
        now = datetime.now(timezone.utc)
        
        # Get parent document reference (document ID is user_id)
        parent_ref = collection.document(current_user_id)
        
        # Create/update parent document with metadata
        parent_data = {
            'user_id': current_user_id,
            'total_count': len(projects),
            'cached_at': now,
            'last_updated': now
        }
        parent_ref.set(parent_data)
        
        # Get projects sub-collection reference
        projects_ref = parent_ref.collection('projects')
        
        # Use batch writes for efficiency (Firestore batch limit is 500)
        if db is None:
            logger.error("Firestore db not available")
            return False
        
        batch = db.batch()
        batch_count = 0
        
        # Delete all existing projects first (to handle removed projects)
        existing_projects = list(projects_ref.stream())
        for existing_doc in existing_projects:
            batch.delete(existing_doc.reference)
            batch_count += 1
            
            if batch_count >= 500:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        
        # Write new projects
        for project in projects:
            project_id = str(project.get('id'))
            if not project_id:
                logger.warning(f"Skipping project without ID: {project}")
                continue
            
            project_doc_ref = projects_ref.document(project_id)
            batch.set(project_doc_ref, project)
            batch_count += 1
            
            # Firestore batch limit is 500 operations
            if batch_count >= 500:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        
        # Commit remaining batch
        if batch_count > 0:
            batch.commit()
        
        logger.info(f"[Cache] Refreshed cache for user {current_user_id}: {len(projects)} projects")
        return True
    except Exception as e:
        logger.error(f"Error refreshing project cache: {e}", exc_info=True)
        return False


def get_cache_stats(collection, user_id: str) -> Dict[str, Any]:
    """
    Return cache statistics using new sub-collection structure.
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID)
    
    Returns:
        Dictionary with cache statistics
    """
    try:
        # Resolve user_id
        current_user_id, _ = resolve_user_id_for_query(user_id)
        
        # Get parent document directly by user_id (document ID)
        parent_ref = collection.document(current_user_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            return {
                'exists': False,
                'cached_at': None,
                'last_updated': None,
                'total_count': 0
            }
        
        cache_doc = parent_doc.to_dict()
        
        # Count actual projects in sub-collection for accuracy
        projects_ref = parent_ref.collection('projects')
        actual_count = len(list(projects_ref.stream()))
        
        return {
            'exists': True,
            'cached_at': cache_doc.get('cached_at'),
            'last_updated': cache_doc.get('last_updated'),
            'total_count': actual_count
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
    Mark projects as hidden in the cache by deleting them from sub-collection.
    Uses transaction to update parent document count atomically.
    
    Args:
        collection: Firestore collection for projects_cache
        user_id: User ID (Firebase Auth UID)
        project_ids: List of project IDs to mark as hidden
    
    Returns:
        True if successful, False otherwise
    """
    try:
        if not project_ids:
            return True
        
        # Resolve user_id
        current_user_id, _ = resolve_user_id_for_query(user_id)
        
        # Get parent document reference
        parent_ref = collection.document(current_user_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            logger.warning(f"Cache not found for user {current_user_id}")
            return False
        
        # Get projects sub-collection reference
        projects_ref = parent_ref.collection('projects')
        
        # Get current count from parent document before deletion
        parent_data = parent_doc.to_dict()
        current_count = parent_data.get('total_count', 0)
        
        # Use batch deletes for efficiency (Firestore batch limit is 500)
        if db is None:
            logger.error("Firestore db not available")
            return False
        
        batch = db.batch()
        batch_count = 0
        total_to_delete = len(project_ids)
        
        # Delete each project document using batch operations (no existence check needed - delete is idempotent)
        for project_id in project_ids:
            project_ref = projects_ref.document(str(project_id))
            batch.delete(project_ref)
            batch_count += 1
            
            # Firestore batch limit is 500 operations
            if batch_count >= 500:
                batch.commit()
                logger.debug(f"[Cache] Committed batch delete: {batch_count} operations")
                batch = db.batch()
                batch_count = 0
        
        # Commit remaining batch
        if batch_count > 0:
            batch.commit()
        
        if total_to_delete == 0:
            logger.info(f"[Cache] No projects to delete for user {current_user_id}")
            return True
        
        # Calculate new count (current - deleted) instead of counting all remaining projects
        # Note: We use total_to_delete instead of actual deleted count since delete is idempotent
        # and we don't want to count all remaining projects (which would be slow)
        new_count = max(0, current_count - total_to_delete)
        
        # Update parent document with new count
        parent_ref.update({
            'total_count': new_count,
            'last_updated': datetime.now(timezone.utc)
        })
        
        logger.info(f"[Cache] Marked {total_to_delete} project(s) as hidden in cache for user {current_user_id} (count: {current_count} -> {new_count})")
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
