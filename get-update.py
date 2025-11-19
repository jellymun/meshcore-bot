#!/usr/bin/env python3
"""
get-update.py

Fetches fire danger ratings for the Greater Sydney Region from the NSW RFS feed.
Extracts danger levels and fire ban information for today and tomorrow.

Usage:
    python get-update.py

Output:
    Text message under 140 characters with current fire danger information.
"""

import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict
import sys

# --- Configuration Constants ---
RFS_FEED_URL = "https://www.rfs.nsw.gov.au/feeds/fdrToban.xml"
# Set to the exact, case-sensitive name found in the provided XML data
TARGET_DISTRICT_NAME = "Greater Sydney Region" 

# --- Helper Function ---

def get_element_text(parent: ET.Element, tag_name: str) -> str:
    """Safely get text from a child element, or 'Unknown'."""
    element = parent.find(tag_name)
    # Return stripped text if available, otherwise 'Unknown'
    return element.text.strip() if element is not None and element.text else 'Unknown'

# --- Main Functions ---

def fetch_fire_danger_data() -> Optional[ET.Element]:
    """
    Fetch and parse XML data from NSW RFS feed.
    
    Returns:
        Parsed XML root element or None if error occurs.
    """
    try:
        response = requests.get(RFS_FEED_URL, timeout=10)
        response.raise_for_status() 
        return ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as e:
        # Print error to stderr
        print(f"Error fetching data: {e}", file=sys.stderr) 
        return None


def extract_greater_sydney_data(root: ET.Element) -> Optional[Dict[str, str]]:
    """
    Extract fire danger data for the specified district ('Greater Sydney Region').
    
    Note: Searches for <District> tags as per the current RFS feed structure.
    """
    # FIX: Changed search from './/Region' to './/District'
    for district in root.findall('.//District'):
        name_text = get_element_text(district, 'Name')
        
        # Strict case-sensitive match against the confirmed district name
        if name_text == TARGET_DISTRICT_NAME:
            return {
                'DangerLevelToday': get_element_text(district, 'DangerLevelToday'),
                'FireBanToday': get_element_text(district, 'FireBanToday'),
                'DangerLevelTomorrow': get_element_text(district, 'DangerLevelTomorrow'),
                'FireBanTomorrow': get_element_text(district, 'FireBanTomorrow')
            }
    return None


def format_message(data: Dict[str, str]) -> str:
    """
    Format fire danger data into a concise text message under 140 characters.
    """
    # Normalize 'Yes'/'No' to concise ban status
    today_ban = "BAN" if data['FireBanToday'].lower() == 'yes' else "No ban"
    tomorrow_ban = "BAN" if data['FireBanTomorrow'].lower() == 'yes' else "No ban"
    
    # Use 'Sydney' in the output message for brevity
    message = (f"Sydney Region FDI : Today {data['DangerLevelToday']} ({today_ban}), "
               f"Tomor {data['DangerLevelTomorrow']} ({tomorrow_ban})")
    
    # Ensure message is under 140 characters
    return message[:140]


def main() -> None:
    """Main function to execute the fire danger update."""
    root = fetch_fire_danger_data()
    
    # Explicit check for None to avoid DeprecationWarning
    if root is None: 
        return
    
    data = extract_greater_sydney_data(root)
    if not data:
        # Report the name we were unable to find
        print(f"Region data for '{TARGET_DISTRICT_NAME}' not found in feed.")
        return
    
    message = format_message(data)
    print(message)


if __name__ == "__main__":
    main()
