#!/usr/bin/env python3
"""
get-update.py

Fetches fire danger ratings for Greater Sydney Region from NSW RFS feed.
Extracts danger levels and fire ban information for today and tomorrow.

Usage:
    python get-update.py

Output:
    Text message under 140 characters with current fire danger information.
"""

import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict


def fetch_fire_danger_data() -> Optional[ET.Element]:
    """
    Fetch and parse XML data from NSW RFS feed.
    
    Returns:
        Parsed XML root element or None if error occurs.
    """
    url = "https://www.rfs.nsw.gov.au/feeds/fdrToban.xml"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as e:
        print(f"Error fetching data: {e}")
        return None


def extract_greater_sydney_data(root: ET.Element) -> Optional[Dict[str, str]]:
    """
    Extract fire danger data for Greater Sydney Region.
    
    Args:
        root: Parsed XML root element
        
    Returns:
        Dictionary containing danger levels and fire ban information
    """
    for region in root.findall('.//Region'):
        if region.find('Name') is not None and region.find('Name').text == 'Greater Sydney Region':
            return {
                'DangerLevelToday': region.find('DangerLevelToday').text if region.find('DangerLevelToday') is not None else 'Unknown',
                'FireBanToday': region.find('FireBanToday').text if region.find('FireBanToday') is not None else 'Unknown',
                'DangerLevelTomorrow': region.find('DangerLevelTomorrow').text if region.find('DangerLevelTomorrow') is not None else 'Unknown',
                'FireBanTomorrow': region.find('FireBanTomorrow').text if region.find('FireBanTomorrow') is not None else 'Unknown'
            }
    return None


def format_message(data: Dict[str, str]) -> str:
    """
    Format fire danger data into a concise text message under 140 characters.
    
    Args:
        data: Dictionary containing fire danger information
        
    Returns:
        Formatted text message
    """
    today_ban = "BAN" if data['FireBanToday'].lower() == 'yes' else "No ban"
    tomorrow_ban = "BAN" if data['FireBanTomorrow'].lower() == 'yes' else "No ban"
    
    message = (f"Sydney: Today {data['DangerLevelToday']} ({today_ban}), "
               f"Tomor {data['DangerLevelTomorrow']} ({tomorrow_ban})")
    
    # Ensure message is under 140 characters
    return message[:140]


def main() -> None:
    """Main function to execute the fire danger update."""
    root = fetch_fire_danger_data()
    if not root:
        return
    
    data = extract_greater_sydney_data(root)
    if not data:
        print("Greater Sydney Region data not found")
        return
    
    message = format_message(data)
    print(message)


if __name__ == "__main__":
    main()