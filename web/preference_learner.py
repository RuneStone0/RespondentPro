#!/usr/bin/env python3
"""
Module for learning user preferences from behavior
Firestore implementation
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid
import hashlib
import json
from google.cloud.firestore_v1.base_query import FieldFilter

# Create logger for this module
logger = logging.getLogger(__name__)
from .hidden_projects_tracker import log_hidden_project, is_project_hidden
from .ai_analyzer import analyze_hide_feedback, extract_similarity_patterns, find_similar_projects, should_hide_project_based_on_feedback


def _get_or_create_user_prefs(collection, user_id: str) -> tuple:
    """Get user preferences document or create if it doesn't exist. Returns (doc_ref, doc_data, is_new)"""
    query = collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
    docs = list(query)
    if docs:
        return docs[0].reference, docs[0].to_dict(), False
    else:
        # Create new document
        new_data = {
            'user_id': str(user_id),
            'hidden_projects': [],
            'kept_projects': [],
            'hidden_categories': [],
            'learned_patterns': [],
            'question_answers': [],
            'learned_exclusions': [],
            'hide_feedback': [],
            'hide_feedback_updated': datetime.utcnow(),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        doc_ref = collection.add(new_data)
        return doc_ref[1], new_data, True


def record_project_hidden(
    hidden_projects_log_collection,
    user_preferences_collection,
    user_id: str,
    project_id: str,
    feedback_text: Optional[str] = None,
    hidden_method: str = "manual"
) -> bool:
    """
    Track when user hides a project with optional feedback
    
    Args:
        hidden_projects_log_collection: Collection for hidden_projects_log
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        project_id: Project ID
        feedback_text: Optional feedback text
        hidden_method: Method used to hide
        
    Returns:
        True if successful
    """
    try:
        # Log to hidden_projects_log
        log_hidden_project(
            hidden_projects_log_collection,
            user_id,
            project_id,
            hidden_method,
            feedback_text=feedback_text
        )
        
        # Update user_preferences
        doc_ref, prefs_data, is_new = _get_or_create_user_prefs(user_preferences_collection, user_id)
        hidden_projects = prefs_data.get('hidden_projects', [])
        if project_id not in hidden_projects:
            hidden_projects.append(project_id)
        doc_ref.update({
            'hidden_projects': hidden_projects,
            'updated_at': datetime.utcnow()
        })
        
        return True
    except Exception as e:
        logger.error(f"Error recording project hidden: {e}", exc_info=True)
        return False


def record_category_hidden(
    hidden_projects_log_collection,
    user_preferences_collection,
    user_id: str,
    category_name: str,
    category_pattern: Dict[str, Any],
    project_ids: List[str]
) -> bool:
    """
    Track when user hides an entire category
    
    Args:
        hidden_projects_log_collection: Collection for hidden_projects_log
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        category_name: Category name
        category_pattern: Category pattern
        project_ids: List of project IDs in category
        
    Returns:
        True if successful
    """
    try:
        # Log each project
        for project_id in project_ids:
            log_hidden_project(
                hidden_projects_log_collection,
                user_id,
                project_id,
                'category',
                category_name=category_name
            )
        
        # Update user_preferences
        doc_ref, prefs_data, is_new = _get_or_create_user_prefs(user_preferences_collection, user_id)
        hidden_projects = prefs_data.get('hidden_projects', [])
        hidden_categories = prefs_data.get('hidden_categories', [])
        
        # Add project IDs
        for pid in project_ids:
            if pid not in hidden_projects:
                hidden_projects.append(pid)
        
        # Add category if not already present
        category_entry = {
            'name': category_name,
            'pattern': category_pattern,
            'hidden_at': datetime.utcnow()
        }
        # Check if category already exists
        category_exists = any(c.get('name') == category_name for c in hidden_categories)
        if not category_exists:
            hidden_categories.append(category_entry)
        
        doc_ref.update({
            'hidden_projects': hidden_projects,
            'hidden_categories': hidden_categories,
            'updated_at': datetime.utcnow()
        })
        
        return True
    except Exception as e:
        logger.error(f"Error recording category hidden: {e}", exc_info=True)
        return False


def record_project_kept(
    user_preferences_collection,
    user_id: str,
    project_id: str
) -> bool:
    """
    Track when user keeps a project
    
    Args:
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        project_id: Project ID
        
    Returns:
        True if successful
    """
    try:
        doc_ref, prefs_data, is_new = _get_or_create_user_prefs(user_preferences_collection, user_id)
        kept_projects = prefs_data.get('kept_projects', [])
        if project_id not in kept_projects:
            kept_projects.append(project_id)
        doc_ref.update({
            'kept_projects': kept_projects,
            'updated_at': datetime.utcnow()
        })
        return True
    except Exception as e:
        logger.error(f"Error recording project kept: {e}", exc_info=True)
        return False


def analyze_feedback_and_learn(
    user_preferences_collection,
    user_id: str,
    project_id: str,
    feedback_text: str,
    project_data: Dict[str, Any],
    ai_analysis_cache_collection: Optional = None
) -> Dict[str, Any]:
    """
    Store raw feedback text in user preferences for AI-based hiding decisions
    
    Args:
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        project_id: Project ID
        feedback_text: User feedback
        project_data: Project data
        ai_analysis_cache_collection: Optional Firestore collection for AI analysis cache
        
    Returns:
        Dictionary with feedback information
    """
    try:
        # Store raw feedback text in user preferences
        feedback_entry = {
            'id': str(uuid.uuid4()),  # Generate unique ID
            'feedback_text': feedback_text,
            'project_id': project_id,
            'hidden_at': datetime.utcnow()
        }
        
        doc_ref, prefs_data, is_new = _get_or_create_user_prefs(user_preferences_collection, user_id)
        hide_feedback = prefs_data.get('hide_feedback', [])
        hide_feedback.append(feedback_entry)
        
        doc_ref.update({
            'hide_feedback': hide_feedback,
            'hide_feedback_updated': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        })
        
        # Invalidate AI analysis cache for this user since feedback changed
        if ai_analysis_cache_collection is not None:
            query = ai_analysis_cache_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).stream()
            for doc in query:
                doc.reference.delete()
        
        return {'feedback_text': feedback_text, 'project_id': project_id}
    except Exception as e:
        logger.error(f"Error storing feedback: {e}", exc_info=True)
        return {'feedback_text': feedback_text, 'project_id': project_id}


