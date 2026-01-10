/**
 * Firebase Auth client-side authentication
 * Handles user authentication using Firebase Auth SDK
 */

// Firebase Auth instance (initialized after config is loaded)
let auth = null;
let currentUser = null;

/**
 * Set ID token cookie - minimal implementation, let Firebase handle token refresh
 * @param {Object} user - Firebase user object
 */
async function setIdTokenCookie(user) {
    try {
        // Get token - Firebase handles caching and automatic refresh
        const idToken = await user.getIdToken();
        
        // Simple cookie setting - let browser handle defaults where possible
        const isSecure = window.location.protocol === 'https:';
        const cookieOptions = isSecure 
            ? 'path=/; SameSite=None; Secure'
            : 'path=/; SameSite=Lax';
        
        document.cookie = `firebase_id_token=${idToken}; ${cookieOptions}`;
    } catch (error) {
        console.error('Error setting token cookie:', error);
    }
}

/**
 * Clear ID token cookie
 */
function clearIdTokenCookie() {
    document.cookie = 'firebase_id_token=; path=/; max-age=0';
}

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
        
        // Use Firebase's native token change listener - fires on token refresh too
        auth.onIdTokenChanged(async (user) => {
            currentUser = user;
            if (user) {
                // Token changed (including automatic refresh) - update cookie
                await setIdTokenCookie(user);
            } else {
                // User signed out - clear cookie
                clearIdTokenCookie();
            }
        });
        
        // Set initial cookie if user is already signed in
        if (auth.currentUser) {
            currentUser = auth.currentUser;
            setIdTokenCookie(auth.currentUser);
        }
        
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
        // Firebase automatically signs the user in
        currentUser = userCredential.user;
        
        // Explicitly set cookie immediately (don't wait for onIdTokenChanged)
        await setIdTokenCookie(userCredential.user);
        
        // Send email verification
        await userCredential.user.sendEmailVerification();
        
        console.log('Sign up successful, cookie set');
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
        currentUser = userCredential.user;
        
        // Explicitly set cookie immediately (don't wait for onIdTokenChanged)
        // This ensures cookie is set before any redirect happens
        await setIdTokenCookie(userCredential.user);
        
        console.log('Sign in successful, cookie set');
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
        // For local development, always use http:// not https:// to avoid HTTPS redirects
        // Firebase Auth will handle the email link and redirect to this URL
        let continueUrl = window.location.origin + '/about';
        
        // For localhost, always force http:// (never https://) to prevent HTTPS redirects
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            continueUrl = 'http://' + window.location.host + '/about';
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
            currentUser = userCredential.user;
            
            // Explicitly set cookie immediately
            await setIdTokenCookie(userCredential.user);
            
            console.log('Email link sign in successful, cookie set');
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
        currentUser = null;
        clearIdTokenCookie();
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
    // Update currentUser from auth.currentUser if it's different
    if (auth && auth.currentUser !== currentUser) {
        currentUser = auth.currentUser;
    }
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
