from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from test_assets import asset_context as asset_fixture
from test_assets import client_for, login, raster_bytes, seed_user, upload

from app.api.pod import router as pod_router
from app.config import Settings
from app.domain.ids import uuid7
from app.domain.pod import ProductImageSlotDraft
from app.repositories.models import (
    ImageJob,
    PodDesignConcept,
    PodImageSet,
    PodImageSlot,
    PodPrintCandidate,
    PodProduct,
    PodProductCopy,
    PodProductIdea,
)
from app.services.image_executor import ImageJobExecutor
from app.services.jobs import ClaimedJob
from app.services.pod import PodJobExecutor, attach_image_outputs
from app.sub2api import UpstreamImage

asset_context = asset_fixture


@pytest.mark.asyncio
async def test_pod_blank_only_requires_category_and_material_then_locks_one_master(asset_context):
    asset_context.app.include_router(pod_router)
    owner = await seed_user(asset_context, email="pod-owner@example.test")
    async with client_for(asset_context, "pod-owner") as client:
        await login(client, owner.email)
        created = await client.post(
            "/api/v1/pod/blanks", json={"category": "Blanket", "material": "Fleece"}
        )
        assert created.status_code == 201, created.text
        blank = created.json()["blank"]
        assert blank["name"] == "Blanket / Fleece"
        assert blank["references"] == []

        uploaded = (await upload(client, raster_bytes())).json()["asset"]
        print_asset = (await upload(client, raster_bytes(size=(15, 10)))).json()["asset"]
        linked = await client.post(
            f"/api/v1/pod/blanks/{blank['id']}/references",
            json={"asset_id": uploaded["id"], "reference_role": "primary"},
        )
        assert linked.status_code == 201, linked.text
        project_response = await client.post("/api/v1/pod/projects", json={"blank_id": blank["id"]})
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()["project"]

    async with asset_context.database.session_factory() as session:
        idea = PodProductIdea(
            id=uuid7(),
            project_id=uuid.UUID(project["id"]),
            generation_job_id=None,
            generation_batch_id=uuid7(),
            idea_name="Cozy Reading",
            target_audience="Readers",
            use_case="Living room",
            emotional_angle="Warm",
            design_theme="Books",
            visual_direction="Illustration",
            recommended_style="Vintage",
            composition_direction="Center",
            color_direction="Blue",
            core_elements=["book"],
            avoid_elements=["logos"],
            rationale="test",
            infringement_risk={"risk_level": "low", "warnings": []},
            status="adopted",
        )
        concept = PodDesignConcept(
            id=uuid7(),
            product_idea_id=idea.id,
            generation_job_id=None,
            design_name="Badge",
            visual_style="Vintage",
            composition="Central badge",
            layout="Centered",
            main_subject="Book",
            secondary_elements=["stars"],
            color_palette="Blue",
            typography_direction="No text",
            pattern_structure="Badge",
            print_method="DTG",
            recommended_print_area="Front",
            texture_direction="Flat",
            background_direction="Transparent",
            negative_elements=["logos"],
            design_prompt="Original flat book badge print with simple stars and no text.",
            status="adopted",
        )
        candidate = PodPrintCandidate(
            id=uuid7(),
            design_concept_id=concept.id,
            asset_id=uuid.UUID(print_asset["id"]),
            generation_job_id=None,
            prompt_snapshot={},
            status="generated",
        )
        session.add(idea)
        await session.flush()
        session.add(concept)
        await session.flush()
        await session.commit()

    async with client_for(asset_context, "pod-owner") as client:
        await login(client, owner.email)
        print_job = await client.post(
            f"/api/v1/pod/design-concepts/{concept.id}/print-candidates/generate",
            headers={"Idempotency-Key": "pod-print-candidates"},
        )
        assert print_job.status_code == 200, print_job.text

    async with asset_context.database.session_factory() as session:
        candidate.generation_job_id = uuid.UUID(print_job.json()["job"]["job_id"])
        session.add(candidate)
        await session.commit()

    async with client_for(asset_context, "pod-owner") as client:
        await login(client, owner.email)
        approved = await client.post(f"/api/v1/pod/print-candidates/{candidate.id}/approve-master")
        assert approved.status_code == 201, approved.text
        payload = approved.json()
        assert payload["print_master"]["asset_id"] == print_asset["id"]
        assert payload["product"]["print_master_id"] == payload["print_master"]["id"]
        duplicate = await client.post(f"/api/v1/pod/print-candidates/{candidate.id}/approve-master")
        assert duplicate.status_code == 409

        visual = await client.post(
            f"/api/v1/pod/products/{payload['product']['id']}/primary-visual/generate",
            headers={"Idempotency-Key": "pod-primary-visual"},
            json={"scene": "Clean catalog studio", "composition": "Full blanket view"},
        )
        assert visual.status_code == 200, visual.text
        job_id = uuid.UUID(visual.json()["job"]["job_id"])

    async with asset_context.database.session_factory() as session:
        job = await session.get(ImageJob, job_id)
        assert job is not None
        assert job.operation_code == "pod.visual.generate"
        assert job.parameters["reference_asset_ids"][0] == uploaded["id"]
        assert job.parameters["reference_asset_ids"][-1] == print_asset["id"]
        assert job.parameters["print_master_asset_id"] == print_asset["id"]


