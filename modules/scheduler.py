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
    
    import asyncio
    
    # Check if message is 'get-update' and replace with script output
    if message.strip().lower() == 'get-update':
        try:
            import subprocess
            self.logger.info("🔄 Executing get-update.py script")
            
            # Execute get-update.py synchronously 
            #assume that it will read the script from the package directory ; unsure how to code this apart from hard coding.
            result = subprocess.run(
                ['python3', 'get-update.py'], 
                capture_output=True, 
                text=True, 
                timeout=60
            )
            
            if result.stdout.strip():
                message = result.stdout.strip()
                self.logger.info("✅ get-update.py executed successfully")
            else:
                message = "get-update.py executed - no output"
                self.logger.info("ℹ️ get-update.py executed but returned no output")
                
            if result.stderr.strip():
                error_msg = result.stderr.strip()
                message += f"\n[Errors: {error_msg}]"
                self.logger.warning(f"⚠️ get-update.py stderr: {error_msg}")
                
        except subprocess.TimeoutExpired:
            message = "get-update.py timed out after 5 minutes"
            self.logger.error("⏰ get-update.py execution timed out")
        except Exception as e:
            message = f"Error running get-update.py: {str(e)}"
            self.logger.error(f"❌ Error executing get-update.py: {str(e)}")
    
    # Create a new event loop for this thread if one doesn't exist
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Run the async function in the event loop
    loop.run_until_complete(self._send_scheduled_message_async(channel, message))

async def _send_scheduled_message_async(self, channel: str, message: str):
    """Send a scheduled message (async implementation)"""
    await self.bot.command_manager.send_channel_message(channel, message)
    
    def start(self):
        """Start the scheduler in a separate thread"""
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
                self.logger.info(f"Scheduler running - Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
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
        """Send an interval-based advert (synchronous wrapper)"""
        current_time = self.get_current_time()
        self.logger.info(f"📢 Sending interval-based flood advert at {current_time.strftime('%H:%M:%S')}")
        
        import asyncio
        
        # Create a new event loop for this thread if one doesn't exist
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async function in the event loop
        loop.run_until_complete(self._send_interval_advert_async())
    
    async def _send_interval_advert_async(self):
        """Send an interval-based advert (async implementation)"""
        try:
            # Use the same advert functionality as the manual advert command
            await self.bot.meshcore.commands.send_advert(flood=True)
            self.logger.info("Interval-based flood advert sent successfully")
        except Exception as e:
            self.logger.error(f"Error sending interval-based advert: {e}")
