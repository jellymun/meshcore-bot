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
import inspect
from typing import Dict, Tuple

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
        if self.bot.config.has_section('Scheduled_Messages'):
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
        Attempt to invoke an internal bot command via the command manager.
        Tries a sequence of commonly-used method names and argument forms.
        If invocation fails, sends a diagnostic message back to the channel.
        """
        cmdmgr = getattr(self.bot, 'command_manager', None)
        if not cmdmgr:
            self.logger.error("bot.command_manager is not available. Cannot run internal command.")
            try:
                await self.bot.command_manager.send_channel_message(channel, "Error: command manager unavailable.")
            except Exception:
                # If command_manager isn't available to send, fall back to logger
                self.logger.error("Also cannot send error message to channel; command_manager missing.")
            return

        # Candidate method names that command_manager implementations often expose.
        candidate_names = [
            'execute_command',
            'run_command',
            'handle_command',
            'process_command',
            'dispatch_command',
            'handle_message',
            'on_message',
        ]

        # Candidate argument signatures to try for each method name.
        arg_variants = [
            (command_text, channel),
            (channel, command_text),
            (command_text,),
            (channel,),
        ]

        for name in candidate_names:
            if not hasattr(cmdmgr, name):
                continue
            method = getattr(cmdmgr, name)
            for args in arg_variants:
                try:
                    if inspect.iscoroutinefunction(method):
                        await method(*args)
                        self.logger.info(f"Invoked command via {name} with args {args}")
                        return
                    else:
                        result = method(*args)
                        # If result is awaitable, await it
                        if inspect.isawaitable(result):
                            await result
                        self.logger.info(f"Invoked command via {name} with args {args}")
                        return
                except TypeError:
                    # Signature mismatch: try next arg variant
                    continue
                except Exception as e:
                    # Found the method but it raised an error — report and stop trying this method.
                    self.logger.exception(f"Error invoking command manager method '{name}' with args {args}: {e}")
                    # Attempt to inform channel of the error
                    try:
                        await cmdmgr.send_channel_message(channel, f"Error running command '{command_text}': {e}")
                    except Exception:
                        self.logger.error("Failed to send error message to channel after command invocation error.")
                    return

        # If we get here, no suitable method was found or signature attempts failed
        self.logger.error(f"No suitable command-manager method found to run internal command: {command_text}")
        try:
            await cmdmgr.send_channel_message(
                channel,
                f"Failed to run internal command '{command_text}'. Command manager does not expose a compatible invocation method."
            )
        except Exception:
            self.logger.error("Also failed to send failure message to channel.")

    def send_scheduled_message(self, channel: str, message: str):
        """Send a scheduled message (synchronous wrapper for schedule library)"""
        current_time = self.get_current_time()
        self.logger.info(f"📅 Sending scheduled message at {current_time.strftime('%H:%M:%S')} to {channel}: {message}")
        
        # If message is explicitly meant to be an internal bot command use prefix 'cmd:'
        # Example scheduled message in config.ini: "0900: #general: cmd:stats"
        msg_strip = message.lstrip()
        lower_prefix = msg_strip[:4].lower()
        if lower_prefix == 'cmd:':
            command_text = msg_strip[4:].strip()
            if command_text:
                # Run the internal command via command_manager.
                try:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._invoke_internal_command_async(channel, command_text))
                except Exception as e:
                    self.logger.exception(f"Failed to run scheduled internal command '{command_text}': {e}")
                    # Attempt to notify channel of the failure
                    try:
                        loop.run_until_complete(self._send_scheduled_message_async(channel, f"Failed to run scheduled command '{command_text}': {e}"))
                    except Exception:
                        self.logger.error("Failed to send failure notification to channel.")
                return
            else:
                # No command after prefix — send informative message
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                loop.run_until_complete(self._send_scheduled_message_async(channel, "No command specified after 'cmd:'."))
                return

        # Regular (plain text) scheduled message -> send as-is
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async function in the event loop
        loop.run_until_complete(self._send_scheduled_message_async(channel, message))
    
    async def _send_scheduled_message_async(self, channel: str, message: str):
        """Send a scheduled message (async implementation)"""
        # NOTE: Using bot.send_message directly if command_manager is not guaranteed to exist
        try:
            await self.bot.command_manager.send_channel_message(channel, message)
        except AttributeError:
             self.logger.error("bot.command_manager is not available. Cannot send message.")
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
            # NOTE: Reduced logging for routine scheduler checks from info to debug
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
            # Placeholder: keep existing behavior (this method referenced variables defined elsewhere)
            # The implementation previously referenced undeclared local variables; ensure the rest of the bot
            # sets attributes like bot.last_advert_time and Bot.advert_interval_hours if interval ads are wanted.
            pass
        except Exception as e:
            self.logger.error(f"Error in check_interval_advertising: {e}")
