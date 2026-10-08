from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, or_, select

from app.api.dependencies import Principal, require_permission
from app.api.errors import ApiError
from app.api.jobs import enqueue_job
from app.domain.ids import uuid7
from app.domain.pod import (
    DesignConceptDraft,
    generic_product_visual_prompt,
    product_slot_visual_prompt,
    product_visual_prompt,
)
from app.repositories.models import (
    ImageJob,
    OutboxEvent,
    PodBlank,
    PodBlankReference,
    PodDesignConcept,
    PodDevelopmentProject,
    PodImageSet,
    PodImageSlot,
    PodPrintCandidate,
    PodPrintMaster,
    PodProduct,
    PodProductCopy,
    PodProductIdea,
    PodReview,
)
from app.services.assets import AssetService
from app.services.jobs import JobService

router = APIRouter(prefix="/api/v1/pod", tags=["pod-development"])
service = JobService()
PodReader = Annotated[Principal, Depends(require_permission("tasks.read_own"))]
PodWriter = Annotated[Principal, Depends(require_permission("tasks.create"))]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


class PodPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlankCreate(PodPayload):
    category: str = Field(min_length=1, max_length=100)
    material: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=160)
    confirmed_attributes: dict[str, Any] = Field(default_factory=dict)
    product_visual_style: dict[str, Any] = Field(default_factory=dict)

    @field_validator("category", "material", "name")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value


class BlankPatch(PodPayload):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    material: str | None = Field(default=None, min_length=1, max_length=100)
    confirmed_attributes: dict[str, Any] | None = None
    product_visual_style: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class ReferenceCreate(PodPayload):
    asset_id: uuid.UUID
    reference_role: str = Field(default="primary", pattern="^(primary|detail|lifestyle)$")
    sort_order: int = Field(default=0, ge=0, le=1000)
    is_supplier_reference: bool = True


class ProjectCreate(PodPayload):
    blank_id: uuid.UUID
    name: str | None = Field(default=None, max_length=160)


class GenerateIdeas(PodPayload):
    count: int = Field(default=20)

    @field_validator("count")
    @classmethod
    def allowed_count(cls, value: int) -> int:
        if value not in {10, 20, 50}:
            raise ValueError("创意数量仅支持 10、20 或 50")
        return value


class GenerateDesigns(PodPayload):
    count: int = Field(default=4, ge=4, le=8)


class IdeaStatusPatch(PodPayload):
    status: str = Field(pattern="^(adopted|archived)$")


class DesignStatusPatch(PodPayload):
    status: str = Field(pattern="^(adopted|archived)$")


class BulkIdeaStatus(PodPayload):
    idea_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    status: str = Field(pattern="^(adopted|archived)$")


class ProductVisualGenerate(PodPayload):
    scene: str = Field(
        default="Clean light-neutral studio product photography", min_length=3, max_length=1000
    )
    composition: str = Field(
        default="Full product hero view with the product centered", min_length=3, max_length=1000
    )
    size: str = Field(default="1024x1024", pattern="^(auto|1024x1024|1024x1536|1536x1024)$")
    quality: str = Field(default="high", pattern="^(auto|low|medium|high)$")


class ImageSlotPatch(PodPayload):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    scene_prompt: str | None = Field(default=None, min_length=3, max_length=1000)
    composition_prompt: str | None = Field(default=None, min_length=3, max_length=1000)
    style_prompt: str | None = Field(default=None, min_length=3, max_length=1000)
    sort_order: int | None = Field(default=None, ge=0, le=1000)


class ImageSlotGenerate(PodPayload):
    scene_prompt: str | None = Field(default=None, min_length=3, max_length=1000)
    composition_prompt: str | None = Field(default=None, min_length=3, max_length=1000)
    style_prompt: str | None = Field(default=None, min_length=3, max_length=1000)
    size: str = Field(default="1024x1024", pattern="^(auto|1024x1024|1024x1536|1536x1024)$")
    quality: str = Field(default="high", pattern="^(auto|low|medium|high)$")


class BulkImageSlotGenerate(ImageSlotGenerate):
    slot_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


class ProductCopyPatch(PodPayload):
    product_title: str | None = Field(default=None, min_length=5, max_length=200)
    product_description: str | None = Field(default=None, min_length=30, max_length=5000)
    selling_points: list[str] | None = Field(default=None, min_length=3, max_length=8)
    search_keywords: list[str] | None = Field(default=None, min_length=5, max_length=30)
    content_warnings: list[str] | None = Field(default=None, max_length=12)

    @field_validator("selling_points", "search_keywords", "content_warnings")
    @classmethod
    def clean_items(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return [item.strip() for item in value if item.strip()]


class ReviewCreate(PodPayload):
    target_type: str = Field(pattern="^(blank|idea|print_candidate|image_slot|product)$")
    target_id: uuid.UUID
    gate: str = Field(pattern="^(G0|G1|G2|G3)$")
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=4000)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid7().hex


def blank_payload(
    blank: PodBlank, references: list[PodBlankReference] | None = None
) -> dict[str, Any]:
    return {
        "id": str(blank.id),
        "name": blank.name,
        "category": blank.category,
        "material": blank.material,
        "confirmed_attributes": blank.confirmed_attributes,
        "suggested_attributes": blank.suggested_attributes,
        "product_visual_style": blank.product_visual_style,
        "status": blank.status,
        "created_at": blank.created_at,
        "updated_at": blank.updated_at,
        "references": [reference_payload(item) for item in references or []],
    }


def reference_payload(reference: PodBlankReference) -> dict[str, Any]:
    return {
        "id": str(reference.id),
        "asset_id": str(reference.asset_id),
        "reference_role": reference.reference_role,
        "sort_order": reference.sort_order,
        "is_supplier_reference": reference.is_supplier_reference,
        "created_at": reference.created_at,
    }


