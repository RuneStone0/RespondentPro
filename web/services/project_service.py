#!/usr/bin/env python3
"""
Project fetching and management service for Respondent.io Manager
"""

import json
import time
import requests

# Import database collections
try:
    from ..db import projects_cache_collection, hidden_projects_log_collection, project_details_collection, topics_collection, user_preferences_collection, ai_analysis_cache_collection
    from ..services.user_service import check_user_has_credits, get_user_billing_info, check_and_send_credit_notifications
except ImportError:
    from web.db import projects_cache_collection, hidden_projects_log_collection, project_details_collection, topics_collection, user_preferences_collection, ai_analysis_cache_collection
    from services.user_service import check_user_has_credits, get_user_billing_info, check_and_send_credit_notifications

# Import cache manager
try:
    from ..cache_manager import is_cache_fresh, get_cached_projects, refresh_project_cache, mark_projects_hidden_in_cache, get_cached_project_details, cache_project_details
except ImportError:
    from cache_manager import is_cache_fresh, get_cached_projects, refresh_project_cache, mark_projects_hidden_in_cache, get_cached_project_details, cache_project_details

# Import topics service
try:
    from .topics_service import extract_topics_from_project, store_unique_topics
except ImportError:
    from services.topics_service import extract_topics_from_project, store_unique_topics

# Import hidden projects tracker
try:
    from ..hidden_projects_tracker import log_hidden_project, get_hidden_projects_count
except ImportError:
    from hidden_projects_tracker import log_hidden_project, get_hidden_projects_count

# Import respondent auth service
try:
    from .respondent_auth_service import (
        verify_respondent_authentication, get_user_profile, extract_demographic_params_from_mongodb
    )
except ImportError:
    from services.respondent_auth_service import (
        verify_respondent_authentication, get_user_profile, extract_demographic_params_from_mongodb
    )

# Import filter service
try:
    from .filter_service import should_hide_project
except ImportError:
    from services.filter_service import should_hide_project

# Store progress for each user (in-memory, could be moved to Redis/MongoDB for persistence)
hide_progress = {}


def fetch_project_details(session, project_id, project_details_collection=None):
    """
    Fetch detailed project information from Respondent.io API, checking cache first
    
    Args:
        session: Authenticated requests.Session object
        project_id: Project ID to fetch details for
        project_details_collection: Optional MongoDB collection for caching
        
    Returns:
        Dictionary containing the full project details, or None if fetch failed
    """
    # First check cache if collection provided
    if project_details_collection is not None:
        cached_details = get_cached_project_details(project_details_collection, project_id)
        if cached_details:
            print(f"[Project Details] Using cached details for project {project_id}")
            return cached_details
    
    # Fetch from API
    url = f"https://app.respondent.io/v2/projects/view/{project_id}"
    
    headers = {
        "Sec-Fetch-Site": "same-origin"
    }
    
    try:
        start_time = time.time()
        print(f"[Project Details] GET {url}")
        response = session.get(url, headers=headers, timeout=30)
        elapsed_time = time.time() - start_time
        print(f"[Project Details] Response: {response.status_code} ({elapsed_time:.2f}s) - {len(response.content)} bytes")
        
        # Check if response is successful
        if not response.ok:
            print(f"[Project Details] ERROR: {response.status_code} - {response.text[:500]}")
            # If we have cached data, return it even if API fails
            if project_details_collection is not None:
                cached_details = get_cached_project_details(project_details_collection, project_id)
                if cached_details:
                    print(f"[Project Details] API failed, returning cached data for project {project_id}")
                    return cached_details
            return None
        
        # Parse JSON response
        try:
            data = response.json()
            
            # Extract the 'response' field which contains the actual project data
            # The API returns a wrapper with 'response', 'details', etc.
            response_data = data.get('response', data)  # Fallback to full data if 'response' doesn't exist
            
            # Extract project data: move 'project' object to root, keep 'screenerQuestionsLength' if available
            project_data = {}
            if 'project' in response_data and isinstance(response_data.get('project'), dict):
                # Move project data to root
                project_data = response_data['project'].copy()
                # Keep screenerQuestionsLength if it exists at response level
                if 'screenerQuestionsLength' in response_data:
                    project_data['screenerQuestionsLength'] = response_data['screenerQuestionsLength']
            else:
                # Fallback: use response_data as-is if no 'project' field
                project_data = response_data
            
            # Cache only the project data (project at root, with screenerQuestionsLength) if collection provided
            if project_details_collection is not None:
                cache_project_details(project_details_collection, project_id, project_data)
            
            return project_data
        except json.JSONDecodeError as e:
            print(f"[Project Details] Invalid JSON response: {e}")
            # If we have cached data, return it even if parsing fails
            if project_details_collection is not None:
                cached_details = get_cached_project_details(project_details_collection, project_id)
                if cached_details:
                    print(f"[Project Details] JSON parse failed, returning cached data for project {project_id}")
                    return cached_details
            return None
    except Exception as e:
        print(f"[Project Details] ERROR fetching project {project_id}: {e}")
        # If we have cached data, return it even if request fails
        if project_details_collection is not None:
            cached_details = get_cached_project_details(project_details_collection, project_id)
            if cached_details:
                print(f"[Project Details] Request failed, returning cached data for project {project_id}")
                return cached_details
        return None


