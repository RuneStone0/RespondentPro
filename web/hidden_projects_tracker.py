#!/usr/bin/env python3
"""
Module for tracking hidden projects with timestamps for analytics
Firestore implementation
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
from google.cloud.firestore_v1.base_query import FieldFilter


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
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID
        project_id: Project ID that was hidden
        hidden_method: Method used to hide ("manual", "auto_similar", "category", "feedback_based")
        feedback_text: Optional feedback text from user
        category_name: Optional category name if hidden via category
        
    Returns:
        True if successful, False otherwise
    """
    try:
        now = datetime.utcnow()
        
        # Build update document
        update_doc = {
            'user_id': str(user_id),
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
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
        docs = list(query)
        
        if docs:
            # Update existing document
            docs[0].reference.update(update_doc)
        else:
            # Create new document
            update_doc['created_at'] = now
            collection.add(update_doc)
        
        return True
    except Exception as e:
        print(f"Error logging hidden project: {e}")
        return False


def get_hidden_projects_count(collection, user_id: str) -> int:
    """
    Get total count of hidden projects for a user
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID
        
    Returns:
        Total count of hidden projects
    """
    try:
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).stream()
        count = sum(1 for _ in query)
        return count
    except Exception as e:
        print(f"Error getting hidden projects count: {e}")
        return 0


def get_hidden_projects_timeline(
    collection,
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    group_by: str = 'day'
) -> List[Dict[str, Any]]:
    """
    Get hidden projects grouped by date for graphing
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID
        start_date: Optional start date filter
        end_date: Optional end date filter
        group_by: Grouping period ('day', 'week', 'month')
        
    Returns:
        List of dicts with date and count: [{'date': '2024-01-01', 'count': 5}, ...]
    """
    try:
        # Build query
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id)))
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
        print(f"Error getting hidden projects timeline: {e}")
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
    Get statistics about hidden projects
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID
        
    Returns:
        Dictionary with statistics
    """
    try:
        # Get all hidden projects for this user
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).stream()
        docs = list(query)
        
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
        print(f"Error getting hidden projects stats: {e}")
        return {
            'total': 0,
            'by_method': {},
            'recent': []
        }


def is_project_hidden(collection, user_id: str, project_id: str) -> bool:
    """
    Check if a specific project is hidden for a user
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID
        project_id: Project ID to check
        
    Returns:
        True if project is hidden, False otherwise
    """
    try:
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
        docs = list(query)
        return len(docs) > 0
    except Exception as e:
        print(f"Error checking if project is hidden: {e}")
        return False


def get_recently_hidden(
    collection,
    user_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recently hidden projects
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID
        limit: Maximum number of results
        
    Returns:
        List of recently hidden project documents
    """
    try:
        # Get all documents for user, sorted by hidden_at descending
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).order_by('hidden_at', direction='DESCENDING').limit(limit).stream()
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
        print(f"Error getting recently hidden projects: {e}")
        return []


def get_all_hidden_projects(
    collection,
    user_id: str,
    page: int = 1,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Get all hidden projects for a user with pagination support
    
    Args:
        collection: Firestore collection for hidden_projects_log
        user_id: User ID
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
        # Get total count
        total_query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).stream()
        query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).order_by('hidden_at', direction='DESCENDING').stream()
        total = sum(1 for _ in total_query)
        
        # Calculate skip value (Firestore doesn't support skip, so we'll fetch all and slice)
        # For better performance with large datasets, consider using cursor-based pagination
        
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
        
        # Apply pagination
        skip = (page - 1) * limit
        results = all_results[skip:skip + limit]
        
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
        print(f"Error getting all hidden projects: {e}")
        return {
            'projects': [],
            'total': 0,
            'page': page,
            'limit': limit,
            'total_pages': 0
        }
