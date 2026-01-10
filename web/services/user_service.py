#!/usr/bin/env python3
"""
User management service for Respondent.io Manager
Firestore implementation
"""

import base64
import secrets
from datetime import datetime, timedelta
from google.cloud.firestore import DELETE_FIELD
from google.cloud.firestore_v1.base_query import FieldFilter

# Import database collections
try:
    from ..db import users_collection, session_keys_collection, user_preferences_collection, projects_cache_collection, hidden_projects_log_collection
except ImportError:
    from web.db import users_collection, session_keys_collection, user_preferences_collection, projects_cache_collection, hidden_projects_log_collection


def get_user_by_email(email):
    """Get user document by email (stored in username field), returns user_id (document ID)"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        # Email is stored in the username field
        query = users_collection.where(filter=FieldFilter('username', '==', email)).limit(1).stream()
        docs = list(query)
        if docs:
            return docs[0].id  # Return document ID as string
        return None
    except Exception as e:
        error_msg = str(e)
        raise Exception(f"Failed to get user from Firestore: {e}")


def get_email_by_user_id(user_id):
    """Get email (stored in username field) by user_id"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if user_doc.exists:
            return user_doc.to_dict().get('username')  # Email is stored in username field
        return None
    except Exception as e:
        raise Exception(f"Failed to get email from Firestore: {e}")


def user_exists_by_email(email):
    """Check if user exists by email"""
    return get_user_by_email(email) is not None


def generate_verification_token(user_id):
    """Generate a verification token for email verification"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)  # Token expires in 7 days
    
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        users_collection.document(str(user_id)).update({
            'verification_token': token,
            'verification_token_expires': expires_at,
            'updated_at': datetime.utcnow()
        })
        return token
    except Exception as e:
        raise Exception(f"Failed to generate verification token: {e}")


def generate_login_token(user_id):
    """Generate a login token for email-based authentication"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
    
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        users_collection.document(str(user_id)).update({
            'login_token': token,
            'login_token_expires': expires_at,
            'updated_at': datetime.utcnow()
        })
        return token
    except Exception as e:
        raise Exception(f"Failed to generate login token: {e}")


def verify_login_token(user_id, token):
    """Verify login token. Returns True if successful, False otherwise."""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            return False
        
        user_data = user_doc.to_dict()
        stored_token = user_data.get('login_token')
        token_expires = user_data.get('login_token_expires')
        
        # Check if token matches and hasn't expired
        if stored_token != token:
            return False
        
        if token_expires and isinstance(token_expires, datetime):
            if datetime.utcnow() > token_expires:
                return False
        
        # Clear the login token after use
        users_collection.document(str(user_id)).update({
            'login_token': DELETE_FIELD,
            'login_token_expires': DELETE_FIELD,
            'updated_at': datetime.utcnow()
        })
        
        return True
    except Exception as e:
        raise Exception(f"Failed to verify login token: {e}")


