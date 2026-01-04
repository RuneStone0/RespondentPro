#!/usr/bin/env python3
"""
Project Data Analysis Script for Pricing Model

This script analyzes project usage patterns from MongoDB to help determine
optimal pricing tiers. It is READ-ONLY and does not modify any data.
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional
import statistics

from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')
MONGODB_DB = os.environ.get('MONGODB_DB', 'respondent_manager')

# Constants
MINUTES_SAVED_PER_PROJECT = 2


def connect_to_mongodb():
    """Connect to MongoDB and return collections."""
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client[MONGODB_DB]
        
        return {
            'users': db['users'],
            'hidden_projects_log': db['hidden_projects_log'],
            'projects_cache': db['projects_cache']
        }
    except Exception as e:
        print(f"ERROR: Failed to connect to MongoDB: {e}")
        print("Please ensure MongoDB is running and MONGODB_URI is correct in .env file")
        sys.exit(1)


def analyze_hidden_projects(collection) -> Dict[str, Any]:
    """Analyze hidden projects log for usage patterns."""
    print("=" * 80)
    print("ANALYZING HIDDEN PROJECTS LOG")
    print("=" * 80)
    
    if collection is None:
        print("ERROR: hidden_projects_log collection not available")
        return {}
    
    # Get total count
    total_hidden = collection.count_documents({})
    print(f"Total projects hidden: {total_hidden:,}")
    
    if total_hidden == 0:
        print("No hidden projects found in database.")
        return {}
    
    # Get unique users
    unique_users = collection.distinct('user_id')
    user_count = len(unique_users)
    print(f"Unique users: {user_count}")
    print()
    
    # Per-user statistics
    user_stats = {}
    user_monthly_counts = defaultdict(lambda: defaultdict(int))  # user_id -> {year-month: count}
    
    # Aggregate by user
    pipeline = [
        {
            '$group': {
                '_id': '$user_id',
                'total_hidden': {'$sum': 1},
                'first_hidden': {'$min': '$hidden_at'},
                'last_hidden': {'$max': '$hidden_at'},
                'hidden_dates': {'$push': '$hidden_at'}
            }
        }
    ]
    
    for result in collection.aggregate(pipeline):
        user_id = result['_id']
        total = result['total_hidden']
        first_hidden = result.get('first_hidden')
        last_hidden = result.get('last_hidden')
        hidden_dates = result.get('hidden_dates', [])
        
        # Calculate active months
        active_months = set()
        for date in hidden_dates:
            if date:
                if isinstance(date, str):
                    try:
                        date = datetime.fromisoformat(date.replace('Z', '+00:00'))
                    except:
                        continue
                active_months.add(date.strftime('%Y-%m'))
                user_monthly_counts[user_id][date.strftime('%Y-%m')] += 1
        
        # Calculate time span
        if first_hidden and last_hidden:
            if isinstance(first_hidden, str):
                first_hidden = datetime.fromisoformat(first_hidden.replace('Z', '+00:00'))
            if isinstance(last_hidden, str):
                last_hidden = datetime.fromisoformat(last_hidden.replace('Z', '+00:00'))
            
            time_span = (last_hidden - first_hidden).days
            months_active = len(active_months) or 1
            avg_per_month = total / months_active if months_active > 0 else total
        else:
            time_span = 0
            months_active = 1
            avg_per_month = total
        
        user_stats[user_id] = {
            'total_hidden': total,
            'first_hidden': first_hidden,
            'last_hidden': last_hidden,
            'months_active': months_active,
            'avg_per_month': avg_per_month,
            'time_span_days': time_span
        }
    
    # Calculate statistics
    monthly_rates = [stats['avg_per_month'] for stats in user_stats.values()]
    total_hidden_per_user = [stats['total_hidden'] for stats in user_stats.values()]
    
    if not monthly_rates:
        print("No valid user statistics found.")
        return {}
    
    # Calculate percentiles
    monthly_rates_sorted = sorted(monthly_rates)
    total_hidden_sorted = sorted(total_hidden_per_user)
    
    def percentile(data, p):
        if not data:
            return 0
        k = (len(data) - 1) * p
        f = int(k)
        c = k - f
        if f + 1 < len(data):
            return data[f] + c * (data[f + 1] - data[f])
        return data[f]
    
    stats_result = {
        'total_hidden': total_hidden,
        'user_count': user_count,
        'avg_per_user_per_month': statistics.mean(monthly_rates) if monthly_rates else 0,
        'median_per_user_per_month': statistics.median(monthly_rates) if monthly_rates else 0,
        'p25_per_user_per_month': percentile(monthly_rates_sorted, 0.25),
        'p75_per_user_per_month': percentile(monthly_rates_sorted, 0.75),
        'p90_per_user_per_month': percentile(monthly_rates_sorted, 0.90),
        'p95_per_user_per_month': percentile(monthly_rates_sorted, 0.95),
        'max_per_user_per_month': max(monthly_rates) if monthly_rates else 0,
        'avg_total_per_user': statistics.mean(total_hidden_per_user) if total_hidden_per_user else 0,
        'median_total_per_user': statistics.median(total_hidden_per_user) if total_hidden_per_user else 0,
        'max_total_per_user': max(total_hidden_per_user) if total_hidden_per_user else 0,
        'user_stats': user_stats,
        'user_monthly_counts': dict(user_monthly_counts)
    }
    
    # Print statistics
    print("PER-USER STATISTICS (Projects Hidden Per Month):")
    print("-" * 80)
    print(f"  Average:        {stats_result['avg_per_user_per_month']:.2f} projects/month")
    print(f"  Median:         {stats_result['median_per_user_per_month']:.2f} projects/month")
    print(f"  25th Percentile: {stats_result['p25_per_user_per_month']:.2f} projects/month")
    print(f"  75th Percentile: {stats_result['p75_per_user_per_month']:.2f} projects/month")
    print(f"  90th Percentile: {stats_result['p90_per_user_per_month']:.2f} projects/month")
    print(f"  95th Percentile: {stats_result['p95_per_user_per_month']:.2f} projects/month")
    print(f"  Maximum:        {stats_result['max_per_user_per_month']:.2f} projects/month")
    print()
    
    print("LIFETIME STATISTICS (Total Projects Hidden Per User):")
    print("-" * 80)
    print(f"  Average:        {stats_result['avg_total_per_user']:.2f} projects")
    print(f"  Median:         {stats_result['median_total_per_user']:.2f} projects")
    print(f"  Maximum:        {stats_result['max_total_per_user']:,} projects")
    print()
    
    return stats_result


def analyze_project_cache(collection) -> Dict[str, Any]:
    """Analyze project cache for availability patterns."""
    print("=" * 80)
    print("ANALYZING PROJECT CACHE")
    print("=" * 80)
    
    if collection is None:
        print("ERROR: projects_cache collection not available")
        return {}
    
    # Get total cache entries
    total_caches = collection.count_documents({})
    print(f"Total cache entries: {total_caches}")
    
    if total_caches == 0:
        print("No project cache entries found in database.")
        return {}
    
    # Get unique users
    unique_users = collection.distinct('user_id')
    user_count = len(unique_users)
    print(f"Unique users with cache: {user_count}")
    print()
    
    # Analyze cache refresh patterns
    cache_stats = []
    project_counts = []
    
    for cache_doc in collection.find({}):
        user_id = cache_doc.get('user_id')
        cached_at = cache_doc.get('cached_at') or cache_doc.get('last_updated')
        total_count = cache_doc.get('total_count', 0)
        projects = cache_doc.get('projects', [])
        
        if cached_at:
            if isinstance(cached_at, str):
                try:
                    cached_at = datetime.fromisoformat(cached_at.replace('Z', '+00:00'))
                except:
                    cached_at = None
        
        if total_count > 0:
            project_counts.append(total_count)
        
        if cached_at:
            cache_stats.append({
                'user_id': user_id,
                'cached_at': cached_at,
                'total_count': total_count,
                'project_count': len(projects) if isinstance(projects, list) else 0
            })
    
    if not cache_stats:
        print("No valid cache statistics found.")
        return {}
    
    # Sort by date
    cache_stats.sort(key=lambda x: x['cached_at'])
    
    # Calculate refresh frequency and project growth
    user_refresh_intervals = defaultdict(list)
    user_project_growth = defaultdict(list)  # Track project count changes per user
    
    for i in range(1, len(cache_stats)):
        prev = cache_stats[i-1]
        curr = cache_stats[i]
        if prev['user_id'] == curr['user_id']:
            interval = (curr['cached_at'] - prev['cached_at']).total_seconds() / 3600  # hours
            if interval > 0:
                user_refresh_intervals[prev['user_id']].append(interval)
            
            # Track project count changes
            if prev['total_count'] > 0 and curr['total_count'] > 0:
                time_diff_days = (curr['cached_at'] - prev['cached_at']).days
                if time_diff_days > 0:
                    project_change = curr['total_count'] - prev['total_count']
                    # Calculate monthly rate
                    monthly_change = (project_change / time_diff_days) * 30
                    user_project_growth[prev['user_id']].append(monthly_change)
    
    avg_intervals = []
    for intervals in user_refresh_intervals.values():
        if intervals:
            avg_intervals.append(statistics.mean(intervals))
    
    # Calculate average monthly project addition rate
    all_monthly_growth = []
    for growth_list in user_project_growth.values():
        all_monthly_growth.extend(growth_list)
    
    avg_monthly_new_projects = statistics.mean(all_monthly_growth) if all_monthly_growth else 0
    median_monthly_new_projects = statistics.median(all_monthly_growth) if all_monthly_growth else 0
    
    stats_result = {
        'total_caches': total_caches,
        'user_count': user_count,
        'avg_projects_per_cache': statistics.mean(project_counts) if project_counts else 0,
        'median_projects_per_cache': statistics.median(project_counts) if project_counts else 0,
        'max_projects_per_cache': max(project_counts) if project_counts else 0,
        'min_projects_per_cache': min(project_counts) if project_counts else 0,
        'avg_refresh_interval_hours': statistics.mean(avg_intervals) if avg_intervals else 0,
        'avg_monthly_new_projects': avg_monthly_new_projects,
        'median_monthly_new_projects': median_monthly_new_projects,
        'cache_stats': cache_stats,
        'user_project_growth': dict(user_project_growth)
    }
    
    # Print statistics
    print("PROJECT AVAILABILITY STATISTICS:")
    print("-" * 80)
    print(f"  Average projects per cache:  {stats_result['avg_projects_per_cache']:.2f}")
    print(f"  Median projects per cache:    {stats_result['median_projects_per_cache']:.2f}")
    print(f"  Maximum projects per cache:   {stats_result['max_projects_per_cache']:,}")
    print(f"  Minimum projects per cache:   {stats_result['min_projects_per_cache']:,}")
    if stats_result['avg_refresh_interval_hours'] > 0:
        print(f"  Average refresh interval:     {stats_result['avg_refresh_interval_hours']:.2f} hours")
        print(f"  Average refresh interval:     {stats_result['avg_refresh_interval_hours']/24:.2f} days")
    if stats_result['avg_monthly_new_projects'] > 0:
        print(f"  Average new projects/month:   {stats_result['avg_monthly_new_projects']:.2f}")
        print(f"  Median new projects/month:    {stats_result['median_monthly_new_projects']:.2f}")
    print()
    
    return stats_result


def analyze_users(collection) -> Dict[str, Any]:
    """Analyze user collection for registration patterns."""
    print("=" * 80)
    print("ANALYZING USERS")
    print("=" * 80)
    
    if collection is None:
        print("ERROR: users collection not available")
        return {}
    
    total_users = collection.count_documents({})
    print(f"Total users: {total_users}")
    
    if total_users == 0:
        print("No users found in database.")
        return {}
    
    # Get registration dates if available
    registration_dates = []
    for user in collection.find({}, {'created_at': 1, 'registered_at': 1}):
        reg_date = user.get('created_at') or user.get('registered_at')
        if reg_date:
            if isinstance(reg_date, str):
                try:
                    reg_date = datetime.fromisoformat(reg_date.replace('Z', '+00:00'))
                except:
                    continue
            registration_dates.append(reg_date)
    
    stats_result = {
        'total_users': total_users,
        'users_with_registration_date': len(registration_dates)
    }
    
    if registration_dates:
        registration_dates.sort()
        stats_result['first_registration'] = registration_dates[0]
        stats_result['last_registration'] = registration_dates[-1]
        stats_result['registration_span_days'] = (registration_dates[-1] - registration_dates[0]).days
        
        print(f"Users with registration dates: {len(registration_dates)}")
        if len(registration_dates) > 1:
            print(f"First registration: {registration_dates[0].strftime('%Y-%m-%d')}")
            print(f"Last registration: {registration_dates[-1].strftime('%Y-%m-%d')}")
            print(f"Registration span: {stats_result['registration_span_days']} days")
    print()
    
    return stats_result


def calculate_usage_estimates(hidden_stats: Dict[str, Any], 
                              cache_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate usage estimates: projects served, hidden, and time-to-spend."""
    print("=" * 80)
    print("USAGE ESTIMATES & TIME-TO-SPEND CALCULATIONS")
    print("=" * 80)
    print()
    
    if not hidden_stats or not cache_stats:
        print("Insufficient data for usage estimates.")
        return {}
    
    # Get average projects available per user
    avg_projects_available = cache_stats.get('avg_projects_per_cache', 0)
    median_projects_available = cache_stats.get('median_projects_per_cache', 0)
    
    # Get monthly new projects rate
    avg_monthly_new = cache_stats.get('avg_monthly_new_projects', 0)
    median_monthly_new = cache_stats.get('median_monthly_new_projects', 0)
    
    # Get hidden projects per month
    avg_hidden_per_month = hidden_stats.get('avg_per_user_per_month', 0)
    median_hidden_per_month = hidden_stats.get('median_per_user_per_month', 0)
    p75_hidden_per_month = hidden_stats.get('p75_per_user_per_month', 0)
    p90_hidden_per_month = hidden_stats.get('p90_per_user_per_month', 0)
    
    # Calculate hide rate (percentage of projects that get hidden)
    # This is an estimate: hidden projects / (available projects + new projects)
    # We'll use a simplified model: if user sees X projects/month and hides Y, hide rate = Y/X
    # But we need to estimate X (projects served per month)
    
    # Estimate projects served per month:
    # If cache refreshes every N days, and there are M projects available,
    # and N new projects are added per month, then:
    # Projects served ≈ (projects available) + (new projects per month)
    # But we need to account for cache refresh frequency
    
    avg_refresh_days = (cache_stats.get('avg_refresh_interval_hours', 0) / 24) if cache_stats.get('avg_refresh_interval_hours', 0) > 0 else 30
    
    # Estimate: projects served per month = projects available (seen in cache) + new projects
    # For simplicity, assume users see all available projects plus new ones
    # More accurate: projects served ≈ (avg_projects_available) + (monthly_new_projects)
    
    # Calculate hide rate based on actual data
    # If we know hidden/month and can estimate served/month
    # We'll use: hide_rate = hidden_per_month / (estimated_served_per_month)
    
    # Estimate projects served per month
    # Conservative estimate: projects available + new projects per month
    # But projects available might include old ones, so we need to think differently
    
    # Better approach: Use the ratio of hidden to available
    # If user has X projects available and hides Y per month, 
    # and cache refreshes every N days, then:
    # Projects served per month ≈ (X / (N/30)) + monthly_new
    # But this is complex...
    
    # Simplified: Assume projects served ≈ projects available (if refreshed monthly)
    # Plus new projects added
    if avg_refresh_days > 0:
        refreshes_per_month = 30 / avg_refresh_days
        estimated_served_per_month = (avg_projects_available / refreshes_per_month) + avg_monthly_new
    else:
        # If no refresh data, assume projects served ≈ available projects + new projects
        estimated_served_per_month = avg_projects_available + avg_monthly_new
    
    # Calculate hide rate
    if estimated_served_per_month > 0:
        hide_rate = (avg_hidden_per_month / estimated_served_per_month) * 100
    else:
        hide_rate = 0
    
    # For different user segments
    estimates = {
        'avg_monthly_new_projects': avg_monthly_new,
        'median_monthly_new_projects': median_monthly_new,
        'avg_projects_available': avg_projects_available,
        'median_projects_available': median_projects_available,
        'estimated_served_per_month': estimated_served_per_month,
        'hide_rate_percent': hide_rate,
        'avg_hidden_per_month': avg_hidden_per_month,
        'median_hidden_per_month': median_hidden_per_month,
        'p75_hidden_per_month': p75_hidden_per_month,
        'p90_hidden_per_month': p90_hidden_per_month
    }
    
    # Print estimates
    print("MONTHLY PROJECT ADDITION RATE:")
    print("-" * 80)
    print(f"  Average new projects added/month:  {avg_monthly_new:.2f}")
    print(f"  Median new projects added/month:   {median_monthly_new:.2f}")
    print()
    
    print("PROJECTS SERVED TO USERS:")
    print("-" * 80)
    print(f"  Average projects available per user: {avg_projects_available:.2f}")
    print(f"  Estimated projects served/month:     {estimated_served_per_month:.2f}")
    print(f"  Hide rate:                            {hide_rate:.1f}% of projects get hidden")
    print()
    
    print("PROJECTS HIDDEN BY RESPONDENTPRO:")
    print("-" * 80)
    print(f"  Average user:    {avg_hidden_per_month:.2f} projects/month")
    print(f"  Median user:     {median_hidden_per_month:.2f} projects/month")
    print(f"  75th percentile: {p75_hidden_per_month:.2f} projects/month")
    print(f"  90th percentile: {p90_hidden_per_month:.2f} projects/month")
    print()
    
    # Calculate time to spend 1,000 hidden projects
    print("TIME TO SPEND 1,000 HIDDEN PROJECTS:")
    print("-" * 80)
    
    milestones = [1000, 5000, 10000]
    for milestone in milestones:
        if median_hidden_per_month > 0:
            months_median = milestone / median_hidden_per_month
            print(f"  Median user ({median_hidden_per_month:.0f} projects/month):")
            print(f"    {milestone:,} projects = {months_median:.1f} months ({months_median/12:.2f} years)")
        
        if avg_hidden_per_month > 0:
            months_avg = milestone / avg_hidden_per_month
            print(f"  Average user ({avg_hidden_per_month:.0f} projects/month):")
            print(f"    {milestone:,} projects = {months_avg:.1f} months ({months_avg/12:.2f} years)")
        
        if p75_hidden_per_month > 0:
            months_p75 = milestone / p75_hidden_per_month
            print(f"  75th percentile ({p75_hidden_per_month:.0f} projects/month):")
            print(f"    {milestone:,} projects = {months_p75:.1f} months ({months_p75/12:.2f} years)")
        print()
    
    # Calculate costs
    print("COST ESTIMATES FOR 1,000 HIDDEN PROJECTS:")
    print("-" * 80)
    
    # Pay-as-you-go pricing
    cost_per_1000_standard = 5.00
    cost_per_1000_volume_5k = 4.00
    cost_per_1000_volume_10k = 3.00
    
    print("Pay-as-You-Go Pricing:")
    print(f"  Standard rate: ${cost_per_1000_standard:.2f} per 1,000 projects")
    print(f"  Cost for 1,000 projects: ${cost_per_1000_standard:.2f}")
    print(f"  Cost for 5,000 projects: ${(5000/1000) * cost_per_1000_volume_5k:.2f} (${cost_per_1000_volume_5k:.2f}/1k)")
    print(f"  Cost for 10,000 projects: ${(10000/1000) * cost_per_1000_volume_10k:.2f} (${cost_per_1000_volume_10k:.2f}/1k)")
    print()
    
    # Calculate monthly cost for different user types
    print("MONTHLY COST ESTIMATES (Pay-as-You-Go):")
    print("-" * 80)
    if median_hidden_per_month > 0:
        monthly_cost_median = (median_hidden_per_month / 1000) * cost_per_1000_standard
        print(f"  Median user ({median_hidden_per_month:.0f} projects/month): ${monthly_cost_median:.2f}/month")
        print(f"    Annual cost: ${monthly_cost_median * 12:.2f}/year")
    
    if avg_hidden_per_month > 0:
        monthly_cost_avg = (avg_hidden_per_month / 1000) * cost_per_1000_standard
        print(f"  Average user ({avg_hidden_per_month:.0f} projects/month): ${monthly_cost_avg:.2f}/month")
        print(f"    Annual cost: ${monthly_cost_avg * 12:.2f}/year")
    
    if p75_hidden_per_month > 0:
        monthly_cost_p75 = (p75_hidden_per_month / 1000) * cost_per_1000_standard
        print(f"  75th percentile ({p75_hidden_per_month:.0f} projects/month): ${monthly_cost_p75:.2f}/month")
        print(f"    Annual cost: ${monthly_cost_p75 * 12:.2f}/year")
        print()
        print(f"  Subscription break-even: If monthly subscription < ${monthly_cost_p75:.2f}, heavy users save money")
    
    print()
    
    return estimates


