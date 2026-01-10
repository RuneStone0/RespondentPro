#!/usr/bin/env python3
"""
Authentication routes for Respondent.io Manager
"""

import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from google.cloud.firestore_v1.base_query import FieldFilter

# Import user service
try:
    from ..services.user_service import (
        get_user_by_email,
        is_user_verified,
        generate_login_token, verify_login_token
    )
    from ..services.email_service import send_login_email
    from ..auth.firebase_auth import require_auth, get_id_token_from_request, verify_firebase_token
except ImportError:
    from services.user_service import (
        get_user_by_email,
        is_user_verified,
        generate_login_token, verify_login_token
    )
    from services.email_service import send_login_email
    from auth.firebase_auth import require_auth, get_id_token_from_request, verify_firebase_token

bp = Blueprint('auth', __name__)


# get_request_origin() removed - was only used for WebAuthn


@bp.route('/')
def index():
    """Home page - show about page"""
    # Check if user is authenticated via Firebase Auth
    id_token = get_id_token_from_request()
    if id_token:
        decoded_token = verify_firebase_token(id_token)
        if decoded_token:
            return redirect(url_for('page.dashboard'))
    return redirect(url_for('page.about'))


@bp.route('/api/firebase-config')
def firebase_config():
    """Provide Firebase configuration for frontend"""
    import os
    from flask import jsonify
    
    # Get Firebase project ID
    project_id = (os.environ.get('GCP_PROJECT') or 
                 os.environ.get('GCLOUD_PROJECT') or 
                 os.environ.get('PROJECT_ID'))
    
    if not project_id:
        # Try reading from .firebaserc
        try:
            import json
            from pathlib import Path
            firebaserc_path = Path(__file__).parent.parent.parent / '.firebaserc'
            if firebaserc_path.exists():
                with open(firebaserc_path, 'r') as f:
                    firebaserc = json.load(f)
                    project_id = firebaserc.get('projects', {}).get('default')
        except Exception:
            pass
    
    # Firebase web app config
    # Note: These values should be set in environment variables or config file
    # For production, get these from Firebase Console > Project Settings > General > Your apps
    # 
    # IMPORTANT NOTES:
    # - authDomain: Can be either:
    #   * Firebase domain: {project-id}.firebaseapp.com (recommended, always works)
    #   * Custom domain: your-domain.com (requires proper Firebase Hosting setup)
    #   If using custom domain, ensure:
    #   1. Domain is added to Firebase Console > Authentication > Settings > Authorized domains
    #   2. Domain is configured in Firebase Hosting (if using Firebase Hosting)
    #   3. DNS records are properly configured
    # - storageBucket: This is the bucket NAME (not a domain), format: {project-id}.appspot.com
    #   You cannot change this - it's the actual GCS bucket identifier
    auth_domain = os.environ.get('FIREBASE_AUTH_DOMAIN', f'{project_id}.firebaseapp.com' if project_id else '')
    
    config = {
        'apiKey': os.environ.get('FIREBASE_API_KEY', ''),
        'authDomain': auth_domain,
        'projectId': project_id or '',
        'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', f'{project_id}.appspot.com' if project_id else ''),
        'messagingSenderId': os.environ.get('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId': os.environ.get('FIREBASE_APP_ID', '')
    }
    
    # Validate custom domain setup if using custom domain
    if auth_domain and not auth_domain.endswith('.firebaseapp.com'):
        # Custom domain detected - log a note (but don't fail)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Using custom authDomain: {auth_domain}. Ensure it's properly configured in Firebase Console.")
    
    return jsonify(config)


