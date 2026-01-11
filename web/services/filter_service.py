#!/usr/bin/env python3
"""
Filtering service for Respondent.io Manager
"""

import logging

try:
    from ..cache_manager import get_cached_project_details
    from ..db import project_details_collection
except ImportError:
    from cache_manager import get_cached_project_details
    from db import project_details_collection

# Create logger for this module
logger = logging.getLogger(__name__)


def get_project_is_remote(project_id):
    """
    Look up isRemote value from project_details collection by project_id.
    Returns the boolean value or None if not found.
    
    Args:
        project_id: Project ID string
        
    Returns:
        Boolean value of isRemote, or None if not found
    """
    if project_details_collection is None:
        return None
    
    try:
        details = get_cached_project_details(project_details_collection, project_id)
        if details:
            is_remote = details.get('isRemote')
            # Convert to boolean if found
            if is_remote is not None:
                # Convert to boolean if needed (handle string "true"/"false")
                if isinstance(is_remote, str):
                    is_remote = is_remote.lower() in ('true', '1', 'yes')
                return bool(is_remote)
        return None
    except Exception as e:
        logger.error(f"Error getting project isRemote for {project_id}: {e}", exc_info=True)
        return None


def should_hide_project(project, filters, project_details_collection=None, user_id=None, user_preferences_collection=None, ai_analysis_cache_collection=None):
    """Check if a project should be hidden based on filters
    
    Args:
        project: Project data dictionary (must have 'id' field)
        filters: Filter dictionary with min_incentive, min_hourly_rate, isRemote, topics
        project_details_collection: MongoDB collection for project_details
        user_id: Optional user ID for AI preference checking
        user_preferences_collection: Optional MongoDB collection for user_preferences
        ai_analysis_cache_collection: Optional MongoDB collection for AI analysis cache
    """
    min_incentive = filters.get('min_incentive')
    min_hourly_rate = filters.get('min_hourly_rate')
    is_remote = filters.get('isRemote')
    topics = filters.get('topics', [])
    
    # Check simple filters first (fast, deterministic)
    # Check minimum incentive filter
    if min_incentive is not None:
        remuneration = project.get('respondentRemuneration', 0)
        if remuneration < min_incentive:
            return True
    
    # Check minimum hourly rate filter
    if min_hourly_rate is not None:
        remuneration = project.get('respondentRemuneration', 0)
        time_minutes = project.get('timeMinutesRequired', 0)
        if time_minutes > 0:
            hourly_rate = (remuneration / time_minutes) * 60
            if hourly_rate < min_hourly_rate:
                return True
        else:
            # If time is 0, we can't calculate hourly rate, so hide it
            return True
    
    # Check remote filter - use isRemote if available
    if is_remote is True:
        project_id = project.get('id')
        if project_id and project_details_collection is not None:
            project_is_remote = get_project_is_remote(project_id)
            
            # If isRemote is available, check against filter
            if project_is_remote is not None:
                # Hide if project is NOT remote when isRemote filter is enabled
                # (filter "Remote Only" means show only remote, so hide non-remote)
                if not project_is_remote:
                    return True
        # If project doesn't have isRemote field, don't hide based on this filter
        # (could be an old project without detailed data - these will show up in preview)
    
    # Check topics filter
    if topics:
        # Get topics from project (data is now at root level after merging)
        project_topics = project.get('topics', [])
        
        # Check if project has any of the filtered topics
        if isinstance(project_topics, list):
            project_topic_ids = {str(t.get('id')) for t in project_topics if t.get('id')}
            filter_topic_ids = {str(t) for t in topics}
            # If project has any topic in the filter list, hide it
            if project_topic_ids & filter_topic_ids:
                return True
    
    # If project passes all simple filters, check AI-learned preferences
    # Only check if hide_using_ai flag is enabled
    hide_using_ai = filters.get('hide_using_ai', False)
    if hide_using_ai and user_id and user_preferences_collection is not None:
        try:
            from ..preference_learner import should_hide_based_on_ai_preferences
        except ImportError:
            from preference_learner import should_hide_based_on_ai_preferences
        
        if should_hide_based_on_ai_preferences(user_preferences_collection, user_id, project, ai_analysis_cache_collection):
            return True
    
    return False


