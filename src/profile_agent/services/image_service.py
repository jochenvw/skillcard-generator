"""Image service — Azure OpenAI image generation for card image generation.

Note: The images.generate endpoint used here does not support reference-image input.
This adapter accepts uploaded photo metadata but generates based on text
description only. The interface is designed so a future model with
reference-image support can be swapped in.
"""

from __future__ import annotations

import logging

from profile_agent.models.llm_contracts import ImageGenerationRequest, ImageGenerationResult

logger = logging.getLogger(__name__)


class ImageService:
    """Thin adapter around Azure OpenAI image generation."""

    def __init__(self, openai_client, default_deployment: str = "dall-e-3") -> None:
        self._client = openai_client
        self._default_deployment = default_deployment

    # Models that do not support style/quality params and always return base64.
    _GPT_IMAGE_MODELS = ("gpt-image-1", "gpt-image-2")

    def _is_gpt_image_model(self, deployment: str) -> bool:
        return any(deployment.startswith(prefix) for prefix in self._GPT_IMAGE_MODELS)

    async def generate_card_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate a card image from a prompt using Azure OpenAI image generation."""
        deployment = request.model_deployment or self._default_deployment
        gpt_image = self._is_gpt_image_model(deployment)

        # Build kwargs: gpt-image-* models reject style/quality params.
        generate_kwargs: dict = {
            "model": deployment,
            "prompt": request.prompt,
            "size": request.size,
            "n": 1,
        }
        if not gpt_image:
            generate_kwargs["quality"] = request.quality
            generate_kwargs["style"] = request.style

        try:
            response = await self._client.images.generate(**generate_kwargs)
        except Exception as e:
            # Fallback: if the model still rejects a param, retry with minimal kwargs.
            if "Unknown parameter" in str(e) or "unsupported_parameter" in str(e):
                logger.warning("Retrying image generation with minimal params: %s", e)
                try:
                    response = await self._client.images.generate(
                        model=deployment,
                        prompt=request.prompt,
                        size=request.size,
                        n=1,
                    )
                except Exception as retry_e:
                    logger.error("Image generation failed (retry): %s", retry_e)
                    return ImageGenerationResult(
                        success=False,
                        error=str(retry_e),
                        model_deployment=deployment,
                    )
            else:
                logger.error("Image generation failed: %s", e)
                return ImageGenerationResult(
                    success=False,
                    error=str(e),
                    model_deployment=deployment,
                )

        image_data = response.data[0]
        # gpt-image-2 and compatible models return base64 instead of a URL.
        raw_bytes: bytes | None = None
        if getattr(image_data, "b64_json", None):
            import base64
            raw_bytes = base64.b64decode(image_data.b64_json)
        return ImageGenerationResult(
            success=True,
            image_url=image_data.url or "",
            raw_bytes=raw_bytes,
            revised_prompt=getattr(image_data, "revised_prompt", None) or "",
            model_deployment=deployment,
        )

    async def download_image(self, url: str) -> bytes:
        """Download a generated image from its URL."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=60)
            response.raise_for_status()
            return response.content