def update_user_preferences(
    user_preferences_collection,
    user_id: str
) -> Dict[str, Any]:
    """
    Analyze hidden/kept projects to learn preferences
    
    Args:
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        
    Returns:
        Updated preferences dictionary
    """
    try:
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if not docs:
            return {}
        
        prefs = docs[0].to_dict()
        
        # This is a placeholder - in a full implementation, we'd analyze
        # hidden vs kept projects to learn preferences
        # For now, just return current preferences
        
        return {
            'hidden_projects': prefs.get('hidden_projects', []),
            'kept_projects': prefs.get('kept_projects', []),
            'hidden_categories': prefs.get('hidden_categories', []),
            'learned_patterns': prefs.get('learned_patterns', [])
        }
    except Exception as e:
        logger.error(f"Error updating user preferences: {e}", exc_info=True)
        return {}


def get_user_preferences(
    user_preferences_collection,
    user_id: str
) -> Dict[str, Any]:
    """
    Get learned preferences
    
    Args:
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        
    Returns:
        Preferences dictionary
    """
    try:
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if not docs:
            return {
                'hidden_projects': [],
                'kept_projects': [],
                'hidden_categories': [],
                'learned_patterns': [],
                'question_answers': [],
                'learned_exclusions': [],
                'hide_feedback': []
            }
        
        prefs = docs[0].to_dict()
        return {
            'hidden_projects': prefs.get('hidden_projects', []),
            'kept_projects': prefs.get('kept_projects', []),
            'hidden_categories': prefs.get('hidden_categories', []),
            'learned_patterns': prefs.get('learned_patterns', []),
            'question_answers': prefs.get('question_answers', []),
            'learned_exclusions': prefs.get('learned_exclusions', []),
            'hide_feedback': prefs.get('hide_feedback', [])
        }
    except Exception as e:
        logger.error(f"Error getting user preferences: {e}", exc_info=True)
        return {
            'hidden_projects': [],
            'kept_projects': [],
            'hidden_categories': [],
            'learned_patterns': [],
            'question_answers': [],
            'learned_exclusions': [],
            'hide_feedback': []
        }


