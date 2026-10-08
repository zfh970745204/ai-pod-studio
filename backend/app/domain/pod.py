from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PodModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlankAnalysis(PodModel):
    product_type: str = Field(min_length=1, max_length=160)
    visible_material_guess: str = Field(min_length=1, max_length=500)
    product_shape: str = Field(min_length=1, max_length=500)
    likely_print_method: str = Field(min_length=1, max_length=500)
    recommended_use_cases: list[str] = Field(min_length=1, max_length=8)
    visual_features: list[str] = Field(min_length=1, max_length=8)
    suggested_attributes: dict[str, Any] = Field(default_factory=dict)
    confidence_notes: list[str] = Field(default_factory=list, max_length=8)


class ProductIdeaDraft(PodModel):
    idea_name: str = Field(min_length=1, max_length=200)
    target_audience: str = Field(min_length=1, max_length=1000)
    use_case: str = Field(min_length=1, max_length=1000)
    emotional_angle: str = Field(min_length=1, max_length=1000)
    design_theme: str = Field(min_length=1, max_length=1000)
    visual_direction: str = Field(min_length=1, max_length=1000)
    recommended_style: str = Field(min_length=1, max_length=1000)
    composition_direction: str = Field(min_length=1, max_length=1000)
    color_direction: str = Field(min_length=1, max_length=1000)
    core_elements: list[str] = Field(min_length=1, max_length=12)
    avoid_elements: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = Field(min_length=1, max_length=2000)
    infringement_risk: dict[str, Any] = Field(default_factory=dict)

    @field_validator("core_elements", "avoid_elements")
    @classmethod
    def clean_elements(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class ProductIdeaBatch(PodModel):
    items: list[ProductIdeaDraft] = Field(min_length=1, max_length=50)


class DesignConceptDraft(PodModel):
    design_name: str = Field(min_length=1, max_length=200)
    visual_style: str = Field(min_length=1, max_length=1000)
    composition: str = Field(min_length=1, max_length=1000)
    layout: str = Field(min_length=1, max_length=1000)
    main_subject: str = Field(min_length=1, max_length=1000)
    secondary_elements: list[str] = Field(default_factory=list, max_length=12)
    color_palette: str = Field(min_length=1, max_length=1000)
    typography_direction: str = Field(min_length=1, max_length=1000)
    pattern_structure: str = Field(min_length=1, max_length=1000)
    print_method: str = Field(min_length=1, max_length=1000)
    recommended_print_area: str = Field(min_length=1, max_length=1000)
    texture_direction: str = Field(min_length=1, max_length=1000)
    background_direction: str = Field(min_length=1, max_length=1000)
    negative_elements: list[str] = Field(default_factory=list, max_length=12)
    design_prompt: str = Field(min_length=30, max_length=5000)


class DesignConceptBatch(PodModel):
    items: list[DesignConceptDraft] = Field(min_length=1, max_length=12)


class ProductCopyDraft(PodModel):
    product_title: str = Field(min_length=5, max_length=200)
    product_description: str = Field(min_length=30, max_length=5000)
    selling_points: list[str] = Field(min_length=3, max_length=8)
    search_keywords: list[str] = Field(min_length=5, max_length=30)
    content_warnings: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("selling_points", "search_keywords", "content_warnings")
    @classmethod
    def clean_copy_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class ProductImageSlotDraft(PodModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,62}$")
    title: str = Field(min_length=1, max_length=160)
    scope: str = Field(pattern="^(product_specific|generic)$")
    requires_print: bool
    scene_prompt: str = Field(min_length=3, max_length=1000)
    composition_prompt: str = Field(min_length=3, max_length=1000)
    style_prompt: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def validate_scope(self) -> ProductImageSlotDraft:
        if self.scope == "product_specific" and not self.requires_print:
            raise ValueError("商品专属图片槽位必须使用 Print Master")
        if self.scope == "generic" and self.requires_print:
            raise ValueError("通用图片槽位不能要求 Print Master")
        return self


class ProductImageStrategy(PodModel):
    rationale: str = Field(min_length=1, max_length=2000)
    slots: list[ProductImageSlotDraft] = Field(min_length=4, max_length=10)

    @model_validator(mode="after")
    def validate_slots(self) -> ProductImageStrategy:
        codes = [item.code for item in self.slots]
        if len(set(codes)) != len(codes):
            raise ValueError("图片槽位 code 不能重复")
        main = [item for item in self.slots if item.code == "product_main"]
        if len(main) != 1 or main[0].scope != "product_specific" or not main[0].requires_print:
            raise ValueError("图片策略必须包含使用 Print Master 的 product_main 槽位")
        return self


def parse_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("AI 返回的结构化内容不是有效 JSON") from exc
    if not isinstance(parsed, dict):
        raise TypeError("AI 返回的结构化内容必须是对象")
    return parsed


def blank_analysis_instruction(*, category: str, material: str, confirmed: dict[str, Any]) -> str:
    return f"""Analyze the supplied POD blank product references. The user-confirmed facts below are authoritative and must never be overwritten.

Confirmed category: {category}
Confirmed material: {material}
Confirmed attributes: {json.dumps(confirmed, ensure_ascii=False)}

Return JSON only with keys: product_type, visible_material_guess, product_shape, likely_print_method, recommended_use_cases, visual_features, suggested_attributes, confidence_notes.
Every visual inference must be clearly phrased as a suggestion. Do not invent supplier specifications, dimensions, compliance claims, brands, characters, or licenses."""


def product_ideas_instruction(
    *,
    category: str,
    material: str,
    confirmed: dict[str, Any],
    suggested: dict[str, Any],
    count: int,
) -> str:
    return f"""Generate exactly {count} distinct POD Product Idea candidates for a US-market creative exploration workflow. They are candidates, not claims about current sales or trend data.

Product category: {category}
Material: {material}
Confirmed attributes: {json.dumps(confirmed, ensure_ascii=False)}
AI-suggested attributes: {json.dumps(suggested, ensure_ascii=False)}

Return JSON only as {{"items": [...]}}. Every item must have: idea_name, target_audience, use_case, emotional_angle, design_theme, visual_direction, recommended_style, composition_direction, color_direction, core_elements, avoid_elements, rationale, infringement_risk.
infringement_risk must identify risk_level (low, medium, high) and warnings as a list. Avoid brands, logos, celebrity likenesses, protected characters, copyrighted phrases, and copied artwork. Ensure candidates differ in audience, scene, emotional angle, design structure, and element combination; do not only change colors."""


def design_concepts_instruction(*, idea: dict[str, Any], count: int) -> str:
    return f"""Generate exactly {count} materially different print Design Concepts for this adopted POD product idea:
{json.dumps(idea, ensure_ascii=False)}

Return JSON only as {{"items": [...]}}. Every item must have: design_name, visual_style, composition, layout, main_subject, secondary_elements, color_palette, typography_direction, pattern_structure, print_method, recommended_print_area, texture_direction, background_direction, negative_elements, design_prompt.
The concepts must change design structure (for example badge, central illustration, repeat pattern, typography-led, or minimal line work), not merely colors. Avoid protected brands, existing characters, celebrity likenesses, copyrighted quotes, watermarks, and unreadable text. The design_prompt must direct an image model to create one flat printable design, not a product mockup."""


def product_copy_instruction(
    *,
    category: str,
    material: str,
    confirmed: dict[str, Any],
    idea: dict[str, Any],
    design: dict[str, Any],
) -> str:
    return f"""Create original English (US) ecommerce copy for one POD product. This is drafting material for human review, not a claim of market performance, safety, fit, origin, dimensions, or legal clearance.

Confirmed product category: {category}
Confirmed material: {material}
Confirmed attributes: {json.dumps(confirmed, ensure_ascii=False)}
Adopted product idea: {json.dumps(idea, ensure_ascii=False)}
Adopted design concept: {json.dumps(design, ensure_ascii=False)}

Return JSON only with product_title, product_description, selling_points, search_keywords, content_warnings.
Write a concise natural US-English product title, a customer-facing description, 3-8 concrete selling points, and 5-30 relevant search keywords. Mention only confirmed product facts or visual/design direction. Never invent dimensions, care instructions, material performance, certifications, delivery promises, discounts, pricing, sales rank, reviews, trademarks, celebrity names, protected characters, copyrighted phrases, or guarantees. content_warnings must list any facts requiring human confirmation; return an empty list when none are needed."""


def print_prompt(design: DesignConceptDraft, variation_index: int) -> str:
    return f"""Create ONE original, high-quality flat POD print design for production exploration.

Design direction: {design.design_prompt}
Visual style: {design.visual_style}
Composition: {design.composition}
Layout: {design.layout}
Main subject: {design.main_subject}
Color palette: {design.color_palette}
Pattern structure: {design.pattern_structure}
Variation: {variation_index + 1} of 4; vary the composition treatment while retaining the chosen design concept.

Return only the complete print artwork. No product mockup, no garment, no mug, no room, no model, no packaging, no border, no watermark, no brand logo, no copyrighted character, and no unreadable or invented text."""


def product_visual_prompt(
    *, blank_name: str, visual_style: dict[str, Any], scene: str, composition: str
) -> str:
    return f"""Create one premium ecommerce product visual.

Input image 1 and any other blank-reference images show the real product identity for {blank_name}. The final input image is the locked Print Master and is the only source of the product design. Apply that exact design faithfully to the visible product surface. Preserve the real product's silhouette, material cues, component count, proportions, and known construction. Do not redesign, mirror, recolor, crop away, rewrite, or replace the Print Master artwork.

Product visual style: {json.dumps(visual_style, ensure_ascii=False)}
Scene: {scene}
Composition: {composition}

Render one standalone product image. Do not add logos, watermarks, invented labels, unsupported product features, or extra products."""


def product_image_strategy_instruction(
    *,
    category: str,
    material: str,
    confirmed: dict[str, Any],
    suggested: dict[str, Any],
    idea: dict[str, Any],
) -> str:
    return f"""Plan one practical ecommerce image set for an original POD product. This is a creative production plan, not a claim about market requirements.

Blank category: {category}
Material: {material}
Confirmed product facts: {json.dumps(confirmed, ensure_ascii=False)}
AI-suggested product facts: {json.dumps(suggested, ensure_ascii=False)}
Adopted product idea: {json.dumps(idea, ensure_ascii=False)}

Return JSON only as {{"rationale": "...", "slots": [...]}}. Create 4 to 10 image slots that are genuinely useful for this product category. Each slot requires code, title, scope, requires_print, scene_prompt, composition_prompt, style_prompt.

Always include exactly one `product_main` slot with scope `product_specific` and requires_print true. For every product_specific slot, the visible product must use the locked Print Master and real blank references. Vary the set by category and purpose, for example product detail, fabric or print detail, use context, scale, gifting, or alternate angle. Do not use a fixed universal list. A generic slot may only be non-product supplementary imagery and must set requires_print false. Do not request logos, watermarks, brands, protected characters, celebrity likenesses, or unsupported product features."""


def product_slot_visual_prompt(
    *,
    blank_name: str,
    visual_style: dict[str, Any],
    title: str,
    scene: str,
    composition: str,
    style: str,
) -> str:
    base = product_visual_prompt(
        blank_name=blank_name,
        visual_style=visual_style,
        scene=scene,
        composition=composition,
    )
    return f"""{base}

Image slot: {title}
Visual treatment: {style}

This output must fulfill this slot only while preserving the same product and the exact locked Print Master."""


def generic_product_visual_prompt(*, title: str, scene: str, composition: str, style: str) -> str:
    return f"""Create one supplementary ecommerce visual for the image slot {title}.

Scene: {scene}
Composition: {composition}
Visual treatment: {style}

This is a generic supporting visual, not a depiction of a specific sellable product. Do not show or invent any product design, logo, brand, watermark, protected character, or unsupported claim."""
