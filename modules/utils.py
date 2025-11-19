#!/usr/bin/env python3
"""
Utility functions for the MeshCore Bot
Shared helper functions used across multiple modules
"""

import re
from typing import Optional


def abbreviate_location(location: str, max_length: int = 20) -> str:
    """
    Abbreviate a location string to fit within character limits.
    
    Args:
        location: The location string to abbreviate
        max_length: Maximum length for the abbreviated string
        
    Returns:
        Abbreviated location string
    """
    if not location:
        return location
    
    # Apply common abbreviations first
    abbreviated = location
    
    abbreviations = [
        ('Central Business District', 'CBD'),
        ('Business District', 'BD'),
        ('British Columbia', 'BC'),
        ('United States', 'USA'),
        ('United Kingdom', 'UK'),
        ('Washington', 'WA'),
        ('California', 'CA'),
        ('New York', 'NY'),
        ('Texas', 'TX'),
        ('Florida', 'FL'),
        ('Illinois', 'IL'),
        ('Pennsylvania', 'PA'),
        ('Ohio', 'OH'),
        ('Georgia', 'GA'),
        ('North Carolina', 'NC'),
        ('Michigan', 'MI'),
        ('New Jersey', 'NJ'),
        ('Virginia', 'VA'),
        ('Tennessee', 'TN'),
        ('Indiana', 'IN'),
        ('Arizona', 'AZ'),
        ('Massachusetts', 'MA'),
        ('Missouri', 'MO'),
        ('Maryland', 'MD'),
        ('Wisconsin', 'WI'),
        ('Colorado', 'CO'),
        ('Minnesota', 'MN'),
        ('South Carolina', 'SC'),
        ('Alabama', 'AL'),
        ('Louisiana', 'LA'),
        ('Kentucky', 'KY'),
        ('Oregon', 'OR'),
        ('Oklahoma', 'OK'),
        ('Connecticut', 'CT'),
        ('Utah', 'UT'),
        ('Iowa', 'IA'),
        ('Nevada', 'NV'),
        ('Arkansas', 'AR'),
        ('Mississippi', 'MS'),
        ('Kansas', 'KS'),
        ('New Mexico', 'NM'),
        ('Nebraska', 'NE'),
        ('West Virginia', 'WV'),
        ('Idaho', 'ID'),
        ('Hawaii', 'HI'),
        ('New Hampshire', 'NH'),
        ('Maine', 'ME'),
        ('Montana', 'MT'),
        ('Rhode Island', 'RI'),
        ('Delaware', 'DE'),
        ('South Dakota', 'SD'),
        ('North Dakota', 'ND'),
        ('Alaska', 'AK'),
        ('Vermont', 'VT'),
        ('Wyoming', 'WY')
    ]
    
    # Apply abbreviations in order
    for full_term, abbrev in abbreviations:
        if full_term in abbreviated:
            abbreviated = abbreviated.replace(full_term, abbrev)
    
    # If still too long after abbreviations, try to truncate intelligently
    if len(abbreviated) > max_length:
        # Try to keep the most important part (usually the city name)
        parts = abbreviated.split(', ')
        if len(parts) > 1:
            # Keep the first part (usually city) and truncate if needed
            first_part = parts[0]
            if len(first_part) <= max_length:
                abbreviated = first_part
            else:
                abbreviated = first_part[:max_length-3] + '...'
        else:
            # Just truncate with ellipsis
            abbreviated = abbreviated[:max_length-3] + '...'
    
    return abbreviated


