"""Generate vintage-poster cover images per route via local FLUX.2 Klein 4B.

Per-route content (subject, landmarks, landscape, description) is stored in
``routes.yaml`` under ``image_prompt`` so the user can hand-tune each entry.
The shared style suffix (pen-and-ink, hatching, banner composition, lighting)
lives as a Python constant in this module — single source of truth, swap once
to restyle the whole catalog. Final FLUX prompt = ``stored_content + STYLE``.

Cache key: stored content equality + image file existence. Stored content
wins over freshly built content, so hand-edits are never overwritten by
``generate_image``. Bulk-seed via ``images --populate-prompts``.
"""

from __future__ import annotations

import logging
import re
import secrets
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


IMAGE_STYLE_SUFFIX = (
    "scene unfolding across a wide cinematic vista, foreground trail "
    "winding into the middle distance, ridges receding toward the horizon, "
    "detailed pen-and-ink drawing in cross-hatching style, monochrome "
    "black ink on clean white background, fine line work with dense "
    "hatching and stippling for shadow and depth, etching-like texture, "
    "wide banner composition, pure pictorial illustration with empty "
    "margins and a smooth uninterrupted white sky, "
    "soft natural daylight casting long directional shadows, tranquil and timeless atmosphere"
)


def build_image_content(route: Route) -> str:
    """Build the per-route content portion of the prompt (no style, English only).

    Lead with proper-noun anchor (landmark name or destination from path_name),
    then "sweeping hiking landscape" + terrain phrase. French region names and
    description text are dropped — anchor is a proper noun, the rest is English
    so FLUX has clean prompt tokens to work with.
    """
    terrain_phrase = _build_terrain_phrase(route.terrain)
    landmark_phrase = _build_landmark_phrase(route.landmarks)
    anchor = landmark_phrase or _extract_destination(route.path_name)

    parts: list[str] = []
    if anchor:
        parts.append(anchor)
    parts.append("sweeping hiking landscape")
    parts.append(terrain_phrase)

    return ", ".join(parts)


_DESTINATION_PATTERN = re.compile(
    r"^(?:De|Du|Des)\b.*?\s+(?:à|au|aux)\s+([A-ZÀÂÉÈÊÎÔÛÇ][^,]+?)\s*$"
)


def _extract_destination(path_name: str) -> str | None:
    """Pull the destination proper noun from a path like ``De X à Y``.

    Strict shape: must start with ``De/Du/Des`` and the destination must begin
    with an uppercase letter. Rejects idioms (``Au fil de la Seine``, ``à pied``)
    that would otherwise smuggle French common nouns into the prompt.
    """
    if not path_name:
        return None
    match = _DESTINATION_PATTERN.match(path_name.strip())
    if not match:
        return None
    return match.group(1).strip() or None


def build_image_prompt(route: Route) -> str:
    """Full FLUX prompt = stored-or-built content + shared style suffix.

    Hand-edits in ``routes.yaml`` win: if stored content exists, use it as-is.
    Otherwise build fresh from route metadata.
    """
    stored = _read_stored_prompt(route.path_ref)
    content = stored if stored is not None else build_image_content(route)
    return f"{content}, {IMAGE_STYLE_SUFFIX}"


def _build_terrain_phrase(terrain_tags: list[str]) -> str:
    phrases = [_TERRAIN_PHRASES[tag] for tag in terrain_tags if tag in _TERRAIN_PHRASES]
    if not phrases:
        return "open countryside under a soft sky"
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " and " + phrases[-1]


def _build_landmark_phrase(landmarks: list[Landmark]) -> str:
    """Describe up to 3 landmarks for the scene composition.

    Named landmarks are anchored by name (e.g. "Mont-Saint-Michel abbey") so
    FLUX can draw the actual monument; unnamed ones fall back to generic prose.
    """
    if not landmarks:
        return ""
    pieces: list[str] = []
    for landmark in landmarks[:3]:
        descriptor = _LANDMARK_PROSE.get(landmark.kind, landmark.kind.replace("_", " "))
        if landmark.name:
            pieces.append(f"{landmark.name} ({descriptor})")
        elif landmark.kind in _LANDMARK_PROSE:
            pieces.append(descriptor)
    return ", ".join(pieces)


def generate_image(
    route: Route,
    output_directory: Path,
    *,
    force: bool = False,
) -> str | None:
    """Generate (or reuse) the cover image for a route.

    Image generation is opt-in: routes without ``image_prompt`` in
    ``routes.yaml`` are skipped. Bulk-seed via ``--populate-prompts``, then
    keep the entries you want and delete the rest.

    Returns the relative path under the data directory (e.g.
    ``images/abc123.webp``) on success, or ``None`` when generation was
    skipped (no stored prompt, missing image extra, or pipeline error).

    Cache contract: if the output file exists, regeneration is skipped.
    ``force=True`` overrides the cache. Stored content is never overwritten.
    """
    relative_path = f"{IMAGES_SUBDIRECTORY}/{route.identifier}.webp"
    output_path = output_directory / relative_path

    stored_content = _read_stored_prompt(route.path_ref)
    if stored_content is None:
        logger.info("  Skipping %s — no image_prompt in routes.yaml", route.path_ref)
        return None
    prompt = f"{stored_content}, {IMAGE_STYLE_SUFFIX}"

    if not force and output_path.exists():
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
    seed = secrets.randbits(32)

    logger.info("  Generating image for %s (seed=%d)", route.path_ref, seed)
    try:
        image = _run_pipeline(pipeline, prompt, seed)
    except Exception:
        logger.exception("  Image generation failed for %s; continuing", route.path_ref)
        return None

    image.save(output_path, format="WEBP", quality=WEBP_QUALITY, method=6)
    logger.info("  Wrote %s", output_path)

    return relative_path


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
