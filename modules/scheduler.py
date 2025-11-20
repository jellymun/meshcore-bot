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
        from .models import MeshMessage

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
