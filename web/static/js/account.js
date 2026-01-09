/**
 * Account page JavaScript for passkey management
 */

function setButtonLoading(button, isLoading, text = null) {
    if (!button) return;
    
    if (isLoading) {
        button.disabled = true;
        button.classList.add('btn-loading');
        const btnText = button.querySelector('.btn-text');
        if (btnText) {
            if (text) {
                btnText.textContent = text;
            }
            // Add spinner if it doesn't exist
            if (!button.querySelector('.btn-spinner')) {
                const spinner = document.createElement('span');
                spinner.className = 'btn-spinner';
                button.insertBefore(spinner, btnText);
            }
        }
    } else {
        button.disabled = false;
        button.classList.remove('btn-loading');
        const spinner = button.querySelector('.btn-spinner');
        if (spinner) {
            spinner.remove();
        }
    }
}

async function addPasskey() {
    const button = document.getElementById('addPasskeyBtn');
    const errorMessage = document.getElementById('errorMessage');
    const successMessage = document.getElementById('successMessage');
    
    errorMessage.style.display = 'none';
    successMessage.style.display = 'none';
    setButtonLoading(button, true, 'Adding...');
    
    try {
        // Begin passkey registration
        const beginResponse = await fetch('/api/passkeys/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!beginResponse.ok) {
            const error = await beginResponse.json();
            throw new Error(error.error || 'Failed to begin passkey registration');
        }
        
        const options = await beginResponse.json();
        
        // Validate required fields
        if (!options.challenge) {
            throw new Error('Missing challenge in options');
        }
        
        // Convert options for WebAuthn API
        const publicKeyCredentialCreationOptions = {
            challenge: base64urlToUint8Array(options.challenge),
            rp: options.rp,
            user: {
                id: base64urlToUint8Array(options.user.id),
                name: options.user.name,
                displayName: options.user.displayName
            },
            pubKeyCredParams: options.pubKeyCredParams,
            authenticatorSelection: options.authenticatorSelection,
            timeout: options.timeout,
            attestation: options.attestation
        };
        
        // Create credential
        const credential = await navigator.credentials.create({
            publicKey: publicKeyCredentialCreationOptions
        });
        
        // Convert credential to format for server
        const credentialForServer = {
            id: credential.id,
            rawId: uint8ArrayToBase64url(new Uint8Array(credential.rawId)),
            type: credential.type,
            response: {
                clientDataJSON: uint8ArrayToBase64url(new Uint8Array(credential.response.clientDataJSON)),
                attestationObject: uint8ArrayToBase64url(new Uint8Array(credential.response.attestationObject))
            }
        };
        
        // Complete registration
        const completeResponse = await fetch('/api/passkeys/add/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: credentialForServer })
        });
        
        if (!completeResponse.ok) {
            const error = await completeResponse.json();
            throw new Error(error.error || 'Failed to complete passkey registration');
        }
        
        const result = await completeResponse.json();
        
        if (result.success) {
            successMessage.textContent = 'Passkey added successfully!';
            successMessage.style.display = 'block';
            // Reload page to show new passkey
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        }
    } catch (error) {
        errorMessage.textContent = 'Error: ' + error.message;
        errorMessage.style.display = 'block';
        console.error('Error adding passkey:', error);
    } finally {
        setButtonLoading(button, false);
        const btnText = button.querySelector('.btn-text');
        if (btnText) {
            btnText.textContent = 'Add Passkey';
        }
    }
}

async function deletePasskey(credentialId) {
    if (!confirm('Are you sure you want to delete this passkey? You will not be able to use it to log in anymore.')) {
        return;
    }
    
    const errorMessage = document.getElementById('errorMessage');
    const successMessage = document.getElementById('successMessage');
    
    errorMessage.style.display = 'none';
    successMessage.style.display = 'none';
    
    // Find the delete button for this passkey
    const passkeyElement = document.querySelector(`[data-credential-id="${credentialId}"]`);
    const deleteButton = passkeyElement ? passkeyElement.querySelector('button.delete-btn') : null;
    
    let originalText = 'Delete';
    if (deleteButton) {
        const btnText = deleteButton.querySelector('.btn-text');
        originalText = btnText ? btnText.textContent : deleteButton.textContent;
        setButtonLoading(deleteButton, true, 'Deleting...');
    }
    
    try {
        const response = await fetch(`/api/passkeys/${encodeURIComponent(credentialId)}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to delete passkey');
        }
        
        const result = await response.json();
        
        if (result.success) {
            successMessage.textContent = 'Passkey deleted successfully!';
            successMessage.style.display = 'block';
            // Reload page to update list
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        }
    } catch (error) {
        errorMessage.textContent = 'Error: ' + error.message;
        errorMessage.style.display = 'block';
        console.error('Error deleting passkey:', error);
    } finally {
        if (deleteButton) {
            setButtonLoading(deleteButton, false);
            const btnText = deleteButton.querySelector('.btn-text');
            if (btnText) {
                btnText.textContent = originalText;
            } else {
                deleteButton.textContent = originalText;
            }
        }
    }
}

// Helper functions for base64url encoding/decoding
function base64urlToUint8Array(base64url) {
    const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
    const padding = base64.length % 4 === 0 ? 0 : 4 - (base64.length % 4);
    const paddedBase64 = base64 + '='.repeat(padding);
    const binary = atob(paddedBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
}

function uint8ArrayToBase64url(bytes) {
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    const base64 = btoa(binary);
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}
