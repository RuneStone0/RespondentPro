#!/usr/bin/env python3
"""
Project fetching and management service for Respondent.io Manager
"""

import json
import time
import requests

# Import database collections
try:
    from ..db import projects_cache_collection, hidden_projects_log_collection
except ImportError:
    from web.db import projects_cache_collection, hidden_projects_log_collection

# Import cache manager
try:
    from ..cache_manager import is_cache_fresh, get_cached_projects, refresh_project_cache, mark_projects_hidden_in_cache
except ImportError:
    from cache_manager import is_cache_fresh, get_cached_projects, refresh_project_cache, mark_projects_hidden_in_cache

# Import hidden projects tracker
try:
    from ..hidden_projects_tracker import log_hidden_project, get_hidden_projects_count
except ImportError:
    from hidden_projects_tracker import log_hidden_project, get_hidden_projects_count

# Import respondent auth service
try:
    from .respondent_auth_service import (
        verify_respondent_authentication, fetch_user_profile, extract_demographic_params
    )
except ImportError:
    from services.respondent_auth_service import (
        verify_respondent_authentication, fetch_user_profile, extract_demographic_params
    )

# Import filter service
try:
    from .filter_service import should_hide_project
except ImportError:
    from services.filter_service import should_hide_project

# Store progress for each user (in-memory, could be moved to Redis/MongoDB for persistence)
hide_progress = {}


def fetch_respondent_projects(session, profile_id, page_size=15, page=1, user_id=None, use_cache=True, 
                               gender=None, education_level=None, ethnicity=None, date_of_birth=None, country=None, sort="v4Score"):
    """
    Fetch projects from Respondent.io API, checking cache first if available
    
    Args:
        session: Authenticated requests.Session object
        profile_id: Profile ID to search for
        page_size: Number of results per page (default: 15)
        page: Page number (default: 1)
        user_id: Optional user ID for cache lookup
        use_cache: Whether to use cache (default: True)
        gender: Optional gender filter (e.g., "male")
        education_level: Optional education level filter (e.g., "bachelordegree")
        ethnicity: Optional ethnicity filter (e.g., "whitecaucasian")
        date_of_birth: Optional date of birth filter (e.g., "1988-06-22")
        country: Optional country filter (e.g., "US")
        sort: Sort order (default: "v4Score", can be "respondentRemuneration")
        
    Returns:
        Dictionary containing the API response with projects
    """
    # Check cache first if user_id provided and cache is enabled
    if use_cache and user_id and projects_cache_collection is not None:
        cache_fresh = is_cache_fresh(projects_cache_collection, str(user_id))
        if cache_fresh:
            cached = get_cached_projects(projects_cache_collection, str(user_id))
            if cached and cached.get('projects'):
                # Return cached projects (for now, return all - pagination can be added later)
                return {
                    'results': cached['projects'],
                    'count': cached.get('total_count', len(cached['projects'])),
                    'page': page,
                    'pageSize': page_size
                }
    
    # Fetch from API
    base_url = "https://app.respondent.io/api/v4/matching/projects/search/profiles"
    
    # Build query parameters
    params = {
        "maxIncentive": 1000,
        "minIncentive": 5,
        "maxTimeMinutesRequired": 800,
        "minTimeMinutesRequired": 5,
        "sort": sort,
        "pageSize": page_size,
        "page": page,
        "includeCount": "false",
        "showHiddenProjects": "false",
        "onlyShowMatched": "false",
        "showEligible": "true",
    }
    
    # Add optional demographic parameters if provided
    if gender:
        params["gender"] = gender
    if education_level:
        params["educationLevel"] = education_level
    if ethnicity:
        params["ethnicity"] = ethnicity
    if date_of_birth:
        params["dateOfBirth"] = date_of_birth
    if country:
        params["country"] = country
    
    # Construct the full URL
    url = f"{base_url}/{profile_id}"
    
    # Add additional headers for the project request
    headers = {
        "Sec-Fetch-Site": "same-origin"
    }
    
    # Make the request
    start_time = time.time()
    print(f"[Respondent.io API] GET {url} (page={page}, page_size={page_size})")
    response = session.get(url, params=params, headers=headers, timeout=30)
    elapsed_time = time.time() - start_time
    print(f"[Respondent.io API] Response: {response.status_code} ({elapsed_time:.2f}s) - {len(response.content)} bytes")
    
    # Check if response is successful
    if not response.ok:
        print(f"[Respondent.io API] ERROR: {response.status_code} - {response.text[:500]}")
        raise Exception(f"Failed to fetch projects: {response.status_code} - {response.text[:500]}")
    
    # Parse JSON response
    try:
        data = response.json()
        
        # Don't cache single pages - only cache when fetching all pages via fetch_all_respondent_projects
        # This prevents caching incomplete data
        
        return data
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON response: {e}")


