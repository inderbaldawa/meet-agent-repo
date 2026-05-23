"""Single-call wrapper around Google Cloud Vision."""

from __future__ import annotations

import logging
from typing import TypedDict

from google.cloud import vision

log = logging.getLogger(__name__)


class VisionResult(TypedDict):
    labels: list[str]
    text: str
    logos: list[str]


_client: vision.ImageAnnotatorClient | None = None


def client() -> vision.ImageAnnotatorClient:
    global _client
    if _client is None:
        _client = vision.ImageAnnotatorClient()
    return _client


def analyze(image_bytes: bytes) -> VisionResult:
    image = vision.Image(content=image_bytes)
    features = [
        vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION, max_results=10),
        vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
        vision.Feature(type_=vision.Feature.Type.LOGO_DETECTION, max_results=5),
    ]
    request = vision.AnnotateImageRequest(image=image, features=features)
    response = client().annotate_image(request=request)
    if response.error.message:
        log.warning("vision API error: %s", response.error.message)
        return VisionResult(labels=[], text="", logos=[])
    text = response.text_annotations[0].description if response.text_annotations else ""
    return VisionResult(
        labels=[l.description for l in response.label_annotations],
        text=text.strip(),
        logos=[l.description for l in response.logo_annotations],
    )
