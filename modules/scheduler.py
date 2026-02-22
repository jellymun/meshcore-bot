#!/usr/bin/env python3
"""
Message scheduler functionality for the MeshCore Bot
Handles scheduled messages and timing
"""

import time
import threading
import schedule
import datetime
import pytz
import sqlite3
import json
import os
import re
import asyncio
from typing import Dict, Tuple, Any
from pathlib import Path
from .utils import format_keyword_response_with_placeholders
from .models import MeshMessage


class MessageScheduler:
    """Manages scheduled messages and timing"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger
        self.scheduled_messages = {}
        self.scheduler_thread = None

    def get_current_time(self):
        """Get current time in configured timezone"""
        timezone_str = self.bot.config.get('Bot', 'timezone', fallback='')

        if timezone_str:
            try:
                tz = pytz.timezone(timezone_str)
                return datetime.datetime.now(tz)
            except pytz.exceptions.UnknownTimeZoneError:
                self.logger.warning(f"Invalid timezone '{timezone_str}', using system timezone")
                return datetime.datetime.now()
        else:
            return datetime.datetime.now()

    def setup_scheduled_messages(self):
        """Setup scheduled messages from config"""
        # Fix: Clear any existing jobs to prevent double-execution if this 
        # method is called more than once during initialization.
        schedule.clear()
        
        if self.bot.config.has_section('Scheduled_Messages'):
            self.logger.info("Found Scheduled_Messages section")
            for time_str, message_info in self.bot.config.items('Scheduled_Messages'):
                self.logger.info(f"Processing scheduled message: '{time_str}' -> '{message_info}'")
                try:
                    # Validate time format first
                    if not self._is_valid_time_format(time_str):
                        self.logger.warning(f"Invalid time format '{time_str}' for scheduled message: {message_info}")
                        continue

                    # Normalize message_info for parsing (preserve original for storage)
                    raw = message_info.strip()

                    # 1) Channel-first pattern: "<channel>:cmd:<command>"
                    #    Example: "pogo:cmd:wx sydney"
                    m = re.match(r'^\s*(?P<channel>[^:]+)\s*:\s*cmd\s*:\s*(?P<cmd>.+)$', raw, flags=re.IGNORECASE)
                    if m:
                        channel = m.group('channel').strip()
                        cmd_part = m.group('cmd').strip()
                        self.logger.info(f"Scheduled command message for {channel}: '{cmd_part}' (parsed channel-first form)")
                        hour = int(time_str[:2])
                        minute = int(time_str[2:])
                        schedule_time = f"{hour:02d}:{minute:02d}"
                        schedule.every().day.at(schedule_time).do(
                            self.send_scheduled_command, channel, cmd_part
                        )
                        self.scheduled_messages[time_str] = (channel, raw)
                        continue

                    # 2) Command-first pattern: "cmd:<command>" or "cmd:<channel>:<command>"
                    if raw.lower().startswith('cmd:'):
                        parts = raw.split(':', 2)
                        # parts could be ['cmd', 'command'] or ['cmd', 'channel', 'command']
                        cmd_part = parts[-1].strip()
                        channel = 'Pogo'  # Default channel
                        if len(parts) == 3:
                            channel = parts[1].strip()

                        self.logger.info(f"Scheduled command message for {channel}: '{cmd_part}' (parsed cmd-first form)")
                        hour = int(time_str[:2])
                        minute = int(time_str[2:])
                        schedule_time = f"{hour:02d}:{minute:02d}"
                        schedule.every().day.at(schedule_time).do(
                            self.send_scheduled_command, channel, cmd_part
                        )
                        self.scheduled_messages[time_str] = (channel, raw)
                    else:
                        # Handle regular messages (existing behavior)
                        if ':' not in message_info:
                            self.logger.warning(f"Invalid scheduled message format (missing channel separator): {message_info}")
                            continue
                        channel, message = message_info.split(':', 1)
                        # Convert HHMM to HH:MM for scheduler
                        hour = int(time_str[:2])
                        minute = int(time_str[2:])
                        schedule_time = f"{hour:02d}:{minute:02d}"

                        schedule.every().day.at(schedule_time).do(
                            self.send_scheduled_message, channel.strip(), message.strip()
                        )
                        self.scheduled_messages[time_str] = (channel.strip(), message.strip())
                        self.logger.info(f"Scheduled message: {schedule_time} -> {channel}: {message}")
                except ValueError:
                    self.logger.warning(f"Invalid scheduled message format: {message_info}")
                except Exception as e:
                    self.logger.warning(f"Error setting up scheduled message '{time_str}': {e}")

        # Setup interval-based advertising
        self.setup_interval_advertising()

    def setup_interval_advertising(self):
        """Setup interval-based advertising from config"""
        try:
            advert_interval_hours = self.bot.config.getint('Bot', 'advert_interval_hours', fallback=0)
            if advert_interval_hours > 0:
                self.logger.info(f"Setting up interval-based advertising every {advert_interval_hours} hours")
                # Initialize bot's last advert time to now to prevent immediate advert if not already set
                if not hasattr(self.bot, 'last_advert_time') or self.bot.last_advert_time is None:
                    self.bot.last_advert_time = time.time()
            else:
                self.logger.info("Interval-based advertising disabled (advert_interval_hours = 0)")
        except Exception as e:
            self.logger.warning(f"Error setting up interval advertising: {e}")

    def _is_valid_time_format(self, time_str: str) -> bool:
        """Validate time format (HHMM)"""
        try:
            if len(time_str) != 4:
                return False
            hour = int(time_str[:2])
            minute = int(time_str[2:])
            return 0 <= hour <= 23 and 0 <= minute <= 59
        except ValueError:
            return False

    def send_scheduled_message(self, channel: str, message: str):
        """Send a scheduled message (synchronous wrapper for schedule library)"""
        current_time = self.get_current_time()
        self.logger.info(f"📅 Sending scheduled message at {current_time.strftime('%H:%M:%S')} to {channel}: {message}")

        # Use the main event loop if available, otherwise create a new one
        if hasattr(self.bot, 'main_event_loop') and self.bot.main_event_loop and self.bot.main_event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._send_scheduled_message_async(channel, message),
                self.bot.main_event_loop
            )
            try:
                future.result(timeout=60)
            except Exception as e:
                self.logger.error(f"Error sending scheduled message: {e}")
        else:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(self._send_scheduled_message_async(channel, message))

    def send_scheduled_command(self, channel: str, command: str):
        """Synchronous wrapper to execute a scheduled command"""
        current_time = self.get_current_time()
        self.logger.info(f"📅 Executing scheduled command at {current_time.strftime('%H:%M:%S')} in {channel}: {command}")

        if hasattr(self.bot, 'main_event_loop') and self.bot.main_event_loop and self.bot.main_event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.execute_scheduled_command(channel, command),
                self.bot.main_event_loop
            )
            try:
                future.result(timeout=60)
            except Exception as e:
                self.logger.error(f"Error executing scheduled command: {e}")
        else:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(self.execute_scheduled_command(channel, command))

    async def execute_scheduled_command(self, channel: str, command: str):
        """Execute a scheduled command as if sent by a remote user"""
        self.logger.info(f"Executing scheduled command: '{command}' in channel '{channel}'")

        try:
            mesh_message = MeshMessage(
                content=command,
                sender_id='scheduled_command',
                sender_pubkey=None,
                channel=channel,
                hops=None,
                path=None,
                is_dm=False,
                timestamp=int(time.time()),
                snr=None,
                rssi=None,
                elapsed=None
            )

            if hasattr(self.bot, 'command_manager') and hasattr(self.bot.command_manager, 'execute_commands'):
                await self.bot.command_manager.execute_commands(mesh_message)
            else:
                if hasattr(self.bot.command_manager, 'handle_command_message'):
                    await self.bot.command_manager.handle_command_message(mesh_message)
                else:
                    raise AttributeError("CommandManager has no 'execute_commands' or 'handle_command_message' method")

        except AttributeError as ae:
            self.logger.error(f"CommandManager missing expected method to dispatch scheduled command: {ae}")
        except Exception as e:
            self.logger.error(f"Error executing scheduled command '{command}': {e}")

    async def _get_mesh_info(self) -> Dict[str, Any]:
        """Get mesh network information for scheduled messages"""
        info = {
            'total_contacts': 0,
            'total_repeaters': 0,
            'total_companions': 0,
            'total_roomservers': 0,
            'total_sensors': 0,
            'recent_activity_24h': 0,
            'new_companions_7d': 0,
            'new_repeaters_7d': 0,
            'new_roomservers_7d': 0,
            'new_sensors_7d': 0,
            'total_contacts_30d': 0,
            'total_repeaters_30d': 0,
            'total_companions_30d': 0,
            'total_roomservers_30d': 0,
            'total_sensors_30d': 0
        }

        try:
            if hasattr(self.bot, 'repeater_manager'):
                try:
                    stats = await self.bot.repeater_manager.get_contact_statistics()
                    if stats:
                        info['total_contacts'] = stats.get('total_heard', 0)
                        by_role = stats.get('by_role', {})
                        info['total_repeaters'] = by_role.get('repeater', 0)
                        info['total_companions'] = by_role.get('companion', 0)
                        info['total_roomservers'] = by_role.get('roomserver', 0)
                        info['total_sensors'] = by_role.get('sensor', 0)
                        info['recent_activity_24h'] = stats.get('recent_activity', 0)
                except Exception as e:
                    self.logger.debug(f"Error getting stats from repeater_manager: {e}")

            if info['total_contacts'] == 0 and hasattr(self.bot, 'meshcore') and hasattr(self.bot.meshcore, 'contacts'):
                info['total_contacts'] = len(self.bot.meshcore.contacts)
                if hasattr(self.bot, 'repeater_manager'):
                    for contact_data in self.bot.meshcore.contacts.values():
                        if self.bot.repeater_manager._is_repeater_device(contact_data):
                            info['total_repeaters'] += 1
                        else:
                            info['total_companions'] += 1

            if info['recent_activity_24h'] == 0:
                try:
                    with sqlite3.connect(self.bot.db_manager.db_path, timeout=30.0) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_stats'")
                        if cursor.fetchone():
                            cutoff_time = int(time.time()) - (24 * 60 * 60)
                            cursor.execute('''
                                SELECT COUNT(DISTINCT sender_id)
                                FROM message_stats
                                WHERE timestamp >= ? AND is_dm = 0
                            ''', (cutoff_time,))
                            result = cursor.fetchone()
                            if result:
                                info['recent_activity_24h'] = result[0]
                except Exception:
                    pass

            try:
                with sqlite3.connect(self.bot.db_manager.db_path, timeout=30.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='complete_contact_tracking'")
                    if cursor.fetchone():
                        cursor.execute('''
                            SELECT role, COUNT(DISTINCT public_key) as count
                            FROM complete_contact_tracking
                            WHERE first_heard >= datetime('now', '-7 days')
                            AND role IS NOT NULL AND role != ''
                            GROUP BY role
                        ''')
                        for row in cursor.fetchall():
                            role = (row[0] or '').lower()
                            count = row[1] or 0
                            if role == 'companion': info['new_companions_7d'] = count
                            elif role == 'repeater': info['new_repeaters_7d'] = count
                            elif role == 'roomserver': info['new_roomservers_7d'] = count
                            elif role == 'sensor': info['new_sensors_7d'] = count

                        cursor.execute('''
                            SELECT COUNT(DISTINCT public_key) as count
                            FROM complete_contact_tracking
                            WHERE last_heard >= datetime('now', '-30 days')
                        ''')
                        result = cursor.fetchone()
                        if result: info['total_contacts_30d'] = result[0] or 0
            except Exception as e:
                self.logger.debug(f"Error getting extended DB stats: {e}")

        except Exception as e:
            self.logger.debug(f"Error getting mesh info: {e}")

        return info

    def _has_mesh_info_placeholders(self, message: str) -> bool:
        """Check if message contains mesh info placeholders"""
        placeholders = [
            '{total_contacts}', '{total_repeaters}', '{total_companions}',
            '{total_roomservers}', '{total_sensors}', '{recent_activity_24h}',
            '{new_companions_7d}', '{new_repeaters_7d}', '{new_roomservers_7d}', '{new_sensors_7d}',
            '{total_contacts_30d}', '{total_repeaters_30d}', '{total_companions_30d}',
            '{total_roomservers_30d}', '{total_sensors_30d}',
            '{repeaters}', '{companions}'
        ]
        return any(placeholder in message for placeholder in placeholders)

    async def _send_scheduled_message_async(self, channel: str, message: str):
        """Send a scheduled message (async implementation)"""
        if self._has_mesh_info_placeholders(message):
            try:
                mesh_info = await self._get_mesh_info()
                message = format_keyword_response_with_placeholders(
                    message,
                    message=None,
                    bot=self.bot,
                    mesh_info=mesh_info
                )
            except Exception as e:
                self.logger.warning(f"Error replacing placeholders: {e}")

        await self.bot.command_manager.send_channel_message(channel, message)

    def start(self):
        """Start the scheduler in a separate thread"""
        try:
            self.setup_scheduled_messages()
        except Exception as e:
            self.logger.debug(f"Error during setup_scheduled_messages in start(): {e}")

        self.scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        self.scheduler_thread.start()

    def run_scheduler(self):
        """Run the scheduler in a separate thread"""
        self.logger.info("Scheduler thread started")
        last_log_time = 0
        last_feed_poll_time = 0
        last_job_count = 0
        last_job_log_time = 0

        while getattr(self.bot, 'connected', False):
            current_time = self.get_current_time()

            if time.time() - last_log_time > 300:
                self.logger.info(f"Scheduler running - {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                last_log_time = time.time()

            pending_jobs = schedule.get_jobs()
            current_job_count = len(pending_jobs) if pending_jobs else 0
            if current_job_count != last_job_count and (time.time() - last_job_log_time) >= 30:
                if current_job_count > 0:
                    self.logger.debug(f"Found {current_job_count} scheduled jobs")
                last_job_count = current_job_count
                last_job_log_time = time.time()

            self.check_interval_advertising()

            if time.time() - last_feed_poll_time >= 60:
                if (hasattr(self.bot, 'feed_manager') and self.bot.feed_manager and
                    hasattr(self.bot.feed_manager, 'enabled') and self.bot.feed_manager.enabled and
                    getattr(self.bot, 'connected', False)):
                    if hasattr(self.bot, 'main_event_loop') and self.bot.main_event_loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.bot.feed_manager.poll_all_feeds(), self.bot.main_event_loop)
                    last_feed_poll_time = time.time()

            # Process pending channel ops and message queues every few seconds
            if time.time() - getattr(self, 'last_channel_ops_check_time', 0) >= 5:
                if hasattr(self.bot, 'channel_manager') and getattr(self.bot, 'connected', False):
                    if hasattr(self.bot, 'main_event_loop') and self.bot.main_event_loop.is_running():
                        asyncio.run_coroutine_threadsafe(self._process_channel_operations(), self.bot.main_event_loop)
                    self.last_channel_ops_check_time = time.time()

            schedule.run_pending()
            time.sleep(1)

        self.logger.info("Scheduler thread stopped")

    def check_interval_advertising(self):
        """Check if it's time for an interval advert"""
        try:
            interval = self.bot.config.getint('Bot', 'advert_interval_hours', fallback=0)
            if interval <= 0: return

            current = time.time()
            if not hasattr(self.bot, 'last_advert_time') or self.bot.last_advert_time is None:
                self.bot.last_advert_time = current
                return

            if (current - self.bot.last_advert_time) >= (interval * 3600):
                self.send_interval_advert()
                self.bot.last_advert_time = current
        except Exception as e:
            self.logger.error(f"Error in advertising check: {e}")

    def send_interval_advert(self):
        """Send an interval advert via main event loop"""
        if hasattr(self.bot, 'main_event_loop') and self.bot.main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(self._send_interval_advert_async(), self.bot.main_event_loop)

    async def _send_interval_advert_async(self):
        try:
            await self.bot.meshcore.commands.send_advert(flood=True)
            self.logger.info("Interval-based flood advert sent")
        except Exception as e:
            self.logger.error(f"Error sending advert: {e}")

    async def _process_channel_operations(self):
        """Process pending channel operations from DB"""
        try:
            db_path = str(self.bot.db_manager.db_path)
            with sqlite3.connect(db_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM channel_operations WHERE status = 'pending' LIMIT 10")
                operations = cursor.fetchall()

            if not operations: return

            for op in operations:
                success = False
                try:
                    if op['operation_type'] == 'add':
                        key = bytes.fromhex(op['channel_key_hex']) if op['channel_key_hex'] else None
                        success = await self.bot.channel_manager.add_channel(op['channel_idx'], op['channel_name'], channel_secret=key)
                    elif op['operation_type'] == 'remove':
                        success = await self.bot.channel_manager.remove_channel(op['channel_idx'])

                    with sqlite3.connect(db_path, timeout=30.0) as conn:
                        status = 'completed' if success else 'failed'
                        conn.execute("UPDATE channel_operations SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?", (status, op['id']))
                except Exception as e:
                    self.logger.error(f"Op {op['id']} failed: {e}")
        except Exception as e:
            self.logger.error(f"Process channel ops failed: {e}")
