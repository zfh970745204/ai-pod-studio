from __future__ import annotations

import base64
import time
import uuid
from typing import Any

from sqlalchemy import select

from app.domain.ids import uuid7
from app.domain.pod import (
    BlankAnalysis,
    DesignConceptBatch,
    DesignConceptDraft,
    ProductCopyDraft,
    ProductIdeaBatch,
    ProductImageStrategy,
    blank_analysis_instruction,
    design_concepts_instruction,
    parse_json,
    print_prompt,
    product_copy_instruction,
    product_image_strategy_instruction,
)
from app.repositories.models import (
    Asset,
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
)
from app.services.configuration import sub2api_profile_settings
from app.services.jobs import ClaimedJob, PermanentJobError
from app.sub2api import Sub2APIClient, Sub2APIError


class PodJobExecutor:
    """Runs text and multimodal POD stages through the durable ImageJob queue."""

    def __init__(self, settings, database, storage, *, config_cache=None) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage
        self.config_cache = config_cache

    async def __call__(self, claim: ClaimedJob) -> dict[str, Any]:
        started = time.perf_counter()
        if claim.operation_code == "pod.blank.analyze":
            provider_id = await self._analyze_blank(claim)
        elif claim.operation_code == "pod.idea.generate":
            provider_id = await self._generate_ideas(claim)
        elif claim.operation_code == "pod.design.generate":
            provider_id = await self._generate_designs(claim)
        elif claim.operation_code == "pod.image.strategy.generate":
            provider_id = await self._generate_image_strategy(claim)
        elif claim.operation_code == "pod.copy.generate":
            provider_id = await self._generate_product_copy(claim)
        else:
            raise PermanentJobError("POD_EXECUTOR_MISSING", "POD 任务没有可用执行器")
        return {
            "provider_request_id": provider_id,
            "metrics": {"duration_ms": round((time.perf_counter() - started) * 1000)},
        }

    async def _analyze_blank(self, claim: ClaimedJob) -> str | None:
        blank_id = self._uuid(claim.parameters, "blank_id")
        async with self.database.session_factory() as session:
            blank = await self._owned(session, PodBlank, blank_id, claim.user_id, "胚件不存在")
            references = await self._references(session, blank.id)
            content = await self._vision_content(
                references,
                blank_analysis_instruction(
                    category=blank.category,
                    material=blank.material,
                    confirmed=dict(blank.confirmed_attributes),
                ),
            )
            result = await self._chat(claim, content)
            analysis = BlankAnalysis.model_validate(parse_json(result.content))
            blank.suggested_attributes = {
                **analysis.suggested_attributes,
                "product_type": analysis.product_type,
                "visible_material_guess": analysis.visible_material_guess,
                "product_shape": analysis.product_shape,
                "likely_print_method": analysis.likely_print_method,
                "recommended_use_cases": analysis.recommended_use_cases,
                "visual_features": analysis.visual_features,
                "confidence_notes": analysis.confidence_notes,
                "source": "ai_suggested",
            }
            await session.commit()
        return result.provider_request_id

    async def _generate_ideas(self, claim: ClaimedJob) -> str | None:
        project_id = self._uuid(claim.parameters, "project_id")
        count = int(claim.parameters.get("count", 20))
        async with self.database.session_factory() as session:
            project = await self._owned(
                session, PodDevelopmentProject, project_id, claim.user_id, "开发项目不存在"
            )
            blank = await self._owned(
                session, PodBlank, project.blank_id, claim.user_id, "胚件不存在"
            )
            from app.domain.pod import product_ideas_instruction

            result = await self._chat(
                claim,
                product_ideas_instruction(
                    category=blank.category,
                    material=blank.material,
                    confirmed=dict(blank.confirmed_attributes),
                    suggested=dict(blank.suggested_attributes),
                    count=count,
                ),
            )
            batch = ProductIdeaBatch.model_validate(parse_json(result.content))
            if len(batch.items) != count:
                raise PermanentJobError("POD_AI_COUNT_MISMATCH", "AI 返回的创意数量不符合请求")
            batch_id = uuid7()
            for item in batch.items:
                session.add(
                    PodProductIdea(
                        id=uuid7(),
                        project_id=project.id,
                        generation_job_id=claim.job_id,
                        generation_batch_id=batch_id,
                        status="proposed",
                        **item.model_dump(),
                    )
                )
            project.status, project.current_stage = "active", "ideas"
            await session.commit()
        return result.provider_request_id

    async def _generate_designs(self, claim: ClaimedJob) -> str | None:
        idea_id = self._uuid(claim.parameters, "product_idea_id")
        count = int(claim.parameters.get("count", 4))
        async with self.database.session_factory() as session:
            idea = await self._idea_owned(session, idea_id, claim.user_id)
            result = await self._chat(
                claim, design_concepts_instruction(idea=self._idea_dict(idea), count=count)
            )
            batch = DesignConceptBatch.model_validate(parse_json(result.content))
            if len(batch.items) != count:
                raise PermanentJobError("POD_AI_COUNT_MISMATCH", "AI 返回的设计数量不符合请求")
            for item in batch.items:
                session.add(
                    PodDesignConcept(
                        id=uuid7(),
                        product_idea_id=idea.id,
                        generation_job_id=claim.job_id,
                        status="proposed",
                        **item.model_dump(),
                    )
                )
            await session.commit()
        return result.provider_request_id

    async def _generate_image_strategy(self, claim: ClaimedJob) -> str | None:
        product_id = self._uuid(claim.parameters, "product_id")
        async with self.database.session_factory() as session:
            product = await self._owned(
                session, PodProduct, product_id, claim.user_id, "商品不存在"
            )
            project = await self._owned(
                session, PodDevelopmentProject, product.project_id, claim.user_id, "开发项目不存在"
            )
            blank = await self._owned(
                session, PodBlank, project.blank_id, claim.user_id, "胚件不存在"
            )
            idea = await self._idea_owned(session, product.product_idea_id, claim.user_id)
            master = await session.get(PodPrintMaster, product.print_master_id)
            if master is None or master.status != "active":
                raise PermanentJobError(
                    "POD_PRINT_MASTER_NOT_ACTIVE", "Print Master 尚未锁定或已失效"
                )
            result = await self._chat(
                claim,
                product_image_strategy_instruction(
                    category=blank.category,
                    material=blank.material,
                    confirmed=dict(blank.confirmed_attributes),
                    suggested=dict(blank.suggested_attributes),
                    idea=self._idea_dict(idea),
                ),
            )
            strategy = ProductImageStrategy.model_validate(parse_json(result.content))
            active_sets = list(
                (
                    await session.scalars(
                        select(PodImageSet)
                        .where(PodImageSet.product_id == product.id, PodImageSet.status == "active")
                        .with_for_update()
                    )
                ).all()
            )
            for image_set in active_sets:
                image_set.status = "archived"
            latest_version = await session.scalar(
                select(PodImageSet.version)
                .where(PodImageSet.product_id == product.id)
                .order_by(PodImageSet.version.desc())
                .limit(1)
            )
            image_set = PodImageSet(
                id=uuid7(),
                product_id=product.id,
                generation_job_id=claim.job_id,
                version=(latest_version or 0) + 1,
                strategy_snapshot={
                    "rationale": strategy.rationale,
                    "slots": [item.model_dump() for item in strategy.slots],
                },
                status="active",
            )
            session.add(image_set)
            await session.flush()
            for index, slot in enumerate(strategy.slots):
                session.add(
                    PodImageSlot(
                        id=uuid7(),
                        image_set_id=image_set.id,
                        code=slot.code,
                        title=slot.title,
                        scope=slot.scope,
                        requires_print=slot.requires_print,
                        scene_prompt=slot.scene_prompt,
                        composition_prompt=slot.composition_prompt,
                        style_prompt=slot.style_prompt,
                        sort_order=index,
                        prompt_snapshot={},
                        status="planned",
                    )
                )
            # A new active strategy requires a newly generated and reviewed product_main.
            # Prior set assets remain traceable through their archived slots.
            product.primary_visual_asset_id = None
            product.primary_visual_job_id = None
            product.status = "drafting"
            project.current_stage = "image_strategy"
            await session.commit()
        return result.provider_request_id

    async def _generate_product_copy(self, claim: ClaimedJob) -> str | None:
        product_id = self._uuid(claim.parameters, "product_id")
        async with self.database.session_factory() as session:
            product = await self._owned(
                session, PodProduct, product_id, claim.user_id, "商品不存在"
            )
            if product.primary_visual_asset_id is None or product.status not in {
                "visual_ready",
                "approved",
                "review_pending",
            }:
                raise PermanentJobError(
                    "POD_PRODUCT_MAIN_VISUAL_REQUIRED", "请先完成商品主图生成和审核"
                )
            project = await self._owned(
                session, PodDevelopmentProject, product.project_id, claim.user_id, "开发项目不存在"
            )
            blank = await self._owned(
                session, PodBlank, project.blank_id, claim.user_id, "胚件不存在"
            )
            idea = await self._idea_owned(session, product.product_idea_id, claim.user_id)
            concept = await session.get(PodDesignConcept, product.design_concept_id)
            master = await session.get(PodPrintMaster, product.print_master_id)
            if concept is None or concept.status != "adopted":
                raise PermanentJobError("POD_DESIGN_NOT_ADOPTED", "当前商品设计方案不可用")
            if master is None or master.status != "active":
                raise PermanentJobError(
                    "POD_PRINT_MASTER_NOT_ACTIVE", "Print Master 尚未锁定或已失效"
                )
            active_set = await session.scalar(
                select(PodImageSet).where(
                    PodImageSet.product_id == product.id, PodImageSet.status == "active"
                )
            )
            if active_set is not None:
                main_slot = await session.scalar(
                    select(PodImageSlot).where(
                        PodImageSlot.image_set_id == active_set.id,
                        PodImageSlot.code == "product_main",
                    )
                )
                if main_slot is None or main_slot.status != "approved":
                    raise PermanentJobError(
                        "POD_PRODUCT_MAIN_REVIEW_REQUIRED", "请先完成当前商品主图的 G2 审核"
                    )
            instruction = product_copy_instruction(
                category=blank.category,
                material=blank.material,
                confirmed=dict(blank.confirmed_attributes),
                idea=self._idea_dict(idea),
                design={
                    key: getattr(concept, key)
                    for key in (
                        "design_name",
                        "visual_style",
                        "composition",
                        "layout",
                        "main_subject",
                        "secondary_elements",
                        "color_palette",
                        "typography_direction",
                        "pattern_structure",
                        "print_method",
                        "recommended_print_area",
                        "texture_direction",
                        "background_direction",
                        "negative_elements",
                    )
                },
            )
            result = await self._chat(claim, instruction)
            draft = ProductCopyDraft.model_validate(parse_json(result.content))
            active_copies = list(
                (
                    await session.scalars(
                        select(PodProductCopy)
                        .where(
                            PodProductCopy.product_id == product.id,
                            PodProductCopy.status == "active",
                        )
                        .with_for_update()
                    )
                ).all()
            )
            for copy in active_copies:
                copy.status = "archived"
            if active_copies:
                await session.flush()
            latest_version = await session.scalar(
                select(PodProductCopy.version)
                .where(PodProductCopy.product_id == product.id)
                .order_by(PodProductCopy.version.desc())
                .limit(1)
            )
            session.add(
                PodProductCopy(
                    id=uuid7(),
                    product_id=product.id,
                    generation_job_id=claim.job_id,
                    version=(latest_version or 0) + 1,
                    locale="en-US",
                    prompt_snapshot={
                        "model_prompt": instruction,
                        "product_id": str(product.id),
                        "print_master_id": str(master.id),
                        "content": draft.model_dump(),
                    },
                    status="active",
                    **draft.model_dump(),
                )
            )
            product.status = "review_pending"
            project.current_stage = "product_copy"
            await session.commit()
        return result.provider_request_id

    async def _chat(self, claim: ClaimedJob, content: str | list[dict[str, Any]]):
        clients = await self._clients(claim)
        last: Exception | None = None
        for client in clients:
            try:
                return await client.chat_json(
                    system_prompt="You are an AI POD product-development assistant. Return valid JSON only.",
                    user_content=content,
                )
            except Sub2APIError as exc:
                last = exc
        raise PermanentJobError("POD_AI_UNAVAILABLE", "POD AI 服务暂时不可用") from last

    async def _clients(self, claim: ClaimedJob) -> list[Sub2APIClient]:
        if self.config_cache is not None and claim.sub2api_config_version is not None:
            config = await self.config_cache.get("sub2api", claim.sub2api_config_version)
            settings = sub2api_profile_settings(config)
            if settings:
                return [Sub2APIClient(item) for item in settings]
        if self.settings.sub2api_configured:
            return [Sub2APIClient(self.settings)]
        raise PermanentJobError("SUB2API_NOT_CONFIGURED", "Sub2API 尚未配置")

    async def _vision_content(self, refs: list[Asset], instruction: str) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": instruction}]
        for asset in refs[:3]:
            raw = await self.storage.get_object(asset.object_key)
            encoded = base64.b64encode(raw).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{asset.mime_type};base64,{encoded}"},
                }
            )
        return content

    async def _references(self, session, blank_id: uuid.UUID) -> list[Asset]:
        rows = await session.execute(
            select(Asset)
            .join(PodBlankReference, PodBlankReference.asset_id == Asset.id)
            .where(PodBlankReference.blank_id == blank_id)
            .order_by(PodBlankReference.sort_order, PodBlankReference.id)
        )
        assets = list(rows.scalars())
        if not assets:
            raise PermanentJobError("POD_BLANK_REFERENCE_REQUIRED", "请先为胚件添加真实参考图")
        return assets

    @staticmethod
    async def _owned(session, model, item_id, owner_id, message):
        item = await session.get(model, item_id)
        if item is None or item.owner_id != owner_id:
            raise PermanentJobError("POD_RESOURCE_NOT_FOUND", message)
        return item

    @staticmethod
    async def _idea_owned(session, idea_id, owner_id) -> PodProductIdea:
        row = await session.execute(
            select(PodProductIdea)
            .join(PodDevelopmentProject)
            .where(PodProductIdea.id == idea_id, PodDevelopmentProject.owner_id == owner_id)
        )
        idea = row.scalar_one_or_none()
        if idea is None:
            raise PermanentJobError("POD_RESOURCE_NOT_FOUND", "产品创意不存在")
        return idea

    @staticmethod
    def _uuid(values: dict[str, Any], name: str) -> uuid.UUID:
        try:
            return uuid.UUID(str(values[name]))
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentJobError("INVALID_OPERATION_PARAMETERS", f"参数 {name} 无效") from exc

    @staticmethod
    def _idea_dict(idea: PodProductIdea) -> dict[str, Any]:
        return {
            key: getattr(idea, key)
            for key in (
                "idea_name",
                "target_audience",
                "use_case",
                "emotional_angle",
                "design_theme",
                "visual_direction",
                "recommended_style",
                "composition_direction",
                "color_direction",
                "core_elements",
                "avoid_elements",
                "rationale",
                "infringement_risk",
            )
        }