@pytest.mark.asyncio
async def test_pod_product_visual_passes_blank_and_master_as_original_references():
    settings = Settings(
        _env_file=None,
        sub2api_api_key="test-key",
        sub2api_base_url="https://upstream.example.test/v1",
    )
    client = SimpleNamespace(edit=AsyncMock(return_value=UpstreamImage(b"visual", "png", None)))
    executor = ImageJobExecutor(settings, None, None, sub2api=client)
    executor._references = AsyncMock(return_value=[b"blank", b"detail", b"print-master"])
    claim = ClaimedJob(
        uuid.uuid4(),
        uuid.uuid4(),
        "pod.visual.generate",
        None,
        {
            "prompt": "apply locked print",
            "size": "1024x1024",
            "quality": "high",
            "blank_id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "product_id": str(uuid.uuid4()),
            "print_master_id": str(uuid.uuid4()),
            "print_master_asset_id": str(uuid.uuid4()),
            "blank_reference_asset_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
        },
        1,
        480,
        30,
    )
    output, extension, _, metadata = await executor._execute(claim, None)
    assert output == b"visual" and extension == "png"
    client.edit.assert_awaited_once()
    assert client.edit.call_args.kwargs["image_png"] == b"blank"
    assert client.edit.call_args.kwargs["reference_images"] == [b"detail", b"print-master"]
    assert metadata["scope"] == "product_specific"
    assert metadata["requires_print"] is True


@pytest.mark.asyncio
async def test_print_candidates_record_the_full_model_prompt_snapshot():
    concept_id = uuid.uuid4()
    added = []

    class RecordingSession:
        async def get(self, _model, _identifier):
            return SimpleNamespace(id=concept_id)

        def add(self, candidate):
            added.append(candidate)

    design = {
        "design_name": "Badge",
        "visual_style": "Vintage",
        "composition": "Central badge",
        "layout": "Centered",
        "main_subject": "Book",
        "secondary_elements": ["stars"],
        "color_palette": "Blue",
        "typography_direction": "No text",
        "pattern_structure": "Badge",
        "print_method": "DTG",
        "recommended_print_area": "Front",
        "texture_direction": "Flat",
        "background_direction": "Transparent",
        "negative_elements": ["logos"],
        "design_prompt": "Original flat book badge print with simple stars and no text.",
    }
    claim = ClaimedJob(
        uuid.uuid4(),
        uuid.uuid4(),
        "pod.print.generate",
        None,
        {"design_concept_id": str(concept_id), "design": design},
        1,
        480,
        30,
    )
    asset_ids = [uuid.uuid4(), uuid.uuid4()]

    await attach_image_outputs(RecordingSession(), claim, asset_ids)

    assert [candidate.asset_id for candidate in added] == asset_ids
    assert added[0].prompt_snapshot["design_concept"] == design
    assert added[0].prompt_snapshot["variation_index"] == 1
    assert added[1].prompt_snapshot["variation_index"] == 2
    assert "Variation: 1 of 4" in added[0].prompt_snapshot["model_prompt"]
    assert "Variation: 2 of 4" in added[1].prompt_snapshot["model_prompt"]


def test_product_specific_image_slots_require_a_print_master():
    with pytest.raises(ValueError, match="商品专属图片槽位必须使用 Print Master"):
        ProductImageSlotDraft.model_validate(
            {
                "code": "product_main",
                "title": "商品主图",
                "scope": "product_specific",
                "requires_print": False,
                "scene_prompt": "明亮的棚拍场景",
                "composition_prompt": "完整展示产品",
                "style_prompt": "干净的电商视觉",
            }
        )


