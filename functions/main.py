"""
Cloud Functions entry point for RespondentPro
Uses functions-framework to run Flask app as a Cloud Function
"""

import os
import sys
from pathlib import Path

# Since we're deploying from project root, web module is directly accessible
# But we still need to add the project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set environment variables for Firebase
# GCP_PROJECT is automatically set by Cloud Functions
# For local development, it can be set in .env.yaml
# Note: Cannot use FIREBASE_PROJECT_ID as env var (reserved prefix)
project_id = os.environ.get('GCP_PROJECT') or os.environ.get('PROJECT_ID', 'respondentpro')
os.environ['PROJECT_ID'] = project_id  # Set for backward compatibility

# Initialize Firebase Admin (if not already initialized)
try:
    import firebase_admin
    from firebase_admin import initialize_app
    if not firebase_admin._apps:
        initialize_app()
except (ValueError, ImportError):
    # Already initialized or firebase_admin not available
    pass

# Import the Flask app
try:
    from web.app import app
    # Verify the app is properly initialized
    if app is None:
        raise ValueError("Flask app is None")
    print(f"Flask app loaded successfully: {app}")
except Exception as e:
    print(f"Error importing Flask app: {e}")
    import traceback
    traceback.print_exc()
    raise

# For Cloud Functions 2nd Gen, functions-framework automatically detects Flask apps
# and runs them as HTTP servers on the PORT environment variable (default 8080)
# Export the Flask app directly - functions-framework will detect it and run it
# The functions-framework uses Flask's WSGI interface to run the app
respondentpro = app
