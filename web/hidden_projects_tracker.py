#!/usr/bin/env python3
"""
Module for tracking hidden projects with timestamps for analytics
Firestore implementation
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
from google.cloud.firestore_v1.base_query import FieldFilter

# Import helper for user_id resolution
from .cache_manager import resolve_user_id_for_query

# Import db collections (lazy import to avoid circular dependencies)
# These will be imported at module level but may be None if db not initialized
try:
    from .db import users_collection, db
except ImportError:
    users_collection = None
    db = None

# Create logger for this module
logger = logging.getLogger(__name__)


def log_hidden_project(
    collection,
    user_id: str,
    project_id: str,
    hidden_method: str,
    feedback_text: Optional[str] = None,
    category_name: Optional[str] = None
) -> bool:
    """
    Log a hidden project with timestamp
    Ensures the same project_id cannot be logged more than once per user.
    If the project is already logged, updates the timestamp and method.
    Also updates the cached count in the user document for performance.
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        project_id: Project ID that was hidden
        hidden_method: Method used to hide ("manual", "auto_similar", "category", "feedback_based")
        feedback_text: Optional feedback text from user
        category_name: Optional category name if hidden via category
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Import resolve helper
        from .cache_manager import resolve_user_id_for_query
        
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        now = datetime.utcnow()
        
        # Build update document
        update_doc = {
            'user_id': current_user_id,  # Always use current user_id
            'project_id': str(project_id),
            'hidden_at': now,
            'hidden_method': hidden_method,
            'updated_at': now
        }
        
        # Add optional fields if provided
        if feedback_text:
            update_doc['feedback_text'] = feedback_text
        
        if category_name:
            update_doc['category_name'] = category_name
        
        # Find existing document
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
        docs = list(query)
        
        is_new = False
        if docs:
            # Update existing document
            docs[0].reference.update(update_doc)
        else:
            # Create new document
            update_doc['created_at'] = now
            collection.add(update_doc)
            is_new = True
        
        # OPTIMIZATION: Update cached count in user document to avoid full scans
        # This makes get_projects_processed_count() much faster
        if is_new:
            # Use module-level imports (already imported at top)
            
            if users_collection and db:
                try:
                    user_doc_ref = users_collection.document(current_user_id)
                    user_doc = user_doc_ref.get()
                    if user_doc.exists:
                        # Increment cached count
                        current_count = user_doc.to_dict().get('projects_processed_count', 0)
                        user_doc_ref.update({
                            'projects_processed_count': current_count + 1,
                            'last_processed_at': now
                        })
                except Exception as e:
                    # Don't fail if cache update fails
                    logger.warning(f"Warning: Failed to update cached count: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Error logging hidden project: {e}", exc_info=True)
        return False


def get_hidden_projects_count(collection, user_id: str) -> int:
    """
    Get total count of hidden projects for a user, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        
    Returns:
        Total count of hidden projects
    """
    try:
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Try with current user_id first
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).stream()
        count = sum(1 for _ in query)
        
        # If no results and we have old_user_id, try that and migrate
        if count == 0 and old_user_id:
            query_old = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).stream()
            docs = list(query_old)
            if docs:
                # Migrate all documents to use new user_id
                # Use module-level db import
                
                if db:
                    batch = db.batch()
                    migrated_count = 0
                    for doc in docs:
                        batch.update(doc.reference, {'user_id': current_user_id})
                        migrated_count += 1
                    batch.commit()
                    logger.info(f"[Migration] Migrated {migrated_count} hidden project log(s) from old user_id {old_user_id} to {current_user_id}")
                else:
                    # Fallback: update documents one by one
                    migrated_count = 0
                    for doc in docs:
                        doc.reference.update({'user_id': current_user_id})
                        migrated_count += 1
                    logger.info(f"[Migration] Migrated {migrated_count} hidden project log(s) from old user_id {old_user_id} to {current_user_id}")
                count = migrated_count
        
        return count
    except Exception as e:
        logger.error(f"Error getting hidden projects count: {e}", exc_info=True)
        return 0