def fetch_all_respondent_projects(session, profile_id, page_size=15, user_id=None, use_cache=True, cookies=None, authorization=None):
    """
    Fetch all pages of projects from Respondent.io API, checking cache first
    
    Uses heuristic pagination: if a page returns exactly page_size results, assume there's
    a next page and continue fetching until a page returns fewer than page_size results.
    
    Args:
        session: Authenticated requests.Session object
        profile_id: Profile ID to search for
        page_size: Number of results per page (default: 15)
        user_id: Optional user ID for cache lookup
        use_cache: Whether to use cache (default: True)
        cookies: Optional cookies dict for session validation
        authorization: Optional authorization header for session validation
        
    Returns:
        tuple: (all_projects_list, total_count)
    """
    # Verify session keys are still valid before fetching (if cookies/authorization provided)
    if cookies and authorization is not None:
        print(f"[Respondent.io API] Verifying session keys before fetching projects...")
        verification = verify_respondent_authentication(cookies, authorization)
        if not verification.get('success'):
            error_msg = verification.get('message', 'Session keys are invalid or expired')
            print(f"[Respondent.io API] {error_msg}")
            raise Exception(f"Session keys are invalid or expired: {error_msg}")
        print(f"[Respondent.io API] Session keys verified successfully")
    elif cookies:
        # Only cookies provided, still try to verify
        print(f"[Respondent.io API] Verifying session keys before fetching projects...")
        verification = verify_respondent_authentication(cookies, None)
        if not verification.get('success'):
            error_msg = verification.get('message', 'Session keys are invalid or expired')
            print(f"[Respondent.io API] {error_msg}")
            raise Exception(f"Session keys are invalid or expired: {error_msg}")
        print(f"[Respondent.io API] Session keys verified successfully")
    
    # Check cache first if user_id provided and cache is enabled
    if use_cache and user_id and projects_cache_collection is not None:
        cache_fresh = is_cache_fresh(projects_cache_collection, str(user_id))
        if cache_fresh:
            cached = get_cached_projects(projects_cache_collection, str(user_id))
            if cached and cached.get('projects'):
                return cached['projects'], cached.get('total_count', len(cached['projects']))
    
    # Fetch user profile to get demographic parameters (optional - if it fails, continue without them)
    demographic_params = {}
    if cookies and authorization is not None:
        try:
            # Get user_id from authentication verification
            print(f"[Respondent.io API] Getting user_id for profile fetch...")
            verification = verify_respondent_authentication(cookies, authorization)
            user_id_for_profile = verification.get('user_id')
            
            if user_id_for_profile:
                print(f"[Respondent.io API] Fetching user profile (user_id={user_id_for_profile})")
                profile_data = fetch_user_profile(session, user_id_for_profile)
                if profile_data:
                    demographic_params = extract_demographic_params(profile_data)
                    print(f"[Respondent.io API] Extracted demographic params: {demographic_params}")
                else:
                    print(f"[Respondent.io API] No profile data returned, continuing without demographic filters")
            else:
                print(f"[Respondent.io API] Could not extract user_id from authentication, skipping profile fetch")
        except Exception as e:
            print(f"[Respondent.io API] Failed to fetch profile (continuing without demographic filters): {e}")
            # Continue without demographic parameters - they're optional
    
    # Fetch all pages using heuristic pagination
    print(f"[Respondent.io API] Fetching all projects (profile_id={profile_id}, page_size={page_size})")
    all_projects = []
    page = 1
    max_pages = 20  # Safety limit to prevent infinite loops
    
    while page <= max_pages:
        try:
            # Use demographic parameters from user profile
            page_data = fetch_respondent_projects(
                session, profile_id, page_size, page=page, user_id=None, use_cache=False,
                gender=demographic_params.get('gender'),
                education_level=demographic_params.get('education_level'),
                ethnicity=demographic_params.get('ethnicity'),
                date_of_birth=demographic_params.get('date_of_birth'),
                country=demographic_params.get('country'),
                sort="respondentRemuneration"
            )
            
            # Validate response structure
            if not isinstance(page_data, dict):
                print(f"[Respondent.io API] Invalid response format for page {page}, stopping pagination")
                break
            
            page_results = page_data.get('results', [])
            
            # Handle case where results might be None or not a list
            if not isinstance(page_results, list):
                print(f"[Respondent.io API] Invalid results format for page {page}, stopping pagination")
                break
            
            results_count = len(page_results)
            
            # If we got 0 results, we've reached the end
            if results_count == 0:
                print(f"[Respondent.io API] Reached last page (got 0 results on page {page})")
                break
            
            all_projects.extend(page_results)
            print(f"[Respondent.io API] Fetched page {page}: {results_count} results (total: {len(all_projects)} projects)")
            
            # Continue fetching if we got exactly page_size results (definitely more pages)
            # Also continue if we got fewer than page_size but > 0 (might be more pages, check next page)
            # Only stop if we get 0 results (handled above)
            if results_count == page_size:
                # Got exactly page_size, definitely more pages available
                page += 1
            elif results_count < page_size:
                # Got fewer than page_size, but check next page to confirm it's empty
                # If next page returns 0, we'll stop; if it returns > 0, we continue
                page += 1
            
        except Exception as e:
            print(f"[Respondent.io API] ERROR fetching page {page}: {e}")
            # If we have some results, continue with what we have
            # If this is the first page and it fails, we should raise the error
            if page == 1:
                raise
            # For subsequent pages, stop pagination but return what we have
            print(f"[Respondent.io API] Stopping pagination due to error, returning {len(all_projects)} projects collected so far")
            break
    
    if page > max_pages:
        print(f"[Respondent.io API] WARNING: Reached maximum page limit ({max_pages}), stopping pagination")
    
    total_count = len(all_projects)
    print(f"[Respondent.io API] Completed fetching all projects: {total_count} projects total across {page} page(s)")
    
    # Cache the results if user_id provided
    if user_id and projects_cache_collection is not None:
        refresh_project_cache(
            projects_cache_collection,
            str(user_id),
            all_projects,
            total_count
        )
    
    return all_projects, total_count


