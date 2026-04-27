"""Generate vintage-poster cover images per route via local FLUX.2 Klein 4B.

Prompts are stored back into ``routes.yaml`` under ``image_prompt`` per route.
On the next run, the regenerated prompt is compared with the stored one — if
unchanged and the image file exists, generation is skipped. This means the
prompt itself is the cache key (no separate hash field needed) and the user
can hand-tune prompts by editing the yaml.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from open_rando.fetchers.discovery import ROUTES_YAML_PATH
from open_rando.models import Landmark, Route

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger("open_rando")

FLUX_MODEL_ID = "black-forest-labs/FLUX.2-klein-4b"
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 384
WEBP_QUALITY = 82
NUM_INFERENCE_STEPS = 10
GUIDANCE_SCALE = 0.0
PROMPT_NEGATIVE_SUFFIX = (
    " Avoid: text, letters, words, labels, signage, captions, "
    "modern buildings, cars, people, photo realism, "
    "color washes, paper texture, aged paper, sepia tones, "
    "watermarks, frames, borders."
)

IMAGES_SUBDIRECTORY = "images"

_TERRAIN_PHRASES: dict[str, str] = {
    "mountain": "rugged mountain ridges and snow-flecked peaks",
    "coastal": "windswept sea cliffs and distant blue horizon",
    "forest": "dense ancient forest with sun-dappled clearings",
    "hills": "rolling green hills and patchwork farmland",
    "plains": "open plains and meandering rivers",
}

_LANDMARK_PROSE: dict[str, str] = {
    "castle": "a hilltop medieval castle",
    "ruins": "weathered stone ruins overgrown with ivy",
    "fort": "an old stone fortress",
    "monument": "a stately stone monument",
    "memorial": "a quiet memorial cross",
    "archaeological_site": "ancient archaeological remains",
    "tower": "a lone watchtower",
    "wayside_cross": "a wayside stone cross",
    "viewpoint": "a panoramic viewpoint over the valley",
    "attraction": "a scenic local attraction",
    "peak": "a prominent rocky peak",
    "cliff": "dramatic limestone cliffs",
    "cave_entrance": "the dark mouth of a cave",
    "waterfall": "a cascading waterfall",
    "lighthouse": "a tall coastal lighthouse",
}


def build_image_prompt(route: Route) -> str:
    """Build a pen-and-ink hatching prompt from route metadata + landmarks.

    Deterministic for a given route+landmark snapshot — prompt equality is
    used as the regeneration cache key.
    """
    region = route.region or "rural France"
    terrain_phrase = _build_terrain_phrase(route.terrain)
    landmark_phrase, _ = _build_landmark_phrases(route.landmarks)
    description_excerpt = (route.description or "").strip()[:200]

    parts = [
        "A detailed pen-and-ink drawing in cross-hatching style, "
        "antique engraving aesthetic reminiscent of 19th-century travel "
        "illustrations, monochrome black ink on a clean white background, "
        "fine line work with dense hatching for shadow and depth.",
        f"Subject: a hiking landscape in {region}, {terrain_phrase}.",
    ]
    if landmark_phrase:
        parts.append(f"Featuring: {landmark_phrase}.")
    if description_excerpt:
        parts.append(f"Atmosphere: {description_excerpt}")
    parts.append(
        "Style: intricate stippling and cross-hatching, etching-like texture, "
        "wide cinematic banner composition, sketchbook feel, no color, "
        "no text or labels of any kind."
    )
    return " ".join(parts) + PROMPT_NEGATIVE_SUFFIX


def _build_terrain_phrase(terrain_tags: list[str]) -> str:
    phrases = [_TERRAIN_PHRASES[tag] for tag in terrain_tags if tag in _TERRAIN_PHRASES]
    if not phrases:
        return "open countryside under a soft sky"
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " and " + phrases[-1]


def _build_landmark_phrases(landmarks: list[Landmark]) -> tuple[str, str]:
    """Return (subject_phrase, label_phrase).

    subject_phrase describes the landmarks for the scene composition.
    label_phrase lists the names that should be drawn as text labels.
    """
    if not landmarks:
        return "", ""
    subject_pieces: list[str] = []
    label_pieces: list[str] = []
    for landmark in landmarks[:2]:
        if landmark.name:
            descriptor = _LANDMARK_PROSE.get(landmark.kind, landmark.kind.replace("_", " "))
            subject_pieces.append(f"{descriptor} ({landmark.name})")
            label_pieces.append(f'"{landmark.name}"')
        else:
            unnamed = _LANDMARK_PROSE.get(landmark.kind)
            if unnamed:
                subject_pieces.append(unnamed)
    return ", ".join(subject_pieces), ", ".join(label_pieces)


def generate_image(
    route: Route,
    output_directory: Path,
    *,
    force: bool = False,
) -> str | None:
    """Generate (or reuse) the cover image for a route.

    Returns the relative path under the data directory (e.g.
    ``images/abc123.webp``) on success, or ``None`` if generation was skipped
    because the image extra is not installed.

    Cache contract: if the route's stored ``image_prompt`` in ``routes.yaml``
    matches the freshly built prompt and the output file exists, regeneration
    is skipped. ``force=True`` overrides the cache.
    """
    prompt = build_image_prompt(route)
    relative_path = f"{IMAGES_SUBDIRECTORY}/{route.identifier}.webp"
    output_path = output_directory / relative_path

    stored_prompt = _read_stored_prompt(route.path_ref)

    cache_hit = (
        not force and stored_prompt is not None and stored_prompt == prompt and output_path.exists()
    )
    if cache_hit:
        logger.info("  Image cache hit for %s — reusing %s", route.path_ref, relative_path)
        return relative_path

    try:
        pipeline = _load_flux_pipeline()
    except _ImageDependencyMissingError as error:
        logger.warning(
            "  Skipping image generation for %s — %s. Install with `uv sync --extra images`.",
            route.path_ref,
            error,
        )
        return None
    except Exception:
        logger.exception("  Failed to load FLUX pipeline; skipping image generation")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    seed = _seed_for_route(route.identifier)

    logger.info("  Generating image for %s (seed=%d)", route.path_ref, seed)
    try:
        image = _run_pipeline(pipeline, prompt, seed)
    except Exception:
        logger.exception("  Image generation failed for %s; continuing", route.path_ref)
        return None

    image.save(output_path, format="WEBP", quality=WEBP_QUALITY, method=6)
    logger.info("  Wrote %s", output_path)

    _write_stored_prompt(route.path_ref, prompt)

    return relative_path


def _seed_for_route(route_id: str) -> int:
    digest = hashlib.sha256(route_id.encode()).hexdigest()
    return int(digest[:8], 16)


# Pipeline singleton, lazy-loaded ----------------------------------------------

_pipeline_singleton: Any | None = None


class _ImageDependencyMissingError(RuntimeError):
    pass


def _load_flux_pipeline() -> Any:
    global _pipeline_singleton
    if _pipeline_singleton is not None:
        return _pipeline_singleton

    try:
        import torch
        from diffusers import DiffusionPipeline
    except ImportError as error:
        raise _ImageDependencyMissingError(str(error)) from error

    if torch.cuda.is_available():
        device = "cuda"
        dtype = torch.bfloat16
    elif torch.backends.mps.is_available():
        device = "mps"
        dtype = torch.bfloat16
    else:
        device = "cpu"
        dtype = torch.float32

    logger.info("Loading FLUX pipeline %s on %s", FLUX_MODEL_ID, device)
    pipeline = DiffusionPipeline.from_pretrained(  # type: ignore[no-untyped-call]
        FLUX_MODEL_ID, torch_dtype=dtype
    )
    pipeline = pipeline.to(device)
    _pipeline_singleton = pipeline
    return pipeline


def _run_pipeline(pipeline: Any, prompt: str, seed: int) -> Image:
    import torch

    generator = torch.Generator(device="cpu").manual_seed(seed)
    output = pipeline(
        prompt=prompt,
        width=IMAGE_WIDTH,
        height=IMAGE_HEIGHT,
        num_inference_steps=NUM_INFERENCE_STEPS,
        guidance_scale=GUIDANCE_SCALE,
        generator=generator,
    )
    image: Image = output.images[0]
    return image


# routes.yaml round-trip -------------------------------------------------------

_yaml_singleton: Any | None = None


def _yaml() -> Any:
    """Lazy-load ruamel.yaml round-trip parser (preserves comments/order)."""
    global _yaml_singleton
    if _yaml_singleton is not None:
        return _yaml_singleton

    from ruamel.yaml import YAML

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    _yaml_singleton = yaml
    return yaml


def _read_stored_prompt(path_ref: str) -> str | None:
    yaml = _yaml()
    try:
        with ROUTES_YAML_PATH.open(encoding="utf-8") as handle:
            data = yaml.load(handle)
    except Exception:
        logger.exception("Could not read %s for prompt cache", ROUTES_YAML_PATH)
        return None

    for entry in data.get("routes", []):
        if entry.get("ref") == path_ref:
            stored = entry.get("image_prompt")
            return str(stored) if stored is not None else None
    return None


def _write_stored_prompt(path_ref: str, prompt: str) -> None:
    yaml = _yaml()
    try:
        with ROUTES_YAML_PATH.open(encoding="utf-8") as handle:
            data = yaml.load(handle)
    except Exception:
        logger.exception("Could not read %s to write prompt cache", ROUTES_YAML_PATH)
        return

    from ruamel.yaml.scalarstring import LiteralScalarString

    target_entry = None
    for entry in data.get("routes", []):
        if entry.get("ref") == path_ref:
            target_entry = entry
            break

    if target_entry is None:
        logger.warning("Could not find %s in %s for prompt cache", path_ref, ROUTES_YAML_PATH)
        return

    target_entry["image_prompt"] = LiteralScalarString(prompt)

    with ROUTES_YAML_PATH.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle)
