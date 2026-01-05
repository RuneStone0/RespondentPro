#!/usr/bin/env python3
"""
User management service for Respondent.io Manager
"""

import base64
import secrets
from bson import ObjectId
from datetime import datetime, timedelta

# Import database collections
try:
    from ..db import users_collection, session_keys_collection, user_preferences_collection, projects_cache_collection, hidden_projects_log_collection
except ImportError:
    from web.db import users_collection, session_keys_collection, user_preferences_collection, projects_cache_collection, hidden_projects_log_collection


def get_user_by_email(email):
    """Get user document by email (stored in username field), returns user_id (_id)"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        # Email is stored in the username field for backward compatibility
        user_doc = users_collection.find_one({'username': email})
        if user_doc:
            return str(user_doc['_id'])  # Return user_id as string
        return None
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to get user from MongoDB: {e}")


def get_user_by_username(username):
    """Legacy function - use get_user_by_email instead. Kept for backward compatibility."""
    return get_user_by_email(username)


def get_email_by_user_id(user_id):
    """Get email (stored in username field) by user_id"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if user_doc:
            return user_doc.get('username')  # Email is stored in username field
        return None
    except Exception as e:
        raise Exception(f"Failed to get email from MongoDB: {e}")


def get_username_by_user_id(user_id):
    """Legacy function - use get_email_by_user_id instead. Kept for backward compatibility."""
    return get_email_by_user_id(user_id)


def user_exists_by_email(email):
    """Check if user exists by email"""
    return get_user_by_email(email) is not None


def user_exists(username):
    """Legacy function - use user_exists_by_email instead. Kept for backward compatibility."""
    return user_exists_by_email(username)


def generate_verification_token(user_id):
    """Generate a verification token for email verification"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)  # Token expires in 7 days
    
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'verification_token': token,
                    'verification_token_expires': expires_at,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        return token
    except Exception as e:
        raise Exception(f"Failed to generate verification token: {e}")


def generate_login_token(user_id):
    """Generate a login token for email-based authentication"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
    
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'login_token': token,
                    'login_token_expires': expires_at,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        return token
    except Exception as e:
        raise Exception(f"Failed to generate login token: {e}")


def verify_login_token(user_id, token):
    """Verify login token. Returns True if successful, False otherwise."""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return False
        
        stored_token = user_doc.get('login_token')
        token_expires = user_doc.get('login_token_expires')
        
        # Check if token matches and hasn't expired
        if stored_token != token:
            return False
        
        if token_expires and isinstance(token_expires, datetime):
            if datetime.utcnow() > token_expires:
                return False
        
        # Clear the login token after use
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$unset': {
                    'login_token': '',
                    'login_token_expires': ''
                },
                '$set': {
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        return True
    except Exception as e:
        raise Exception(f"Failed to verify login token: {e}")


def create_user(email):
    """Create a new user with email (stored in username field) and return user_id (_id)"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        # Validate email format
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            raise ValueError("Invalid email format")
        
        # Check if user already exists
        existing_user = users_collection.find_one({'username': email})
        if existing_user:
            return str(existing_user['_id'])
        
        # Generate verification token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        # Create new user - email is stored in username field for backward compatibility
        result = users_collection.insert_one({
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
        })
        
        return str(result.inserted_id)
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to create user in MongoDB: {e}")


def load_credentials_by_user_id(user_id, rp_id=None):
    """Load passkey credentials for a specific user_id from MongoDB (stored in users collection)
    
    Args:
        user_id: User ID
        rp_id: Optional relying party ID to filter credentials. If None, returns all credentials.
               If specified and no matching credential found, returns None for backward compatibility.
    
    Returns:
        If rp_id is None: List of all credentials
        If rp_id is specified: Single credential dict matching rp_id, or None if not found
    """
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return None
        
        # Check for new credentials array format
        if 'credentials' in user_doc and isinstance(user_doc['credentials'], list):
            credentials_list = []
            for cred_doc in user_doc['credentials']:
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
        
        # Backward compatibility: check for old single credential format
        if 'credential' in user_doc:
            cred_doc = user_doc['credential']
            cred = {
                'credential_id': None,
                'public_key': None,
                'counter': cred_doc.get('counter', 0),
                'rp_id': 'localhost'  # Default for old credentials
            }
            
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
            
            # If rp_id filter specified, check if it matches
            if rp_id is not None and cred.get('rp_id') != rp_id:
                return None
            
            return cred if rp_id is None else (cred if cred.get('rp_id') == rp_id else None)
        
        return None
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to load credentials from MongoDB: {e}")


def add_credential_to_user(user_id, cred, rp_id=None):
    """Add a new passkey credential to user's credentials array"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
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
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            raise Exception(f"User {user_id} not found")
        
        # If user has old single credential format, migrate it
        if 'credential' in user_doc and 'credentials' not in user_doc:
            old_cred = user_doc['credential']
            old_cred['rp_id'] = 'localhost'  # Default for migrated credentials
            old_cred['created_at'] = user_doc.get('created_at', datetime.utcnow())
            users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {
                    '$set': {'credentials': [old_cred]},
                    '$unset': {'credential': ''}
                }
            )
        
        # Add new credential to array (avoid duplicates by checking credential_id)
        credential_id_str = credential_doc['credential_id']
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$pull': {'credentials': {'credential_id': credential_id_str}},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$push': {'credentials': credential_doc},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to add credential to MongoDB: {e}")


