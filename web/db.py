#!/usr/bin/env python3
"""
Database connection and collection setup for Respondent.io Manager
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# MongoDB connection
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')
MONGODB_DB = os.environ.get('MONGODB_DB', 'respondent_manager')

# Initialize collections as None (will be set if connection succeeds)
client = None
db = None
users_collection = None
session_keys_collection = None
projects_cache_collection = None
user_preferences_collection = None
hidden_projects_log_collection = None
hide_feedback_collection = None
category_recommendations_collection = None
user_profiles_collection = None
mongo_available = False

try:
    if not MONGODB_DB:
        raise ValueError("MONGODB_DB environment variable is not set")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    # Test connection
    client.server_info()
    db = client[MONGODB_DB]
    # Collections
    users_collection = db['users']
    session_keys_collection = db['session_keys']
    projects_cache_collection = db['projects_cache']
    user_preferences_collection = db['user_preferences']
    hidden_projects_log_collection = db['hidden_projects_log']
    hide_feedback_collection = db['hide_feedback']
    category_recommendations_collection = db['category_recommendations']
    user_profiles_collection = db['user_profiles']
    
    # Create indexes for new collections (non-blocking - failures won't prevent app from starting)
    try:
        if projects_cache_collection is not None:
            projects_cache_collection.create_index([('user_id', 1)], background=True)
            projects_cache_collection.create_index([('project_id', 1)], unique=True, sparse=True, background=True)
        if user_preferences_collection is not None:
            user_preferences_collection.create_index([('user_id', 1)], background=True)
        if hidden_projects_log_collection is not None:
            hidden_projects_log_collection.create_index([('user_id', 1)], background=True)
            hidden_projects_log_collection.create_index([('project_id', 1)], background=True)
            hidden_projects_log_collection.create_index([('hidden_at', 1)], background=True)
            # Unique compound index to prevent duplicate project_id entries per user
            # Drop existing non-unique index if it exists, then create unique one
            try:
                # Try to drop the existing non-unique index if it exists
                hidden_projects_log_collection.drop_index('user_id_1_project_id_1')
            except Exception:
                # Index doesn't exist or has different name, that's fine
                pass
            # Create unique compound index
            hidden_projects_log_collection.create_index(
                [('user_id', 1), ('project_id', 1)], 
                unique=True, 
                background=True,
                name='user_id_1_project_id_1_unique'
            )
        if hide_feedback_collection is not None:
            hide_feedback_collection.create_index([('user_id', 1)], background=True)
            hide_feedback_collection.create_index([('project_id', 1)], background=True)
        if category_recommendations_collection is not None:
            category_recommendations_collection.create_index([('user_id', 1)], background=True)
        if user_profiles_collection is not None:
            user_profiles_collection.create_index([('user_id', 1)], unique=True, background=True)
            user_profiles_collection.create_index([('updated_at', 1)], background=True)
    except Exception as e:
        print(f"Warning: Could not create indexes (this is non-critical): {e}")
    
    # Test read/write permissions by attempting a simple operation
    try:
        users_collection.find_one({})
    except Exception as perm_error:
        print(f"Warning: MongoDB permissions issue: {perm_error}")
        print("The MongoDB user may not have read/write permissions.")
        print("For MongoDB Atlas, ensure your database user has 'readWrite' role on the database.")
        # Don't fail completely, but warn the user
    mongo_available = True
except Exception as e:
    print(f"Error: MongoDB connection failed: {e}")
    print("Please ensure MongoDB is running and MONGODB_URI is correct in .env file")
    if "Atlas" in str(e) or "atlas" in str(e).lower():
        print("\nMongoDB Atlas specific issues:")
        print("1. Ensure your IP address is whitelisted in Atlas Network Access")
        print("2. Ensure your database user has 'readWrite' role on the database")
        print("3. Check that your connection string includes the correct username and password")
    client = None
    db = None
    users_collection = None
    session_keys_collection = None
    projects_cache_collection = None
    user_preferences_collection = None
    hidden_projects_log_collection = None
    hide_feedback_collection = None
    category_recommendations_collection = None
    user_profiles_collection = None
    mongo_available = False