def get_hidden_projects_timeline(
    collection,
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    group_by: str = 'day'
) -> List[Dict[str, Any]]:
    """
    Get hidden projects grouped by date for graphing, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        start_date: Optional start date filter
        end_date: Optional end date filter
        group_by: Grouping period ('day', 'week', 'month')
        
    Returns:
        List of dicts with date and count: [{'date': '2024-01-01', 'count': 5}, ...]
    """
    try:
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Build query with current user_id
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id))
        if start_date:
            query = query.where(filter=FieldFilter('hidden_at', '>=', start_date))
        if end_date:
            query = query.where(filter=FieldFilter('hidden_at', '<=', end_date))
        
        # Fetch all matching documents
        docs = list(query.stream())
        
        # Group by date client-side
        date_format = _get_date_format(group_by)
        grouped = defaultdict(int)
        
        for doc in docs:
            doc_data = doc.to_dict()
            hidden_at = doc_data.get('hidden_at')
            if hidden_at:
                if isinstance(hidden_at, datetime):
                    date_str = hidden_at.strftime(date_format)
                else:
                    # If it's already a string, try to parse it
                    try:
                        hidden_at = datetime.fromisoformat(str(hidden_at).replace('Z', '+00:00'))
                        date_str = hidden_at.strftime(date_format)
                    except:
                        continue
                grouped[date_str] += 1
        
        # Convert to list of dicts and sort
        results = [{'date': date, 'count': count} for date, count in sorted(grouped.items())]
        return results
    except Exception as e:
        logger.error(f"Error getting hidden projects timeline: {e}", exc_info=True)
        return []


def _get_date_format(group_by: str) -> str:
    """Get date format string for grouping"""
    formats = {
        'day': '%Y-%m-%d',
        'week': '%Y-W%V',
        'month': '%Y-%m'
    }
    return formats.get(group_by, '%Y-%m-%d')


def get_hidden_projects_stats(collection, user_id: str) -> Dict[str, Any]:
    """
    Get statistics about hidden projects, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        
    Returns:
        Dictionary with statistics
    """
    try:
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Get all hidden projects for this user with current user_id
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).stream()
        docs = list(query)
        
        # If no results and we have old_user_id, try that and migrate
        if not docs and old_user_id:
            query_old = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).stream()
            docs = list(query_old)
            if docs:
                # Migrate all documents to use new user_id
                # Use module-level db import
                
                if db:
                    batch = db.batch()
                    for doc in docs:
                        batch.update(doc.reference, {'user_id': current_user_id})
                    batch.commit()
                    logger.info(f"[Migration] Migrated {len(docs)} hidden project log(s) from old user_id {old_user_id} to {current_user_id}")
                else:
                    # Fallback: update documents one by one
                    for doc in docs:
                        doc.reference.update({'user_id': current_user_id})
                    logger.info(f"[Migration] Migrated {len(docs)} hidden project log(s) from old user_id {old_user_id} to {current_user_id}")
        
        total = len(docs)
        
        # Count by method client-side
        method_counts = defaultdict(int)
        recent_projects = []
        
        for doc in docs:
            doc_data = doc.to_dict()
            method = doc_data.get('hidden_method', 'unknown')
            method_counts[method] += 1
            
            # Collect recent projects
            recent_projects.append({
                'project_id': doc_data.get('project_id'),
                'hidden_at': doc_data.get('hidden_at'),
                'hidden_method': method
            })
        
        # Sort by hidden_at descending and take top 10
        recent_projects.sort(key=lambda x: x.get('hidden_at') or datetime.min, reverse=True)
        recent = recent_projects[:10]
        
        # Convert datetime to ISO format for JSON serialization
        for item in recent:
            if 'hidden_at' in item and item['hidden_at']:
                if isinstance(item['hidden_at'], datetime):
                    item['hidden_at'] = item['hidden_at'].isoformat()
        
        return {
            'total': total,
            'by_method': {
                'manual': method_counts.get('manual', 0),
                'auto_similar': method_counts.get('auto_similar', 0),
                'category': method_counts.get('category', 0),
                'feedback_based': method_counts.get('feedback_based', 0)
            },
            'recent': recent
        }
    except Exception as e:
        logger.error(f"Error getting hidden projects stats: {e}", exc_info=True)
        return {
            'total': 0,
            'by_method': {},
            'recent': []
        }