@pytest.mark.asyncio
async def test_pod_image_set_slots_keep_blank_and_print_master_provenance(asset_context):
    asset_context.app.include_router(pod_router)
    owner = await seed_user(asset_context, email="pod-image-set-owner@example.test")
    async with client_for(asset_context, "pod-image-set-owner") as client:
        await login(client, owner.email)
        blank_response = await client.post(
            "/api/v1/pod/blanks", json={"category": "Blanket", "material": "Fleece"}
        )
        assert blank_response.status_code == 201, blank_response.text
        blank = blank_response.json()["blank"]
        blank_asset = (await upload(client, raster_bytes())).json()["asset"]
        print_asset = (await upload(client, raster_bytes(size=(15, 10)))).json()["asset"]
        generic_output = (await upload(client, raster_bytes(size=(16, 11)))).json()["asset"]
        main_output = (await upload(client, raster_bytes(size=(17, 12)))).json()["asset"]
        linked = await client.post(
            f"/api/v1/pod/blanks/{blank['id']}/references",
            json={"asset_id": blank_asset["id"], "reference_role": "primary"},
        )
        assert linked.status_code == 201, linked.text
        project_response = await client.post("/api/v1/pod/projects", json={"blank_id": blank["id"]})
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()["project"]

    async with asset_context.database.session_factory() as session:
        idea = PodProductIdea(
            id=uuid7(),
            project_id=uuid.UUID(project["id"]),
            generation_job_id=None,
            generation_batch_id=uuid7(),
            idea_name="Cozy Reading",
            target_audience="Readers",
            use_case="Living room",
            emotional_angle="Warm",
            design_theme="Books",
            visual_direction="Illustration",
            recommended_style="Vintage",
            composition_direction="Center",
            color_direction="Blue",
            core_elements=["book"],
            avoid_elements=["logos"],
            rationale="test",
            infringement_risk={"risk_level": "low", "warnings": []},
            status="adopted",
        )
        concept = PodDesignConcept(
            id=uuid7(),
            product_idea_id=idea.id,
            generation_job_id=None,
            design_name="Badge",
            visual_style="Vintage",
            composition="Central badge",
            layout="Centered",
            main_subject="Book",
            secondary_elements=["stars"],
            color_palette="Blue",
            typography_direction="No text",
            pattern_structure="Badge",
            print_method="DTG",
            recommended_print_area="Front",
            texture_direction="Flat",
            background_direction="Transparent",
            negative_elements=["logos"],
            design_prompt="Original flat book badge print with simple stars and no text.",
            status="adopted",
        )
        session.add(idea)
        await session.flush()
        session.add(concept)
        await session.flush()
        await session.commit()

    async with client_for(asset_context, "pod-image-set-owner") as client:
        await login(client, owner.email)
        print_job_response = await client.post(
            f"/api/v1/pod/design-concepts/{concept.id}/print-candidates/generate",
            headers={"Idempotency-Key": "pod-image-set-print-candidates"},
        )
        assert print_job_response.status_code == 200, print_job_response.text

    candidate = PodPrintCandidate(
        id=uuid7(),
        design_concept_id=concept.id,
        asset_id=uuid.UUID(print_asset["id"]),
        generation_job_id=uuid.UUID(print_job_response.json()["job"]["job_id"]),
        prompt_snapshot={},
        status="generated",
    )
    async with asset_context.database.session_factory() as session:
        session.add(candidate)
        await session.commit()

    async with client_for(asset_context, "pod-image-set-owner") as client:
        await login(client, owner.email)
        approved = await client.post(f"/api/v1/pod/print-candidates/{candidate.id}/approve-master")
        assert approved.status_code == 201, approved.text
        product = approved.json()["product"]

        strategy = await client.post(
            f"/api/v1/pod/products/{product['id']}/image-set/strategy/generate",
            headers={"Idempotency-Key": "pod-image-set-strategy"},
        )
        assert strategy.status_code == 200, strategy.text

    main_slot_id = uuid7()
    generic_slot_id = uuid7()
    image_set_id = uuid7()
    async with asset_context.database.session_factory() as session:
        strategy_job = await session.get(ImageJob, uuid.UUID(strategy.json()["job"]["job_id"]))
        assert strategy_job is not None
        assert strategy_job.operation_code == "pod.image.strategy.generate"
        assert strategy_job.source_asset_id is None
        assert strategy_job.parameters == {"product_id": product["id"]}

        image_set = PodImageSet(
            id=image_set_id,
            product_id=uuid.UUID(product["id"]),
            generation_job_id=None,
            version=1,
            strategy_snapshot={"rationale": "test", "slots": []},
            status="active",
        )
        main_slot = PodImageSlot(
            id=main_slot_id,
            image_set_id=image_set.id,
            code="product_main",
            title="商品主图",
            scope="product_specific",
            requires_print=True,
            scene_prompt="明亮白色棚拍",
            composition_prompt="完整产品正面居中",
            style_prompt="真实电商产品图",
            sort_order=0,
            prompt_snapshot={},
            status="planned",
        )
        generic_slot = PodImageSlot(
            id=generic_slot_id,
            image_set_id=image_set.id,
            code="gift_mood",
            title="礼物氛围",
            scope="generic",
            requires_print=False,
            scene_prompt="温暖送礼场景",
            composition_prompt="包装与丝带静物构图",
            style_prompt="明亮编辑风格",
            sort_order=1,
            prompt_snapshot={},
            status="planned",
        )
        session.add_all([image_set, main_slot, generic_slot])
        await session.commit()

    async with client_for(asset_context, "pod-image-set-owner") as client:
        await login(client, owner.email)
        bulk = await client.post(
            f"/api/v1/pod/products/{product['id']}/image-slots/bulk-generate",
            headers={"Idempotency-Key": "pod-image-set-bulk"},
            json={"slot_ids": [str(main_slot_id), str(generic_slot_id)]},
        )
        assert bulk.status_code == 200, bulk.text
        assert bulk.json()["submitted"] == 2

    async with asset_context.database.session_factory() as session:
        jobs = [
            await session.get(ImageJob, uuid.UUID(item["job_id"])) for item in bulk.json()["jobs"]
        ]
        assert all(job is not None for job in jobs)
        main_job = next(job for job in jobs if job.operation_code == "pod.visual.generate")
        generic_job = next(job for job in jobs if job.operation_code == "pod.visual.generic")
        assert main_job.source_asset_id == uuid.UUID(blank_asset["id"])
        assert main_job.parameters["reference_asset_ids"] == [blank_asset["id"], print_asset["id"]]
        assert main_job.parameters["blank_reference_asset_ids"] == [blank_asset["id"]]
        assert main_job.parameters["print_master_asset_id"] == print_asset["id"]
        assert main_job.parameters["image_slot_id"] == str(main_slot_id)
        assert generic_job.source_asset_id is None
        assert "reference_asset_ids" not in generic_job.parameters
        assert generic_job.parameters["image_slot_id"] == str(generic_slot_id)

        await attach_image_outputs(
            session,
            ClaimedJob(
                generic_job.id,
                owner.id,
                generic_job.operation_code,
                generic_job.source_asset_id,
                generic_job.parameters,
                1,
                480,
                30,
            ),
            [uuid.UUID(generic_output["id"])],
        )
        await session.commit()
        unchanged_product = await session.get(PodProduct, uuid.UUID(product["id"]))
        generic_slot = await session.get(PodImageSlot, generic_slot_id)
        assert unchanged_product is not None and unchanged_product.status == "drafting"
        assert generic_slot is not None and generic_slot.asset_id == uuid.UUID(generic_output["id"])

    async with client_for(asset_context, "pod-image-set-owner") as client:
        await login(client, owner.email)
        premature_review = await client.post(
            "/api/v1/pod/reviews",
            json={
                "target_type": "product",
                "target_id": product["id"],
                "gate": "G3",
                "decision": "approved",
            },
        )
        assert premature_review.status_code == 409, premature_review.text
        assert premature_review.json()["code"] == "POD_PRODUCT_MAIN_VISUAL_REQUIRED"

    async with asset_context.database.session_factory() as session:
        await attach_image_outputs(
            session,
            ClaimedJob(
                main_job.id,
                owner.id,
                main_job.operation_code,
                main_job.source_asset_id,
                main_job.parameters,
                1,
                480,
                30,
            ),
            [uuid.UUID(main_output["id"])],
        )
        await session.commit()
        completed_product = await session.get(PodProduct, uuid.UUID(product["id"]))
        completed_slot = await session.get(PodImageSlot, main_slot_id)
        assert completed_product is not None
        assert completed_product.status == "visual_ready"
        assert completed_product.primary_visual_asset_id == uuid.UUID(main_output["id"])
        assert completed_slot is not None and completed_slot.status == "generated"

    async with client_for(asset_context, "pod-image-set-owner") as client:
        await login(client, owner.email)
        unreviewed_main = await client.post(
            "/api/v1/pod/reviews",
            json={
                "target_type": "product",
                "target_id": product["id"],
                "gate": "G3",
                "decision": "approved",
            },
        )
        assert unreviewed_main.status_code == 409, unreviewed_main.text
        assert unreviewed_main.json()["code"] == "POD_PRODUCT_MAIN_REVIEW_REQUIRED"
        image_review = await client.post(
            "/api/v1/pod/reviews",
            json={
                "target_type": "image_slot",
                "target_id": str(main_slot_id),
                "gate": "G2",
                "decision": "approved",
            },
        )
        assert image_review.status_code == 201, image_review.text
        missing_copy = await client.post(
            "/api/v1/pod/reviews",
            json={
                "target_type": "product",
                "target_id": product["id"],
                "gate": "G3",
                "decision": "approved",
            },
        )
        assert missing_copy.status_code == 409, missing_copy.text
        assert missing_copy.json()["code"] == "POD_PRODUCT_COPY_REQUIRED"
        copy_job_response = await client.post(
            f"/api/v1/pod/products/{product['id']}/copy/generate",
            headers={"Idempotency-Key": "pod-product-copy"},
        )
        assert copy_job_response.status_code == 200, copy_job_response.text

    async with asset_context.database.session_factory() as session:
        copy_job = await session.get(ImageJob, uuid.UUID(copy_job_response.json()["job"]["job_id"]))
        assert copy_job is not None
        assert copy_job.operation_code == "pod.copy.generate"
        assert copy_job.source_asset_id is None
        assert copy_job.parameters == {"product_id": product["id"]}

    copy_executor = PodJobExecutor(
        asset_context.settings, asset_context.database, asset_context.storage
    )
    copy_executor._chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {
                    "product_title": "Cozy Reading Fleece Blanket for Book Lovers",
                    "product_description": "Bring a book-loving touch to a quiet reading corner with an original illustrated blanket design made for warm, relaxed moments at home.",
                    "selling_points": [
                        "Original book-inspired illustrated print",
                        "A warm visual accent for reading spaces",
                        "Gift-ready direction for readers and book lovers",
                    ],
                    "search_keywords": [
                        "book lover blanket",
                        "reading gift",
                        "cozy home decor",
                        "reader gift",
                        "bookish blanket",
                    ],
                    "content_warnings": ["Confirm available sizes before listing."],
                }
            ),
            provider_request_id="copy-request-1",
        )
    )
    await copy_executor(
        ClaimedJob(
            copy_job.id,
            owner.id,
            copy_job.operation_code,
            copy_job.source_asset_id,
            copy_job.parameters,
            1,
            240,
            30,
        )
    )

    async with client_for(asset_context, "pod-image-set-owner") as client:
        await login(client, owner.email)
        detail = await client.get(f"/api/v1/pod/projects/{project['id']}")
        assert detail.status_code == 200, detail.text
        copies = detail.json()["product_copies"]
        assert len(copies) == 1
        assert copies[0]["status"] == "active"
        assert copies[0]["version"] == 1
        assert copies[0]["generation_job_id"] == str(copy_job.id)
        assert copies[0]["prompt_snapshot"]["product_id"] == product["id"]
        edited = await client.patch(
            f"/api/v1/pod/product-copies/{copies[0]['id']}",
            json={"product_title": "Cozy Reading Fleece Blanket for Readers"},
        )
        assert edited.status_code == 200, edited.text
        assert (
            edited.json()["product_copy"]["product_title"]
            == "Cozy Reading Fleece Blanket for Readers"
        )
        product_review = await client.post(
            "/api/v1/pod/reviews",
            json={
                "target_type": "product",
                "target_id": product["id"],
                "gate": "G3",
                "decision": "approved",
            },
        )
        assert product_review.status_code == 201, product_review.text

    async with asset_context.database.session_factory() as session:
        approved_slot = await session.get(PodImageSlot, main_slot_id)
        approved_product = await session.get(PodProduct, uuid.UUID(product["id"]))
        approved_copy = await session.scalar(
            select(PodProductCopy).where(
                PodProductCopy.product_id == uuid.UUID(product["id"]),
                PodProductCopy.status == "active",
            )
        )
        assert approved_slot is not None and approved_slot.status == "approved"
        assert approved_product is not None and approved_product.status == "approved"
        assert approved_copy is not None
