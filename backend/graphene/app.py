from __future__ import annotations

import base64
import os
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .context import build_context_packet, load_catalog, profile_for_task
from .execution import (
    ExecutionError,
    GoogleAdkConfig,
    execute_deterministic_local,
    execute_google_adk,
    fixture_base_sha,
    run_fixture_tests,
)
from .execution.adapter import _git, _initialize_repository
from .graph import GraphBuildError, GraphBuilder
from .hashing import canonical_json_sha256, candidate_tree_sha256, sha256_hex
from .models import (
    CreateRunRequest,
    DemoResetRequest,
    ExecuteRunRequest,
    FeedbackRecord,
    FeedbackRequest,
    GoldenContract,
    GraphMvpContract,
    GraphNode,
    GraphNodeKind,
    GraphQuery,
    GraphResponse,
    HumanDecision,
    MemoryDecisionRequest,
    MemoryDecisionValue,
    MemoryRef,
    MemoryRevision,
    MemoryState,
    PromoteRunRequest,
    PromotionReceipt,
    ProofItem,
    ProofType,
    RelatedFile,
    RunRecord,
    RunState,
    TaskId,
)
from .store import (
    FirestoreStore,
    IdempotencyConflict,
    InMemoryStore,
    JsonFileStore,
    Store,
    StoreConflict,
)

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "demo/fixture"
FRONTEND_ROOT = ROOT / "frontend"
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
GRAPH_CONTRACT = GraphMvpContract.model_validate_json(
    (ROOT / "contracts/graph_mvp.json").read_text()
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{sha256_hex(chr(0).join(parts).encode())[:20]}"


def _key(operation: str, key: str) -> str:
    return f"{operation}_{sha256_hex(key.encode())[:32]}"


def _request_hash(request: object) -> str:
    return canonical_json_sha256(request.model_dump(mode="json"))


def _task(task_id: TaskId):
    return next(item for item in GOLDEN.tasks if item.task_id == task_id)


def _proof(
    run: RunRecord,
    proof_type: ProofType,
    payload: dict[str, object],
    *,
    evidence: tuple[str, ...] = (),
) -> ProofItem:
    sequence = len(run.proof) + 1
    return ProofItem(
        event_id=_stable_id("event", run.run_id, str(sequence), proof_type.value),
        run_id=run.run_id,
        sequence=sequence,
        evidence_event_ids=evidence,
        type=proof_type,
        occurred_at=_now(),
        payload=payload,
    )


def _replace(run: RunRecord, **updates: object) -> RunRecord:
    return RunRecord.model_validate({**run.model_dump(mode="json"), **updates})


def _records(store: Store, run_id: str) -> GraphBuilder:
    current = store.get_run(run_id)
    if current is None:
        raise HTTPException(404, "run not found")
    memories: list[MemoryRevision] = []
    memory = store.get_memory(GOLDEN.memory.memory_id, GOLDEN.memory.revision)
    packet = store.get_context_packet(run_id)
    packet_refs = {
        (item.memory_id, item.revision)
        for item in (() if packet is None else packet.approved_memories)
    }
    if memory is not None and (
        memory.evidence_run_id == run_id
        or MemoryRef(memory_id=memory.memory_id, revision=memory.revision)
        in current.injected_memories
        or (memory.memory_id, memory.revision) in packet_refs
    ):
        memories.append(memory)
    runs = [current]
    feedback: list[FeedbackRecord] = []
    for item in memories:
        if item.evidence_run_id != run_id:
            origin = store.get_run(item.evidence_run_id)
            if origin is None:
                raise GraphBuildError("memory origin run is missing")
            runs.append(origin)
        record = store.get_feedback(item.feedback_id)
        if record is None:
            raise GraphBuildError("memory feedback is missing")
        feedback.append(record)
    injection = store.get_injection_receipt(run_id)
    return GraphBuilder(
        GRAPH_CONTRACT,
        runs=runs,
        feedback=feedback,
        memories=memories,
        context_packets=(() if packet is None else (packet,)),
        injection_receipts=(() if injection is None else (injection,)),
    )


def _build_packet(store: Store, run: RunRecord):
    if run.task_id == TaskId.ADAPTED_WINDOW_SECONDS:
        memory = store.get_memory(GOLDEN.memory.memory_id, GOLDEN.memory.revision)
        if memory is None or memory.state != MemoryState.APPROVED:
            raise StoreConflict("adapted execution requires approved memory revision 1")
        source_run_id = memory.evidence_run_id
        memories = (memory,)
    else:
        source_run_id = run.run_id
        memories = ()
    source_graph = _records(store, source_run_id).build(source_run_id)
    selected = tuple(
        node.id
        for node in source_graph.nodes
        if node.kind in {GraphNodeKind.HUNK, GraphNodeKind.FEEDBACK, GraphNodeKind.MEMORY_REVISION}
    )
    return build_context_packet(
        contract=GRAPH_CONTRACT,
        task=_task(run.task_id),
        consumer_run_id=run.run_id,
        consumer_agent_profile_id=run.agent_profile_id,
        packet_id=_stable_id("ctx", run.run_id),
        base_sha=run.base_sha,
        tool_names=GOLDEN.tool_names,
        memories=memories,
        source_graph_hash=source_graph.graph_hash,
        related_files=(RelatedFile(path=_task(run.task_id).target_paths[0], reason="task target"),),
        selected_node_ids=selected,
    )


def _reconstruct_and_commit(candidate, execution_mode: str) -> tuple[str, dict[str, str]]:
    patch = base64.b64decode(candidate.canonical_patch_base64, validate=True)
    if sha256_hex(patch) != candidate.candidate_patch_sha256:
        raise StoreConflict("candidate patch bytes changed")
    with tempfile.TemporaryDirectory(prefix="graphene-promotion-") as temporary:
        root = Path(temporary) / "fixture"
        base_sha = _initialize_repository(GOLDEN, FIXTURE_ROOT, root)
        if base_sha != candidate.base_commit_sha:
            raise StoreConflict("candidate base is stale")
        applied = subprocess.run(
            ("git", "apply", "--binary", "--whitespace=nowarn", "-"),
            cwd=root,
            input=patch,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if applied.returncode:
            raise StoreConflict("candidate patch no longer applies")
        files = {path: (root / path).read_bytes() for path in candidate.changed_paths}
        if (
            candidate.candidate_tree_hash_version != "graphene.tree.v2"
            or candidate_tree_sha256(files) != candidate.candidate_tree_sha256
            or any(
                sha256_hex(files[change.path]) != change.after_sha256
                for change in candidate.file_changes
            )
        ):
            raise StoreConflict("reconstructed candidate hashes do not match")
        test = run_fixture_tests(root, GOLDEN.fixture)
        if test.timed_out or test.exit_code != 0:
            raise StoreConflict("reconstructed candidate failed tests")
        _git(root, "add", "--all")
        tree_sha = _git(root, "write-tree").decode().strip()
        commit_sha = _git(
            root,
            "commit-tree",
            tree_sha,
            "-p",
            base_sha,
            "-m",
            "Graphene approved candidate",
        ).decode().strip()
        return commit_sha, {
            "message": "Graphene approved candidate",
            "tree_sha": tree_sha,
            "execution_mode": execution_mode,
        }


def create_app(store: Store | None = None, demo_token: str | None = None) -> FastAPI:
    application = FastAPI(title="Graphene", version=__version__)
    application.state.store = store or InMemoryStore()
    application.state.demo_token = demo_token or os.getenv("GRAPHENE_DEMO_TOKEN")
    application.state.execution_mode = os.getenv(
        "GRAPHENE_EXECUTION_MODE", "deterministic-local"
    )
    if application.state.execution_mode not in {"deterministic-local", "google-adk"}:
        raise RuntimeError("GRAPHENE_EXECUTION_MODE must be deterministic-local or google-adk")

    async def handled_conflict(_, error: Exception):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    async def handled_graph(_, error: Exception):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    for error_type in (StoreConflict, IdempotencyConflict, ExecutionError):
        application.add_exception_handler(error_type, handled_conflict)
    application.add_exception_handler(GraphBuildError, handled_graph)

    @application.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)
        expected = application.state.demo_token
        if expected is None:
            return JSONResponse(
                status_code=503,
                content={"detail": "authentication is not configured"},
            )
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "invalid bearer token"})
        token = authorization.removeprefix("Bearer ")
        if not token or " " in token or not secrets.compare_digest(token, expected):
            return JSONResponse(status_code=401, content={"detail": "invalid bearer token"})
        return await call_next(request)

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        configured_adk = application.state.execution_mode == "google-adk"
        return {
            "status": "ok",
            "execution": (
                "google-adk-configured-unverified" if configured_adk else "deterministic-local"
            ),
            "gemini": "configured-unverified" if configured_adk else "unverified",
            "firestore": "unverified",
            "cloud_run": "unverified",
        }

    @application.post("/api/demo/reset")
    def reset(request: DemoResetRequest):
        application.state.store.reset_demo(request.idempotency_key, _request_hash(request))
        return {"status": "reset"}

    @application.get("/api/runs", response_model=tuple[RunRecord, ...])
    def list_runs():
        return application.state.store.list_runs()

    @application.post("/api/runs", response_model=RunRecord)
    def create_run(
        request: CreateRunRequest,
    ):
        task = _task(request.task_id)
        profile = profile_for_task(GRAPH_CONTRACT, request.task_id)
        binding = next(item for item in GRAPH_CONTRACT.task_profiles if item.task_id == request.task_id)
        run_id = _stable_id("run", request.idempotency_key, request.task_id.value)
        run = RunRecord(
            run_id=run_id,
            task_id=request.task_id,
            repo_id=task.repo_id,
            state=RunState.QUEUED,
            revision=0,
            agent_profile_id=profile.agent_profile_id,
            base_sha=fixture_base_sha(GOLDEN, FIXTURE_ROOT),
            allowed_paths=task.expected_changed_paths,
            allowed_tools=GOLDEN.tool_names,
            fresh_session=binding.fresh_session,
            session_id=_stable_id("session", run_id),
            created_at=_now(),
        )
        return application.state.store.create_run(
            run, request.idempotency_key, _request_hash(request)
        )

    @application.get("/api/runs/{run_id}", response_model=RunRecord)
    def get_run(run_id: str):
        run = application.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return run

    @application.post("/api/runs/{run_id}/execute", response_model=RunRecord)
    async def execute(
        run_id: str,
        request: ExecuteRunRequest,
    ):
        store = application.state.store
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        if run.state in {RunState.WAITING_FOR_PROMOTION, RunState.COMPLETED}:
            store.save_run(
                run,
                request.expected_run_revision,
                _key("waiting", request.idempotency_key),
                _request_hash(request),
            )
            return run
        if run.state != RunState.QUEUED or run.revision != request.expected_run_revision:
            raise StoreConflict("run is not executable at the requested revision")
        packet = _build_packet(store, run)
        store.create_context_packet(
            packet,
            _key("packet", request.idempotency_key),
            packet.packet_sha256,
        )
        running = _replace(
            run,
            state=RunState.RUNNING,
            revision=run.revision + 1,
            context_packet_id=packet.packet_id,
            context_packet_sha256=packet.packet_sha256,
            source_graph_revision=packet.source_graph_revision,
            source_graph_hash=packet.source_graph_hash,
            selected_node_ids=packet.selected_node_ids,
        )
        running = store.save_run(
            running,
            run.revision,
            _key("running", request.idempotency_key),
            _request_hash(request),
        )
        try:
            if application.state.execution_mode == "google-adk":
                result = await execute_google_adk(
                    config=GoogleAdkConfig(
                        mode="google-adk",
                        model_id=os.getenv("GRAPHENE_MODEL", GOLDEN.model.model_id),
                    ),
                    store=store,
                    golden_contract=GOLDEN,
                    graph_contract=GRAPH_CONTRACT,
                    packet=packet,
                    fixture_root=FIXTURE_ROOT,
                    session_id=running.session_id,
                    occurred_at=_now(),
                )
                model_id = result.metadata.returned_model_id
            else:
                result = execute_deterministic_local(
                    store=store,
                    golden_contract=GOLDEN,
                    graph_contract=GRAPH_CONTRACT,
                    packet=packet,
                    fixture_root=FIXTURE_ROOT,
                    session_id=running.session_id,
                    occurred_at=_now(),
                )
                model_id = None
        except Exception as error:
            injection = store.get_injection_receipt(run_id)
            failed_proof = _proof(
                running,
                ProofType.RUN_FAILED,
                {
                    "execution_mode": application.state.execution_mode,
                    "error": type(error).__name__,
                },
            )
            failed = _replace(
                running,
                state=RunState.FAILED,
                revision=running.revision + 1,
                injected_memories=(() if injection is None else injection.memory_revisions),
                proof=(failed_proof,),
                error=f"{type(error).__name__} during bounded execution",
            )
            store.save_run(
                failed,
                running.revision,
                _key("execution_failed", request.idempotency_key),
                _request_hash(request),
            )
            raise ExecutionError("bounded execution failed") from None
        waiting = _replace(
            running,
            state=RunState.WAITING_FOR_PROMOTION,
            revision=running.revision + 1,
            injected_memories=result.injection_receipt.memory_revisions,
            proof=result.proof,
            policy_checks=(result.policy_check,),
            candidate=result.candidate,
            model_id=model_id,
        )
        return store.save_run(
            waiting,
            running.revision,
            _key("waiting", request.idempotency_key),
            _request_hash(request),
        )

    @application.post("/api/runs/{run_id}/feedback", response_model=MemoryRevision)
    def feedback(
        run_id: str,
        request: FeedbackRequest,
    ):
        store = application.state.store
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        if run.revision != request.expected_run_revision or request.correction != GOLDEN.memory.correction:
            raise StoreConflict("feedback must bind the exact frozen origin revision and correction")
        detail = _records(store, run_id).node_detail(run_id, request.selected_hunk_id)
        if detail is None or detail.kind != GraphNodeKind.HUNK or detail.run_id != run_id:
            raise StoreConflict("selected hunk does not belong to the run")
        write_event = next(
            (
                item
                for item in run.proof
                if item.event_id == request.evidence_event_id
                and item.type == ProofType.FILE_WRITTEN
            ),
            None,
        )
        candidate = run.candidate
        hunk_path = detail.data.get("path")
        file_change = next(
            (
                item
                for item in (() if candidate is None else candidate.file_changes)
                if item.path == hunk_path
            ),
            None,
        )
        if (
            write_event is None
            or candidate is None
            or file_change is None
            or write_event.run_id != run.run_id
            or write_event.payload.get("path") != hunk_path
            or write_event.payload.get("before_sha256") != file_change.before_sha256
            or write_event.payload.get("after_sha256") != file_change.after_sha256
            or detail.data.get("before_sha256") != file_change.before_sha256
            or detail.data.get("after_sha256") != file_change.after_sha256
            or detail.data.get("candidate_patch_sha256")
            != candidate.candidate_patch_sha256
            or detail.data.get("candidate_revision") != candidate.candidate_revision
        ):
            raise StoreConflict("feedback evidence must be the matching observed write")
        scope = next(
            (item for item in GOLDEN.memory.scope_options if item.scope_id == request.scope_id),
            None,
        )
        if scope is None:
            raise StoreConflict("unknown server-owned scope option")
        if store.get_memory(GOLDEN.memory.memory_id, GOLDEN.memory.revision) is not None:
            raise StoreConflict("memory revision already exists")
        record = FeedbackRecord(
            feedback_id=_stable_id("feedback", run_id, request.idempotency_key),
            run_id=run_id,
            evidence_event_id=request.evidence_event_id,
            exact_correction=request.correction,
            selected_hunk_id=request.selected_hunk_id,
            selected_scope_id=request.scope_id,
            occurred_at=_now(),
        )
        record = store.create_feedback(
            record,
            _key("feedback", request.idempotency_key),
            _request_hash(request),
        )
        memory = MemoryRevision(
            memory_id=GOLDEN.memory.memory_id,
            revision=GOLDEN.memory.revision,
            state=MemoryState.PROPOSED,
            rule=GOLDEN.memory.rule,
            repo_id=GOLDEN.memory.repo_id,
            path_globs=scope.path_globs,
            task_tags=scope.task_tags,
            required_test_path=GOLDEN.memory.required_test_path,
            required_check=GOLDEN.memory.required_check,
            evidence_run_id=run_id,
            feedback_id=record.feedback_id,
        )
        return store.create_memory(
            memory,
            _key("memory", request.idempotency_key),
            canonical_json_sha256(memory.model_dump(mode="json")),
        )

    @application.post("/api/memories/{memory_id}/decision", response_model=MemoryRevision)
    def decide_memory(
        memory_id: str,
        request: MemoryDecisionRequest,
    ):
        store = application.state.store
        memory = store.get_memory(memory_id, request.expected_revision)
        if memory is None:
            raise HTTPException(404, "memory revision not found")
        decision = HumanDecision(
            decision_id=_stable_id("decision", memory_id, request.idempotency_key),
            value=request.decision,
            purpose="memory",
            bound_digest=canonical_json_sha256(
                memory.model_dump(mode="json", exclude={"state", "decision"})
            ),
            occurred_at=_now(),
        )
        return store.decide_memory(
            memory_id,
            request.expected_revision,
            decision,
            request.idempotency_key,
            _request_hash(request),
        )

    @application.post("/api/runs/{run_id}/promote", response_model=RunRecord)
    def promote(
        run_id: str,
        request: PromoteRunRequest,
    ):
        store = application.state.store
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        if run.state == RunState.COMPLETED:
            store.save_run(
                run,
                request.expected_run_revision,
                _key("completed", request.idempotency_key),
                _request_hash(request),
            )
            return run
        if run.state not in {RunState.WAITING_FOR_PROMOTION, RunState.PROMOTING}:
            raise StoreConflict("run is not waiting for promotion")
        candidate = run.candidate
        packet = store.get_context_packet(run_id)
        memory = store.get_memory(request.memory_id, request.memory_revision)
        bindings = (
            candidate is not None,
            packet is not None,
            run.revision == request.expected_run_revision or run.state == RunState.PROMOTING,
            candidate is not None and request.base_commit_sha == candidate.base_commit_sha,
            candidate is not None and request.candidate_patch_sha256 == candidate.candidate_patch_sha256,
            candidate is not None and request.candidate_tree_sha256 == candidate.candidate_tree_sha256,
            candidate is not None
            and request.candidate_tree_hash_version == candidate.candidate_tree_hash_version,
            candidate is not None and request.test_receipt_sha256 == candidate.test_receipt.receipt_sha256,
            packet is not None and request.context_packet_id == packet.packet_id,
            packet is not None and request.context_packet_sha256 == packet.packet_sha256,
            request.source_graph_revision == run.source_graph_revision,
            request.source_graph_hash == run.source_graph_hash,
            request.selected_node_ids == run.selected_node_ids,
            memory is not None and memory.state == MemoryState.APPROVED,
            MemoryRef(memory_id=request.memory_id, revision=request.memory_revision)
            in run.injected_memories,
        )
        if not all(bindings):
            raise StoreConflict("promotion request does not bind current authoritative state")
        if run.state == RunState.WAITING_FOR_PROMOTION:
            decision = HumanDecision(
                decision_id=_stable_id("promotion", run_id, request.idempotency_key),
                value=MemoryDecisionValue.APPROVE,
                purpose="promotion",
                bound_digest=candidate.candidate_patch_sha256,
                occurred_at=_now(),
            )
            approved = _proof(
                run,
                ProofType.PROMOTION_APPROVED,
                {
                    "candidate_patch_sha256": candidate.candidate_patch_sha256,
                    "context_packet_sha256": packet.packet_sha256,
                    "human_decision_id": decision.decision_id,
                },
                evidence=(run.proof[-1].event_id,),
            )
            run = _replace(
                run,
                state=RunState.PROMOTING,
                revision=run.revision + 1,
                proof=(*run.proof, approved),
                promotion_decision=decision,
            )
            run = store.save_run(
                run,
                request.expected_run_revision,
                _key("promoting", request.idempotency_key),
                _request_hash(request),
            )
        try:
            execution_mode = (
                "google-adk"
                if any(
                    item.payload.get("execution_mode") == "google-adk"
                    for item in run.proof
                )
                else "deterministic-local"
            )
            commit_sha, commit_metadata = _reconstruct_and_commit(
                candidate, execution_mode
            )
        except Exception as error:
            failed = _replace(
                run,
                state=RunState.FAILED,
                revision=run.revision + 1,
                error=str(error)[:1024] or type(error).__name__,
            )
            store.save_run(
                failed,
                run.revision,
                _key("promotion_failed", request.idempotency_key),
                _request_hash(request),
            )
            raise
        committed = _proof(
            run,
            ProofType.CANDIDATE_COMMITTED,
            {"commit_sha": commit_sha, **commit_metadata},
            evidence=(run.proof[-1].event_id,),
        )
        receipt = PromotionReceipt(
            run_id=run_id,
            base_commit_sha=candidate.base_commit_sha,
            candidate_patch_sha256=candidate.candidate_patch_sha256,
            candidate_tree_sha256=candidate.candidate_tree_sha256,
            candidate_tree_hash_version=candidate.candidate_tree_hash_version,
            memory_id=request.memory_id,
            memory_revision=request.memory_revision,
            context_packet_id=packet.packet_id,
            context_packet_sha256=packet.packet_sha256,
            source_graph_revision=run.source_graph_revision,
            source_graph_hash=run.source_graph_hash,
            selected_node_ids=run.selected_node_ids,
            test_receipt_sha256=candidate.test_receipt.receipt_sha256,
            human_decision_id=run.promotion_decision.decision_id,
            expected_run_revision=request.expected_run_revision,
            commit_sha=commit_sha,
            commit_metadata=commit_metadata,
        )
        completed = _replace(
            run,
            state=RunState.COMPLETED,
            revision=run.revision + 1,
            proof=(*run.proof, committed),
            promotion_receipt=receipt,
        )
        return store.save_run(
            completed,
            run.revision,
            _key("completed", request.idempotency_key),
            _request_hash(request),
        )

    @application.get("/api/runs/{run_id}/proof", response_model=tuple[ProofItem, ...])
    def proof(run_id: str):
        run = application.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return run.proof

    @application.get("/api/runs/{run_id}/graph", response_model=GraphResponse)
    def graph(
        run_id: str,
        depth: int = Query(default=1, ge=0, le=2),
        path_prefix: str | None = None,
    ):
        return _records(application.state.store, run_id).build(
            run_id, GraphQuery(depth=depth, path_prefix=path_prefix)
        )

    @application.get("/api/runs/{run_id}/graph/nodes/{node_id}", response_model=GraphNode)
    def graph_node(run_id: str, node_id: str):
        node = _records(application.state.store, run_id).node_detail(run_id, node_id)
        if node is None:
            raise HTTPException(404, "graph node not found")
        return node

    @application.get("/api/runs/{run_id}/context-packet")
    def context_packet(run_id: str):
        packet = application.state.store.get_context_packet(run_id)
        if packet is None:
            raise HTTPException(404, "context packet not found")
        return packet

    @application.get("/api/agent-catalog")
    def agent_catalog():
        return load_catalog(GRAPH_CONTRACT)

    if (FRONTEND_ROOT / "index.html").exists():
        application.mount(
            "/", StaticFiles(directory=FRONTEND_ROOT, html=True), name="frontend"
        )

    return application


def _default_store() -> Store:
    backend = os.getenv("GRAPHENE_STORE_BACKEND", "memory")
    if backend == "firestore":
        return FirestoreStore(namespace=os.getenv("GRAPHENE_NAMESPACE", "hackathon"))
    if backend == "json":
        path = os.getenv("GRAPHENE_STORE_PATH")
        if not path:
            raise RuntimeError("GRAPHENE_STORE_PATH is required for the json store")
        return JsonFileStore(path)
    if backend == "memory":
        return InMemoryStore()
    raise RuntimeError(f"unknown GRAPHENE_STORE_BACKEND: {backend}")


app = create_app(_default_store())
