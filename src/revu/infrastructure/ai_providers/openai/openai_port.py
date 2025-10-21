from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.openai.openai_adapter import (
    OpenAIAdapter,
    get_openai_adapter,
)
from revu.infrastructure.ai_providers.base import BaseAIPort


class OpenAIPort(BaseAIPort):
    def __init__(self, adapter: OpenAIAdapter) -> None:
        super().__init__()
        self.adapter = adapter

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        output = await self.adapter.get_chat_response(
            user_input=self._get_diff_prompt(pr_title, pr_body, diff),
            instructions=self.system_prompt or self._get_comment_prompt(),
        )

        return output.output_parsed  # type: ignore

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        system_prompt = self._get_prompt(git_provider)
        
        if self.system_prompt:
            system_prompt = self.system_prompt

        response_model = self._get_response_model(git_provider)

        output = await self.adapter.get_chat_response(
            user_input=self._get_diff_prompt(pr_title, pr_body, diff),
            instructions=system_prompt,
            response_model=response_model,
        )

        parsed_output = output.output_parsed

        return ReviewResponseDTO.from_request(
            general_comment=parsed_output.general_comment,  # type: ignore
            comments=[comment.model_dump() for comment in parsed_output.comments],  # type: ignore
            git_provider=git_provider,
        )
    


def get_openai_port() -> OpenAIPort:
    return OpenAIPort(adapter=get_openai_adapter())
