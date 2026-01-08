#!/usr/bin/env python3
"""
Session Keep-Alive Test Script

Tests how long a session can be kept alive by sending requests at regular
intervals (every 1 hour). The script will continue until the session expires.
"""
import requests
import time
from datetime import datetime, timedelta


# Configuration
URL = "https://app.respondent.io/api/v4/profiles/user/691f593aabd77eb5a29c7b35"
COOKIE_VALUE = ""
REQUEST_INTERVAL_HOURS = 1  # Send request every 1 hour
REQUEST_TIMEOUT = 120  # Request timeout in seconds (2 minutes)

# Headers
headers = {
    "Cookie": f"respondent.session.sid={COOKIE_VALUE}",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "Sec-Fetch-Site": "same-origin"
}


def format_time_delta(hours):
    """Format time delta in hours to a human-readable string."""
    if hours < 24:
        return f"{hours:.1f} hours"
    else:
        days = hours / 24
        return f"{days:.2f} days"


def print_raw_request(method, url, headers):
    """Print the raw HTTP request that will be sent."""
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    path = parsed.path
    if parsed.query:
        path += f"?{parsed.query}"
    
    print("  Raw HTTP Request:")
    print("  " + "-" * 76)
    print(f"  {method} {path} HTTP/1.1")
    print(f"  Host: {parsed.netloc}")
    for key, value in headers.items():
        print(f"  {key}: {value}")
    print("  " + "-" * 76)


def main():
    """Main function to test session keep-alive."""
    print("=" * 80)
    print("Session Keep-Alive Test Script")
    print("=" * 80)
    print(f"Target URL: {URL}")
    print(f"Request interval: {REQUEST_INTERVAL_HOURS} hour(s)")
    print("=" * 80)
    print()

    # Baseline request to verify session is valid
    print("[Baseline Request]")
    print("  Verifying session is valid...")
    print_raw_request("GET", URL, headers)
    print("  Sending request...", end=" ", flush=True)
    try:
        baseline_response = requests.get(URL, headers=headers, timeout=REQUEST_TIMEOUT)
        print(f"Status: {baseline_response.status_code}")
        
        if baseline_response.status_code != 200:
            print()
            print("=" * 80)
            print("ERROR: Baseline request failed!")
            print("=" * 80)
            print(f"Status Code: {baseline_response.status_code}")
            print(f"Status Reason: {baseline_response.reason}")
            print()
            print("The session cookie appears to be invalid or expired.")
            print("Please verify the cookie value and try again.")
            print("=" * 80)
            return
        
        print("  ✓ Session is valid. Starting keep-alive test...")
        print()
        
    except requests.exceptions.RequestException as e:
        print(f"ERROR: {e}")
        print()
        print("=" * 80)
        print("ERROR: Baseline request failed!")
        print("=" * 80)
        print("Could not connect to the server. Please check your network connection.")
        print("=" * 80)
        return

    request_count = 0
    start_time = datetime.now()
    last_request_time = None
    request_interval_seconds = REQUEST_INTERVAL_HOURS * 3600

    try:
        while True:
            request_count += 1
            current_time = datetime.now()
            
            # Calculate time since last request
            if last_request_time:
                time_since_last = current_time - last_request_time
                time_since_last_hours = time_since_last.total_seconds() / 3600
                time_since_last_str = format_time_delta(time_since_last_hours)
            else:
                time_since_last_str = "N/A (first request)"
            
            # Calculate total elapsed time
            total_elapsed = current_time - start_time
            total_elapsed_hours = total_elapsed.total_seconds() / 3600
            
            # Log request timestamp and time since last request
            print(f"[Request #{request_count}]")
            print(f"  Timestamp: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Time since last request: {time_since_last_str}")
            print(f"  Total session age: {format_time_delta(total_elapsed_hours)}")
            print_raw_request("GET", URL, headers)
            print("  Sending request...", end=" ", flush=True)
            
            # Send GET request
            try:
                response = requests.get(URL, headers=headers, timeout=REQUEST_TIMEOUT)
                print(f"Status: {response.status_code}")
                
                # Check if session expired (non-200 response)
                if response.status_code != 200:
                    print()
                    print("=" * 80)
                    print("SESSION EXPIRED")
                    print("=" * 80)
                    print()
                    
                    # Full HTTP response
                    print("Full HTTP Response:")
                    print("-" * 80)
                    print(f"Status Code: {response.status_code}")
                    print(f"Status Reason: {response.reason}")
                    print()
                    print("Response Headers:")
                    for key, value in response.headers.items():
                        print(f"  {key}: {value}")
                    print()
                    print("Response Body:")
                    print("-" * 80)
                    try:
                        # Try to decode as JSON first
                        print(response.json())
                    except:
                        # Fall back to text
                        print(response.text)
                    print("-" * 80)
                    print()
                    
                    # Summary
                    print("Summary:")
                    print("-" * 80)
                    print(f"Total requests made: {request_count}")
                    print(f"Total session lifetime: {format_time_delta(total_elapsed_hours)}")
                    print(f"Request interval: {format_time_delta(REQUEST_INTERVAL_HOURS)}")
                    print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"Session expired at: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    print("=" * 80)
                    break
                
            except requests.exceptions.RequestException as e:
                print(f"ERROR: {e}")
                print()
                print("=" * 80)
                print("ERROR: Request failed!")
                print("=" * 80)
                print(f"Error: {e}")
                print(f"Total requests made: {request_count}")
                print(f"Total session lifetime: {format_time_delta(total_elapsed_hours)}")
                print(f"Last successful request at: {last_request_time.strftime('%Y-%m-%d %H:%M:%S') if last_request_time else 'N/A'}")
                print("=" * 80)
                break
            
            # Update last request time
            last_request_time = current_time
            
            # Calculate next request time
            next_request_time = current_time + timedelta(seconds=request_interval_seconds)
            print(f"  Next request in {format_time_delta(REQUEST_INTERVAL_HOURS)} at {next_request_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            
            # Sleep for the interval with progress updates
            sleep_start = datetime.now()
            sleep_interval = 3600  # Update every 1 hour (3600 seconds)
            remaining_seconds = request_interval_seconds
            
            while remaining_seconds > 0:
                # Sleep in chunks to allow progress updates
                sleep_chunk = min(sleep_interval, remaining_seconds)
                time.sleep(sleep_chunk)
                remaining_seconds -= sleep_chunk
                
                # Show progress every hour
                if remaining_seconds > 0:
                    elapsed = (datetime.now() - sleep_start).total_seconds()
                    elapsed_hours = elapsed / 3600
                    remaining_hours = remaining_seconds / 3600
                    total_session_age = (datetime.now() - start_time).total_seconds() / 3600
                    print(f"  [Progress] Session age: {format_time_delta(total_session_age)}, "
                          f"Next request in: {format_time_delta(remaining_hours)}", flush=True)
            
            print(f"  Wait complete. Proceeding to next request...")
            print()
            
    except KeyboardInterrupt:
        print()
        print("=" * 80)
        print("Test interrupted by user")
        print("=" * 80)
        if request_count > 0:
            total_elapsed = datetime.now() - start_time
            total_elapsed_hours = total_elapsed.total_seconds() / 3600
            print(f"Total requests made: {request_count}")
            print(f"Total session lifetime: {format_time_delta(total_elapsed_hours)}")
            print(f"Request interval: {format_time_delta(REQUEST_INTERVAL_HOURS)}")
            print(f"Last request at: {last_request_time.strftime('%Y-%m-%d %H:%M:%S') if last_request_time else 'N/A'}")
        print("=" * 80)


if __name__ == "__main__":
    main()
