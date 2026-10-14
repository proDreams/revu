from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    NoAIResponse,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
)


class OpenAICompatiblePort(BaseAIPort):
    def __init__(self, adapter: OpenAICompatibleAdapter) -> None:
        self.adapter = adapter

    @staticmethod
    def _get_messages(
        system_prompt: str, user_prompt: str
    ) -> list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam]:
        messages: list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=user_prompt),
        ]

        return messages

    async def get_comment_response(self, task: ReviewTask) -> str:
        user_prompt = self._get_diff_prompt(task)
        output = await self.adapter.get_chat_response(
            messages=self._get_messages(system_prompt=self._comment_instructions(task), user_prompt=user_prompt)
        )

        content = output.choices[0].message.content

        if not content:
            raise NoAIResponse("OpenAI-compatible provider returned an empty review comment")

        return content

    async def get_inline_response(self, task: ReviewTask) -> ReviewResponseDTO:
        response_model = self._get_response_model(task.git_host)

        user_prompt = self._get_diff_prompt(task)

        output = await self.adapter.get_chat_response(
            messages=self._get_messages(system_prompt=self._inline_instructions(task), user_prompt=user_prompt),
            response_model=response_model,
        )

        parsed_output = output.choices[0].message.parsed

        # A refusal or a plain-text answer leaves ``parsed`` empty; without this
        # check it blew up later as an AttributeError inside a background task.
        if parsed_output is None:
            raise InvalidAIOutput("OpenAI-compatible provider did not return a structured review")

        return ReviewResponseDTO.from_request(
            general_comment=parsed_output.general_comment,  # type: ignore
            comments=[comment.model_dump() for comment in parsed_output.comments],  # type: ignore
            git_host=task.git_host,
        )
