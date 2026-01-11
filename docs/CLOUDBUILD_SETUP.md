# Cloud Build Setup for Firebase Auto-Deployment

This guide explains how to set up automatic Firebase deployments using Google Cloud Build when code is pushed to the `main` branch.

## Prerequisites

1. **Google Cloud Project**: Your Firebase project must be linked to a Google Cloud project
2. **gcloud CLI**: Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
3. **Firebase CLI**: Install Firebase CLI (optional, for local testing)
4. **Repository**: Your code should be in a Git repository (GitHub, GitLab, Bitbucket, or Cloud Source Repositories)

## Step 1: Get Firebase CI Token

You need a Firebase CI token for automated deployments. Get it by running:

```bash
firebase login:ci
```

This will output a token that looks like: `1//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

**Save this token** - you'll need it in the next step.

## Step 2: Create Cloud Build Trigger

### Option A: Using Google Cloud Console (Recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **Cloud Build** → **Triggers**
3. Click **Create Trigger**
4. Configure the trigger:
   - **Name**: `firebase-deploy-main`
   - **Event**: Push to a branch
   - **Source**: Connect your repository (GitHub, GitLab, etc.)
   - **Branch**: `^main$` (regex pattern for main branch)
   - **Configuration**: Cloud Build configuration file
   - **Location**: Repository root
   - **Cloud Build configuration file**: `cloudbuild.yaml`
5. Click **Show included and ignored files** and ensure:
   - **Included files filter**: Leave empty or set to `**/*` (all files)
   - **Ignored files filter**: `**/node_modules/**,**/.git/**`
6. Under **Substitution variables**, add:
   - **Variable**: `_FIREBASE_TOKEN`
   - **Value**: Paste the token from Step 1
7. Click **Create**

### Option B: Using gcloud CLI

```bash
# Set your project
gcloud config set project respondentpro-xyz

# Create the trigger
gcloud builds triggers create github \
  --name="firebase-deploy-main" \
  --repo-name="YOUR_REPO_NAME" \
  --repo-owner="YOUR_GITHUB_USERNAME" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --substitutions="_FIREBASE_TOKEN=YOUR_FIREBASE_TOKEN_HERE"
```

**Note**: Replace `YOUR_REPO_NAME`, `YOUR_GITHUB_USERNAME`, and `YOUR_FIREBASE_TOKEN_HERE` with your actual values.

## Step 3: Enable Required APIs

Make sure the following APIs are enabled in your Google Cloud project:

```bash
gcloud services enable cloudbuild.googleapis.com
gcloud services enable firebase.googleapis.com
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable firestore.googleapis.com
```

## Step 4: Grant Cloud Build Permissions

Cloud Build needs permissions to deploy to Firebase. Grant the necessary roles:

```bash
# Get your project number
PROJECT_NUMBER=$(gcloud projects describe respondentpro-xyz --format="value(projectNumber)")

# Grant Cloud Build service account the necessary permissions
gcloud projects add-iam-policy-binding respondentpro-xyz \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/firebase.admin"

gcloud projects add-iam-policy-binding respondentpro-xyz \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/cloudfunctions.admin"

gcloud projects add-iam-policy-binding respondentpro-xyz \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/firestore.admin"
```

## Step 5: Test the Setup

1. Make a small change to your code
2. Commit and push to the `main` branch:
   ```bash
   git add .
   git commit -m "Test Cloud Build trigger"
   git push origin main
   ```
3. Go to **Cloud Build** → **History** in Google Cloud Console
4. You should see a build running automatically
5. Wait for it to complete (usually 5-10 minutes for first deployment)

## What Gets Deployed

The `cloudbuild.yaml` configuration deploys:

1. **Firestore Rules and Indexes**: Security rules and database indexes
2. **Cloud Functions**: All Python functions (including scheduled functions)
3. **Firebase Hosting**: Static files and rewrites configuration

## Troubleshooting

### Build Fails with Authentication Error

If you see authentication errors:
1. Verify the `_FIREBASE_TOKEN` substitution variable is set correctly
2. Regenerate the token: `firebase login:ci`
3. Update the trigger with the new token

### Build Fails with Permission Error

If you see permission errors:
1. Verify the IAM roles were granted correctly (Step 4)
2. Check that the Cloud Build service account has the necessary permissions

### Build Times Out

If builds timeout:
1. The default timeout is 1200s (20 minutes)
2. You can increase it in `cloudbuild.yaml` by changing the `timeout` value
3. For very large deployments, consider using a higher machine type

### Functions Deployment Fails

If function deployment fails:
1. Check that `requirements.txt` is correct
2. Verify Python 3.13 runtime is available in your region
3. Check Cloud Build logs for specific error messages

## Manual Deployment

You can also trigger a manual build:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_FIREBASE_TOKEN=$(firebase login:ci)
```

Or if you've stored the token in Secret Manager:

```bash
# Store token in Secret Manager
echo -n "YOUR_FIREBASE_TOKEN" | gcloud secrets create firebase-token --data-file=-

# Use in build
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_FIREBASE_TOKEN=$(gcloud secrets versions access latest --secret=firebase-token)
```

## Security Best Practices

1. **Store Firebase Token in Secret Manager**: Instead of hardcoding the token in the trigger, use Secret Manager:
   ```bash
   # Create secret
   echo -n "YOUR_FIREBASE_TOKEN" | gcloud secrets create firebase-token --data-file=-
   
   # Grant Cloud Build access
   PROJECT_NUMBER=$(gcloud projects describe respondentpro-xyz --format="value(projectNumber)")
   gcloud secrets add-iam-policy-binding firebase-token \
     --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   
   # Update trigger to use secret
   # In Cloud Console, update the substitution variable to:
   # $(gcloud secrets versions access latest --secret=firebase-token)
   ```

2. **Use Branch Protection**: Protect your `main` branch to require pull request reviews before merging

3. **Monitor Build Logs**: Regularly check Cloud Build logs for any issues or security warnings

## Cost Considerations

Cloud Build pricing:
- **Free tier**: 120 build-minutes per day
- **After free tier**: $0.003 per build-minute
- Typical Firebase deployment: 5-15 minutes
- Estimated cost: $0.015 - $0.045 per deployment (after free tier)

The configuration uses `E2_HIGHCPU_8` machine type for faster builds. You can reduce costs by using `E2_HIGHCPU_2` or `E2_HIGHCPU_4` if builds are taking too long.
