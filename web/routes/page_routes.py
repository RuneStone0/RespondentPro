#!/usr/bin/env python3
"""
Page routes for Respondent.io Manager
"""

from flask import Blueprint, render_template, session, redirect, url_for
from datetime import datetime

# Import services
try:
    from ..services.user_service import load_user_config, load_user_filters, save_user_config
    from ..services.respondent_auth_service import create_respondent_session, verify_respondent_authentication
    from ..services.project_service import fetch_all_respondent_projects, get_hidden_count
    from ..cache_manager import get_cache_stats
    from ..db import projects_cache_collection
except ImportError:
    from services.user_service import load_user_config, load_user_filters, save_user_config
    from services.respondent_auth_service import create_respondent_session, verify_respondent_authentication
    from services.project_service import fetch_all_respondent_projects, get_hidden_count
    from cache_manager import get_cache_stats
    from db import projects_cache_collection

bp = Blueprint('page', __name__)


@bp.route('/dashboard')
def dashboard():
    """Dashboard - redirect to projects page (session keys now configured via modal)"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return redirect(url_for('page.projects'))


@bp.route('/projects')
def projects():
    """Projects page - list all available projects"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    username = session.get('username', 'User')
    config = load_user_config(user_id)
    filters = load_user_filters(user_id)
    
    # Check if user has configured session keys
    has_config = config is not None and config.get('cookies', {}).get('respondent.session.sid')
    show_config_modal = not has_config
    
    projects_data = None
    error = None
    hidden_count = 0
    
    # Only try to fetch projects if config exists
    if has_config:
        try:
            # Get profile_id from config or try to verify authentication to get it
            profile_id = config.get('profile_id')
            
            if not profile_id:
                # Try to get profile_id by verifying authentication
                verification = verify_respondent_authentication(
                    cookies=config.get('cookies', {}),
                    authorization=config.get('authorization')
                )
                if verification.get('success') and verification.get('profile_id'):
                    profile_id = verification.get('profile_id')
                    # Save the profile_id for future use
                    save_user_config(user_id, config, profile_id=profile_id)
                    config['profile_id'] = profile_id
                else:
                    # Credentials are invalid, show modal
                    show_config_modal = True
            
            if profile_id:
                # Create authenticated session
                req_session = create_respondent_session(
                    cookies=config.get('cookies', {}),
                    authorization=config.get('authorization')
                )
                
                # Fetch all projects (will use cache if available, otherwise fetches all pages)
                all_projects, total_count = fetch_all_respondent_projects(
                    session=req_session,
                    profile_id=profile_id,
                    page_size=50,
                    user_id=user_id,
                    use_cache=True,
                    cookies=config.get('cookies', {}),
                    authorization=config.get('authorization')
                )
                
                # Sort projects by hourly rate (highest first)
                def calculate_hourly_rate(project):
                    remuneration = project.get('respondentRemuneration', 0) or 0
                    time_minutes = project.get('timeMinutesRequired', 0) or 0
                    if time_minutes > 0:
                        return (remuneration / time_minutes) * 60
                    return 0
                
                sorted_projects = sorted(
                    all_projects,
                    key=calculate_hourly_rate,
                    reverse=True
                )
                
                # Convert to the format expected by the template
                projects_data = {
                    'results': sorted_projects,
                    'count': total_count,
                    'page': 1,
                    'pageSize': len(sorted_projects)
                }
                
                # Get persistent hidden count from MongoDB
                hidden_count = get_hidden_count(user_id)
            else:
                # Unable to determine profile ID, show modal
                show_config_modal = True
        except Exception as e:
            # If authentication fails or API error occurs, show modal
            import traceback
            print(f"Error fetching projects: {traceback.format_exc()}")
            show_config_modal = True
    
    # Get cache refresh time and total count
    cache_refreshed_utc = None
    total_projects_count = 0
    if projects_cache_collection is not None:
        try:
            cache_stats = get_cache_stats(projects_cache_collection, str(user_id))
            last_updated = cache_stats.get('last_updated')
            total_projects_count = cache_stats.get('total_count', 0)
            if last_updated:
                if isinstance(last_updated, datetime):
                    cache_refreshed_utc = last_updated.isoformat() + 'Z'
                elif isinstance(last_updated, str):
                    if not last_updated.endswith('Z') and '+' not in last_updated:
                        cache_refreshed_utc = last_updated + 'Z'
                    else:
                        cache_refreshed_utc = last_updated
                else:
                    try:
                        if hasattr(last_updated, 'isoformat'):
                            cache_refreshed_utc = last_updated.isoformat() + 'Z'
                        elif hasattr(last_updated, 'strftime'):
                            cache_refreshed_utc = datetime.fromtimestamp(last_updated.timestamp()).isoformat() + 'Z'
                        else:
                            cache_refreshed_utc = str(last_updated)
                    except:
                        cache_refreshed_utc = None
        except Exception as e:
            print(f"Error getting cache refresh time: {e}")
            cache_refreshed_utc = None
    
    return render_template(
        'projects.html',
        username=username,
        config=config,
        projects=projects_data,
        has_config=has_config,
        show_config_modal=show_config_modal,
        filters=filters,
        cache_refreshed_utc=cache_refreshed_utc,
        error=error,
        hidden_count=hidden_count,
        total_projects_count=total_projects_count
    )