def create_user(email):
    """Create a new user with email (stored in username field) and return user_id (document ID)"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        # Validate email format
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            raise ValueError("Invalid email format")
        
        # Check if user already exists
        existing_user = get_user_by_email(email)
        if existing_user:
            return existing_user
        
        # Generate verification token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        # Create new user - email is stored in username field
        user_data = {
            'username': email,  # Email stored in username field
            'email_verified': False,
            'verification_token': token,
            'verification_token_expires': expires_at,
            'credentials': [],  # Array for multiple passkeys
            'projects_processed_limit': 500,  # Default limit for new users
            'credits_low_email_sent': False,
            'credits_exhausted_email_sent': False,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Firestore will auto-generate document ID
        # add() returns a tuple (timestamp, document_reference)
        _, doc_ref = users_collection.add(user_data)
        return doc_ref.id
    except Exception as e:
        raise Exception(f"Failed to create user in Firestore: {e}")


def load_credentials_by_user_id(user_id, rp_id=None):
    """Load passkey credentials for a specific user_id from Firestore (stored in users collection)
    
    Args:
        user_id: User ID
        rp_id: Optional relying party ID to filter credentials. If None, returns all credentials.
               If specified and no matching credential found, returns None.
    
    Returns:
        If rp_id is None: List of all credentials
        If rp_id is specified: Single credential dict matching rp_id, or None if not found
    """
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            return None
        
        user_data = user_doc.to_dict()
        
        # Check for credentials array format
        if 'credentials' in user_data and isinstance(user_data['credentials'], list):
            credentials_list = []
            for cred_doc in user_data['credentials']:
                cred = {
                    'credential_id': None,
                    'public_key': None,
                    'counter': cred_doc.get('counter', 0),
                    'rp_id': cred_doc.get('rp_id', 'localhost'),
                    'created_at': cred_doc.get('created_at'),
                    'name': cred_doc.get('name')
                }
                
                # Convert base64 strings back to bytes for webauthn library
                if 'credential_id' in cred_doc and cred_doc['credential_id']:
                    cred_id = cred_doc['credential_id']
                    if isinstance(cred_id, str):
                        padding = 4 - (len(cred_id) % 4)
                        if padding != 4:
                            cred_id += '=' * padding
                        cred['credential_id'] = base64.urlsafe_b64decode(cred_id)
                    else:
                        cred['credential_id'] = cred_id
                
                if 'public_key' in cred_doc and cred_doc['public_key']:
                    pub_key = cred_doc['public_key']
                    if isinstance(pub_key, str):
                        padding = 4 - (len(pub_key) % 4)
                        if padding != 4:
                            pub_key += '=' * padding
                        cred['public_key'] = base64.urlsafe_b64decode(pub_key)
                    else:
                        cred['public_key'] = pub_key
                
                credentials_list.append(cred)
            
            # Filter by rp_id if specified
            if rp_id is not None:
                matching_cred = None
                for cred in credentials_list:
                    if cred.get('rp_id') == rp_id:
                        matching_cred = cred
                        break
                return matching_cred
            
            return credentials_list
        
        return None
    except Exception as e:
        raise Exception(f"Failed to load credentials from Firestore: {e}")


def add_credential_to_user(user_id, cred, rp_id=None):
    """Add a new passkey credential to user's credentials array"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        # Determine rp_id
        if rp_id is None:
            rp_id = cred.get('rp_id', 'localhost')
        else:
            cred['rp_id'] = rp_id
        
        # Convert bytes to base64 for storage
        credential_doc = {
            'counter': cred.get('counter', 0),
            'rp_id': rp_id,
            'created_at': datetime.utcnow(),
            'name': cred.get('name')
        }
        
        if 'credential_id' in cred and cred['credential_id']:
            if isinstance(cred['credential_id'], bytes):
                credential_doc['credential_id'] = base64.urlsafe_b64encode(cred['credential_id']).decode('utf-8').rstrip('=')
            else:
                credential_doc['credential_id'] = cred['credential_id']
        
        if 'public_key' in cred and cred['public_key']:
            if isinstance(cred['public_key'], bytes):
                credential_doc['public_key'] = base64.urlsafe_b64encode(cred['public_key']).decode('utf-8').rstrip('=')
            else:
                credential_doc['public_key'] = cred['public_key']
        
        # Get user document to check format
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            raise Exception(f"User {user_id} not found")
        
        user_data = user_doc.to_dict()
        
        # Add new credential to array (avoid duplicates by checking credential_id)
        credential_id_str = credential_doc['credential_id']
        credentials = user_data.get('credentials', [])
        
        # Remove existing credential with same credential_id
        credentials = [c for c in credentials if c.get('credential_id') != credential_id_str]
        
        # Add new credential
        credentials.append(credential_doc)
        
        # Update document
        users_collection.document(str(user_id)).update({
            'credentials': credentials,
            'updated_at': datetime.utcnow()
        })
    except Exception as e:
        raise Exception(f"Failed to add credential to Firestore: {e}")