@bp.route('/api/debug/token-check')
def debug_token_check():
    """Debug endpoint to check token status - helps diagnose authentication issues"""
    from flask import jsonify
    from ..auth.firebase_auth import get_id_token_from_request, verify_firebase_token
    
    id_token = get_id_token_from_request()
    
    response_data = {
        'token_present': bool(id_token),
        'request_path': request.path,
        'request_method': request.method,
        'cookies_present': list(request.cookies.keys()),
        'has_authorization_header': 'Authorization' in request.headers,
    }
    
    if not id_token:
        response_data['error'] = 'No token found in request'
        # Check if Authorization header exists but is empty
        auth_header = request.headers.get('Authorization', '')
        if auth_header:
            response_data['authorization_header'] = auth_header[:50] + '...' if len(auth_header) > 50 else auth_header
        return jsonify(response_data), 200
    
    # Token is present, try to verify it
    response_data['token_length'] = len(id_token)
    response_data['token_preview'] = id_token[:50] + '...' if len(id_token) > 50 else id_token
    
    decoded_token = verify_firebase_token(id_token)
    
    if not decoded_token:
        response_data['token_valid'] = False
        response_data['error'] = 'Token verification failed'
        return jsonify(response_data), 200
    
    # Token is valid
    response_data['token_valid'] = True
    response_data['uid'] = decoded_token.get('uid')
    response_data['email'] = decoded_token.get('email')
    response_data['email_verified'] = decoded_token.get('email_verified', False)
    response_data['token_exp'] = decoded_token.get('exp')
    response_data['token_iat'] = decoded_token.get('iat')
    
    return jsonify(response_data), 200


@bp.route('/login')
def login():
    """Login page - redirect to about page (login is now in modal)"""
    # Check if user is authenticated via Firebase Auth
    id_token = get_id_token_from_request()
    if id_token:
        decoded_token = verify_firebase_token(id_token)
        if decoded_token:
            return redirect(url_for('page.dashboard'))
    return redirect(url_for('page.about'))


# WebAuthn routes removed - Firebase Auth handles authentication now

# Firebase Auth endpoints
@bp.route('/api/auth/signup', methods=['POST'])
def firebase_signup():
    """Firebase Auth signup endpoint (handled by frontend, this is for reference)"""
    return jsonify({'error': 'Signup is handled by Firebase Auth client SDK on the frontend'}), 400


@bp.route('/api/auth/signin', methods=['POST'])
def firebase_signin():
    """Firebase Auth signin endpoint (handled by frontend, this is for reference)"""
    return jsonify({'error': 'Signin is handled by Firebase Auth client SDK on the frontend'}), 400


@bp.route('/api/auth/logout', methods=['POST'])
@require_auth
def firebase_logout():
    """Firebase Auth logout endpoint"""
    # Logout is handled by frontend Firebase Auth SDK
    # This endpoint can be used for any server-side cleanup if needed
    return jsonify({'success': True, 'message': 'Logged out successfully'})


# All WebAuthn routes removed - Firebase Auth handles authentication


@bp.route('/logout')
def logout():
    """Logout user - clears Firebase Auth session (handled by frontend)"""
    # Logout is handled by Firebase Auth client SDK
    # This endpoint redirects to about page
    return redirect(url_for('page.about'))


# Legacy WebAuthn routes removed:
# - /api/register/begin
# - /api/register/complete  
# - /api/login/begin
# - /api/login/complete
# - /api/passkeys
# - /api/passkeys/add
# - /api/passkeys/add/complete
# - /api/passkeys/<credential_id> (DELETE)

# All WebAuthn route implementations removed
    """Begin passkey authentication"""
    try:
        data = request.json
        email = data.get('email')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Validate email format
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        user_id = get_user_by_email(email)
        if not user_id:
            return jsonify({'error': 'User not found'}), 404
        
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
        # Load credentials filtered by rp_id
        user_credential = load_credentials_by_user_id(user_id, rp_id=rp_id)
        
        # If no credential for this domain, check if user has other credentials
        if not user_credential:
            all_credentials = load_credentials_by_user_id(user_id, rp_id=None)
            if all_credentials and len(all_credentials) > 0:
                # User has credentials but not for this domain
                return jsonify({
                    'error': 'No passkey for this domain',
                    'has_other_credentials': True,
                    'can_login_via_email': True,
                    'message': 'You have passkeys registered for other domains. Please add a passkey or log in via email.'
                }), 404
            else:
                # User exists but has no credentials at all - allow them to add first passkey
                return jsonify({
                    'error': 'No credentials found for user',
                    'user_exists': True,
                    'needs_first_passkey': True,
                    'can_login_via_email': True,
                    'message': 'Your account exists but has no passkeys. Please register a passkey to continue or log in via email.'
                }), 404
        
        if PublicKeyCredentialType:
            cred_type = PublicKeyCredentialType.PUBLIC_KEY
        else:
            class CredentialType:
                value = 'public-key'
            cred_type = CredentialType()
        
        if PublicKeyCredentialDescriptor:
            credential_descriptor = PublicKeyCredentialDescriptor(
                id=user_credential['credential_id'],
                type=cred_type
            )
        else:
            credential_descriptor = SimpleNamespace(
                id=user_credential['credential_id'],
                type=cred_type
            )
        
        options = generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=[credential_descriptor]
        )
        
        session['challenge'] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        session['login_user_id'] = user_id
        session['login_email'] = email
        
        options_json_str = options_to_json(options)
        if isinstance(options_json_str, str):
            options_json = json.loads(options_json_str)
        elif isinstance(options_json_str, dict):
            options_json = options_json_str
        else:
            try:
                options_json = json.loads(json.dumps(options_json_str))
            except:
                options_json = {}
        
        challenge_b64 = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        options_json['challenge'] = challenge_b64
        
        return jsonify(options_json)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


