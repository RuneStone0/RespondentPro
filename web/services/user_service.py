#!/usr/bin/env python3
"""
User management service for Respondent.io Manager
"""

import base64
from bson import ObjectId
from datetime import datetime

# Import database collections
try:
    from ..db import users_collection, session_keys_collection
except ImportError:
    from web.db import users_collection, session_keys_collection


def get_user_by_username(username):
    """Get user document by username, returns user_id (_id)"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'username': username})
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


def get_username_by_user_id(user_id):
    """Get username by user_id"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        user_doc = users_collection.find_one({'_id': ObjectId(user_id)})
        if user_doc:
            return user_doc.get('username')
        return None
    except Exception as e:
        raise Exception(f"Failed to get username from MongoDB: {e}")


def user_exists(username):
    """Check if user exists by username"""
    return get_user_by_username(username) is not None


def create_user(username):
    """Create a new user and return user_id (_id)"""
    if users_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
    try:
        # Check if user already exists
        existing_user = users_collection.find_one({'username': username})
        if existing_user:
            return str(existing_user['_id'])
        
        # Create new user
        result = users_collection.insert_one({
            'username': username,
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
    if session_keys_collection is None:
        return {
            'min_incentive': None,
            'min_incentive_auto': False,
            'min_hourly_rate': None,
            'min_hourly_rate_auto': False,
            'research_types': [],  # List of allowed research types (empty = show all)
            'research_types_auto': False
        }
    try:
        config_doc = session_keys_collection.find_one({'user_id': user_id})
        if config_doc and 'filters' in config_doc:
            filters = config_doc['filters']
            return {
                'min_incentive': filters.get('min_incentive'),
                'min_incentive_auto': filters.get('min_incentive_auto', False),
                'min_hourly_rate': filters.get('min_hourly_rate'),
                'min_hourly_rate_auto': filters.get('min_hourly_rate_auto', False),
                'research_types': filters.get('research_types', []),
                'research_types_auto': filters.get('research_types_auto', False)
            }
    except Exception as e:
        print(f"Error loading user filters: {e}")
    return {
        'min_incentive': None,
        'min_incentive_auto': False,
        'min_hourly_rate': None,
        'min_hourly_rate_auto': False,
        'research_types': [],
        'research_types_auto': False
    }


def save_user_filters(user_id, filters):
    """Save user's project filter preferences to MongoDB"""
    if session_keys_collection is None:
        raise Exception("MongoDB connection not available. Please ensure MongoDB is running.")
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
        
        # Get auto/manual mode settings (default to False if not provided)
        min_incentive_auto = filters.get('min_incentive_auto', False)
        min_hourly_rate_auto = filters.get('min_hourly_rate_auto', False)
        research_types_auto = filters.get('research_types_auto', False)
        
        # Convert to boolean if needed
        if isinstance(min_incentive_auto, str):
            min_incentive_auto = min_incentive_auto.lower() in ('true', '1', 'yes', 'on')
        if isinstance(min_hourly_rate_auto, str):
            min_hourly_rate_auto = min_hourly_rate_auto.lower() in ('true', '1', 'yes', 'on')
        if isinstance(research_types_auto, str):
            research_types_auto = research_types_auto.lower() in ('true', '1', 'yes', 'on')
        
        # Get research types filter (list of allowed research type IDs)
        research_types = filters.get('research_types', [])
        if not isinstance(research_types, list):
            research_types = []
        # Convert to integers and filter out invalid values
        research_types = [int(rt) for rt in research_types if str(rt).isdigit()]
        
        # Update the document with filters
        session_keys_collection.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'filters': {
                        'min_incentive': min_incentive,
                        'min_incentive_auto': bool(min_incentive_auto),
                        'min_hourly_rate': min_hourly_rate,
                        'min_hourly_rate_auto': bool(min_hourly_rate_auto),
                        'research_types': research_types,
                        'research_types_auto': bool(research_types_auto)
                    },
                    'updated_at': datetime.utcnow()
                }
            },
            upsert=False  # Don't create if doesn't exist, user must have config first
        )
    except Exception as e:
        raise Exception(f"Failed to save filters to MongoDB: {e}")

