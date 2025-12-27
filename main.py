#!/usr/bin/env python3
"""
CLI tool for Respondent.io API management
"""

import click
import requests
import json
import sys
from typing import Optional, Dict, Any
from pathlib import Path


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    Load configuration from JSON file
    
    Args:
        config_path: Path to the config file
        
    Returns:
        Dictionary containing configuration
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    return config


def create_session(cookies: Dict[str, str], authorization: Optional[str] = None) -> requests.Session:
    """
    Create a requests session with cookies and authorization header
    
    Args:
        cookies: Dictionary of cookie name-value pairs
        authorization: Authorization header value (e.g., "Bearer <token>")
        
    Returns:
        Configured requests.Session object
    """
    session = requests.Session()
    
    # Set cookies in the session
    for name, value in cookies.items():
        if value:  # Only set non-empty cookies
            session.cookies.set(name, value)
    
    # Set default headers
    session.headers.update({
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Set Authorization header if provided
    if authorization:
        session.headers.update({"Authorization": authorization})
    
    return session


def _output_request_debug_info(response: requests.Response, request_url: str):
    """
    Output HTTP request details for debugging
    
    Args:
        response: The response object from the request
        request_url: The URL that was requested
    """
    click.echo("\n" + "="*80, err=True)
    click.echo("HTTP REQUEST DEBUG INFO", err=True)
    click.echo("="*80, err=True)
    click.echo(f"Request URL: {request_url}", err=True)
    click.echo(f"Request Method: {response.request.method}", err=True)
    click.echo(f"\nRequest Headers:", err=True)
    for key, value in response.request.headers.items():
        # Mask Authorization header for security
        if key.lower() == 'authorization':
            masked_value = value[:20] + "..." if len(value) > 20 else "***"
            click.echo(f"  {key}: {masked_value}", err=True)
        else:
            click.echo(f"  {key}: {value}", err=True)
    
    # Show cookies if any
    if response.request.headers.get('Cookie'):
        click.echo(f"\nCookies: {response.request.headers.get('Cookie')[:200]}...", err=True)
    
    click.echo(f"\nResponse Status: {response.status_code}", err=True)
    click.echo(f"Response Headers:", err=True)
    for key, value in response.headers.items():
        click.echo(f"  {key}: {value}", err=True)
    
    click.echo(f"\nResponse Body (first 1000 chars):", err=True)
    click.echo(response.text[:1000], err=True)
    click.echo("="*80 + "\n", err=True)


def verify_authentication(session: requests.Session, verbose: bool = True) -> bool:
    """
    Verify authentication by checking the /v2/respondents/me endpoint
    
    Args:
        session: Requests session with cookies
        verbose: Whether to print detailed output
        
    Returns:
        True if authenticated, False otherwise
    """
    auth_url = "https://app.respondent.io/v2/respondents/me"
    
    try:
        if verbose:
            click.echo("Verifying authentication...")
            click.echo(f"Checking: {auth_url}")
        
        response = session.get(auth_url, timeout=30)
        
        if verbose:
            click.echo(f"Response status: {response.status_code}")
        
        # Check if we got a successful response (200)
        if response.status_code == 200:
            # Try to parse JSON response
            try:
                user_data = response.json()
                
                # Extract profile ID and first name from nested response structure
                profile_id = None
                first_name = None
                
                if isinstance(user_data, dict) and 'response' in user_data:
                    response_data = user_data.get('response', {})
                    
                    # Get profile ID from response.profile.id
                    if 'profile' in response_data and isinstance(response_data['profile'], dict):
                        profile_id = response_data['profile'].get('id')
                    
                    # Get first name from response.firstName
                    first_name = response_data.get('firstName')
                
                # Authentication failed if we can't extract required fields
                if not profile_id or not first_name:
                    if verbose:
                        click.echo("❌ Authentication failed: Unable to extract Profile ID and First Name from response", err=True)
                        if not profile_id:
                            click.echo("   Missing: Profile ID", err=True)
                        if not first_name:
                            click.echo("   Missing: First Name", err=True)
                        _output_request_debug_info(response, auth_url)
                    return False
                
                # Authentication successful - display the extracted values
                if verbose:
                    click.echo(f"✅ Authentication successful!")
                    click.echo(f"   Profile ID: {profile_id}")
                    click.echo(f"   First Name: {first_name}")
                
                return True
            except json.JSONDecodeError:
                if verbose:
                    click.echo("❌ Authentication failed: Invalid JSON response", err=True)
                    _output_request_debug_info(response, auth_url)
                return False
        elif response.status_code == 401:
            if verbose:
                click.echo("❌ Authentication failed: Unauthorized (401)", err=True)
                _output_request_debug_info(response, auth_url)
            return False
        elif response.status_code == 403:
            if verbose:
                click.echo("❌ Authentication failed: Forbidden (403)", err=True)
                _output_request_debug_info(response, auth_url)
            return False
        else:
            if verbose:
                click.echo(f"⚠️  Unexpected status code: {response.status_code}", err=True)
                _output_request_debug_info(response, auth_url)
            return False
            
    except requests.exceptions.RequestException as e:
        if verbose:
            click.echo(f"❌ Error verifying authentication: {e}", err=True)
            # Try to output request info if available
            if hasattr(e, 'request') and e.request:
                click.echo(f"\nRequest URL: {e.request.url}", err=True)
                click.echo(f"Request Method: {e.request.method}", err=True)
                click.echo(f"Request Headers: {dict(e.request.headers)}", err=True)
        return False


def fetch_projects(
    session: requests.Session,
    profile_id: str = "691f593b2e2ac1bd7fa84915",
    max_incentive: int = 1000,
    min_incentive: int = 5,
    max_time_minutes: int = 800,
    min_time_minutes: int = 5,
    sort: str = "v4Score",
    page_size: int = 15,
    page: int = 1,
    include_count: bool = True,
    gender: Optional[str] = "male",
    education_level: Optional[str] = "bachelordegree",
    ethnicity: Optional[str] = "whitecaucasian",
    date_of_birth: Optional[str] = "1988-06-22",
    show_hidden_projects: bool = False,
    only_show_matched: bool = False,
    show_eligible: bool = True,
    country: Optional[str] = "US",
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Fetch projects from Respondent.io API
    
    Args:
        session: Requests session with authentication cookies
        profile_id: Profile ID to search for
        ... (other parameters)
        verbose: Whether to print detailed output
    
    Returns:
        Dictionary containing the API response
    """
    base_url = "https://app.respondent.io/api/v4/matching/projects/search/profiles"
    
    # Build query parameters
    params = {
        "maxIncentive": max_incentive,
        "minIncentive": min_incentive,
        "maxTimeMinutesRequired": max_time_minutes,
        "minTimeMinutesRequired": min_time_minutes,
        "sort": sort,
        "pageSize": page_size,
        "page": page,
        "includeCount": str(include_count).lower(),
        "showHiddenProjects": str(show_hidden_projects).lower(),
        "onlyShowMatched": str(only_show_matched).lower(),
        "showEligible": str(show_eligible).lower(),
    }
    
    # Add optional parameters if provided
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
    
    try:
        if verbose:
            click.echo(f"\nFetching projects from: {url}")
            click.echo(f"Parameters: {params}")
        
        # Add additional headers for the project request
        headers = {
            "Sec-Fetch-Site": "same-origin"
        }
        
        # Make the request using the session (cookies are already in the session)
        response = session.get(url, params=params, headers=headers, timeout=30)
        
        if verbose:
            click.echo(f"Response status code: {response.status_code}")
        
        # Check if response is successful
        if not response.ok:
            if verbose:
                click.echo(f"Error response text: {response.text[:500]}", err=True)
            response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get('Content-Type', '')
        if verbose:
            click.echo(f"Content-Type: {content_type}")
        
        # Try to parse JSON response
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            click.echo(f"\nError: Response is not valid JSON", err=True)
            click.echo(f"JSON decode error: {e}", err=True)
            click.echo(f"Response status: {response.status_code}", err=True)
            click.echo(f"Response text (first 1000 chars):\n{response.text[:1000]}", err=True)
            raise
        
        return data
        
    except requests.exceptions.RequestException as e:
        click.echo(f"Error making request: {e}", err=True)
        if hasattr(e, 'response') and e.response is not None:
            click.echo(f"Response status code: {e.response.status_code}", err=True)
            click.echo(f"Response text (first 1000 chars): {e.response.text[:1000]}", err=True)
        raise


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Respondent.io API management CLI tool"""
    pass


@cli.command()
@click.option('--config', '-c', default='config.json', help='Path to config file')
@click.option('--verbose/--no-verbose', default=True, help='Show detailed output')
def auth(config, verbose):
    """Test authentication with Respondent.io"""
    try:
        # Load configuration
        config_data = load_config(config)
        cookies = config_data.get("cookies", {})
        authorization = config_data.get("authorization")
        
        if not cookies:
            click.echo("❌ No cookies found in config file", err=True)
            sys.exit(1)
        
        # Create session with cookies and authorization header
        session = create_session(cookies, authorization=authorization)
        
        # Verify authentication
        is_authenticated = verify_authentication(session, verbose=verbose)
        
        if is_authenticated:
            click.echo("\n✅ Authentication successful!")
            sys.exit(0)
        else:
            click.echo("\n❌ Authentication failed. Please check your cookies in config.json", err=True)
            sys.exit(1)
            
    except FileNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.json', help='Path to config file')
@click.option('--profile-id', default='691f593b2e2ac1bd7fa84915', help='Profile ID to search for')
@click.option('--max-incentive', type=int, default=1000, help='Maximum incentive')
@click.option('--min-incentive', type=int, default=5, help='Minimum incentive')
@click.option('--max-time', type=int, default=800, help='Maximum time in minutes')
@click.option('--min-time', type=int, default=5, help='Minimum time in minutes')
@click.option('--sort', default='v4Score', help='Sort order')
@click.option('--page-size', type=int, default=15, help='Number of results per page')
@click.option('--page', type=int, default=1, help='Page number')
@click.option('--gender', help='Filter by gender')
@click.option('--education', help='Filter by education level')
@click.option('--ethnicity', help='Filter by ethnicity')
@click.option('--dob', help='Date of birth (YYYY-MM-DD)')
@click.option('--country', help='Filter by country')
@click.option('--output', '-o', help='Output file to save results (JSON)')
@click.option('--verbose/--no-verbose', default=True, help='Show detailed output')
@click.option('--debug', is_flag=True, help='Write projects JSON to projects.json')
def projects(config, profile_id, max_incentive, min_incentive, max_time, min_time,
             sort, page_size, page, gender, education, ethnicity, dob, country,
             output, verbose, debug):
    """List available projects"""
    try:
        # Load configuration
        config_data = load_config(config)
        cookies = config_data.get("cookies", {})
        authorization = config_data.get("authorization")
        
        if not cookies:
            click.echo("❌ No cookies found in config file", err=True)
            sys.exit(1)
        
        # Create session with cookies and authorization header
        session = create_session(cookies, authorization=authorization)
        
        # Verify authentication before proceeding
        if not verify_authentication(session, verbose=verbose):
            click.echo("\n❌ Authentication verification failed. Please check your cookies in config.json", err=True)
            sys.exit(1)
        
        # Fetch the projects using the authenticated session
        data = fetch_projects(
            session=session,
            profile_id=profile_id,
            max_incentive=max_incentive,
            min_incentive=min_incentive,
            max_time_minutes=max_time,
            min_time_minutes=min_time,
            sort=sort,
            page_size=page_size,
            page=page,
            gender=gender,
            education_level=education,
            ethnicity=ethnicity,
            date_of_birth=dob,
            country=country,
            verbose=verbose
        )
        
        # Extract projects from response
        projects_list = data.get('results', [])
        page_num = data.get('page', 1)
        page_size_actual = data.get('pageSize', len(projects_list))
        total_count = data.get('count')  # Total count if include_count was enabled
        
        if not projects_list:
            click.echo("\nNo projects found.")
            if total_count is not None:
                click.echo(f"Total projects available: {total_count}")
            if output:
                with open(output, 'w') as f:
                    json.dump(data, f, indent=2)
                click.echo(f"✅ Response saved to: {output}")
            return
        
        # Display formatted project list
        click.echo(f"\n{'='*100}")
        if total_count is not None:
            click.echo(f"Projects (Page {page_num}, {len(projects_list)} results, Total: {total_count})")
        else:
            click.echo(f"Projects (Page {page_num}, {len(projects_list)} results)")
        click.echo(f"{'='*100}\n")
        
        for idx, project in enumerate(projects_list, 1):
            project_id = project.get('id', 'N/A')
            name = project.get('name', 'N/A')
            description = project.get('description', 'N/A')
            remuneration = project.get('respondentRemuneration', 0)
            time_minutes = project.get('timeMinutesRequired', 0)
            
            # Calculate hourly rate
            if time_minutes > 0:
                hourly_rate = (remuneration / time_minutes) * 60
                hourly_rate_str = f"${hourly_rate:.2f}/hr"
            else:
                hourly_rate_str = "N/A"
            
            # Format output
            click.echo(f"[{idx}] ID: {project_id}")
            click.echo(f"    Hourly Rate: {hourly_rate_str} (${remuneration} for {time_minutes} min)")
            click.echo(f"    Name: {name}")
            click.echo(f"    Description: {description[:200]}{'...' if len(description) > 200 else ''}")
            click.echo()
        
        click.echo(f"{'='*100}")
        
        # Display total count if available
        if total_count is not None:
            click.echo(f"\nTotal projects available: {total_count}")
        
        # Save to projects.json if debug flag is set
        if debug:
            with open('projects.json', 'w') as f:
                json.dump(data, f, indent=2)
            click.echo(f"\n✅ Debug: Projects JSON saved to: projects.json")
        
        # Optionally save full JSON to file
        if output:
            with open(output, 'w') as f:
                json.dump(data, f, indent=2)
            click.echo(f"\n✅ Full response saved to: {output}")
        
    except FileNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


def _hide_project(session: requests.Session, project_id: str, verbose: bool = True) -> bool:
    """
    Hide a single project
    
    Args:
        session: Authenticated requests session
        project_id: Project ID to hide
        verbose: Whether to show detailed output
        
    Returns:
        True if successful, False otherwise
    """
    url = f"https://app.respondent.io/v2/profiles/project/{project_id}/hidden"
    
    if verbose:
        click.echo(f"Hiding project: {project_id}")
        click.echo(f"POST {url}")
    
    # Add headers for the request
    headers = {
        "Sec-Fetch-Site": "same-origin"
    }
    
    # Make the POST request
    response = session.post(url, headers=headers, timeout=30)
    
    if verbose:
        click.echo(f"Response status: {response.status_code}")
    
    # Check if response is successful
    if response.ok:
        if verbose:
            try:
                data = response.json()
                click.echo(f"✅ Project {project_id} hidden successfully")
                click.echo(f"Response: {json.dumps(data, indent=2)}")
            except json.JSONDecodeError:
                click.echo(f"✅ Project {project_id} hidden successfully (no JSON response)")
        else:
            click.echo(f"✅ Project {project_id} hidden successfully")
        return True
    else:
        click.echo(f"❌ Failed to hide project {project_id}", err=True)
        click.echo(f"Status code: {response.status_code}", err=True)
        click.echo(f"Response: {response.text[:500]}", err=True)
        return False


def _fetch_and_filter_page(session: requests.Session, profile_id: str, page: int, page_size: int, 
                           filter_type: str, filter_value, verbose: bool = False):
    """
    Fetch a single page of projects and filter them
    
    Args:
        filter_type: Type of filter ('hourly_rate', 'incentive', or 'kind_of_research')
        filter_value: The filter value used (float for hourly_rate/incentive, int for kind_of_research)
    
    Returns:
        Tuple of (filtered_projects, total_count, has_more_pages)
    """
    data = fetch_projects(
        session=session,
        profile_id=profile_id,
        page=page,
        page_size=page_size,
        verbose=verbose
    )
    
    projects_list = data.get('results', [])
    total_count = data.get('count')
    page_num = data.get('page', page)
    page_size_actual = data.get('pageSize', page_size)
    
    # Filter projects
    filtered_projects = []
    for project in projects_list:
        remuneration = project.get('respondentRemuneration', 0)
        time_minutes = project.get('timeMinutesRequired', 0)
        kind_of_research = project.get('kindOfResearch')
        
        if filter_type == 'hourly_rate':
            if time_minutes > 0:
                project_hourly_rate = (remuneration / time_minutes) * 60
                if project_hourly_rate < filter_value:
                    project['calculated_hourly_rate'] = project_hourly_rate
                    filtered_projects.append(project)
        elif filter_type == 'incentive':
            if remuneration < filter_value:
                if time_minutes > 0:
                    project_hourly_rate = (remuneration / time_minutes) * 60
                else:
                    project_hourly_rate = 0
                project['calculated_hourly_rate'] = project_hourly_rate
                filtered_projects.append(project)
        elif filter_type == 'kind_of_research':
            # Hide projects that don't match the specified kindOfResearch value
            # filter_value is the kindOfResearch value we want to keep (e.g., 1 for remote)
            # So we hide everything that's NOT equal to filter_value
            if kind_of_research != filter_value:
                if time_minutes > 0:
                    project_hourly_rate = (remuneration / time_minutes) * 60
                else:
                    project_hourly_rate = 0
                project['calculated_hourly_rate'] = project_hourly_rate
                filtered_projects.append(project)
    
    # Check if there are more pages
    has_more = len(projects_list) == page_size_actual
    
    return filtered_projects, total_count, has_more


def _process_filtered_projects(session: requests.Session, profile_id: str, page_size: int,
                               filter_type: str, filter_value, verbose: bool = True):
    """
    Process filtered projects with interactive prompts and pagination support
    
    Args:
        session: Authenticated requests session
        profile_id: Profile ID for fetching projects
        page_size: Number of results per page
        filter_type: Type of filter ('hourly_rate', 'incentive', or 'kind_of_research')
        filter_value: The filter value used (float for hourly_rate/incentive, int for kind_of_research)
        verbose: Whether to show detailed output
    """
    # Map kindOfResearch values to human-readable names
    kind_names = {1: "remote", 2: "focus groups", 8: "in-person"}
    
    if filter_type == 'hourly_rate':
        filter_label = f"hourly rate < ${filter_value}/hr"
    elif filter_type == 'incentive':
        filter_label = f"incentive < ${filter_value}"
    elif filter_type == 'kind_of_research':
        kind_name = kind_names.get(filter_value, f"kindOfResearch={filter_value}")
        filter_label = f"not {kind_name} (kindOfResearch != {filter_value})"
    else:
        filter_label = f"filter: {filter_type} = {filter_value}"
    
    # Fetch first page
    page = 1
    all_filtered_projects = []
    total_count = None
    has_more = True
    
    if verbose:
        click.echo(f"\nFetching and filtering projects with {filter_label}...")
    
    # Fetch first page
    filtered_projects, total_count, has_more = _fetch_and_filter_page(
        session, profile_id, page, page_size, filter_type, filter_value, verbose=False
    )
    all_filtered_projects.extend(filtered_projects)
    
    # Show initial summary
    if total_count is not None:
        click.echo(f"Total projects available: {total_count}")
    
    if not all_filtered_projects:
        click.echo(f"No projects found with {filter_label}")
        return
    
    # Display all filtered projects from first page
    click.echo(f"\nFound {len(all_filtered_projects)} project(s) with {filter_label} on page {page}:\n")
    
    for idx, project in enumerate(all_filtered_projects, 1):
        project_id_val = project.get('id', 'N/A')
        name = project.get('name', 'N/A')
        description = project.get('description', 'N/A')
        remuneration = project.get('respondentRemuneration', 0)
        time_minutes = project.get('timeMinutesRequired', 0)
        hourly_rate_val = project.get('calculated_hourly_rate', 0)
        kind_of_research = project.get('kindOfResearch')
        kind_name = kind_names.get(kind_of_research, f"unknown ({kind_of_research})")
        project_link = f"https://app.respondent.io/respondents/v2/projects/view/{project_id_val}"
        
        click.echo(f"[{idx}] {project_id_val}")
        click.echo(f"    Hourly Rate: ${hourly_rate_val:.2f}/hr (${remuneration} for {time_minutes} min)")
        if filter_type == 'kind_of_research':
            click.echo(f"    Research Type: {kind_name} (kindOfResearch={kind_of_research})")
        click.echo(f"    Name: {name}")
        click.echo(f"    Description: {description[:200]}{'...' if len(description) > 200 else ''}")
        click.echo(f"    Link: {project_link}")
        click.echo()
    
    # Interactive prompt for each project
    hide_all = False
    processed_count = 0
    
    for idx, project in enumerate(all_filtered_projects):
        if hide_all:
            # User chose to hide all, so hide this one
            _hide_project(session, project.get('id'), verbose=verbose)
            processed_count += 1
            continue
        
        project_id_val = project.get('id', 'N/A')
        name = project.get('name', 'N/A')
        description = project.get('description', 'N/A')
        remuneration = project.get('respondentRemuneration', 0)
        time_minutes = project.get('timeMinutesRequired', 0)
        hourly_rate_val = project.get('calculated_hourly_rate', 0)
        kind_of_research = project.get('kindOfResearch')
        kind_name = kind_names.get(kind_of_research, f"unknown ({kind_of_research})")
        project_link = f"https://app.respondent.io/respondents/v2/projects/view/{project_id_val}"
        
        click.echo(f"\n{'='*80}")
        click.echo(f"Project {idx + 1}/{len(all_filtered_projects)} (Page {page})")
        click.echo(f"ID: {project_id_val}")
        click.echo(f"Name: {name}")
        click.echo(f"Hourly Rate: ${hourly_rate_val:.2f}/hr (${remuneration} for {time_minutes}min.)")
        if filter_type == 'kind_of_research':
            click.echo(f"Research Type: {kind_name} (kindOfResearch={kind_of_research})")
        click.echo(f"Description: {description}")
        click.echo(f"Link: {project_link}")
        click.echo(f"{'='*80}")
        
        while True:
            choice = click.prompt(
                "Hide this project? (y)es, (n)o, hide (a)ll, (e)xit",
                type=click.Choice(['y', 'n', 'a', 'e'], case_sensitive=False),
                default='y'
            ).lower()
            
            if choice == 'y':
                _hide_project(session, project_id_val, verbose=verbose)
                processed_count += 1
                break
            elif choice == 'n':
                click.echo("Skipping this project...")
                break
            elif choice == 'a':
                hide_all = True
                _hide_project(session, project_id_val, verbose=verbose)
                processed_count += 1
                
                # Hide remaining projects on current page
                for remaining_project in all_filtered_projects[idx + 1:]:
                    _hide_project(session, remaining_project.get('id'), verbose=verbose)
                    processed_count += 1
                
                # Continue with pagination
                click.echo(f"\n✅ Hidden {len(all_filtered_projects) - idx} project(s) on page {page}")
                if has_more:
                    click.echo(f"Continuing to fetch and hide matching projects from remaining pages...")
                
                break
            elif choice == 'e':
                click.echo("Exiting...")
                return
    
    # If hide_all was selected, continue paginating through all pages
    if hide_all and has_more:
        page += 1
        while True:
            if verbose:
                click.echo(f"\nFetching page {page}...")
            
            filtered_projects, _, has_more = _fetch_and_filter_page(
                session, profile_id, page, page_size, filter_type, filter_value, verbose=False
            )
            
            if not filtered_projects:
                if has_more:
                    page += 1
                    continue
                else:
                    break
            
            if verbose:
                click.echo(f"Found {len(filtered_projects)} matching project(s) on page {page}")
            
            # Hide all matching projects on this page
            for project in filtered_projects:
                project_id = project.get('id')
                _hide_project(session, project_id, verbose=verbose)
                processed_count += 1
            
            if not has_more:
                break
            
            page += 1
        
        click.echo(f"\n✅ All {processed_count} project(s) processed across all pages")
    else:
        click.echo(f"\n✅ Processing complete ({processed_count} project(s) hidden)")


@cli.command()
@click.option('--config', '-c', default='config.json', help='Path to config file')
@click.option('--id', 'project_id', help='Project ID to hide')
@click.option('--hourly-rate', 'hourly_rate', type=int, help='Hide all projects with hourly rate lower than this value')
@click.option('--incentive', 'incentive', type=int, help='Hide all projects with total incentive lower than this value')
@click.option('--hide-not-kind', 'hide_not_kind', type=click.Choice(['remote', 'in-person', 'focus-groups'], case_sensitive=False), help='Hide all projects that are not of the specified research type (remote=1, in-person=8, focus-groups=2)')
@click.option('--profile-id', default='691f593b2e2ac1bd7fa84915', help='Profile ID for fetching projects (used with --hourly-rate, --incentive, or --hide-not-kind)')
@click.option('--verbose/--no-verbose', default=True, help='Show detailed output')
def hide(config, project_id, hourly_rate, incentive, hide_not_kind, profile_id, verbose):
    """Hide a project or multiple projects by hourly rate, incentive, or research type"""
    try:
        # Load configuration
        config_data = load_config(config)
        cookies = config_data.get("cookies", {})
        authorization = config_data.get("authorization")
        
        if not cookies:
            click.echo("❌ No cookies found in config file", err=True)
            sys.exit(1)
        
        # Create session with cookies and authorization header
        session = create_session(cookies, authorization=authorization)
        
        # Verify authentication before proceeding
        if not verify_authentication(session, verbose=verbose):
            click.echo("\n❌ Authentication verification failed. Please check your cookies in config.json", err=True)
            sys.exit(1)
        
        # Handle research kind filtering mode
        if hide_not_kind is not None:
            # Map human-readable names to kindOfResearch values
            kind_mapping = {
                'remote': 1,
                'in-person': 8,
                'focus-groups': 2
            }
            kind_value = kind_mapping[hide_not_kind.lower()]
            _process_filtered_projects(session, profile_id, 50, 'kind_of_research', kind_value, verbose)
        
        # Handle hourly rate filtering mode
        elif hourly_rate is not None:
            _process_filtered_projects(session, profile_id, 50, 'hourly_rate', hourly_rate, verbose)
        
        # Handle incentive filtering mode
        elif incentive is not None:
            _process_filtered_projects(session, profile_id, 50, 'incentive', incentive, verbose)
            
        # Handle single project ID mode
        elif project_id:
            success = _hide_project(session, project_id, verbose=verbose)
            if not success:
                sys.exit(1)
        else:
            click.echo("❌ Either --id, --hourly-rate, --incentive, or --hide-not-kind must be provided", err=True)
            click.echo("Use --help for more information", err=True)
            sys.exit(1)
        
    except FileNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()

