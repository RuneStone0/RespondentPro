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
 * Toggle between light and dark theme
 */
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
}

/**
 * Update theme icon based on current theme
 */
function updateThemeIcon(theme) {
    const icon = document.getElementById('theme-icon');
    if (icon) {
        if (theme === 'dark') {
            // Moon icon for dark mode
            icon.innerHTML = '<path d="M9.528 1.718a.75.75 0 01.162.819A8.97 8.97 0 009 6a9 9 0 009 9 8.97 8.97 0 003.463-.69.75.75 0 01.981.98 10.503 10.503 0 01-9.694 6.46c-5.799 0-10.5-4.701-10.5-10.5 0-4.368 2.667-8.112 6.46-9.694a.75.75 0 01.818.162z"/>';
        } else {
            // Sun icon for light mode
            icon.innerHTML = '<path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59zM21.75 12a.75.75 0 01-.75.75h-2.25a.75.75 0 010-1.5H21a.75.75 0 01.75.75zM17.834 18.894a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 10-1.061 1.06l1.59 1.591zM12 18a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-2.25A.75.75 0 0112 18zM7.758 17.303a.75.75 0 00-1.061-1.06l-1.591 1.59a.75.75 0 001.06 1.061l1.591-1.59zM6 12a.75.75 0 01-.75.75H3a.75.75 0 010-1.5h2.25A.75.75 0 016 12zM6.697 7.757a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 00-1.061 1.06l1.59 1.591z"/>';
        }
    }
}

/**
 * Load saved theme from localStorage
 * Should be called on page load
 */
function loadTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

// Auto-load theme when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadTheme);
} else {
    loadTheme();
}

