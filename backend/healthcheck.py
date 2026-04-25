#!/usr/bin/env python3
"""
Simple health check script for Docker containers.
Checks if the API is responding at /health endpoint.
This replaces curl which is not available in python:3.11-slim images.
"""
import sys
import urllib.request
import urllib.error

try:
    # Try to connect to health endpoint with 5 second timeout
    response = urllib.request.urlopen("http://localhost:8000/health", timeout=5)
    
    # Check if status is OK (200)
    if response.status == 200:
        sys.exit(0)  # Success
    else:
        sys.exit(1)  # Failed
except (urllib.error.URLError, urllib.error.HTTPError, Exception):
    # Any error means unhealthy
    sys.exit(1)

