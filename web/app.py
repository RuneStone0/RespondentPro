#!/usr/bin/env python3
"""
Flask web UI for Respondent.io API management with passkey authentication
"""

import os
import secrets
import time
import requests
import logging
import warnings
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Suppress SSL certificate warnings for local development
# This is especially useful when using self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import database collections
try:
    from .db import (
        users_collection, session_keys_collection, projects_cache_collection,
        user_preferences_collection, hidden_projects_log_collection,
        hide_feedback_collection, category_recommendations_collection,
        user_profiles_collection, mongo_available, client, db
    )
except ImportError:
    from db import (
        users_collection, session_keys_collection, projects_cache_collection,
        user_preferences_collection, hidden_projects_log_collection,
        hide_feedback_collection, category_recommendations_collection,
        user_profiles_collection, mongo_available, client, db
    )

# Import user service
try:
    from .services.user_service import (
        get_user_by_username, get_username_by_user_id, user_exists, create_user,
        load_credentials_by_user_id, save_credentials_by_user_id,
        load_user_config, save_user_config, update_last_synced,
        load_user_filters, save_user_filters
    )
except ImportError:
    from services.user_service import (
        get_user_by_username, get_username_by_user_id, user_exists, create_user,
        load_credentials_by_user_id, save_credentials_by_user_id,
        load_user_config, save_user_config, update_last_synced,
        load_user_filters, save_user_filters
    )

# Import respondent auth service
try:
    from .services.respondent_auth_service import (
        create_respondent_session, verify_respondent_authentication,
        fetch_and_store_user_profile, get_user_profile, fetch_user_profile,
        extract_demographic_params
    )
except ImportError:
    from services.respondent_auth_service import (
        create_respondent_session, verify_respondent_authentication,
        fetch_and_store_user_profile, get_user_profile, fetch_user_profile,
        extract_demographic_params
    )

# Import project service
try:
    from .services.project_service import (
        fetch_respondent_projects, fetch_all_respondent_projects,
        hide_project_via_api, get_hidden_count, process_and_hide_projects,
        get_hide_progress, hide_progress
    )
except ImportError:
    from services.project_service import (
        fetch_respondent_projects, fetch_all_respondent_projects,
        hide_project_via_api, get_hidden_count, process_and_hide_projects,
        get_hide_progress, hide_progress
    )

# Import filter service
try:
    from .services.filter_service import (
        apply_filters_to_projects, should_hide_project
    )
except ImportError:
    from services.filter_service import (
        apply_filters_to_projects, should_hide_project
    )

# Import new modules
try:
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
except ImportError:
    from cache_manager import is_cache_fresh, get_cached_projects, refresh_project_cache, get_cache_stats, mark_projects_hidden_in_cache
    from hidden_projects_tracker import (
        log_hidden_project, get_hidden_projects_count, get_hidden_projects_timeline,
        get_hidden_projects_stats, is_project_hidden
    )
    from ai_analyzer import (
        analyze_project, analyze_projects_batch, extract_metadata_with_grok,
        analyze_hide_feedback, find_similar_projects, generate_category_recommendations,
        get_projects_in_category, validate_category_pattern
    )
    from preference_learner import (
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

# Suppress SSL certificate warnings for local development
class SSLCertificateFilter(logging.Filter):
    """Filter to suppress SSL certificate unknown warnings in local development"""
    def filter(self, record):
        # Suppress warnings about SSL certificate unknown (common with self-signed certs)
        if 'SSLV3_ALERT_CERTIFICATE_UNKNOWN' in str(record.getMessage()):
            return False
        if 'ssl/tls alert certificate unknown' in str(record.getMessage()).lower():
            return False
        if 'certificate unknown' in str(record.getMessage()).lower():
            return False
        return True

# Apply filter to gunicorn's error logger
gunicorn_error_logger = logging.getLogger('gunicorn.error')
gunicorn_error_logger.addFilter(SSLCertificateFilter())

# Also apply to root logger to catch any other SSL warnings
root_logger = logging.getLogger()
root_logger.addFilter(SSLCertificateFilter())


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
        if mongo_available and client is not None and db is not None:
            start_time = time.time()
            # Perform a lightweight ping operation
            db.command('ping')
            db_response_time_ms = round((time.time() - start_time) * 1000, 2)
            db_available = True
        else:
            db_status = "unhealthy"
            db_error = "MongoDB connection not available"
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
    grok_status = "healthy"
    grok_api_key_configured = False
    grok_reachable = False
    grok_error = None
    
    try:
        grok_api_key = os.environ.get('GROK_API_KEY')
        grok_api_url = os.environ.get('GROK_API_URL', 'https://api.x.ai/v1/chat/completions')
        
        if grok_api_key:
            grok_api_key_configured = True
            
            # Perform a lightweight connectivity test with timeout
            # Test if we can reach the API domain (not making a full API call)
            try:
                from urllib.parse import urlparse
                parsed_url = urlparse(grok_api_url)
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                
                # Make a simple HEAD request to check connectivity
                test_response = requests.head(
                    base_url,
                    timeout=2,
                    allow_redirects=True
                )
                # If we get any response (even 404/403), the service is reachable
                grok_reachable = True
            except requests.exceptions.Timeout:
                grok_error = "Connection timeout"
                grok_status = "degraded"
                grok_reachable = False
            except requests.exceptions.ConnectionError:
                grok_error = "Connection error - API unreachable"
                grok_status = "degraded"
                grok_reachable = False
            except Exception as e:
                # For other errors, assume reachable if we got past connection
                # (e.g., 403/404 means service is up but endpoint/auth issue)
                if "timeout" in str(e).lower() or "connection" in str(e).lower():
                    grok_reachable = False
                    grok_error = str(e)
                    grok_status = "degraded"
                else:
                    grok_reachable = True
        else:
            grok_error = "GROK_API_KEY not configured"
            grok_status = "degraded"
            # Grok is optional, so don't mark overall as unhealthy
    except Exception as e:
        grok_error = str(e)
        grok_status = "degraded"
        # Grok is optional, so don't mark overall as unhealthy
    
    services['grok'] = {
        'status': grok_status,
        'api_key_configured': grok_api_key_configured,
        'reachable': grok_reachable,
        'error': grok_error
    }
    
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
    elif (grok_status == "degraded" or smtp_status == "degraded") and db_status == "healthy":
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


# Register blueprints
try:
    from .routes.auth_routes import bp as auth_bp
    from .routes.page_routes import bp as page_bp
    from .routes.api_routes import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(page_bp)
    app.register_blueprint(api_bp)
except ImportError:
    from routes.auth_routes import bp as auth_bp
    from routes.page_routes import bp as page_bp
    from routes.api_routes import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(page_bp)
    app.register_blueprint(api_bp)

# Initialize notification scheduler if MongoDB is available
if mongo_available and db is not None:
    try:
        from .notification_scheduler import start_notification_scheduler
        notification_thread = start_notification_scheduler(db, check_interval_hours=1, token_check_interval_hours=12)
        print("[Notifications] Notification scheduler started (weekly: 1h, token expiration: 12h)")
    except ImportError:
        try:
            from notification_scheduler import start_notification_scheduler
            notification_thread = start_notification_scheduler(db, check_interval_hours=1, token_check_interval_hours=12)
            print("[Notifications] Notification scheduler started (weekly: 1h, token expiration: 12h)")
        except Exception as e:
            print(f"[Notifications] Failed to start notification scheduler: {e}")
    except Exception as e:
        print(f"[Notifications] Failed to start notification scheduler: {e}")