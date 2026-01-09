"""
Cloud Function for scheduled notifications
Triggered by Cloud Scheduler
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from functions_framework import http
from web.notification_scheduler import check_and_send_weekly_notifications, check_and_send_token_expiration_notifications


@http
def scheduled_notifications(request):
    """Cloud Function triggered by Cloud Scheduler for notifications"""
    try:
        # Check weekly notifications
        check_and_send_weekly_notifications()
        
        # Check token expiration notifications
        check_and_send_token_expiration_notifications()
        
        return {'status': 'success', 'message': 'Notifications checked'}, 200
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500
