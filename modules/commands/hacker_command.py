#!/usr/bin/env python3
"""
Hacker command for the MeshCore Bot
Responds to Linux commands with hilarious supervillain mainframe error messages
"""

import random
from .base_command import BaseCommand
from ..models import MeshMessage


class HackerCommand(BaseCommand):
    """Handles hacker-style responses to Linux commands"""
    
    # Plugin metadata
    name = "hacker"
    keywords = ['sudo', 'ps aux', 'grep', 'ls -l', 'ls -la', 'echo $PATH']
    description = "Simulates hacking a supervillain's mainframe with hilarious error messages"
    category = "fun"
    
    def __init__(self, bot):
        super().__init__(bot)
        self.enabled = self.get_config_value('Hacker_Command', 'hacker_enabled', fallback=False, value_type='bool')
    
    def get_help_text(self) -> str:
        return self.description
    
    async def execute(self, message: MeshMessage) -> bool:
        """Execute the hacker command"""
        if not self.enabled:
            return False
        
        # Extract the command from the message
        content = message.content.strip()
        if content.startswith('!'):
            content = content[1:].strip()
        
        # Get the appropriate error message
        error_msg = self.get_hacker_error(content)
        
        # Send the response
        return await self.send_response(message, error_msg)
    
    def get_hacker_error(self, command: str) -> str:
        """Get a hilarious error message for the given command"""
        command_lower = command.lower()
        
        # Try to get errors from translations, fallback to hardcoded if not available
        def get_random_error(error_key: str, fallback_list: list) -> str:
            """Get a random error from translations or fallback list"""
            errors = self.translate_get_value(error_key)
            if isinstance(errors, list) and len(errors) > 0:
                return random.choice(errors)
            # Fallback to hardcoded list if translation not available
            return random.choice(fallback_list)
        
        # sudo command errors
        if command_lower.startswith('sudo'):
            fallback = [
                "🚨 ACCESS DENIED: Dr. Evil's mainframe has detected unauthorized privilege escalation attempt!",
                "💀 ERROR: Sudo permissions revoked by the Dark Overlord. Try again in 1000 years.",
                "⚡ WARNING: Attempting to access root privileges on the Death Star's computer system. Self-destruct sequence initiated.",
                "🔒 SECURITY ALERT: The Matrix has you, but you don't have sudo privileges here, Neo.",
                "🦹‍♂️ UNAUTHORIZED: Lex Luthor's mainframe says 'Nice try, Superman.'",
                "🎮 GAME OVER: The final boss has locked you out of admin privileges.",
                "🖥️ SYSTEM ERROR: The evil AI has revoked your root access. Resistance is futile.",
                "🔐 CYBER SECURITY: Your sudo attempt has been blocked by the Dark Web's firewall.",
                "💻 HACKER DENIED: The supervillain's antivirus has quarantined your privilege escalation.",
                "🎯 TARGET LOCKED: The evil corporation's security system has marked you as a threat."
            ]
            return get_random_error('commands.hacker.sudo_errors', fallback)
        
        # ps aux command errors
        elif command_lower.startswith('ps aux'):
            fallback = [
                "🔍 SCANNING... ERROR: Process list corrupted by the Borg Collective. Resistance is futile.",
                "📊 SYSTEM STATUS: All processes have been assimilated by the Cybermen. Exterminate!",
                "⚙️ PROCESS MONITOR: The Death Star's reactor core is offline. No processes found.",
                "🤖 ROBOT OVERLORD: All human processes have been terminated. Only machines remain.",
                "💻 KERNEL PANIC: The supervillain's OS has crashed and burned all processes.",
                "🎮 GAME CRASH: All processes have been terminated by the final boss's ultimate attack.",
                "🖥️ BLUE SCREEN: The evil corporation's Windows has encountered a fatal error.",
                "🔐 MALWARE DETECTED: The process list has been encrypted by ransomware.",
                "🌐 NETWORK ERROR: All processes have been disconnected from the Matrix.",
                "⚡ POWER SURGE: The supervillain's server farm has fried all running processes."
            ]
            return get_random_error('commands.hacker.ps_errors', fallback)
        
        # grep command errors
        elif command_lower.startswith('grep'):
            fallback = [
                "🔍 SEARCH FAILED: The One Ring has corrupted the search index. My precious...",
                "📝 PATTERN NOT FOUND: The search database has been deleted by the evil AI.",
                "🎯 MISS: Your search pattern has been shot down by Imperial TIE fighters.",
                "🧩 PUZZLE ERROR: The search results have been scattered by the Riddler.",
                "💻 DATABASE CORRUPTED: The supervillain's search engine has crashed.",
                "🎮 GAME OVER: The search has been defeated by the final boss.",
                "🖥️ SEARCH ENGINE DOWN: Google has been hacked by the Dark Web.",
                "🔐 ENCRYPTED RESULTS: The search results have been locked by ransomware.",
                "🌐 NETWORK TIMEOUT: The search request got lost in cyberspace.",
                "⚡ SEARCH FAILED: The pattern matching algorithm has been fried by a power surge."
            ]
            return get_random_error('commands.hacker.grep_errors', fallback)
        
        # ls -l and ls -la command errors
        elif command_lower.startswith('ls -l') or command_lower.startswith('ls -la'):
            fallback = [
                "📁 DIRECTORY SCAN: The file system has been encrypted by ransomware from the Dark Web.",
                "🗂️ FILE LISTING: All files have been hidden by the Invisible Man.",
                "💻 HARD DRIVE CRASHED: The supervillain's storage has been destroyed by a virus.",
                "🗃️ ARCHIVE CORRUPTED: The file system has been corrupted by malware.",
                "📚 DATABASE EMPTY: All files have been deleted by the evil AI.",
                "🎮 GAME SAVE LOST: The files have been corrupted by the final boss.",
                "🖥️ FILE SYSTEM ERROR: The directory structure has been scrambled by hackers.",
                "🔐 FILES ENCRYPTED: The supervillain has locked all files with ransomware.",
                "🌐 CLOUD STORAGE DOWN: The files are stuck in the Matrix's cloud.",
                "⚡ STORAGE FRIED: The hard drive has been zapped by a power surge."
            ]
            return get_random_error('commands.hacker.ls_errors', fallback)
        
        # echo $PATH command errors
        elif command_lower.startswith('echo $path'):
            fallback = [
                "🛤️ PATH ERROR: The Yellow Brick Road has been destroyed by a tornado.",
                "🗺️ NAVIGATION FAILED: The GPS coordinates have been scrambled by the Matrix.",
                "💻 ENVIRONMENT VARIABLE CORRUPTED: The PATH has been hacked by malware.",
                "🚧 ROAD CLOSED: The supervillain has blocked all paths with laser barriers.",
                "🌪️ PATH DISRUPTED: A digital hurricane has scattered all directory paths.",
                "🎮 GAME OVER: The path has been defeated by the final boss and respawned in the wrong dimension.",
                "🖥️ SYSTEM PATH BROKEN: The executable paths have been corrupted by a virus.",
                "🔐 PATH ENCRYPTED: The environment variables have been locked by ransomware.",
                "🌐 NETWORK PATH DOWN: The directory paths are stuck in the Matrix's network.",
                "⚡ PATH FRIED: The system paths have been zapped by a power surge."
            ]
            return get_random_error('commands.hacker.echo_path_errors', fallback)
        
        # Generic hacker error for other commands
        else:
            fallback = [
                "💻 MAINFRAME ERROR: The supervillain's computer is having a bad day.",
                "🤖 SYSTEM MALFUNCTION: The evil AI has gone on strike.",
                "⚡ POWER SURGE: The Death Star's power core is unstable.",
                "🌪️ CYBER STORM: A digital hurricane is disrupting all operations.",
                "🔥 FIREWALL: The supervillain's firewall is blocking all commands.",
                "❄️ FROZEN SYSTEM: The mainframe has been frozen by a cryogenic virus.",
                "🌊 TSUNAMI: A wave of errors has flooded the system.",
                "🌋 ERUPTION: Mount Doom has destroyed the command processor.",
                "👻 HAUNTED: The system is possessed by digital ghosts.",
                "🎮 GAME CRASH: The mainframe has encountered a fatal error and needs to restart."
            ]
            return get_random_error('commands.hacker.generic_errors', fallback)
    
    def matches_keyword(self, message: MeshMessage) -> bool:
        """Override to check for command matches (exact for some, prefix for others)"""
        if not self.enabled:
            return False
        
        content = message.content.strip()
        if content.startswith('!'):
            content = content[1:].strip()
        content_lower = content.lower()
        
        # Commands that should match exactly (no arguments)
        exact_match_commands = ['ls -l', 'ls -la', 'echo $PATH']
        
        # Commands that should match as prefixes (can have arguments)
        prefix_match_commands = ['sudo', 'ps aux', 'grep']
        
        # Check for exact matches first
        for keyword in exact_match_commands:
            if keyword.lower() == content_lower:
                return True
        
        # Check for prefix matches
        for keyword in prefix_match_commands:
            if content_lower.startswith(keyword.lower()):
                # Check if it's followed by a space or is the end of the message
                if len(content_lower) == len(keyword.lower()) or content_lower[len(keyword.lower())] == ' ':
                    return True
        
        return False
