# Respondent.io Management Web UI

A modern web interface for managing your Respondent.io projects. Respondent.io is a research platform that connects companies with participants for paid studies, interviews, and surveys. This web application helps you efficiently manage and filter projects to find the best opportunities.

## Features

### Web UI
- **Passkey Authentication**: Secure login using WebAuthn passkeys (no passwords!)
- **Session Key Management**: Easy-to-use web interface to manage your Respondent.io session keys
- **Project Management**: Browse and filter projects with calculated hourly rates
- **Smart Filtering**: Automatically hide projects based on your criteria (incentive amount, hourly rate, research type, etc.)
- **Feedback System**: Track why you're hiding projects for better decision-making
- Modern, responsive web interface

## Installation

1. Clone or download this repository

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and set your configuration:
# - SECRET_KEY: Generate a secure key with: python -c "import secrets; print(secrets.token_hex(32))"
# - FIREBASE_PROJECT_ID: Your Firebase project ID
# - GOOGLE_APPLICATION_CREDENTIALS: Path to Firebase service account JSON file
```

### Firebase Setup

1. **Create Firebase Project**:
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Create a new project or select existing one
   - Note your Project ID

2. **Enable Firestore**:
   - Go to Firestore Database in Firebase Console
   - Create database in Native mode
   - Deploy indexes: `firebase deploy --only firestore:indexes`
   - Deploy security rules: `firebase deploy --only firestore:rules`

3. **Enable Firebase Authentication**:
   - Go to Authentication in Firebase Console
   - Enable Email/Password provider
   - Enable Passkey/WebAuthn (if available)
   - Add authorized domains

4. **Service Account**:
   - Go to Project Settings → Service Accounts
   - Generate new private key
   - Save the JSON file
   - Set `GOOGLE_APPLICATION_CREDENTIALS` in `.env` to the path of this file

5. **Deploy Firestore Indexes and Rules**:
   ```bash
   firebase deploy --only firestore
   ```

## Web UI Usage

### Starting the Web Server (Local Development)

```bash
python web.py
```

The web interface will be available at `http://localhost:5000`

### Deploying to Firebase

1. **Install Firebase CLI**:
   ```bash
   npm install -g firebase-tools
   firebase login
   ```

2. **Initialize Firebase** (if not already done):
   ```bash
   firebase init
   # Select: Firestore, Functions, Hosting
   ```

3. **Deploy**:
   ```bash
   firebase deploy
   ```

   Or deploy specific services:
   ```bash
   firebase deploy --only functions
   firebase deploy --only hosting
   firebase deploy --only firestore
   ```

### Migrating Data from MongoDB

If you have existing MongoDB data, use the migration script:

```bash
python scripts/migrate_mongodb_to_firestore.py
```

This will migrate all collections from MongoDB to Firestore.

### First Time Setup

1. **Register**: Click "Register" tab and choose a username
2. **Create Passkey**: Follow your browser's prompt to create a passkey (you can use your device's biometric authentication or security key)
3. **Add Session Keys**: After logging in, you'll be prompted to add your Respondent.io session keys

### Getting Your Session Keys

1. Log into respondent.io in your browser
2. Open Developer Tools (F12) → Network tab
3. Refresh the page or click around until you see requests to app.respondent.io
4. Click any request (e.g. one to `/api/v1/projects` or `/api/v1/me`)
5. In the Request Headers section, copy these values:
    - **Cookies**: Find `respondent.session.sid=`, copy the cookie name and value
    - **Authorization**: Copy the Bearer token (it looks like `Bearer eyJhbGciOi...`)
6. Paste values into the web interface

## Security Notes

- Keep your session cookies and authorization tokens secure
- Tokens expire periodically - you may need to refresh them
- Never commit your `.env` file to version control

## License

This project is provided as-is for personal use.
