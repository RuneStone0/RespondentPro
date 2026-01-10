#!/usr/bin/env python3
"""
Entry point for Respondent.io Web UI
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
load_dotenv(Path(__file__).parent / '.env')

from web.app import app

if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.run(debug=debug, host=host, port=port)

