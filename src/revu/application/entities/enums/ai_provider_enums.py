from enum import StrEnum


class AIProviderEnum(StrEnum):
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    GIGACHAT = "gigachat"
    YANDEXGPT = "yandexgpt"
