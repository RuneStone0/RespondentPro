#!/usr/bin/env python3
"""
Module for AI analysis using Grok API
"""

import os
import json
import base64
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

GROK_API_KEY = os.environ.get('GROK_API_KEY')
GROK_API_URL = os.environ.get('GROK_API_URL', 'https://api.x.ai/v1/chat/completions')


def _call_grok_api(prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
    """
    Make a call to Grok API
    
    Args:
        prompt: User prompt
        system_prompt: Optional system prompt
        
    Returns:
        Response text or None if error
    """
    if not GROK_API_KEY:
        print("Warning: GROK_API_KEY not set, skipping AI analysis")
        return None
    
    try:
        headers = {
            'Authorization': f'Bearer {GROK_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        
        # Use the correct Grok model
        model = 'grok-4-1-fast-reasoning'
        
        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.3
        }
        
        print(f"[Grok API] POST {GROK_API_URL}")
        print(f"[Grok API] Model: {model}, Messages: {len(messages)}")
        
        response = requests.post(GROK_API_URL, headers=headers, json=payload, timeout=30)
        
        # Log response details for debugging
        print(f"[Grok API] Response status: {response.status_code}")
        if not response.ok:
            error_text = response.text[:500] if response.text else "No response body"
            print(f"[Grok API] Error response: {error_text}")
            print(f"[Grok API] Full URL: {GROK_API_URL}")
            print(f"[Grok API] Request payload keys: {list(payload.keys())}")
            
            # If 404, suggest checking the endpoint URL
            if response.status_code == 404:
                print("[Grok API] 404 Error - Possible issues:")
                print("  - Check if the API endpoint URL is correct")
                print("  - Verify the model name is correct (try: grok-beta, grok-2, grok)")
                print("  - Check xAI API documentation for the correct endpoint")
                print("  - Ensure your API key has access to the Grok API")
        
        response.raise_for_status()
        
        data = response.json()
        return data.get('choices', [{}])[0].get('message', {}).get('content', '')
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error {e.response.status_code if e.response else 'unknown'}: {e.response.text[:500] if e.response else str(e)}"
        print(f"[Grok API] Error: {error_msg}")
        print(f"[Grok API] URL: {GROK_API_URL}")
        print(f"[Grok API] Model: {payload.get('model', 'unknown')}")
        return None
    except Exception as e:
        print(f"[Grok API] Error calling Grok API: {e}")
        print(f"[Grok API] URL: {GROK_API_URL}")
        return None


def analyze_project(project_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract regions, professions, industries from a single project using Grok AI
    
    Args:
        project_data: Project data dictionary
        
    Returns:
        Dictionary with extracted metadata
    """
    name = project_data.get('name', '')
    description = project_data.get('description', '')
    
    return extract_metadata_with_grok(description, name)


def extract_metadata_with_grok(description: str, name: str) -> Dict[str, Any]:
    """
    Use Grok API to extract structured metadata
    
    Args:
        description: Project description
        name: Project name
        
    Returns:
        Dictionary with extracted metadata
    """
    prompt = f"""Analyze the following project and extract key information. Return ONLY a valid JSON object with no additional text.

Project Name: {name}
Description: {description}

Extract and return a JSON object with these fields:
- regions: List of US states, countries, or regions mentioned (e.g., ["California", "New York", "US"])
- professions: List of job titles or professions mentioned (e.g., ["healthcare professionals", "IT leaders", "engineers"])
- industries: List of industries or sectors mentioned (e.g., ["healthcare", "manufacturing", "SaaS"])

Return format:
{{
  "regions": ["region1", "region2"],
  "professions": ["profession1", "profession2"],
  "industries": ["industry1", "industry2"]
}}"""

    response = _call_grok_api(prompt)
    if not response:
        return {'regions': [], 'professions': [], 'industries': []}
    
    try:
        # Try to extract JSON from response
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:]
        if response.startswith('```'):
            response = response[3:]
        if response.endswith('```'):
            response = response[:-3]
        response = response.strip()
        
        metadata = json.loads(response)
        return {
            'regions': metadata.get('regions', []),
            'professions': metadata.get('professions', []),
            'industries': metadata.get('industries', [])
        }
    except Exception as e:
        print(f"Error parsing Grok response: {e}")
        return {'regions': [], 'professions': [], 'industries': []}


def analyze_projects_batch(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch analyze multiple projects
    
    Args:
        projects: List of project dictionaries
        
    Returns:
        List of projects with extracted metadata added
    """
    results = []
    for project in projects:
        metadata = analyze_project(project)
        project['extracted_metadata'] = metadata
        results.append(project)
    return results


def analyze_hide_feedback(feedback_text: str, project_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze user feedback to extract key reasons for hiding
    
    Args:
        feedback_text: User's feedback text
        project_data: Project data
        
    Returns:
        Dictionary with extracted reasons and patterns
    """
    name = project_data.get('name', '')
    description = project_data.get('description', '')
    
    prompt = f"""A user hid a project and provided this feedback: "{feedback_text}"

Project Name: {name}
Description: {description}

Analyze the feedback and extract:
1. Key reasons why the project was hidden
2. Patterns or criteria that could identify similar projects to hide

Return ONLY a valid JSON object:
{{
  "reasons": ["reason1", "reason2"],
  "patterns": {{
    "keywords": ["keyword1", "keyword2"],
    "regions": ["region1"],
    "professions": ["profession1"],
    "industries": ["industry1"]
  }}
}}"""

    response = _call_grok_api(prompt)
    if not response:
        return {'reasons': [], 'patterns': {}}
    
    try:
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:]
        if response.startswith('```'):
            response = response[3:]
        if response.endswith('```'):
            response = response[:-3]
        response = response.strip()
        
        result = json.loads(response)
        return {
            'reasons': result.get('reasons', []),
            'patterns': result.get('patterns', {})
        }
    except Exception as e:
        print(f"Error parsing feedback analysis: {e}")
        return {'reasons': [], 'patterns': {}}


def extract_similarity_patterns(feedback_text: str, project_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract patterns that can be used to find similar projects
    
    Args:
        feedback_text: User's feedback text
        project_data: Project data
        
    Returns:
        Dictionary with similarity patterns
    """
    analysis = analyze_hide_feedback(feedback_text, project_data)
    return analysis.get('patterns', {})


def find_similar_projects(
    user_id: str,
    project_id: str,
    all_projects: List[Dict[str, Any]],
    similarity_patterns: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Find projects similar to a hidden one based on feedback patterns
    
    Args:
        user_id: User ID
        project_id: Hidden project ID
        all_projects: List of all available projects
        similarity_patterns: Patterns extracted from feedback
        
    Returns:
        List of similar projects
    """
    similar = []
    keywords = similarity_patterns.get('keywords', [])
    regions = similarity_patterns.get('regions', [])
    professions = similarity_patterns.get('professions', [])
    industries = similarity_patterns.get('industries', [])
    
    for project in all_projects:
        if project.get('id') == project_id:
            continue
        
        name = project.get('name', '').lower()
        description = project.get('description', '').lower()
        text = f"{name} {description}"
        
        # Check for keyword matches
        matches_keywords = any(keyword.lower() in text for keyword in keywords) if keywords else False
        
        # Check extracted metadata
        metadata = project.get('extracted_metadata', {})
        matches_regions = any(region.lower() in str(metadata.get('regions', [])).lower() for region in regions) if regions else False
        matches_professions = any(prof.lower() in str(metadata.get('professions', [])).lower() for prof in professions) if professions else False
        matches_industries = any(ind.lower() in str(metadata.get('industries', [])).lower() for ind in industries) if industries else False
        
        if matches_keywords or matches_regions or matches_professions or matches_industries:
            similar.append(project)
    
    return similar


def generate_category_recommendations(
    user_id: str,
    all_projects: List[Dict[str, Any]],
    hidden_projects: List[str]
) -> List[Dict[str, Any]]:
    """
    Use Grok AI to generate category recommendations based on project patterns and user behavior
    
    Args:
        user_id: User ID
        all_projects: List of all projects
        hidden_projects: List of hidden project IDs
        
    Returns:
        List of category recommendations
    """
    # Get sample of project names and descriptions
    sample_projects = all_projects[:50]  # Limit to avoid token limits
    projects_text = "\n".join([
        f"- {p.get('name', '')}: {p.get('description', '')[:200]}"
        for p in sample_projects
    ])
    
    prompt = f"""Analyze the following projects and suggest categories that users might want to hide. 
Consider patterns like:
- Geographic regions (e.g., "California-only projects")
- Professions (e.g., "Healthcare professionals")
- Industries (e.g., "Manufacturing projects")
- Research types (e.g., "In-person studies")

Projects:
{projects_text}

Return ONLY a valid JSON array of category recommendations:
[
  {{
    "category_name": "Category Name",
    "description": "Brief description",
    "category_pattern": {{
      "keywords": ["keyword1", "keyword2"],
      "regions": ["region1"],
      "professions": ["profession1"],
      "industries": ["industry1"]
    }}
  }}
]

Return 5-10 relevant categories."""

    response = _call_grok_api(prompt)
    if not response:
        return []
    
    try:
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:]
        if response.startswith('```'):
            response = response[3:]
        if response.endswith('```'):
            response = response[:-3]
        response = response.strip()
        
        recommendations = json.loads(response)
        if not isinstance(recommendations, list):
            recommendations = [recommendations]
        
        # Count projects in each category
        for rec in recommendations:
            pattern = rec.get('category_pattern', {})
            matching_projects = get_projects_in_category(pattern, all_projects)
            rec['project_count'] = len(matching_projects)
        
        # Filter out categories with 0 projects and sort by count
        recommendations = [r for r in recommendations if r.get('project_count', 0) > 0]
        recommendations.sort(key=lambda x: x.get('project_count', 0), reverse=True)
        
        return recommendations[:10]  # Return top 10
    except Exception as e:
        print(f"Error parsing category recommendations: {e}")
        return []


def get_projects_in_category(
    category_pattern: Dict[str, Any],
    all_projects: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Filter projects matching a category pattern
    
    Args:
        category_pattern: Pattern dictionary with keywords, regions, professions, industries
        all_projects: List of all projects
        
    Returns:
        List of matching projects
    """
    matching = []
    keywords = category_pattern.get('keywords', [])
    regions = category_pattern.get('regions', [])
    professions = category_pattern.get('professions', [])
    industries = category_pattern.get('industries', [])
    
    for project in all_projects:
        name = project.get('name', '').lower()
        description = project.get('description', '').lower()
        text = f"{name} {description}"
        
        # Check keyword matches
        matches_keywords = any(keyword.lower() in text for keyword in keywords) if keywords else False
        
        # Check extracted metadata
        metadata = project.get('extracted_metadata', {})
        metadata_regions = [r.lower() for r in metadata.get('regions', [])]
        metadata_professions = [p.lower() for p in metadata.get('professions', [])]
        metadata_industries = [i.lower() for i in metadata.get('industries', [])]
        
        matches_regions = any(region.lower() in metadata_regions for region in regions) if regions else False
        matches_professions = any(prof.lower() in metadata_professions for prof in professions) if professions else False
        matches_industries = any(ind.lower() in metadata_industries for ind in industries) if industries else False
        
        if matches_keywords or matches_regions or matches_professions or matches_industries:
            matching.append(project)
    
    return matching


def validate_category_pattern(category_pattern: Dict[str, Any]) -> bool:
    """
    Validate that a category pattern is safe to use
    
    Args:
        category_pattern: Pattern dictionary
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(category_pattern, dict):
        return False
    
    # Check for required fields (at least one should be present)
    has_keywords = bool(category_pattern.get('keywords'))
    has_regions = bool(category_pattern.get('regions'))
    has_professions = bool(category_pattern.get('professions'))
    has_industries = bool(category_pattern.get('industries'))
    
    return has_keywords or has_regions or has_professions or has_industries