def update_credential_counter(user_id, credential_id, new_counter):
    """Update the counter for a specific credential"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        # Convert credential_id to string if it's bytes
        if isinstance(credential_id, bytes):
            credential_id_str = base64.urlsafe_b64encode(credential_id).decode('utf-8').rstrip('=')
        else:
            credential_id_str = str(credential_id)
        
        # Get user document
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            raise Exception(f"User {user_id} not found")
        
        user_data = user_doc.to_dict()
        credentials = user_data.get('credentials', [])
        
        # Find and update the credential
        updated = False
        for cred in credentials:
            if cred.get('credential_id') == credential_id_str:
                cred['counter'] = new_counter
                updated = True
                break
        
        if not updated:
            raise Exception(f"Credential {credential_id_str} not found")
        
        # Update document
        users_collection.document(str(user_id)).update({
            'credentials': credentials,
            'updated_at': datetime.utcnow()
        })
    except Exception as e:
        raise Exception(f"Failed to update credential counter: {e}")


def delete_credential_from_user(user_id, credential_id):
    """Delete a specific passkey credential from user's credentials array"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        # Convert credential_id to string if it's bytes
        if isinstance(credential_id, bytes):
            credential_id_str = base64.urlsafe_b64encode(credential_id).decode('utf-8').rstrip('=')
        else:
            credential_id_str = str(credential_id)
        
        # Get user document
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            raise Exception(f"User {user_id} not found")
        
        user_data = user_doc.to_dict()
        credentials = user_data.get('credentials', [])
        
        # Remove credential
        original_count = len(credentials)
        credentials = [c for c in credentials if c.get('credential_id') != credential_id_str]
        
        if len(credentials) == original_count:
            raise Exception("Credential not found or already deleted")
        
        # Update document
        users_collection.document(str(user_id)).update({
            'credentials': credentials,
            'updated_at': datetime.utcnow()
        })
        
        return True
    except Exception as e:
        raise Exception(f"Failed to delete credential from Firestore: {e}")


def load_user_config(user_id):
    """Load user's Respondent.io config from Firestore by user_id or firebase_uid"""
    if session_keys_collection is None:
        return None
    try:
        # First try direct lookup by user_id
        query = session_keys_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if docs:
            config_doc = docs[0].to_dict()
            return {
                'cookies': config_doc.get('cookies', {}),
                'profile_id': config_doc.get('profile_id'),
                'last_synced': config_doc.get('last_synced')
            }
        
        # If not found, try to find user by firebase_uid in users collection
        # and then look up config by that user_id
        if users_collection:
            # Check if user_id is actually a firebase_uid
            user_doc = users_collection.document(str(user_id)).get()
            if user_doc.exists:
                # This is a firebase_uid document, user_id matches
                pass
            else:
                # Try to find user by firebase_uid field
                firebase_uid_query = users_collection.where(filter=FieldFilter('firebase_uid', '==', str(user_id))).limit(1).stream()
                firebase_uid_docs = list(firebase_uid_query)
                if firebase_uid_docs:
                    # Found user with this firebase_uid, use the document ID
                    actual_user_id = firebase_uid_docs[0].id
                    query = session_keys_collection.where(filter=FieldFilter('user_id', '==', str(actual_user_id))).limit(1).stream()
                    docs = list(query)
                    if docs:
                        config_doc = docs[0].to_dict()
                        return {
                            'cookies': config_doc.get('cookies', {}),
                            'profile_id': config_doc.get('profile_id'),
                            'last_synced': config_doc.get('last_synced')
                        }
    except Exception as e:
        print(f"Error loading user config: {e}")
    return None


def update_last_synced(user_id):
    """Update the last synced timestamp for a user"""
    if session_keys_collection is None:
        return
    try:
        query = session_keys_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if docs:
            docs[0].reference.update({
                'last_synced': datetime.utcnow()
            })
    except Exception as e:
        print(f"Error updating last synced time: {e}")


def save_user_config(user_id, config, profile_id=None):
    """Save user's Respondent.io config to Firestore by user_id or firebase_uid"""
    if session_keys_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        # Resolve user_id - if it's a firebase_uid, find the actual user_id
        actual_user_id = str(user_id)
        if users_collection:
            # Check if user_id is a firebase_uid by looking for document with that ID
            user_doc = users_collection.document(str(user_id)).get()
            if not user_doc.exists:
                # Try to find user by firebase_uid field
                firebase_uid_query = users_collection.where(filter=FieldFilter('firebase_uid', '==', str(user_id))).limit(1).stream()
                firebase_uid_docs = list(firebase_uid_query)
                if firebase_uid_docs:
                    actual_user_id = firebase_uid_docs[0].id
        
        update_data = {
            'user_id': actual_user_id,
            'cookies': config.get('cookies', {}),
            'updated_at': datetime.utcnow()
        }
        if profile_id:
            update_data['profile_id'] = profile_id
        
        # Find existing document or create new one
        query = session_keys_collection.where(filter=FieldFilter('user_id', '==', actual_user_id)).limit(1).stream()
        docs = list(query)
        if docs:
            docs[0].reference.update(update_data)
        else:
            session_keys_collection.add(update_data)
    except Exception as e:
        raise Exception(f"Failed to save to Firestore: {e}")