def generate_pricing_recommendations(hidden_stats: Dict[str, Any], 
                                     cache_stats: Dict[str, Any],
                                     user_stats: Dict[str, Any]) -> None:
    """Generate pricing recommendations based on analysis."""
    print("=" * 80)
    print("PRICING RECOMMENDATIONS")
    print("=" * 80)
    print()
    
    if not hidden_stats:
        print("Insufficient data for pricing recommendations.")
        return
    
    median_monthly = hidden_stats.get('median_per_user_per_month', 0)
    avg_monthly = hidden_stats.get('avg_per_user_per_month', 0)
    p75_monthly = hidden_stats.get('p75_per_user_per_month', 0)
    p90_monthly = hidden_stats.get('p90_per_user_per_month', 0)
    max_monthly = hidden_stats.get('max_per_user_per_month', 0)
    
    # Calculate time saved
    print("VALUE PROPOSITION (Time Saved):")
    print("-" * 80)
    print(f"  Each project hidden saves: {MINUTES_SAVED_PER_PROJECT} minutes")
    print(f"  Median user saves: {median_monthly * MINUTES_SAVED_PER_PROJECT:.0f} min/month = {median_monthly * MINUTES_SAVED_PER_PROJECT / 60:.1f} hours/month")
    print(f"  Average user saves: {avg_monthly * MINUTES_SAVED_PER_PROJECT:.0f} min/month = {avg_monthly * MINUTES_SAVED_PER_PROJECT / 60:.1f} hours/month")
    print(f"  Heavy user (75th pct) saves: {p75_monthly * MINUTES_SAVED_PER_PROJECT:.0f} min/month = {p75_monthly * MINUTES_SAVED_PER_PROJECT / 60:.1f} hours/month")
    print(f"  Power user (90th pct) saves: {p90_monthly * MINUTES_SAVED_PER_PROJECT:.0f} min/month = {p90_monthly * MINUTES_SAVED_PER_PROJECT / 60:.1f} hours/month")
    print()
    
    # Pricing recommendations
    print("RECOMMENDED PRICING TIERS:")
    print("-" * 80)
    
    # Free tier recommendation
    if median_monthly > 0:
        # Free tier should cover median user for ~2-3 months
        free_tier_recommendation = max(500, int(median_monthly * 2))
        print(f"1. FREE TIER:")
        print(f"   Recommended: {free_tier_recommendation:,} projects")
        print(f"   Rationale: Covers median user for ~2 months ({median_monthly:.0f} projects/month)")
        print(f"   Alternative: 500 projects (covers {500/median_monthly:.1f} months for median user)")
        print()
    
    # Pay-as-you-go recommendation
    print("2. PAY-AS-YOU-GO:")
    print(f"   Standard rate: $5 per 1,000 projects")
    print(f"   Cost per project: $0.005")
    print(f"   Cost per hour saved: ${(5 / 1000) / (MINUTES_SAVED_PER_PROJECT / 60):.2f} per hour")
    print()
    print("   Volume Discounts:")
    print(f"   - 5,000+ projects: $4 per 1,000 (20% discount)")
    print(f"   - 10,000+ projects: $3 per 1,000 (40% discount)")
    print()
    
    # Subscription recommendation
    if p75_monthly > 0:
        # Subscription should be cheaper than pay-as-you-go for heavy users
        monthly_payg_cost = (p75_monthly * 12) / 1000 * 5  # Annual cost at standard rate
        subscription_recommendation = max(19.99, monthly_payg_cost / 12 * 0.8)  # 20% discount
        
        print("3. SUBSCRIPTION TIERS:")
        print(f"   Monthly Subscription:")
        print(f"   Recommended: ${subscription_recommendation:.2f}/month")
        print(f"   Rationale: 20% discount vs pay-as-you-go for 75th percentile user")
        print(f"   Break-even: {subscription_recommendation * 1000 / 5:.0f} projects/month")
        print()
        print(f"   Annual Subscription:")
        annual_price = subscription_recommendation * 12 * 0.83  # ~17% additional discount
        print(f"   Recommended: ${annual_price:.2f}/year (${annual_price/12:.2f}/month)")
        print(f"   Rationale: Additional ~17% discount for annual commitment")
        print(f"   Savings vs monthly: ${(subscription_recommendation * 12) - annual_price:.2f}/year")
        print()
    
    # Revenue projections (example)
    if hidden_stats['user_count'] > 0:
        print("5. REVENUE PROJECTIONS (Example):")
        print("-" * 80)
        print("   Assumptions:")
        print("   - 50% of users stay on free tier")
        print("   - 30% use pay-as-you-go (at median usage)")
        print("   - 20% subscribe monthly")
        print()
        
        paying_users = hidden_stats['user_count'] * 0.5
        payg_users = paying_users * 0.6
        sub_users = paying_users * 0.4
        
        monthly_payg_revenue = payg_users * (median_monthly / 1000) * 5
        monthly_sub_revenue = sub_users * subscription_recommendation if p75_monthly > 0 else 0
        monthly_total = monthly_payg_revenue + monthly_sub_revenue
        
        print(f"   Monthly Revenue Estimate:")
        print(f"   - Pay-as-you-go: ${monthly_payg_revenue:.2f} ({payg_users:.0f} users)")
        print(f"   - Subscriptions: ${monthly_sub_revenue:.2f} ({sub_users:.0f} users)")
        print(f"   - Total: ${monthly_total:.2f}/month")
        print(f"   - Annual: ${monthly_total * 12:.2f}/year")
        print()


def main():
    """Main analysis function."""
    print("=" * 80)
    print("PROJECT DATA ANALYSIS FOR PRICING MODEL")
    print("=" * 80)
    print("This script analyzes project usage patterns to help determine optimal pricing.")
    print("READ-ONLY: No data will be modified.")
    print("=" * 80)
    print()
    
    # Connect to MongoDB
    collections = connect_to_mongodb()
    
    # Run analyses
    hidden_stats = analyze_hidden_projects(collections['hidden_projects_log'])
    cache_stats = analyze_project_cache(collections['projects_cache'])
    user_stats = analyze_users(collections['users'])
    
    # Calculate usage estimates
    usage_estimates = calculate_usage_estimates(hidden_stats, cache_stats)
    
    # Generate recommendations
    generate_pricing_recommendations(hidden_stats, cache_stats, user_stats)
    
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print("Use the recommendations above to finalize your pricing model.")
    print("=" * 80)


if __name__ == "__main__":
    main()
