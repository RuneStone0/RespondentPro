#!/usr/bin/env python3
"""
API routes for Respondent.io Manager
"""

import json
import base64
import threading
import time
from flask import Blueprint, request, jsonify, session
from datetime import datetime

# Import services
try:
    from ..services.user_service import load_user_config, save_user_config, load_user_filters, save_user_filters, update_last_synced
    from ..services.respondent_auth_service import create_respondent_session, verify_respondent_authentication, fetch_and_store_user_profile
    from ..services.project_service import (
        fetch_respondent_projects, fetch_all_respondent_projects, hide_project_via_api,
        get_hidden_count, process_and_hide_projects, get_hide_progress, hide_progress
    )
    from ..cache_manager import get_cached_projects, get_cache_stats, mark_projects_hidden_in_cache
    from ..hidden_projects_tracker import (
        get_hidden_projects_count, get_hidden_projects_timeline, get_hidden_projects_stats
    )
    from ..ai_analyzer import (
        generate_question_from_project, find_similar_projects, generate_hide_suggestions
    )
    from ..preference_learner import (
        record_project_hidden, store_question_answer, get_user_preferences, should_hide_based_on_ai_preferences
    )
    from ..services.filter_service import should_hide_project, get_project_is_remote
    from ..db import (
        projects_cache_collection, hidden_projects_log_collection, user_preferences_collection, topics_collection,
        project_details_collection
    )
    from ..services.topics_service import get_all_topics
except ImportError:
    from services.user_service import load_user_config, save_user_config, load_user_filters, save_user_filters, update_last_synced
    from services.respondent_auth_service import create_respondent_session, verify_respondent_authentication, fetch_and_store_user_profile
    from services.project_service import (
        fetch_respondent_projects, fetch_all_respondent_projects, hide_project_via_api,
        get_hidden_count, process_and_hide_projects, get_hide_progress, hide_progress
    )
    from cache_manager import get_cached_projects, get_cache_stats, mark_projects_hidden_in_cache
    from hidden_projects_tracker import (
        get_hidden_projects_count, get_hidden_projects_timeline, get_hidden_projects_stats
    )
    from ai_analyzer import (
        generate_question_from_project, find_similar_projects, generate_hide_suggestions
    )
    from preference_learner import (
        record_project_hidden, store_question_answer, get_user_preferences, should_hide_based_on_ai_preferences
    )
    from services.filter_service import should_hide_project, get_project_is_remote
    from db import (
        projects_cache_collection, hidden_projects_log_collection, user_preferences_collection, topics_collection,
        project_details_collection
    )
    from services.topics_service import get_all_topics

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/session-keys', methods=['POST'])
def save_session_keys():
    """Save user's Respondent.io session keys to MongoDB and test them"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        data = request.json
        session_sid = data.get('session_sid', '').strip()
        authorization = data.get('authorization', '').strip()
        
        if not session_sid:
            return jsonify({'error': 'respondent.session.sid is required'}), 400
        
        user_id = session['user_id']
        config = {
            'cookies': {
                'respondent.session.sid': session_sid
            },
            'authorization': authorization if authorization else None
        }
        
        # Test the credentials first
        verification_result = verify_respondent_authentication(
            cookies=config['cookies'],
            authorization=config.get('authorization')
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
                    print(f"Error fetching profile in background: {e}")
            
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
def get_session_keys():
    """Get user's Respondent.io session keys"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    config = load_user_config(user_id)
    
    if not config:
        return jsonify({'cookies': {}, 'authorization': None})
    
    return jsonify(config)


@bp.route('/filters', methods=['GET'])
def get_filters():
    """Get user's project filter preferences"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    filters = load_user_filters(user_id)
    
    return jsonify(filters)


@bp.route('/topics', methods=['GET'])
def get_topics():
    """Get all available topics"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        topics = get_all_topics(topics_collection)
        return jsonify({'topics': topics})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/filters', methods=['POST'])
