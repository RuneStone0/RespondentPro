#!/usr/bin/env python3
"""
Respondent.io authentication and session management service
"""

import time
import requests
from datetime import datetime

# Import database collections
try:
    from ..db import user_profiles_collection
except ImportError:
    from web.db import user_profiles_collection

# Import user service for config loading
try:
    from .user_service import load_user_config
except ImportError:
    from services.user_service import load_user_config


def create_respondent_session(cookies):
    """
    Create a requests session with Respondent.io authentication
    
    Args:
        cookies: Dictionary of cookie name-value pairs
        
    Returns:
        Configured requests.Session object
    """
    session = requests.Session()
    
    # Set cookies
    for name, value in cookies.items():
        if value:
            session.cookies.set(name, value)
    
    # Set headers
    session.headers.update({
        "X-Requested-With": "XMLHttpRequest"
    })
    
    return session


def verify_respondent_authentication(cookies):
    """
    Verify authentication with Respondent.io API using the same logic as CLI
    
    Args:
        cookies: Dictionary of cookie name-value pairs
        
    Returns:
        Dictionary with 'success' (bool), 'message' (str), and optional 'profile_id' and 'first_name'
    """
    auth_url = "https://app.respondent.io/v2/respondents/me"
    
    try:
        # Create a requests session
        req_session = requests.Session()
        
        # Set cookies
        for name, value in cookies.items():
            if value:
                req_session.cookies.set(name, value)
        
        # Set headers
        req_session.headers.update({
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Make the request
        start_time = time.time()
        print(f"[Respondent.io API] GET {auth_url} (verify_authentication)")
        response = req_session.get(auth_url, timeout=30)
        elapsed_time = time.time() - start_time
        print(f"[Respondent.io API] Response: {response.status_code} ({elapsed_time:.2f}s)")
        
        # Check response status
        if response.status_code == 200:
            try:
                user_data = response.json()
                
                # Extract profile ID and first name from nested response structure
                profile_id = None
                first_name = None
                user_id = None
                
                if isinstance(user_data, dict) and 'response' in user_data:
                    response_data = user_data.get('response', {})
                    
                    # Get profile ID from response.profile.id
                    if 'profile' in response_data and isinstance(response_data['profile'], dict):
                        profile_id = response_data['profile'].get('id')
                    
                    # Get first name from response.firstName
                    first_name = response_data.get('firstName')
                    
                    # Get user ID - try different possible locations
                    if 'id' in response_data:
                        user_id = response_data.get('id')
                    elif 'userId' in response_data:
                        user_id = response_data.get('userId')
                    elif 'user' in response_data and isinstance(response_data['user'], dict):
                        user_id = response_data['user'].get('id')
                    elif 'profile' in response_data and isinstance(response_data['profile'], dict):
                        # Sometimes user_id might be in profile
                        user_id = response_data['profile'].get('userId') or response_data['profile'].get('user_id')
                
                # Check if we got the required fields
                if not profile_id or not first_name:
                    return {
                        'success': False,
                        'message': 'Authentication failed: Unable to extract Profile ID and First Name from response',
                        'status_code': response.status_code
                    }
                
                # Authentication successful
                result = {
                    'success': True,
                    'message': 'Authentication successful',
                    'profile_id': profile_id,
                    'first_name': first_name,
                    'user_id': user_id,  # Respondent.io user ID for profile fetching
                    'status_code': response.status_code
                }
                if user_id:
                    result['user_id'] = user_id
                return result
            except Exception as json_error:
                return {
                    'success': False,
                    'message': f'Authentication failed: Invalid JSON response - {str(json_error)}',
                    'status_code': response.status_code
                }
        elif response.status_code == 401:
            return {
                'success': False,
                'message': 'Authentication failed: Unauthorized (401)',
                'status_code': response.status_code
            }
        elif response.status_code == 403:
            return {
                'success': False,
                'message': 'Authentication failed: Forbidden (403)',
                'status_code': response.status_code
            }
        else:
            return {
                'success': False,
                'message': f'Unexpected status code: {response.status_code}',
                'status_code': response.status_code
            }
            
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'message': f'Error verifying authentication: {str(e)}',
            'status_code': None
        }


def fetch_user_profile(session, user_id):
    """
    Fetch user profile data from Respondent.io API to get demographic information
    
    Args:
        session: Authenticated requests.Session object
        user_id: User ID (not profile_id) to fetch profile for
        
    Returns:
        Dictionary containing profile data with demographic fields, or None if failed
    """
    # The profile endpoint uses user_id, not profile_id
    profile_url = f"https://app.respondent.io/api/v4/profiles/user/{user_id}"
    
    try:
        headers = {
            "Sec-Fetch-Site": "same-origin"
        }
        
        start_time = time.time()
        print(f"[Respondent.io API] GET {profile_url} (fetch_user_profile)")
        # Use shorter timeout for profile fetch since it's optional
        response = session.get(profile_url, headers=headers, timeout=10)
        elapsed_time = time.time() - start_time
        print(f"[Respondent.io API] Response: {response.status_code} ({elapsed_time:.2f}s)")
        
        if response.status_code == 200:
            profile_data = response.json()
            return profile_data
        else:
            print(f"[Respondent.io API] Failed to fetch profile: {response.status_code} - {response.text[:500]}")
            return None
    except requests.exceptions.Timeout:
        print(f"[Respondent.io API] Profile fetch timed out (this is optional, continuing without demographic filters)")
        return None
    except Exception as e:
        print(f"[Respondent.io API] Error fetching profile: {e}")
        return None


def extract_demographic_params(profile_data):
    """
    Extract demographic parameters from profile data
    
    Args:
        profile_data: Dictionary containing profile data from API
        
    Returns:
        Dictionary with demographic parameters (gender, education_level, ethnicity, date_of_birth, country)
    """
    if not isinstance(profile_data, dict):
        return {}
    
    # The structure might vary, so we'll try common field names
    # Common patterns: response.data, response.profile, or direct fields
    data = profile_data
    if 'response' in profile_data and isinstance(profile_data['response'], dict):
        data = profile_data['response']
        if 'data' in data:
            data = data['data']
        elif 'profile' in data:
            data = data['profile']
    
    params = {}
    
    # Extract gender
    if 'gender' in data:
        params['gender'] = data['gender']
    elif 'genderId' in data:
        # Might be an ID that needs mapping, but try the value first
        params['gender'] = str(data['genderId']).lower() if data['genderId'] else None
    
    # Extract education level
    if 'educationLevel' in data:
        params['education_level'] = data['educationLevel']
    elif 'education' in data and isinstance(data['education'], dict):
        params['education_level'] = data['education'].get('level')
    
    # Extract ethnicity
    if 'ethnicity' in data:
        params['ethnicity'] = data['ethnicity']
    elif 'ethnicityId' in data:
        params['ethnicity'] = str(data['ethnicityId']).lower() if data['ethnicityId'] else None
    
    # Extract date of birth
    if 'dateOfBirth' in data:
        params['date_of_birth'] = data['dateOfBirth']
    elif 'dob' in data:
        params['date_of_birth'] = data['dob']
    elif 'birthDate' in data:
        params['date_of_birth'] = data['birthDate']
    
    # Extract country
    if 'country' in data:
        params['country'] = data['country']
    elif 'countryCode' in data:
        params['country'] = data['countryCode']
    elif 'location' in data and isinstance(data['location'], dict):
        params['country'] = data['location'].get('country') or data['location'].get('countryCode')
    
    return params


def extract_demographic_params_from_mongodb(profile_data):
    """
    Extract demographic parameters from MongoDB profile data structure
    
    Args:
        profile_data: Dictionary containing profile data from MongoDB (nested under 'profile' key)
        
    Returns:
        Dictionary with demographic parameters (gender, education_level, ethnicity, date_of_birth, country)
    """
    if not isinstance(profile_data, dict):
        return {}
    
    params = {}
    
    # Extract gender from demographics
    if 'demographics' in profile_data and isinstance(profile_data['demographics'], dict):
        demographics = profile_data['demographics']
        if 'gender' in demographics:
            params['gender'] = demographics['gender']
        
        # Extract education level
        if 'educationLevel' in demographics:
            params['education_level'] = demographics['educationLevel']
        
        # Extract ethnicity
        if 'ethnicity' in demographics:
            params['ethnicity'] = demographics['ethnicity']
        
        # Extract date of birth
        if 'dateOfBirth' in demographics:
            params['date_of_birth'] = demographics['dateOfBirth']
        elif 'birthDate' in demographics:
            params['date_of_birth'] = demographics['birthDate']
    
    # Extract country from location.city.country
    if 'location' in profile_data and isinstance(profile_data['location'], dict):
        location = profile_data['location']
        if 'city' in location and isinstance(location['city'], dict):
            city = location['city']
            if 'country' in city:
                params['country'] = city['country']
        elif 'country' in location:
            params['country'] = location['country']
        elif 'countryCode' in location:
            params['country'] = location['countryCode']
    
    return params


def get_user_profile(mongo_user_id):
    """
    Retrieve user profile data from MongoDB
    
    Args:
        mongo_user_id: Our internal MongoDB user_id (ObjectId as string)
        
    Returns:
        Dictionary containing profile data if found, None otherwise
    """
    if user_profiles_collection is None:
        return None
    
    try:
        profile_doc = user_profiles_collection.find_one({'user_id': mongo_user_id})
        if profile_doc:
            return profile_doc.get('profile')
        return None
    except Exception as e:
        print(f"[Profile] Error retrieving profile for user {mongo_user_id}: {e}")
        return None


def fetch_and_store_user_profile(mongo_user_id, respondent_user_id=None):
    """
    Fetch user profile data from Respondent.io API and store it in MongoDB
    
    Args:
        mongo_user_id: Our internal MongoDB user_id (ObjectId as string)
        respondent_user_id: Optional Respondent.io user_id. If not provided, will try to get from config
        
    Returns:
        Dictionary containing profile data if successful, None otherwise
    """
    if user_profiles_collection is None:
        return None
    
    try:
        # Load user config to get cookies and authorization
        config = load_user_config(mongo_user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            # User doesn't have Respondent.io credentials configured yet
            return None
        
        # Create authenticated session
        req_session = create_respondent_session(
            cookies=config.get('cookies', {})
        )
        
        # If respondent_user_id not provided, try to get it from verification
        if not respondent_user_id:
            verification_result = verify_respondent_authentication(
                cookies=config.get('cookies', {})
            )
            if verification_result.get('success'):
                respondent_user_id = verification_result.get('user_id')
        
        if not respondent_user_id:
            print(f"[Profile] Could not determine Respondent.io user_id for MongoDB user {mongo_user_id}")
            return None
        
        # Fetch the profile
        profile_data = fetch_user_profile(req_session, respondent_user_id)
        
        if profile_data:
            # Store profile in user_profiles collection
            user_profiles_collection.update_one(
                {'user_id': mongo_user_id},
                {
                    '$set': {
                        'profile': profile_data,
                        'respondent_user_id': respondent_user_id,
                        'updated_at': datetime.utcnow()
                    },
                    '$setOnInsert': {
                        'created_at': datetime.utcnow()
                    }
                },
                upsert=True
            )
            print(f"[Profile] Successfully fetched and stored profile for user {mongo_user_id}")
            return profile_data
        else:
            print(f"[Profile] Failed to fetch profile for user {mongo_user_id}")
            return None
            
    except Exception as e:
        print(f"[Profile] Error fetching/storing profile for user {mongo_user_id}: {e}")
        import traceback
        print(traceback.format_exc())
        return None

