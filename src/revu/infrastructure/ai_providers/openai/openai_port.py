from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    NoAIResponse,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.openai.openai_adapter import OpenAIAdapter


class OpenAIPort(BaseAIPort):
    def __init__(self, adapter: OpenAIAdapter) -> None:
        super().__init__()
        self.adapter = adapter

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        output = await self.adapter.get_chat_response(
            user_input=self._get_diff_prompt(pr_title, pr_body, diff),
            instructions=self._comment_instructions(),
        )

        # No schema is requested in comment mode, so the SDK leaves
        # ``output_parsed`` as None and the answer lives in ``output_text``.
        text = output.output_text

        if not text:
            raise NoAIResponse("OpenAI returned an empty review comment")

        return text

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        response_model = self._get_response_model(git_provider)

        output = await self.adapter.get_chat_response(
            user_input=self._get_diff_prompt(pr_title, pr_body, diff),
            instructions=self._inline_instructions(git_provider),
            response_model=response_model,
        )

        parsed_output = output.output_parsed

        # The model may refuse or answer in free text; both leave parsed=None
        # and used to surface as an unhelpful AttributeError in the background.
        if parsed_output is None:
            raise InvalidAIOutput("OpenAI did not return a structured review")

        return ReviewResponseDTO.from_request(
            general_comment=parsed_output.general_comment,  # type: ignore
            comments=[comment.model_dump() for comment in parsed_output.comments],  # type: ignore
            git_provider=git_provider,
        )