def save_filters():
    """Save user's project filter preferences"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = session['user_id']
        data = request.json
        
        # Default to empty dict if no data provided (save_user_filters handles this)
        if data is None:
            data = {}
        
        save_user_filters(user_id, data)
        
        # Update last synced time when filters are applied
        update_last_synced(user_id)
        
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
                        cookies=config.get('cookies', {}),
                        authorization=config.get('authorization')
                    )
                    
                    def hide_in_background():
                        try:
                            process_and_hide_projects(
                                user_id, req_session, profile_id, saved_filters,
                                cookies=config.get('cookies', {}),
                                authorization=config.get('authorization')
                            )
                        except Exception as e:
                            import traceback
                            print(f"Error in background hide process: {traceback.format_exc()}")
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
def hide_projects():
    """Start the process of hiding projects based on filters"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = session['user_id']
        config = load_user_config(user_id)
        filters = load_user_filters(user_id)
        
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            return jsonify({'error': 'Session keys not configured'}), 400
        
        profile_id = config.get('profile_id')
        if not profile_id:
            return jsonify({'error': 'Profile ID not found'}), 400
        
        req_session = create_respondent_session(
            cookies=config.get('cookies', {}),
            authorization=config.get('authorization')
        )
        
        def hide_in_background():
            try:
                process_and_hide_projects(
                    user_id, req_session, profile_id, filters,
                    cookies=config.get('cookies', {}),
                    authorization=config.get('authorization')
                )
            except Exception as e:
                import traceback
                print(f"Error in background hide process: {traceback.format_exc()}")
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
def preview_hide():
    """Preview projects that would be hidden based on current filter settings"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = session['user_id']
        data = request.json
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
            'topics': data.get('topics', [])
        }
        
        # Check if any filters are set
        if filters['min_incentive'] is None and filters['min_hourly_rate'] is None and filters['isRemote'] is None and not filters['topics']:
            return jsonify({
                'success': True,
                'projects': [],
                'count': 0,
                'message': 'No filters set - no projects would be hidden'
            })
        
        # Get cached projects or fetch them
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            return jsonify({'error': 'Session keys not configured'}), 400
        
        profile_id = config.get('profile_id')
        if not profile_id:
            return jsonify({'error': 'Profile ID not found'}), 400
        
        # Try to get from cache first, otherwise fetch projects
        req_session = create_respondent_session(
            cookies=config.get('cookies', {}),
            authorization=config.get('authorization')
        )
        all_projects, _ = fetch_all_respondent_projects(
            session=req_session,
            profile_id=profile_id,
            page_size=50,
            user_id=user_id,
            use_cache=True,
            cookies=config.get('cookies', {}),
            authorization=config.get('authorization')
        )
        
        # Find projects that would be hidden
        projects_to_hide = []
        for project in all_projects:
            # Check if project should be hidden
            if should_hide_project(project, filters, project_details_collection=project_details_collection):
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
        
        return jsonify({
            'success': True,
            'projects': projects_to_hide,
            'count': len(projects_to_hide)
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/hide-progress', methods=['GET'])
def get_hide_progress_route():
    """Get the current progress of hiding projects"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
        progress = get_hide_progress(user_id)
        return jsonify(progress)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/hide-project', methods=['POST'])
