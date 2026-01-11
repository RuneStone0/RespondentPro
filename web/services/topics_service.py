#!/usr/bin/env python3
"""
Topics extraction and management service for Respondent.io Manager
Firestore implementation
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from google.cloud.firestore_v1.base_query import FieldFilter

# Create logger for this module
logger = logging.getLogger(__name__)


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


def store_unique_topics(collection, topics: List[Dict[str, Any]]) -> bool:
    """
    Store unique topics in the topics collection
    
    Args:
        collection: Firestore collection for topics
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
            
            # Find existing topic by topic_id
            query = collection.where(filter=FieldFilter('topic_id', '==', str(topic_id))).limit(1).stream()
            docs = list(query)
            
            topic_data = {
                'topic_id': str(topic_id),
                'name': topic_name,
                'last_seen': topic,  # Store the full topic object for reference
                'updated_at': datetime.utcnow()
            }
            
            if docs:
                # Update existing topic
                docs[0].reference.update(topic_data)
            else:
                # Create new topic
                collection.add(topic_data)
        
        return True
    except Exception as e:
        logger.error(f"Error storing topics: {e}", exc_info=True)
        return False


def get_all_topics(collection) -> List[Dict[str, Any]]:
    """
    Get all unique topics from the collection
    
    Args:
        collection: Firestore collection for topics
        
    Returns:
        List of topic dictionaries with 'topic_id' and 'name'
    """
    if collection is None:
        return []
    
    try:
        topics = []
        for doc in collection.stream():
            doc_data = doc.to_dict()
            topics.append({
                'id': doc_data.get('topic_id'),
                'name': doc_data.get('name')
            })
        return topics
    except Exception as e:
        logger.error(f"Error getting all topics: {e}", exc_info=True)
        return []