# All WebAuthn routes removed - Firebase Auth handles authentication
# Removed routes:
# - /api/register/begin
# - /api/register/complete
# - /api/login/begin  
# - /api/login/complete
# - /api/passkeys
# - /api/passkeys/add
# - /api/passkeys/add/complete
# - /api/passkeys/<credential_id> (DELETE)

def login_complete_removed():
    """Complete passkey authentication"""
    try:
        if 'login_user_id' not in session:
            return jsonify({'error': 'No login in progress'}), 400
        
        user_id = session.get('login_user_id')
        email = session.get('login_email')
        challenge_b64 = session.get('challenge')
        
        if not user_id or not challenge_b64:
            return jsonify({'error': 'Session expired'}), 400
        
        # Determine rp_id first
        hostname = request.host.split(':')[0]
        if hostname == '127.0.0.1' or hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
        # Load credential for the specific rp_id
        user_credential = load_credentials_by_user_id(user_id, rp_id=rp_id)
        if not user_credential:
            return jsonify({'error': 'No credentials found for this domain'}), 404
        
        # Ensure user_credential is a dict, not a list
        # This can happen if load_credentials_by_user_id returns a list by mistake
        if isinstance(user_credential, list):
            if len(user_credential) == 0:
                return jsonify({'error': 'No credentials found for this domain'}), 404
            # If it's a list, find the one matching rp_id or take the first one
            matching_cred = None
            for cred in user_credential:
                if isinstance(cred, dict) and cred.get('rp_id') == rp_id:
                    matching_cred = cred
                    break
            if not matching_cred:
                matching_cred = user_credential[0] if isinstance(user_credential[0], dict) else None
            if not matching_cred:
                return jsonify({'error': 'Invalid credential format'}), 500
            user_credential = matching_cred
        
        # Verify user_credential is a dict with required fields
        if not isinstance(user_credential, dict) or 'public_key' not in user_credential:
            return jsonify({'error': 'Invalid credential format'}), 500
        
        data = request.json
        credential_data = data.get('credential')
        
        if not credential_data:
            return jsonify({'error': 'Credential is required'}), 400
        
        # Validate credential_data structure
        if not isinstance(credential_data, dict):
            return jsonify({'error': f'Invalid credential format: expected dict, got {type(credential_data).__name__}'}), 400
        
        if 'response' not in credential_data:
            return jsonify({'error': 'Credential response is missing'}), 400
        
        # Ensure response is a dict, not a list
        response_data = credential_data.get('response')
        if response_data is None:
            return jsonify({'error': 'Credential response is missing'}), 400
        
        # Check if response_data is a list (which would be invalid)
        # Use type() check first to avoid any potential issues with isinstance
        response_type = type(response_data).__name__
        if response_type == 'list':
            return jsonify({'error': f'Invalid credential response format: expected dict, got list. Response type: {response_type}, Length: {len(response_data)}'}), 400
        
        # Ensure response_data is a dict - use hasattr to check for dict-like behavior
        if not hasattr(response_data, 'get') or not hasattr(response_data, 'keys'):
            return jsonify({'error': f'Invalid credential response format: expected dict, got {response_type}. Response: {str(response_data)[:200]}'}), 400
        
        # Validate required response fields - use .get() to safely access
        required_fields = ['clientDataJSON', 'authenticatorData', 'signature']
        missing_fields = []
        for field in required_fields:
            if not hasattr(response_data, 'get') or response_data.get(field) is None:
                missing_fields.append(field)
        
        if missing_fields:
            return jsonify({'error': f'Missing required fields in credential response: {", ".join(missing_fields)}'}), 400
        
        try:
            def decode_base64(s):
                if not s:
                    return None
                padding = 4 - (len(s) % 4)
                if padding != 4:
                    s += '=' * padding
                return base64.urlsafe_b64decode(s)
            
            challenge_b64_padded = challenge_b64
            padding = 4 - (len(challenge_b64_padded) % 4)
            if padding != 4:
                challenge_b64_padded += '=' * padding
            challenge = base64.urlsafe_b64decode(challenge_b64_padded)
            
            authentication_response = SimpleNamespace(
                client_data_json=decode_base64(response_data['clientDataJSON']),
                authenticator_data=decode_base64(response_data['authenticatorData']),
                signature=decode_base64(response_data['signature']),
                user_handle=decode_base64(response_data.get('userHandle')) if response_data.get('userHandle') else None
            )
            
            credential = AuthenticationCredential(
                id=credential_data['id'],
                raw_id=decode_base64(credential_data['rawId']),
                response=authentication_response,
                type=credential_data.get('type', 'public-key')
            )
            
            origin = get_request_origin()
            expected_rp_id = rp_id
            
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=expected_rp_id,
                expected_origin=origin,
                credential_public_key=user_credential['public_key'],
                credential_current_sign_count=user_credential.get('counter', 0)
            )
            
            # Update counter for the specific credential
            if isinstance(user_credential['credential_id'], bytes):
                credential_id_for_update = user_credential['credential_id']
            else:
                credential_id_for_update = user_credential['credential_id']
            
            update_credential_counter(user_id, credential_id_for_update, verification.new_sign_count)
            
            session['user_id'] = user_id
            session['email'] = email
            session.permanent = True
            session.pop('login_user_id', None)
            session.pop('login_email', None)
            session.pop('challenge', None)
            
            # Check if email is verified - redirect to verification pending if not
            if not is_user_verified(user_id):
                return jsonify({'success': True, 'redirect': url_for('auth.verify_pending')})
            
            return jsonify({'success': True, 'redirect': url_for('page.dashboard')})
        except Exception as e:
            import traceback
            return jsonify({'error': f'Verification failed: {str(e)}\n{traceback.format_exc()}'}), 400
            
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