def load_user_filters(user_id):
    """Load user's project filter preferences from Firestore, handling migration from old user_id to Firebase Auth UID"""
    if user_preferences_collection is None:
        return {
            'min_incentive': None,
            'min_hourly_rate': None,
            'isRemote': None,
            'auto_hide': False,
            'topics': [],  # List of topic IDs to hide projects for
            'hide_using_ai': False
        }
    try:
        # Import resolve helper
        try:
            from ..cache_manager import resolve_user_id_for_query
        except ImportError:
            try:
                from web.cache_manager import resolve_user_id_for_query
            except ImportError:
                def resolve_user_id_for_query(user_id: str):
                    return str(user_id), None
        
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Try with current user_id first
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', current_user_id)).limit(1).stream()
        docs = list(query)
        
        # If not found and we have old_user_id, try that
        if not docs and old_user_id:
            query_old = user_preferences_collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(1).stream()
            docs = list(query_old)
            # If found, migrate it
            if docs:
                docs[0].reference.update({'user_id': current_user_id})
                print(f"[Migration] Migrated user preferences from old user_id {old_user_id} to {current_user_id}")
        
        if docs:
            prefs_doc = docs[0].to_dict()
            if 'filters' in prefs_doc:
                filters = prefs_doc['filters']
                auto_hide = filters.get('auto_hide', False)
                is_remote = filters.get('isRemote')
                
                # Ensure isRemote is either None or True (never False)
                if is_remote is not None and is_remote is not True:
                    if isinstance(is_remote, str):
                        is_remote = is_remote.lower() in ('true', '1', 'yes', 'on')
                    else:
                        is_remote = bool(is_remote)
                    if not is_remote:
                        is_remote = None
                
                return {
                    'min_incentive': filters.get('min_incentive'),
                    'min_hourly_rate': filters.get('min_hourly_rate'),
                    'isRemote': is_remote,
                    'auto_hide': bool(auto_hide),
                    'topics': filters.get('topics', []),
                    'hide_using_ai': filters.get('hide_using_ai', False)
                }
    except Exception as e:
        print(f"Error loading user filters: {e}")
    return {
        'min_incentive': None,
        'min_hourly_rate': None,
        'isRemote': None,
        'auto_hide': False,
        'topics': [],
        'hide_using_ai': False
    }


def save_user_filters(user_id, filters):
    """Save user's project filter preferences to Firestore (stored in user_preferences collection)"""
    if user_preferences_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    
    # Handle None filters - default to empty dict
    if filters is None:
        filters = {}
    
    try:
        # Convert string values to numbers or None
        # Explicitly handle null/None values to ensure cleared settings are saved
        min_incentive = None
        min_hourly_rate = None
        
        min_incentive_val = filters.get('min_incentive')
        if min_incentive_val is not None and min_incentive_val != '':
            try:
                min_incentive = float(min_incentive_val)
            except (ValueError, TypeError):
                min_incentive = None
        
        min_hourly_rate_val = filters.get('min_hourly_rate')
        if min_hourly_rate_val is not None and min_hourly_rate_val != '':
            try:
                min_hourly_rate = float(min_hourly_rate_val)
            except (ValueError, TypeError):
                min_hourly_rate = None
        
        # Get auto-hide mode setting (default to False if not provided)
        auto_hide = filters.get('auto_hide', False)
        
        # Convert to boolean if needed
        if isinstance(auto_hide, str):
            auto_hide = auto_hide.lower() in ('true', '1', 'yes', 'on')
        
        # Get remote filter setting (isRemote)
        is_remote = filters.get('isRemote')
        # Handle None, True, or string "true" values
        if is_remote is None or is_remote == '':
            is_remote = None
        elif isinstance(is_remote, str):
            is_remote = is_remote.lower() in ('true', '1', 'yes', 'on')
            if not is_remote:
                is_remote = None
        elif is_remote is False:
            # Never save False, convert to None
            is_remote = None
        else:
            # Ensure it's True if it's truthy
            is_remote = True
        
        # Get topics filter (list of topic IDs to hide projects for)
        topics = filters.get('topics', [])
        if not isinstance(topics, list):
            topics = []
        # Convert to strings and filter out empty values
        topics = [str(t) for t in topics if t]
        
        # Get hide_using_ai flag (default to False if not provided)
        hide_using_ai = filters.get('hide_using_ai', False)
        # Convert to boolean if needed
        if isinstance(hide_using_ai, str):
            hide_using_ai = hide_using_ai.lower() in ('true', '1', 'yes', 'on')
        hide_using_ai = bool(hide_using_ai)
        
        # Update the document with filters in user_preferences collection
        update_data = {
            'user_id': str(user_id),  # Ensure user_id is set when creating new document
            'filters': {
                'min_incentive': min_incentive,
                'min_hourly_rate': min_hourly_rate,
                'isRemote': is_remote,
                'auto_hide': bool(auto_hide),
                'topics': topics,
                'hide_using_ai': hide_using_ai
            },
            'updated_at': datetime.utcnow()
        }
        
        # Resolve user_id to ensure we use the correct format
        try:
            from ..cache_manager import resolve_user_id_for_query
        except ImportError:
            try:
                from web.cache_manager import resolve_user_id_for_query
            except ImportError:
                def resolve_user_id_for_query(user_id: str):
                    return str(user_id), None
        
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Update user_id in update_data to use current format
        update_data['user_id'] = current_user_id
        
        # Try to find existing document with current user_id
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', current_user_id)).limit(1).stream()
        docs = list(query)
        
        # If not found and we have old_user_id, try that and migrate
        if not docs and old_user_id:
            query_old = user_preferences_collection.where(filter=FieldFilter('user_id', '==', old_user_id)).limit(1).stream()
            docs = list(query_old)
            if docs:
                # Migrate to new user_id
                docs[0].reference.update({'user_id': current_user_id})
                print(f"[Migration] Migrated user preferences from old user_id {old_user_id} to {current_user_id}")
        
        if docs:
            docs[0].reference.update(update_data)
        else:
            update_data['created_at'] = datetime.utcnow()
            user_preferences_collection.add(update_data)
    except Exception as e:
        raise Exception(f"Failed to save filters to Firestore: {e}")