def update_credential_counter(user_id, credential_id, new_counter):
    """Update the counter for a specific credential"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        # Convert credential_id to string if it's bytes
        if isinstance(credential_id, bytes):
            credential_id_str = base64.urlsafe_b64encode(credential_id).decode('utf-8').rstrip('=')
        else:
            credential_id_str = str(credential_id)
        
        users_collection.update_one(
            {
                '_id': ObjectId(user_id),
                'credentials.credential_id': credential_id_str
            },
            {
                '$set': {
                    'credentials.$.counter': new_counter,
                    'updated_at': datetime.utcnow()
                }
            }
        )
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to update credential counter: {e}")


def delete_credential_from_user(user_id, credential_id):
    """Delete a specific passkey credential from user's credentials array"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        # Convert credential_id to string if it's bytes
        if isinstance(credential_id, bytes):
            credential_id_str = base64.urlsafe_b64encode(credential_id).decode('utf-8').rstrip('=')
        else:
            credential_id_str = str(credential_id)
        
        result = users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$pull': {'credentials': {'credential_id': credential_id_str}},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )
        
        if result.modified_count == 0:
            raise Exception("Credential not found or already deleted")
        
        return True
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to delete credential from MongoDB: {e}")


# Backward compatibility function
def save_credentials_by_user_id(user_id, cred):
    """Legacy function - use add_credential_to_user instead. Kept for backward compatibility."""
    # Try to determine rp_id from cred or default to localhost
    rp_id = cred.get('rp_id', 'localhost')
    return add_credential_to_user(user_id, cred, rp_id)


def load_user_config(user_id):
    """Load user's Respondent.io config from MongoDB by user_id"""
    if session_keys_collection is None:
        return None
    try:
        config_doc = session_keys_collection.find_one({'user_id': user_id})
        if config_doc:
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
        session_keys_collection.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'last_synced': datetime.utcnow()
                }
            },
            upsert=False
        )
    except Exception as e:
        print(f"Error updating last synced time: {e}")


def save_user_config(user_id, config, profile_id=None):
    """Save user's Respondent.io config to MongoDB by user_id"""
    if session_keys_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        update_data = {
            'user_id': user_id,
            'cookies': config.get('cookies', {}),
            'updated_at': datetime.utcnow()
        }
        if profile_id:
            update_data['profile_id'] = profile_id
        
        session_keys_collection.update_one(
            {'user_id': user_id},
            {'$set': update_data},
            upsert=True
        )
    except Exception as e:
        raise Exception(f"Failed to save to MongoDB: {e}")


def load_user_filters(user_id):
    """Load user's project filter preferences from MongoDB"""
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
        prefs_doc = user_preferences_collection.find_one({'user_id': user_id})
        if prefs_doc and 'filters' in prefs_doc:
            filters = prefs_doc['filters']
            # Backward compatibility: if old format exists, convert to new format
            auto_hide = filters.get('auto_hide', False)
            if not auto_hide:
                # Check old format for backward compatibility
                auto_hide = (
                    filters.get('min_incentive_auto', False) or
                    filters.get('min_hourly_rate_auto', False) or
                    filters.get('hide_remote_auto', False)
                )
            
            # Handle isRemote: check for new format first, then backward compatibility
            is_remote = filters.get('isRemote')
            if is_remote is None:
                # Backward compatibility: if old hide_remote exists, convert to isRemote
                old_hide_remote = filters.get('hide_remote', False)
                if isinstance(old_hide_remote, str):
                    old_hide_remote = old_hide_remote.lower() in ('true', '1', 'yes', 'on')
                if old_hide_remote:
                    is_remote = True
            
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
    """Save user's project filter preferences to MongoDB (stored in user_preferences collection)"""
    if user_preferences_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    
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
        
        # Backward compatibility: check old format if auto_hide not provided
        if not auto_hide:
            auto_hide = (
                filters.get('min_incentive_auto', False) or
                filters.get('min_hourly_rate_auto', False) or
                filters.get('hide_remote_auto', False)
            )
        
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
        user_preferences_collection.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'user_id': user_id,  # Ensure user_id is set when creating new document
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
            },
            upsert=True  # Create document if it doesn't exist so filters can always be saved
        )
    except Exception as e:
        raise Exception(f"Failed to save filters to MongoDB: {e}")


