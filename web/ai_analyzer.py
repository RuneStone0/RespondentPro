#!/usr/bin/env python3
"""
Module for AI analysis using Grok API
"""

import json
import logging
from typing import Dict, Any, List, Optional

# Import centralized Grok service
from .services.grok_service import call_grok_api

# Create logger for this module
logger = logging.getLogger(__name__)


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

    response = call_grok_api(prompt)
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
        logger.error(f"Error parsing Grok response: {e}", exc_info=True)
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

    response = call_grok_api(prompt)
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
        logger.error(f"Error parsing feedback analysis: {e}", exc_info=True)
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

    response = call_grok_api(prompt)
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
        logger.error(f"Error parsing category recommendations: {e}", exc_info=True)
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


def generate_hide_suggestions(project_data: Dict[str, Any]) -> List[str]:
    """
    Generate suggestions for why a user might want to hide a project
    
    Args:
        project_data: Project data dictionary with name, description, etc.
        
    Returns:
        List of exactly 3 suggestion strings
    """
    name = project_data.get('name', '')
    description = project_data.get('description', '')
    
    prompt = f"""Analyze the following project and suggest exactly 3 short, precise reasons why a user might want to hide it. 
Focus on the user's personal perspective - express why this project doesn't matter to them personally.
Write suggestions in FIRST PERSON from the user's viewpoint (e.g., "I don't...", "I'm not...", "I don't know...").
Base your suggestions ONLY on the project title and description - do not consider rates, time, or other details.
Keep each suggestion SHORT and PRECISE - aim for 5-10 words maximum.

Project Name: {name}
Description: {description}

Return ONLY a valid JSON array of exactly 3 short, precise suggestion strings, no additional text:
[
  "Reason 1 (e.g., I don't know how law firms operate)",
  "Reason 2 (e.g., I'm not a law firm leader)",
  "Reason 3 (e.g., I'm not interested in legal topics)"
]

Make each suggestion specific to this project, written in first person, short and precise (5-10 words max), expressing the user's personal reasons for hiding it based on the project content."""

    response = call_grok_api(prompt, model='grok-4-1-fast-non-reasoning')
    if not response:
        # Fallback suggestions if AI fails
        return [
            "I'm not interested in this",
            "I don't have relevant experience",
            "This doesn't match my background"
        ]
    
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
        
        suggestions = json.loads(response)
        if isinstance(suggestions, list) and len(suggestions) > 0:
            # Ensure we have exactly 3 suggestions
            if len(suggestions) >= 3:
                return suggestions[:3]
            else:
                # Pad with fallback suggestions if needed
                fallback = [
                    "I'm not interested in this",
                    "I don't have relevant experience",
                    "This doesn't match my background"
                ]
                return (suggestions + fallback)[:3]
        else:
            raise ValueError("Invalid response format")
    except Exception as e:
        logger.error(f"Error parsing hide suggestions: {e}", exc_info=True)
        # Return fallback suggestions
        return [
            "I'm not interested in this",
            "I don't have relevant experience",
            "This doesn't match my background"
        ]


def should_hide_project_based_on_feedback(
    project_data: Dict[str, Any],
    feedback_list: List[Dict[str, Any]]
) -> bool:
    """
    Use AI to determine if a project should be hidden based on user's previous feedback
    
    Args:
        project_data: Project data dictionary with name, description, etc.
        feedback_list: List of feedback entries with feedback_text, project_id, hidden_at
        
    Returns:
        True if project should be hidden, False otherwise
    """
    if not feedback_list:
        return False
    
    name = project_data.get('name', '')
    description = project_data.get('description', '')
    
    # Format feedback list for the prompt
    feedback_texts = []
    for feedback in feedback_list:
        feedback_text = feedback.get('feedback_text', '')
        if feedback_text:
            feedback_texts.append(f'  - "{feedback_text}"')
    
    feedback_summary = '\n'.join(feedback_texts) if feedback_texts else '  (no feedback)'
    
    prompt = f"""Analyze the following project and determine if it should be hidden based on the user's previous feedback.

Project Name: {name}
Description: {description}

User's Previous Feedback (reasons they hid other projects):
{feedback_summary}

Based on the user's previous feedback, should this project be hidden?
Consider the context and meaning of the feedback. For example, if the user said "I'm not a law firm professional", 
then projects about law firms should be hidden.

Return ONLY "true" or "false" (lowercase, no quotes, no additional text)."""

    response = call_grok_api(prompt, model='grok-4-1-fast-non-reasoning')
    if not response:
        return False
    
    try:
        response = response.strip().lower()
        # Remove any quotes or whitespace
        response = response.strip('"\'')
        
        if response == 'true':
            return True
        elif response == 'false':
            return False
        else:
            # If response is unclear, default to False (don't hide)
            logger.warning(f"Unexpected AI response for hide decision: {response}")
            return False
    except Exception as e:
        logger.error(f"Error parsing AI hide decision: {e}", exc_info=True)
        return False


def generate_question_from_project(project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Generate a contextual question from a project to learn user preferences
    
    Analyzes a project to detect key disqualifying factors (professions, regions, 
    industries, requirements) and generates a question that can help learn user preferences.
    
    Args:
        project_data: Project data dictionary with name, description, etc.
        
    Returns:
        Question object with question_text, question_type, pattern_to_learn, or None if no pattern detected
    """
    name = project_data.get('name', '')
    description = project_data.get('description', '')
    
    prompt = f"""Analyze the following project that a user just hid. Generate a single, clear question that would help understand why they hid it.

Project Name: {name}
Description: {description}

Identify the most likely reason this project was hidden. Common reasons include:
- Requiring specific professions (e.g., "healthcare professionals", "IT leaders")
- Requiring specific locations/regions (e.g., "California residents", "New York only")
- Requiring specific industries or sectors
- Other specific requirements or disqualifiers

Return ONLY a valid JSON object with no additional text:
{{
  "question_text": "Are you a healthcare professional?",
  "question_type": "profession",
  "pattern": {{
    "keywords": ["healthcare", "medical", "doctor", "nurse"],
    "professions": ["healthcare professionals"],
    "regions": [],
    "industries": ["healthcare"]
  }}
}}

Question types can be: "profession", "region", "industry", or "other"
If no clear pattern is detected, return null or an empty object."""

    response = call_grok_api(prompt)
    if not response:
        return None
    
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
        
        # Check for null or empty responses
        if not response or response.lower() in ('null', 'none', '{}'):
            return None
        
        question_data = json.loads(response)
        
        # Validate that we have required fields
        if not question_data.get('question_text') or not question_data.get('pattern'):
            return None
        
        # Generate a unique question ID based on the pattern
        import hashlib
        pattern_str = json.dumps(question_data.get('pattern', {}), sort_keys=True)
        question_id = hashlib.md5(pattern_str.encode()).hexdigest()[:16]
        question_data['id'] = question_id
        
        return question_data
    except Exception as e:
        logger.error(f"Error parsing question generation response: {e}", exc_info=True)
        return None

