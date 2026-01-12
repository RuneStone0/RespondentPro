#!/usr/bin/env python3
"""
API routes for Respondent.io Manager
"""

import json
import base64
import logging
import threading
import time
import traceback
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from google.cloud.firestore_v1.base_query import FieldFilter

# Create logger for this module
logger = logging.getLogger(__name__)

# Import Firebase Auth decorators
try:
    from ..auth.firebase_auth import require_auth, get_user_id_from_token
except ImportError:
    from auth.firebase_auth import require_auth, get_user_id_from_token

# Import services
try:
    from ..services.user_service import load_user_config, save_user_config, load_user_filters, save_user_filters, update_user_onboarding_status, get_user_onboarding_status, get_projects_processed_count, get_user_billing_info, check_user_has_credits, is_admin, update_user_billing_limit, check_and_send_credit_notifications
    from ..services.respondent_service import create_respondent_session, verify_respondent_authentication, fetch_and_store_user_profile
    from ..services.project_service import (
        fetch_respondent_projects, fetch_all_respondent_projects, hide_project_via_api,
        get_hidden_count, process_and_hide_projects, get_hide_progress, hide_progress
    )
    from ..cache_manager import get_cached_projects, get_cache_stats, mark_projects_hidden_in_cache, get_cached_project_details, is_cache_fresh
    from ..hidden_projects_tracker import (
        get_hidden_projects_count, get_hidden_projects_timeline, get_hidden_projects_stats,
        get_all_hidden_projects, get_last_sync_time
    )
    from ..ai_analyzer import (
        generate_question_from_project, find_similar_projects, generate_hide_suggestions
    )
    from ..preference_learner import (
        record_project_hidden, store_question_answer, get_user_preferences, should_hide_based_on_ai_preferences,
        analyze_feedback_and_learn
    )
    from ..services.filter_service import should_hide_project, get_project_is_remote
    from ..db import (
        projects_cache_collection, hidden_projects_log_collection, user_preferences_collection, topics_collection,
        project_details_collection, ai_analysis_cache_collection
    )
    from ..services.topics_service import get_all_topics
    from ..services.email_service import send_support_email
except ImportError:
    from services.user_service import load_user_config, save_user_config, load_user_filters, save_user_filters, update_user_onboarding_status, get_user_onboarding_status, get_projects_processed_count, get_user_billing_info, check_user_has_credits, is_admin, update_user_billing_limit, check_and_send_credit_notifications
    from services.respondent_service import create_respondent_session, verify_respondent_authentication, fetch_and_store_user_profile
    from services.project_service import (
        fetch_respondent_projects, fetch_all_respondent_projects, hide_project_via_api,
        get_hidden_count, process_and_hide_projects, get_hide_progress, hide_progress
    )
    from cache_manager import get_cached_projects, get_cache_stats, mark_projects_hidden_in_cache, get_cached_project_details, is_cache_fresh
    from hidden_projects_tracker import (
        get_hidden_projects_count, get_hidden_projects_timeline, get_hidden_projects_stats,
        get_all_hidden_projects, get_last_sync_time
    )
    from ai_analyzer import (
        generate_question_from_project, find_similar_projects, generate_hide_suggestions
    )
    from preference_learner import (
        record_project_hidden, store_question_answer, get_user_preferences, should_hide_based_on_ai_preferences,
        analyze_feedback_and_learn
    )
    from services.filter_service import should_hide_project, get_project_is_remote
    from db import (
        projects_cache_collection, hidden_projects_log_collection, user_preferences_collection, topics_collection,
        project_details_collection, ai_analysis_cache_collection
    )
    from services.topics_service import get_all_topics
    from services.email_service import send_support_email

bp = Blueprint('api', __name__, url_prefix='/api')

# Store progress for preview-hide operations (in-memory)
preview_hide_progress = {}


def extract_session_sid_from_cookie_blob(cookie_string):
    """Extract respondent.session.sid from a cookie blob string"""
    if not cookie_string or not isinstance(cookie_string, str):
        return None
    
    cookie_string = cookie_string.strip()
    
    # Check if it looks like a cookie blob (contains semicolons and respondent.session.sid)
    if ';' not in cookie_string or 'respondent.session.sid' not in cookie_string:
        return None
    
    # Split by semicolons to get individual cookies
    cookies = cookie_string.split(';')
    
    # Find the respondent.session.sid cookie
    for cookie in cookies:
        cookie = cookie.strip()
        
        # Check if this cookie starts with respondent.session.sid=
        if cookie.startswith('respondent.session.sid='):
            # Extract the value after the equals sign
            value = cookie[len('respondent.session.sid='):].strip()
            return value
    
    return None


@bp.route('/session-keys', methods=['POST'])
@require_auth
def save_session_keys():
    """Save user's Respondent.io session keys to MongoDB and test them"""
    try:
        data = request.json
        session_sid = data.get('session_sid', '').strip()
        
        # If session_sid looks like a cookie blob, try to extract it
        if session_sid and ';' in session_sid and 'respondent.session.sid' in session_sid:
            extracted = extract_session_sid_from_cookie_blob(session_sid)
            if extracted:
                session_sid = extracted
        
        if not session_sid:
            return jsonify({'error': 'respondent.session.sid is required'}), 400
        
        user_id = request.auth['uid']
        config = {
            'cookies': {
                'respondent.session.sid': session_sid
            }
        }
        
        # Test the credentials first
        verification_result = verify_respondent_authentication(
            cookies=config['cookies']
        )
        
        # Save the config with profile_id if verification succeeded
        profile_id = None
        respondent_user_id = None
        if verification_result.get('success') and verification_result.get('profile_id'):
            profile_id = verification_result.get('profile_id')
            respondent_user_id = verification_result.get('user_id')
        
        save_user_config(user_id, config, profile_id=profile_id)
        
        # Fetch and store user profile if verification succeeded
        if verification_result.get('success') and respondent_user_id:
            def fetch_profile_background():
                try:
                    fetch_and_store_user_profile(user_id, respondent_user_id)
                except Exception as e:
                    logger.error(f"Error fetching profile in background: {e}", exc_info=True)
            
            thread = threading.Thread(target=fetch_profile_background)
            thread.daemon = True
            thread.start()
        
        response_data = {
            'success': True,
            'message': 'Session keys saved successfully',
            'verification': verification_result
        }
        
        return jsonify(response_data)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/session-keys', methods=['GET'])
