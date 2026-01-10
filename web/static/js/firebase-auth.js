/**
 * Firebase Auth client-side authentication
 * Handles user authentication using Firebase Auth SDK
 */

// Firebase Auth instance (initialized after config is loaded)
let auth = null;
let currentUser = null;

/**
 * Initialize Firebase Auth with configuration
 * @param {Object} config - Firebase configuration object
 */
function initFirebaseAuth(config) {
    if (!config || !config.apiKey) {
        console.error('Firebase config is missing or invalid');
        return false;
    }
    
    try {
        // Initialize Firebase if not already initialized
        if (!window.firebase || !window.firebase.apps || window.firebase.apps.length === 0) {
            firebase.initializeApp(config);
        }
        
        auth = firebase.auth();
        
        // Set up auth state observer
        auth.onAuthStateChanged(async (user) => {
            currentUser = user;
            if (user) {
                // User is signed in
                console.log('User signed in:', user.email);
                // Store ID token in cookie for backend requests
                try {
                    const idToken = await user.getIdToken();
                    // Set cookie with ID token
                    // Add Secure flag if using HTTPS
                    const isSecure = window.location.protocol === 'https:';
                    const cookieOptions = `path=/; max-age=3600; SameSite=Lax${isSecure ? '; Secure' : ''}`;
                    document.cookie = `firebase_id_token=${idToken}; ${cookieOptions}`;
                    
                    // Set up periodic token refresh (every 50 minutes, before 1 hour expiry)
                    // Clear any existing interval first
                    if (window._tokenRefreshInterval) {
                        clearInterval(window._tokenRefreshInterval);
                    }
                    window._tokenRefreshInterval = setInterval(async () => {
                        try {
                            const refreshedToken = await user.getIdToken(true); // Force refresh
                            const refreshedCookieOptions = `path=/; max-age=3600; SameSite=Lax${isSecure ? '; Secure' : ''}`;
                            document.cookie = `firebase_id_token=${refreshedToken}; ${refreshedCookieOptions}`;
                            console.log('Token refreshed automatically');
                        } catch (error) {
                            console.error('Error refreshing token:', error);
                        }
                    }, 50 * 60 * 1000); // 50 minutes
                } catch (error) {
                    console.error('Error getting ID token:', error);
                }
            } else {
                // User is signed out
                console.log('User signed out');
                // Clear token refresh interval
                if (window._tokenRefreshInterval) {
                    clearInterval(window._tokenRefreshInterval);
                    window._tokenRefreshInterval = null;
                }
                // Remove cookie
                document.cookie = 'firebase_id_token=; path=/; max-age=0';
            }
        });
        
        return true;
    } catch (error) {
        console.error('Error initializing Firebase Auth:', error);
        return false;
    }
}

/**
 * Sign up a new user with email and password
 * @param {string} email - User email
 * @param {string} password - User password
 * @returns {Promise} - Promise that resolves with user credential
 */
async function signUpWithEmail(email, password) {
    if (!auth) {
        throw new Error('Firebase Auth not initialized');
    }
    
    try {
        const userCredential = await auth.createUserWithEmailAndPassword(email, password);
        // Note: createUserWithEmailAndPassword automatically signs the user in
        // Send email verification
        await userCredential.user.sendEmailVerification();
        // Set ID token cookie (user is already signed in)
        const idToken = await userCredential.user.getIdToken();
        const isSecure = window.location.protocol === 'https:';
        const cookieOptions = `path=/; max-age=3600; SameSite=Lax${isSecure ? '; Secure' : ''}`;
        document.cookie = `firebase_id_token=${idToken}; ${cookieOptions}`;
        return userCredential;
    } catch (error) {
        console.error('Error signing up:', error);
        throw error;
    }
}

/**
 * Sign in with email and password
 * @param {string} email - User email
 * @param {string} password - User password
 * @returns {Promise} - Promise that resolves with user credential
 */
async function signInWithEmail(email, password) {
    if (!auth) {
        throw new Error('Firebase Auth not initialized');
    }
    
    try {
        const userCredential = await auth.signInWithEmailAndPassword(email, password);
        // Update ID token cookie
        const idToken = await userCredential.user.getIdToken();
        const isSecure = window.location.protocol === 'https:';
        const cookieOptions = `path=/; max-age=3600; SameSite=Lax${isSecure ? '; Secure' : ''}`;
        document.cookie = `firebase_id_token=${idToken}; ${cookieOptions}`;
        return userCredential;
    } catch (error) {
        console.error('Error signing in:', error);
        throw error;
    }
}

/**
 * Sign in with email link (passwordless)
 * @param {string} email - User email
 * @returns {Promise} - Promise that resolves when email is sent
 */
async function signInWithEmailLink(email) {
    if (!auth) {
        throw new Error('Firebase Auth not initialized');
    }
    
    try {
        // Use the current origin for the continue URL
        // For local development, ensure we use http:// not https://
        // Firebase Auth will handle the email link and redirect to this URL
        let continueUrl = window.location.origin + '/about';
        
        // For localhost, always use http:// (not https://) unless we're actually on HTTPS
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            if (window.location.protocol === 'http:') {
                continueUrl = 'http://' + window.location.host + '/about';
            }
        }
        
        const actionCodeSettings = {
            url: continueUrl,
            handleCodeInApp: true,
        };
        
        await auth.sendSignInLinkToEmail(email, actionCodeSettings);
        // Store email in localStorage for verification when user clicks the link
        window.localStorage.setItem('emailForSignIn', email);
        return true;
    } catch (error) {
        console.error('Error sending sign-in link:', error);
        throw error;
    }
}

