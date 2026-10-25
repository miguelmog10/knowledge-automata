"""Project exceptions for the LLM service layer (ADR-0012).

Messages never contain API keys, prompts or artifact text. Provider error messages are
included only where they describe our request (``LLMRequestError``).
"""

from knowledge_automata.llm.interfaces import Usage


class LLMError(Exception):
    """Base class for every error raised by the LLM service layer."""


class LLMConfigError(LLMError):
    """Missing or invalid settings, for example no ``CO_API_KEY``."""


class LLMAuthError(LLMError):
    """The provider rejected the API key (401, 403 or 498)."""


class LLMRateLimitError(LLMError):
    """The provider refused the call for rate or quota reasons, after the SDK's retries.

    ``monthly_cap`` is true when the limit only resets next month (a trial key's monthly
    call cap or the account's billing cap), so retrying soon cannot help.
    """

    def __init__(self, message: str, *, monthly_cap: bool = False) -> None:
        super().__init__(message)
        self.monthly_cap = monthly_cap


class LLMRequestError(LLMError):
    """The provider rejected our request (other 4xx), for example a schema it does not accept."""


class LLMUnavailableError(LLMError):
    """Server errors after retries, timeouts and network errors."""


class LLMResponseError(LLMError):
    """The response is not usable: not JSON, not a JSON object, truncated or incomplete.

    ``usage`` carries the billed units when the provider charged for the unusable response,
    so the event log still records the cost.
    """

    def __init__(self, message: str, *, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage
