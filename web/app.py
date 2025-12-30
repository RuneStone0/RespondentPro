#!/usr/bin/env python3
"""
Flask web UI for Respondent.io API management with passkey authentication
"""

import os
import secrets
from pathlib import Path
from flask import Flask
from dotenv import load_dotenv

# Import database collections
try:
    from .db import (
        users_collection, session_keys_collection, projects_cache_collection,
        user_preferences_collection, hidden_projects_log_collection,
        hide_feedback_collection, category_recommendations_collection,
        user_profiles_collection, mongo_available
    )
except ImportError:
    from db import (
        users_collection, session_keys_collection, projects_cache_collection,
        user_preferences_collection, hidden_projects_log_collection,
        hide_feedback_collection, category_recommendations_collection,
        user_profiles_collection, mongo_available
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

