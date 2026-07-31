"""
Chat Type Filters
Custom filters for Telegram update types.
"""
from telegram import Update
from telegram.ext import filters


class ChatTypeFilter(filters.MessageFilter):
    """Filter messages by chat type."""

    def __init__(self, chat_type: str):
        super().__init__()
        self.chat_type = chat_type
        self.data_filter = True

    def filter(self, message: Update) -> bool:
        if not message.effective_chat:
            return False
        return message.effective_chat.type == self.chat_type


class PrivateChatFilter(ChatTypeFilter):
    """Filter for private chats only."""

    def __init__(self):
        super().__init__("private")


class GroupChatFilter(ChatTypeFilter):
    """Filter for group/supergroup chats only."""

    def __init__(self):
        super().__init__("group")


class ChannelChatFilter(ChatTypeFilter):
    """Filter for channel chats only."""

    def __init__(self):
        super().__init__("channel")


# Pre-instantiated filters
private_chat = PrivateChatFilter()
group_chat = GroupChatFilter()
channel_chat = ChannelChatFilter()
non_private_chat = group_chat | channel_chat
