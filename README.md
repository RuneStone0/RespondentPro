# Respondent.io Management CLI

A lightweight, no-nonsense command-line tool for power users of Respondent.io.
Respondent.io is a research platform that connects companies with participants for paid studies, interviews, and surveys. Incentives can range from pocket change to serious money, but the catch? A ton of low-paying or super-long “$200 over 7 days” traps that waste your time.
This CLI fixes that.

With it you can:
* List all your active projects in one glance
* Instantly calculate real hourly rates (because $200 sounds nice until you realize it’s $200 for 10 hours of diary entries)
* Hide junk projects automatically — e.g. anything under $70 flat or below your desired hourly rate

Why bother? Because life’s too short to manually click “Not interested” on fifty $10 surveys. Save your brainpower for the gigs that actually pay the rent.

Quick Example
```
Bashrespondent hide --min-hourly 80    # bye-bye low-rate nonsense
respondent hide --min-incentive 70     # ignore anything under $70
respondent list --show-hourly          # see real rates at a glance
```

Light, fast, and mildly judgmental about bad incentives. Enjoy the extra free time (and money).

## Features

### Web UI (NEW!)
- **Passkey Authentication**: Secure login using WebAuthn passkeys (no passwords!)
- **Session Key Management**: Easy-to-use web interface to manage your Respondent.io session keys
- Modern, responsive web interface

### CLI Tool
- **Authentication**: Verify your authentication status with Respondent.io
- **List Projects**: Browse available projects with calculated hourly rates
- **Hide Projects**: Hide individual projects or filter and hide multiple projects by:
  - Project ID
  - Hourly rate threshold
  - Total incentive threshold

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
python respondent_web.py
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

### CLI Tool - Getting Your Credentials

1. Log into respondent.io in your browser
2. Open Developer Tools (F12) → Network tab
3. Refresh the page or click around until you see requests to app.respondent.io
4. Click any request (e.g. one to `/api/v1/projects` or `/api/v1/me`)
5. In the Request Headers section, copy these two values:
    - cookie: find respondent.session.sid=, copy the whole thing (just the value after = is enough if you prefer)
    - authorization: copy the Bearer token (it looks like `Bearer eyJhbGciOi...`)
6. Paste values into `config.json`

## Usage

### CLI Tool

```bash
# Test your authentication status
python respondent_cli.py auth

# List projects
python respondent_cli.py projects

# Hide a single project by ID:
python respondent_cli.py hide --id 692f1ffb607b02364a3c37d6

# Hide all projects with an hourly rate lower than the specified amount
python respondent_cli.py hide --hourly-rate 50

# Hide all projects with a total incentive lower than the specified amount:
python respondent_cli.py hide --incentive 50
```

Alternatively, you can use the CLI module directly:
```bash
python -m cli.main auth
python -m cli.main projects
```

## Security Notes

- Never commit your `config.json` file to version control
- Keep your session cookies and authorization tokens secure
- Tokens expire periodically - you may need to refresh them

## License

This project is provided as-is for personal use.