def update_user_onboarding_status(user_id, has_account):
    """Update the has_respondent_account field in the user document"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        users_collection.document(str(user_id)).update({
            'has_respondent_account': bool(has_account),
            'updated_at': datetime.utcnow()
        })
    except Exception as e:
        raise Exception(f"Failed to update onboarding status in Firestore: {e}")


def get_user_onboarding_status(user_id):
    """Retrieve the has_respondent_account field from user document"""
    if users_collection is None:
        return None
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if user_doc.exists:
            return user_doc.to_dict().get('has_respondent_account')
        return None
    except Exception as e:
        print(f"Error getting onboarding status: {e}")
        return None


def get_user_verification_status(user_id):
    """Check if user's email is verified"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            return False
        return user_doc.to_dict().get('email_verified', False)
    except Exception as e:
        raise Exception(f"Failed to get verification status: {e}")


def is_user_verified(user_id):
    """Quick check for middleware - returns boolean, raises if user not found"""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            raise Exception(f"User {user_id} not found")
        return user_doc.to_dict().get('email_verified', False)
    except Exception as e:
        raise Exception(f"Failed to check verification status: {e}")


def verify_user_email(user_id, token):
    """Verify user email with token. Returns True if successful, False otherwise."""
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            return False
        
        user_data = user_doc.to_dict()
        stored_token = user_data.get('verification_token')
        token_expires = user_data.get('verification_token_expires')
        
        # Check if token matches and hasn't expired
        if stored_token != token:
            return False
        
        if token_expires and isinstance(token_expires, datetime):
            if datetime.utcnow() > token_expires:
                return False
        
        # Verify the email
        users_collection.document(str(user_id)).update({
            'email_verified': True,
            'updated_at': datetime.utcnow(),
            'verification_token': DELETE_FIELD,
            'verification_token_expires': DELETE_FIELD
        })
        
        return True
    except Exception as e:
        raise Exception(f"Failed to verify email: {e}")


# Admin user IDs - can be configured via ADMIN_USER_IDS environment variable (comma-separated)
# or hardcoded as fallback
def get_admin_user_ids():
    """Get admin user IDs from environment variable or hardcoded list"""
    import os
    env_admin_ids = os.environ.get('ADMIN_USER_IDS', '')
    if env_admin_ids:
        # Parse comma-separated list from environment variable
        admin_ids = [admin_id.strip() for admin_id in env_admin_ids.split(',') if admin_id.strip()]
        if admin_ids:
            return admin_ids
    
    # Fallback to hardcoded list if env var not set
    ADMIN_USER_IDS = [
        # Add admin user IDs here as strings (fallback if ADMIN_USER_IDS env var not set)
        # Example: '507f1f77bcf86cd799439011'
    ]
    return ADMIN_USER_IDS


