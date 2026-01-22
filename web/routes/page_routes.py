#!/usr/bin/env python3
"""
Page routes for Respondent.io Manager
"""

import logging
import traceback
from flask import Blueprint, render_template, session, redirect, url_for, request, abort
from datetime import datetime

# Create logger for this module
logger = logging.getLogger(__name__)

# Import services
from ..services.user_service import load_user_config, load_user_filters, save_user_config, get_user_onboarding_status, is_user_verified, get_user_billing_info, is_admin, get_email_by_user_id, update_user_billing_limit
from ..services.respondent_service import create_respondent_session, verify_respondent_authentication
from ..services.project_service import fetch_all_respondent_projects, get_hidden_count
from ..cache_manager import get_cache_stats, get_cached_projects, is_cache_fresh
from ..db import projects_cache_collection, users_collection
from ..auth.firebase_auth import require_verified, require_account_limit, get_id_token_from_request, verify_firebase_token

bp = Blueprint('page', __name__)


@bp.route('/dashboard')
@require_verified
@require_account_limit
def dashboard():
    """Dashboard - redirect to projects page if credentials valid, otherwise onboarding"""
    import logging
    logger = logging.getLogger(__name__)
    
    user_id = request.auth['uid']
    email = request.auth.get('email', 'Unknown')
    logger.info(f"Dashboard accessed by user {user_id} ({email})")
    
    config = load_user_config(user_id)
    
    # Check if user has configured session keys
    has_config = config is not None and config.get('cookies', {}).get('respondent.session.sid')
    
    # Verify credentials are valid
    if has_config:
        try:
            verification = verify_respondent_authentication(
                cookies=config.get('cookies', {})
            )
            if verification.get('success', False):
                logger.info(f"User {user_id} has valid credentials, redirecting to /projects")
                return redirect(url_for('page.projects'))
            else:
                logger.info(f"User {user_id} has invalid credentials, redirecting to /account")
        except Exception as e:
            logger.warning(f"Error verifying credentials for user {user_id}: {e}")
    
    # No valid credentials, redirect to account
    logger.info(f"User {user_id} has no credentials configured, redirecting to /account")
    return redirect(url_for('page.account'))


@bp.route('/account')
@require_verified
def account():
    """Account page - manage respondent.io credentials and billing"""
    user_id = request.auth['uid']
    email = request.auth.get('email', 'User')
    config = load_user_config(user_id)
    
    # Check if credentials are valid
    has_valid_credentials = False
    if config and config.get('cookies', {}).get('respondent.session.sid'):
        try:
            verification = verify_respondent_authentication(
                cookies=config.get('cookies', {})
            )
            has_valid_credentials = verification.get('success', False)
        except Exception:
            has_valid_credentials = False
    
    # Pre-fill form if config exists
    session_sid = None
    if config and config.get('cookies', {}).get('respondent.session.sid'):
        session_sid = config['cookies']['respondent.session.sid']
    
    # Get billing info
    try:
        billing_info = get_user_billing_info(user_id)
    except Exception as e:
        logger.error(f"Error loading billing info: {e}", exc_info=True)
        billing_info = {
            'projects_processed_limit': 500,
            'projects_processed_count': 0,
            'projects_remaining': 500
        }
    
    return render_template(
        'account.html',
        email=email,
        billing_info=billing_info,
        has_valid_credentials=has_valid_credentials,
        session_sid=session_sid,
        config=config
    )


@bp.route('/notifications')
@require_verified
@require_account_limit
def notifications():
    """Notifications page - configure email notification preferences"""
    user_id = request.auth['uid']
    email = request.auth.get('email', 'User')
    
    return render_template('notifications.html', email=email)


@bp.route('/history')
@require_verified
@require_account_limit
def history():
    """History page - view hidden projects log"""
    user_id = request.auth['uid']
    email = request.auth.get('email', 'User')
    
    return render_template('history.html', email=email)


@bp.route('/about')
def about():
    """About page - information about Respondent Pro, handles Firebase Auth email link sign-in"""
    # Check for Firebase Auth token
    email = None
    login_error = None
    login_success = None
    
    # Check if user is authenticated via Firebase Auth
    id_token = get_id_token_from_request()
    if id_token:
        decoded_token = verify_firebase_token(id_token)
        if decoded_token:
            email = decoded_token.get('email')
    
    # Check for Firebase Auth email link parameters (oobCode, mode, etc.)
    # These are handled by the frontend JavaScript
    oob_code = request.args.get('oobCode')
    mode = request.args.get('mode')
    
    if oob_code and mode == 'signIn':
        # Firebase Auth email link detected - frontend will handle it
        login_success = "Processing login link. Please wait..."
    
    return render_template('about.html', email=email, login_error=login_error, login_success=login_success)


@bp.route('/support')
@require_verified
@require_account_limit
def support():
    """Support page - contact form for authenticated users"""
    user_id = request.auth['uid']
    email = request.auth.get('email', 'User')
    return render_template('support.html', email=email)


