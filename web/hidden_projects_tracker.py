#!/usr/bin/env python3
"""
Module for tracking hidden projects with timestamps for analytics
"""

from datetime import datetime, timedelta
from bson import ObjectId
from typing import List, Dict, Any, Optional
from pymongo.collection import Collection


def log_hidden_project(
    collection: Collection,
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
        collection: MongoDB collection for hidden_projects_log
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
            '$set': {
                'hidden_at': now,
                'hidden_method': hidden_method,
                'updated_at': now
            }
        }
        
        # Add optional fields if provided
        if feedback_text:
            update_doc['$set']['feedback_text'] = feedback_text
        
        if category_name:
            update_doc['$set']['category_name'] = category_name
        
        # Use upsert to insert if not exists, or update if exists
        # This ensures no duplicates while updating the timestamp if already hidden
        result = collection.update_one(
            {
                'user_id': user_id,
                'project_id': project_id
            },
            update_doc,
            upsert=True
        )
        
        # If this was an insert (not an update), set created_at
        if result.upserted_id is not None:
            collection.update_one(
                {'_id': result.upserted_id},
                {'$set': {'created_at': now}}
            )
        
        return True
    except Exception as e:
        print(f"Error logging hidden project: {e}")
        return False


def get_hidden_projects_count(collection: Collection, user_id: str) -> int:
    """
    Get total count of hidden projects for a user
    
    Args:
        collection: MongoDB collection for hidden_projects_log
        user_id: User ID
        
    Returns:
        Total count of hidden projects
    """
    try:
        return collection.count_documents({'user_id': user_id})
    except Exception as e:
        print(f"Error getting hidden projects count: {e}")
        return 0


def get_hidden_projects_timeline(
    collection: Collection,
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    group_by: str = 'day'
) -> List[Dict[str, Any]]:
    """
    Get hidden projects grouped by date for graphing
    
    Args:
        collection: MongoDB collection for hidden_projects_log
        user_id: User ID
        start_date: Optional start date filter
        end_date: Optional end date filter
        group_by: Grouping period ('day', 'week', 'month')
        
    Returns:
        List of dicts with date and count: [{'date': '2024-01-01', 'count': 5}, ...]
    """
    try:
        query = {'user_id': user_id}
        
        if start_date or end_date:
            query['hidden_at'] = {}
            if start_date:
                query['hidden_at']['$gte'] = start_date
            if end_date:
                query['hidden_at']['$lte'] = end_date
        
        # Aggregate by date
        date_format = _get_date_format(group_by)
        pipeline = [
            {'$match': query},
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': date_format,
                            'date': '$hidden_at'
                        }
                    },
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'_id': 1}},
            {
                '$project': {
                    '_id': 0,
                    'date': '$_id',
                    'count': 1
                }
            }
        ]
        
        results = list(collection.aggregate(pipeline))
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


def get_hidden_projects_stats(collection: Collection, user_id: str) -> Dict[str, Any]:
    """
    Get statistics about hidden projects
    
    Args:
        collection: MongoDB collection for hidden_projects_log
        user_id: User ID
        
    Returns:
        Dictionary with statistics
    """
    try:
        total = collection.count_documents({'user_id': user_id})
        
        # Count by method
        pipeline = [
            {'$match': {'user_id': user_id}},
            {
                '$group': {
                    '_id': '$hidden_method',
                    'count': {'$sum': 1}
                }
            }
        ]
        
        method_counts = {}
        for result in collection.aggregate(pipeline):
            method_counts[result['_id']] = result['count']
        
        # Get recent hidden projects
        recent = list(
            collection.find(
                {'user_id': user_id},
                {'project_id': 1, 'hidden_at': 1, 'hidden_method': 1}
            )
            .sort('hidden_at', -1)
            .limit(10)
        )
        
        # Convert ObjectId to string for JSON serialization
        for item in recent:
            if '_id' in item:
                item['_id'] = str(item['_id'])
            if 'hidden_at' in item:
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


def is_project_hidden(collection: Collection, user_id: str, project_id: str) -> bool:
    """
    Check if a specific project is hidden for a user
    
    Args:
        collection: MongoDB collection for hidden_projects_log
        user_id: User ID
        project_id: Project ID to check
        
    Returns:
        True if project is hidden, False otherwise
    """
    try:
        count = collection.count_documents({
            'user_id': user_id,
            'project_id': project_id
        })
        return count > 0
    except Exception as e:
        print(f"Error checking if project is hidden: {e}")
        return False


def get_recently_hidden(
    collection: Collection,
    user_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recently hidden projects
    
    Args:
        collection: MongoDB collection for hidden_projects_log
        user_id: User ID
        limit: Maximum number of results
        
    Returns:
        List of recently hidden project documents
    """
    try:
        results = list(
            collection.find(
                {'user_id': user_id},
                {'project_id': 1, 'hidden_at': 1, 'hidden_method': 1, 'category_name': 1}
            )
            .sort('hidden_at', -1)
            .limit(limit)
        )
        
        # Convert ObjectId to string for JSON serialization
        for item in results:
            if '_id' in item:
                item['_id'] = str(item['_id'])
            if 'hidden_at' in item:
                item['hidden_at'] = item['hidden_at'].isoformat()
        
        return results
    except Exception as e:
        print(f"Error getting recently hidden projects: {e}")
        return []