def update_user_onboarding_status(user_id, has_account):
    """Update the has_respondent_account field in the user document"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'has_respondent_account': bool(has_account),
                    'updated_at': datetime.utcnow()
                }
            }
        )
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to update onboarding status in MongoDB: {e}")


def get_user_onboarding_status(user_id):
    """Retrieve the has_respondent_account field from user document"""
    if users_collection is None:
        return None
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if user_doc:
            return user_doc.get('has_respondent_account')
        return None
    except Exception as e:
        print(f"Error getting onboarding status: {e}")
        return None


def get_user_verification_status(user_id):
    """Check if user's email is verified"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return False
        return user_doc.get('email_verified', False)
    except Exception as e:
        raise Exception(f"Failed to get verification status: {e}")


def is_user_verified(user_id):
    """Quick check for middleware - returns boolean, raises if user not found"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            raise Exception(f"User {user_id} not found")
        return user_doc.get('email_verified', False)
    except Exception as e:
        raise Exception(f"Failed to check verification status: {e}")


def verify_user_email(user_id, token):
    """Verify user email with token. Returns True if successful, False otherwise."""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return False
        
        stored_token = user_doc.get('verification_token')
        token_expires = user_doc.get('verification_token_expires')
        
        # Check if token matches and hasn't expired
        if stored_token != token:
            return False
        
        if token_expires and isinstance(token_expires, datetime):
            if datetime.utcnow() > token_expires:
                return False
        
        # Verify the email
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'email_verified': True,
                    'updated_at': datetime.utcnow()
                },
                '$unset': {
                    'verification_token': '',
                    'verification_token_expires': ''
                }
            }
        )
        
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
    """Calculate total projects processed for user.
    
    Counts projects from hidden_projects_log_collection for the user.
    This represents all projects that have been processed (hidden) by the user.
    
    Args:
        user_id: User ID
        
    Returns:
        Total count of projects processed
    """
    if hidden_projects_log_collection is None:
        return 0
    try:
        # Count all projects in hidden_projects_log for this user
        count = hidden_projects_log_collection.count_documents({'user_id': str(user_id)})
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
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return None
        
        limit = user_doc.get('projects_processed_limit', 500)
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
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return (False, 0)
        
        limit = user_doc.get('projects_processed_limit', 500)
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
    if users_collection is None:
        return {
            'projects_processed_limit': 500,
            'projects_processed_count': 0,
            'projects_remaining': 500
        }
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return {
                'projects_processed_limit': 500,
                'projects_processed_count': 0,
                'projects_remaining': 500
            }
        
        limit = user_doc.get('projects_processed_limit', 500)
        processed = get_projects_processed_count(user_id)
        
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
        return {
            'projects_processed_limit': 500,
            'projects_processed_count': 0,
            'projects_remaining': 500
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
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
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
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': update_data}
        )
        return True
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
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
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc:
            return
        
        # Get billing info
        billing_info = get_user_billing_info(user_id)
        limit = billing_info.get('projects_processed_limit', 500)
        processed = billing_info.get('projects_processed_count', 0)
        remaining = billing_info.get('projects_remaining')
        
        # If limit is None or very large (effectively unlimited), skip notifications
        if limit is None or limit >= 999999999:
            return
        
        # Get user email
        user_email = user_doc.get('username')  # Email is stored in username field
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
            if not user_doc.get('credits_exhausted_email_sent', False):
                try:
                    send_credits_exhausted_email(user_email, limit)
                    # Mark as sent
                    users_collection.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$set': {'credits_exhausted_email_sent': True, 'updated_at': datetime.utcnow()}}
                    )
                except Exception as e:
                    print(f"Error sending credits exhausted email: {e}")
        
        # Check if < 10% remaining
        elif remaining is not None and remaining < limit * 0.1:
            # Check if low credits email already sent
            if not user_doc.get('credits_low_email_sent', False):
                try:
                    send_credits_low_email(user_email, remaining, limit)
                    # Mark as sent
                    users_collection.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$set': {'credits_low_email_sent': True, 'updated_at': datetime.utcnow()}}
                    )
                except Exception as e:
                    print(f"Error sending credits low email: {e}")
    
    except Exception as e:
        print(f"Error checking credit notifications: {e}")