@require_auth
def get_session_keys():
    """Get user's Respondent.io session keys"""
    user_id = request.auth['uid']
    config = load_user_config(user_id)
    
    if not config:
        return jsonify({'cookies': {}})
    
    return jsonify(config)


@bp.route('/session-keys/validate', methods=['POST'])
@require_auth
def validate_session_keys():
    """Validate session keys without saving them"""
    try:
        data = request.json
        session_sid = data.get('session_sid', '').strip()
        
        # If session_sid looks like a cookie blob, try to extract it
        if session_sid and ';' in session_sid and 'respondent.session.sid' in session_sid:
            extracted = extract_session_sid_from_cookie_blob(session_sid)
            if extracted:
                session_sid = extracted
        
        if not session_sid:
            return jsonify({'valid': False, 'message': 'Session ID is required'})
        
        # Test the credentials without saving
        config = {
            'cookies': {
                'respondent.session.sid': session_sid
            }
        }
        
        verification_result = verify_respondent_authentication(
            cookies=config['cookies']
        )
        
        return jsonify({
            'valid': verification_result.get('success', False),
            'message': verification_result.get('message', '')
        })
    except Exception as e:
        import traceback
        return jsonify({'valid': False, 'message': str(e)}), 500


@bp.route('/onboarding/has-account', methods=['POST'])
@require_auth
def save_has_account():
    """Save user's has_respondent_account status"""
    try:
        data = request.json
        has_account = data.get('has_account', False)
        
        # Convert to boolean if needed
        if isinstance(has_account, str):
            has_account = has_account.lower() in ('true', '1', 'yes', 'on')
        has_account = bool(has_account)
        
        user_id = request.auth['uid']
        update_user_onboarding_status(user_id, has_account)
        
        return jsonify({
            'success': True,
            'message': 'Account status updated successfully',
            'has_account': has_account
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/filters', methods=['GET'])
@require_auth
def get_filters():
    """Get user's project filter preferences"""
    user_id = request.auth['uid']
    filters = load_user_filters(user_id)
    
    return jsonify(filters)


@bp.route('/topics', methods=['GET'])
@require_auth
def get_topics():
    """Get all available topics"""
    try:
        topics = get_all_topics(topics_collection)
        return jsonify({'topics': topics})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/filters', methods=['POST'])
@require_auth
def save_filters():
    """Save user's project filter preferences"""
    try:
        user_id = request.auth['uid']
        data = request.json
        
        # Default to empty dict if no data provided (save_user_filters handles this)
        if data is None:
            data = {}
        
        save_user_filters(user_id, data)
        
        # Load the saved filters to ensure we use the correct values
        saved_filters = load_user_filters(user_id)
        
        # Check if there are any active filters that would hide projects
        has_active_filters = (
            saved_filters.get('min_incentive') is not None or
            saved_filters.get('min_hourly_rate') is not None or
            saved_filters.get('isRemote') is True or
            (saved_filters.get('topics') and len(saved_filters.get('topics', [])) > 0)
        )
        
        # If there are active filters, start the hide process
        if has_active_filters:
            config = load_user_config(user_id)
            if config and config.get('cookies', {}).get('respondent.session.sid'):
                profile_id = config.get('profile_id')
                if profile_id:
                    req_session = create_respondent_session(
                        cookies=config.get('cookies', {})
                    )
                    
                    def hide_in_background():
                        try:
                            process_and_hide_projects(
                                user_id, req_session, profile_id, saved_filters,
                                cookies=config.get('cookies', {})
                            )
                        except Exception as e:
                            import traceback
                            logger.error(f"Error in background hide process", exc_info=True)
                            user_id_str = str(user_id)
                            if user_id_str in hide_progress:
                                hide_progress[user_id_str]['status'] = 'error'
                                hide_progress[user_id_str]['error'] = str(e)
                    
                    thread = threading.Thread(target=hide_in_background)
                    thread.daemon = True
                    thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Filters saved successfully',
            'filters': load_user_filters(user_id),
            'last_synced': datetime.utcnow().isoformat()
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/hide-projects', methods=['POST'])
@require_auth
def hide_projects():
    """Start the process of hiding projects based on filters"""
    try:
        user_id = request.auth['uid']
        
        # Check user credits before starting
        try:
            billing_info = get_user_billing_info(user_id)
            limit = billing_info.get('projects_processed_limit', 500)
            processed = billing_info.get('projects_processed_count', 0)
            
            # If limit is None or very large (effectively unlimited), skip check
            if limit is not None and limit < 999999999:
                if processed >= limit:
                    return jsonify({
                        'error': f'You have reached your project processing limit ({limit} projects). Please contact support to upgrade.',
                        'redirect': '/account'
                    }), 403
        except Exception as e:
            logger.warning(f"Warning: Could not check billing info: {e}")
            # Continue anyway - don't block on billing info errors
        
        config = load_user_config(user_id)
        filters = load_user_filters(user_id)
        
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            return jsonify({'error': 'Session keys not configured'}), 400
        
        profile_id = config.get('profile_id')
        if not profile_id:
            return jsonify({'error': 'Profile ID not found'}), 400
        
        req_session = create_respondent_session(
            cookies=config.get('cookies', {})
        )
        
        def hide_in_background():
            try:
                process_and_hide_projects(
                    user_id, req_session, profile_id, filters,
                    cookies=config.get('cookies', {})
                )
            except Exception as e:
                import traceback
                logger.error(f"Error in background hide process", exc_info=True)
                user_id_str = str(user_id)
                if user_id_str in hide_progress:
                    hide_progress[user_id_str]['status'] = 'error'
                    hide_progress[user_id_str]['error'] = str(e)
        
        thread = threading.Thread(target=hide_in_background)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Hide process started'
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/preview-hide', methods=['POST'])
@require_auth
def preview_hide():
    """Preview projects that would be hidden based on current filter settings"""
    try:
        user_id = request.auth['uid']
        user_id_str = str(user_id)
        data = request.json
        
        # Initialize progress tracking
        preview_hide_progress[user_id_str] = {
            'status': 'processing',
            'current': 0,
            'total': 0,
            'matched': 0
        }
        
        # Get isRemote filter setting
        is_remote = data.get('isRemote')
        # Handle None, True, or string "true" values
        if is_remote is None or is_remote == '':
            is_remote = None
        elif isinstance(is_remote, str):
            is_remote = is_remote.lower() in ('true', '1', 'yes', 'on')
            if not is_remote:
                is_remote = None
        elif is_remote is False:
            # Never use False, convert to None
            is_remote = None
        else:
            # Ensure it's True if it's truthy
            is_remote = True
        
        filters = {
            'min_incentive': data.get('min_incentive'),
            'min_hourly_rate': data.get('min_hourly_rate'),
            'isRemote': is_remote,
            'auto_hide': data.get('auto_hide', False),
            'topics': data.get('topics', []),
            'hide_using_ai': data.get('hide_using_ai', False)
        }
        
        # Check if any filters are set
        if filters['min_incentive'] is None and filters['min_hourly_rate'] is None and filters['isRemote'] is None and not filters['topics'] and not filters['hide_using_ai']:
            preview_hide_progress[user_id_str]['status'] = 'completed'
            return jsonify({
                'success': True,
                'projects': [],
                'count': 0,
                'message': 'No filters set - no projects would be hidden'
            })
        
        # Get cached projects or fetch them
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            preview_hide_progress[user_id_str]['status'] = 'error'
            return jsonify({'error': 'Session keys not configured'}), 400
        
        profile_id = config.get('profile_id')
        if not profile_id:
            preview_hide_progress[user_id_str]['status'] = 'error'
            return jsonify({'error': 'Profile ID not found'}), 400
        
        # Try to get from cache first, otherwise fetch projects
        req_session = create_respondent_session(
            cookies=config.get('cookies', {})
        )
        all_projects, _ = fetch_all_respondent_projects(
            session=req_session,
            profile_id=profile_id,
            page_size=50,
            user_id=user_id,
            use_cache=True,
            cookies=config.get('cookies', {})
        )
        
        # Update total count
        preview_hide_progress[user_id_str]['total'] = len(all_projects)
        
        # Find projects that would be hidden
        # Pass user_id and user_preferences_collection for AI filtering when hide_using_ai is enabled
        hide_using_ai = filters.get('hide_using_ai', False)
        
        projects_to_hide = []
        for idx, project in enumerate(all_projects):
            # Update progress
            preview_hide_progress[user_id_str]['current'] = idx + 1
            
            # Check if project should be hidden
            if should_hide_project(
                project, 
                filters, 
                project_details_collection=project_details_collection,
                user_id=user_id_str if hide_using_ai else None,
                user_preferences_collection=user_preferences_collection if hide_using_ai else None,
                ai_analysis_cache_collection=ai_analysis_cache_collection if hide_using_ai else None
            ):
                preview_hide_progress[user_id_str]['matched'] += 1
                
                # Calculate hourly rate for display
                remuneration = project.get('respondentRemuneration', 0)
                time_minutes = project.get('timeMinutesRequired', 0)
                hourly_rate = 0
                if time_minutes > 0:
                    hourly_rate = (remuneration / time_minutes) * 60
                
                # Get remote status for display
                project_id = project.get('id')
                project_is_remote = None
                if project_id and project_details_collection is not None:
                    project_is_remote = get_project_is_remote(project_id)
                
                remote_status = 'Unknown'
                if project_is_remote is not None:
                    remote_status = 'Remote' if project_is_remote else 'Not Remote'
                
                projects_to_hide.append({
                    'id': project.get('id'),
                    'name': project.get('name', 'Untitled Project'),
                    'incentive': remuneration,
                    'hourly_rate': round(hourly_rate, 2),
                    'time_minutes': time_minutes,
                    'remote_status': remote_status
                })
        
        # Mark as completed and prepare response
        result = {
            'success': True,
            'projects': projects_to_hide,
            'count': len(projects_to_hide)
        }
        
        # Clear progress after a short delay to allow frontend to get final status
        def clear_progress():
            time.sleep(2)  # Wait 2 seconds before clearing
            if user_id_str in preview_hide_progress:
                del preview_hide_progress[user_id_str]
        
        # Clear progress in background thread
        threading.Thread(target=clear_progress, daemon=True).start()
        
        preview_hide_progress[user_id_str]['status'] = 'completed'
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        user_id_str = str(request.auth.get('uid', 'unknown') if hasattr(request, 'auth') and request.auth else 'unknown')
        if user_id_str in preview_hide_progress:
            preview_hide_progress[user_id_str]['status'] = 'error'
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/preview-hide-progress', methods=['GET'])
@require_auth
def get_preview_hide_progress():
    """Get the current preview-hide progress for a user"""
    try:
        user_id_str = str(request.auth['uid'])
        progress = preview_hide_progress.get(user_id_str, {
            'status': 'not_started',
            'current': 0,
            'total': 0,
            'matched': 0
        })
        return jsonify(progress)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/hide-progress', methods=['GET'])
@require_auth
def get_hide_progress_route():
    """Get the current progress of hiding projects"""
    try:
        user_id = str(request.auth['uid'])
        progress = get_hide_progress(user_id)
        return jsonify(progress)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/hide-project', methods=['POST'])
@require_auth
def hide_project():
    """Hide a single project with optional feedback and generate AI question"""
    try:
        user_id = str(request.auth['uid'])
        
        # Check user credits before hiding
        try:
            billing_info = get_user_billing_info(user_id)
            limit = billing_info.get('projects_processed_limit', 500)
            processed = billing_info.get('projects_processed_count', 0)
            
            # If limit is None or very large (effectively unlimited), skip check
            if limit is not None and limit < 999999999:
                if processed >= limit:
                    return jsonify({
                        'error': f'You have reached your project processing limit ({limit} projects). Please contact support to upgrade.',
                        'redirect': '/account'
                    }), 403
        except Exception as e:
            logger.warning(f"Warning: Could not check billing info: {e}")
            # Continue anyway - don't block on billing info errors
        
        data = request.json
        project_id = data.get('project_id')
        feedback_text = data.get('feedback_text')
        hidden_method_param = data.get('hidden_method')
        
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400
        
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            return jsonify({'error': 'Session keys not configured'}), 400
        
        req_session = create_respondent_session(
            cookies=config.get('cookies', {})
        )
        
        success = hide_project_via_api(req_session, project_id)
        if not success:
            return jsonify({'error': 'Failed to hide project'}), 500
        
        if projects_cache_collection is not None:
            mark_projects_hidden_in_cache(projects_cache_collection, user_id, [project_id])
        
        # Determine hidden method: use provided method, or 'feedback_based' if feedback provided, else 'manual'
        if hidden_method_param:
            hidden_method = hidden_method_param
        elif feedback_text:
            hidden_method = 'feedback_based'
        else:
            hidden_method = 'manual'
        
        # Get project data for AI analysis
        project_data = None
        if projects_cache_collection is not None:
            cached = get_cached_projects(projects_cache_collection, user_id)
            if cached and cached.get('projects'):
                for proj in cached.get('projects', []):
                    if proj.get('id') == project_id:
                        project_data = proj
                        break
        
        # If not in cache, try to fetch it (simplified - just use basic data)
        if not project_data:
            project_data = {'id': project_id, 'name': '', 'description': ''}
        
        if user_preferences_collection is not None and hidden_projects_log_collection is not None:
            record_project_hidden(
                hidden_projects_log_collection,
                user_preferences_collection,
                user_id,
                project_id,
                feedback_text=feedback_text,
                hidden_method=hidden_method
            )
            
            # Analyze feedback and learn patterns if feedback was provided
            if feedback_text and project_data:
                analyze_feedback_and_learn(
                    user_preferences_collection,
                    user_id,
                    project_id,
                    feedback_text,
                    project_data,
                    ai_analysis_cache_collection
                )
        
        # Generate AI question if no feedback provided (feedback means user already explained)
        # Skip question generation for 'applied' method
        question = None
        if not feedback_text and project_data and hidden_method != 'applied':
            # Check if we've already asked this type of question before
            prefs = get_user_preferences(user_preferences_collection, user_id) if user_preferences_collection is not None else {}
            existing_question_ids = {qa.get('question_id') for qa in prefs.get('question_answers', [])}
            
            question_data = generate_question_from_project(project_data)
            if question_data and question_data.get('id') not in existing_question_ids:
                question = question_data
        
        # Check and send credit notifications after hiding project
        try:
            check_and_send_credit_notifications(user_id)
        except Exception as e:
            logger.error(f"Error checking credit notifications: {e}", exc_info=True)
            # Don't fail the operation if notification check fails
        
        return jsonify({
            'success': True,
            'auto_hidden_count': 0,
            'auto_hidden_ids': [],
            'question': question
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/hide-suggestions', methods=['POST'])
@require_auth
def get_hide_suggestions():
    """Get AI-generated suggestions for why a user might hide a project"""
    try:
        user_id = str(request.auth['uid'])
        data = request.json
        project_id = data.get('project_id')
        
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400
        
        # Get project data from cache
        project_data = None
        if projects_cache_collection is not None:
            cached = get_cached_projects(projects_cache_collection, user_id)
            if cached and cached.get('projects'):
                for proj in cached.get('projects', []):
                    if proj.get('id') == project_id:
                        project_data = proj
                        break
        
        if not project_data:
            return jsonify({'error': 'Project not found'}), 404
        
        # Generate suggestions
        suggestions = generate_hide_suggestions(project_data)
        
        return jsonify({
            'success': True,
            'suggestions': suggestions,
            'project': {
                'id': project_data.get('id'),
                'name': project_data.get('name', 'Untitled Project'),
                'description': project_data.get('description', ''),
                'remuneration': project_data.get('respondentRemuneration', 0),
                'time_minutes': project_data.get('timeMinutesRequired', 0),
                'topics': project_data.get('topics', [])
            }
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/answer-question', methods=['POST'])
@require_auth
def answer_question():
    """Answer an AI-generated question and auto-hide similar projects if applicable"""
    try:
        user_id = str(request.auth['uid'])
        data = request.json
        question_id = data.get('question_id')
        question_text = data.get('question_text')
        answer = data.get('answer')  # True/False
        pattern = data.get('pattern')
        project_id = data.get('project_id')
        
        if question_id is None or question_text is None or answer is None or pattern is None:
            return jsonify({'error': 'question_id, question_text, answer, and pattern are required'}), 400
        
        # Convert answer to boolean if needed
        if isinstance(answer, str):
            answer = answer.lower() in ('true', 'yes', '1', 'on')
        answer = bool(answer)
        
        # Store the answer
        if user_preferences_collection is not None:
            store_question_answer(
                user_preferences_collection,
                user_id,
                question_id,
                question_text,
                answer,
                pattern,
                project_id
            )
        
        # If answer is False (user doesn't match requirement), find and auto-hide similar projects
        auto_hidden_count = 0
        auto_hidden_ids = []
        
        if not answer:  # User said "no" - they don't match the requirement
            config = load_user_config(user_id)
            if config and config.get('cookies', {}).get('respondent.session.sid'):
                profile_id = config.get('profile_id')
                if profile_id:
                    # Get all projects
                    cached = None
                    if projects_cache_collection is not None:
                        cached = get_cached_projects(projects_cache_collection, user_id)
                    
                    if cached and cached.get('projects'):
                        all_projects = cached.get('projects', [])
                        
                        # Find similar projects using the pattern
                        similar_projects = find_similar_projects(
                            user_id,
                            project_id or '',
                            all_projects,
                            pattern
                        )
                        
                        # Filter out already hidden projects
                        prefs = get_user_preferences(user_preferences_collection, user_id) if user_preferences_collection is not None else {}
                        hidden_projects = set(prefs.get('hidden_projects', []))
                        
                        projects_to_hide = [p for p in similar_projects if p.get('id') not in hidden_projects]
                        
                        if projects_to_hide:
                            req_session = create_respondent_session(
                                cookies=config.get('cookies', {})
                            )
                            
                            for project in projects_to_hide[:20]:  # Limit to 20 to avoid rate limiting
                                proj_id = project.get('id')
                                if proj_id:
                                    success = hide_project_via_api(req_session, proj_id)
                                    if success:
                                        auto_hidden_ids.append(proj_id)
                                        auto_hidden_count += 1
                                        time.sleep(0.1)
                            
                            # Update cache and log
                            if projects_cache_collection is not None and auto_hidden_ids:
                                mark_projects_hidden_in_cache(projects_cache_collection, user_id, auto_hidden_ids)
                            
                            if hidden_projects_log_collection is not None and user_preferences_collection is not None:
                                for proj_id in auto_hidden_ids:
                                    record_project_hidden(
                                        hidden_projects_log_collection,
                                        user_preferences_collection,
                                        user_id,
                                        proj_id,
                                        hidden_method='ai_auto'
                                    )
        
        return jsonify({
            'success': True,
            'auto_hidden_count': auto_hidden_count,
            'auto_hidden_ids': auto_hidden_ids
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/hide-feedback', methods=['GET'])
@require_auth
def get_hide_feedback():
    """Get all hide_feedback entries for the current user"""
    try:
        user_id = str(request.auth['uid'])
        
        if user_preferences_collection is None:
            return jsonify({'success': True, 'feedback': []})
        
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if not docs:
            return jsonify({'success': True, 'feedback': []})
        
        prefs = docs[0].to_dict()
        feedback_list = prefs.get('hide_feedback', [])
        
        # Add IDs to old entries that don't have them and prepare response data
        import copy
        
        response_feedback = []
        for feedback in feedback_list:
            feedback_copy = copy.deepcopy(feedback)
            
            # Convert datetime objects to ISO format strings for JSON serialization
            if 'hidden_at' in feedback_copy and isinstance(feedback_copy['hidden_at'], datetime):
                feedback_copy['hidden_at'] = feedback_copy['hidden_at'].isoformat() + 'Z'
            
            response_feedback.append(feedback_copy)
        
        return jsonify({
            'success': True,
            'feedback': response_feedback
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/hide-feedback/<feedback_id>', methods=['PUT', 'PATCH'])
@require_auth
def update_hide_feedback(feedback_id):
    """Update a specific hide_feedback entry's text"""
    try:
        user_id = str(request.auth['uid'])
        data = request.json
        
        if not data or 'feedback_text' not in data:
            return jsonify({'error': 'feedback_text is required'}), 400
        
        new_feedback_text = data.get('feedback_text', '').strip()
        
        if user_preferences_collection is None:
            return jsonify({'error': 'Database not available'}), 500
        
        # Find the feedback entry and update it
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if not docs:
            return jsonify({'error': 'User preferences not found'}), 404
        
        prefs = docs[0].to_dict()
        feedback_list = prefs.get('hide_feedback', [])
        feedback_found = False
        
        for feedback in feedback_list:
            if feedback.get('id') == feedback_id:
                feedback['feedback_text'] = new_feedback_text
                feedback_found = True
                break
        
        if not feedback_found:
            return jsonify({'error': 'Feedback entry not found'}), 404
        
        # Update the document
        docs[0].reference.update({
            'hide_feedback': feedback_list,
            'updated_at': datetime.utcnow()
        })
        
        # Invalidate AI analysis cache for this user since feedback changed
        if ai_analysis_cache_collection is not None:
            cache_query = ai_analysis_cache_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).stream()
            for doc in cache_query:
                doc.reference.delete()
        
        return jsonify({
            'success': True,
            'message': 'Feedback updated successfully'
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/hide-feedback/<feedback_id>', methods=['DELETE'])
@require_auth
def delete_hide_feedback(feedback_id):
    """Delete a specific hide_feedback entry"""
    try:
        user_id = str(request.auth['uid'])
        
        if user_preferences_collection is None:
            return jsonify({'error': 'Database not available'}), 500
        
        # Find the feedback entry and remove it
        query = user_preferences_collection.where(filter=FieldFilter('user_id', '==', str(user_id))).limit(1).stream()
        docs = list(query)
        if not docs:
            return jsonify({'error': 'User preferences not found'}), 404
        
        prefs = docs[0].to_dict()
        feedback_list = prefs.get('hide_feedback', [])
        original_length = len(feedback_list)
        
        # Remove the feedback entry by id
        feedback_list = [f for f in feedback_list if f.get('id') != feedback_id]
        
        if len(feedback_list) == original_length:
            return jsonify({'error': 'Feedback entry not found'}), 404
        
        # Update the document
        docs[0].reference.update({
            'hide_feedback': feedback_list,
            'updated_at': datetime.utcnow()
        })
        
        # Invalidate AI analysis cache for this user since feedback changed
        if ai_analysis_cache_collection is not None:
            ai_analysis_cache_collection.delete_many({'user_id': user_id})
        
        return jsonify({
            'success': True,
            'message': 'Feedback deleted successfully'
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/analytics/hidden-count', methods=['GET'])
@require_auth
def get_hidden_count_api():
    """Get total count of hidden projects"""
    try:
        user_id = str(request.auth['uid'])
        count = get_hidden_count(user_id)
        return jsonify({'total_count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/analytics/hidden-timeline', methods=['GET'])
@require_auth
def get_hidden_timeline():
    """Get hidden projects grouped by date for graphing"""
    try:
        user_id = str(request.auth['uid'])
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        group_by = request.args.get('group_by', 'day')
        
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        if hidden_projects_log_collection is not None:
            timeline = get_hidden_projects_timeline(
                hidden_projects_log_collection,
                user_id,
                start_date,
                end_date,
                group_by
            )
            total = get_hidden_projects_count(hidden_projects_log_collection, user_id)
            return jsonify({'timeline': timeline, 'total': total})
        else:
            return jsonify({'timeline': [], 'total': 0})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/analytics/hidden-stats', methods=['GET'])
@require_auth
def get_hidden_stats():
    """Get detailed statistics about hidden projects"""
    try:
        user_id = str(request.auth['uid'])
        if hidden_projects_log_collection is not None:
            stats = get_hidden_projects_stats(hidden_projects_log_collection, user_id)
            return jsonify(stats)
        else:
            return jsonify({
                'total': 0,
                'by_method': {},
                'recent': []
            })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/projects', methods=['GET'])
@require_auth
def get_projects():
    """Get cached projects as JSON for AJAX loading"""
    try:
        user_id = str(request.auth['uid'])
        
        # Get cached projects if available
        projects_data = None
        cache_is_fresh = False
        cache_exists = False
        
        if projects_cache_collection is not None:
            cache_exists = get_cached_projects(projects_cache_collection, user_id) is not None
            cache_is_fresh = is_cache_fresh(projects_cache_collection, user_id)
            
            cached = get_cached_projects(projects_cache_collection, user_id)
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
                
                projects_data = {
                    'results': sorted_projects,
                    'count': cached.get('total_count', len(sorted_projects)),
                    'page': 1,
                    'pageSize': len(sorted_projects)
                }
        
        # Get cache stats for timestamp
        cache_refreshed_utc = None
        if projects_cache_collection is not None:
            stats = get_cache_stats(projects_cache_collection, user_id)
            last_updated = stats.get('last_updated')
            if last_updated:
                if isinstance(last_updated, datetime):
                    cache_refreshed_utc = last_updated.isoformat() + 'Z'
                elif isinstance(last_updated, str):
                    if not last_updated.endswith('Z') and '+' not in last_updated:
                        cache_refreshed_utc = last_updated + 'Z'
                    else:
                        cache_refreshed_utc = last_updated
                else:
                    if hasattr(last_updated, 'isoformat'):
                        cache_refreshed_utc = last_updated.isoformat() + 'Z'
                    elif hasattr(last_updated, 'strftime'):
                        cache_refreshed_utc = datetime.fromtimestamp(last_updated.timestamp()).isoformat() + 'Z'
                    else:
                        cache_refreshed_utc = str(last_updated)
        
        return jsonify({
            'projects': projects_data,
            'cache_exists': cache_exists,
            'cache_is_fresh': cache_is_fresh,
            'cache_refreshed_utc': cache_refreshed_utc,
            'total_count': projects_data.get('count', 0) if projects_data else 0
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/cache/stats', methods=['GET'])
@require_auth
def get_cache_stats_api():
    """Get cache statistics including refresh time"""
    try:
        user_id = str(request.auth['uid'])
        
        # Get last sync time from hidden_projects_log
        last_sync = None
        if hidden_projects_log_collection is not None:
            last_sync = get_last_sync_time(hidden_projects_log_collection, user_id)
        
        # Convert to ISO format for client-side timezone conversion
        last_sync_iso = None
        if last_sync:
            if isinstance(last_sync, datetime):
                last_sync_iso = last_sync.isoformat() + 'Z'
            elif isinstance(last_sync, str):
                if not last_sync.endswith('Z') and '+' not in last_sync:
                    last_sync_iso = last_sync + 'Z'
                else:
                    last_sync_iso = last_sync
            else:
                if hasattr(last_sync, 'isoformat'):
                    last_sync_iso = last_sync.isoformat() + 'Z'
                elif hasattr(last_sync, 'strftime'):
                    last_sync_iso = datetime.fromtimestamp(last_sync.timestamp()).isoformat() + 'Z'
                else:
                    last_sync_iso = str(last_sync)
        
        # Also get cache stats for total_count
        total_count = 0
        if projects_cache_collection is not None:
            stats = get_cache_stats(projects_cache_collection, user_id)
            total_count = stats.get('total_count', 0)
        
        return jsonify({
            'exists': True,
            'last_updated': last_sync_iso,
            'total_count': total_count
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/cache/refresh', methods=['POST'])
@require_auth
def refresh_cache():
    """Manually refresh the project cache (runs in background)"""
    try:
        user_id = str(request.auth['uid'])
        
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            return jsonify({'error': 'Session keys not configured'}), 400
        
        profile_id = config.get('profile_id')
        if not profile_id:
            return jsonify({'error': 'Profile ID not found'}), 400
        
        # Define background refresh function
        def refresh_cache_background():
            try:
                logger.info(f"[Cache Refresh] Starting background refresh for user {user_id}")
                req_session = create_respondent_session(
                    cookies=config.get('cookies', {})
                )
                
                all_projects, total_count = fetch_all_respondent_projects(
                    session=req_session,
                    profile_id=profile_id,
                    page_size=50,
                    user_id=user_id,
                    use_cache=False,
                    cookies=config.get('cookies', {})
                )
                
                # Check if AI-based hiding is enabled and hide matching projects
                filters = load_user_filters(user_id)
                hide_using_ai = filters.get('hide_using_ai', False)
                hidden_count = 0
                hidden_project_ids = []
                errors = []
                
                if hide_using_ai:
                    logger.info(f"[Cache Refresh] AI-based hiding is enabled, checking {len(all_projects)} projects")
                    
                    # Find projects that should be hidden based on AI preferences
                    projects_to_hide = []
                    for project in all_projects:
                        if should_hide_project(
                            project,
                            filters,
                            project_details_collection=project_details_collection,
                            user_id=user_id,
                            user_preferences_collection=user_preferences_collection,
                            ai_analysis_cache_collection=ai_analysis_cache_collection
                        ):
                            projects_to_hide.append(project)
                    
                    logger.info(f"[Cache Refresh] Found {len(projects_to_hide)} projects to hide based on AI preferences")
                    
                    # Hide each project via API
                    for project in projects_to_hide:
                        project_id = project.get('id')
                        if project_id:
                            try:
                                success = hide_project_via_api(req_session, project_id)
                                if success:
                                    hidden_count += 1
                                    hidden_project_ids.append(project_id)
                                    
                                    # Log the hidden project
                                    if hidden_projects_log_collection is not None and user_preferences_collection is not None:
                                        record_project_hidden(
                                            hidden_projects_log_collection,
                                            user_preferences_collection,
                                            user_id,
                                            project_id,
                                            feedback_text=None,
                                            hidden_method='ai_auto'
                                        )
                                else:
                                    errors.append(project_id)
                                    logger.warning(f"[Cache Refresh] Failed to hide project {project_id}")
                            except Exception as e:
                                errors.append(project_id)
                                logger.error(f"[Cache Refresh] Error hiding project {project_id}: {e}", exc_info=True)
                            
                            # Small delay to avoid rate limiting
                            time.sleep(0.1)
                    
                    # Update cache to mark projects as hidden
                    if projects_cache_collection is not None and hidden_project_ids:
                        mark_projects_hidden_in_cache(projects_cache_collection, user_id, hidden_project_ids)
                        logger.info(f"[Cache Refresh] Marked {len(hidden_project_ids)} projects as hidden in cache")
                    
                    # Refresh cache from API to get updated project list after hiding
                    if projects_cache_collection is not None and hidden_project_ids:
                        try:
                            logger.info(f"[Cache Refresh] Refreshing cache after hiding {len(hidden_project_ids)} projects")
                            all_projects, total_count = fetch_all_respondent_projects(
                                session=req_session,
                                profile_id=profile_id,
                                page_size=50,
                                user_id=user_id,
                                use_cache=False,
                                cookies=config.get('cookies', {})
                            )
                            logger.info(f"[Cache Refresh] Cache refreshed: {len(all_projects)} projects now in cache")
                        except Exception as e:
                            logger.error(f"[Cache Refresh] Error refreshing cache after hiding: {e}", exc_info=True)
                            # Don't fail the whole operation if cache refresh fails
                
                logger.info(f"[Cache Refresh] Background refresh completed for user {user_id}")
            except Exception as e:
                import traceback
                logger.error(f"[Cache Refresh] Error in background refresh: {e}", exc_info=True)
        
        # Start background thread
        thread = threading.Thread(target=refresh_cache_background)
        thread.daemon = True
        thread.start()
        
        # Return immediately
        return jsonify({
            'success': True,
            'message': 'Cache refresh started in background',
            'status': 'refreshing'
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/notifications/preferences', methods=['GET'])
@require_auth
def get_notification_preferences():
    """Get user's notification preferences"""
    try:
        user_id = request.auth['uid']
        
        # Import notification service
        try:
            from ..services.notification_service import load_notification_preferences
        except ImportError:
            from services.notification_service import load_notification_preferences
        
        preferences = load_notification_preferences(user_id)
        
        # Convert datetime objects to ISO format strings for JSON serialization
        result = {}
        for key, value in preferences.items():
            if isinstance(value, dict):
                result[key] = {}
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, datetime):
                        result[key][sub_key] = sub_value.isoformat() + 'Z'
                    else:
                        result[key][sub_key] = sub_value
            else:
                result[key] = value
        
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/notifications/preferences', methods=['POST'])
@require_auth
def save_notification_preferences():
    """Save user's notification preferences"""
    try:
        user_id = request.auth['uid']
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Import notification service
        try:
            from ..services.notification_service import save_notification_preferences
        except ImportError:
            from services.notification_service import save_notification_preferences
        
        # Validate and prepare preferences
        preferences = {
            'weekly_project_summary': {
                'enabled': bool(data.get('weekly_project_summary', {}).get('enabled', True)),
                'day_of_week': int(data.get('weekly_project_summary', {}).get('day_of_week', 0))
            },
            'session_token_expired': {
                'enabled': bool(data.get('session_token_expired', {}).get('enabled', True))
            }
        }
        
        # Validate day_of_week (0-6)
        if not (0 <= preferences['weekly_project_summary']['day_of_week'] <= 6):
            return jsonify({'error': 'Invalid day_of_week. Must be between 0 and 6.'}), 400
        
        save_notification_preferences(user_id, preferences)
        
        return jsonify({'success': True, 'message': 'Notification preferences saved successfully'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/history', methods=['GET'])
@require_auth
def get_history():
    """Get hidden projects history with pagination and counts"""
    try:
        user_id = str(request.auth['uid'])
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        # Validate pagination
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 50
        
        if hidden_projects_log_collection is None:
            return jsonify({
                'manual_count': 0,
                'automated_count': 0,
                'total_count': 0,
                'projects': [],
                'page': page,
                'limit': limit,
                'total_pages': 0
            })
        
        # Get paginated projects
        result = get_all_hidden_projects(
            hidden_projects_log_collection,
            user_id,
            page=page,
            limit=limit
        )
        
        # Count manual vs automated - optimize by calculating from the results we already have
        # This avoids a separate full collection scan
        manual_methods = ['manual', 'feedback_based', 'applied']
        automated_methods = ['auto', 'ai_auto', 'auto_similar', 'category']
        
        # Calculate method counts from the paginated results we already fetched
        # For accurate counts, we still need the full scan, but we can optimize it
        method_counts = {}
        try:
            from ..cache_manager import resolve_user_id_for_query
        except ImportError:
            try:
                from web.cache_manager import resolve_user_id_for_query
            except ImportError:
                def resolve_user_id_for_query(user_id: str):
                    return str(user_id), None
        
        current_user_id, old_user_id = resolve_user_id_for_query(user_id)
        
        try:
            # OPTIMIZATION: Only do full method count for small datasets (< 500 records)
            # For larger datasets, skip to avoid timeout (method counts are nice-to-have)
            total_from_result = result.get('total', 0)
            
            # If dataset is small, do accurate count
            # Otherwise, skip method counting for performance
            if total_from_result > 0 and total_from_result <= 500:
                # Small dataset - do full count for accuracy
                query = hidden_projects_log_collection.where(filter=FieldFilter('user_id', '==', current_user_id)).stream()
                for doc in query:
                    doc_data = doc.to_dict()
                    method = doc_data.get('hidden_method', 'unknown')
                    method_counts[method] = method_counts.get(method, 0) + 1
                
                # If no results and we have old_user_id, try that
                if not method_counts and old_user_id:
                    query_old = hidden_projects_log_collection.where(filter=FieldFilter('user_id', '==', old_user_id)).stream()
                    for doc in query_old:
                        doc_data = doc.to_dict()
                        method = doc_data.get('hidden_method', 'unknown')
                        method_counts[method] = method_counts.get(method, 0) + 1
            else:
                # Large dataset - estimate from paginated results or skip
                # Count from the projects we already fetched as a sample
                for project in result.get('projects', []):
                    method = project.get('hidden_method', 'unknown')
                    method_counts[method] = method_counts.get(method, 0) + 1
                # These are estimates, not exact counts
        except Exception as e:
            logger.error(f"Error counting by method: {e}", exc_info=True)
            method_counts = {}
        
        # Calculate manual and automated counts
        manual_count = sum(method_counts.get(method, 0) for method in manual_methods)
        automated_count = sum(method_counts.get(method, 0) for method in automated_methods)
        
        # Get total projects processed count
        total_projects_processed = get_projects_processed_count(user_id)
        
        # Enrich projects with names from cache
        enriched_projects = []
        for project in result['projects']:
            project_id = project.get('project_id')
            project_name = None
            
            # Try to get project name from cache
            if project_id and project_details_collection is not None:
                cached_details = get_cached_project_details(project_details_collection, project_id)
                if cached_details:
                    project_name = cached_details.get('name')
            
            # Add project name to the project data
            enriched_project = project.copy()
            enriched_project['project_name'] = project_name
            enriched_projects.append(enriched_project)
        
        return jsonify({
            'manual_count': manual_count,
            'automated_count': automated_count,
            'total_count': result['total'],
            'total_projects_processed': total_projects_processed,
            'projects': enriched_projects,
            'page': result['page'],
            'limit': result['limit'],
            'total_pages': result['total_pages']
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/admin/update-user-billing', methods=['POST'])
@require_auth
def update_user_billing():
    """Update user billing limit (admin only)"""
    user_id = request.auth['uid']
    
    # Check if user is admin
    if not is_admin(user_id):
        return jsonify({'error': 'Unauthorized - admin access required'}), 403
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        target_user_id = data.get('user_id')
        new_limit = data.get('projects_processed_limit')
        
        if not target_user_id:
            return jsonify({'error': 'user_id is required'}), 400
        
        if new_limit is None:
            return jsonify({'error': 'projects_processed_limit is required'}), 400
        
        # Validate limit
        try:
            new_limit = int(new_limit)
            if new_limit < 0:
                return jsonify({'error': 'Limit must be a positive integer'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid limit value'}), 400
        
        # Update user billing limit
        update_user_billing_limit(target_user_id, new_limit)
        
        return jsonify({
            'success': True,
            'message': 'User billing limit updated successfully'
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/support', methods=['POST'])
@require_auth
def submit_support():
    """Submit a support request (authenticated users only)"""
    user_id = request.auth['uid']
    user_email = request.auth.get('email')
    
    if not user_email:
        return jsonify({'error': 'Email not found in session'}), 400
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'error': 'Question is required'}), 400
        
        # Get user billing info to include in email
        try:
            from ..services.user_service import get_user_billing_info
        except ImportError:
            from services.user_service import get_user_billing_info
        
        billing_info = get_user_billing_info(user_id)
        
        # Send support email using the authenticated user's email
        try:
            send_support_email(user_id, user_email, question, billing_info)
        except Exception as email_error:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Error sending support email: {email_error}", exc_info=True)
            # Return error to user so they know email failed
            return jsonify({
                'error': f'Failed to send email: {str(email_error)}. Please check your email configuration or try again later.'
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Support request submitted successfully. We will get back to you soon!'
        })
        
    except Exception as e:
        import traceback
        logger.error(f"Error in support route: {e}", exc_info=True)
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500

