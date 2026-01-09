#!/usr/bin/env python3
"""
Migration script to migrate existing users from Firestore to Firebase Auth

This script:
1. Reads all users from Firestore users collection
2. Creates Firebase Auth accounts for each user using their email
3. Links Firebase Auth UID to existing Firestore user document
4. Migrates email verification status
5. Generates a migration report

Usage:
    python scripts/migrate_users_to_firebase_auth.py [--dry-run] [--batch-size N]
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Initialize Firebase Admin
try:
    import firebase_admin
    from firebase_admin import auth, credentials
    from web.firebase_init import initialize_firebase_admin
    from web.db import users_collection, db
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running from the project root and all dependencies are installed")
    sys.exit(1)

# Initialize Firebase Admin
try:
    initialize_firebase_admin()
    print("Firebase Admin initialized successfully")
except Exception as e:
    print(f"Error initializing Firebase Admin: {e}")
    sys.exit(1)


def migrate_user(user_doc, dry_run=False):
    """
    Migrate a single user to Firebase Auth.
    
    Args:
        user_doc: Firestore document snapshot
        dry_run: If True, don't actually create Firebase Auth account
        
    Returns:
        dict: Migration result with status and details
    """
    user_id = user_doc.id
    user_data = user_doc.to_dict()
    email = user_data.get('username')  # Email is stored in username field
    
    if not email:
        return {
            'user_id': user_id,
            'email': None,
            'status': 'skipped',
            'reason': 'No email found in user document',
            'firebase_uid': None
        }
    
    result = {
        'user_id': user_id,
        'email': email,
        'status': 'unknown',
        'reason': None,
        'firebase_uid': None,
        'email_verified': user_data.get('email_verified', False)
    }
    
    if dry_run:
        result['status'] = 'dry_run'
        result['reason'] = 'Dry run - would create Firebase Auth account'
        return result
    
    try:
        # Check if user already exists in Firebase Auth
        try:
            existing_user = auth.get_user_by_email(email)
            firebase_uid = existing_user.uid
            result['status'] = 'exists'
            result['reason'] = 'User already exists in Firebase Auth'
            result['firebase_uid'] = firebase_uid
        except auth.UserNotFoundError:
            # User doesn't exist, create new account
            try:
                # Create user with email
                # Note: We can't set password without user interaction, so we'll create without password
                # User will need to use password reset or email link to set password
                user_record = auth.create_user(
                    email=email,
                    email_verified=user_data.get('email_verified', False),
                    disabled=False
                )
                firebase_uid = user_record.uid
                result['status'] = 'created'
                result['reason'] = 'Successfully created Firebase Auth account'
                result['firebase_uid'] = firebase_uid
            except Exception as e:
                result['status'] = 'error'
                result['reason'] = f'Error creating Firebase Auth account: {str(e)}'
                return result
        
        # Update Firestore user document with Firebase Auth UID
        try:
            users_collection.document(user_id).update({
                'firebase_uid': firebase_uid,
                'migrated_to_firebase_auth': True,
                'migrated_at': datetime.utcnow()
            })
            result['firestore_updated'] = True
        except Exception as e:
            result['status'] = 'partial'
            result['reason'] = f'Created Firebase Auth account but failed to update Firestore: {str(e)}'
            result['firestore_updated'] = False
        
        return result
        
    except Exception as e:
        result['status'] = 'error'
        result['reason'] = f'Unexpected error: {str(e)}'
        return result


def migrate_all_users(dry_run=False, batch_size=10):
    """
    Migrate all users from Firestore to Firebase Auth.
    
    Args:
        dry_run: If True, don't actually create accounts
        batch_size: Number of users to process before printing progress
        
    Returns:
        dict: Migration report with statistics
    """
    if users_collection is None:
        print("Error: Firestore users collection not available")
        return None
    
    print(f"\n{'DRY RUN: ' if dry_run else ''}Starting user migration...")
    print(f"Batch size: {batch_size}")
    print("-" * 60)
    
    # Get all users
    try:
        all_users = list(users_collection.stream())
        total_users = len(all_users)
        print(f"Found {total_users} users to migrate\n")
    except Exception as e:
        print(f"Error fetching users: {e}")
        return None
    
    # Migration results
    results = {
        'total': total_users,
        'created': 0,
        'exists': 0,
        'skipped': 0,
        'errors': 0,
        'partial': 0,
        'dry_run': 0,
        'details': []
    }
    
    # Process users
    for idx, user_doc in enumerate(all_users, 1):
        result = migrate_user(user_doc, dry_run=dry_run)
        results['details'].append(result)
        
        # Update statistics
        if result['status'] == 'created':
            results['created'] += 1
        elif result['status'] == 'exists':
            results['exists'] += 1
        elif result['status'] == 'skipped':
            results['skipped'] += 1
        elif result['status'] == 'error':
            results['errors'] += 1
        elif result['status'] == 'partial':
            results['partial'] += 1
        elif result['status'] == 'dry_run':
            results['dry_run'] += 1
        
        # Print progress
        if idx % batch_size == 0 or idx == total_users:
            status_msg = f"Processed {idx}/{total_users} users"
            if not dry_run:
                status_msg += f" (Created: {results['created']}, Exists: {results['exists']}, Errors: {results['errors']})"
            print(status_msg)
    
    return results


def generate_report(results, output_file=None):
    """
    Generate a migration report.
    
    Args:
        results: Migration results dictionary
        output_file: Optional file path to save report
    """
    if results is None:
        print("No results to report")
        return
    
    print("\n" + "=" * 60)
    print("MIGRATION REPORT")
    print("=" * 60)
    print(f"Total users processed: {results['total']}")
    print(f"Created: {results['created']}")
    print(f"Already exists: {results['exists']}")
    print(f"Skipped: {results['skipped']}")
    print(f"Errors: {results['errors']}")
    print(f"Partial (created but Firestore update failed): {results['partial']}")
    if results['dry_run'] > 0:
        print(f"Dry run (would create): {results['dry_run']}")
    print("=" * 60)
    
    # Show errors
    if results['errors'] > 0 or results['partial'] > 0:
        print("\nERRORS AND PARTIAL MIGRATIONS:")
        print("-" * 60)
        for detail in results['details']:
            if detail['status'] in ('error', 'partial'):
                print(f"User ID: {detail['user_id']}")
                print(f"Email: {detail.get('email', 'N/A')}")
                print(f"Status: {detail['status']}")
                print(f"Reason: {detail['reason']}")
                print()
    
    # Save to file if requested
    if output_file:
        report_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'total': results['total'],
                'created': results['created'],
                'exists': results['exists'],
                'skipped': results['skipped'],
                'errors': results['errors'],
                'partial': results['partial']
            },
            'details': results['details']
        }
        
        with open(output_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        print(f"\nDetailed report saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Migrate users from Firestore to Firebase Auth'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without actually creating Firebase Auth accounts'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of users to process before printing progress (default: 10)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='migration_report.json',
        help='Output file for detailed migration report (default: migration_report.json)'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("WARNING: Running in DRY RUN mode - no accounts will be created")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted")
            return
    else:
        print("WARNING: This will create Firebase Auth accounts for all users")
        print("Make sure you have backed up your data and understand the implications")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted")
            return
    
    # Run migration
    results = migrate_all_users(dry_run=args.dry_run, batch_size=args.batch_size)
    
    # Generate report
    if results:
        generate_report(results, output_file=args.output if not args.dry_run else None)


if __name__ == '__main__':
    main()
