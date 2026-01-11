#!/usr/bin/env python3
"""
Centralized configuration management for app_config.json
Handles loading and accessing application configuration values.
"""

import json
import logging
from pathlib import Path

# Create logger for this module
logger = logging.getLogger(__name__)

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
APP_CONFIG_PATH = PROJECT_ROOT / 'app_config.json'

# Cache for the loaded config
_config_cache = None


def get_app_config(reload=False):
    """
    Load and return the application configuration from app_config.json
    
    Args:
        reload: If True, force reload from file (default: False, uses cache)
    
    Returns:
        dict: Configuration dictionary, empty dict if file doesn't exist or can't be loaded
    """
    global _config_cache
    
    if _config_cache is None or reload:
        try:
            if APP_CONFIG_PATH.exists():
                with open(APP_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    _config_cache = json.load(f)
                    logger.debug(f"Loaded app config from {APP_CONFIG_PATH}")
            else:
                logger.warning(f"app_config.json not found at {APP_CONFIG_PATH}")
                _config_cache = {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse app_config.json: {e}")
            _config_cache = {}
        except Exception as e:
            logger.warning(f"Could not load app_config.json: {e}")
            _config_cache = {}
    
    return _config_cache.copy() if _config_cache else {}


def get_config_value(key, default=None, section=None):
    """
    Get a configuration value from app_config.json
    
    Args:
        key: The configuration key to retrieve
        default: Default value if key is not found
        section: Optional section name (e.g., 'firebase') to look within
    
    Returns:
        The configuration value or default if not found
    
    Examples:
        get_config_value('support-email')
        get_config_value('apiKey', section='firebase')
    """
    config = get_app_config()
    
    if section:
        section_config = config.get(section, {})
        return section_config.get(key, default)
    
    return config.get(key, default)


def get_firebase_config():
    """
    Get Firebase configuration from app_config.json
    
    Returns:
        dict: Firebase configuration dictionary
    """
    config = get_app_config()
    return config.get('firebase', {})


def reload_config():
    """
    Force reload of configuration from file (clears cache)
    """
    global _config_cache
    _config_cache = None
    return get_app_config(reload=True)
