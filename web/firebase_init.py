#!/usr/bin/env python3
"""
Centralized Firebase Admin initialization
Handles credential setup for both local development and Cloud Functions
"""

import os
import logging
import firebase_admin
from firebase_admin import credentials as firebase_creds
from pathlib import Path

# Create logger for this module
logger = logging.getLogger(__name__)


def is_cloud_environment():
    """Check if we're running in Cloud Functions/Cloud Run"""
    return bool(
        os.environ.get('GCP_PROJECT') or 
        os.environ.get('GCLOUD_PROJECT') or 
        os.environ.get('FUNCTION_NAME') or 
        os.environ.get('K_SERVICE')
    )


def initialize_firebase_admin(project_id=None, project_root=None):
    """
    Initialize Firebase Admin SDK with appropriate credentials.
    
    Args:
        project_id: Optional project ID. If None, will use GCP_PROJECT or PROJECT_ID from env
        project_root: Optional project root path for resolving relative credential paths
    
    Returns:
        bool: True if initialization succeeded or was already initialized
    """
    # Check if already initialized
    if firebase_admin._apps:
        logger.info("Firebase Admin already initialized")
        return True
    
    # Get project ID from environment (Cloud Functions sets GCP_PROJECT or GCLOUD_PROJECT automatically)
    if not project_id:
        project_id = (os.environ.get('GCP_PROJECT') or 
                     os.environ.get('GCLOUD_PROJECT') or 
                     os.environ.get('PROJECT_ID'))
    
    # Check environment
    is_cloud = is_cloud_environment()
    google_app_creds = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    
    logger.info(
        f"Initializing Firebase Admin (GCP_PROJECT={os.environ.get('GCP_PROJECT')}, "
        f"GCLOUD_PROJECT={os.environ.get('GCLOUD_PROJECT')}, "
        f"PROJECT_ID={os.environ.get('PROJECT_ID')}, Cloud={is_cloud}, "
        f"GOOGLE_APPLICATION_CREDENTIALS={google_app_creds})"
    )
    
    try:
        # In Cloud Functions, ALWAYS use default credentials (ignore GOOGLE_APPLICATION_CREDENTIALS)
        if is_cloud:
            # Temporarily unset GOOGLE_APPLICATION_CREDENTIALS to force default credentials
            old_creds = os.environ.pop('GOOGLE_APPLICATION_CREDENTIALS', None)
            if old_creds:
                logger.info(f"Unsetting GOOGLE_APPLICATION_CREDENTIALS ({old_creds}) to use default credentials")
            
            try:
                # Use ApplicationDefault credentials explicitly
                cred = firebase_creds.ApplicationDefault()
                init_options = {}
                if project_id:
                    init_options['projectId'] = project_id
                firebase_admin.initialize_app(cred, init_options)
                logger.info(
                    f"Firebase Admin initialized with Application Default Credentials "
                    f"(Cloud environment, Project: {project_id or 'auto-detected'})"
                )
            except Exception as e:
                # Fallback to default initialization
                logger.warning(f"ApplicationDefault failed ({e}), trying default initialization...")
                init_options = {}
                if project_id:
                    init_options['projectId'] = project_id
                firebase_admin.initialize_app(**init_options)
                logger.info(
                    f"Firebase Admin initialized with default credentials "
                    f"(fallback, Project: {project_id or 'auto-detected'})"
                )
            # Don't restore GOOGLE_APPLICATION_CREDENTIALS in cloud - we want to use default credentials
            return True
        
        # Local development - use service account file if available
        elif google_app_creds:
            cred_path = Path(google_app_creds)
            if not cred_path.is_absolute() and project_root:
                cred_path = Path(project_root) / cred_path
            
            if cred_path.exists():
                cred = firebase_creds.Certificate(str(cred_path))
                init_options = {}
                if project_id:
                    init_options['projectId'] = project_id
                firebase_admin.initialize_app(cred, init_options)
                logger.info(f"Firebase Admin initialized with service account: {cred_path}")
                return True
            else:
                # File doesn't exist - try default credentials
                logger.warning(
                    f"Service account file not found ({cred_path}), "
                    f"trying default credentials..."
                )
                if project_id:
                    firebase_admin.initialize_app({'projectId': project_id})
                    logger.info(f"Firebase Admin initialized with default credentials (Project: {project_id})")
                    return True
                else:
                    raise FileNotFoundError(
                        f"Service account credentials file not found: {cred_path} "
                        f"and no PROJECT_ID/GCP_PROJECT available"
                    )
        
        # No GOOGLE_APPLICATION_CREDENTIALS set - use default credentials
        elif project_id:
            firebase_admin.initialize_app({'projectId': project_id})
            logger.info(f"Firebase Admin initialized with default credentials (Project: {project_id})")
            return True
        
        # Last resort - try default initialization
        else:
            try:
                firebase_admin.initialize_app()
                logger.info("Firebase Admin initialized with default credentials (no project ID specified)")
                return True
            except ValueError as e:
                if "already exists" in str(e).lower():
                    logger.info("Firebase Admin already initialized")
                    return True
                else:
                    raise ValueError(
                        "Either GOOGLE_APPLICATION_CREDENTIALS or PROJECT_ID/GCP_PROJECT must be set, "
                        "or default credentials must be available"
                    )
    
    except ValueError as e:
        # Already initialized - this is OK
        if "already exists" in str(e).lower() or "already initialized" in str(e).lower():
            logger.info("Firebase Admin already initialized (from previous initialization)")
            return True
        else:
            logger.warning(f"Firebase Admin initialization issue: {e}")
            raise
    
    except Exception as e:
        logger.error(f"Error initializing Firebase Admin: {e}", exc_info=True)
        raise
