# Local Testing Guide

## Overview

This is a **Flask application**, not a static site. HTML pages are served dynamically through Flask routes and templates, not as static files. That's why there's no `index.html` in `web/static/` - the HTML templates are in `web/templates/` and are rendered by Flask.

## Method 1: Run Flask App Directly (Recommended for Development)

This is the simplest way to test locally:

```bash
# Make sure you're in the project root
cd /home/RuneStone0/RespondentPro

# Activate virtual environment (if using one)
source .venv/bin/activate

# Run the Flask app
python web.py
```

The app will be available at:
- **http://localhost:5000**

## Method 2: Test Cloud Function Locally

To test how the app will run in Cloud Functions:

```bash
cd /home/RuneStone0/RespondentPro/functions

# Test with functions-framework
functions-framework --target=main.respondentpro --port=8080
```

The app will be available at:
- **http://localhost:8080**

## Method 3: Use Firebase Emulators

For a more complete Firebase environment:

```bash
# Install Firebase emulators (if not already installed)
npm install -g firebase-tools

# Start emulators
firebase emulators:start

# Or start specific emulators
firebase emulators:start --only functions,firestore
```

## Environment Setup

Make sure your `.env` file is configured:

```bash
# Copy example if needed
cp .env.example .env

# Edit .env with your settings:
# - FIREBASE_PROJECT_ID
# - GOOGLE_APPLICATION_CREDENTIALS (path to service account JSON)
# - SECRET_KEY
# - SMTP settings
# - etc.
```

## Static Files Explanation

**Why no `index.html` in `web/static/`?**

- `web/static/` contains: CSS, JavaScript, images, fonts (static assets)
- `web/templates/` contains: HTML templates (rendered by Flask)
- Flask serves templates dynamically through routes defined in `web/routes/`

**File Structure:**
```
web/
├── static/          # Static assets (CSS, JS, images)
│   ├── css/
│   ├── js/
│   └── img/
├── templates/       # HTML templates (Flask renders these)
│   ├── base.html
│   ├── dashboard.html
│   ├── login.html
│   └── ...
└── routes/         # Flask routes (define URLs)
    ├── page_routes.py
    ├── api_routes.py
    └── auth_routes.py
```

## Testing Different Routes

Once the app is running, you can access:

- **Home/Dashboard**: http://localhost:5000/
- **Login**: http://localhost:5000/login
- **Register**: http://localhost:5000/register
- **Account**: http://localhost:5000/account
- **API endpoints**: http://localhost:5000/api/...

## Troubleshooting

### Port Already in Use

```bash
# Use a different port
PORT=5001 python web.py
```

### Firestore Connection Issues

```bash
# Quick test Firestore connection
python -c "from web.db import firestore_available; print('Available:', firestore_available)"

# Or use the comprehensive test script
python test_firebase_init.py

# Or use the quick test script
python test_firebase_quick.py                    # Test local environment
python test_firebase_quick.py --cloud            # Test cloud environment (simulated)
python test_firebase_quick.py --cloud --creds    # Test cloud with GOOGLE_APPLICATION_CREDENTIALS set
python test_firebase_quick.py --debug            # Enable debug logging
```

### Import Errors

```bash
# Make sure you're in the project root
cd /home/RuneStone0/RespondentPro

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Testing Firebase Initialization Locally

### Quick Test Script

Test Firebase initialization without deploying:

```bash
# Test local environment (uses GOOGLE_APPLICATION_CREDENTIALS from .env)
python test_firebase_quick.py

# Test cloud environment simulation (simulates GCP_PROJECT)
python test_firebase_quick.py --cloud

# Test cloud environment with GOOGLE_APPLICATION_CREDENTIALS set (tests unset logic)
python test_firebase_quick.py --cloud --creds

# Enable debug logging for detailed output
python test_firebase_quick.py --debug
```

### Comprehensive Test Suite

Run all test scenarios:

```bash
python test_firebase_init.py
```

This will test:
1. Local environment with service account
2. Cloud environment (simulated)
3. Firestore connection through db.py

### Testing with functions-framework (Simulates Cloud Functions)

To test exactly how it will run in Cloud Functions:

```bash
# Set environment variables to simulate cloud
export GCP_PROJECT=respondentpro-xyz
export FUNCTION_NAME=respondentpro

# Run with functions-framework (from project root)
functions-framework --target=main.respondentpro --port=8080
```

Then test the endpoint:
```bash
curl http://localhost:8080/
```

## Development Tips

1. **Auto-reload**: Flask's dev server auto-reloads on code changes
2. **Debug mode**: Set `FLASK_DEBUG=True` in `.env` for detailed error pages
3. **Test before deploy**: Use `test_firebase_quick.py` to verify Firebase initialization before deploying

## Next Steps

After testing locally:
1. Fix any issues
2. Deploy to Firebase: `firebase deploy --only functions`
3. Deploy hosting: `firebase deploy --only hosting`