# Logout route already defined above


@bp.route('/verify-pending')
def verify_pending():
    """Verification pending page - shown when user is not verified"""
    # Check for Firebase Auth token
    id_token = get_id_token_from_request()
    if id_token:
        decoded_token = verify_firebase_token(id_token)
        if decoded_token:
            email = decoded_token.get('email', '')
            # If already verified, redirect to dashboard
            if decoded_token.get('email_verified', False):
                return redirect(url_for('page.dashboard'))
            return render_template('verify_pending.html', email=email)
    
    # Not authenticated - redirect to about page
    return redirect(url_for('page.about'))


@bp.route('/api/verify-email/send', methods=['POST'])
@require_auth
def send_verification_email_api():
    """Send verification email (resend functionality) - Firebase Auth handles this"""
    # Firebase Auth handles email verification natively
    # This endpoint is kept for backward compatibility but redirects to Firebase Auth flow
    return jsonify({
        'error': 'Email verification is handled by Firebase Auth. Please use the Firebase Auth client SDK to resend verification emails.'
    }), 400


@bp.route('/api/verify-email/<token>')
def verify_email_token(token):
    """Verify email with token (GET endpoint for email links) - Legacy support"""
    # Legacy email verification - Firebase Auth handles this natively
    # This endpoint is kept for backward compatibility with old verification emails
    try:
        try:
            from ..db import users_collection
        except ImportError:
            from db import users_collection
        
        if users_collection:
            query = users_collection.where(filter=FieldFilter('verification_token', '==', token)).limit(1).stream()
            docs = list(query)
            if docs:
                user_doc = docs[0]
                user_data = user_doc.to_dict()
                user_id = user_doc.id
                # Import verify_user_email if needed
                try:
                    from ..services.user_service import verify_user_email
                except ImportError:
                    from services.user_service import verify_user_email
                
                if verify_user_email(user_id, token):
                    # Redirect to dashboard - user will need to sign in with Firebase Auth
                    return redirect(url_for('page.dashboard'))
    except Exception:
        pass
    
    return redirect(url_for('page.about'))


