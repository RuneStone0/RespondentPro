# Cloud Build Setup for Firebase Auto-Deployment

This guide explains how to set up automatic Firebase deployments using Google Cloud Build when code is pushed to the `main` branch.

## Prerequisites

1. **Google Cloud Project**: Your Firebase project must be linked to a Google Cloud project
2. **gcloud CLI**: Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
3. **Firebase CLI**: Install Firebase CLI (optional, for local testing)
4. **Repository**: Your code should be in a Git repository (GitHub, GitLab, Bitbucket, or Cloud Source Repositories)

## Step 1: Grant Cloud Build Permissions

Cloud Build uses its service account credentials to authenticate with Firebase. Grant the necessary permissions:

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

**Note**: This setup uses Application Default Credentials (ADC), so you don't need to manage Firebase CI tokens that expire. The Cloud Build service account automatically authenticates with Firebase.

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
6. **No substitution variables needed** - authentication uses Cloud Build service account
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
  --build-config="cloudbuild.yaml"
```

**Note**: Replace `YOUR_REPO_NAME` and `YOUR_GITHUB_USERNAME` with your actual values. No Firebase token is needed - authentication uses the Cloud Build service account.

## Step 3: Enable Required APIs

Make sure the following APIs are enabled in your Google Cloud project:

```bash
gcloud services enable cloudbuild.googleapis.com
gcloud services enable firebase.googleapis.com
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable firestore.googleapis.com
```

## Step 4: Test the Setup

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
1. Verify the Cloud Build service account has the necessary permissions (see Step 1)
2. Re-run the permission grant commands from Step 1
3. Ensure the service account has `roles/firebase.admin` role

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
gcloud builds submit --config cloudbuild.yaml
```

No authentication tokens needed - the build uses your current gcloud credentials or the Cloud Build service account.

## Security Best Practices

1. **Service Account Authentication**: This setup uses Cloud Build's service account with Application Default Credentials (ADC), which is more secure than managing tokens:
   - No tokens to expire or rotate
   - Automatic credential management
   - Follows Google Cloud security best practices

2. **Use Branch Protection**: Protect your `main` branch to require pull request reviews before merging

3. **Monitor Build Logs**: Regularly check Cloud Build logs for any issues or security warnings

4. **Least Privilege**: The service account only has the minimum required permissions (`roles/firebase.admin`, `roles/cloudfunctions.admin`, `roles/firestore.admin`)

## Cost Considerations

Cloud Build pricing:
- **Free tier**: 120 build-minutes per day
- **After free tier**: $0.003 per build-minute
- Typical Firebase deployment: 5-15 minutes
- Estimated cost: $0.015 - $0.045 per deployment (after free tier)

The configuration uses `E2_HIGHCPU_8` machine type for faster builds. You can reduce costs by using `E2_HIGHCPU_2` or `E2_HIGHCPU_4` if builds are taking too long.
