#!/usr/bin/env python3
"""
Global Weather command for the MeshCore Bot
Provides worldwide weather information using Open-Meteo API
"""

import re
import requests
from datetime import datetime
from geopy.geocoders import Nominatim
from ..base_command import BaseCommand
from ...models import MeshMessage


class GlobalWxCommand(BaseCommand):
    """Handles global weather commands with city/location support"""
    
    # Plugin metadata
    name = "gwx"
    keywords = ['gwx', 'globalweather', 'gwxa']
    description = "Get weather information for any global location (usage: gwx Tokyo)"
    category = "weather"
    cooldown_seconds = 5  # 5 second cooldown per user to prevent API abuse
    
    # Error constants
    ERROR_FETCHING_DATA = "Error fetching weather data"
    NO_ALERTS = "No weather alerts available"
    
    def __init__(self, bot):
        super().__init__(bot)
        self.url_timeout = 10  # seconds
        
        # Per-user cooldown tracking
        self.user_cooldowns = {}  # user_id -> last_execution_time
        
        # Get default state and country from config for city disambiguation
        self.default_state = self.bot.config.get('Weather', 'default_state', fallback='WA')
        self.default_country = self.bot.config.get('Weather', 'default_country', fallback='US')
        
        # Get unit preferences from config
        self.temperature_unit = self.bot.config.get('Weather', 'temperature_unit', fallback='fahrenheit').lower()
        self.wind_speed_unit = self.bot.config.get('Weather', 'wind_speed_unit', fallback='mph').lower()
        self.precipitation_unit = self.bot.config.get('Weather', 'precipitation_unit', fallback='inch').lower()
        
        # Validate units
        if self.temperature_unit not in ['fahrenheit', 'celsius']:
            self.logger.warning(f"Invalid temperature_unit '{self.temperature_unit}', using 'fahrenheit'")
            self.temperature_unit = 'fahrenheit'
        if self.wind_speed_unit not in ['mph', 'kmh', 'ms']:
            self.logger.warning(f"Invalid wind_speed_unit '{self.wind_speed_unit}', using 'mph'")
            self.wind_speed_unit = 'mph'
        if self.precipitation_unit not in ['inch', 'mm']:
            self.logger.warning(f"Invalid precipitation_unit '{self.precipitation_unit}', using 'inch'")
            self.precipitation_unit = 'inch'
        
        # Initialize geocoder
        self.geolocator = Nominatim(user_agent="meshcore-bot")
        
        # Get database manager for geocoding cache
        self.db_manager = bot.db_manager
    
    def get_help_text(self) -> str:
        return "Usage: gwx <location> - Get weather for any global location (city, country, or coordinates)"
    
    def matches_keyword(self, message: MeshMessage) -> bool:
        """Check if message starts with a weather keyword"""
        content = message.content.strip()
        if content.startswith('!'):
            content = content[1:].strip()
        content_lower = content.lower()
        for keyword in self.keywords:
            if content_lower.startswith(keyword + ' '):
                return True
        return False
    
    def can_execute(self, message: MeshMessage) -> bool:
        """Override cooldown check to be per-user instead of per-command-instance"""
        if self.requires_dm and not message.is_dm:
            return False
        
        # Check per-user cooldown
        if self.cooldown_seconds > 0:
            import time
            current_time = time.time()
            user_id = message.sender_id
            
            if user_id in self.user_cooldowns:
                last_execution = self.user_cooldowns[user_id]
                if (current_time - last_execution) < self.cooldown_seconds:
                    return False
        
        return True
    
    def get_remaining_cooldown(self, user_id: str) -> int:
        """Get remaining cooldown time for a specific user"""
        if self.cooldown_seconds <= 0:
            return 0
        
        import time
        current_time = time.time()
        if user_id in self.user_cooldowns:
            last_execution = self.user_cooldowns[user_id]
            elapsed = current_time - last_execution
            remaining = self.cooldown_seconds - elapsed
            return max(0, int(remaining))
        
        return 0
    
    def _record_execution(self, user_id: str):
        """Record the execution time for a specific user"""
        import time
        self.user_cooldowns[user_id] = time.time()
    
    async def execute(self, message: MeshMessage) -> bool:
        """Execute the weather command"""
        content = message.content.strip()
        
        # Parse the command to extract location
        parts = content.split(maxsplit=1)
        if len(parts) < 2:
            await self.send_response(message, "Usage: gwx <location> - Example: gwx Tokyo or gwx Paris, France")
            return True
        
        location = parts[1].strip()
        
        try:
            # Record execution for this user
            self._record_execution(message.sender_id)
            
            # Get weather data for the location
            weather_data = await self.get_weather_for_location(location)
            
            # Check if we need to send multiple messages (for alerts)
            if isinstance(weather_data, tuple) and weather_data[0] == "multi_message":
                # Send weather data first
                await self.send_response(message, weather_data[1])
                
                # Wait for bot TX rate limiter
                import asyncio
                rate_limit = self.bot.config.getfloat('Bot', 'bot_tx_rate_limit_seconds', fallback=1.0)
                sleep_time = max(rate_limit + 1.0, 2.0)
                await asyncio.sleep(sleep_time)
                
                # Send alerts
                await self.send_response(message, weather_data[2])
            else:
                await self.send_response(message, weather_data)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in global weather command: {e}")
            await self.send_response(message, f"Error getting weather data: {e}")
            return True
    
    async def get_weather_for_location(self, location: str) -> str:
        """Get weather data for any global location"""
        try:
            # Convert location to lat/lon with address details
            result = self.geocode_location(location)
            if not result or result[0] is None or result[1] is None:
                return f"Could not find location '{location}'"
            
            lat, lon, address_info, geocode_result = result
            
            # Format location name for display
            location_display = self._format_location_display(address_info, geocode_result, location)
            
            # Get weather forecast from Open-Meteo
            weather_text = self.get_open_meteo_weather(lat, lon)
            if weather_text == self.ERROR_FETCHING_DATA:
                return "Error fetching weather data from Open-Meteo"
            
            # Check for severe weather warnings (Open-Meteo doesn't provide detailed alerts,
            # but we can infer from extreme conditions)
            alert_text = self._check_extreme_conditions(weather_text)
            
            if alert_text:
                # Return multi-message format
                return ("multi_message", f"{location_display}: {weather_text}", alert_text)
            
            return f"{location_display}: {weather_text}"
            
        except Exception as e:
            self.logger.error(f"Error getting weather for {location}: {e}")
            return f"Error getting weather data: {e}"
    
    def geocode_location(self, location: str) -> tuple:
        """Convert location string to lat/lon with address details"""
        try:
            # Check cache first
            cache_key = location.lower().strip()
            cached_lat, cached_lon = self.db_manager.get_cached_geocoding(cache_key)
            
            if cached_lat is not None and cached_lon is not None:
                self.logger.debug(f"Using cached geocoding for {location}")
                # Get address details with reverse geocoding
                try:
                    reverse_location = self.geolocator.reverse(f"{cached_lat}, {cached_lon}")
                    if reverse_location:
                        address_info = reverse_location.raw.get('address', {})
                        # Store the full geocode result for display name
                        return cached_lat, cached_lon, address_info, reverse_location
                except Exception:
                    pass
                return cached_lat, cached_lon, {}, None
            
            # Try geocoding with different strategies
            geocode_result = None
            
            # Strategy 1: Try as-is
            geocode_result = self.geolocator.geocode(location)
            
            # Strategy 2: If no result and no country specified, try with default country
            if not geocode_result and ',' not in location:
                geocode_result = self.geolocator.geocode(f"{location}, {self.default_country}")
            
            if not geocode_result:
                return None, None, None, None
            
            lat, lon = geocode_result.latitude, geocode_result.longitude
            address_info = geocode_result.raw.get('address', {})
            
            # Cache the result
            self.db_manager.cache_geocoding(cache_key, lat, lon)
            
            return lat, lon, address_info, geocode_result
            
        except Exception as e:
            self.logger.error(f"Error geocoding location {location}: {e}")
            return None, None, None, None
    
    def _format_location_display(self, address_info: dict, geocode_result, fallback: str) -> str:
        """Format location name for display from address info - returns 'City, CountryCode' format"""
        # Get country code first (prefer this over full country name)
        country_code = ''
        if address_info:
            country_code = address_info.get('country_code', '').upper()
        
        # Try to get city name from address_info (this is more reliable than display_name)
        city = None
        if address_info:
            # Try various address fields in order of preference
            city = (address_info.get('city') or 
                    address_info.get('town') or 
                    address_info.get('village') or 
                    address_info.get('municipality') or
                    address_info.get('city_district'))
            
            # If we still don't have a city, try parsing from display_name
            if not city and geocode_result and hasattr(geocode_result, 'raw'):
                display_name = geocode_result.raw.get('display_name', '')
                if display_name:
                    # Parse display_name - usually format is "Place, City, State/Province, Country"
                    # We want the city, not the specific place
                    parts = [p.strip() for p in display_name.split(',')]
                    # Skip the first part (specific location) and look for city in later parts
                    for i, part in enumerate(parts[1:], 1):
                        # Check if this part looks like a city (not a state/province or country)
                        if i < len(parts) - 1:  # Not the last part (country)
                            city = part
                            break
        
        # If still no city, try extracting from display_name first part (but clean it up)
        if not city and geocode_result and hasattr(geocode_result, 'raw'):
            display_name = geocode_result.raw.get('display_name', '')
            if display_name:
                parts = [p.strip() for p in display_name.split(',')]
                if parts:
                    # Take first part but try to extract city name
                    first_part = parts[0]
                    # Remove common venue/location suffixes
                    for suffix in [' Terminal', ' Station', ' Airport', ' Hotel', ' Building', 
                                   ' Plaza', ' Center', ' Centre', ' Park', ' Square']:
                        if suffix in first_part:
                            first_part = first_part.replace(suffix, '').strip()
                    city = first_part
        
        # For US locations, include state abbreviation
        if country_code == 'US':
            state = None
            if address_info:
                state = address_info.get('state')
            if city and state:
                state_abbrev = self._get_state_abbreviation(state)
                return f"{city}, {state_abbrev}"
            elif city:
                return f"{city}, US"
        
        # For international locations, always use country code if available
        if city:
            if country_code:
                return f"{city}, {country_code}"
            elif address_info and address_info.get('country'):
                # Fallback to country name if no code available
                country = address_info.get('country')
                # Shorten very long country names
                if len(country) > 15:
                    return f"{city}, {country[:15]}"
                return f"{city}, {country}"
            else:
                return city
        
        # Final fallback: try to extract from input and capitalize
        if fallback:
            # Try to extract city name from input (before first comma if present)
            parts = fallback.split(',')
            city_part = parts[0].strip().title()
            # Remove common suffixes
            for suffix in [' Terminal', ' Station', ' Airport', ' Hotel', ' Building']:
                if suffix in city_part:
                    city_part = city_part.replace(suffix, '').strip()
            
            if country_code:
                return f"{city_part}, {country_code}"
            elif len(parts) > 1:
                # Try to get country from input
                country_part = parts[-1].strip()
                return f"{city_part}, {country_part[:10]}"  # Limit country name length
            return city_part
        
        return fallback.title()
    
    def _get_state_abbreviation(self, state: str) -> str:
        """Convert full state name to abbreviation"""
        state_map = {
            'Washington': 'WA', 'California': 'CA', 'New York': 'NY', 'Texas': 'TX',
            'Florida': 'FL', 'Illinois': 'IL', 'Pennsylvania': 'PA', 'Ohio': 'OH',
            'Georgia': 'GA', 'North Carolina': 'NC', 'Michigan': 'MI', 'New Jersey': 'NJ',
            'Virginia': 'VA', 'Tennessee': 'TN', 'Indiana': 'IN', 'Arizona': 'AZ',
            'Massachusetts': 'MA', 'Missouri': 'MO', 'Maryland': 'MD', 'Wisconsin': 'WI',
            'Colorado': 'CO', 'Minnesota': 'MN', 'South Carolina': 'SC', 'Alabama': 'AL',
            'Louisiana': 'LA', 'Kentucky': 'KY', 'Oregon': 'OR', 'Oklahoma': 'OK',
            'Connecticut': 'CT', 'Utah': 'UT', 'Iowa': 'IA', 'Nevada': 'NV',
            'Arkansas': 'AR', 'Mississippi': 'MS', 'Kansas': 'KS', 'New Mexico': 'NM',
            'Nebraska': 'NE', 'West Virginia': 'WV', 'Idaho': 'ID', 'Hawaii': 'HI',
            'New Hampshire': 'NH', 'Maine': 'ME', 'Montana': 'MT', 'Rhode Island': 'RI',
            'Delaware': 'DE', 'South Dakota': 'SD', 'North Dakota': 'ND', 'Alaska': 'AK',
            'Vermont': 'VT', 'Wyoming': 'WY'
        }
        return state_map.get(state, state)
    
    def get_open_meteo_weather(self, lat: float, lon: float) -> str:
        """Get weather forecast from Open-Meteo API"""
        try:
            # Open-Meteo API endpoint with current weather and forecast
            api_url = "https://api.open-meteo.com/v1/forecast"
            
            params = {
                'latitude': lat,
                'longitude': lon,
                'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m,dewpoint_2m,visibility,surface_pressure',
                'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max',
                'hourly': 'temperature_2m,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m',
                'temperature_unit': self.temperature_unit,
                'wind_speed_unit': self.wind_speed_unit,
                'precipitation_unit': self.precipitation_unit,
                'timezone': 'auto',
                'forecast_days': 2
            }
            
            response = requests.get(api_url, params=params, timeout=self.url_timeout)
            
            if not response.ok:
                self.logger.warning(f"Error fetching weather from Open-Meteo: {response.status_code}")
                return self.ERROR_FETCHING_DATA
            
            data = response.json()
            
            # Check units in response to verify API is respecting our unit requests
            current_units = data.get('current_units', {})
            temp_unit = current_units.get('temperature_2m', '°F')
            visibility_unit = current_units.get('visibility', 'm')
            
            # Extract current conditions
            current = data.get('current', {})
            daily = data.get('daily', {})
            hourly = data.get('hourly', {})
            
            # Current conditions - API should return in Fahrenheit when requested
            temp = int(current.get('temperature_2m', 0))
            feels_like = int(current.get('apparent_temperature', temp))
            dewpoint = current.get('dewpoint_2m')
            humidity = int(current.get('relative_humidity_2m', 0))
            wind_speed = int(current.get('wind_speed_10m', 0))
            wind_direction = self._degrees_to_direction(current.get('wind_direction_10m', 0))
            wind_gusts = int(current.get('wind_gusts_10m', 0))
            visibility = current.get('visibility')
            pressure = current.get('surface_pressure')
            weather_code = current.get('weather_code', 0)
            
            # Convert visibility to miles based on actual unit from API
            # API returns visibility in feet when using imperial units
            if visibility is not None:
                if visibility_unit == 'ft' or 'ft' in str(visibility_unit).lower():
                    # Convert from feet to miles (1 mile = 5280 feet)
                    visibility_mi = visibility / 5280.0
                else:
                    # Assume meters, convert to miles (1 mile = 1609.34 meters)
                    visibility_mi = visibility / 1609.34
            else:
                visibility_mi = None
            
            # Pressure validation - account for high elevation locations
            # Normal sea level pressure is 1013 hPa, range is typically 950-1050 hPa
            # At high elevations (e.g., 2500m), pressure can be 750-800 hPa, which is normal
            # Only filter out extremely low pressures (< 600 hPa) which would be invalid
            if pressure is not None and pressure < 600:
                self.logger.warning(f"Extremely low pressure value: {pressure} hPa - might be invalid")
                pressure = None
            
            # Get weather description and emoji
            weather_desc = self._get_weather_description(weather_code)
            weather_emoji = self._get_weather_emoji(weather_code)
            
            # Determine temperature unit symbol
            temp_symbol = "°F" if self.temperature_unit == 'fahrenheit' else "°C"
            
            # Determine if it's day or night for forecast period name
            now = datetime.now()
            hour = now.hour
            if 6 <= hour < 18:
                period_name = "Today"
            else:
                period_name = "Tonight"
            
            # Build current weather string
            weather = f"{period_name}: {weather_emoji}{weather_desc} {temp}{temp_symbol}"
            
            # Add feels like if significantly different
            if abs(feels_like - temp) >= 5:
                weather += f" (feels {feels_like}{temp_symbol})"
            
            # Add wind info (always show if >= 3 mph, show gusts if significant)
            if wind_speed >= 3:
                weather += f" {wind_direction}{wind_speed}"
                if wind_gusts > wind_speed + 3:
                    weather += f"G{wind_gusts}"
            
            # Add humidity
            weather += f" {humidity}%RH"
            
            # Add additional conditions if space allows
            conditions = []
            
            # Add dew point
            if dewpoint is not None:
                dewpoint_val = int(dewpoint)
                conditions.append(f"💧{dewpoint_val}{temp_symbol}")
            
            # Add visibility (already converted to miles above)
            if visibility_mi is not None and visibility_mi > 0:
                # Cap visibility at 20 miles for display (beyond that is essentially unlimited)
                visibility_display = int(visibility_mi)
                if visibility_display > 20:
                    visibility_display = 20
                conditions.append(f"👁️{visibility_display}mi")
            
            # Add pressure (convert from hPa to display format)
            if pressure is not None:
                pressure_hpa = int(pressure)
                conditions.append(f"📊{pressure_hpa}hPa")
            
            # Add conditions to weather string if space allows
            if conditions and len(weather) < 120:
                weather += " " + " ".join(conditions)
            
            # Add forecast for today/tonight and tomorrow
            # API should return temperatures in Fahrenheit when requested
            if daily:
                today_high = int(daily['temperature_2m_max'][0])
                today_low = int(daily['temperature_2m_min'][0])
                
                weather += f" | {period_name}: {today_high}{temp_symbol}/{today_low}{temp_symbol}"
                
                # Add tomorrow if space allows (check length more carefully)
                if len(daily['temperature_2m_max']) > 1:
                    tomorrow_high = int(daily['temperature_2m_max'][1])
                    tomorrow_low = int(daily['temperature_2m_min'][1])
                    
                    tomorrow_code = daily['weather_code'][1]
                    tomorrow_emoji = self._get_weather_emoji(tomorrow_code)
                    
                    # Get tomorrow's period name
                    tomorrow_period = "Tomorrow"
                    tomorrow_str = f" | {tomorrow_period}: {tomorrow_emoji}{tomorrow_high}{temp_symbol}/{tomorrow_low}{temp_symbol}"
                    
                    # Only add if we have space (leave room for potential precipitation)
                    if len(weather + tomorrow_str) < 180:  # Increased limit to prevent truncation
                        weather += tomorrow_str
                        
                        # Add precipitation probability if significant and space allows
                        if len(daily.get('precipitation_probability_max', [])) > 1:
                            precip_prob = daily['precipitation_probability_max'][1]
                            if precip_prob >= 30:
                                precip_str = f" 🌦️{precip_prob}%"
                                if len(weather + precip_str) <= 200:  # Reasonable message length limit
                                    weather += precip_str
            
            return weather
            
        except Exception as e:
            self.logger.error(f"Error fetching Open-Meteo weather: {e}")
            return self.ERROR_FETCHING_DATA
    
    def _degrees_to_direction(self, degrees: float) -> str:
        """Convert wind direction in degrees to compass direction with emoji"""
        if degrees is None:
            return ""
        
        directions = [
            (0, "⬆️N"), (22.5, "↗️NE"), (45, "↗️NE"), (67.5, "➡️E"),
            (90, "➡️E"), (112.5, "↘️SE"), (135, "↘️SE"), (157.5, "⬇️S"),
            (180, "⬇️S"), (202.5, "↙️SW"), (225, "↙️SW"), (247.5, "⬅️W"),
            (270, "⬅️W"), (292.5, "↖️NW"), (315, "↖️NW"), (337.5, "⬆️N"),
            (360, "⬆️N")
        ]
        
        # Find closest direction
        for i in range(len(directions) - 1):
            if directions[i][0] <= degrees < directions[i + 1][0]:
                return directions[i][1]
        
        return "⬆️N"  # Default to North
    
    def _get_weather_description(self, code: int) -> str:
        """Convert WMO weather code to description"""
        # WMO Weather interpretation codes
        weather_codes = {
            0: "Clear",
            1: "Mostly Clear",
            2: "Partly Cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Foggy",
            51: "Light Drizzle",
            53: "Drizzle",
            55: "Heavy Drizzle",
            56: "Light Freezing Drizzle",
            57: "Freezing Drizzle",
            61: "Light Rain",
            63: "Rain",
            65: "Heavy Rain",
            66: "Light Freezing Rain",
            67: "Freezing Rain",
            71: "Light Snow",
            73: "Snow",
            75: "Heavy Snow",
            77: "Snow Grains",
            80: "Light Showers",
            81: "Showers",
            82: "Heavy Showers",
            85: "Light Snow Showers",
            86: "Snow Showers",
            95: "Thunderstorm",
            96: "T-Storm w/Hail",
            99: "Severe T-Storm"
        }
        
        return weather_codes.get(code, "Unknown")
    
    def _get_weather_emoji(self, code: int) -> str:
        """Convert WMO weather code to emoji"""
        emoji_map = {
            0: "☀️",      # Clear
            1: "🌤️",     # Mostly Clear
            2: "⛅",     # Partly Cloudy
            3: "☁️",      # Overcast
            45: "🌫️",    # Fog
            48: "🌫️",    # Fog
            51: "🌦️",    # Drizzle
            53: "🌦️",    # Drizzle
            55: "🌧️",    # Heavy Drizzle
            56: "🌧️",    # Freezing Drizzle
            57: "🌧️",    # Freezing Drizzle
            61: "🌧️",    # Rain
            63: "🌧️",    # Rain
            65: "🌧️",    # Heavy Rain
            66: "🌧️",    # Freezing Rain
            67: "🌧️",    # Freezing Rain
            71: "❄️",     # Snow
            73: "❄️",     # Snow
            75: "❄️",     # Heavy Snow
            77: "❄️",     # Snow Grains
            80: "🌦️",    # Showers
            81: "🌦️",    # Showers
            82: "🌧️",    # Heavy Showers
            85: "🌨️",    # Snow Showers
            86: "🌨️",    # Snow Showers
            95: "⛈️",     # Thunderstorm
            96: "⛈️",     # Thunderstorm with Hail
            99: "⛈️"      # Severe Thunderstorm
        }
        
        return emoji_map.get(code, "🌤️")
    
    def _check_extreme_conditions(self, weather_text: str) -> str:
        """Check for extreme weather conditions that warrant warnings"""
        warnings = []
        
        # Extract temperature from weather text
        temp_match = re.search(r'(\d+)°F', weather_text)
        if temp_match:
            temp = int(temp_match.group(1))
            if temp >= 95:
                warnings.append("⚠️ Extreme heat")
            elif temp <= 20:
                warnings.append("⚠️ Extreme cold")
        
        # Check for severe weather indicators
        if "Heavy Rain" in weather_text or "Heavy Showers" in weather_text:
            warnings.append("⚠️ Heavy rain")
        
        if "Thunderstorm" in weather_text or "T-Storm" in weather_text:
            warnings.append("⚠️ Thunderstorms")
        
        if "Heavy Snow" in weather_text or "Snow Showers" in weather_text:
            warnings.append("⚠️ Heavy snow")
        
        # Check for high winds
        wind_match = re.search(r'[NESW]{1,2}(\d+)', weather_text)
        if wind_match:
            wind_speed = int(wind_match.group(1))
            if wind_speed >= 30:
                warnings.append(f"⚠️ High winds ({wind_speed} mph)")
        
        return " | ".join(warnings) if warnings else None