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
        user_exists, create_user, get_user_by_username,
        load_credentials_by_user_id, save_credentials_by_user_id
    )
except ImportError:
    from services.user_service import (
        user_exists, create_user, get_user_by_username,
        load_credentials_by_user_id, save_credentials_by_user_id
    )

bp = Blueprint('auth', __name__)


@bp.route('/')
def index():
    """Home page - redirect to login if not authenticated"""
    if 'user_id' in session:
        return redirect(url_for('page.dashboard'))
    return redirect(url_for('auth.login'))


@bp.route('/login')
def login():
    """Login page"""
    return render_template('login.html')


@bp.route('/api/register/begin', methods=['POST'])
def register_begin():
    """Begin passkey registration"""
    try:
        data = request.json
        username = data.get('username')
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        # Check if user already exists
        if user_exists(username):
            return jsonify({'error': 'Username already exists'}), 400
        
        # Generate registration options
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Respondent Pro",
            user_id=username.encode('utf-8'),
            user_name=username,
            user_display_name=username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
                user_verification=UserVerificationRequirement.PREFERRED
            )
        )
        
        session['challenge'] = base64.urlsafe_b64encode(options.challenge).decode('utf-8').rstrip('=')
        session['registration_username'] = username
        session['registration'] = True
        
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
        
        username = session.get('registration_username')
        challenge_b64 = session.get('challenge')
        
        if not username or not challenge_b64:
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
            
            origin = f"{request.scheme}://{request.host}"
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
            
            user_id = create_user(username)
            
            save_credentials_by_user_id(user_id, {
                'credential_id': verification.credential_id,
                'public_key': verification.credential_public_key,
                'counter': verification.sign_count
            })
            
            session['user_id'] = user_id
            session['username'] = username
            session.pop('registration', None)
            session.pop('registration_username', None)
            session.pop('challenge', None)
            
            return jsonify({'success': True, 'redirect': url_for('page.dashboard')})
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
        username = data.get('username')
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        user_id = get_user_by_username(username)
        if not user_id:
            return jsonify({'error': 'User not found'}), 404
        
        user_credential = load_credentials_by_user_id(user_id)
        if not user_credential:
            return jsonify({'error': 'No credentials found for user'}), 404
        
        hostname = request.host.split(':')[0]
        if hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
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
        session['login_username'] = username
        
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
        username = session.get('login_username')
        challenge_b64 = session.get('challenge')
        
        if not user_id or not challenge_b64:
            return jsonify({'error': 'Session expired'}), 400
        
        user_credential = load_credentials_by_user_id(user_id)
        if not user_credential:
            return jsonify({'error': 'No credentials found'}), 404
        
        data = request.json
        credential_data = data.get('credential')
        
        if not credential_data:
            return jsonify({'error': 'Credential is required'}), 400
        
        hostname = request.host.split(':')[0]
        if hostname == '127.0.0.1' or hostname == '0.0.0.0':
            rp_id = 'localhost'
        else:
            rp_id = hostname
        
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
                client_data_json=decode_base64(credential_data['response']['clientDataJSON']),
                authenticator_data=decode_base64(credential_data['response']['authenticatorData']),
                signature=decode_base64(credential_data['response']['signature']),
                user_handle=decode_base64(credential_data['response'].get('userHandle')) if credential_data['response'].get('userHandle') else None
            )
            
            credential = AuthenticationCredential(
                id=credential_data['id'],
                raw_id=decode_base64(credential_data['rawId']),
                response=authentication_response,
                type=credential_data.get('type', 'public-key')
            )
            
            origin = f"{request.scheme}://{request.host}"
            hostname = request.host.split(':')[0]
            if hostname == '0.0.0.0':
                expected_rp_id = 'localhost'
            else:
                expected_rp_id = hostname
            
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=expected_rp_id,
                expected_origin=origin,
                credential_public_key=user_credential['public_key'],
                credential_current_sign_count=user_credential.get('counter', 0)
            )
            
            # Update counter
            save_credentials_by_user_id(user_id, {
                'credential_id': user_credential['credential_id'],
                'public_key': user_credential['public_key'],
                'counter': verification.new_sign_count
            })
            
            session['user_id'] = user_id
            session['username'] = username
            session.pop('login_user_id', None)
            session.pop('login_username', None)
            session.pop('challenge', None)
            
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