@bp.route('/admin')
@require_verified
@require_account_limit
def admin():
    """Admin page - manage user billing limits"""
    user_id = request.auth['uid']
    email = request.auth.get('email', 'User')
    
    # Check if user is admin
    if not is_admin(user_id):
        # Return 403 Forbidden for non-admin users
        abort(403)
    
    # Get all users with billing info
    users_data = []
    error_message = None
    try:
        if users_collection is None:
            error_message = "Firestore connection not available"
        else:
            all_users = users_collection.stream()
            user_count = 0
            for user_doc in all_users:
                user_count += 1
                try:
                    user_data = user_doc.to_dict()
                    user_id_str = user_doc.id
                    
                    # Get Firebase Auth UID - for new users, document ID is the firebase_uid
                    # For old users, firebase_uid is stored in the document
                    firebase_uid = user_data.get('firebase_uid') or user_id_str
                    
                    # Use the same method as account page - get_user_billing_info calls get_projects_processed_count internally
                    # Pass the Firebase Auth UID (not the document ID) to get correct projects processed count
                    billing_info = get_user_billing_info(firebase_uid)
                    users_data.append({
                        'user_id': user_id_str,
                        'email': user_data.get('username', 'Unknown'),
                        'billing_info': billing_info
                    })
                except Exception as e:
                    logger.error(f"Error getting billing info for user {user_id_str}: {e}", exc_info=True)
                    # Still add user with default billing info (same pattern as account page)
                    users_data.append({
                        'user_id': user_id_str,
                        'email': user_data.get('username', 'Unknown'),
                        'billing_info': {
                            'projects_processed_limit': 500,
                            'projects_processed_count': 0,
                            'projects_remaining': 500
                        }
                    })
            
            if user_count == 0:
                error_message = "No users found in database"
    except Exception as e:
        error_message = f"Error loading users: {str(e)}"
        logger.error(f"Error loading users for admin: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
    
    return render_template('admin.html', users=users_data, email=email, error_message=error_message)


@bp.route('/projects')
@require_verified
@require_account_limit
def projects():
    """Projects page - list all available projects"""
    user_id = request.auth['uid']
    email = request.auth.get('email', 'User')
    config = load_user_config(user_id)
    filters = load_user_filters(user_id)
    
    # Check if user has configured session keys
    has_config = config is not None and config.get('cookies', {}).get('respondent.session.sid')
    
    # Verify credentials are valid, redirect to onboarding if not
    if has_config:
        try:
            verification = verify_respondent_authentication(
                cookies=config.get('cookies', {})
            )
            if not verification.get('success', False):
                # Credentials are invalid, redirect to account
                return redirect(url_for('page.account'))
        except Exception as e:
            # Error verifying, redirect to account
            import traceback
            logger.error(f"Error verifying authentication in projects route: {e}", exc_info=True)
            return redirect(url_for('page.account'))
    else:
        # No credentials configured, redirect to account
        return redirect(url_for('page.account'))
    
    projects_data = None
    error = None
    hidden_count = 0
    cache_is_fresh = False
    cache_exists = False
    
    # Get hidden count (always available)
    hidden_count = get_hidden_count(user_id)
    
    # Only try to get cached projects if config exists
    if has_config and projects_cache_collection is not None:
        try:
            # Check if cache exists and is fresh
            cache_exists = get_cached_projects(projects_cache_collection, str(user_id)) is not None
            cache_is_fresh = is_cache_fresh(projects_cache_collection, str(user_id))
            
            # Get cached projects if available (even if stale)
            cached = get_cached_projects(projects_cache_collection, str(user_id))
            if cached and cached.get('projects'):
                # Sort projects by hourly rate (highest first)
                def calculate_hourly_rate(project):
                    remuneration = project.get('respondentRemuneration', 0) or 0
                    time_minutes = project.get('timeMinutesRequired', 0) or 0
                    if time_minutes > 0:
                        return (remuneration / time_minutes) * 60
                    return 0
                
                sorted_projects = sorted(
                    cached['projects'],
                    key=calculate_hourly_rate,
                    reverse=True
                )
                
                # Convert to the format expected by the template
                projects_data = {
                    'results': sorted_projects,
                    'count': cached.get('total_count', len(sorted_projects)),
                    'page': 1,
                    'pageSize': len(sorted_projects)
                }
            
            # Don't trigger automatic background refresh on page load
            # Users can manually refresh using the refresh button if needed
        except Exception as e:
            # If error occurs, just log it - don't block page load
            import traceback
            logger.error(f"Error getting cached projects for user {user_id}: {e}", exc_info=True)
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Get cache refresh time and total count
    cache_refreshed_utc = None
    total_projects_count = 0
    if projects_cache_collection is not None:
        try:
            cache_stats = get_cache_stats(projects_cache_collection, str(user_id))
            last_updated = cache_stats.get('last_updated')
            total_projects_count = cache_stats.get('total_count', 0)
            if last_updated:
                if isinstance(last_updated, datetime):
                    cache_refreshed_utc = last_updated.isoformat() + 'Z'
                elif isinstance(last_updated, str):
                    if not last_updated.endswith('Z') and '+' not in last_updated:
                        cache_refreshed_utc = last_updated + 'Z'
                    else:
                        cache_refreshed_utc = last_updated
                else:
                    try:
                        if hasattr(last_updated, 'isoformat'):
                            cache_refreshed_utc = last_updated.isoformat() + 'Z'
                        elif hasattr(last_updated, 'strftime'):
                            cache_refreshed_utc = datetime.fromtimestamp(last_updated.timestamp()).isoformat() + 'Z'
                        else:
                            cache_refreshed_utc = str(last_updated)
                    except:
                        cache_refreshed_utc = None
        except Exception as e:
            logger.error(f"Error getting cache refresh time: {e}", exc_info=True)
            cache_refreshed_utc = None
    
    return render_template(
        'projects.html',
        email=email,
        config=config,
        projects=projects_data,
        has_config=has_config,
        filters=filters,
        cache_refreshed_utc=cache_refreshed_utc,
        error=error,
        hidden_count=hidden_count,
        total_projects_count=total_projects_count,
        cache_is_fresh=cache_is_fresh,
        cache_exists=cache_exists
    )

