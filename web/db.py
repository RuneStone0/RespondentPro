#!/usr/bin/env python3
"""
Database connection and collection setup for Respondent.io Manager
Firestore implementation
"""

import os
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from pathlib import Path

# Create logger for this module
logger = logging.getLogger(__name__)

# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Firebase/Firestore connection
# Use GCP_PROJECT or GCLOUD_PROJECT (set by Cloud Functions) or PROJECT_ID (for local dev)
# Note: Cannot use FIREBASE_PROJECT_ID as env var (reserved prefix in Cloud Functions)
FIREBASE_PROJECT_ID = (os.environ.get('GCP_PROJECT') or 
                       os.environ.get('GCLOUD_PROJECT') or 
                       os.environ.get('PROJECT_ID'))

# Initialize collections as None (will be set if connection succeeds)
db = None
users_collection = None
session_keys_collection = None
projects_cache_collection = None
user_preferences_collection = None
hidden_projects_log_collection = None
hide_feedback_collection = None
category_recommendations_collection = None
user_profiles_collection = None
project_details_collection = None
topics_collection = None
ai_analysis_cache_collection = None
user_notifications_collection = None
firestore_available = False

try:
    # Check if we're in cloud environment - if so, ensure GOOGLE_APPLICATION_CREDENTIALS is unset
    # before getting Firestore client (google.auth.default() checks this env var)
    try:
        from .firebase_init import is_cloud_environment
    except ImportError:
        from firebase_init import is_cloud_environment
    
    # Check if Firebase Admin is already initialized (e.g., from main.py)
    if firebase_admin._apps:
        logger.info("Firebase Admin already initialized, will get Firestore client...")
        # Ensure GOOGLE_APPLICATION_CREDENTIALS is unset in cloud before getting client
        # This is critical because firestore.client() calls google.auth.default() which checks this env var
        if is_cloud_environment() and 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
            old_creds = os.environ.pop('GOOGLE_APPLICATION_CREDENTIALS')
            logger.info(f"Unsetting GOOGLE_APPLICATION_CREDENTIALS ({old_creds}) before getting Firestore client")
    else:
        # Use centralized initialization function
        try:
            from .firebase_init import initialize_firebase_admin
            # initialize_firebase_admin() checks if already initialized internally
            initialize_firebase_admin(project_id=FIREBASE_PROJECT_ID, project_root=PROJECT_ROOT)
        except ImportError:
            # Fallback if firebase_init not available (shouldn't happen, but be safe)
            try:
                from firebase_init import initialize_firebase_admin
                # initialize_firebase_admin() checks if already initialized internally
                initialize_firebase_admin(project_id=FIREBASE_PROJECT_ID, project_root=PROJECT_ROOT)
            except ImportError:
                logger.warning("Could not import firebase_init, using basic initialization")
                # Check again before initializing (might have been initialized by another import)
                if not firebase_admin._apps:
                    try:
                        firebase_admin.initialize_app()
                    except ValueError as e:
                        # Already initialized - this is OK (might have been initialized between check and call)
                        if "already exists" in str(e).lower() or "already initialized" in str(e).lower():
                            logger.info("Firebase Admin already initialized (caught during db.py fallback initialization)")
                        else:
                            raise
    
    # Get Firestore client (whether we just initialized or it was already initialized)
    # CRITICAL: Ensure GOOGLE_APPLICATION_CREDENTIALS is unset in cloud before calling firestore.client()
    # because firestore.client() internally calls google.auth.default() which checks this env var
    if is_cloud_environment() and 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        old_creds = os.environ.pop('GOOGLE_APPLICATION_CREDENTIALS')
        logger.info(f"Unsetting GOOGLE_APPLICATION_CREDENTIALS ({old_creds}) before calling firestore.client()")
    
    logger.debug("Getting Firestore client...")
    try:
        db = firestore.client()
        logger.info("Firestore client obtained successfully")
    except Exception as client_error:
        logger.error(f"Failed to get Firestore client: {client_error}", exc_info=True)
        raise  # Re-raise to be caught by outer exception handler
    
    # Collections (Firestore collections are accessed via db.collection())
    logger.debug("Setting up Firestore collections...")
    users_collection = db.collection('users')
    session_keys_collection = db.collection('session_keys')
    projects_cache_collection = db.collection('projects_cache')
    user_preferences_collection = db.collection('user_preferences')
    hidden_projects_log_collection = db.collection('hidden_projects_log')
    hide_feedback_collection = db.collection('hide_feedback')
    category_recommendations_collection = db.collection('category_recommendations')
    user_profiles_collection = db.collection('user_profiles')
    project_details_collection = db.collection('project_details')
    topics_collection = db.collection('topics')
    ai_analysis_cache_collection = db.collection('ai_analysis_cache')
    user_notifications_collection = db.collection('user_notifications')
    logger.debug("Firestore collections set up successfully")
    
    # Test connection by attempting a simple operation
    try:
        # Try to read from a collection (this will fail if permissions are wrong or database doesn't exist)
        logger.debug("Testing Firestore connection...")
        list(users_collection.limit(1).stream())
        logger.debug("Firestore connection test successful")
        firestore_available = True
        logger.info("Firestore connection established successfully")
    except Exception as perm_error:
        error_msg = str(perm_error).lower()
        if "does not exist" in error_msg or "404" in error_msg:
            logger.warning(
                f"Firestore database does not exist: {perm_error}. "
                "This is expected in local development without Firestore emulator. "
                "Set FIRESTORE_EMULATOR_HOST to use emulator, or ensure database exists in GCP project.",
                exc_info=False  # Don't print full traceback for expected local dev scenario
            )
        else:
            logger.warning(
                f"Firestore permissions issue during test: {perm_error}. "
                "Please ensure your service account has proper Firestore permissions.",
                exc_info=True
            )
        # Set firestore_available to False if connection test fails
        firestore_available = False
        # Don't fail completely, but mark as unavailable
    