def hide_project_via_api(session, project_id):
    """
    Hide a single project via Respondent.io API
    
    Args:
        session: Authenticated requests.Session object
        project_id: Project ID to hide
        
    Returns:
        bool: True if successful, False otherwise
    """
    url = f"https://app.respondent.io/v2/profiles/project/{project_id}/hidden"
    
    headers = {
        "Sec-Fetch-Site": "same-origin"
    }
    
    try:
        start_time = time.time()
        print(f"[Respondent.io API] POST {url} (project_id={project_id})")
        response = session.post(url, headers=headers, timeout=30)
        elapsed_time = time.time() - start_time
        print(f"[Respondent.io API] Response: {response.status_code} ({elapsed_time:.2f}s)")
        return response.ok
    except Exception as e:
        print(f"[Respondent.io API] ERROR hiding project {project_id}: {e}")
        return False


def get_hidden_count(user_id):
    """Get the current hidden count for a user"""
    if hidden_projects_log_collection is None:
        return 0
    try:
        return get_hidden_projects_count(hidden_projects_log_collection, user_id)
    except Exception as e:
        print(f"Error getting hidden count: {e}")
        return 0


def process_and_hide_projects(user_id, session, profile_id, filters, page_size=15):
    """
    Process all projects and hide matching ones via API
    
    Args:
        user_id: User ID for tracking progress
        session: Authenticated requests.Session object
        profile_id: Profile ID to search for
        filters: Filter criteria dict
        page_size: Number of results per page
        
    Returns:
        dict with results: total_processed, total_hidden, failures
    """
    user_id_str = str(user_id)
    
    # Initialize progress
    hide_progress[user_id_str] = {
        'status': 'in_progress',
        'current': 0,
        'total': 0,
        'hidden': 0,
        'errors': []
    }
    
    try:
        # Fetch all pages - note: cookies and authorization not available in this context
        # Session validation will be skipped if cookies/authorization not provided
        all_projects, total_count = fetch_all_respondent_projects(session, profile_id, page_size, user_id=user_id, use_cache=True, cookies=None, authorization=None)
        
        hide_progress[user_id_str]['total'] = len(all_projects)
        
        # Find projects that should be hidden
        projects_to_hide = []
        for project in all_projects:
            if should_hide_project(project, filters):
                projects_to_hide.append(project)
        
        total_to_hide = len(projects_to_hide)
        hidden_count = 0
        errors = []
        hidden_project_ids = []
        
        # Hide each project
        for idx, project in enumerate(projects_to_hide):
            project_id = project.get('id')
            if project_id:
                hide_progress[user_id_str]['current'] = idx + 1
                success = hide_project_via_api(session, project_id)
                if success:
                    hidden_count += 1
                    hidden_project_ids.append(project_id)
                    hide_progress[user_id_str]['hidden'] = hidden_count
                    # Log to hidden_projects_log
                    if hidden_projects_log_collection is not None:
                        log_hidden_project(
                            hidden_projects_log_collection,
                            str(user_id),
                            project_id,
                            'manual'
                        )
                else:
                    errors.append(project_id)
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
        
        # Update cache to remove hidden projects
        if projects_cache_collection is not None and hidden_project_ids:
            mark_projects_hidden_in_cache(projects_cache_collection, user_id_str, hidden_project_ids)
        
        # Update progress to completed
        hide_progress[user_id_str]['status'] = 'completed'
        
        return {
            'total_processed': len(all_projects),
            'total_to_hide': total_to_hide,
            'total_hidden': hidden_count,
            'errors': errors
        }
        
    except Exception as e:
        hide_progress[user_id_str]['status'] = 'error'
        hide_progress[user_id_str]['error'] = str(e)
        raise


def get_hide_progress(user_id):
    """Get the current hide progress for a user"""
    user_id_str = str(user_id)
    return hide_progress.get(user_id_str, {
        'status': 'not_started',
        'current': 0,
        'total': 0,
        'hidden': 0,
        'errors': []
    })

