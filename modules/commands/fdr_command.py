#!/usr/bin/env python3
"""
FDR Command - Fetches and displays Fire Danger Ratings for Greater Sydney Region
or a user-specified district/council area.
"""

from .base_command import BaseCommand
from ..models import MeshMessage # Keep the import for runtime use

import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict
import asyncio
import sys

# --- Configuration Constants ---
RFS_FEED_URL = "https://www.rfs.nsw.gov.au/feeds/fdrToban.xml"
# Default District name if no argument is provided
DEFAULT_DISTRICT_NAME = "Greater Sydney Region" 
MAX_TIMEOUT = 10 

class FdrCommand(BaseCommand):
    """Command to get Fire Danger Ratings for the Greater Sydney Region or a specified district"""
    
    # Plugin metadata
    name = "fdr"
    keywords = ['fdr', 'fire', 'firedanger']
    description = f"Get today and tomorrow's Fire Danger Rating. Defaults to '{DEFAULT_DISTRICT_NAME}'. Usage: !fdr <Region Name>"
    category = "info"
    
    def __init__(self, bot):
        super().__init__(bot)

    # --- Helper Methods ---

    def _get_element_text(self, parent: ET.Element, tag_name: str) -> str:
        """Safely get text from a child element, or 'Unknown'."""
        element = parent.find(tag_name)
        return element.text.strip() if element is not None and element.text else 'Unknown'

    def _fetch_data(self) -> Optional[ET.Element]:
        """
        Synchronously fetch and parse XML data from NSW RFS feed.
        This must be run in a separate thread/executor.
        """
        try:
            self.bot.logger.debug(f"FDR: Fetching data from {RFS_FEED_URL}")
            response = requests.get(RFS_FEED_URL, timeout=MAX_TIMEOUT)
            response.raise_for_status() 
            return ET.fromstring(response.content)
        except requests.RequestException as e:
            self.bot.logger.error(f"FDR: Request error (Check internet/URL): {e}")
            return None
        except ET.ParseError as e:
            self.bot.logger.error(f"FDR: XML Parsing error: {e}")
            return None


    def _extract_data(self, root: ET.Element, target_name: str) -> Optional[Dict[str, str]]:
        """
        Synchronously extract fire danger data for the specified district.
        """
        # Searches for <District> tags as per the current RFS feed structure.
        for district in root.findall('.//District'):
            name_text = self._get_element_text(district, 'Name')
            
            # Strict case-sensitive match against the target district name
            if name_text == target_name:
                return {
                    'DangerLevelToday': self._get_element_text(district, 'DangerLevelToday'),
                    'FireBanToday': self._get_element_text(district, 'FireBanToday'),
                    'DangerLevelTomorrow': self._get_element_text(district, 'DangerLevelTomorrow'),
                    'FireBanTomorrow': self._get_element_text(district, 'FireBanTomorrow')
                }
        return None


    def _format_fdr_response(self, data: Dict[str, str], district_name: str) -> str:
        """
        Format fire danger data into a concise text message.
        """
        today_ban = "BAN" if data['FireBanToday'].lower() == 'yes' else "No ban"
        tomorrow_ban = "BAN" if data['FireBanTomorrow'].lower() == 'yes' else "No ban"
        
        # Use the requested district name in the output message
        message = (f"🔥 {district_name}: Today {data['DangerLevelToday']} ({today_ban}), "
                   f"Tomorrow {data['DangerLevelTomorrow']} ({tomorrow_ban})")
        
        return message


    # --- Execution Method ---

    # Using 'MeshMessage' as a string to resolve forward reference/type hint issue
    async def execute(self, message: 'MeshMessage') -> bool:
        """Execute the FDR command, optionally using a user-supplied district name or message location"""
        
        # Default to the primary district
        target_name = DEFAULT_DISTRICT_NAME
        
        # Robustly obtain text/content from MeshMessage objects (message implementations vary)
        # Prefer message.content (the project's MessageHandler uses 'content'), but accept other attrs.
        text_value = getattr(message, 'content', None)
        if not text_value:
            # try common alternatives
            for attr in ('text', 'body', 'message', 'msg'):
                text_value = getattr(message, attr, None)
                if isinstance(text_value, str) and text_value.strip():
                    break
            else:
                # try payload-like attribute
                payload = getattr(message, 'payload', None)
                if isinstance(payload, dict):
                    for key in ('text', 'content', 'body', 'message'):
                        tv = payload.get(key)
                        if isinstance(tv, str) and tv.strip():
                            text_value = tv
                            break
        if not isinstance(text_value, str):
            text_value = ''

        # 1. Check for text arguments (highest priority)
        # Split text_value once to separate command (e.g., 'fdr') from arguments (e.g., 'Greater Hunter')
        command_parts = text_value.split(maxsplit=1) if text_value else []
        
        if len(command_parts) > 1:
            # Use the explicit text argument
            target_name = command_parts[1].strip()
        
        # 2. Fallback: If no argument was provided, check the message's built-in location
        elif hasattr(message, 'location') and getattr(message, 'location'):
            # Use the location from the MeshMessage object
            target_name = message.location
            
        response = None
        
        try:
            # 3. Fetch and Parse Data
            root = await asyncio.to_thread(self._fetch_data)
            
            if root is None:
                response = "❌ Failed to fetch fire danger data. Check logs for details."
                await self.send_response(message, response)
                return False

            # 4. Extract Data for the Target Name
            # Pass the dynamic target_name to the extraction function
            data = await asyncio.to_thread(self._extract_data, root, target_name)

            # 5. Format Response
            if data is None:
                response = f"⚠️ Fire data for '{target_name}' not found in the feed. Check the full region list for correct spelling."
            else:
                # Pass the target_name to the formatting function for clear output
                response = self._format_fdr_response(data, target_name)

            await self.send_response(message, response)
            return True
                
        except Exception as e:
            error_msg = f"Error executing FDR command: {e}"
            # Use bot.logger to avoid printing raw error to user unless necessary
            self.bot.logger.error(error_msg) 
            await self.send_response(message, "❌ An unexpected error occurred while processing the fire data.")
            return False
    
    def get_help_text(self):
        """Get help text for this command"""
        return self.description
