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
# - MONGODB_URI: Your MongoDB connection string (default: mongodb://localhost:27017/)
# - MONGODB_DB: Your MongoDB database name (default: respondent_manager)
```

### MongoDB Atlas Setup (if using cloud MongoDB)

If you're using MongoDB Atlas, ensure:

1. **Database User Permissions**: Your database user must have the `readWrite` role on the database
   - Go to Atlas → Database Access → Edit your user
   - Under "Database User Privileges", add Built-in Role: `readWrite`
   - Select your database name

2. **Network Access**: Whitelist your IP address
   - Go to Atlas → Network Access → Add IP Address
   - Add your current IP or use `0.0.0.0/0` for development (not recommended for production)

3. **Connection String**: Use the format:
   ```
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
   ```
   Replace `username`, `password`, and `cluster` with your Atlas credentials.

## Web UI Usage

### Starting the Web Server

```bash
python web.py
```

The web interface will be available at `http://localhost:5000`

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