def apply_filters_to_projects(projects_data, filters, project_details_collection=None, user_id=None, user_preferences_collection=None, ai_analysis_cache_collection=None):
    """Apply user filters to projects list
    
    Args:
        projects_data: Dictionary with 'results' list of projects
        filters: Filter dictionary with min_incentive, min_hourly_rate, isRemote, topics, hide_using_ai
        project_details_collection: MongoDB collection for project_details
        user_id: Optional user ID for AI preference checking
        user_preferences_collection: Optional MongoDB collection for user_preferences
        ai_analysis_cache_collection: Optional MongoDB collection for AI analysis cache
        
    Returns:
        tuple: (filtered_projects_data, hidden_count)
    """
    if not projects_data or not projects_data.get('results'):
        return projects_data, 0
    
    min_incentive = filters.get('min_incentive')
    min_hourly_rate = filters.get('min_hourly_rate')
    is_remote = filters.get('isRemote')
    topics = filters.get('topics', [])
    hide_using_ai = filters.get('hide_using_ai', False)
    
    # If no filters set, return all projects
    if min_incentive is None and min_hourly_rate is None and is_remote is None and not topics and not hide_using_ai:
        return projects_data, 0
    
    original_count = len(projects_data.get('results', []))
    filtered_results = []
    
    for project in projects_data.get('results', []):
        should_hide = False
        
        # Check minimum incentive filter
        if min_incentive is not None:
            remuneration = project.get('respondentRemuneration', 0)
            if remuneration < min_incentive:
                should_hide = True
        
        # Check minimum hourly rate filter
        if min_hourly_rate is not None and not should_hide:
            remuneration = project.get('respondentRemuneration', 0)
            time_minutes = project.get('timeMinutesRequired', 0)
            if time_minutes > 0:
                hourly_rate = (remuneration / time_minutes) * 60
                if hourly_rate < min_hourly_rate:
                    should_hide = True
            else:
                # If time is 0, we can't calculate hourly rate, so hide it
                should_hide = True
        
        # Check remote filter - use isRemote if available
        if is_remote is True and not should_hide:
            project_id = project.get('id')
            if project_id and project_details_collection is not None:
                project_is_remote = get_project_is_remote(project_id)
                
                # If isRemote is available, check against filter
                if project_is_remote is not None:
                    # Hide if project is NOT remote when isRemote filter is enabled
                    if not project_is_remote:
                        should_hide = True
            # If project doesn't have isRemote field, don't hide based on this filter
        
        # Check topics filter
        if topics and not should_hide:
            # Get topics from project (data is now at root level after merging)
            project_topics = project.get('topics', [])
            
            # Check if project has any of the filtered topics
            if isinstance(project_topics, list):
                project_topic_ids = {str(t.get('id')) for t in project_topics if t.get('id')}
                filter_topic_ids = {str(t) for t in topics}
                # If project has any topic in the filter list, hide it
                if project_topic_ids & filter_topic_ids:
                    should_hide = True
        
        # Check AI preferences if hide_using_ai is enabled
        if hide_using_ai and not should_hide and user_id and user_preferences_collection is not None:
            try:
                from ..preference_learner import should_hide_based_on_ai_preferences
            except ImportError:
                from preference_learner import should_hide_based_on_ai_preferences
            
            if should_hide_based_on_ai_preferences(user_preferences_collection, user_id, project, ai_analysis_cache_collection):
                should_hide = True
        
        if not should_hide:
            filtered_results.append(project)
    
    # Create new projects_data with filtered results
    filtered_data = projects_data.copy()
    filtered_data['results'] = filtered_results
    filtered_data['count'] = len(filtered_results)  # Update count
    
    hidden_count = original_count - len(filtered_results)
    
    return filtered_data, hidden_count

