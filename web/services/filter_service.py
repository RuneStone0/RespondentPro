#!/usr/bin/env python3
"""
Filtering service for Respondent.io Manager
"""


def should_hide_project(project, filters):
    """Check if a project should be hidden based on filters"""
    min_incentive = filters.get('min_incentive')
    min_hourly_rate = filters.get('min_hourly_rate')
    research_types = filters.get('research_types', [])
    
    # If no filters set, don't hide anything
    if min_incentive is None and min_hourly_rate is None and not research_types:
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
    
    # Check research type filter
    if research_types:
        project_research_type = project.get('kindOfResearch')
        # If project has no research type, hide it if filter is set
        if project_research_type is None:
            return True
        # If project's research type is not in the allowed list, hide it
        elif project_research_type not in research_types:
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
    research_types = filters.get('research_types', [])
    
    # If no filters set, return all projects
    if min_incentive is None and min_hourly_rate is None and not research_types:
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
        
        # Check research type filter
        if research_types and not should_hide:
            project_research_type = project.get('kindOfResearch')
            # If project has no research type, hide it if filter is set
            if project_research_type is None:
                should_hide = True
            # If project's research type is not in the allowed list, hide it
            elif project_research_type not in research_types:
                should_hide = True
        
        if not should_hide:
            filtered_results.append(project)
    
    # Create new projects_data with filtered results
    filtered_data = projects_data.copy()
    filtered_data['results'] = filtered_results
    filtered_data['count'] = len(filtered_results)  # Update count
    
    hidden_count = original_count - len(filtered_results)
    
    return filtered_data, hidden_count

