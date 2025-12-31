#!/usr/bin/env python3
"""
User management service for Respondent.io Manager
"""

import base64
from bson import ObjectId
from datetime import datetime

# Import database collections
try:
    from ..db import users_collection, session_keys_collection, user_preferences_collection
except ImportError:
    from web.db import users_collection, session_keys_collection, user_preferences_collection


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
        
        # Create new user - email is stored in username field for backward compatibility
        result = users_collection.insert_one({
            'username': email,  # Email stored in username field
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


def load_credentials_by_user_id(user_id):
    """Load passkey credentials for a specific user_id from MongoDB (stored in users collection)"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_doc or 'credential' not in user_doc:
            return None
        
        cred_doc = user_doc['credential']
        cred = {
            'credential_id': None,
            'public_key': None,
            'counter': cred_doc.get('counter', 0)
        }
        # Convert base64 strings back to bytes for webauthn library
        if 'credential_id' in cred_doc and cred_doc['credential_id']:
            cred_id = cred_doc['credential_id']
            if isinstance(cred_id, str):
                # Add padding if needed
                padding = 4 - (len(cred_id) % 4)
                if padding != 4:
                    cred_id += '=' * padding
                cred['credential_id'] = base64.urlsafe_b64decode(cred_id)
            else:
                cred['credential_id'] = cred_id
        
        if 'public_key' in cred_doc and cred_doc['public_key']:
            pub_key = cred_doc['public_key']
            if isinstance(pub_key, str):
                # Add padding if needed
                padding = 4 - (len(pub_key) % 4)
                if padding != 4:
                    pub_key += '=' * padding
                cred['public_key'] = base64.urlsafe_b64decode(pub_key)
            else:
                cred['public_key'] = pub_key
        
        return cred
    except Exception as e:
        error_msg = str(e)
        if "not allowed" in error_msg.lower() or "AtlasError" in error_msg:
            raise Exception(
                f"MongoDB permissions error: {error_msg}\n"
                "For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.\n"
                "You can set this in Atlas: Database Access → Edit User → Database User Privileges → Add Built-in Role → readWrite"
            )
        raise Exception(f"Failed to load credentials from MongoDB: {e}")


def save_credentials_by_user_id(user_id, cred):
    """Save passkey credentials for a specific user_id to MongoDB (stored in users collection)"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        # Convert bytes to base64 for storage
        credential_doc = {
            'counter': cred.get('counter', 0),
            'updated_at': datetime.utcnow()
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
        
        # Update the user document with the credential
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'credential': credential_doc,
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
        raise Exception(f"Failed to save credentials to MongoDB: {e}")


def load_user_config(user_id):
    """Load user's Respondent.io config from MongoDB by user_id"""
    if session_keys_collection is None:
        return None
    try:
        config_doc = session_keys_collection.find_one({'user_id': user_id})
        if config_doc:
            return {
                'cookies': config_doc.get('cookies', {}),
                'authorization': config_doc.get('authorization'),
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
            'authorization': config.get('authorization'),
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

