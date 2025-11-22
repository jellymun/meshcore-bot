#!/usr/bin/env python3
"""
Utility functions for the MeshCore Bot
Shared helper functions used across multiple modules
"""

import re
import hashlib
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


def calculate_packet_hash(raw_hex: str, payload_type: int = None) -> str:
    """
    Calculate hash for packet identification - based on packet.cpp
    Packet hashes are unique to the originally sent message, allowing
    identification of the same message arriving via different paths.
    
    Args:
        raw_hex: Raw packet data as hex string
        payload_type: Optional payload type as integer (if None, extracted from header)
                      Must be numeric value (0-15), not enum or string
        
    Returns:
        16-character hex string (8 bytes) in uppercase, or "0000000000000000" on error
    """
    try:
        # Parse the packet to extract payload type and payload data
        byte_data = bytes.fromhex(raw_hex)
        header = byte_data[0]
        
        # Get payload type from header (bits 2-5)
        if payload_type is None:
            payload_type = (header >> 2) & 0x0F
        else:
            # Ensure payload_type is an integer (handle enum.value if passed)
            if hasattr(payload_type, 'value'):
                payload_type = payload_type.value
            payload_type = int(payload_type) & 0x0F  # Ensure it's 0-15
        
        # Check if transport codes are present
        route_type = header & 0x03
        has_transport = route_type in [0x00, 0x03]  # TRANSPORT_FLOOD or TRANSPORT_DIRECT
        
        # Calculate path length offset dynamically based on transport codes
        offset = 1  # After header
        if has_transport:
            offset += 4  # Skip 4 bytes of transport codes
        
        # Validate we have enough bytes for path_len
        if len(byte_data) <= offset:
            return "0000000000000000"
        
        # Read path_len (1 byte on wire, but stored as uint16_t in C++)
        path_len = byte_data[offset]
        offset += 1
        
        # Validate we have enough bytes for the path
        if len(byte_data) < offset + path_len:
            return "0000000000000000"
        
        # Skip past the path to get to payload
        payload_start = offset + path_len
        
        # Validate we have payload data
        if len(byte_data) <= payload_start:
            return "0000000000000000"
        
        payload_data = byte_data[payload_start:]
        
        # Calculate hash exactly like MeshCore Packet::calculatePacketHash():
        # 1. Payload type (1 byte)
        # 2. Path length (2 bytes as uint16_t, little-endian) - ONLY for TRACE packets (type 9)
        # 3. Payload data
        hash_obj = hashlib.sha256()
        hash_obj.update(bytes([payload_type]))
        
        if payload_type == 9:  # PAYLOAD_TYPE_TRACE
            # C++ does: sha.update(&path_len, sizeof(path_len))
            # path_len is uint16_t, so sizeof(path_len) = 2 bytes
            # Convert path_len to 2-byte little-endian uint16_t
            hash_obj.update(path_len.to_bytes(2, byteorder='little'))
        
        hash_obj.update(payload_data)
        
        # Return first 16 hex characters (8 bytes) in uppercase
        return hash_obj.hexdigest()[:16].upper()
    except Exception as e:
        # Return default hash on error (caller should handle logging)
        return "0000000000000000"


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate haversine distance between two points in kilometers.
    
    Args:
        lat1: Latitude of first point in degrees
        lon1: Longitude of first point in degrees
        lat2: Latitude of second point in degrees
        lon2: Longitude of second point in degrees
        
    Returns:
        Distance in kilometers
    """
    import math
    
    # Convert latitude and longitude from degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth's radius in kilometers
    earth_radius = 6371.0
    return earth_radius * c