def is_project_hidden(collection, user_id: str, project_id: str) -> bool:
    """
    Check if a specific project is hidden for a user, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        project_id: Project ID to check
        
    Returns:
        True if project is hidden, False otherwise
    """
    try:
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Try with current user_id first
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
        docs = list(query)
        
        # If not found and we have old_user_id, try that
        if not docs and old_user_id:
            query_old = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
            docs = list(query_old)
            # If found, migrate it
            if docs:
                docs[0].reference.update({'user_id': current_user_id})
                logger.info(f"[Migration] Migrated hidden project log from old user_id {old_user_id} to {current_user_id}")
        
        return len(docs) > 0
    except Exception as e:
        logger.error(f"Error checking if project is hidden: {e}", exc_info=True)
        return False


def get_last_sync_time(collection, user_id: str) -> Optional[datetime]:
    """
    Get the last sync time from hidden_projects_log (most recent hidden_at timestamp), handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        
    Returns:
        Most recent hidden_at datetime, or None if no projects have been hidden
    """
    try:
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Get the most recent document sorted by hidden_at descending with current user_id
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).order_by('hidden_at', direction='DESCENDING').limit(1).stream()
        docs = list(query)
        
        # If not found and we have old_user_id, try that
        if not docs and old_user_id:
            query_old = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).order_by('hidden_at', direction='DESCENDING').limit(1).stream()
            docs = list(query_old)
        
        if docs:
            doc_data = docs[0].to_dict()
            last_sync = doc_data.get('hidden_at')
            if last_sync:
                # Handle Firestore Timestamp objects
                if hasattr(last_sync, 'timestamp'):
                    # Firestore Timestamp object
                    return datetime.utcfromtimestamp(last_sync.timestamp())
                elif isinstance(last_sync, datetime):
                    # Already a datetime object
                    return last_sync
                elif isinstance(last_sync, str):
                    # Try to parse ISO format string
                    try:
                        return datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                    except:
                        return None
                else:
                    logger.warning(f"Unexpected timestamp type: {type(last_sync)}, value: {last_sync}")
                    return None
        
        return None
    except Exception as e:
        logger.error(f"Error getting last sync time: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return None


def get_recently_hidden(
    collection,
    user_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recently hidden projects, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        limit: Maximum number of results
        
    Returns:
        List of recently hidden project documents
    """
    try:
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Get all documents for user, sorted by hidden_at descending with current user_id
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).order_by('hidden_at', direction='DESCENDING').limit(limit).stream()
        results = []
        
        for doc in query:
            doc_data = doc.to_dict()
            results.append({
                'project_id': doc_data.get('project_id'),
                'hidden_at': doc_data.get('hidden_at'),
                'hidden_method': doc_data.get('hidden_method'),
                'category_name': doc_data.get('category_name')
            })
        
        # Convert datetime to ISO format for JSON serialization
        for item in results:
            if 'hidden_at' in item and item['hidden_at']:
                if isinstance(item['hidden_at'], datetime):
                    item['hidden_at'] = item['hidden_at'].isoformat()
        
        return results
    except Exception as e:
        logger.error(f"Error getting recently hidden projects: {e}", exc_info=True)
        return []


def get_all_hidden_projects(
    collection,
    user_id: str,
    page: int = 1,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Get all hidden projects for a user with pagination support, handling migration from old user_id to Firebase Auth UID
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID (Firebase Auth UID for new users)
        page: Page number (1-indexed)
        limit: Number of results per page
        
    Returns:
        Dictionary with:
        - 'projects': List of hidden project documents
        - 'total': Total count of hidden projects
        - 'page': Current page number
        - 'limit': Results per page
        - 'total_pages': Total number of pages
    """
    try:
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Check if we need to migrate first (only check once, not on every query)
        if old_user_id:
            # Quick check if migration is needed
            check_query = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(1).stream()
            if list(check_query):
                # Migration needed - but don't do it here, let it happen in background
                # For now, we'll query both and merge results
                pass
        
        # Use efficient pagination with limit() - only fetch what we need
        # Calculate offset for cursor-based approach (Firestore doesn't support offset, so we use limit)
        # For page 1: fetch first 'limit' documents
        # For page 2+: we'd need cursor, but for simplicity, we'll use a larger limit and slice
        
        # Optimize: Only fetch the documents we need + a small buffer for migration check
        fetch_limit = limit * page + 10  # Fetch enough for current page + small buffer
        
        # Get paginated results with limit to avoid fetching all documents
        query = collection.where(filter=FieldFilter('user_id', '==', current_user_id)).order_by('hidden_at', direction='DESCENDING').limit(fetch_limit).stream()
        
        all_results = []
        for doc in query:
            doc_data = doc.to_dict()
            all_results.append({
                'project_id': doc_data.get('project_id'),
                'hidden_at': doc_data.get('hidden_at'),
                'hidden_method': doc_data.get('hidden_method'),
                'category_name': doc_data.get('category_name'),
                'feedback_text': doc_data.get('feedback_text')
            })
        
        # If we got fewer results than expected and have old_user_id, check for migration
        if len(all_results) < limit and old_user_id:
            old_query = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).order_by('hidden_at', direction='DESCENDING').limit(limit).stream()
            old_results = []
            for doc in old_query:
                doc_data = doc.to_dict()
                old_results.append({
                    'project_id': doc_data.get('project_id'),
                    'hidden_at': doc_data.get('hidden_at'),
                    'hidden_method': doc_data.get('hidden_method'),
                    'category_name': doc_data.get('category_name'),
                    'feedback_text': doc_data.get('feedback_text')
                })
            
            if old_results:
                # Migrate these documents
                from ..db import db
                
                if db:
                    batch = db.batch()
                    old_query_for_migration = collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(500).stream()
                    migrated = 0
                    for doc in old_query_for_migration:
                        batch.update(doc.reference, {'user_id': current_user_id})
                        migrated += 1
                        if migrated >= 500:  # Firestore batch limit
                            batch.commit()
                            batch = db.batch()
                            migrated = 0
                    if migrated > 0:
                        batch.commit()
                    if migrated > 0 or migrated == 0:
                        logger.info(f"[Migration] Migrated hidden project logs from old user_id {old_user_id} to {current_user_id}")
                
                # Merge old results
                all_results.extend(old_results)
                all_results.sort(key=lambda x: x.get('hidden_at') or datetime.min, reverse=True)
        
        # Apply pagination
        skip = (page - 1) * limit
        results = all_results[skip:skip + limit]
        
        # OPTIMIZATION: Avoid expensive total count query
        # If we fetched fewer than fetch_limit, we've reached the end
        # Otherwise, we'll estimate or skip exact count (can be calculated client-side)
        if len(all_results) < fetch_limit:
            total = len(all_results)  # Exact count - we fetched all documents
        else:
            # We fetched the limit, so there are likely more documents
            # OPTIMIZATION: Avoid expensive full collection scan for total count
            # Use fetched count as minimum, frontend can show "50+" or handle pagination
            total = len(all_results)  # Minimum count - indicates there are at least this many
        
        # Convert datetime to ISO format for JSON serialization
        for item in results:
            if 'hidden_at' in item and item['hidden_at']:
                if isinstance(item['hidden_at'], datetime):
                    item['hidden_at'] = item['hidden_at'].isoformat()
        
        # Calculate total pages
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        
        return {
            'projects': results,
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': total_pages
        }
    except Exception as e:
        logger.error(f"Error getting all hidden projects: {e}", exc_info=True)
        return {
            'projects': [],
            'total': 0,
            'page': page,
            'limit': limit,
            'total_pages': 0
        }