@bp.route('/api/verify-email/verify', methods=['POST'])
@require_auth
def verify_email_api():
    """Verify email with token (POST endpoint for API calls) - Legacy support"""
    # Firebase Auth handles email verification natively
    # This endpoint is kept for backward compatibility
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({'error': 'Token is required'}), 400
    
    try:
        # Import verify_user_email if needed
        try:
            from ..services.user_service import verify_user_email
        except ImportError:
            from services.user_service import verify_user_email
        
        user_id = request.auth['uid']
        if verify_user_email(user_id, token):
            return jsonify({'success': True, 'message': 'Email verified'})
        else:
            return jsonify({'error': 'Invalid or expired token'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# All WebAuthn passkey routes removed - Firebase Auth handles passkeys natively
# Removed: /api/passkeys, /api/passkeys/add, /api/passkeys/add/complete, /api/passkeys/<credential_id>

def list_passkeys_removed():
    """List all passkeys for current user"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    
    try:
        credentials = load_credentials_by_user_id(user_id, rp_id=None)
        
        if not credentials:
            return jsonify({'passkeys': []})
        
        # Ensure credentials is a list
        if not isinstance(credentials, list):
            credentials = [credentials]
        
        passkeys = []
        for cred in credentials:
            # Convert credential_id to base64 string for display
            cred_id_str = None
            if cred.get('credential_id'):
                if isinstance(cred['credential_id'], bytes):
                    cred_id_str = base64.urlsafe_b64encode(cred['credential_id']).decode('utf-8').rstrip('=')
                cred_id_bytes = cred['credential_id']
                # Also store bytes for deletion
                cred_id_for_delete = cred_id_bytes
            else:
                cred_id_str = str(cred.get('credential_id', ''))
                cred_id_for_delete = cred_id_str
            
            passkeys.append({
                'credential_id': cred_id_str,
                'credential_id_bytes': base64.urlsafe_b64encode(cred_id_for_delete).decode('utf-8').rstrip('=') if isinstance(cred_id_for_delete, bytes) else cred_id_for_delete,
                'rp_id': cred.get('rp_id', 'localhost'),
                'created_at': cred.get('created_at').isoformat() if cred.get('created_at') else None,
                'name': cred.get('name', '')
            })
        
        return jsonify({'passkeys': passkeys})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


def add_passkey_begin_removed():
    """Begin adding new passkey"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    email = session.get('email')
    
    # Check if email is verified
    if not is_user_verified(user_id):
        return jsonify({'error': 'Email must be verified before adding passkeys'}), 403
    
    try:
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
        # Check if user already has a credential for this rp_id
        existing_cred = load_credentials_by_user_id(user_id, rp_id=rp_id)
        if existing_cred:
            return jsonify({'error': 'You already have a passkey for this domain'}), 400
        
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Respondent Pro",
            user_id=email.encode('utf-8') if email else user_id.encode('utf-8'),
            user_name=email or user_id,
            user_display_name=email or user_id,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
                user_verification=UserVerificationRequirement.PREFERRED
            )
        )
        
        session['challenge'] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        session['add_passkey'] = True
        session['add_passkey_rp_id'] = rp_id
        
        options_json_str = options_to_json(options)
        if isinstance(options_json_str, str):
            options_json = json.loads(options_json_str)
        elif isinstance(options_json_str, dict):
            options_json = options_json_str
        else:
            try:
                options_json = json.loads(json.dumps(options_json_str))
            except:
                options_json = {}
        
        challenge_b64 = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        options_json['challenge'] = challenge_b64
        
        return jsonify(options_json)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