def project_payload(project: PodDevelopmentProject) -> dict[str, Any]:
    return {
        "id": str(project.id),
        "blank_id": str(project.blank_id),
        "name": project.name,
        "status": project.status,
        "current_stage": project.current_stage,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def idea_payload(idea: PodProductIdea) -> dict[str, Any]:
    return {
        "id": str(idea.id),
        "project_id": str(idea.project_id),
        "generation_job_id": str(idea.generation_job_id) if idea.generation_job_id else None,
        "generation_batch_id": str(idea.generation_batch_id),
        "idea_name": idea.idea_name,
        "target_audience": idea.target_audience,
        "use_case": idea.use_case,
        "emotional_angle": idea.emotional_angle,
        "design_theme": idea.design_theme,
        "visual_direction": idea.visual_direction,
        "recommended_style": idea.recommended_style,
        "composition_direction": idea.composition_direction,
        "color_direction": idea.color_direction,
        "core_elements": idea.core_elements,
        "avoid_elements": idea.avoid_elements,
        "rationale": idea.rationale,
        "infringement_risk": idea.infringement_risk,
        "status": idea.status,
        "created_at": idea.created_at,
        "updated_at": idea.updated_at,
    }


def concept_payload(concept: PodDesignConcept) -> dict[str, Any]:
    return {
        "id": str(concept.id),
        "product_idea_id": str(concept.product_idea_id),
        "generation_job_id": str(concept.generation_job_id) if concept.generation_job_id else None,
        "design_name": concept.design_name,
        "visual_style": concept.visual_style,
        "composition": concept.composition,
        "layout": concept.layout,
        "main_subject": concept.main_subject,
        "secondary_elements": concept.secondary_elements,
        "color_palette": concept.color_palette,
        "typography_direction": concept.typography_direction,
        "pattern_structure": concept.pattern_structure,
        "print_method": concept.print_method,
        "recommended_print_area": concept.recommended_print_area,
        "texture_direction": concept.texture_direction,
        "background_direction": concept.background_direction,
        "negative_elements": concept.negative_elements,
        "design_prompt": concept.design_prompt,
        "status": concept.status,
        "created_at": concept.created_at,
        "updated_at": concept.updated_at,
    }


def candidate_payload(candidate: PodPrintCandidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "design_concept_id": str(candidate.design_concept_id),
        "asset_id": str(candidate.asset_id),
        "generation_job_id": str(candidate.generation_job_id),
        "status": candidate.status,
        "created_at": candidate.created_at,
    }


def master_payload(master: PodPrintMaster) -> dict[str, Any]:
    return {
        "id": str(master.id),
        "project_id": str(master.project_id),
        "print_candidate_id": str(master.print_candidate_id),
        "asset_id": str(master.asset_id),
        "version": master.version,
        "status": master.status,
        "locked_by": str(master.locked_by),
        "locked_at": master.locked_at,
    }


def product_payload(product: PodProduct) -> dict[str, Any]:
    return {
        "id": str(product.id),
        "project_id": str(product.project_id),
        "product_idea_id": str(product.product_idea_id),
        "design_concept_id": str(product.design_concept_id),
        "print_master_id": str(product.print_master_id),
        "primary_visual_asset_id": str(product.primary_visual_asset_id)
        if product.primary_visual_asset_id
        else None,
        "primary_visual_job_id": str(product.primary_visual_job_id)
        if product.primary_visual_job_id
        else None,
        "status": product.status,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


def product_copy_payload(copy: PodProductCopy) -> dict[str, Any]:
    return {
        "id": str(copy.id),
        "product_id": str(copy.product_id),
        "generation_job_id": str(copy.generation_job_id) if copy.generation_job_id else None,
        "version": copy.version,
        "locale": copy.locale,
        "product_title": copy.product_title,
        "product_description": copy.product_description,
        "selling_points": copy.selling_points,
        "search_keywords": copy.search_keywords,
        "content_warnings": copy.content_warnings,
        "prompt_snapshot": copy.prompt_snapshot,
        "status": copy.status,
        "created_at": copy.created_at,
        "updated_at": copy.updated_at,
    }


def image_slot_payload(slot: PodImageSlot) -> dict[str, Any]:
    return {
        "id": str(slot.id),
        "image_set_id": str(slot.image_set_id),
        "code": slot.code,
        "title": slot.title,
        "scope": slot.scope,
        "requires_print": slot.requires_print,
        "scene_prompt": slot.scene_prompt,
        "composition_prompt": slot.composition_prompt,
        "style_prompt": slot.style_prompt,
        "sort_order": slot.sort_order,
        "asset_id": str(slot.asset_id) if slot.asset_id else None,
        "generation_job_id": str(slot.generation_job_id) if slot.generation_job_id else None,
        "prompt_snapshot": slot.prompt_snapshot,
        "status": slot.status,
        "created_at": slot.created_at,
        "updated_at": slot.updated_at,
    }


def image_set_payload(
    image_set: PodImageSet, slots: list[PodImageSlot] | None = None
) -> dict[str, Any]:
    return {
        "id": str(image_set.id),
        "product_id": str(image_set.product_id),
        "generation_job_id": str(image_set.generation_job_id)
        if image_set.generation_job_id
        else None,
        "version": image_set.version,
        "strategy_snapshot": image_set.strategy_snapshot,
        "status": image_set.status,
        "created_at": image_set.created_at,
        "updated_at": image_set.updated_at,
        "slots": [image_slot_payload(slot) for slot in slots or []],
    }


async def _blank_or_404(session, blank_id: uuid.UUID, owner_id: uuid.UUID) -> PodBlank:
    blank = await session.get(PodBlank, blank_id)
    if blank is None or blank.owner_id != owner_id:
        raise ApiError(404, "POD_BLANK_NOT_FOUND", "胚件不存在")
    return blank


async def _project_or_404(
    session, project_id: uuid.UUID, owner_id: uuid.UUID
) -> PodDevelopmentProject:
    project = await session.get(PodDevelopmentProject, project_id)
    if project is None or project.owner_id != owner_id:
        raise ApiError(404, "POD_PROJECT_NOT_FOUND", "开发项目不存在")
    return project


async def _idea_or_404(session, idea_id: uuid.UUID, owner_id: uuid.UUID) -> PodProductIdea:
    result = await session.execute(
        select(PodProductIdea)
        .join(PodDevelopmentProject)
        .where(PodProductIdea.id == idea_id, PodDevelopmentProject.owner_id == owner_id)
    )
    idea = result.scalar_one_or_none()
    if idea is None:
        raise ApiError(404, "POD_IDEA_NOT_FOUND", "产品创意不存在")
    return idea


async def _concept_or_404(session, concept_id: uuid.UUID, owner_id: uuid.UUID) -> PodDesignConcept:
    result = await session.execute(
        select(PodDesignConcept)
        .join(PodProductIdea, PodProductIdea.id == PodDesignConcept.product_idea_id)
        .join(PodDevelopmentProject, PodDevelopmentProject.id == PodProductIdea.project_id)
        .where(PodDesignConcept.id == concept_id, PodDevelopmentProject.owner_id == owner_id)
    )
    concept = result.scalar_one_or_none()
    if concept is None:
        raise ApiError(404, "POD_DESIGN_NOT_FOUND", "设计方案不存在")
    return concept


async def _product_or_404(session, product_id: uuid.UUID, owner_id: uuid.UUID) -> PodProduct:
    product = await session.get(PodProduct, product_id)
    if product is None or product.owner_id != owner_id:
        raise ApiError(404, "POD_PRODUCT_NOT_FOUND", "商品不存在")
    return product


async def _copy_or_404(
    session, copy_id: uuid.UUID, owner_id: uuid.UUID
) -> tuple[PodProductCopy, PodProduct]:
    row = await session.execute(
        select(PodProductCopy, PodProduct)
        .join(PodProduct, PodProduct.id == PodProductCopy.product_id)
        .where(PodProductCopy.id == copy_id, PodProduct.owner_id == owner_id)
    )
    result = row.one_or_none()
    if result is None:
        raise ApiError(404, "POD_PRODUCT_COPY_NOT_FOUND", "商品文案不存在")
    return result


async def _require_product_main_reviewed(session, product: PodProduct) -> None:
    if product.primary_visual_asset_id is None:
        raise ApiError(409, "POD_PRODUCT_MAIN_VISUAL_REQUIRED", "请先生成商品主图再继续")
    active_set = await session.scalar(
        select(PodImageSet).where(
            PodImageSet.product_id == product.id,
            PodImageSet.status == "active",
        )
    )
    if active_set is None:
        return
    main_slot = await session.scalar(
        select(PodImageSlot).where(
            PodImageSlot.image_set_id == active_set.id,
            PodImageSlot.code == "product_main",
        )
    )
    if main_slot is None or main_slot.status != "approved":
        raise ApiError(409, "POD_PRODUCT_MAIN_REVIEW_REQUIRED", "请先完成当前商品主图的 G2 审核")


async def _image_slot_or_404(
    session, slot_id: uuid.UUID, owner_id: uuid.UUID, *, product_id: uuid.UUID | None = None
) -> tuple[PodImageSlot, PodImageSet, PodProduct]:
    row = await session.execute(
        select(PodImageSlot, PodImageSet, PodProduct)
        .join(PodImageSet, PodImageSet.id == PodImageSlot.image_set_id)
        .join(PodProduct, PodProduct.id == PodImageSet.product_id)
        .where(PodImageSlot.id == slot_id, PodProduct.owner_id == owner_id)
    )
    result = row.one_or_none()
    if result is None or (product_id is not None and result[2].id != product_id):
        raise ApiError(404, "POD_IMAGE_SLOT_NOT_FOUND", "图片槽位不存在")
    slot, image_set, product = result
    if image_set.status != "active":
        raise ApiError(409, "POD_IMAGE_SET_NOT_ACTIVE", "图片套组不是当前版本")
    return slot, image_set, product


async def _slot_generation_spec(
    session,
    *,
    product: PodProduct,
    image_set: PodImageSet,
    slot: PodImageSlot,
    payload: ImageSlotGenerate,
    owner_id: uuid.UUID,
) -> tuple[str, uuid.UUID | None, dict[str, Any]]:
    if slot.status == "approved":
        raise ApiError(409, "POD_IMAGE_SLOT_APPROVED", "已审核通过的图片槽位不能直接重生成")
    if slot.generation_job_id is not None:
        previous = await session.get(ImageJob, slot.generation_job_id)
        if previous is not None and previous.status in {"queued", "running", "retry_wait"}:
            raise ApiError(409, "POD_IMAGE_SLOT_RUNNING", "该图片槽位已有进行中的生成任务")
    scene = payload.scene_prompt or slot.scene_prompt
    composition = payload.composition_prompt or slot.composition_prompt
    style = payload.style_prompt or slot.style_prompt
    if slot.scope == "product_specific":
        if not slot.requires_print:
            raise ApiError(422, "POD_IMAGE_SLOT_INVALID", "商品专属图片必须使用 Print Master")
        project = await _project_or_404(session, product.project_id, owner_id)
        blank = await _blank_or_404(session, project.blank_id, owner_id)
        master = await session.get(PodPrintMaster, product.print_master_id)
        if master is None or master.status != "active":
            raise ApiError(409, "POD_PRINT_MASTER_NOT_ACTIVE", "Print Master 尚未锁定或已失效")
        references = list(
            (
                await session.scalars(
                    select(PodBlankReference)
                    .where(PodBlankReference.blank_id == blank.id)
                    .order_by(PodBlankReference.sort_order, PodBlankReference.id)
                )
            ).all()
        )
        if not references:
            raise ApiError(422, "POD_BLANK_REFERENCE_REQUIRED", "请先添加真实胚件参考图")
        if master.asset_id in {reference.asset_id for reference in references}:
            raise ApiError(
                409,
                "POD_PRINT_MASTER_MUST_BE_SEPARATE",
                "Print Master 不能使用胚件真实参考图素材",
            )
        reference_asset_ids = [reference.asset_id for reference in references] + [master.asset_id]
        prompt = product_slot_visual_prompt(
            blank_name=blank.name,
            visual_style=blank.product_visual_style,
            title=slot.title,
            scene=scene,
            composition=composition,
            style=style,
        )
        return (
            "pod.visual.generate",
            references[0].asset_id,
            {
                "blank_id": str(blank.id),
                "project_id": str(project.id),
                "product_id": str(product.id),
                "print_master_id": str(master.id),
                "print_master_asset_id": str(master.asset_id),
                "blank_reference_asset_ids": [str(reference.asset_id) for reference in references],
                "reference_asset_ids": [str(asset_id) for asset_id in reference_asset_ids],
                "image_set_id": str(image_set.id),
                "image_slot_id": str(slot.id),
                "image_slot_code": slot.code,
                "scope": slot.scope,
                "requires_print": True,
                "prompt": prompt,
                "size": payload.size,
                "quality": payload.quality,
                "image_count": 1,
            },
        )
    if slot.requires_print:
        raise ApiError(422, "POD_IMAGE_SLOT_INVALID", "通用图片槽位不能要求 Print Master")
    prompt = generic_product_visual_prompt(
        title=slot.title,
        scene=scene,
        composition=composition,
        style=style,
    )
    return (
        "pod.visual.generic",
        None,
        {
            "product_id": str(product.id),
            "image_set_id": str(image_set.id),
            "image_slot_id": str(slot.id),
            "image_slot_code": slot.code,
            "scope": slot.scope,
            "requires_print": False,
            "prompt": prompt,
            "size": payload.size,
            "quality": payload.quality,
            "image_count": 1,
        },
    )


async def _submit_job(
    *,
    request: Request,
    principal: Principal,
    operation_code: str,
    source_asset_id: uuid.UUID | None,
    parameters: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    runtime = request.app.state.runtime_services
    request_id = _request_id(request)
    async with runtime.database.session_factory() as session:
        canonical = service.canonical_parameters(parameters)
        existing = await session.scalar(
            select(ImageJob).where(
                ImageJob.user_id == principal.user_id,
                ImageJob.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.operation_code != operation_code or existing.parameters != canonical:
                raise ApiError(
                    409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key 已用于不同的 POD 任务"
                )
            return {
                "job_id": str(existing.id),
                "created": False,
                "dispatched": False,
                "status": existing.status,
            }
        quote = await service.create_quote(
            session,
            user_id=principal.user_id,
            operation_code=operation_code,
            source_asset_id=source_asset_id,
            parameters=canonical,
            ttl_seconds=request.app.state.settings.job_quote_ttl_seconds,
            request_id=request_id,
        )
        job, created = await service.create_job(
            session,
            user_id=principal.user_id,
            quote_id=quote.id,
            parameters=canonical,
            idempotency_key=idempotency_key,
            request_fingerprint=service.request_fingerprint(principal.user_id, quote.id, canonical),
            request_id=request_id,
            require_sub2api_config=not request.app.state.settings.legacy_sync_api_enabled,
        )
        await session.commit()
        await session.refresh(job)
    dispatched = await enqueue_job(request, job) if created else False
    return {
        "job_id": str(job.id),
        "created": created,
        "dispatched": dispatched,
        "status": job.status,
    }


def _record_event(
    session,
    *,
    topic: str,
    aggregate_id: uuid.UUID,
    owner_id: uuid.UUID,
    request_id: str,
    details: dict[str, Any],
) -> None:
    session.add(
        OutboxEvent(
            id=uuid7(),
            topic=topic,
            aggregate_type="pod",
            aggregate_id=aggregate_id,
            payload={"user_id": str(owner_id), "request_id": request_id, **details},
            status="pending",
            attempts=0,
            available_at=datetime.now(UTC),
            version=1,
        )
    )


@router.get("/blanks")
async def list_blanks(
    request: Request,
    principal: PodReader,
    cursor: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        statement = select(PodBlank).where(PodBlank.owner_id == principal.user_id)
        if status_filter:
            if status_filter not in {"active", "archived"}:
                raise ApiError(422, "INVALID_STATUS", "胚件状态无效")
            statement = statement.where(PodBlank.status == status_filter)
        if cursor:
            anchor = await session.get(PodBlank, cursor)
            if anchor is None or anchor.owner_id != principal.user_id:
                raise ApiError(422, "INVALID_CURSOR", "分页游标无效")
            statement = statement.where(
                or_(
                    PodBlank.created_at < anchor.created_at,
                    and_(PodBlank.created_at == anchor.created_at, PodBlank.id < anchor.id),
                )
            )
        rows = list(
            (
                await session.scalars(
                    statement.order_by(PodBlank.created_at.desc(), PodBlank.id.desc()).limit(
                        limit + 1
                    )
                )
            ).all()
        )
        items = rows[:limit]
        references = (
            list(
                (
                    await session.scalars(
                        select(PodBlankReference).where(
                            PodBlankReference.blank_id.in_([item.id for item in items])
                        )
                    )
                ).all()
            )
            if items
            else []
        )
    grouped: dict[uuid.UUID, list[PodBlankReference]] = {}
    for reference in references:
        grouped.setdefault(reference.blank_id, []).append(reference)
    return {
        "items": [blank_payload(item, grouped.get(item.id, [])) for item in items],
        "next_cursor": str(items[-1].id) if len(rows) > limit and items else None,
    }


@router.post("/blanks", status_code=status.HTTP_201_CREATED)
async def create_blank(
    payload: BlankCreate, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        blank = PodBlank(
            id=uuid7(),
            owner_id=principal.user_id,
            name=payload.name or f"{payload.category} / {payload.material}",
            category=payload.category,
            material=payload.material,
            confirmed_attributes=payload.confirmed_attributes,
            suggested_attributes={},
            product_visual_style=payload.product_visual_style,
            status="active",
        )
        session.add(blank)
        _record_event(
            session,
            topic="pod.blank.created",
            aggregate_id=blank.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={"category": blank.category},
        )
        await session.commit()
        await session.refresh(blank)
    return {"blank": blank_payload(blank)}


@router.get("/blanks/{blank_id}")
async def get_blank(blank_id: uuid.UUID, request: Request, principal: PodReader) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        blank = await _blank_or_404(session, blank_id, principal.user_id)
        references = list(
            (
                await session.scalars(
                    select(PodBlankReference)
                    .where(PodBlankReference.blank_id == blank.id)
                    .order_by(PodBlankReference.sort_order, PodBlankReference.id)
                )
            ).all()
        )
    return {"blank": blank_payload(blank, references)}


@router.patch("/blanks/{blank_id}")
async def update_blank(
    blank_id: uuid.UUID, payload: BlankPatch, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        blank = await _blank_or_404(session, blank_id, principal.user_id)
        for field in payload.model_fields_set:
            setattr(blank, field, getattr(payload, field))
        _record_event(
            session,
            topic="pod.blank.updated",
            aggregate_id=blank.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={"fields": sorted(payload.model_fields_set)},
        )
        await session.commit()
        await session.refresh(blank)
    return {"blank": blank_payload(blank)}


@router.post("/blanks/{blank_id}/references", status_code=status.HTTP_201_CREATED)
async def add_blank_reference(
    blank_id: uuid.UUID, payload: ReferenceCreate, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        blank = await _blank_or_404(session, blank_id, principal.user_id)
        await AssetService().require_usable(session, payload.asset_id, owner_id=principal.user_id)
        exists = await session.scalar(
            select(PodBlankReference.id).where(
                PodBlankReference.blank_id == blank.id,
                PodBlankReference.asset_id == payload.asset_id,
            )
        )
        if exists:
            raise ApiError(409, "POD_REFERENCE_EXISTS", "该素材已关联到胚件")
        reference = PodBlankReference(id=uuid7(), blank_id=blank.id, **payload.model_dump())
        session.add(reference)
        await session.commit()
        await session.refresh(reference)
    return {"reference": reference_payload(reference)}


@router.post("/blanks/{blank_id}/analysis")
async def analyze_blank(
    blank_id: uuid.UUID, request: Request, principal: PodWriter, idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        blank = await _blank_or_404(session, blank_id, principal.user_id)
        source = await session.scalar(
            select(PodBlankReference.asset_id)
            .where(PodBlankReference.blank_id == blank.id)
            .order_by(PodBlankReference.sort_order, PodBlankReference.id)
            .limit(1)
        )
        if source is None:
            raise ApiError(422, "POD_BLANK_REFERENCE_REQUIRED", "请先上传并关联真实胚件参考图")
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code="pod.blank.analyze",
        source_asset_id=source,
        parameters={"blank_id": str(blank_id)},
        idempotency_key=idempotency_key,
    )
    return {"job": job}


@router.get("/projects")
async def list_projects(
    request: Request,
    principal: PodReader,
    cursor: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        statement = select(PodDevelopmentProject).where(
            PodDevelopmentProject.owner_id == principal.user_id
        )
        if cursor:
            anchor = await session.get(PodDevelopmentProject, cursor)
            if anchor is None or anchor.owner_id != principal.user_id:
                raise ApiError(422, "INVALID_CURSOR", "分页游标无效")
            statement = statement.where(
                or_(
                    PodDevelopmentProject.created_at < anchor.created_at,
                    and_(
                        PodDevelopmentProject.created_at == anchor.created_at,
                        PodDevelopmentProject.id < anchor.id,
                    ),
                )
            )
        rows = list(
            (
                await session.scalars(
                    statement.order_by(
                        PodDevelopmentProject.created_at.desc(), PodDevelopmentProject.id.desc()
                    ).limit(limit + 1)
                )
            ).all()
        )
        items = rows[:limit]
    return {
        "items": [project_payload(item) for item in items],
        "next_cursor": str(items[-1].id) if len(rows) > limit and items else None,
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        blank = await _blank_or_404(session, payload.blank_id, principal.user_id)
        project = PodDevelopmentProject(
            id=uuid7(),
            owner_id=principal.user_id,
            blank_id=blank.id,
            name=payload.name or f"{blank.name} 产品开发",
            status="draft",
            current_stage="blank",
        )
        session.add(project)
        _record_event(
            session,
            topic="pod.project.created",
            aggregate_id=project.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={"blank_id": str(blank.id)},
        )
        await session.commit()
        await session.refresh(project)
    return {"project": project_payload(project)}


@router.get("/projects/{project_id}")
async def get_project(
    project_id: uuid.UUID, request: Request, principal: PodReader
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        project = await _project_or_404(session, project_id, principal.user_id)
        blank = await _blank_or_404(session, project.blank_id, principal.user_id)
        references = list(
            (
                await session.scalars(
                    select(PodBlankReference)
                    .where(PodBlankReference.blank_id == blank.id)
                    .order_by(PodBlankReference.sort_order, PodBlankReference.id)
                )
            ).all()
        )
        ideas = list(
            (
                await session.scalars(
                    select(PodProductIdea)
                    .where(PodProductIdea.project_id == project.id)
                    .order_by(PodProductIdea.created_at.desc(), PodProductIdea.id.desc())
                    .limit(100)
                )
            ).all()
        )
        concepts = list(
            (
                await session.scalars(
                    select(PodDesignConcept)
                    .join(PodProductIdea)
                    .where(PodProductIdea.project_id == project.id)
                    .order_by(PodDesignConcept.created_at.desc(), PodDesignConcept.id.desc())
                    .limit(200)
                )
            ).all()
        )
        candidates = list(
            (
                await session.scalars(
                    select(PodPrintCandidate)
                    .join(PodDesignConcept)
                    .join(PodProductIdea)
                    .where(PodProductIdea.project_id == project.id)
                    .order_by(PodPrintCandidate.created_at.desc(), PodPrintCandidate.id.desc())
                    .limit(200)
                )
            ).all()
        )
        master = await session.scalar(
            select(PodPrintMaster).where(
                PodPrintMaster.project_id == project.id, PodPrintMaster.status == "active"
            )
        )
        products = list(
            (
                await session.scalars(
                    select(PodProduct)
                    .where(PodProduct.project_id == project.id)
                    .order_by(PodProduct.created_at.desc())
                )
            ).all()
        )
        image_sets = (
            list(
                (
                    await session.scalars(
                        select(PodImageSet)
                        .where(PodImageSet.product_id.in_([item.id for item in products]))
                        .order_by(PodImageSet.product_id, PodImageSet.version.desc())
                    )
                ).all()
            )
            if products
            else []
        )
        slots = (
            list(
                (
                    await session.scalars(
                        select(PodImageSlot)
                        .where(PodImageSlot.image_set_id.in_([item.id for item in image_sets]))
                        .order_by(PodImageSlot.sort_order, PodImageSlot.id)
                    )
                ).all()
            )
            if image_sets
            else []
        )
        copies = (
            list(
                (
                    await session.scalars(
                        select(PodProductCopy)
                        .where(PodProductCopy.product_id.in_([item.id for item in products]))
                        .order_by(PodProductCopy.product_id, PodProductCopy.version.desc())
                    )
                ).all()
            )
            if products
            else []
        )
    slots_by_set: dict[uuid.UUID, list[PodImageSlot]] = {}
    for slot in slots:
        slots_by_set.setdefault(slot.image_set_id, []).append(slot)
    return {
        "project": project_payload(project),
        "blank": blank_payload(blank, references),
        "ideas": [idea_payload(item) for item in ideas],
        "design_concepts": [concept_payload(item) for item in concepts],
        "print_candidates": [candidate_payload(item) for item in candidates],
        "print_master": master_payload(master) if master else None,
        "products": [product_payload(item) for item in products],
        "image_sets": [
            image_set_payload(item, slots_by_set.get(item.id, [])) for item in image_sets
        ],
        "product_copies": [product_copy_payload(item) for item in copies],
    }


@router.post("/projects/{project_id}/ideas/generate")
async def generate_ideas(
    project_id: uuid.UUID,
    payload: GenerateIdeas,
    request: Request,
    principal: PodWriter,
    idempotency_key: IdempotencyKey,
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        await _project_or_404(session, project_id, principal.user_id)
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code="pod.idea.generate",
        source_asset_id=None,
        parameters={"project_id": str(project_id), "count": payload.count},
        idempotency_key=idempotency_key,
    )
    return {"job": job}


@router.patch("/ideas/{idea_id}")
async def update_idea(
    idea_id: uuid.UUID, payload: IdeaStatusPatch, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        idea = await _idea_or_404(session, idea_id, principal.user_id)
        idea.status = payload.status
        _record_event(
            session,
            topic="pod.idea.status_changed",
            aggregate_id=idea.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={"status": idea.status},
        )
        await session.commit()
        await session.refresh(idea)
    return {"idea": idea_payload(idea)}


@router.post("/ideas/bulk-status")
async def bulk_update_ideas(
    payload: BulkIdeaStatus, request: Request, principal: PodWriter
) -> dict[str, Any]:
    if len(set(payload.idea_ids)) != len(payload.idea_ids):
        raise ApiError(422, "DUPLICATE_IDS", "不能重复选择创意")
    async with request.app.state.runtime_services.database.session_factory() as session:
        ideas = list(
            (
                await session.scalars(
                    select(PodProductIdea)
                    .join(PodDevelopmentProject)
                    .where(
                        PodProductIdea.id.in_(payload.idea_ids),
                        PodDevelopmentProject.owner_id == principal.user_id,
                    )
                )
            ).all()
        )
        if len(ideas) != len(payload.idea_ids):
            raise ApiError(404, "POD_IDEA_NOT_FOUND", "部分产品创意不存在")
        for idea in ideas:
            idea.status = payload.status
        await session.commit()
    return {"updated": len(ideas), "status": payload.status}


@router.post("/ideas/{idea_id}/design-concepts/generate")
async def generate_designs(
    idea_id: uuid.UUID,
    payload: GenerateDesigns,
    request: Request,
    principal: PodWriter,
    idempotency_key: IdempotencyKey,
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        idea = await _idea_or_404(session, idea_id, principal.user_id)
        if idea.status != "adopted":
            raise ApiError(409, "POD_IDEA_NOT_ADOPTED", "请先采用产品创意")
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code="pod.design.generate",
        source_asset_id=None,
        parameters={"product_idea_id": str(idea_id), "count": payload.count},
        idempotency_key=idempotency_key,
    )
    return {"job": job}


@router.patch("/design-concepts/{concept_id}")
async def update_concept(
    concept_id: uuid.UUID, payload: DesignStatusPatch, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        concept = await _concept_or_404(session, concept_id, principal.user_id)
        concept.status = payload.status
        await session.commit()
        await session.refresh(concept)
    return {"design_concept": concept_payload(concept)}


@router.post("/design-concepts/{concept_id}/print-candidates/generate")
async def generate_prints(
    concept_id: uuid.UUID, request: Request, principal: PodWriter, idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        concept = await _concept_or_404(session, concept_id, principal.user_id)
        if concept.status != "adopted":
            raise ApiError(409, "POD_DESIGN_NOT_ADOPTED", "请先采用设计方案")
        design = DesignConceptDraft.model_validate(
            {field: getattr(concept, field) for field in DesignConceptDraft.model_fields}
        )
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code="pod.print.generate",
        source_asset_id=None,
        parameters={
            "design_concept_id": str(concept_id),
            "design": design.model_dump(),
            "image_count": 4,
            "quality": "high",
            "size": "1024x1024",
        },
        idempotency_key=idempotency_key,
    )
    return {"job": job}


@router.post("/print-candidates/{candidate_id}/approve-master", status_code=status.HTTP_201_CREATED)
async def approve_print_master(
    candidate_id: uuid.UUID, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        row = await session.execute(
            select(PodPrintCandidate, PodDesignConcept, PodProductIdea, PodDevelopmentProject)
            .join(PodDesignConcept, PodDesignConcept.id == PodPrintCandidate.design_concept_id)
            .join(PodProductIdea, PodProductIdea.id == PodDesignConcept.product_idea_id)
            .join(PodDevelopmentProject, PodDevelopmentProject.id == PodProductIdea.project_id)
            .where(
                PodPrintCandidate.id == candidate_id,
                PodDevelopmentProject.owner_id == principal.user_id,
            )
            .with_for_update()
        )
        result = row.one_or_none()
        if result is None:
            raise ApiError(404, "POD_PRINT_CANDIDATE_NOT_FOUND", "印花候选不存在")
        candidate, concept, idea, project = result
        if (
            candidate.status != "generated"
            or concept.status != "adopted"
            or idea.status != "adopted"
        ):
            raise ApiError(
                409, "POD_PRINT_CANDIDATE_NOT_READY", "印花候选所属创意和设计方案必须已采用"
            )
        is_blank_reference = await session.scalar(
            select(PodBlankReference.id).where(
                PodBlankReference.blank_id == project.blank_id,
                PodBlankReference.asset_id == candidate.asset_id,
            )
        )
        if is_blank_reference is not None:
            raise ApiError(
                422,
                "POD_PRINT_MASTER_MUST_BE_SEPARATE",
                "Print Master 不能使用胚件真实参考图素材",
            )
        active = await session.scalar(
            select(PodPrintMaster)
            .where(PodPrintMaster.project_id == project.id, PodPrintMaster.status == "active")
            .with_for_update()
        )
        if active is not None:
            raise ApiError(409, "POD_PRINT_MASTER_EXISTS", "该项目已有锁定的 Print Master")
        master = PodPrintMaster(
            id=uuid7(),
            project_id=project.id,
            print_candidate_id=candidate.id,
            asset_id=candidate.asset_id,
            version=1,
            status="active",
            locked_by=principal.user_id,
            locked_at=datetime.now(UTC),
        )
        product = PodProduct(
            id=uuid7(),
            owner_id=principal.user_id,
            project_id=project.id,
            product_idea_id=idea.id,
            design_concept_id=concept.id,
            print_master_id=master.id,
            status="drafting",
        )
        candidate.status = "approved"
        project.current_stage = "print_master"
        project.status = "active"
        session.add_all([master, product])
        _record_event(
            session,
            topic="pod.print_master.locked",
            aggregate_id=master.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={"project_id": str(project.id), "candidate_id": str(candidate.id)},
        )
        await session.commit()
        await session.refresh(master)
        await session.refresh(product)
    return {"print_master": master_payload(master), "product": product_payload(product)}


@router.post("/products/{product_id}/image-set/strategy/generate")
async def generate_image_strategy(
    product_id: uuid.UUID, request: Request, principal: PodWriter, idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        product = await _product_or_404(session, product_id, principal.user_id)
        master = await session.get(PodPrintMaster, product.print_master_id)
        if master is None or master.status != "active":
            raise ApiError(409, "POD_PRINT_MASTER_NOT_ACTIVE", "请先锁定有效的 Print Master")
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code="pod.image.strategy.generate",
        source_asset_id=None,
        parameters={"product_id": str(product_id)},
        idempotency_key=idempotency_key,
    )
    return {"job": job}


@router.patch("/image-slots/{slot_id}")
async def update_image_slot(
    slot_id: uuid.UUID, payload: ImageSlotPatch, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        slot, _image_set, _product = await _image_slot_or_404(session, slot_id, principal.user_id)
        if slot.status == "approved":
            raise ApiError(409, "POD_IMAGE_SLOT_APPROVED", "已审核通过的图片槽位不能直接修改")
        for field in payload.model_fields_set:
            setattr(slot, field, getattr(payload, field))
        await session.commit()
        await session.refresh(slot)
    return {"image_slot": image_slot_payload(slot)}


async def _submit_image_slot_generation(
    *,
    product_id: uuid.UUID,
    slot_id: uuid.UUID,
    payload: ImageSlotGenerate,
    request: Request,
    principal: Principal,
    idempotency_key: str,
) -> dict[str, Any]:
    runtime = request.app.state.runtime_services
    async with runtime.database.session_factory() as session:
        product = await _product_or_404(session, product_id, principal.user_id)
        slot, image_set, slot_product = await _image_slot_or_404(
            session, slot_id, principal.user_id, product_id=product.id
        )
        operation_code, source_asset_id, parameters = await _slot_generation_spec(
            session,
            product=slot_product,
            image_set=image_set,
            slot=slot,
            payload=payload,
            owner_id=principal.user_id,
        )
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code=operation_code,
        source_asset_id=source_asset_id,
        parameters=parameters,
        idempotency_key=idempotency_key,
    )
    async with runtime.database.session_factory() as session:
        slot, _image_set, _product = await _image_slot_or_404(
            session, slot_id, principal.user_id, product_id=product_id
        )
        slot.generation_job_id = uuid.UUID(job["job_id"])
        if payload.scene_prompt is not None:
            slot.scene_prompt = payload.scene_prompt
        if payload.composition_prompt is not None:
            slot.composition_prompt = payload.composition_prompt
        if payload.style_prompt is not None:
            slot.style_prompt = payload.style_prompt
        slot.prompt_snapshot = {
            "operation_code": operation_code,
            "model_prompt": parameters["prompt"],
            "scene_prompt": slot.scene_prompt,
            "composition_prompt": slot.composition_prompt,
            "style_prompt": slot.style_prompt,
            "parameters": parameters,
        }
        _record_event(
            session,
            topic="pod.image_slot.generation_submitted",
            aggregate_id=slot.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={
                "product_id": str(product_id),
                "job_id": job["job_id"],
                "slot_code": slot.code,
            },
        )
        await session.commit()
    return {"job": job}


@router.post("/products/{product_id}/image-slots/{slot_id}/generate")
async def generate_image_slot(
    product_id: uuid.UUID,
    slot_id: uuid.UUID,
    payload: ImageSlotGenerate,
    request: Request,
    principal: PodWriter,
    idempotency_key: IdempotencyKey,
) -> dict[str, Any]:
    return await _submit_image_slot_generation(
        product_id=product_id,
        slot_id=slot_id,
        payload=payload,
        request=request,
        principal=principal,
        idempotency_key=idempotency_key,
    )


@router.post("/products/{product_id}/image-slots/bulk-generate")
async def bulk_generate_image_slots(
    product_id: uuid.UUID,
    payload: BulkImageSlotGenerate,
    request: Request,
    principal: PodWriter,
    idempotency_key: IdempotencyKey,
) -> dict[str, Any]:
    if len(set(payload.slot_ids)) != len(payload.slot_ids):
        raise ApiError(422, "DUPLICATE_IDS", "不能重复选择图片槽位")
    results = []
    single_payload = ImageSlotGenerate(
        scene_prompt=payload.scene_prompt,
        composition_prompt=payload.composition_prompt,
        style_prompt=payload.style_prompt,
        size=payload.size,
        quality=payload.quality,
    )
    for slot_id in payload.slot_ids:
        results.append(
            await _submit_image_slot_generation(
                product_id=product_id,
                slot_id=slot_id,
                payload=single_payload,
                request=request,
                principal=principal,
                idempotency_key=f"{idempotency_key[:180]}:slot:{slot_id}",
            )
        )
    return {"submitted": len(results), "jobs": [result["job"] for result in results]}


@router.post("/products/{product_id}/copy/generate")
async def generate_product_copy(
    product_id: uuid.UUID, request: Request, principal: PodWriter, idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        product = await _product_or_404(session, product_id, principal.user_id)
        await _require_product_main_reviewed(session, product)
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code="pod.copy.generate",
        source_asset_id=None,
        parameters={"product_id": str(product_id)},
        idempotency_key=idempotency_key,
    )
    return {"job": job}


@router.patch("/product-copies/{copy_id}")
async def update_product_copy(
    copy_id: uuid.UUID, payload: ProductCopyPatch, request: Request, principal: PodWriter
) -> dict[str, Any]:
    if not payload.model_fields_set:
        raise ApiError(422, "POD_PRODUCT_COPY_EMPTY_UPDATE", "请至少修改一个商品文案字段")
    async with request.app.state.runtime_services.database.session_factory() as session:
        copy, product = await _copy_or_404(session, copy_id, principal.user_id)
        if copy.status != "active":
            raise ApiError(409, "POD_PRODUCT_COPY_ARCHIVED", "已归档的商品文案不能直接修改")
        from app.domain.pod import ProductCopyDraft

        values = {
            "product_title": copy.product_title,
            "product_description": copy.product_description,
            "selling_points": copy.selling_points,
            "search_keywords": copy.search_keywords,
            "content_warnings": copy.content_warnings,
        }
        values.update({field: getattr(payload, field) for field in payload.model_fields_set})
        checked = ProductCopyDraft.model_validate(values)
        for field, value in checked.model_dump().items():
            setattr(copy, field, value)
        product.status = "review_pending"
        _record_event(
            session,
            topic="pod.product_copy.updated",
            aggregate_id=copy.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={"product_id": str(product.id), "fields": sorted(payload.model_fields_set)},
        )
        await session.commit()
        await session.refresh(copy)
    return {"product_copy": product_copy_payload(copy)}


@router.delete("/product-copies/{copy_id}")
async def archive_product_copy(
    copy_id: uuid.UUID, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        copy, product = await _copy_or_404(session, copy_id, principal.user_id)
        if copy.status == "archived":
            return {"product_copy": product_copy_payload(copy)}
        copy.status = "archived"
        if product.status in {"review_pending", "approved"}:
            product.status = "visual_ready"
        _record_event(
            session,
            topic="pod.product_copy.archived",
            aggregate_id=copy.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={"product_id": str(product.id)},
        )
        await session.commit()
        await session.refresh(copy)
    return {"product_copy": product_copy_payload(copy)}


@router.post("/products/{product_id}/primary-visual/generate")
async def generate_primary_visual(
    product_id: uuid.UUID,
    payload: ProductVisualGenerate,
    request: Request,
    principal: PodWriter,
    idempotency_key: IdempotencyKey,
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        product = await session.get(PodProduct, product_id)
        if product is None or product.owner_id != principal.user_id:
            raise ApiError(404, "POD_PRODUCT_NOT_FOUND", "商品不存在")
        master = await session.get(PodPrintMaster, product.print_master_id)
        project = await _project_or_404(session, product.project_id, principal.user_id)
        blank = await _blank_or_404(session, project.blank_id, principal.user_id)
        references = list(
            (
                await session.scalars(
                    select(PodBlankReference)
                    .where(PodBlankReference.blank_id == blank.id)
                    .order_by(PodBlankReference.sort_order, PodBlankReference.id)
                )
            ).all()
        )
        if not references:
            raise ApiError(422, "POD_BLANK_REFERENCE_REQUIRED", "请先添加真实胚件参考图")
        if master is None or master.status != "active":
            raise ApiError(409, "POD_PRINT_MASTER_NOT_ACTIVE", "Print Master 尚未锁定或已失效")
        if master.asset_id in {reference.asset_id for reference in references}:
            raise ApiError(
                409,
                "POD_PRINT_MASTER_MUST_BE_SEPARATE",
                "Print Master 不能使用胚件真实参考图素材",
            )
        asset_ids = [item.asset_id for item in references] + [master.asset_id]
        prompt = product_visual_prompt(
            blank_name=blank.name,
            visual_style=blank.product_visual_style,
            scene=payload.scene,
            composition=payload.composition,
        )
    parameters = {
        "blank_id": str(blank.id),
        "project_id": str(project.id),
        "product_id": str(product.id),
        "print_master_id": str(master.id),
        "print_master_asset_id": str(master.asset_id),
        "blank_reference_asset_ids": [str(item.asset_id) for item in references],
        "reference_asset_ids": [str(item) for item in asset_ids],
        "prompt": prompt,
        "size": payload.size,
        "quality": payload.quality,
        "image_count": 1,
    }
    job = await _submit_job(
        request=request,
        principal=principal,
        operation_code="pod.visual.generate",
        source_asset_id=references[0].asset_id,
        parameters=parameters,
        idempotency_key=idempotency_key,
    )
    return {"job": job}


@router.post("/reviews", status_code=status.HTTP_201_CREATED)
async def create_review(
    payload: ReviewCreate, request: Request, principal: PodWriter
) -> dict[str, Any]:
    async with request.app.state.runtime_services.database.session_factory() as session:
        if payload.target_type == "product":
            product = await session.get(PodProduct, payload.target_id)
            if product is None or product.owner_id != principal.user_id:
                raise ApiError(404, "POD_PRODUCT_NOT_FOUND", "商品不存在")
            if payload.gate != "G3":
                raise ApiError(422, "POD_REVIEW_GATE_INVALID", "商品审核必须使用 G3")
            if payload.decision == "approved":
                await _require_product_main_reviewed(session, product)
                copy = await session.scalar(
                    select(PodProductCopy).where(
                        PodProductCopy.product_id == product.id,
                        PodProductCopy.status == "active",
                    )
                )
                if copy is None:
                    raise ApiError(409, "POD_PRODUCT_COPY_REQUIRED", "请先生成并确认商品文案")
            product.status = "approved" if payload.decision == "approved" else "rejected"
        if payload.target_type == "image_slot":
            slot, _image_set, _product = await _image_slot_or_404(
                session, payload.target_id, principal.user_id
            )
            if payload.gate != "G2":
                raise ApiError(422, "POD_REVIEW_GATE_INVALID", "商品图片审核必须使用 G2")
            if slot.asset_id is None:
                raise ApiError(409, "POD_IMAGE_SLOT_NOT_GENERATED", "请先生成商品图片")
            slot.status = "approved" if payload.decision == "approved" else "rejected"
        review = PodReview(id=uuid7(), owner_id=principal.user_id, **payload.model_dump())
        session.add(review)
        _record_event(
            session,
            topic="pod.review.created",
            aggregate_id=review.id,
            owner_id=principal.user_id,
            request_id=_request_id(request),
            details={
                "target_type": payload.target_type,
                "gate": payload.gate,
                "decision": payload.decision,
            },
        )
        await session.commit()
        await session.refresh(review)
    return {
        "review": {
            "id": str(review.id),
            "target_type": review.target_type,
            "target_id": str(review.target_id),
            "gate": review.gate,
            "decision": review.decision,
            "note": review.note,
            "created_at": review.created_at,
        }
    }
