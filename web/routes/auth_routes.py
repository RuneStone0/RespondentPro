#!/usr/bin/env python3
"""
Authentication routes for Respondent.io Manager
"""

import json
import base64
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorAttachment,
    UserVerificationRequirement,
    RegistrationCredential,
    AuthenticationCredential,
)
from types import SimpleNamespace

# Try to import PublicKeyCredentialDescriptor and PublicKeyCredentialType
try:
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, PublicKeyCredentialType
except ImportError:
    PublicKeyCredentialDescriptor = None
    try:
        from webauthn.helpers.structs import PublicKeyCredentialType
    except ImportError:
        PublicKeyCredentialType = None

# Import user service
try:
    from ..services.user_service import (
        user_exists_by_email, create_user, get_user_by_email,
        load_credentials_by_user_id, add_credential_to_user, delete_credential_from_user,
        update_credential_counter, get_user_verification_status, is_user_verified,
        verify_user_email, generate_verification_token, get_email_by_user_id,
        generate_login_token, verify_login_token
    )
    from ..services.email_service import send_verification_email, send_login_email
except ImportError:
    from services.user_service import (
        user_exists_by_email, create_user, get_user_by_email,
        load_credentials_by_user_id, add_credential_to_user, delete_credential_from_user,
        update_credential_counter, get_user_verification_status, is_user_verified,
        verify_user_email, generate_verification_token, get_email_by_user_id,
        generate_login_token, verify_login_token
    )
    from services.email_service import send_verification_email, send_login_email

bp = Blueprint('auth', __name__)


def get_request_origin():
    """
    Get the correct origin for the request, handling reverse proxy scenarios.
    Checks X-Forwarded-Proto header first (set by reverse proxies like load balancers),
    then falls back to request.scheme.
    """
    # Check for X-Forwarded-Proto header (set by reverse proxies)
    forwarded_proto = request.headers.get('X-Forwarded-Proto', '').lower()
    if forwarded_proto in ('http', 'https'):
        scheme = forwarded_proto
    else:
        scheme = request.scheme
    
    return f"{scheme}://{request.host}"


@bp.route('/')
def index():
    """Home page - show about page"""
    if 'user_id' in session:
        return redirect(url_for('page.dashboard'))
    return redirect(url_for('page.about'))


@bp.route('/login')
def login():
    """Login page - redirect to about page (login is now in modal)"""
    if 'user_id' in session:
        return redirect(url_for('page.dashboard'))
    return redirect(url_for('page.about'))


@bp.route('/api/register/begin', methods=['POST'])
def register_begin():
    """Begin passkey registration"""
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
        
        # Check if user already exists
        existing_user_id = get_user_by_email(email)
        if existing_user_id:
            # User exists - check if they have any credentials
            all_credentials = load_credentials_by_user_id(existing_user_id, rp_id=None)
            if all_credentials and len(all_credentials) > 0:
                # User has credentials - they should login instead
                # Check if they have credentials for current domain
                hostname = request.host.split(':')[0]
                if hostname == '0.0.0.0':
                    rp_id = 'localhost'
                else:
                    rp_id = hostname
                
                domain_credential = load_credentials_by_user_id(existing_user_id, rp_id=rp_id)
                if domain_credential:
                    # They have a passkey for this domain - should login
                    return jsonify({
                        'error': 'Email already registered. Please log in instead.',
                        'has_credentials': True,
                        'can_login_via_email': True
                    }), 400
                else:
                    # They have credentials but not for this domain
                    return jsonify({
                        'error': 'Email already registered. Please log in instead.',
                        'has_credentials': True,
                        'no_domain_passkey': True,
                        'can_login_via_email': True
                    }), 400
            else:
                # User exists but has no credentials - allow them to register first passkey
                # We'll use the existing user_id when completing registration
                session['existing_user_id'] = existing_user_id
                session['registration_email'] = email
                session['registration'] = True
        
        # If we get here, either user doesn't exist (new registration) or exists but has no credentials
        if 'registration_email' not in session:
            session['registration_email'] = email
            session['registration'] = True
        
        # Generate registration options
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Respondent Pro",
            user_id=email.encode('utf-8'),
            user_name=email,
            user_display_name=email,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
                user_verification=UserVerificationRequirement.PREFERRED
            )
        )
        
        session['challenge'] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        
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
        return jsonify({'error': str(e)}), 500


@bp.route('/api/register/complete', methods=['POST'])
def register_complete():
    """Complete passkey registration"""
    try:
        if 'registration' not in session or not session['registration']:
            return jsonify({'error': 'No registration in progress'}), 400
        
        email = session.get('registration_email')
        challenge_b64 = session.get('challenge')
        
        if not email or not challenge_b64:
            return jsonify({'error': 'Session expired'}), 400
        
        data = request.json
        credential_data = data.get('credential')
        
        if not credential_data:
            return jsonify({'error': 'Credential is required'}), 400
        
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
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
            
            # Check if user already exists (from session)
            existing_user_id = session.get('existing_user_id')
            if existing_user_id:
                # User exists but had no credentials - use existing user_id
                user_id = existing_user_id
                session.pop('existing_user_id', None)
            else:
                # New user - create account
                user_id = create_user(email)
            
            # Add credential with rp_id
            add_credential_to_user(user_id, {
                'credential_id': verification.credential_id,
                'public_key': verification.credential_public_key,
                'counter': verification.sign_count
            }, rp_id=expected_rp_id)
            
            # Send verification email
            try:
                from ..db import users_collection
            except ImportError:
                from db import users_collection
            
            try:
                from bson import ObjectId
                user_doc = users_collection.find_one({'_id': ObjectId(user_id)}) if users_collection else None
                if user_doc:
                    token = user_doc.get('verification_token')
                    if token:
                        send_verification_email(email, token)
            except Exception as e:
                print(f"Warning: Failed to send verification email: {e}")
            
            session['user_id'] = user_id
            session['email'] = email
            session.permanent = True
            session.pop('registration', None)
            session.pop('registration_email', None)
            session.pop('challenge', None)
            
            # Redirect to verification pending page
            return jsonify({'success': True, 'redirect': url_for('auth.verify_pending')})
        except Exception as e:
            import traceback
            return jsonify({'error': f'Verification failed: {str(e)}\n{traceback.format_exc()}'}), 400
            
    except Exception as e:
        import traceback
        return jsonify({'error': str(e) + '\n' + traceback.format_exc()}), 500