/**
 * Complete sign in with email link
 * @param {string} email - User email
 * @param {string} emailLink - The link from the email
 * @returns {Promise} - Promise that resolves with user credential
 */
async function signInWithEmailLinkComplete(email, emailLink) {
    if (!auth) {
        throw new Error('Firebase Auth not initialized');
    }
    
    try {
        if (auth.isSignInWithEmailLink(emailLink)) {
            const userCredential = await auth.signInWithEmailLink(email, emailLink);
            // Clear email from localStorage
            window.localStorage.removeItem('emailForSignIn');
            // Update ID token cookie
            const idToken = await userCredential.user.getIdToken();
            const isSecure = window.location.protocol === 'https:';
            const cookieOptions = `path=/; max-age=3600; SameSite=Lax${isSecure ? '; Secure' : ''}`;
            document.cookie = `firebase_id_token=${idToken}; ${cookieOptions}`;
            return userCredential;
        } else {
            throw new Error('Invalid email link');
        }
    } catch (error) {
        console.error('Error completing sign-in:', error);
        throw error;
    }
}

/**
 * Sign out current user
 * @returns {Promise} - Promise that resolves when sign out is complete
 */
async function signOut() {
    if (!auth) {
        throw new Error('Firebase Auth not initialized');
    }
    
    try {
        await auth.signOut();
        // Remove cookie
        document.cookie = 'firebase_id_token=; path=/; max-age=0';
        return true;
    } catch (error) {
        console.error('Error signing out:', error);
        throw error;
    }
}

/**
 * Get current user
 * @returns {Object|null} - Current user or null
 */
function getCurrentUser() {
    return currentUser || (auth ? auth.currentUser : null);
}

/**
 * Get current user's ID token
 * @returns {Promise<string>} - Promise that resolves with ID token
 */
async function getIdToken() {
    const user = getCurrentUser();
    if (!user) {
        throw new Error('No user signed in');
    }
    return await user.getIdToken();
}

/**
 * Send password reset email
 * @param {string} email - User email
 * @returns {Promise} - Promise that resolves when email is sent
 */
async function sendPasswordResetEmail(email) {
    if (!auth) {
        throw new Error('Firebase Auth not initialized');
    }
    
    try {
        await auth.sendPasswordResetEmail(email);
        return true;
    } catch (error) {
        console.error('Error sending password reset email:', error);
        throw error;
    }
}

/**
 * Re-authenticate user (required for sensitive operations)
 * @param {string} password - User password
 * @returns {Promise} - Promise that resolves with user credential
 */
async function reauthenticateUser(password) {
    const user = getCurrentUser();
    if (!user || !user.email) {
        throw new Error('No user signed in');
    }
    
    const credential = firebase.auth.EmailAuthProvider.credential(user.email, password);
    return await user.reauthenticateWithCredential(credential);
}

/**
 * Update user password
 * @param {string} newPassword - New password
 * @returns {Promise} - Promise that resolves when password is updated
 */
async function updatePassword(newPassword) {
    const user = getCurrentUser();
    if (!user) {
        throw new Error('No user signed in');
    }
    
    try {
        await user.updatePassword(newPassword);
        return true;
    } catch (error) {
        console.error('Error updating password:', error);
        throw error;
    }
}

/**
 * Set up passkey (WebAuthn) as multi-factor authentication
 * Note: This requires Firebase Auth with MFA enabled
 * @returns {Promise} - Promise that resolves when passkey is enrolled
 */
async function enrollPasskey() {
    const user = getCurrentUser();
    if (!user) {
        throw new Error('No user signed in');
    }
    
    try {
        // Get multi-factor session
        const multiFactorSession = await user.multiFactor.getSession();
        
        // Enroll passkey as second factor
        // Note: This is a simplified version - actual implementation depends on Firebase Auth MFA setup
        const multiFactorAssertion = await navigator.credentials.create({
            publicKey: {
                challenge: new Uint8Array(32),
                rp: {
                    name: 'Respondent Pro',
                    id: window.location.hostname
                },
                user: {
                    id: new TextEncoder().encode(user.uid),
                    name: user.email,
                    displayName: user.email
                },
                pubKeyCredParams: [{ alg: -7, type: 'public-key' }],
                authenticatorSelection: {
                    authenticatorAttachment: 'platform',
                    userVerification: 'required'
                }
            }
        });
        
        // Enroll the passkey
        const multiFactorInfo = await user.multiFactor.enroll(multiFactorAssertion, 'Passkey');
        return multiFactorInfo;
    } catch (error) {
        console.error('Error enrolling passkey:', error);
        throw error;
    }
}

// Export functions for use in other scripts
window.firebaseAuth = {
    init: initFirebaseAuth,
    signUp: signUpWithEmail,
    signIn: signInWithEmail,
    signInWithLink: signInWithEmailLink,
    signInWithLinkComplete: signInWithEmailLinkComplete,
    completeSignInWithEmailLink: signInWithEmailLinkComplete, // Alias for consistency
    signOut: signOut,
    getCurrentUser: getCurrentUser,
    getIdToken: getIdToken,
    sendPasswordReset: sendPasswordResetEmail,
    reauthenticate: reauthenticateUser,
    updatePassword: updatePassword,
    enrollPasskey: enrollPasskey,
    getAuth: () => auth,
    isInitialized: () => auth !== null && typeof auth !== 'undefined'
};
