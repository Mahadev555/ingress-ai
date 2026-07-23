from typing import Any

import httpx

from app.providers.base import NativeRequest, ProviderCreds, UpstreamStreamError
from app.providers.openai import OpenAIAdapter, _safe_json
from app.schemas.unified import GATEWAY_ONLY_FIELDS, ChatCompletionRequest

# Models are addressed as "azure/<deployment>"; this prefix selects the adapter
# and is stripped to recover the Azure deployment name.
AZURE_PREFIX = "azure/"


class AzureOpenAIAdapter(OpenAIAdapter):
    """Azure OpenAI speaks the OpenAI body/response, but routes by deployment
    name and an api-version query param, and authenticates with `api-key`.

    Only request-building differs, so parsing and streaming are inherited.
    """

    def build_request(self, req: ChatCompletionRequest, creds: ProviderCreds) -> NativeRequest:
        deployment = _deployment_name(req.model)
        api_version = creds.extra.get("api_version", "")

        body = req.model_dump(exclude_none=True, exclude=GATEWAY_ONLY_FIELDS)
        body["model"] = deployment

        return NativeRequest(
            method="POST",
            url=(
                f"{creds.base_url}/openai/deployments/{deployment}"
                f"/chat/completions?api-version={api_version}"
            ),
            headers={"api-key": creds.api_key, "Content-Type": "application/json"},
            json=body,
        )

    async def embed(
        self,
        model: str,
        payload: dict[str, Any],
        creds: ProviderCreds,
        client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        deployment = _deployment_name(model)
        api_version = creds.extra.get("api_version", "")
        body = {k: v for k, v in payload.items() if k != "model"}
        resp = await client.post(
            f"{creds.base_url}/openai/deployments/{deployment}/embeddings?api-version={api_version}",
            headers={"api-key": creds.api_key, "Content-Type": "application/json"},
            json=body,
        )
        if resp.status_code != 200:
            raise UpstreamStreamError(resp.status_code, _safe_json(resp))
        return resp.json()


def _deployment_name(model: str) -> str:
    if model.startswith(AZURE_PREFIX):
        return model[len(AZURE_PREFIX) :]
    return model