@bp.route('/api/login/begin', methods=['POST'])
def login_begin():
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


@bp.route('/api/login/complete', methods=['POST'])
def login_complete():
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


@bp.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('auth.login'))


@bp.route('/verify-pending')
def verify_pending():
    """Verification pending page - shown when user is not verified"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    email = session.get('email', '')
    
    # If already verified, redirect to dashboard
    try:
        if is_user_verified(user_id):
            return redirect(url_for('page.dashboard'))
    except Exception:
        pass
    
    return render_template('verify_pending.html', email=email)


@bp.route('/api/verify-email/send', methods=['POST'])
def send_verification_email_api():
    """Send verification email (resend functionality)"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    email = session.get('email')
    
    if not email:
        email = get_email_by_user_id(user_id)
    
    if not email:
        return jsonify({'error': 'Email not found'}), 404
    
    try:
        # Generate new token
        token = generate_verification_token(user_id)
        send_verification_email(email, token)
        return jsonify({'success': True, 'message': 'Verification email sent'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/verify-email/<token>')
def verify_email_token(token):
    """Verify email with token (GET endpoint for email links)"""
    if 'user_id' not in session:
        # Try to find user by token
        try:
            from bson import ObjectId
            try:
                from ..db import users_collection
            except ImportError:
                from db import users_collection
            
            if users_collection:
                user_doc = users_collection.find_one({'verification_token': token})
                if user_doc:
                    user_id = str(user_doc['_id'])
                    if verify_user_email(user_id, token):
                        # Set session and redirect
                        session['user_id'] = user_id
                        session['email'] = user_doc.get('username', '')
                        session.permanent = True
                        return redirect(url_for('page.dashboard'))
        except Exception:
            pass
        
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    try:
        if verify_user_email(user_id, token):
            return redirect(url_for('page.dashboard'))
        else:
            return render_template('verify_pending.html', 
                                 email=session.get('email', ''),
                                 error='Invalid or expired verification token')
    except Exception as e:
        return render_template('verify_pending.html',
                             email=session.get('email', ''),
                             error=str(e))


@bp.route('/api/verify-email/verify', methods=['POST'])
def verify_email_api():
    """Verify email with token (POST endpoint for API calls)"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({'error': 'Token is required'}), 400
    
    try:
        if verify_user_email(user_id, token):
            return jsonify({'success': True, 'message': 'Email verified'})
        else:
            return jsonify({'error': 'Invalid or expired token'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/passkeys', methods=['GET'])
def list_passkeys():
    """List all passkeys for current user"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    
    try:
        credentials = load_credentials_by_user_id(user_id, rp_id=None)
        
        if not credentials:
            return jsonify({'passkeys': []})
        
        # Convert to list if single credential (backward compatibility)
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


@bp.route('/api/passkeys/add', methods=['POST'])
def add_passkey_begin():
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


@bp.route('/api/passkeys/add/complete', methods=['POST'])
def add_passkey_complete():
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


@bp.route('/api/passkeys/<credential_id>', methods=['DELETE'])
def delete_passkey(credential_id):
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
    """Send login link via email"""
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
        
        # Check if user exists
        user_id = get_user_by_email(email)
        if not user_id:
            return jsonify({'error': 'User not found'}), 404
        
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


@bp.route('/api/login/email/<token>')
def verify_login_email_token(token):
    """Verify login email token and log user in"""
    try:
        # Find user by login token
        try:
            from ..db import users_collection
        except ImportError:
            from db import users_collection
        
        from bson import ObjectId
        
        if users_collection is None:
            return redirect(url_for('auth.login'))
        
        user_doc = users_collection.find_one({'login_token': token})
        if not user_doc:
            return render_template('login.html', error='Invalid or expired login link')
        
        user_id = str(user_doc['_id'])
        email = user_doc.get('username', '')
        
        # Verify token
        if not verify_login_token(user_id, token):
            return render_template('login.html', error='Invalid or expired login link')
        
        # Check if email is verified
        if not is_user_verified(user_id):
            # Set session and redirect to verification pending
            session['user_id'] = user_id
            session['email'] = email
            session.permanent = True
            return redirect(url_for('auth.verify_pending'))
        
        # Log user in
        session['user_id'] = user_id
        session['email'] = email
        session.permanent = True
        
        # Check if user has credentials for current domain
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
        user_credential = load_credentials_by_user_id(user_id, rp_id=rp_id)
        
        if not user_credential:
            # User logged in but has no passkey for this domain - redirect to account to add one
            # Set a flag in session to show message about adding passkey
            session['needs_passkey_for_domain'] = True
            return redirect(url_for('page.account'))
        
        # User has passkey, redirect to dashboard
        return redirect(url_for('page.dashboard'))
        
    except Exception as e:
        import traceback
        print(f"Error verifying login token: {traceback.format_exc()}")
        return render_template('login.html', error='An error occurred. Please try again.')

