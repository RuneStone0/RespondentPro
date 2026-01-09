"""
Main entry point for Cloud Functions
This file is required by Firebase Functions SDK discovery
It sets up the Flask app for Cloud Functions 2nd Gen
"""

import os
import sys
import logging
from pathlib import Path

# Create logger for this module
logger = logging.getLogger(__name__)

# Since we're deploying from project root, web module is directly accessible
# But we still need to add the project root to path for imports
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set environment variables for Firebase
# GCP_PROJECT or GCLOUD_PROJECT is automatically set by Cloud Functions
# For local development, it can be set in .env.yaml or PROJECT_ID env var
# Note: Cannot use FIREBASE_PROJECT_ID as env var (reserved prefix)

# Check if we're in cloud environment
is_cloud = bool(os.environ.get('GCP_PROJECT') or os.environ.get('GCLOUD_PROJECT') or 
                os.environ.get('FUNCTION_NAME') or os.environ.get('K_SERVICE'))

# Get project ID from environment variables (Cloud Functions sets these automatically)
project_id = (os.environ.get('GCP_PROJECT') or 
              os.environ.get('GCLOUD_PROJECT') or 
              os.environ.get('PROJECT_ID'))

# For local development, try reading from .firebaserc
if not project_id:
    try:
        import json
        firebaserc_path = PROJECT_ROOT / '.firebaserc'
        if firebaserc_path.exists():
            with open(firebaserc_path, 'r') as f:
                firebaserc = json.load(f)
                project_id = firebaserc.get('projects', {}).get('default')
                if project_id:
                    logger.info(f"Read project ID from .firebaserc: {project_id}")
    except Exception as e:
        logger.debug(f"Could not read .firebaserc: {e}")

# In cloud environment, project ID must be available
if not project_id:
    if is_cloud:
        error_msg = (
            "Project ID not found! In Cloud Functions, GCP_PROJECT or GCLOUD_PROJECT "
            "should be automatically set. Please check your Cloud Functions configuration."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)
    else:
        # Local development - allow None, will use default credentials
        logger.warning("No project ID found. Using default credentials (project ID will be auto-detected)")

if project_id:
    os.environ['PROJECT_ID'] = project_id  # Set for backward compatibility
    logger.info(f"Using project ID: {project_id}")
else:
    logger.info("No project ID set - will use default credentials with auto-detected project")

# Initialize Firebase Admin (if not already initialized)
try:
    from web.firebase_init import initialize_firebase_admin
    initialize_firebase_admin(project_id=project_id, project_root=PROJECT_ROOT)
except ImportError as e:
    logger.warning(f"Could not import firebase_init: {e}")
    # Fallback to basic initialization
    try:
        import firebase_admin
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
            logger.info("Firebase Admin initialized (fallback)")
    except Exception as fallback_error:
        logger.warning(f"Firebase Admin initialization failed: {fallback_error}", exc_info=True)
except Exception as e:
    logger.warning(f"Firebase Admin initialization error: {e}", exc_info=True)

# Import the Flask app
try:
    from web.app import app
    # Verify the app is properly initialized
    if app is None:
        raise ValueError("Flask app is None")
    logger.info(f"Flask app loaded successfully: {app}")
except Exception as e:
    logger.error(f"Error importing Flask app: {e}", exc_info=True)
    raise

# For Cloud Functions 2nd Gen, create an HTTP function wrapper for the Flask app
# Functions-framework expects a callable function, not a Flask app object
from functions_framework import http
from flask import Response

@http
def respondentpro(request):
    """
    HTTP function wrapper for Flask app
    Converts the Cloud Functions request to Flask's WSGI interface
    """
    # Use Flask's test request context to handle the request
    with app.test_request_context(
        path=request.path,
        method=request.method,
        headers=dict(request.headers),
        data=request.get_data(),
        query_string=request.query_string.decode('utf-8') if request.query_string else ''
    ):
        # Process the request through Flask
        response = app.full_dispatch_request()
        
        # Convert Flask response to functions-framework compatible format
        # The response should be returned directly - functions-framework handles it
        return response
