#!/usr/bin/env python3
"""
Flask web UI for Respondent.io API management with passkey authentication
"""

import os
import secrets
import time
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, render_template
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from .services.grok_service import check_grok_health

# Import database collections
from .db import (
    users_collection, session_keys_collection, projects_cache_collection,
    user_preferences_collection, hidden_projects_log_collection,
    hide_feedback_collection, category_recommendations_collection,
    user_profiles_collection, firestore_available, db
)

# Import user service
from .services.user_service import (
    create_user,
    load_credentials_by_user_id,
    load_user_config, save_user_config, update_last_synced,
    load_user_filters, save_user_filters
)

# Import respondent auth service
from .services.respondent_auth_service import (
    create_respondent_session, verify_respondent_authentication,
    fetch_and_store_user_profile, get_user_profile, fetch_user_profile,
    extract_demographic_params
)

# Import project service
from .services.project_service import (
    fetch_respondent_projects, fetch_all_respondent_projects,
    hide_project_via_api, get_hidden_count, process_and_hide_projects,
    get_hide_progress, hide_progress
)

# Import filter service
from .services.filter_service import (
    apply_filters_to_projects, should_hide_project
)

# Import new modules
from .cache_manager import is_cache_fresh, get_cached_projects, refresh_project_cache, get_cache_stats, mark_projects_hidden_in_cache
from .hidden_projects_tracker import (
    log_hidden_project, get_hidden_projects_count, get_hidden_projects_timeline,
    get_hidden_projects_stats, is_project_hidden
)
from .ai_analyzer import (
    analyze_project, analyze_projects_batch, extract_metadata_with_grok,
    analyze_hide_feedback, find_similar_projects, generate_category_recommendations,
    get_projects_in_category, validate_category_pattern
)
from .preference_learner import (
    record_project_hidden, record_category_hidden, record_project_kept,
    analyze_feedback_and_learn, get_user_preferences, should_hide_project,
    find_and_auto_hide_similar
)

# Get the directory where this file is located
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / '.env')

app = Flask(__name__, 
            template_folder=str(BASE_DIR / 'templates'),
            static_folder=str(BASE_DIR / 'static'),
            static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Configure sessions to last as long as possible (10 years)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=3650)


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint that reports status of database, Grok API, SMTP, and application.
    Returns 200 if all services are healthy, 503 if any critical service is down.
    """
    overall_status = "healthy"
    http_status = 200
    services = {}
    
    # Database health check
    db_status = "healthy"
    db_available = False
    db_response_time_ms = None
    db_error = None
    
    try:
        from .db import firestore_available, db
        if firestore_available and db is not None:
            start_time = time.time()
            # Perform a lightweight operation to test connection
            list(db.collection('users').limit(1).stream())
            db_response_time_ms = round((time.time() - start_time) * 1000, 2)
            db_available = True
        else:
            db_status = "unhealthy"
            db_error = "Firestore connection not available"
            overall_status = "unhealthy"
            http_status = 503
    except Exception as e:
        db_status = "unhealthy"
        db_available = False
        db_error = str(e)
        overall_status = "unhealthy"
        http_status = 503
    
    services['database'] = {
        'status': db_status,
        'available': db_available,
        'response_time_ms': db_response_time_ms,
        'error': db_error
    }
    
    # Grok API health check
    
    
    services['grok'] = check_grok_health()
    
    # SMTP health check
    smtp_status = "healthy"
    smtp_configured = False
    smtp_reachable = False
    smtp_response_time_ms = None
    smtp_error = None
    
    try:
        import smtplib
        from .services.email_service import get_smtp_config
    except ImportError:
        try:
            import smtplib
            from services.email_service import get_smtp_config
        except ImportError:
            smtp_error = "Email service not available"
            smtp_status = "degraded"
    
    if smtp_error is None:
        try:
            config = get_smtp_config()
            
            # Check if SMTP credentials are configured
            if config.get('user') and config.get('password') and config.get('from_email'):
                smtp_configured = True
                
                # Perform a lightweight connectivity test
                try:
                    start_time = time.time()
                    host = config.get('host', 'smtp.mailgun.org')
                    port = config.get('port', 587)
                    
                    # Try to connect to SMTP server (with timeout)
                    server = smtplib.SMTP(timeout=2)
                    server.connect(host, port)
                    server.quit()
                    
                    smtp_response_time_ms = round((time.time() - start_time) * 1000, 2)
                    smtp_reachable = True
                except smtplib.SMTPConnectError as e:
                    smtp_error = f"SMTP connection error: {str(e)}"
                    smtp_status = "degraded"
                    smtp_reachable = False
                except smtplib.SMTPException as e:
                    smtp_error = f"SMTP error: {str(e)}"
                    smtp_status = "degraded"
                    smtp_reachable = False
                except Exception as e:
                    if "timeout" in str(e).lower() or "connection" in str(e).lower():
                        smtp_error = f"SMTP connection timeout/error: {str(e)}"
                        smtp_status = "degraded"
                        smtp_reachable = False
                    else:
                        # Other errors might indicate server is reachable but has issues
                        smtp_reachable = True
                        smtp_error = f"SMTP check warning: {str(e)}"
            else:
                smtp_error = "SMTP credentials not fully configured (missing SMTP_USER, SMTP_PASSWORD, or SMTP_FROM_EMAIL)"
                smtp_status = "degraded"
        except Exception as e:
            smtp_error = str(e)
            smtp_status = "degraded"
            # SMTP is optional, so don't mark overall as unhealthy
    
    services['smtp'] = {
        'status': smtp_status,
        'configured': smtp_configured,
        'reachable': smtp_reachable,
        'response_time_ms': smtp_response_time_ms,
        'error': smtp_error
    }
    
    # If database is down, mark overall as unhealthy
    if db_status == "unhealthy":
        overall_status = "unhealthy"
        http_status = 503
    elif (services['grok']['status'] == "degraded" or smtp_status == "degraded") and db_status == "healthy":
        overall_status = "degraded"
        # Still return 200 for degraded (non-critical service)
    
    response = {
        'status': overall_status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'services': services
    }
    
    return jsonify(response), http_status


@app.route('/favicon.ico')
def favicon():
    """Serve the favicon"""
    return send_from_directory(
        str(BASE_DIR / 'static' / 'img'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )


@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors with a custom page"""
    return render_template('404.html'), 404


# Register blueprints
try:
    from .routes.auth_routes import bp as auth_bp
    from .routes.page_routes import bp as page_bp
    from .routes.api_routes import bp as api_bp
    from .routes.scheduled_jobs_routes import bp as scheduled_jobs_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(page_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(scheduled_jobs_bp)
except ImportError:
    from routes.auth_routes import bp as auth_bp
    from routes.page_routes import bp as page_bp
    from routes.api_routes import bp as api_bp
    from routes.scheduled_jobs_routes import bp as scheduled_jobs_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(page_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(scheduled_jobs_bp)



# Background threads disabled - Cloud Scheduler handles these tasks via HTTP endpoints:
# - /scheduled/notifications (runs every Friday at 9:00 AM)
# - /scheduled/cache-refresh (runs daily at 6:00 AM)
# - /scheduled/session-keepalive (runs every 8 hours)
# These are configured in web/routes/scheduled_jobs_routes.py and called by Google Cloud Scheduler