def should_hide_project(
    user_preferences_collection,
    user_id: str,
    project: Dict[str, Any]
) -> bool:
    """
    Use learned preferences to suggest hiding
    
    Args:
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        project: Project data
        
    Returns:
        True if project should be hidden based on preferences
    """
    try:
        prefs = get_user_preferences(user_preferences_collection, user_id)
        
        # Check if project matches any hidden category patterns
        for category in prefs.get('hidden_categories', []):
            pattern = category.get('pattern', {})
            # Simple matching - could be enhanced
            project_text = f"{project.get('name', '')} {project.get('description', '')}".lower()
            keywords = pattern.get('keywords', [])
            if any(keyword.lower() in project_text for keyword in keywords):
                return True
        
        # Check learned patterns
        for learned in prefs.get('learned_patterns', []):
            patterns = learned.get('patterns', {})
            project_text = f"{project.get('name', '')} {project.get('description', '')}".lower()
            keywords = patterns.get('keywords', [])
            if any(keyword.lower() in project_text for keyword in keywords):
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking if should hide project: {e}", exc_info=True)
        return False


def _compute_feedback_hash(feedback_list: List[Dict[str, Any]]) -> str:
    """
    Compute a hash of the feedback list to detect changes
    
    Args:
        feedback_list: List of feedback entries
        
    Returns:
        SHA256 hash string of the feedback list
    """
    # Create a stable representation of feedback for hashing
    # Only include feedback_text and id (to detect additions/deletions/edits)
    feedback_data = []
    for feedback in feedback_list:
        feedback_data.append({
            'id': feedback.get('id', ''),
            'feedback_text': feedback.get('feedback_text', '')
        })
    
    # Sort by id to ensure consistent hashing
    feedback_data.sort(key=lambda x: x.get('id', ''))
    
    # Create hash
    feedback_json = json.dumps(feedback_data, sort_keys=True)
    return hashlib.sha256(feedback_json.encode('utf-8')).hexdigest()


def should_hide_based_on_ai_preferences(
    user_preferences_collection,
    user_id: str,
    project: Dict[str, Any],
    ai_analysis_cache_collection: Optional = None
) -> bool:
    """
    Check if project should be hidden based on user's raw feedback using AI
    
    This function uses AI to analyze the project against all stored raw feedback
    to determine if it should be hidden based on the user's previous reasons.
    Uses timestamp-based caching to avoid expensive AI calls when hide_feedback hasn't changed.
    
    Args:
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        project: Project data
        ai_analysis_cache_collection: Optional Firestore collection for AI analysis cache
        
    Returns:
        True if project should be hidden based on AI analysis of user feedback
    """
    try:
        project_id = project.get('id')
        if not project_id:
            return False
        
        # Get user preferences to check hide_feedback_updated timestamp
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if not docs:
            return False
        
        prefs = docs[0].to_dict()
        
        # Get all stored raw feedback
        hide_feedback = prefs.get('hide_feedback', [])
        if not hide_feedback:
            return False
        
        # Get current hide_feedback_updated timestamp
        current_feedback_timestamp = prefs.get('hide_feedback_updated')
        
        # Check cache if available
        if ai_analysis_cache_collection is not None and current_feedback_timestamp is not None:
            cache_query = ai_analysis_cache_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
            cache_docs = list(cache_query)
            if cache_docs:
                cache_entry = cache_docs[0].to_dict()
                cached_timestamp = cache_entry.get('hide_feedback_updated')
                
                # If timestamps match (no changes to hide_feedback), return cached result
                if cached_timestamp == current_feedback_timestamp:
                    return cache_entry.get('should_hide', False)
        
        # Cache miss or feedback changed - run AI analysis
        should_hide = should_hide_project_based_on_feedback(project, hide_feedback)
        
        # Store result in cache if available
        if ai_analysis_cache_collection is not None:
            cache_data = {
                'user_id': str(user_id),
                'project_id': str(project_id),
                'hide_feedback_updated': current_feedback_timestamp,
                'should_hide': should_hide,
                'cached_at': datetime.utcnow()
            }
            
            cache_query = ai_analysis_cache_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).where(filter=FieldFilter('project_id', '==', str(project_id))).limit(1).stream()
            cache_docs = list(cache_query)
            if cache_docs:
                cache_docs[0].reference.update(cache_data)
            else:
                ai_analysis_cache_collection.add(cache_data)
        
        return should_hide
    except Exception as e:
        logger.error(f"Error checking AI preferences: {e}", exc_info=True)
        return False


