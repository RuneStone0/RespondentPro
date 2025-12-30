#!/usr/bin/env python3
"""
Filtering service for Respondent.io Manager
"""


def get_project_is_remote(project):
    """
    Extract isRemote value from project, checking all possible locations.
    Returns the boolean value or None if not found.
    """
    project_is_remote = None
    # Check nested project.project.isRemote
    if isinstance(project.get('project'), dict):
        project_is_remote = project.get('project', {}).get('isRemote')
    # Check details.isRemote (for cached documents that weren't fully merged)
    if project_is_remote is None and isinstance(project.get('details'), dict):
        project_is_remote = project.get('details', {}).get('isRemote')
    # Check root level isRemote (after merge, details contents are at root)
    if project_is_remote is None:
        project_is_remote = project.get('isRemote')
    # Also check if details has a nested details key (some cached structures)
    if project_is_remote is None and isinstance(project.get('details'), dict):
        nested_details = project.get('details', {}).get('details')
        if isinstance(nested_details, dict):
            project_is_remote = nested_details.get('isRemote')
    
    # Convert to boolean if found
    if project_is_remote is not None:
        # Convert to boolean if needed (handle string "true"/"false")
        if isinstance(project_is_remote, str):
            project_is_remote = project_is_remote.lower() in ('true', '1', 'yes')
        project_is_remote = bool(project_is_remote)
    
    return project_is_remote


def should_hide_project(project, filters):
    """Check if a project should be hidden based on filters"""
    min_incentive = filters.get('min_incentive')
    min_hourly_rate = filters.get('min_hourly_rate')
    is_remote = filters.get('isRemote')
    topics = filters.get('topics', [])
    
    # If no filters set, don't hide anything
    if min_incentive is None and min_hourly_rate is None and is_remote is None and not topics:
        return False
    
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
        project_is_remote = get_project_is_remote(project)
        
        # If isRemote is available, check against filter
        if project_is_remote is not None:
            # Hide if project is remote and isRemote filter is enabled
            if project_is_remote:
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
    
    return False


def apply_filters_to_projects(projects_data, filters):
    """Apply user filters to projects list
    
    Returns:
        tuple: (filtered_projects_data, hidden_count)
    """
    if not projects_data or not projects_data.get('results'):
        return projects_data, 0
    
    min_incentive = filters.get('min_incentive')
    min_hourly_rate = filters.get('min_hourly_rate')
    is_remote = filters.get('isRemote')
    topics = filters.get('topics', [])
    
    # If no filters set, return all projects
    if min_incentive is None and min_hourly_rate is None and is_remote is None and not topics:
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
            project_is_remote = get_project_is_remote(project)
            
            # If isRemote is available, check against filter
            if project_is_remote is not None:
                # Hide if project is remote and isRemote filter is enabled
                if project_is_remote:
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
        
        if not should_hide:
            filtered_results.append(project)
    
    # Create new projects_data with filtered results
    filtered_data = projects_data.copy()
    filtered_data['results'] = filtered_results
    filtered_data['count'] = len(filtered_results)  # Update count
    
    hidden_count = original_count - len(filtered_results)
    
    return filtered_data, hidden_count