def fetch_respondent_projects(session, profile_id, page_size=50, page=1, user_id=None, use_cache=True, 
                               gender=None, education_level=None, ethnicity=None, date_of_birth=None, country=None, sort="v4Score"):
    """
    Fetch projects from Respondent.io API, checking cache first if available
    
    Args:
        session: Authenticated requests.Session object
        profile_id: Profile ID to search for
        page_size: Number of results per page (default: 50)
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
        "includeCount": "true",
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


def fetch_all_respondent_projects(session, profile_id, page_size=50, user_id=None, use_cache=True, cookies=None):
    """
    Fetch all pages of projects from Respondent.io API, checking cache first
    
    Uses totalResults-based pagination: fetches the first page with includeCount=true to get
    totalResults, then calculates the total number of pages needed and fetches all pages.
    
    Args:
        session: Authenticated requests.Session object
        profile_id: Profile ID to search for
        page_size: Number of results per page (default: 50)
        user_id: Optional user ID for cache lookup
        use_cache: Whether to use cache (default: True)
        cookies: Optional cookies dict for session validation
        
    Returns:
        tuple: (all_projects_list, total_count)
    """
    # Verify session keys are still valid before fetching (if cookies provided)
    if cookies:
        print(f"[Respondent.io API] Verifying session keys before fetching projects...")
        verification = verify_respondent_authentication(cookies)
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
    
    # Fetch user profile from MongoDB to get demographic parameters
    demographic_params = {}
    if user_id:
        try:
            print(f"[Respondent.io API] Fetching user profile from MongoDB (user_id={user_id})")
            profile_data = get_user_profile(str(user_id))
            if profile_data:
                demographic_params = extract_demographic_params_from_mongodb(profile_data)
                print(f"[Respondent.io API] Extracted demographic params from MongoDB: {demographic_params}")
            else:
                print(f"[Respondent.io API] No profile data found in MongoDB, continuing without demographic filters")
        except Exception as e:
            print(f"[Respondent.io API] Failed to fetch profile from MongoDB (continuing without demographic filters): {e}")
            # Continue without demographic parameters - they're optional
    
    # Fetch all pages using totalResults-based pagination
    print(f"[Respondent.io API] Fetching all projects (profile_id={profile_id}, page_size={page_size})")
    all_projects = []
    total_results = None
    total_pages = None
    
    # Fetch first page to get totalResults
    try:
        page_data = fetch_respondent_projects(
            session, profile_id, page_size, page=1, user_id=None, use_cache=False,
            gender=demographic_params.get('gender'),
            education_level=demographic_params.get('education_level'),
            ethnicity=demographic_params.get('ethnicity'),
            date_of_birth=demographic_params.get('date_of_birth'),
            country=demographic_params.get('country'),
            sort="respondentRemuneration"
        )
        
        # Validate response structure
        if not isinstance(page_data, dict):
            raise Exception(f"Invalid response format for page 1: {type(page_data)}")
        
        # Extract page_results first
        page_results = page_data.get('results', [])
        if not isinstance(page_results, list):
            raise Exception(f"Invalid results format for page 1: {type(page_results)}")
        
        # Extract totalResults from first page response
        total_results = page_data.get('totalResults')
        if total_results is None:
            print(f"[Respondent.io API] WARNING: totalResults not found in response, falling back to count of results")
            # Fallback: use the count of results we got
            total_results = len(page_results)
        
        # Calculate total pages needed (ceiling division)
        total_pages = (total_results + page_size - 1) // page_size
        
        all_projects.extend(page_results)
        print(f"[Respondent.io API] Fetched page 1: {len(page_results)} results (totalResults: {total_results}, total pages: {total_pages})")
        
        # Safety limit to prevent excessive requests
        max_pages = 100
        if total_pages > max_pages:
            print(f"[Respondent.io API] WARNING: total_pages ({total_pages}) exceeds safety limit ({max_pages}), limiting to {max_pages} pages")
            total_pages = max_pages
        
        # Fetch remaining pages (2 through total_pages)
        for page in range(2, total_pages + 1):
            try:
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
                if not isinstance(page_results, list):
                    print(f"[Respondent.io API] Invalid results format for page {page}, stopping pagination")
                    break
                
                results_count = len(page_results)
                if results_count == 0:
                    print(f"[Respondent.io API] Reached last page (got 0 results on page {page})")
                    break
                
                all_projects.extend(page_results)
                print(f"[Respondent.io API] Fetched page {page}: {results_count} results (total: {len(all_projects)} projects)")
                
            except Exception as e:
                print(f"[Respondent.io API] ERROR fetching page {page}: {e}")
                # For subsequent pages, stop pagination but return what we have
                print(f"[Respondent.io API] Stopping pagination due to error, returning {len(all_projects)} projects collected so far")
                break
        
    except Exception as e:
        print(f"[Respondent.io API] ERROR fetching first page: {e}")
        raise
    
    # Use totalResults if available, otherwise use count of fetched projects
    total_count = total_results if total_results is not None else len(all_projects)
    print(f"[Respondent.io API] Completed fetching all projects: {len(all_projects)} projects fetched (totalResults: {total_count})")
    
    # Fetch detailed project information for each project
    print(f"[Project Details] Fetching detailed information for {len(all_projects)} projects...")
    all_topics = []
    enriched_projects = []
    
    for idx, project in enumerate(all_projects):
        project_id = project.get('id')
        if not project_id:
            enriched_projects.append(project)
            continue
        
        try:
            # Fetch detailed project information (will check cache first)
            details = fetch_project_details(session, project_id, project_details_collection)
            
            if details:
                # Merge detailed data into project object
                # The details now contain the project data at root level (after migration/caching)
                # with screenerQuestionsLength if available
                merged_project = project.copy()
                merged_project.update(details)
                enriched_projects.append(merged_project)
                
                # Extract topics from the detailed project
                project_topics = extract_topics_from_project(merged_project)
                all_topics.extend(project_topics)
            else:
                # If details fetch failed, use original project
                enriched_projects.append(project)
                print(f"[Project Details] Warning: Failed to fetch details for project {project_id}, using basic data")
        except Exception as e:
            print(f"[Project Details] Error processing project {project_id}: {e}")
            # Continue with original project if details fetch fails
            enriched_projects.append(project)
        
        # Progress update every 10 projects
        if (idx + 1) % 10 == 0:
            print(f"[Project Details] Processed {idx + 1}/{len(all_projects)} projects...")
    
    print(f"[Project Details] Completed fetching details for {len(enriched_projects)} projects")
    
    # Store unique topics in topics collection
    if topics_collection is not None and all_topics:
        print(f"[Topics] Storing {len(all_topics)} topic references...")
        store_unique_topics(topics_collection, all_topics)
        unique_topic_count = len(set(t.get('id') for t in all_topics if t.get('id')))
        print(f"[Topics] Stored {unique_topic_count} unique topics")
    
    # Cache the enriched results if user_id provided
    if user_id and projects_cache_collection is not None:
        refresh_project_cache(
            projects_cache_collection,
            str(user_id),
            enriched_projects,
            total_count
        )
    
    return enriched_projects, total_count


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
    """Get the current hidden count for a user, handling migration from old user_id to Firebase Auth UID"""
    if hidden_projects_log_collection is None:
        return 0
    try:
        return get_hidden_projects_count(hidden_projects_log_collection, user_id)
    except Exception as e:
        print(f"Error getting hidden count: {e}")
        return 0


def process_and_hide_projects(user_id, session, profile_id, filters, page_size=50, cookies=None):
    """
    Process all projects and hide matching ones via API
    
    Args:
        user_id: User ID for tracking progress
        session: Authenticated requests.Session object
        profile_id: Profile ID to search for
        filters: Filter criteria dict
        page_size: Number of results per page
        cookies: Optional cookies dict for cache refresh
        
    Returns:
        dict with results: total_processed, total_hidden, failures
    """
    user_id_str = str(user_id)
    
    # Check user credits before processing
    try:
        billing_info = get_user_billing_info(user_id)
        limit = billing_info.get('projects_processed_limit', 500)
        processed = billing_info.get('projects_processed_count', 0)
        
        # If limit is None or very large (effectively unlimited), skip check
        if limit is not None and limit < 999999999:
            if processed >= limit:
                raise Exception(f"You have reached your project processing limit ({limit} projects). Please contact support to upgrade.")
    except Exception as e:
        # If it's our credit limit exception, re-raise it
        if "reached your project processing limit" in str(e):
            raise
        # Otherwise, log and continue (don't block on billing info errors)
        print(f"Warning: Could not check billing info: {e}")
    
    # Initialize progress
    hide_progress[user_id_str] = {
        'status': 'in_progress',
        'current': 0,
        'total': 0,
        'hidden': 0,
        'errors': []
    }
    
    try:
        # Fetch all pages - note: cookies not available in this context
        # Session validation will be skipped if cookies not provided
        all_projects, total_count = fetch_all_respondent_projects(session, profile_id, page_size, user_id=user_id, use_cache=True, cookies=None)
        
        hide_progress[user_id_str]['total'] = len(all_projects)
        
        # Find projects that should be hidden
        # Pass user_id and user_preferences_collection for AI filtering when auto-hide or hide_using_ai is enabled
        hide_using_ai = filters.get('hide_using_ai', False)
        auto_hide_enabled = filters.get('auto_hide', False)
        should_check_ai = auto_hide_enabled or hide_using_ai
        
        projects_to_hide = []
        for project in all_projects:
            if should_hide_project(
                project, 
                filters, 
                project_details_collection=project_details_collection,
                user_id=user_id_str if should_check_ai else None,
                user_preferences_collection=user_preferences_collection if should_check_ai else None,
                ai_analysis_cache_collection=ai_analysis_cache_collection if should_check_ai else None
            ):
                projects_to_hide.append(project)
        
        total_to_hide = len(projects_to_hide)
        print(f"[Project Service] Found {total_to_hide} projects to hide out of {len(all_projects)} total projects")
        print(f"[Project Service] Filters: {filters}")
        hidden_count = 0
        errors = []
        hidden_project_ids = []
        
        # Determine hidden_method based on whether auto-hide is enabled
        auto_hide_enabled = filters.get('auto_hide', False)
        hidden_method = 'auto' if auto_hide_enabled else 'manual'
        
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
                    # Log to hidden_projects_log with correct method
                    if hidden_projects_log_collection is not None:
                        log_hidden_project(
                            hidden_projects_log_collection,
                            str(user_id),
                            project_id,
                            hidden_method
                        )
                else:
                    errors.append(project_id)
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
        
        # Update cache to remove hidden projects
        if projects_cache_collection is not None and hidden_project_ids:
            mark_projects_hidden_in_cache(projects_cache_collection, user_id_str, hidden_project_ids)
        
        # Refresh cache from API to get updated project list after hiding
        if projects_cache_collection is not None and hidden_project_ids:
            try:
                print(f"[Project Service] Refreshing cache after hiding {len(hidden_project_ids)} projects")
                # Fetch fresh data from API (bypassing cache)
                all_projects_refreshed, total_count_refreshed = fetch_all_respondent_projects(
                    session, profile_id, page_size, user_id=user_id, use_cache=False, 
                    cookies=cookies
                )
                print(f"[Project Service] Cache refreshed: {len(all_projects_refreshed)} projects now in cache")
            except Exception as e:
                print(f"[Project Service] Error refreshing cache after hiding: {e}")
                # Don't fail the whole operation if cache refresh fails
        
        # Update progress to completed
        hide_progress[user_id_str]['status'] = 'completed'
        
        # Check and send credit notifications after processing
        try:
            check_and_send_credit_notifications(user_id)
        except Exception as e:
            print(f"Error checking credit notifications: {e}")
            # Don't fail the operation if notification check fails
        
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