def store_question_answer(
    user_preferences_collection,
    user_id: str,
    question_id: str,
    question_text: str,
    answer: bool,
    pattern: Dict[str, Any],
    project_id: Optional[str] = None
) -> bool:
    """
    Store a user's answer to an AI-generated question
    
    Args:
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        question_id: Unique question ID
        question_text: The question text
        answer: User's answer (True/False)
        pattern: Pattern associated with the question
        project_id: Optional project ID that triggered the question
        
    Returns:
        True if successful
    """
    try:
        # Store the question answer
        question_answer = {
            'question_id': question_id,
            'question_text': question_text,
            'answer': answer,
            'pattern': pattern,
            'project_id': project_id,
            'answered_at': datetime.utcnow()
        }
        
        doc_ref, prefs_data, is_new = _get_or_create_user_prefs(user_preferences_collection, user_id)
        question_answers = prefs_data.get('question_answers', [])
        # Check if question already answered
        question_exists = any(q.get('question_id') == question_id for q in question_answers)
        if not question_exists:
            question_answers.append(question_answer)
        
        update_data = {
            'question_answers': question_answers,
            'updated_at': datetime.utcnow()
        }
        
        # If answer is False (user doesn't match the requirement), add to learned exclusions
        if not answer:
            learned_exclusions = prefs_data.get('learned_exclusions', [])
            learned_exclusion = {
                'question_id': question_id,
                'pattern': pattern,
                'learned_at': datetime.utcnow()
            }
            # Check if exclusion already exists
            exclusion_exists = any(e.get('question_id') == question_id for e in learned_exclusions)
            if not exclusion_exists:
                learned_exclusions.append(learned_exclusion)
            update_data['learned_exclusions'] = learned_exclusions
        
        doc_ref.update(update_data)
        
        return True
    except Exception as e:
        logger.error(f"Error storing question answer: {e}", exc_info=True)
        return False


def find_and_auto_hide_similar(
    hidden_projects_log_collection,
    user_preferences_collection,
    user_id: str,
    hidden_project_id: str,
    all_projects: List[Dict[str, Any]],
    similarity_patterns: Dict[str, Any]
) -> List[str]:
    """
    Find similar projects based on feedback and auto-hide them
    
    Args:
        hidden_projects_log_collection: Collection for hidden_projects_log
        user_preferences_collection: Collection for user_preferences
        user_id: User ID
        hidden_project_id: Hidden project ID
        all_projects: List of all projects
        similarity_patterns: Patterns extracted from feedback
        
    Returns:
        List of project IDs that were auto-hidden
    """
    try:
        similar_projects = find_similar_projects(
            user_id,
            hidden_project_id,
            all_projects,
            similarity_patterns
        )
        
        auto_hidden_ids = []
        for project in similar_projects:
            project_id = project.get('id')
            if project_id and not is_project_hidden(hidden_projects_log_collection, user_id, project_id):
                log_hidden_project(
                    hidden_projects_log_collection,
                    user_id,
                    project_id,
                    'auto_similar'
                )
                auto_hidden_ids.append(project_id)
        
        # Update user preferences
        if auto_hidden_ids:
            doc_ref, prefs_data, is_new = _get_or_create_user_prefs(user_preferences_collection, user_id)
            hidden_projects = prefs_data.get('hidden_projects', [])
            for pid in auto_hidden_ids:
                if pid not in hidden_projects:
                    hidden_projects.append(pid)
            doc_ref.update({
                'hidden_projects': hidden_projects,
                'updated_at': datetime.utcnow()
            })
        
        return auto_hidden_ids
    except Exception as e:
        logger.error(f"Error finding and auto-hiding similar projects: {e}", exc_info=True)
        return []