except ValueError as e:
    # Check if Firebase Admin is already initialized (this is OK)
    error_msg = str(e).lower()
    if "already exists" in error_msg or "already initialized" in error_msg:
        try:
            logger.info("Firebase Admin already initialized, getting Firestore client...")
            # Firebase Admin is already initialized, just get the client
            db = firestore.client()
            # Set up collections
            users_collection = db.collection('users')
            session_keys_collection = db.collection('session_keys')
            projects_cache_collection = db.collection('projects_cache')
            user_preferences_collection = db.collection('user_preferences')
            hidden_projects_log_collection = db.collection('hidden_projects_log')
            hide_feedback_collection = db.collection('hide_feedback')
            category_recommendations_collection = db.collection('category_recommendations')
            user_profiles_collection = db.collection('user_profiles')
            project_details_collection = db.collection('project_details')
            topics_collection = db.collection('topics')
            ai_analysis_cache_collection = db.collection('ai_analysis_cache')
            user_notifications_collection = db.collection('user_notifications')
            firestore_available = True
            logger.info("Firestore connection established successfully (using existing Firebase Admin initialization)")
        except Exception as client_error:
            logger.error(
                f"Failed to get Firestore client after Firebase Admin was already initialized: {client_error}",
                exc_info=True
            )
            db = None
            users_collection = None
            session_keys_collection = None
            projects_cache_collection = None
            user_preferences_collection = None
            hidden_projects_log_collection = None
            hide_feedback_collection = None
            category_recommendations_collection = None
            user_profiles_collection = None
            project_details_collection = None
            topics_collection = None
            ai_analysis_cache_collection = None
            user_notifications_collection = None
            firestore_available = False
    else:
        logger.error(
            f"Firestore connection failed: {e}. "
            "Please ensure Firebase is configured correctly: "
            "1. Set PROJECT_ID or GCP_PROJECT environment variable (GCP_PROJECT is auto-set in Cloud Functions), "
            "2. Set GOOGLE_APPLICATION_CREDENTIALS to path of service account JSON file, "
            "3. Or ensure default credentials are available (for Cloud Functions/Cloud Run)"
        )
        db = None
        users_collection = None
        session_keys_collection = None
        projects_cache_collection = None
        user_preferences_collection = None
        hidden_projects_log_collection = None
        hide_feedback_collection = None
        category_recommendations_collection = None
        user_profiles_collection = None
        project_details_collection = None
        topics_collection = None
        ai_analysis_cache_collection = None
        user_notifications_collection = None
        firestore_available = False
except Exception as e:
    logger.error(
        f"Firestore connection failed: {e}. "
        "Please ensure Firebase is configured correctly: "
        "1. Set PROJECT_ID or GCP_PROJECT environment variable (GCP_PROJECT is auto-set in Cloud Functions), "
        "2. Set GOOGLE_APPLICATION_CREDENTIALS to path of service account JSON file, "
        "3. Or ensure default credentials are available (for Cloud Functions/Cloud Run)",
        exc_info=True
    )
    db = None
    users_collection = None
    session_keys_collection = None
    projects_cache_collection = None
    user_preferences_collection = None
    hidden_projects_log_collection = None
    hide_feedback_collection = None
    category_recommendations_collection = None
    user_profiles_collection = None
    project_details_collection = None
    topics_collection = None
    ai_analysis_cache_collection = None
    user_notifications_collection = None
    firestore_available = False
