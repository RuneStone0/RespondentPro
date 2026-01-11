#!/usr/bin/env python3
"""
Grok API service for centralized management of all Grok API interactions
"""

import os
import logging
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlparse

# Create logger for this module
logger = logging.getLogger(__name__)


def get_grok_config() -> Dict[str, Optional[str]]:
    """
    Get Grok API configuration from environment variables
    
    Returns:
        Dictionary with api_key and api_url
    """
    return {
        'api_key': os.environ.get('GROK_API_KEY'),
        'api_url': os.environ.get('GROK_API_URL', 'https://api.x.ai/v1/chat/completions')
    }


def call_grok_api(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: str = 'grok-4-1-fast-reasoning'
) -> Optional[str]:
    """
    Make a call to Grok API
    
    Args:
        prompt: User prompt
        system_prompt: Optional system prompt
        model: Grok model to use (default: 'grok-4-1-fast-reasoning')
        
    Returns:
        Response text or None if error
    """
    config = get_grok_config()
    api_key = config['api_key']
    api_url = config['api_url']
    
    if not api_key:
        logger.warning("GROK_API_KEY not set, skipping AI analysis")
        return None
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        
        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.3
        }
        
        logger.debug(f"POST {api_url}")
        logger.debug(f"Model: {model}, Messages: {len(messages)}")
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        # Log response details for debugging
        logger.debug(f"Response status: {response.status_code}")
        if not response.ok:
            error_text = response.text[:500] if response.text else "No response body"
            logger.error(f"Error response: {error_text}")
            logger.error(f"Full URL: {api_url}")
            logger.error(f"Request payload keys: {list(payload.keys())}")
            
            # If 404, suggest checking the endpoint URL
            if response.status_code == 404:
                logger.error("404 Error - Possible issues:")
                logger.error("  - Check if the API endpoint URL is correct")
                logger.error("  - Verify the model name is correct (try: grok-beta, grok-2, grok)")
                logger.error("  - Check xAI API documentation for the correct endpoint")
                logger.error("  - Ensure your API key has access to the Grok API")
        
        response.raise_for_status()
        
        data = response.json()
        return data.get('choices', [{}])[0].get('message', {}).get('content', '')
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error {e.response.status_code if e.response else 'unknown'}: {e.response.text[:500] if e.response else str(e)}"
        logger.error(f"Error: {error_msg}")
        logger.error(f"URL: {api_url}")
        logger.error(f"Model: {payload.get('model', 'unknown')}")
        return None
    except Exception as e:
        logger.error(f"Error calling Grok API: {e}", exc_info=True)
        logger.error(f"URL: {api_url}")
        return None


def check_grok_health() -> Dict[str, Any]:
    """
    Check Grok API health status
    
    Returns:
        Dictionary with status, api_key_configured, reachable, and error fields
    """
    grok_status = "healthy"
    grok_api_key_configured = False
    grok_reachable = False
    grok_error = None
    
    try:
        config = get_grok_config()
        api_key = config['api_key']
        api_url = config['api_url']
        
        if api_key:
            grok_api_key_configured = True
            
            # Perform a lightweight connectivity test with timeout
            # Test if we can reach the API domain (not making a full API call)
            try:
                parsed_url = urlparse(api_url)
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                
                # Make a simple HEAD request to check connectivity
                test_response = requests.head(
                    base_url,
                    timeout=2,
                    allow_redirects=True
                )
                # If we get any response (even 404/403), the service is reachable
                grok_reachable = True
            except requests.exceptions.Timeout:
                grok_error = "Connection timeout"
                grok_status = "degraded"
                grok_reachable = False
            except requests.exceptions.ConnectionError:
                grok_error = "Connection error - API unreachable"
                grok_status = "degraded"
                grok_reachable = False
            except Exception as e:
                # For other errors, assume reachable if we got past connection
                # (e.g., 403/404 means service is up but endpoint/auth issue)
                if "timeout" in str(e).lower() or "connection" in str(e).lower():
                    grok_reachable = False
                    grok_error = str(e)
                    grok_status = "degraded"
                else:
                    grok_reachable = True
        else:
            grok_error = "GROK_API_KEY not configured"
            grok_status = "degraded"
            # Grok is optional, so don't mark overall as unhealthy
    except Exception as e:
        grok_error = str(e)
        grok_status = "degraded"
        # Grok is optional, so don't mark overall as unhealthy
    
    return {
        'status': grok_status,
        'api_key_configured': grok_api_key_configured,
        'reachable': grok_reachable,
        'error': grok_error
    }
