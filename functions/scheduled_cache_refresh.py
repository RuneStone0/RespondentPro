"""
Cloud Function for scheduled cache refresh
Triggered by Cloud Scheduler
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from functions_framework import http
from web.cache_refresh import refresh_stale_caches


@http
def scheduled_cache_refresh(request):
    """Cloud Function triggered by Cloud Scheduler for cache refresh"""
    try:
        # Refresh stale caches (default max age: 24 hours)
        refresh_stale_caches(max_age_hours=24)
        
        return {'status': 'success', 'message': 'Cache refresh completed'}, 200
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500
