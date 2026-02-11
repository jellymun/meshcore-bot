#!/usr/bin/env python3
"""
Path Decode Command for the MeshCore Bot
Decodes hex path data to show which repeaters were involved in message routing
"""

import re
import time
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from .base_command import BaseCommand
from ..models import MeshMessage
from ..utils import calculate_distance


class PathCommand(BaseCommand):
    """Command for decoding path data to repeater names"""
    
    # Plugin metadata
    name = "path"
    keywords = ["path", "decode", "route"]
    description = "Decode hex path data to show which repeaters were involved in message routing"
    requires_dm = False
    cooldown_seconds = 1
    category = "meshcore_info"
    
    def __init__(self, bot):
        super().__init__(bot)
        self.path_enabled = self.get_config_value('Path_Command', 'enabled', fallback=True, value_type='bool')
        self.geographic_guessing_enabled = False
        self.bot_latitude = None
        self.bot_longitude = None
        
        self.proximity_method = bot.config.get('Path_Command', 'proximity_method', fallback='simple')
        self.path_proximity_fallback = bot.config.getboolean('Path_Command', 'path_proximity_fallback', fallback=True)
        self.max_proximity_range = bot.config.getfloat('Path_Command', 'max_proximity_range', fallback=200.0)
        self.max_repeater_age_days = bot.config.getint('Path_Command', 'max_repeater_age_days', fallback=14)
        
        recency_weight = bot.config.getfloat('Path_Command', 'recency_weight', fallback=0.4)
        self.recency_weight = max(0.0, min(1.0, recency_weight))
        self.proximity_weight = 1.0 - self.recency_weight
        
        self.star_bias_multiplier = bot.config.getfloat('Path_Command', 'star_bias_multiplier', fallback=2.5)
        self.star_bias_multiplier = max(1.0, self.star_bias_multiplier)
        
        self.high_confidence_symbol = bot.config.get('Path_Command', 'high_confidence_symbol', fallback='🎯')
        self.medium_confidence_symbol = bot.config.get('Path_Command', 'medium_confidence_symbol', fallback='📍')
        self.low_confidence_symbol = bot.config.get('Path_Command', 'low_confidence_symbol', fallback='❓')
        
        self.enable_p_shortcut = bot.config.getboolean('Path_Command', 'enable_p_shortcut', fallback=False)
        if self.enable_p_shortcut:
            if "p" not in self.keywords:
                self.keywords.append("p")
        
        try:
            if bot.config.has_section('Bot'):
                lat = bot.config.getfloat('Bot', 'bot_latitude', fallback=None)
                lon = bot.config.getfloat('Bot', 'bot_longitude', fallback=None)
                
                if lat is not None and lon is not None:
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        self.bot_latitude = lat
                        self.bot_longitude = lon
                        self.geographic_guessing_enabled = True
                        self.logger.info(f"Geographic proximity guessing enabled with bot location: {lat:.4f}, {lon:.4f}")
                    else:
                        self.logger.warning(f"Invalid bot coordinates in config: {lat}, {lon}")
                else:
                    self.logger.info("Bot location not configured - geographic proximity guessing disabled")
            else:
                self.logger.info("Bot section not found - geographic proximity guessing disabled")
        except Exception as e:
            self.logger.warning(f"Error reading bot location from config: {e}")
    
    def can_execute(self, message: MeshMessage) -> bool:
        """Check if this command can be executed"""
        if not self.path_enabled:
            return False
        return super().can_execute(message)
    
    def matches_keyword(self, message: MeshMessage) -> bool:
        """Check if message starts with 'path' keyword or 'p' shortcut"""
        content = message.content.strip()
        
        if content.startswith('!'):
            content = content[1:].strip()
        
        content_lower = content.lower()
        
        if self.enable_p_shortcut:
            if content_lower == "p":
                return True
            elif (content.startswith('p ') or content.startswith('P ')) and len(content) > 2:
                return True
        
        for keyword in self.keywords:
            if content_lower == keyword or content_lower.startswith(keyword + ' '):
                return True
        return False
    
    async def execute(self, message: MeshMessage) -> bool:
        """Execute path decode command"""
        self.logger.info(f"Path command executed with content: {message.content}")
        
        self._current_message = message
        
        content = message.content.strip()
        parts = content.split()
        
        if len(parts) < 2:
            response = await self._extract_path_from_recent_messages()
        else:
            path_input = " ".join(parts[1:])
            response = await self._decode_path(path_input)
        
        await self._send_path_response(message, response)
        return True
    
    async def _decode_path(self, path_input: str) -> str:
        """Decode hex path data to repeater names"""
        try:
            path_input = path_input.replace(',', ' ').replace(':', ' ')
            
            hex_pattern = r'[0-9a-fA-F]{2}'
            hex_matches = re.findall(hex_pattern, path_input)
            
            if not hex_matches:
                return self.translate('commands.path.no_valid_hex')
            
            node_ids = [match.upper() for match in hex_matches]
            
            self.logger.info(f"Decoding path with {len(node_ids)} nodes: {','.join(node_ids)}")
            
            repeater_info = await self._lookup_repeater_names(node_ids)
            
            return self._format_path_response(node_ids, repeater_info)
            
        except Exception as e:
            self.logger.error(f"Error decoding path: {e}")
            return self.translate('commands.path.error_decoding', error=str(e))
    
    async def _lookup_repeater_names(self, node_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Look up repeater names for given node IDs"""
        repeater_info = {}
        
        try:
            api_data = None
            
            for node_id in node_ids:
                if hasattr(self.bot, 'repeater_manager'):
                    try:
                        complete_db = await self.bot.repeater_manager.get_repeater_devices(include_historical=True)
                        
                        results = []
                        for row in complete_db:
                            if row['public_key'].startswith(node_id):
                                results.append({
                                    'name': row['name'],
                                    'public_key': row['public_key'],
                                    'device_type': row['device_type'],
                                    'last_seen': row['last_heard'],
                                    'last_heard': row['last_heard'],
                                    'last_advert_timestamp': row.get('last_advert_timestamp'),
                                    'is_active': row['is_currently_tracked'],
                                    'latitude': row['latitude'],
                                    'longitude': row['longitude'],
                                    'city': row['city'],
                                    'state': row['state'],
                                    'country': row['country'],
                                    'advert_count': row['advert_count'],
                                    'signal_strength': row['signal_strength'],
                                    'hop_count': row['hop_count'],
                                    'role': row['role'],
                                    'is_starred': bool(row.get('is_starred', 0))
                                })
                    except Exception as e:
                        self.logger.debug(f"Error getting complete database: {e}")
                        results = []
                
                if not results:
                    try:
                        if self.max_repeater_age_days > 0:
                            query = '''
                                SELECT name, public_key, device_type, last_heard, last_heard as last_seen, 
                                       last_advert_timestamp, latitude, longitude, city, state, country,
                                       advert_count, signal_strength, hop_count, role, is_starred
                                FROM complete_contact_tracking 
                                WHERE public_key LIKE ? AND role IN ('repeater', 'roomserver')
                                AND (
                                    (last_advert_timestamp IS NOT NULL AND last_advert_timestamp >= datetime('now', '-{} days'))
                                    OR (last_advert_timestamp IS NULL AND last_heard >= datetime('now', '-{} days'))
                                )
                                ORDER BY COALESCE(last_advert_timestamp, last_heard) DESC
                            '''.format(self.max_repeater_age_days, self.max_repeater_age_days)
                        else:
                            query = '''
                                SELECT name, public_key, device_type, last_heard, last_heard as last_seen, 
                                       last_advert_timestamp, latitude, longitude, city, state, country,
                                       advert_count, signal_strength, hop_count, role, is_starred
                                FROM complete_contact_tracking 
                                WHERE public_key LIKE ? AND role IN ('repeater', 'roomserver')
                                ORDER BY COALESCE(last_advert_timestamp, last_heard) DESC
                            '''
                        
                        prefix_pattern = f"{node_id}%"
                        results = self.bot.db_manager.execute_query(query, (prefix_pattern,))
                        
                        if results:
                            results = [
                                {
                                    'name': row['name'],
                                    'public_key': row['public_key'],
                                    'device_type': row['device_type'],
                                    'last_seen': row['last_seen'],
                                    'last_heard': row.get('last_heard', row['last_seen']),
                                    'last_advert_timestamp': row.get('last_advert_timestamp'),
                                    'is_active': True,
                                    'latitude': row['latitude'],
                                    'longitude': row['longitude'],
                                    'city': row['city'],
                                    'state': row['state'],
                                    'country': row['country'],
                                    'advert_count': row.get('advert_count', 0),
                                    'signal_strength': row.get('signal_strength'),
                                    'hop_count': row.get('hop_count'),
                                    'role': row.get('role'),
                                    'is_starred': bool(row.get('is_starred', 0))
                                } for row in results
                            ]
                    except Exception as e:
                        self.logger.debug(f"Error querying complete_contact_tracking directly: {e}")
                        results = []
                
                if results:
                    repeaters_data = [
                        {
                            'name': row['name'],
                            'public_key': row['public_key'],
                            'device_type': row['device_type'],
                            'last_seen': row['last_seen'],
                            'last_heard': row.get('last_heard', row['last_seen']),
                            'last_advert_timestamp': row.get('last_advert_timestamp'),
                            'is_active': row['is_active'],
                            'latitude': row['latitude'],
                            'longitude': row['longitude'],
                            'city': row['city'],
                            'state': row['state'],
                            'country': row['country'],
                            'is_starred': row.get('is_starred', False)
                        } for row in results
                    ]
                    
                    scored_repeaters = self._calculate_recency_weighted_scores(repeaters_data)
                    min_recency_threshold = 0.01
                    recent_repeaters = [r for r, score in scored_repeaters if score >= min_recency_threshold]
                    
                    if len(recent_repeaters) > 1:
                        if self.geographic_guessing_enabled:
                            sender_location = self._get_sender_location()
                            selected_repeater, confidence = self._select_repeater_by_proximity(recent_repeaters, node_id, None, sender_location)
                            
                            if selected_repeater and confidence >= 0.5:
                                repeater_info[node_id] = {
                                    'name': selected_repeater['name'],
                                    'public_key': selected_repeater['public_key'],
                                    'device_type': selected_repeater['device_type'],
                                    'last_seen': selected_repeater['last_seen'],
                                    'is_active': selected_repeater['is_active'],
                                    'found': True,
                                    'collision': False,
                                    'geographic_guess': True,
                                    'confidence': confidence,
                                    'latitude': selected_repeater.get('latitude'),
                                    'longitude': selected_repeater.get('longitude'),
                                    'city': selected_repeater.get('city'),
                                    'state': selected_repeater.get('state'),
                                    'country': selected_repeater.get('country'),
                                    'signal_strength': selected_repeater.get('signal_strength'),
                                    'hop_count': selected_repeater.get('hop_count')
                                }
                            else:
                                repeater_info[node_id] = {
                                    'found': True,
                                    'collision': True,
                                    'matches': len(recent_repeaters),
                                    'node_id': node_id,
                                    'repeaters': recent_repeaters
                                }
                        else:
                            repeater_info[node_id] = {
                                'found': True,
                                'collision': True,
                                'matches': len(recent_repeaters),
                                'node_id': node_id,
                                'repeaters': recent_repeaters
                            }
                    elif len(recent_repeaters) == 1:
                        repeater = recent_repeaters[0]
                        repeater_info[node_id] = {
                            'name': repeater['name'],
                            'public_key': repeater['public_key'],
                            'device_type': repeater['device_type'],
                            'last_seen': repeater['last_seen'],
                            'is_active': repeater['is_active'],
                            'found': True,
                            'collision': False,
                            'latitude': repeater.get('latitude'),
                            'longitude': repeater.get('longitude'),
                            'city': repeater.get('city'),
                            'state': repeater.get('state'),
                            'country': repeater.get('country'),
                            'signal_strength': repeater.get('signal_strength'),
                            'hop_count': repeater.get('hop_count')
                        }
                    else:
                        repeater_info[node_id] = {
                            'found': False,
                            'node_id': node_id
                        }
                else:
                    device_matches = []
                    if hasattr(self.bot.meshcore, 'contacts'):
                        for contact_key, contact_data in self.bot.meshcore.contacts.items():
                            public_key = contact_data.get('public_key', contact_key)
                            if public_key.startswith(node_id):
                                if hasattr(self.bot, 'repeater_manager') and self.bot.repeater_manager._is_repeater_device(contact_data):
                                    name = contact_data.get('adv_name', contact_data.get('name', self.translate('commands.path.unknown_name')))
                                    device_matches.append({
                                        'name': name,
                                        'public_key': public_key,
                                        'device_type': contact_data.get('type', 'Unknown'),
                                        'last_seen': 'Active',
                                        'is_active': True,
                                        'source': 'device'
                                    })
                    
                    if device_matches:
                        if len(device_matches) > 1:
                            repeater_info[node_id] = {
                                'found': True,
                                'collision': True,
                                'matches': len(device_matches),
                                'node_id': node_id,
                                'repeaters': device_matches
                            }
                        else:
                            match = device_matches[0]
                            repeater_info[node_id] = {
                                'name': match['name'],
                                'public_key': match['public_key'],
                                'device_type': match['device_type'],
                                'last_seen': match['last_seen'],
                                'is_active': match['is_active'],
                                'found': True,
                                'collision': False,
                                'source': 'device'
                            }
                    else:
                        repeater_info[node_id] = {
                            'found': False,
                            'node_id': node_id
                        }
        
        except Exception as e:
            self.logger.error(f"Error looking up repeater names: {e}")
            for node_id in node_ids:
                repeater_info[node_id] = {
                    'found': False,
                    'node_id': node_id,
                    'error': str(e)
                }
        
        return repeater_info
    
    def _get_sender_location(self) -> Optional[Tuple[float, float]]:
        """Get sender location from current message if available"""
        try:
            if not hasattr(self, '_current_message') or not self._current_message:
                return None
            
            sender_pubkey = self._current_message.sender_pubkey
            if not sender_pubkey:
                return None
            
            query = '''
                SELECT latitude, longitude 
                FROM complete_contact_tracking 
                WHERE public_key = ? 
                AND latitude IS NOT NULL AND longitude IS NOT NULL
                AND latitude != 0 AND longitude != 0
                ORDER BY COALESCE(last_advert_timestamp, last_heard) DESC
                LIMIT 1
            '''
            
            results = self.bot.db_manager.execute_query(query, (sender_pubkey,))
            
            if results:
                row = results[0]
                return (row['latitude'], row['longitude'])
            return None
        except Exception as e:
            self.logger.debug(f"Error getting sender location: {e}")
            return None
    
    def _select_repeater_by_proximity(self, repeaters: List[Dict[str, Any]], node_id: str = None, path_context: List[str] = None, sender_location: Optional[Tuple[float, float]] = None) -> Tuple[Optional[Dict[str, Any]], float]:
        """Select the most likely repeater based on geographic proximity"""
        if not repeaters:
            return None, 0.0
        
        if not self.geographic_guessing_enabled:
            return None, 0.0
        
        repeaters_with_location = []
        for repeater in repeaters:
            lat = repeater.get('latitude')
            lon = repeater.get('longitude')
            if lat is not None and lon is not None:
                if not (lat == 0.0 and lon == 0.0):
                    repeaters_with_location.append(repeater)
        
        if not repeaters_with_location:
            return None, 0.0
        
        if self.proximity_method == 'path' and path_context and node_id:
            result = self._select_by_path_proximity(repeaters_with_location, node_id, path_context, sender_location)
            if result[0] is not None:
                return result
            elif self.path_proximity_fallback:
                return self._select_by_simple_proximity(repeaters_with_location)
            else:
                return None, 0.0
        else:
            return self._select_by_simple_proximity(repeaters_with_location)
    
    def _select_by_simple_proximity(self, repeaters_with_location: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
        """Select repeater based on proximity to bot location"""
        scored_repeaters = self._calculate_recency_weighted_scores(repeaters_with_location)
        
        min_recency_threshold = 0.01
        scored_repeaters = [(r, score) for r, score in scored_repeaters if score >= min_recency_threshold]
        
        if not scored_repeaters:
            return None, 0.0
        
        if len(scored_repeaters) == 1:
            repeater, recency_score = scored_repeaters[0]
            distance = calculate_distance(
                self.bot_latitude, self.bot_longitude,
                repeater['latitude'], repeater['longitude']
            )
            if self.max_proximity_range > 0 and distance > self.max_proximity_range:
                return None, 0.0
            
            base_confidence = 0.4 + (recency_score * 0.5)
            return repeater, base_confidence
        
        combined_scores = []
        for repeater, recency_score in scored_repeaters:
            distance = calculate_distance(
                self.bot_latitude, self.bot_longitude,
                repeater['latitude'], repeater['longitude']
            )
            
            if self.max_proximity_range > 0 and distance > self.max_proximity_range:
                continue
            
            normalized_distance = min(distance / 1000.0, 1.0)
            proximity_score = 1.0 - normalized_distance
            
            combined_score = (recency_score * self.recency_weight) + (proximity_score * self.proximity_weight)
            
            if repeater.get('is_starred', False):
                combined_score *= self.star_bias_multiplier
                self.logger.debug(f"Applied star bias ({self.star_bias_multiplier}x) to {repeater.get('name', 'unknown')}")
            
            combined_scores.append((combined_score, distance, repeater))
        
        if not combined_scores:
            return None, 0.0
        
        combined_scores.sort(key=lambda x: x[0], reverse=True)
        
        best_score, best_distance, best_repeater = combined_scores[0]
        
        if len(combined_scores) == 1:
            confidence = 0.4 + (best_score * 0.5)
        else:
            second_best_score = combined_scores[1][0]
            score_ratio = best_score / second_best_score if second_best_score > 0 else 1.0
            
            if score_ratio > 1.5:
                confidence = 0.9
            elif score_ratio > 1.2:
                confidence = 0.8
            elif score_ratio > 1.1:
                confidence = 0.7
            else:
                distances_for_tiebreaker = [(d, r) for _, d, r in combined_scores]
                selected_repeater = self._apply_tie_breakers(distances_for_tiebreaker)
                confidence = 0.5
                return selected_repeater, confidence
        
        return best_repeater, confidence
    
    def _calculate_recency_weighted_scores(self, repeaters: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], float]]:
        """Calculate recency-weighted scores for all repeaters"""
        import math
        
        scored_repeaters = []
        now = datetime.now()
        
        for repeater in repeaters:
            most_recent_time = None
            
            last_heard = repeater.get('last_heard')
            if last_heard:
                try:
                    if isinstance(last_heard, str):
                        dt = datetime.fromisoformat(last_heard.replace('Z', '+00:00'))
                    else:
                        dt = last_heard
                    if most_recent_time is None or dt > most_recent_time:
                        most_recent_time = dt
                except:
                    pass
            
            last_advert = repeater.get('last_advert_timestamp')
            if last_advert:
                try:
                    if isinstance(last_advert, str):
                        dt = datetime.fromisoformat(last_advert.replace('Z', '+00:00'))
                    else:
                        dt = last_advert
                    if most_recent_time is None or dt > most_recent_time:
                        most_recent_time = dt
                except:
                    pass
            
            last_seen = repeater.get('last_seen')
            if last_seen:
                try:
                    if isinstance(last_seen, str):
                        dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                    else:
                        dt = last_seen
                    if most_recent_time is None or dt > most_recent_time:
                        most_recent_time = dt
                except:
                    pass
            
            if most_recent_time is None:
                recency_score = 0.1
            else:
                hours_ago = (now - most_recent_time).total_seconds() / 3600.0
                recency_score = math.exp(-hours_ago / 12.0)
                recency_score = max(0.0, min(1.0, recency_score))
            
            scored_repeaters.append((repeater, recency_score))
        
        scored_repeaters.sort(key=lambda x: x[1], reverse=True)
        
        return scored_repeaters
    
    def _apply_tie_breakers(self, distances: List[Tuple[float, Dict[str, Any]]]) -> Dict[str, Any]:
        """Apply tie-breaker strategies when repeaters have identical coordinates"""
        min_distance = distances[0][0]
        tied_repeaters = [repeater for distance, repeater in distances if distance == min_distance]
        
        active_repeaters = [r for r in tied_repeaters if r.get('is_active', True)]
        if len(active_repeaters) == 1:
            return active_repeaters[0]
        elif len(active_repeaters) > 1:
            tied_repeaters = active_repeaters
        
        def get_recent_timestamp(repeater):
            timestamps = []
            
            last_heard = repeater.get('last_heard')
            if last_heard:
                try:
                    if isinstance(last_heard, str):
                        dt = datetime.fromisoformat(last_heard.replace('Z', '+00:00'))
                    else:
                        dt = last_heard
                    timestamps.append(dt)
                except:
                    pass
            
            last_advert = repeater.get('last_advert_timestamp')
            if last_advert:
                try:
                    if isinstance(last_advert, str):
                        dt = datetime.fromisoformat(last_advert.replace('Z', '+00:00'))
                    else:
                        dt = last_advert
                    timestamps.append(dt)
                except:
                    pass
            
            last_seen = repeater.get('last_seen')
            if last_seen:
                try:
                    if isinstance(last_seen, str):
                        dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                    else:
                        dt = last_seen
                    timestamps.append(dt)
                except:
                    pass
            
            if timestamps:
                return max(timestamps)
            else:
                return datetime.min
        
        try:
            tied_repeaters.sort(key=get_recent_timestamp, reverse=True)
        except:
            pass
        
        try:
            tied_repeaters.sort(key=lambda r: r.get('advert_count', 0), reverse=True)
        except:
            pass
        
        tied_repeaters.sort(key=lambda r: r.get('name', ''))
        
        return tied_repeaters[0]
    
    def _select_by_path_proximity(self, repeaters_with_location: List[Dict[str, Any]], node_id: str, path_context: List[str], sender_location: Optional[Tuple[float, float]] = None) -> Tuple[Optional[Dict[str, Any]], float]:
        """Select repeater based on proximity to previous/next nodes in path"""
        try:
            scored_repeaters = self._calculate_recency_weighted_scores(repeaters_with_location)
            min_recency_threshold = 0.01
            recent_repeaters = [r for r, score in scored_repeaters if score >= min_recency_threshold]
            
            if not recent_repeaters:
                return None, 0.0
            
            current_index = path_context.index(node_id) if node_id in path_context else -1
            if current_index == -1:
                return None, 0.0
            
            prev_location = None
            next_location = None
            
            if current_index > 0:
                prev_node_id = path_context[current_index - 1]
                prev_location = self._get_node_location(prev_node_id)
            
            if current_index < len(path_context) - 1:
                next_node_id = path_context[current_index + 1]
                next_location = self._get_node_location(next_node_id)
            
            is_first_repeater = (current_index == 0)
            if is_first_repeater and sender_location:
                self.logger.debug(f"Using sender location for proximity calculation of first repeater: {sender_location[0]:.4f}, {sender_location[1]:.4f}")
                return self._select_by_single_proximity(recent_repeaters, sender_location, "sender")
            
            is_last_repeater = (current_index == len(path_context) - 1)
            if is_last_repeater and self.geographic_guessing_enabled:
                if self.bot_latitude is not None and self.bot_longitude is not None:
                    bot_location = (self.bot_latitude, self.bot_longitude)
                    self.logger.debug(f"Using bot location for proximity calculation of last repeater: {self.bot_latitude:.4f}, {self.bot_longitude:.4f}")
                    return self._select_by_single_proximity(recent_repeaters, bot_location, "bot")
            
            if prev_location and next_location:
                return self._select_by_dual_proximity(recent_repeaters, prev_location, next_location)
            elif prev_location:
                return self._select_by_single_proximity(recent_repeaters, prev_location, "previous")
            elif next_location:
                return self._select_by_single_proximity(recent_repeaters, next_location, "next")
            else:
                return None, 0.0
                
        except Exception as e:
            self.logger.warning(f"Error in path proximity calculation: {e}")
            return None, 0.0
    
    def _get_node_location(self, node_id: str) -> Optional[Tuple[float, float]]:
        """Get location for a node ID from the database"""
        try:
            if self.max_repeater_age_days > 0:
                query = '''
                    SELECT latitude, longitude, is_starred FROM complete_contact_tracking 
                    WHERE public_key LIKE ? AND latitude IS NOT NULL AND longitude IS NOT NULL
                    AND latitude != 0 AND longitude != 0 AND role IN ('repeater', 'roomserver')
                    AND (
                        (last_advert_timestamp IS NOT NULL AND last_advert_timestamp >= datetime('now', '-{} days'))
                        OR (last_advert_timestamp IS NULL AND last_heard >= datetime('now', '-{} days'))
                    )
                    ORDER BY is_starred DESC, COALESCE(last_advert_timestamp, last_heard) DESC
                    LIMIT 1
                '''.format(self.max_repeater_age_days, self.max_repeater_age_days)
            else:
                query = '''
                    SELECT latitude, longitude, is_starred FROM complete_contact_tracking 
                    WHERE public_key LIKE ? AND latitude IS NOT NULL AND longitude IS NOT NULL
                    AND latitude != 0 AND longitude != 0 AND role IN ('repeater', 'roomserver')
                    ORDER BY is_starred DESC, COALESCE(last_advert_timestamp, last_heard) DESC
                    LIMIT 1
                '''
            
            prefix_pattern = f"{node_id}%"
            results = self.bot.db_manager.execute_query(query, (prefix_pattern,))
            
            if results:
                row = results[0]
                return (row['latitude'], row['longitude'])
            return None
        except Exception as e:
            self.logger.warning(f"Error getting location for node {node_id}: {e}")
            return None
    
    def _select_by_dual_proximity(self, repeaters: List[Dict[str, Any]], prev_location: Tuple[float, float], next_location: Tuple[float, float]) -> Tuple[Optional[Dict[str, Any]], float]:
        """Select repeater based on proximity to both previous and next nodes"""
        scored_repeaters = self._calculate_recency_weighted_scores(repeaters)
        
        min_recency_threshold = 0.01
        scored_repeaters = [(r, score) for r, score in scored_repeaters if score >= min_recency_threshold]
        
        if not scored_repeaters:
            return None, 0.0
        
        best_repeater = None
        best_combined_score = 0.0
        
        for repeater, recency_score in scored_repeaters:
            prev_distance = calculate_distance(
                prev_location[0], prev_location[1],
                repeater['latitude'], repeater['longitude']
            )
            
            next_distance = calculate_distance(
                next_location[0], next_location[1],
                repeater['latitude'], repeater['longitude']
            )
            
            avg_distance = (prev_distance + next_distance) / 2
            normalized_distance = min(avg_distance / 1000.0, 1.0)
            proximity_score = 1.0 - normalized_distance
            
            combined_score = (recency_score * self.recency_weight) + (proximity_score * self.proximity_weight)
            
            if repeater.get('is_starred', False):
                combined_score *= self.star_bias_multiplier
                self.logger.debug(f"Applied star bias ({self.star_bias_multiplier}x) to {repeater.get('name', 'unknown')}")
            
            if combined_score > best_combined_score:
                best_combined_score = combined_score
                best_repeater = repeater
        
        if best_repeater:
            if self.max_proximity_range > 0:
                prev_dist = calculate_distance(
                    prev_location[0], prev_location[1],
                    best_repeater['latitude'], best_repeater['longitude']
                )
                next_dist = calculate_distance(
                    next_location[0], next_location[1],
                    best_repeater['latitude'], best_repeater['longitude']
                )
                if prev_dist > self.max_proximity_range or next_dist > self.max_proximity_range:
                    return None, 0.0
            
            confidence = 0.4 + (best_combined_score * 0.5)
            return best_repeater, confidence
        
        return None, 0.0
    
    def _select_by_single_proximity(self, repeaters: List[Dict[str, Any]], reference_location: Tuple[float, float], direction: str) -> Tuple[Optional[Dict[str, Any]], float]:
        """Select repeater based on proximity to single reference node"""
        scored_repeaters = self._calculate_recency_weighted_scores(repeaters)
        
        min_recency_threshold = 0.01
        scored_repeaters = [(r, score) for r, score in scored_repeaters if score >= min_recency_threshold]
        
        if not scored_repeaters:
            return None, 0.0
        
        if direction == "bot" or direction == "sender":
            proximity_weight = 1.0
            recency_weight = 0.0
        else:
            proximity_weight = self.proximity_weight
            recency_weight = self.recency_weight
        
        best_repeater = None
        best_combined_score = 0.0
        all_scores = []
        
        for repeater, recency_score in scored_repeaters:
            distance = calculate_distance(
                reference_location[0], reference_location[1],
                repeater['latitude'], repeater['longitude']
            )
            
            if self.max_proximity_range > 0 and distance > self.max_proximity_range:
                continue
            
            normalized_distance = min(distance / 1000.0, 1.0)
            proximity_score = 1.0 - normalized_distance
            
            combined_score = (recency_score * recency_weight) + (proximity_score * proximity_weight)
            
            if repeater.get('is_starred', False):
                combined_score *= self.star_bias_multiplier
                self.logger.debug(f"Applied star bias ({self.star_bias_multiplier}x) to {repeater.get('name', 'unknown')}")
            
            all_scores.append((repeater.get('name', 'unknown'), distance, recency_score, proximity_score, combined_score))
            
            if combined_score > best_combined_score:
                best_combined_score = combined_score
                best_repeater = repeater
        
        if direction == "bot" and all_scores:
            self.logger.debug(f"Last repeater selection scores (proximity_weight={proximity_weight:.1%}, recency_weight={recency_weight:.1%}):")
            for name, dist, rec, prox, combined in sorted(all_scores, key=lambda x: x[4], reverse=True):
                self.logger.debug(f"  {name}: distance={dist:.1f}km, recency={rec:.3f}, proximity={prox:.3f}, combined={combined:.3f}")
        
        if best_repeater:
            confidence = 0.4 + (best_combined_score * 0.5)
            return best_repeater, confidence
        
        return None, 0.0
    
    def _format_path_response(self, node_ids: List[str], repeater_info: Dict[str, Dict[str, Any]]) -> str:
        """Format the path decode response with detailed repeater information
        
        Maintains the order of repeaters as they appear in the path (first to last)
        Includes signal strength, device type, location, and recency information
        """
        lines = []
        
        for node_id in node_ids:
            info = repeater_info.get(node_id, {})
            
            if info.get('found', False):
                if info.get('collision', False):
                    matches = info.get('matches', 0)
                    line = self.translate('commands.path.node_collision', node_id=node_id, matches=matches)
                elif info.get('geographic_guess', False):
                    name = info['name']
                    confidence = info.get('confidence', 0.0)
                    
                    details = self._build_repeater_details(info)
                    
                    truncation = self.translate('commands.path.truncation')
                    if len(name) > 15:
                        name = name[:12] + truncation
                    
                    if confidence >= 0.9:
                        confidence_indicator = self.high_confidence_symbol
                    elif confidence >= 0.8:
                        confidence_indicator = self.medium_confidence_symbol
                    else:
                        confidence_indicator = self.low_confidence_symbol
                    
                    line = f"{node_id}: {name} {confidence_indicator}\n  {details}"
                else:
                    name = info['name']
                    
                    details = self._build_repeater_details(info)
                    
                    truncation = self.translate('commands.path.truncation')
                    if len(name) > 15:
                        name = name[:12] + truncation
                    
                    line = f"{node_id}: {name}\n  {details}"
            else:
                line = self.translate('commands.path.node_unknown', node_id=node_id)
            
            lines.append(line)
        
        return "\n".join(lines)

    def _build_repeater_details(self, info: Dict[str, Any]) -> str:
        """Build a detailed info string for a repeater including signal strength and other details
        
        Args:
            info: Repeater info dictionary from _lookup_repeater_names
            
        Returns:
            str: Formatted detail string with signal strength, type, location, and recency
        """
        details_parts = []
        
        # Signal strength (RSSI)
        signal_strength = info.get('signal_strength')
        if signal_strength is not None:
            details_parts.append(f"📶 RSSI: {signal_strength}dBm")
        
        # Device type
        device_type = info.get('device_type')
        if device_type:
            details_parts.append(f"🔧 Type: {device_type}")
        
        # Hop count
        hop_count = info.get('hop_count')
        if hop_count is not None:
            details_parts.append(f"📡 Hops: {hop_count}")
        
        # Location (city, state, country)
        city = info.get('city')
        state = info.get('state')
        country = info.get('country')
        location_parts = []
        if city:
            location_parts.append(city)
        if state and state != city:
            location_parts.append(state)
        if country and country != state and country != city:
            location_parts.append(country)
        
        if location_parts:
            details_parts.append(f"📍 {', '.join(location_parts)}")
        
        # Last seen / Recency
        last_seen = info.get('last_seen')
        if last_seen:
            try:
                if isinstance(last_seen, str):
                    last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                else:
                    last_seen_dt = last_seen
                
                now = datetime.now(last_seen_dt.tzinfo) if last_seen_dt.tzinfo else datetime.now()
                hours_ago = (now - last_seen_dt).total_seconds() / 3600
                
                if hours_ago < 1:
                    time_str = "< 1h ago"
                elif hours_ago < 24:
                    time_str = f"{int(hours_ago)}h ago"
                else:
                    days_ago = int(hours_ago / 24)
                    time_str = f"{days_ago}d ago"
                
                details_parts.append(f"🕐 {time_str}")
            except Exception as e:
                self.logger.debug(f"Error formatting last_seen time: {e}")
        
        # Active status
        is_active = info.get('is_active')
        if is_active is not None:
            status = "✅ Active" if is_active else "⚠️ Inactive"
            details_parts.append(status)
        
        # Join all details with pipe separator
        if details_parts:
            return " | ".join(details_parts)
        else:
            return "No details available"
    
    async def _send_path_response(self, message: MeshMessage, response: str):
        """Send path response, splitting into multiple messages if necessary"""
        self.last_response = response
        
        max_length = self.get_max_message_length(message)
        
        if len(response) <= max_length:
            await self.send_response(message, response)
        else:
            lines = response.split('\n')
            current_message = ""
            message_count = 0
            
            for i, line in enumerate(lines):
                if len(current_message) + len(line) + 1 > max_length:
                    if current_message:
                        if i < len(lines):
                            current_message += self.translate('commands.path.continuation_end')
                        await self.send_response(message, current_message.rstrip())
                        await asyncio.sleep(3.0)
                        message_count += 1
                    
                    if message_count > 0:
                        current_message = self.translate('commands.path.continuation_start', line=line)
                    else:
                        current_message = line
                else:
                    if current_message:
                        current_message += f"\n{line}"
                    else:
                        current_message = line
            
            if current_message:
                await self.send_response(message, current_message)
    
    async def _extract_path_from_recent_messages(self) -> str:
        """Extract path from the current message's path information"""
        try:
            if hasattr(self, '_current_message') and self._current_message and self._current_message.path:
                path_string = self._current_message.path
                
                if "Direct" in path_string or "0 hops" in path_string:
                    return self.translate('commands.path.direct_connection')
                
                if " via ROUTE_TYPE_" in path_string:
                    path_part = path_string.split(" via ROUTE_TYPE_")[0]
                else:
                    path_part = path_string
                
                if ',' in path_part:
                    path_input = path_part
                    return await self._decode_path(path_input)
                else:
                    hex_pattern = r'[0-9a-fA-F]{2}'
                    if re.search(hex_pattern, path_part):
                        return await self._decode_path(path_part)
                    else:
                        return self.translate('commands.path.path_prefix', path_string=path_string)
            else:
                return self.translate('commands.path.no_path')
                
        except Exception as e:
            self.logger.error(f"Error extracting path from current message: {e}")
            return self.translate('commands.path.error_extracting', error=str(e))
    
    def get_help(self) -> str:
        """Get help text for the path command"""
        return self.translate('commands.path.help')
    
    def get_help_text(self) -> str:
        """Get help text for the path command (used by help system)"""
        return self.get_help()
