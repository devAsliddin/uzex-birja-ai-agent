"""Conversation context for the AI engine."""


from app.ai.providers.base import LLMMessage


class ConversationContext:
    """Holds a conversation's message history and metadata."""

    def __init__(
        self,
        conversation_id: int | None = None,
        user_id: int | None = None,
        language: str = "ru",
        system_prompt: str | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.language = language
        self.system_prompt = system_prompt
        self.messages: list[LLMMessage] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_message(self, content: str) -> None:
        self.messages.append({"role": "tool", "content": content})

    def get_messages(self) -> list[LLMMessage]:
        return list(self.messages)

