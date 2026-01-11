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

# Lazy import Flask app to avoid blocking during function discovery
# The app will only be imported when the function is actually called
_app = None

def get_app():
    """Lazy loader for Flask app to avoid blocking during function discovery"""
    global _app
    if _app is None:
        try:
            from web.app import app as flask_app
            if flask_app is None:
                raise ValueError("Flask app is None")
            _app = flask_app
            logger.info(f"Flask app loaded successfully: {_app}")
        except Exception as e:
            logger.error(f"Error importing Flask app: {e}", exc_info=True)
            raise
    return _app

# For Cloud Functions 2nd Gen, create an HTTP function wrapper for the Flask app
# Functions-framework expects a callable function, not a Flask app object
from functions_framework import http

@http
def respondentpro(request):
    """
    HTTP function wrapper for Flask app
    Converts the Cloud Functions request to Flask's WSGI interface
    """
    # Lazy load the app only when the function is called
    app = get_app()
    
    # Convert headers to dict (functions-framework provides them as a case-insensitive dict-like object)
    headers = dict(request.headers)
    
    # Extract Cookie header - Firebase Hosting only forwards __session cookie to Cloud Functions
    # Try to get Cookie header from headers
    cookie_header = None
    
    # Try all case variations
    for key in headers.keys():
        if key.lower() == 'cookie':
            cookie_header = headers[key]
            break
    
    # If not in headers dict, try request.headers directly
    if not cookie_header:
        try:
            cookie_header = request.headers.get('Cookie') or request.headers.get('cookie')
        except:
            pass
    
    # If still not found, check if functions-framework provides cookies as attribute
    if not cookie_header and hasattr(request, 'cookies') and request.cookies:
        cookie_parts = [f"{name}={value}" for name, value in request.cookies.items()]
        if cookie_parts:
            cookie_header = '; '.join(cookie_parts)
    
    # Flask's test_request_context needs cookies in environ_base as HTTP_COOKIE
    environ_base = {}
    if cookie_header:
        environ_base['HTTP_COOKIE'] = cookie_header
        logger.debug(f"Cookie header found, setting HTTP_COOKIE: {cookie_header[:100]}...")
    else:
        logger.debug("No cookie header in request")
    
    # Flask's test_request_context should parse cookies from the Cookie header
    # But if it doesn't, we need to ensure they're in the WSGI environ
    # The key is that Flask's Request class looks for cookies in environ['HTTP_COOKIE']
    # But test_request_context might not set this from headers automatically
    
    with app.test_request_context(
        path=request.path,
        method=request.method,
        headers=headers,
        data=request.get_data(),
        query_string=request.query_string.decode('utf-8') if request.query_string else '',
        environ_base=environ_base
    ):
        # Debug: Verify cookies were parsed by Flask
        if cookie_header:
            logger.debug(f"Cookie header was: {cookie_header[:200]}...")
            logger.debug(f"Flask parsed cookies keys: {list(request.cookies.keys())}")
            if 'firebase_id_token' in request.cookies:
                logger.debug("✓ firebase_id_token cookie successfully parsed!")
            else:
                logger.warning(f"✗ firebase_id_token NOT in cookies. Available: {list(request.cookies.keys())}")
                logger.warning(f"Request environ HTTP_COOKIE: {request.environ.get('HTTP_COOKIE', 'NOT SET')[:200]}")
        else:
            logger.warning("No cookie header was extracted from request")
        
        # Process the request through Flask
        response = app.full_dispatch_request()
        
        # Convert Flask response to functions-framework compatible format
        # The response should be returned directly - functions-framework handles it
        return response


# Scheduled jobs are now handled via HTTP endpoints in web/routes/scheduled_jobs_routes.py
# They are called by Google Cloud Scheduler (configured in cloudbuild.yaml)
# No need to import scheduled functions here anymore