def truncate_string(text: str, max_length: int, ellipsis: str = '...') -> str:
    """
    Truncate a string to a maximum length with ellipsis.
    
    Args:
        text: The string to truncate
        max_length: Maximum length including ellipsis
        ellipsis: String to append when truncating
        
    Returns:
        Truncated string
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(ellipsis)] + ellipsis


def format_location_for_display(city: Optional[str], state: Optional[str] = None, 
                               country: Optional[str] = None, max_length: int = 20) -> Optional[str]:
    """
    Format location data for display with intelligent abbreviation.
    
    Args:
        city: City name (may include neighborhood/district)
        state: State/province name
        country: Country name
        max_length: Maximum length for the formatted location
        
    Returns:
        Formatted location string or None if no location data
    """
    if not city:
        return None
    
    # Start with city (which may include neighborhood)
    location_parts = [city]
    
    # Add state if available and different from city
    if state and state not in location_parts:
        location_parts.append(state)
    
    # Join parts and abbreviate if needed
    full_location = ', '.join(location_parts)
    return abbreviate_location(full_location, max_length)


def get_major_city_queries(city: str, state_abbr: Optional[str] = None) -> list:
    """
    Get prioritized geocoding queries for major cities that have multiple locations.
    This helps ensure that common city names resolve to the most likely major city
    rather than a small town with the same name.
    
    Args:
        city: City name (normalized, lowercase)
        state_abbr: Optional state abbreviation (e.g., "CA", "NY")
        
    Returns:
        List of geocoding query strings in priority order
    """
    city_lower = city.lower().strip()
    
    # Comprehensive mapping of major cities with multiple locations
    # Format: 'city_name': [list of queries in priority order]
    major_city_mappings = {
        'new york': ['New York, NY, USA', 'New York City, NY, USA'],
        'los angeles': ['Los Angeles, CA, USA'],
        'chicago': ['Chicago, IL, USA'],
        'houston': ['Houston, TX, USA'],
        'phoenix': ['Phoenix, AZ, USA'],
        'philadelphia': ['Philadelphia, PA, USA'],
        'san antonio': ['San Antonio, TX, USA'],
        'san diego': ['San Diego, CA, USA'],
        'dallas': ['Dallas, TX, USA'],
        'san jose': ['San Jose, CA, USA'],
        'austin': ['Austin, TX, USA'],
        'jacksonville': ['Jacksonville, FL, USA'],
        'san francisco': ['San Francisco, CA, USA'],
        'columbus': ['Columbus, OH, USA'],
        'fort worth': ['Fort Worth, TX, USA'],
        'charlotte': ['Charlotte, NC, USA'],
        'seattle': ['Seattle, WA, USA'],
        'denver': ['Denver, CO, USA'],
        'washington': ['Washington, DC, USA'],
        'boston': ['Boston, MA, USA'],
        'el paso': ['El Paso, TX, USA'],
        'detroit': ['Detroit, MI, USA'],
        'nashville': ['Nashville, TN, USA'],
        'portland': ['Portland, OR, USA', 'Portland, ME, USA'],
        'oklahoma city': ['Oklahoma City, OK, USA'],
        'las vegas': ['Las Vegas, NV, USA'],
        'memphis': ['Memphis, TN, USA'],
        'louisville': ['Louisville, KY, USA'],
        'baltimore': ['Baltimore, MD, USA'],
        'milwaukee': ['Milwaukee, WI, USA'],
        'albuquerque': ['Albuquerque, NM, USA'],
        'tucson': ['Tucson, AZ, USA'],
        'fresno': ['Fresno, CA, USA'],
        'sacramento': ['Sacramento, CA, USA'],
        'kansas city': ['Kansas City, MO, USA', 'Kansas City, KS, USA'],
        'mesa': ['Mesa, AZ, USA'],
        'atlanta': ['Atlanta, GA, USA'],
        'omaha': ['Omaha, NE, USA'],
        'colorado springs': ['Colorado Springs, CO, USA'],
        'raleigh': ['Raleigh, NC, USA'],
        'virginia beach': ['Virginia Beach, VA, USA'],
        'miami': ['Miami, FL, USA'],
        'oakland': ['Oakland, CA, USA'],
        'minneapolis': ['Minneapolis, MN, USA'],
        'tulsa': ['Tulsa, OK, USA'],
        'cleveland': ['Cleveland, OH, USA'],
        'wichita': ['Wichita, KS, USA'],
        'arlington': ['Arlington, TX, USA', 'Arlington, VA, USA'],
        'new orleans': ['New Orleans, LA, USA'],
        'honolulu': ['Honolulu, HI, USA'],
        # Cities with multiple locations that need disambiguation
        'albany': ['Albany, NY, USA', 'Albany, OR, USA', 'Albany, CA, USA'],
        'springfield': ['Springfield, IL, USA', 'Springfield, MO, USA', 'Springfield, MA, USA'],
        'franklin': ['Franklin, TN, USA', 'Franklin, MA, USA'],
        'georgetown': ['Georgetown, TX, USA', 'Georgetown, SC, USA'],
        'madison': ['Madison, WI, USA', 'Madison, AL, USA'],
        'auburn': ['Auburn, AL, USA', 'Auburn, WA, USA'],
        'troy': ['Troy, NY, USA', 'Troy, MI, USA'],
        'clinton': ['Clinton, IA, USA', 'Clinton, MS, USA'],
        'paris': ['Paris, TX, USA', 'Paris, IL, USA', 'Paris, TN, USA'],
    }
    
    # Check if this is a major city
    if city_lower in major_city_mappings:
        queries = major_city_mappings[city_lower].copy()
        
        # If state abbreviation was provided, prioritize queries with that state
        if state_abbr:
            state_upper = state_abbr.upper()
            # Move matching state queries to the front
            matching = [q for q in queries if f', {state_upper},' in q or q.endswith(f', {state_upper}')]
            non_matching = [q for q in queries if q not in matching]
            if matching:
                return matching + non_matching
        
        return queries
    
    # Not a major city - return empty list (caller should use standard geocoding)
    return []
