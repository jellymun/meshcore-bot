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
import asyncio
from typing import Dict

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
        if not self.bot.config.has_section('Scheduled_Messages'):
            self.logger.info("No Scheduled_Messages section found in config")
            return
            
        self.logger.info("Found Scheduled_Messages section")
        for time_str, message_info in self.bot.config.items('Scheduled_Messages'):
            self.logger.info(f"Processing scheduled message: '{time_str}' -> '{message_info}'")
            try:
                # Validate time format first
                if not self._is_valid_time_format(time_str):
                    self.logger.warning(f"Invalid time format '{time_str}' for scheduled message: {message_info}")
                    continue
                
                channel, message = message_info.split(':', 1)
                # Convert HHMM to HH:MM for scheduler
                hour = int(time_str[:2])
                minute = int(time_str[2:])
                schedule_time = f"{hour:02d}:{minute:02d}"
                
                # NOTE: We use self.send_scheduled_message, which handles the async wrapping
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

    async def _invoke_internal_command_async(self, channel: str, command_text: str):
        """
        Invoke a bot command via the existing CommandManager API by constructing
        a MeshMessage and letting CommandManager run its normal matching/execution flow.
        """
        cmdmgr = getattr(self.bot, 'command_manager', None)
        if not cmdmgr:
            self.logger.error("bot.command_manager is not available. Cannot run internal command.")
            return

        # Import here to avoid circular import issues at module level
        # NOTE: Assumes .models exists in the same package context
        try:
            from .models import MeshMessage
        except ImportError:
            # Fallback or error handling if .models is not available
            self.logger.error("Cannot import MeshMessage from .models. Check module structure.")
            return

        # Construct a MeshMessage that represents the scheduled invocation.
        # Use a scheduler sender id so plugins that check sender can see it's internal.
        msg = MeshMessage(
            content=command_text.strip(),
            sender_id='scheduler',
            channel=channel,
            is_dm=False,   # set True if you intend to invoke DM-only commands
        )

        try:
            # Quick pre-check: do any keywords/plugins match?
            matches = cmdmgr.check_keywords(msg)
            if not matches:
                # Try with an explicit '!' prefix (some commands expect '!' style)
                msg_alt = MeshMessage(content='!' + msg.content, sender_id=msg.sender_id, channel=msg.channel, is_dm=msg.is_dm)
                matches = cmdmgr.check_keywords(msg_alt)
                if matches:
                    msg = msg_alt

            if not matches:
                # No match found — inform channel that the scheduled command is unknown
                await cmdmgr.send_channel_message(channel, f"Failed to run internal command '{command_text}': not found.")
                self.logger.error(f"No matching command/plugin found for scheduled command: {command_text}")
                return

            # Execute the command via the CommandManager's normal execution path
            await cmdmgr.execute_commands(msg)
            self.logger.info(f"Scheduled internal command executed: {command_text}")

        except Exception as e:
            self.logger.exception(f"Error invoking internal command '{command_text}': {e}")
            try:
                await cmdmgr.send_channel_message(channel, f"Error running command '{command_text}': {e}")
            except Exception:
                self.logger.error("Failed to send error message to channel after invocation failure.")

    def send_scheduled_message(self, channel: str, message: str):
        """
        Send a scheduled message (synchronous wrapper for schedule library).
        Submits the async task to the bot's main event loop using threadsafe approach.
        """
        current_time = self.get_current_time()
        self.logger.info(f"📅 Sending scheduled message at {current_time.strftime('%H:%M:%S')} to {channel}: {message}")
        
        # --- FIX: Use threadsafe submission to the main event loop ---
        try:
            # Assumes the running event loop is stored on the bot instance as self.bot.loop
            bot_loop = self.bot.loop 
        except AttributeError:
            self.logger.error("Bot's event loop is not accessible at self.bot.loop. Cannot send message safely.")
            return

        # If message is explicitly meant to be an internal bot command use prefix 'cmd:'
        msg_strip = message.lstrip()
        lower_prefix = msg_strip[:4].lower()
        if lower_prefix == 'cmd:':
            command_text = msg_strip[4:].strip()
            if command_text:
                coro = self._invoke_internal_command_async(channel, command_text)
            else:
                coro = self._send_scheduled_message_async(channel, "No command specified after 'cmd:'.")
        else:
            # Regular (plain text) scheduled message -> send as-is
            coro = self._send_scheduled_message_async(channel, message)
            
        # Submit the async job to the main bot's event loop from the scheduler thread
        future = asyncio.run_coroutine_threadsafe(coro, bot_loop)
        try:
            # Wait up to 60 seconds for the coroutine to complete
            future.result(timeout=60) 
            self.logger.info(f"Scheduled message/command submitted successfully to bot loop.")
        except Exception as e:
            self.logger.exception(f"Failed to execute scheduled task via threadsafe submit: {e}")
            
    
    async def _send_scheduled_message_async(self, channel: str, message: str):
        """Send a scheduled message (async implementation)"""
        try:
            # Try command_manager first, fall back to bot.send_message if available
            if hasattr(self.bot, 'command_manager') and self.bot.command_manager:
                await self.bot.command_manager.send_channel_message(channel, message)
            elif hasattr(self.bot, 'send_message') and callable(self.bot.send_message):
                await self.bot.send_message(channel, message)
            else:
                self.logger.error("No available method to send scheduled message")
        except Exception as e:
            self.logger.exception(f"Error sending scheduled message to {channel}: {e}")

    def start(self):
        """Start the scheduler in a separate thread"""
        self.setup_scheduled_messages() # Call setup on start
        self.scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        self.scheduler_thread.start()
    
    def run_scheduler(self):
        """Run the scheduler in a separate thread"""
        self.logger.info("Scheduler thread started")
        last_log_time = 0
        
        while self.bot.connected:
            current_time = self.get_current_time()
            
            # Log current time every 5 minutes for debugging
            if time.time() - last_log_time > 300:  # 5 minutes
                self.logger.debug(f"Scheduler running - Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                last_log_time = time.time()
            
            # Check for pending scheduled messages
            pending_jobs = schedule.get_jobs()
            if pending_jobs:
                self.logger.debug(f"Found {len(pending_jobs)} scheduled jobs")
            
            # Check for interval-based advertising
            self.check_interval_advertising()
            
            schedule.run_pending()
            time.sleep(1)
        
        self.logger.info("Scheduler thread stopped")
    
    def check_interval_advertising(self):
        """Check if it's time to send an interval-based advert"""
        try:
            advert_interval_hours = self.bot.config.getint('Bot', 'advert_interval_hours', fallback=0)
            if advert_interval_hours <= 0:
                return  # Interval advertising disabled
            
            current_time = time.time()
            
            # Check if enough time has passed since last advert
            if not hasattr(self.bot, 'last_advert_time') or self.bot.last_advert_time is None:
                # First time, set the timer
                self.bot.last_advert_time = current_time
                return
            
            time_since_last_advert = current_time - self.bot.last_advert_time
            interval_seconds = advert_interval_hours * 3600  # Convert hours to seconds
            
            if time_since_last_advert >= interval_seconds:
                self.logger.info(f"Time for interval-based advert (every {advert_interval_hours} hours)")
                self.send_interval_advert()
                self.bot.last_advert_time = current_time
                
        except Exception as e:
            self.logger.error(f"Error checking interval advertising: {e}")
    
    def send_interval_advert(self):
        """
        Send an interval-based advert (synchronous wrapper).
        Submits the async task to the bot's main event loop using threadsafe approach.
        """
        current_time = self.get_current_time()
        self.logger.info(f"📢 Sending interval-based flood advert at {current_time.strftime('%H:%M:%S')}")
        
        # --- FIX: Use threadsafe submission to the main event loop ---
        try:
            # Assumes the running event loop is stored on the bot instance as self.bot.loop
            bot_loop = self.bot.loop 
        except AttributeError:
            self.logger.error("Bot's event loop is not accessible at self.bot.loop. Cannot send advert safely.")
            return
        
        coro = self._send_interval_advert_async()
        
        # Submit the async job to the main bot's event loop from the scheduler thread
        future = asyncio.run_coroutine_threadsafe(coro, bot_loop)
        try:
            # Wait up to 60 seconds for the coroutine to complete
            future.result(timeout=60)
            self.logger.info("Interval-based flood advert submitted successfully to bot loop.")
        except Exception as e:
            self.logger.error(f"Error submitting interval-based advert via threadsafe submit: {e}")
    
    async def _send_interval_advert_async(self):
        """Send an interval-based advert (async implementation)"""
        try:
            # Use the same advert functionality as the manual advert command
            # NOTE: Assumes self.bot.meshcore.commands is available and has send_advert
            await self.bot.meshcore.commands.send_advert(flood=True)
            self.logger.info("Interval-based flood advert sent successfully")
        except Exception as e:
            self.logger.error(f"Error sending interval-based advert: {e}")

    def list_scheduled_messages(self):
        """Return a list of currently scheduled messages for debugging"""
        return [
            f"{time_str} -> {channel}: {message}"
            for time_str, (channel, message) in self.scheduled_messages.items()
        ]
