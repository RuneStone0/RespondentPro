/* ============================================
   Base64URL Conversion Helpers
   ============================================ */

/**
 * Convert base64url string to Uint8Array
 * Used for WebAuthn credential handling
 */
function base64urlToUint8Array(base64url) {
    if (base64url === undefined || base64url === null) {
        throw new Error('base64url value is undefined or null');
    }
    
    // If it's already a Uint8Array, return it
    if (base64url instanceof Uint8Array) {
        return base64url;
    }
    
    // If it's an array, convert to Uint8Array
    if (Array.isArray(base64url)) {
        return new Uint8Array(base64url);
    }
    
    // Convert to string if it's not already
    const str = String(base64url);
    
    if (!str || str.length === 0) {
        throw new Error('base64url string is empty');
    }
    
    // Convert base64url to base64
    let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
    // Add padding if needed
    while (base64.length % 4) {
        base64 += '=';
    }
    // Decode base64
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
}

/**
 * Convert Uint8Array to base64url string
 * Used for WebAuthn credential handling
 */
function uint8ArrayToBase64url(bytes) {
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    let base64 = btoa(binary);
    // Convert base64 to base64url
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

/* ============================================
   Message Display Helpers
   ============================================ */

/**
 * Show error message
 */
function showError(message) {
    const errorEl = document.getElementById('error');
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.add('show');
        const successEl = document.getElementById('success');
        if (successEl) {
            successEl.classList.remove('show');
        }
    }
}

/**
 * Show success message
 */
function showSuccess(message) {
    const successEl = document.getElementById('success');
    if (successEl) {
        successEl.textContent = message;
        successEl.classList.add('show');
        const errorEl = document.getElementById('error');
        if (errorEl) {
            errorEl.classList.remove('show');
        }
    }
}

/**
 * Hide all messages
 */
function hideMessage() {
    const errorEl = document.getElementById('error');
    const successEl = document.getElementById('success');
    if (errorEl) errorEl.classList.remove('show');
    if (successEl) successEl.classList.remove('show');
}

/* ============================================
   Theme Management
   ============================================ */
/**
 * Load theme based on browser preferences
 * Uses prefers-color-scheme media query to respect system settings
 */
function loadTheme() {
    // Check if user has a saved preference (for backwards compatibility)
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme) {
        // If there's a saved theme, use it (but we'll respect browser preference going forward)
        document.documentElement.setAttribute('data-theme', savedTheme);
        // Clear the saved theme so browser preference takes over next time
        localStorage.removeItem('theme');
    } else {
        // Use browser preference
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = prefersDark ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
    }
    
    // Listen for changes to browser preference
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', (e) => {
        const theme = e.matches ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
    });
}

// Auto-load theme when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadTheme);
} else {
    loadTheme();
}

/* ============================================
   Modal Management
   ============================================ */

/**
 * Open the Learn More modal
 */
function openLearnMoreModal() {
    const modal = document.getElementById('learnMoreModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        // Focus on close button for accessibility
        const closeBtn = modal.querySelector('.btn-close-modal');
        if (closeBtn) {
            setTimeout(() => closeBtn.focus(), 100);
        }
    }
}

/**
 * Close the Learn More modal
 */
function closeLearnMoreModal() {
    const modal = document.getElementById('learnMoreModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('learnMoreModal');
        if (modal && modal.style.display === 'flex') {
            closeLearnMoreModal();
        }
    }
});
