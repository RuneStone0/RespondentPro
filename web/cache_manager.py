#!/usr/bin/env python3
"""
Module for managing project cache in MongoDB
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bson import ObjectId
from pymongo.collection import Collection


def is_cache_fresh(
    collection: Collection,
    user_id: str,
    max_age_hours: int = 24
) -> bool:
    """
    Check if cache needs refresh
    
    Args:
        collection: MongoDB collection for projects_cache
        user_id: User ID
        max_age_hours: Maximum age of cache in hours before refresh needed
        
    Returns:
        True if cache is fresh, False if refresh needed
    """
    try:
        cache_doc = collection.find_one(
            {'user_id': user_id},
            {'cached_at': 1}
        )
        
        if not cache_doc:
            return False
        
        cached_at = cache_doc.get('cached_at')
        if not cached_at:
            return False
        
        # Check if cache is older than max_age_hours
        age = datetime.utcnow() - cached_at
        return age < timedelta(hours=max_age_hours)
    except Exception as e:
        print(f"Error checking cache freshness: {e}")
        return False


def get_cached_projects(collection: Collection, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached projects
    
    Args:
        collection: MongoDB collection for projects_cache
        user_id: User ID
        
    Returns:
        Dictionary with cached projects data, or None if not found
    """
    try:
        cache_doc = collection.find_one({'user_id': user_id})
        if cache_doc and 'projects' in cache_doc:
            return {
                'projects': cache_doc['projects'],
                'cached_at': cache_doc.get('cached_at'),
                'total_count': cache_doc.get('total_count', 0)
            }
        return None
    except Exception as e:
        print(f"Error getting cached projects: {e}")
        return None


def refresh_project_cache(
    collection: Collection,
    user_id: str,
    projects: List[Dict[str, Any]],
    total_count: int
) -> bool:
    """
    Store projects in cache
    
    Args:
        collection: MongoDB collection for projects_cache
        user_id: User ID
        projects: List of project dictionaries
        total_count: Total number of projects
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cache_doc = {
            'user_id': user_id,
            'projects': projects,
            'total_count': total_count,
            'cached_at': datetime.utcnow(),
            'last_updated': datetime.utcnow()
        }
        
        collection.update_one(
            {'user_id': user_id},
            {'$set': cache_doc},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error refreshing project cache: {e}")
        return False


def get_cache_stats(collection: Collection, user_id: str) -> Dict[str, Any]:
    """
    Return cache statistics
    
    Args:
        collection: MongoDB collection for projects_cache
        user_id: User ID
        
    Returns:
        Dictionary with cache statistics
    """
    try:
        cache_doc = collection.find_one(
            {'user_id': user_id},
            {'cached_at': 1, 'last_updated': 1, 'total_count': 1}
        )
        
        if not cache_doc:
            return {
                'exists': False,
                'cached_at': None,
                'last_updated': None,
                'total_count': 0
            }
        
        return {
            'exists': True,
            'cached_at': cache_doc.get('cached_at'),
            'last_updated': cache_doc.get('last_updated'),
            'total_count': cache_doc.get('total_count', 0)
        }
    except Exception as e:
        print(f"Error getting cache stats: {e}")
        return {
            'exists': False,
            'cached_at': None,
            'last_updated': None,
            'total_count': 0
        }


def mark_projects_hidden_in_cache(
    collection: Collection,
    user_id: str,
    project_ids: List[str]
) -> bool:
    """
    Mark projects as hidden in the cache by removing them from the cached projects list
    
    Args:
        collection: MongoDB collection for projects_cache
        user_id: User ID
        project_ids: List of project IDs to mark as hidden
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if not project_ids:
            return True
        
        # Get current cache
        cache_doc = collection.find_one({'user_id': user_id})
        if not cache_doc or 'projects' not in cache_doc:
            return False
        
        projects = cache_doc.get('projects', [])
        project_ids_set = set(str(pid) for pid in project_ids)
        
        # Filter out hidden projects
        filtered_projects = [
            p for p in projects 
            if str(p.get('id')) not in project_ids_set
        ]
        
        # Update cache with filtered projects
        collection.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'projects': filtered_projects,
                    'total_count': len(filtered_projects),
                    'last_updated': datetime.utcnow()
                }
            }
        )
        
        print(f"[Cache] Marked {len(project_ids)} project(s) as hidden in cache for user {user_id}")
        return True
    except Exception as e:
        print(f"Error marking projects as hidden in cache: {e}")
        return False


def get_cached_project_details(collection: Collection, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached project details by project_id
    
    Args:
        collection: MongoDB collection for project_details
        project_id: Project ID to look up
        
    Returns:
        Dictionary with cached project details (project data at root), or None if not found
    """
    try:
        if collection is None:
            return None
        cache_doc = collection.find_one({'project_id': project_id})
        if cache_doc and 'details' in cache_doc:
            return cache_doc['details']
        return None
    except Exception as e:
        print(f"Error getting cached project details: {e}")
        return None


def cache_project_details(collection: Collection, project_id: str, details: Dict[str, Any]) -> bool:
    """
    Store project details in cache
    
    Args:
        collection: MongoDB collection for project_details
        project_id: Project ID
        details: Full project details dictionary from API
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if collection is None:
            return False
        cache_doc = {
            'project_id': project_id,
            'details': details,
            'cached_at': datetime.utcnow(),
            'last_updated': datetime.utcnow()
        }
        
        collection.update_one(
            {'project_id': project_id},
            {'$set': cache_doc},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error caching project details: {e}")
        return False