async def attach_image_outputs(session, claim: ClaimedJob, asset_ids: list[uuid.UUID]) -> None:
    """Link job assets into POD records while retaining Asset as image authority."""
    if not claim.operation_code.startswith("pod."):
        return
    if claim.operation_code == "pod.print.generate":
        concept_id = PodJobExecutor._uuid(claim.parameters, "design_concept_id")
        concept = await session.get(PodDesignConcept, concept_id)
        if concept is None:
            raise PermanentJobError("POD_RESOURCE_NOT_FOUND", "设计方案不存在")
        design = claim.parameters.get("design")
        if not isinstance(design, dict):
            raise PermanentJobError("INVALID_OPERATION_PARAMETERS", "印花任务缺少设计方案快照")
        parsed = DesignConceptDraft.model_validate(design)
        for index, asset_id in enumerate(asset_ids):
            session.add(
                PodPrintCandidate(
                    id=uuid7(),
                    design_concept_id=concept.id,
                    asset_id=asset_id,
                    generation_job_id=claim.job_id,
                    prompt_snapshot={
                        "design_concept": parsed.model_dump(),
                        "model_prompt": print_prompt(parsed, index),
                        "variation_index": index + 1,
                    },
                    status="generated",
                )
            )
    elif claim.operation_code in {"pod.visual.generate", "pod.visual.generic"}:
        product_id = PodJobExecutor._uuid(claim.parameters, "product_id")
        product = await session.get(PodProduct, product_id)
        if product is None or product.owner_id != claim.user_id:
            raise PermanentJobError("POD_RESOURCE_NOT_FOUND", "商品不存在")
        primary_visual_ready = False
        slot_id = claim.parameters.get("image_slot_id")
        if slot_id is not None:
            try:
                slot = await session.get(PodImageSlot, uuid.UUID(str(slot_id)))
            except (TypeError, ValueError) as exc:
                raise PermanentJobError("INVALID_OPERATION_PARAMETERS", "图片槽位参数无效") from exc
            if slot is None:
                raise PermanentJobError("POD_RESOURCE_NOT_FOUND", "图片槽位不存在")
            image_set = await session.get(PodImageSet, slot.image_set_id)
            if image_set is None or image_set.product_id != product.id:
                raise PermanentJobError("POD_RESOURCE_NOT_FOUND", "图片槽位不属于当前商品")
            slot.asset_id = asset_ids[0]
            slot.generation_job_id = claim.job_id
            slot.status = "generated"
            if slot.code == "product_main":
                product.primary_visual_asset_id = asset_ids[0]
                product.primary_visual_job_id = claim.job_id
                primary_visual_ready = True
        else:
            product.primary_visual_asset_id = asset_ids[0]
            product.primary_visual_job_id = claim.job_id
            primary_visual_ready = True
        if primary_visual_ready:
            product.status = "visual_ready"
