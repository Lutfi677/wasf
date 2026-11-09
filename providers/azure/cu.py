import time
from typing import Any

from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential

ServiceError = HttpResponseError


def make_client(endpoint: str) -> ContentUnderstandingClient:
    return ContentUnderstandingClient(endpoint=endpoint, credential=DefaultAzureCredential())


def analyzer_exists(client: ContentUnderstandingClient, analyzer_id: str) -> bool:
    try:
        client.get_analyzer(analyzer_id)
    except ResourceNotFoundError:
        return False
    return True


def create_analyzer(client: ContentUnderstandingClient, analyzer_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    return client.begin_create_analyzer(analyzer_id, definition).result().as_dict()


def analyze(client: ContentUnderstandingClient, analyzer_id: str, data: bytes) -> tuple[dict[str, Any], dict[str, Any], float]:
    started = time.perf_counter()
    poller = client.begin_analyze_binary(analyzer_id=analyzer_id, binary_input=data, content_type="application/pdf")
    result = poller.result()
    seconds = time.perf_counter() - started
    usage = poller.usage
    return result.as_dict(), usage.as_dict() if usage is not None else {}, seconds