def is_admin(user_id):
    """Check if user_id is in the admin list (from env var or hardcoded)"""
    if not user_id:
        return False
    admin_ids = get_admin_user_ids()
    return str(user_id) in [str(admin_id) for admin_id in admin_ids]


def get_projects_processed_count(user_id):
    """Calculate total projects processed for user, handling migration from old user_id to Firebase Auth UID.
    
    Counts projects from hidden_projects_log_collection for the user.
    This represents all projects that have been processed (hidden) by the user.
    
    Args:
        user_id: User ID (Firebase Auth UID for new users)
        
    Returns:
        Total count of projects processed
    """
    if hidden_projects_log_collection is None:
        return 0
    try:
        # Import resolve helper
        try:
            from ..cache_manager import resolve_user_id_for_query
        except ImportError:
            try:
                from web.cache_manager import resolve_user_id_for_query
            except ImportError:
                def resolve_user_id_for_query(user_id: str):
                    return str(user_id), None
        
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        # Count with current user_id first
        query = hidden_projects_log_collection.where(filter=FieldFilter('user_id', '==', current_user_id)).stream()
        count = sum(1 for _ in query)
        
        # If no results and we have old_user_id, count with that and migrate
        if count == 0 and old_user_id:
            query_old = hidden_projects_log_collection.where(filter=FieldFilter('user_id', '==', old_user_id)).stream()
            docs = list(query_old)
            if docs:
                # Migrate all documents to use new user_id
                # Get the database client from the collection
                try:
                    from ..db import db
                except ImportError:
                    try:
                        from web.db import db
                    except ImportError:
                        db = None
                
                if db:
                    batch = db.batch()
                    migrated_count = 0
                    for doc in docs:
                        batch.update(doc.reference, {'user_id': current_user_id})
                        migrated_count += 1
                    if migrated_count > 0:
                        batch.commit()
                        print(f"[Migration] Migrated {migrated_count} hidden project log(s) from old user_id {old_user_id} to {current_user_id}")
                    count = migrated_count
                else:
                    # Fallback: update documents one by one
                    migrated_count = 0
                    for doc in docs:
                        doc.reference.update({'user_id': current_user_id})
                        migrated_count += 1
                    print(f"[Migration] Migrated {migrated_count} hidden project log(s) from old user_id {old_user_id} to {current_user_id}")
                    count = migrated_count
        
        return count
    except Exception as e:
        print(f"Error getting projects processed count: {e}")
        return 0


def get_projects_remaining(user_id):
    """Calculate remaining credits for user
    
    Args:
        user_id: User ID
        
    Returns:
        Number of projects remaining (limit - processed), or None if unlimited
    """
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            return None
        
        user_data = user_doc.to_dict()
        limit = user_data.get('projects_processed_limit', 500)
        # If limit is very large (effectively unlimited), return None
        if limit is None or limit >= 999999999:
            return None
        
        processed = get_projects_processed_count(user_id)
        remaining = max(0, limit - processed)
        return remaining
    except Exception as e:
        print(f"Error getting projects remaining: {e}")
        return None


def check_user_has_credits(user_id, projects_needed=1):
    """Check if user can process N projects
    
    Args:
        user_id: User ID
        projects_needed: Number of projects needed (default: 1)
        
    Returns:
        Tuple (has_credits: bool, remaining: int or None)
    """
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            return (False, 0)
        
        user_data = user_doc.to_dict()
        limit = user_data.get('projects_processed_limit', 500)
        # If limit is None or very large (effectively unlimited), always return True
        if limit is None or limit >= 999999999:
            return (True, None)
        
        processed = get_projects_processed_count(user_id)
        remaining = limit - processed
        
        return (remaining >= projects_needed, max(0, remaining))
    except Exception as e:
        print(f"Error checking user credits: {e}")
        return (False, 0)


def get_user_billing_info(user_id):
    """Get user billing information
    
    Args:
        user_id: User ID
        
    Returns:
        Dictionary with billing info:
        - projects_processed_limit: Number of projects user can process
        - projects_processed_count: Total projects processed (counted from hidden_projects_log)
        - projects_remaining: Number of projects remaining
    """
    # Always get the actual projects processed count from the hidden projects log
    # This count should be accurate regardless of whether a user document exists
    try:
        processed = get_projects_processed_count(user_id)
    except Exception as e:
        print(f"Error getting projects processed count in billing info: {e}")
        processed = 0
    
    if users_collection is None:
        return {
            'projects_processed_limit': 500,
            'projects_processed_count': processed,
            'projects_remaining': max(0, 500 - processed)
        }
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            # User document doesn't exist, but we still have the processed count
            return {
                'projects_processed_limit': 500,
                'projects_processed_count': processed,
                'projects_remaining': max(0, 500 - processed)
            }
        
        user_data = user_doc.to_dict()
        limit = user_data.get('projects_processed_limit', 500)
        
        # Calculate remaining (None if unlimited)
        if limit is None or limit >= 999999999:
            remaining = None
        else:
            remaining = max(0, limit - processed)
        
        return {
            'projects_processed_limit': limit,
            'projects_processed_count': processed,
            'projects_remaining': remaining
        }
    except Exception as e:
        print(f"Error getting user billing info: {e}")
        # Even on error, return the actual processed count we got earlier
        return {
            'projects_processed_limit': 500,
            'projects_processed_count': processed,
            'projects_remaining': max(0, 500 - processed)
        }


def update_user_billing_limit(user_id, new_limit):
    """Update user's projects_processed_limit (admin function)
    
    Args:
        user_id: User ID
        new_limit: New limit value (can be very large for lifetime users)
        
    Returns:
        True if successful, False otherwise
    """
    if users_collection is None:
        raise Exception("Firestore connection not available. Please ensure Firestore is configured.")
    try:
        # Validate limit
        if new_limit is not None and (not isinstance(new_limit, int) or new_limit < 0):
            raise ValueError("Invalid limit value. Must be a positive integer or None.")
        
        update_data = {
            'projects_processed_limit': new_limit,
            'updated_at': datetime.utcnow()
        }
        
        # Reset notification flags when limit is updated so notifications can be sent again
        update_data['credits_low_email_sent'] = False
        update_data['credits_exhausted_email_sent'] = False
        
        users_collection.document(str(user_id)).update(update_data)
        return True
    except Exception as e:
        raise Exception(f"Failed to update user billing limit: {e}")


def check_and_send_credit_notifications(user_id):
    """Check user's credit status and send email notifications if needed
    
    Args:
        user_id: User ID
        
    Returns:
        None (sends emails as side effect)
    """
    if users_collection is None:
        return
    
    try:
        user_doc = users_collection.document(str(user_id)).get()
        if not user_doc.exists:
            return
        
        user_data = user_doc.to_dict()
        
        # Get billing info
        billing_info = get_user_billing_info(user_id)
        limit = billing_info.get('projects_processed_limit', 500)
        processed = billing_info.get('projects_processed_count', 0)
        remaining = billing_info.get('projects_remaining')
        
        # If limit is None or very large (effectively unlimited), skip notifications
        if limit is None or limit >= 999999999:
            return
        
        # Get user email
        user_email = user_data.get('username')  # Email is stored in username field
        if not user_email:
            return
        
        # Import email service here to avoid circular imports
        try:
            from ..services.email_service import send_credits_low_email, send_credits_exhausted_email
        except ImportError:
            from services.email_service import send_credits_low_email, send_credits_exhausted_email
        
        # Check if limit reached
        if processed >= limit:
            # Check if exhausted email already sent
            if not user_data.get('credits_exhausted_email_sent', False):
                try:
                    send_credits_exhausted_email(user_email, limit)
                    # Mark as sent
                    users_collection.document(str(user_id)).update({
                        'credits_exhausted_email_sent': True,
                        'updated_at': datetime.utcnow()
                    })
                except Exception as e:
                    print(f"Error sending credits exhausted email: {e}")
        
        # Check if < 10% remaining
        elif remaining is not None and remaining < limit * 0.1:
            # Check if low credits email already sent
            if not user_data.get('credits_low_email_sent', False):
                try:
                    send_credits_low_email(user_email, remaining, limit)
                    # Mark as sent
                    users_collection.document(str(user_id)).update({
                        'credits_low_email_sent': True,
                        'updated_at': datetime.utcnow()
                    })
                except Exception as e:
                    print(f"Error sending credits low email: {e}")
    
    except Exception as e:
        print(f"Error checking credit notifications: {e}")
