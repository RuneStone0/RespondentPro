#!/usr/bin/env python3
"""
Topics extraction and management service for Respondent.io Manager
"""

from typing import List, Dict, Any, Optional
from pymongo.collection import Collection


def extract_topics_from_project(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract topics from a project object
    
    Args:
        project: Project dictionary (may have nested structure)
        
    Returns:
        List of topic dictionaries with 'id' and 'name' keys
    """
    topics = []
    
    # Check project.topics (from detailed response)
    if isinstance(project.get('project'), dict):
        project_topics = project.get('project', {}).get('topics', [])
        if isinstance(project_topics, list):
            topics.extend(project_topics)
    
    # Also check direct project.topics (in case it's already merged)
    direct_topics = project.get('topics', [])
    if isinstance(direct_topics, list):
        # Avoid duplicates by checking IDs
        existing_ids = {t.get('id') for t in topics}
        for topic in direct_topics:
            if topic.get('id') and topic.get('id') not in existing_ids:
                topics.append(topic)
    
    return topics


def store_unique_topics(collection: Collection, topics: List[Dict[str, Any]]) -> bool:
    """
    Store unique topics in the topics collection
    
    Args:
        collection: MongoDB collection for topics
        topics: List of topic dictionaries with 'id' and 'name'
        
    Returns:
        True if successful, False otherwise
    """
    if collection is None:
        return False
    
    try:
        for topic in topics:
            topic_id = topic.get('id')
            topic_name = topic.get('name')
            
            if not topic_id or not topic_name:
                continue
            
            # Upsert topic
            collection.update_one(
                {'topic_id': topic_id},
                {
                    '$set': {
                        'topic_id': topic_id,
                        'name': topic_name,
                        'last_seen': topic  # Store the full topic object for reference
                    }
                },
                upsert=True
            )
        
        return True
    except Exception as e:
        print(f"Error storing topics: {e}")
        return False


def get_all_topics(collection: Collection) -> List[Dict[str, Any]]:
    """
    Get all unique topics from the collection
    
    Args:
        collection: MongoDB collection for topics
        
    Returns:
        List of topic dictionaries with 'topic_id' and 'name'
    """
    if collection is None:
        return []
    
    try:
        topics = []
        for doc in collection.find({}):
            topics.append({
                'id': doc.get('topic_id'),
                'name': doc.get('name')
            })
        return topics
    except Exception as e:
        print(f"Error getting all topics: {e}")
        return []


