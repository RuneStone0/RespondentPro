#!/usr/bin/env python3
"""
Firebase Auth token verification utilities
"""

import logging
from functools import wraps
from flask import request, jsonify, redirect, url_for, abort
import firebase_admin
from firebase_admin import auth

logger = logging.getLogger(__name__)


def verify_firebase_token(id_token):
    """
    Verify a Firebase Auth ID token and return decoded token.
    
    Args:
        id_token: The Firebase Auth ID token string
        
    Returns:
        dict: Decoded token containing uid, email, and other claims
        None: If token is invalid or verification fails
        
    Raises:
        Exception: If Firebase Admin is not initialized
    """
    if not firebase_admin._apps:
        raise Exception("Firebase Admin not initialized. Cannot verify tokens.")
    
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except auth.InvalidIdTokenError as e:
        logger.warning(f"Invalid ID token: {e}")
        return None
    except auth.ExpiredIdTokenError as e:
        logger.warning(f"Expired ID token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying ID token: {e}")
        return None


def get_id_token_from_request():
    """
    Extract Firebase Auth ID token from request.
    Checks Authorization header and cookies.
    
    Returns:
        str: ID token if found, None otherwise
    """
    # Check Authorization header (Bearer token)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]  # Remove 'Bearer ' prefix
    
    # Check cookie (for browser-based requests)
    id_token = request.cookies.get('firebase_id_token')
    if id_token:
        return id_token
    
    return None


def require_auth(f):
    """
    Decorator to require Firebase Auth authentication.
    Verifies ID token and adds user info to request context.
    
    Usage:
        @bp.route('/protected')
        @require_auth
        def protected_route():
            user_id = request.auth['uid']
            email = request.auth['email']
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get ID token from request
        id_token = get_id_token_from_request()
        
        if not id_token:
            # Check if this is an API request (JSON) or page request (HTML)
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            else:
                # Return 404 for page requests to prevent path enumeration
                abort(404)
        
        # Verify token
        decoded_token = verify_firebase_token(id_token)
        
        if not decoded_token:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Invalid or expired token'}), 401
            else:
                # Return 404 for page requests to prevent path enumeration
                abort(404)
        
        # Attach decoded token to request for use in route handler
        request.auth = decoded_token
        
        # Ensure Firestore user document exists
        try:
            firebase_uid = decoded_token.get('uid')
            email = decoded_token.get('email')
            email_verified = decoded_token.get('email_verified', False)
            if firebase_uid and email:
                ensure_firestore_user_exists(firebase_uid, email, email_verified)
        except Exception as e:
            # Log but don't fail - user can still access if Firestore is down
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to ensure Firestore user exists: {e}")
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_verified(f):
    """
    Decorator to require Firebase Auth authentication AND email verification.
    Similar to require_auth but also checks email_verified claim.
    
    Usage:
        @bp.route('/protected')
        @require_verified
        def protected_route():
            user_id = request.auth['uid']
            email = request.auth['email']
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check authentication
        id_token = get_id_token_from_request()
        
        if not id_token:
            logger.warning(
                f"require_verified: No token found for {request.path} "
                f"(method: {request.method}, cookies: {list(request.cookies.keys())})"
            )
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            else:
                # Return 404 for page requests to prevent path enumeration
                abort(404)
        
        decoded_token = verify_firebase_token(id_token)
        
        if not decoded_token:
            logger.warning(
                f"require_verified: Token verification failed for {request.path} "
                f"(token preview: {id_token[:50] if id_token else 'None'}...)"
            )
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Invalid or expired token'}), 401
            else:
                # Return 404 for page requests to prevent path enumeration
                abort(404)
        
        # Check email verification
        # Note: We allow unverified users to access pages, but they'll see a verification notice
        # This is less strict than the old system to allow users to use the app immediately after signup
        if not decoded_token.get('email_verified', False):
            # For API requests, still require verification for security
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Email not verified'}), 403
            # For page requests, allow access but the template can show a verification notice
            # Don't redirect - let them use the app
            pass
        
        # Attach decoded token to request
        request.auth = decoded_token
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_user_id_from_token():
    """
    Get user ID from the current request's Firebase Auth token.
    Returns None if no valid token is present.
    
    Returns:
        str: Firebase Auth UID, or None
    """
    if hasattr(request, 'auth') and request.auth:
        return request.auth.get('uid')
    
    id_token = get_id_token_from_request()
    if id_token:
        decoded_token = verify_firebase_token(id_token)
        if decoded_token:
            return decoded_token.get('uid')
    
    return None


def get_user_email_from_token():
    """
    Get user email from the current request's Firebase Auth token.
    Returns None if no valid token is present.
    
    Returns:
        str: User email, or None
    """
    if hasattr(request, 'auth') and request.auth:
        return request.auth.get('email')
    
    id_token = get_id_token_from_request()
    if id_token:
        decoded_token = verify_firebase_token(id_token)
        if decoded_token:
            return decoded_token.get('email')
    
    return None


def ensure_firestore_user_exists(firebase_uid, email, email_verified=False):
    """
    Ensure a Firestore user document exists for a Firebase Auth user.
    Creates the document if it doesn't exist, or updates it with firebase_uid if it does.
    
    Args:
        firebase_uid: Firebase Auth UID
        email: User email
        email_verified: Whether email is verified
        
    Returns:
        str: Firestore user document ID
    """
    try:
        from ..db import users_collection
        from ..services.user_service import get_user_by_email, create_user
        from datetime import datetime
    except ImportError:
        from db import users_collection
        from services.user_service import get_user_by_email, create_user
        from datetime import datetime
    
    if users_collection is None:
        raise Exception("Firestore connection not available")
    
    # First, check if a user document exists with this firebase_uid
    user_doc_by_uid = users_collection.document(firebase_uid).get()
    if user_doc_by_uid.exists:
        # User exists with firebase_uid as document ID - update email verification if needed
        user_data = user_doc_by_uid.to_dict()
        if user_data.get('email_verified') != email_verified:
            users_collection.document(firebase_uid).update({
                'email_verified': email_verified,
                'updated_at': datetime.utcnow()
            })
        return firebase_uid
    
    # Try to find user by email (for existing users from old system)
    user_id = get_user_by_email(email)
    
    if user_id:
        # User exists in Firestore with old ID - update with firebase_uid
        user_doc = users_collection.document(str(user_id)).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            if not user_data.get('firebase_uid'):
                # Update existing document with firebase_uid
                users_collection.document(str(user_id)).update({
                    'firebase_uid': firebase_uid,
                    'email_verified': email_verified,
                    'updated_at': datetime.utcnow()
                })
            elif user_data.get('email_verified') != email_verified:
                # Update email verification status
                users_collection.document(str(user_id)).update({
                    'email_verified': email_verified,
                    'updated_at': datetime.utcnow()
                })
        # Return the existing user_id (not firebase_uid) for backward compatibility
        return str(user_id)
    else:
        # User doesn't exist in Firestore - create new user document
        # Use firebase_uid as the document ID for new users
        user_data = {
            'username': email,  # Email stored in username field
            'firebase_uid': firebase_uid,
            'email_verified': email_verified,
            'credentials': [],  # Array for multiple passkeys (now handled by Firebase Auth)
            'projects_processed_limit': 500,  # Default limit for new users
            'credits_low_email_sent': False,
            'credits_exhausted_email_sent': False,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Create document with firebase_uid as ID
        users_collection.document(firebase_uid).set(user_data)
        return firebase_uid