def hide_project():
    """Hide a single project with optional feedback and generate AI question"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
        data = request.json
        project_id = data.get('project_id')
        feedback_text = data.get('feedback_text')
        
        if not project_id:
            return jsonify({'error': 'project_id is required'}), 400
        
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            return jsonify({'error': 'Session keys not configured'}), 400
        
        req_session = create_respondent_session(
            cookies=config.get('cookies', {}),
            authorization=config.get('authorization')
        )
        
        success = hide_project_via_api(req_session, project_id)
        if not success:
            return jsonify({'error': 'Failed to hide project'}), 500
        
        if projects_cache_collection is not None:
            mark_projects_hidden_in_cache(projects_cache_collection, user_id, [project_id])
        
        hidden_method = 'feedback_based' if feedback_text else 'manual'
        
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
        
        # Generate AI question if no feedback provided (feedback means user already explained)
        question = None
        if not feedback_text and project_data:
            # Check if we've already asked this type of question before
            prefs = get_user_preferences(user_preferences_collection, user_id) if user_preferences_collection is not None else {}
            existing_question_ids = {qa.get('question_id') for qa in prefs.get('question_answers', [])}
            
            question_data = generate_question_from_project(project_data)
            if question_data and question_data.get('id') not in existing_question_ids:
                question = question_data
        
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
def get_hide_suggestions():
    """Get AI-generated suggestions for why a user might hide a project"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
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
def answer_question():
    """Answer an AI-generated question and auto-hide similar projects if applicable"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
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
                                cookies=config.get('cookies', {}),
                                authorization=config.get('authorization')
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


@bp.route('/analytics/hidden-count', methods=['GET'])
def get_hidden_count_api():
    """Get total count of hidden projects"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
        count = get_hidden_count(user_id)
        return jsonify({'total_count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/analytics/hidden-timeline', methods=['GET'])
def get_hidden_timeline():
    """Get hidden projects grouped by date for graphing"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
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
def get_hidden_stats():
    """Get detailed statistics about hidden projects"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
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


@bp.route('/cache/stats', methods=['GET'])
def get_cache_stats_api():
    """Get cache statistics including refresh time"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
        if projects_cache_collection is not None:
            stats = get_cache_stats(projects_cache_collection, user_id)
            last_updated = stats.get('last_updated')
            
            # Return UTC timestamp for client-side timezone conversion
            last_updated_iso = None
            if last_updated:
                if isinstance(last_updated, datetime):
                    last_updated_iso = last_updated.isoformat() + 'Z'
                elif isinstance(last_updated, str):
                    if not last_updated.endswith('Z') and '+' not in last_updated:
                        last_updated_iso = last_updated + 'Z'
                    else:
                        last_updated_iso = last_updated
                else:
                    if hasattr(last_updated, 'isoformat'):
                        last_updated_iso = last_updated.isoformat() + 'Z'
                    elif hasattr(last_updated, 'strftime'):
                        last_updated_iso = datetime.fromtimestamp(last_updated.timestamp()).isoformat() + 'Z'
                    else:
                        last_updated_iso = str(last_updated)
            
            return jsonify({
                'exists': stats.get('exists', False),
                'last_updated': last_updated_iso,
                'total_count': stats.get('total_count', 0)
            })
        else:
            return jsonify({
                'exists': False,
                'last_updated': None,
                'total_count': 0
            })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/cache/refresh', methods=['POST'])
def refresh_cache():
    """Manually refresh the project cache"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        user_id = str(session['user_id'])
        
        config = load_user_config(user_id)
        if not config or not config.get('cookies', {}).get('respondent.session.sid'):
            return jsonify({'error': 'Session keys not configured'}), 400
        
        profile_id = config.get('profile_id')
        if not profile_id:
            return jsonify({'error': 'Profile ID not found'}), 400
        
        req_session = create_respondent_session(
            cookies=config.get('cookies', {}),
            authorization=config.get('authorization')
        )
        
        all_projects, total_count = fetch_all_respondent_projects(
            session=req_session,
            profile_id=profile_id,
            page_size=50,
            user_id=user_id,
            use_cache=False,
            cookies=config.get('cookies', {}),
            authorization=config.get('authorization')
        )
        
        last_updated_iso = None
        if projects_cache_collection is not None:
            cache_stats = get_cache_stats(projects_cache_collection, user_id)
            last_updated = cache_stats.get('last_updated')
            if last_updated:
                if isinstance(last_updated, datetime):
                    last_updated_iso = last_updated.isoformat() + 'Z'
                elif isinstance(last_updated, str):
                    if not last_updated.endswith('Z') and '+' not in last_updated:
                        last_updated_iso = last_updated + 'Z'
                    else:
                        last_updated_iso = last_updated
                else:
                    if hasattr(last_updated, 'isoformat'):
                        last_updated_iso = last_updated.isoformat() + 'Z'
                    elif hasattr(last_updated, 'strftime'):
                        last_updated_iso = datetime.fromtimestamp(last_updated.timestamp()).isoformat() + 'Z'
        
        return jsonify({
            'success': True,
            'message': 'Cache refreshed successfully',
            'last_updated': last_updated_iso,
            'total_count': total_count
        })
        
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500