def add_passkey_complete_removed():
    """Complete adding new passkey"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    if 'add_passkey' not in session or not session['add_passkey']:
        return jsonify({'error': 'No passkey addition in progress'}), 400
    
    user_id = session['user_id']
    challenge_b64 = session.get('challenge')
    rp_id = session.get('add_passkey_rp_id', 'localhost')
    
    if not challenge_b64:
        return jsonify({'error': 'Session expired'}), 400
    
    data = request.json
    credential_data = data.get('credential')
    
    if not credential_data:
        return jsonify({'error': 'Credential is required'}), 400
    
    try:
        challenge_b64_padded = challenge_b64
        padding = 4 - (len(challenge_b64_padded) % 4)
        if padding != 4:
            challenge_b64_padded += '=' * padding
        challenge = base64.urlsafe_b64decode(challenge_b64_padded)
        
        def decode_base64(s):
            padding = 4 - (len(s) % 4)
            if padding != 4:
                s += '=' * padding
            return base64.urlsafe_b64decode(s)
        
        registration_response = SimpleNamespace(
            client_data_json=decode_base64(credential_data['response']['clientDataJSON']),
            attestation_object=decode_base64(credential_data['response']['attestationObject'])
        )
        
        credential = RegistrationCredential(
            id=credential_data['id'],
            raw_id=decode_base64(credential_data['rawId']),
            response=registration_response,
            type=credential_data.get('type', 'public-key')
        )
        
        origin = get_request_origin()
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            expected_rp_id = 'localhost'
        else:
            expected_rp_id = hostname
        
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=expected_rp_id,
            expected_origin=origin
        )
        
        # Add credential to user
        add_credential_to_user(user_id, {
            'credential_id': verification.credential_id,
            'public_key': verification.credential_public_key,
            'counter': verification.sign_count
        }, rp_id=expected_rp_id)
        
        session.pop('add_passkey', None)
        session.pop('add_passkey_rp_id', None)
        session.pop('challenge', None)
        
        return jsonify({'success': True, 'message': 'Passkey added successfully'})
    except Exception as e:
        import traceback
        return jsonify({'error': f'Verification failed: {str(e)}\n{traceback.format_exc()}'}), 400


def delete_passkey_removed(credential_id):
    """Delete a passkey"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    
    try:
        # Decode credential_id if it's base64
        try:
            padding = 4 - (len(credential_id) % 4)
            if padding != 4:
                credential_id += '=' * padding
            credential_id_bytes = base64.urlsafe_b64decode(credential_id)
        except:
            credential_id_bytes = credential_id.encode('utf-8') if isinstance(credential_id, str) else credential_id
        
        # Check if user has more than one credential
        all_credentials = load_credentials_by_user_id(user_id, rp_id=None)
        if not all_credentials:
            return jsonify({'error': 'No credentials found'}), 404
        
        if not isinstance(all_credentials, list):
            all_credentials = [all_credentials]
        
        if len(all_credentials) <= 1:
            return jsonify({'error': 'Cannot delete last passkey'}), 400
        
        delete_credential_from_user(user_id, credential_id_bytes)
        
        return jsonify({'success': True, 'message': 'Passkey deleted successfully'})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/api/login/email/send', methods=['POST'])
def send_login_email_api():
    """Send login link via email (works with both Firebase Auth and legacy users)"""
    try:
        data = request.json
        email = data.get('email')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Validate email format
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Check if user exists in Firestore
        user_id = get_user_by_email(email)
        
        # If user doesn't exist in Firestore, check if they exist in Firebase Auth
        if not user_id:
            try:
                import firebase_admin
                from firebase_admin import auth
                firebase_user = auth.get_user_by_email(email)
                # User exists in Firebase Auth but not in Firestore
                # Create Firestore user document
                from ..auth.firebase_auth import ensure_firestore_user_exists
                user_id = ensure_firestore_user_exists(
                    firebase_user.uid,
                    email,
                    firebase_user.email_verified
                )
            except auth.UserNotFoundError:
                # User doesn't exist in Firebase Auth either
                return jsonify({'error': 'User not found. Please sign up first.'}), 404
            except Exception as e:
                # Other error - log and return generic message
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error checking Firebase Auth for user {email}: {e}")
                return jsonify({'error': 'User not found. Please sign up first.'}), 404
        
        # Generate login token and send email
        try:
            token = generate_login_token(user_id)
            send_login_email(email, token)
            return jsonify({'success': True, 'message': 'Login link sent to your email'})
        except Exception as e:
            return jsonify({'error': f'Failed to send login email: {str(e)}'}), 500
            
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


# Removed /api/login/email/<token> endpoint - now handled on /about page with ?token= query parameter

