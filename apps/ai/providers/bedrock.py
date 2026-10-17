"""AWS Bedrock (Claude/Mistral) через Converse API — прод-маршрут ЕС.

ЕС — ALLOWLIST (ревью AI-0: список «плохих» префиксов пропускал ARN и будущие
геопрофили): регион `eu-*` и модель либо EU-профиль `eu.<провайдер>.…`, либо голый ID
`<провайдер>.…` (обрабатывается в регионе вызова). ARN, `global.`, `us.` и любой
неизвестный префикс — вне ЕС."""

from __future__ import annotations

from django.conf import settings

from apps.secrets.store import get_or_setting

from ..errors import AIConfigError, AIRateLimited, AIRefused, AIUnavailable
from .base import Provider, ProviderRequest, ProviderResponse

MODEL_PROVIDERS = ("anthropic.", "mistral.", "amazon.", "meta.", "cohere.")
_THROTTLE = {"ThrottlingException", "TooManyRequestsException", "ServiceQuotaExceededException"}
_UNAVAILABLE = {
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
}


def converse_kwargs(req: ProviderRequest) -> dict:
    content = [{"image": {"format": img.fmt, "source": {"bytes": img.data}}} for img in req.images]
    content.append({"text": req.prompt})
    inference = {"maxTokens": req.max_tokens}
    if req.temperature is not None:
        inference["temperature"] = req.temperature
    kwargs = {
        "modelId": req.model,
        "messages": [{"role": "user", "content": content}],
        "inferenceConfig": inference,
    }
    if req.system:
        kwargs["system"] = [{"text": req.system}]
    return kwargs


def parse_converse(data: dict, model: str) -> ProviderResponse:
    if data.get("stopReason") in ("content_filtered", "guardrail_intervened"):
        raise AIRefused("content filter")
    blocks = ((data.get("output") or {}).get("message") or {}).get("content") or []
    usage = data.get("usage") or {}
    return ProviderResponse(
        text="".join(b.get("text", "") for b in blocks),
        tokens_in=int(usage.get("inputTokens") or 0),
        tokens_out=int(usage.get("outputTokens") or 0),
        model=model,
    )


class BedrockProvider(Provider):
    name = "bedrock"

    def eu_for(self, model: str) -> bool:
        region = settings.AWS_BEDROCK_REGION or ""
        model = model or ""
        if not region.startswith("eu-"):
            return False
        bare = model[3:] if model.startswith("eu.") else model
        return bare.startswith(MODEL_PROVIDERS)

    def _client(self, timeout_s: int):
        import boto3
        from botocore.config import Config

        key_id = get_or_setting("aws_bedrock_access_key_id", "AWS_BEDROCK_ACCESS_KEY_ID")
        secret = get_or_setting("aws_bedrock_secret_access_key", "AWS_BEDROCK_SECRET_ACCESS_KEY")
        if not key_id or not secret:
            raise AIConfigError("bedrock credentials missing")
        return boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_BEDROCK_REGION,
            # Явный адрес: boto3 иначе берёт AWS_ENDPOINT_URL* из окружения процесса.
            endpoint_url=f"https://bedrock-runtime.{settings.AWS_BEDROCK_REGION}.amazonaws.com",
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            config=Config(
                connect_timeout=5,
                read_timeout=timeout_s,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )

    def call(self, req: ProviderRequest) -> ProviderResponse:
        from botocore.exceptions import BotoCoreError, ClientError

        if not req.model:
            raise AIConfigError("bedrock model missing")
        client = self._client(req.timeout_s)
        try:
            data = client.converse(**converse_kwargs(req))
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code", "")
            if code in _THROTTLE:
                raise AIRateLimited(code) from None
            if code in _UNAVAILABLE:
                raise AIUnavailable(code) from None
            raise AIConfigError(code or "client error") from None
        except BotoCoreError as exc:
            raise AIUnavailable(type(exc).__name__) from None
        return parse_converse(data, req.model)
