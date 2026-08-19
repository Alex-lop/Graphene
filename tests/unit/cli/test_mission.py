from __future__ import annotations

import json
import os
import stat
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

import graphene.cli.mission as mission_cli
from graphene.hashing import canonical_json_bytes
from graphene.cli.mission import (
    MissionCliError,
    _bind_start_request,
    _mission_runtime,
    _private_url_handoff,
    _start_identity,
    _state_root,
    build_parser,
    doctor,
    handle,
    initialize,
)
from graphene.orchestration.models import ProjectPolicy
from graphene.orchestration.scripted import DEFAULT_SCENARIO_PATH, load_scenario


ROOT = Path(__file__).resolve().parents[3]


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
        "GIT_AUTHOR_EMAIL": "fixture@graphene.invalid",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
        "GIT_COMMITTER_EMAIL": "fixture@graphene.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(("git", "init", "-q", "-b", "main"), cwd=repository, check=True)
    (repository / "README.md").write_text("# Fixture\n")
    subprocess.run(("git", "add", "--all", "--"), cwd=repository, check=True)
    subprocess.run(
        ("git", "commit", "-q", "-m", "base"),
        cwd=repository,
        env=environment,
        check=True,
    )
    return repository


@pytest.mark.parametrize(
    ("argv", "action"),
    [
        (["mission", "start", "--repo", ".", "--goal", "ship it"], "start"),
        (["mission", "status", "mission_1"], "status"),
        (["mission", "watch", "mission_1", "--snapshot"], "watch"),
        (["mission", "open", "mission_1"], "open"),
        (["mission", "pause", "mission_1"], "pause"),
        (["mission", "resume", "mission_1"], "resume"),
        (["mission", "cancel", "mission_1", "--confirm", "mission_1"], "cancel"),
        (["mission", "retry", "mission_1", "--task", "task_1"], "retry"),
        (["mission", "replan", "mission_1", "--reason", "scope changed"], "replan"),
        (["mission", "approve-plan", "mission_1", "--revision", "1"], "approve-plan"),
        (
            [
                "mission",
                "decide-gate",
                "mission_1",
                "--gate",
                "gate_1",
                "--decision",
                "redact",
            ],
            "decide-gate",
        ),
        (
            [
                "mission",
                "approve-result",
                "mission_1",
                "--candidate-sha",
                "a" * 64,
            ],
            "approve-result",
        ),
        (
            [
                "mission",
                "reject-result",
                "mission_1",
                "--candidate-sha",
                "a" * 64,
            ],
            "reject-result",
        ),
        (["mission", "replay", "taskmaster", "--no-open"], "replay"),
    ],
)
def test_parser_has_one_coherent_mission_command_family(argv, action) -> None:
    parsed = build_parser().parse_args(argv)

    assert parsed.command == "mission"
    assert parsed.mission_action == action


def test_init_writes_one_atomic_valid_deny_by_default_policy(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    path, policy = initialize(repository)
    original = path.read_bytes()

    assert path == repository / ".graphene/project.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert original.endswith(b"\n")
    assert ProjectPolicy.model_validate_json(original) == policy
    assert policy.network.mode == "deny"
    assert policy.allowed_read_globs == (".graphene/generated/**", "README.md")
    assert "**" not in policy.allowed_read_globs
    assert policy.allowed_write_globs == (".graphene/generated/**",)
    assert [item.template_id for item in policy.command_templates] == ["git-diff-check"]

    with pytest.raises(MissionCliError, match="already exists"):
        initialize(repository)
    assert path.read_bytes() == original
    assert not tuple(path.parent.glob(".project.json-*.tmp"))


def test_doctor_reports_modes_without_echoing_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    initialize(repository)
    canary = "doctor-secret-canary-8d0f"
    monkeypatch.setenv("GOOGLE_API_KEY", canary)

    report = doctor(repository)
    rendered = json.dumps(report, sort_keys=True)

    assert canary not in rendered
    assert report["policy"]["status"] == "usable"
    assert report["modes"]["mission-replay"]["usable"] is True
    assert report["modes"]["gemini-adk"] == {
        "usable": False,
        "configured": True,
        "credential_mode": "gemini_api",
        "proof": "credential hints only; credentials and connectivity not probed",
    }


def test_doctor_credential_hints_match_planner_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    initialize(repository)
    monkeypatch.setenv("GOOGLE_API_KEY", "first-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "second-secret")

    assert doctor(repository)["modes"]["gemini-adk"]["configured"] is False

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "fixture-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertex = doctor(repository)["modes"]["gemini-adk"]
    assert vertex["credential_mode"] == "vertex_ai"
    assert vertex["configured"] is True
    assert vertex["usable"] is False


def test_state_root_rejects_symlink_without_chmodding_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    link = tmp_path / "state-link"
    link.symlink_to(target, target_is_directory=True)
    before = stat.S_IMODE(target.stat().st_mode)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(link))

    with pytest.raises(MissionCliError, match="symlink"):
        _state_root()

    assert stat.S_IMODE(target.stat().st_mode) == before


def test_state_root_rejects_a_symlinked_parent_before_creating_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "linked-parent"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(link / "nested/state"))

    with pytest.raises(MissionCliError, match="symlink"):
        _state_root()

    assert not (target / "nested").exists()


def test_no_open_url_handoff_is_private_and_keeps_token_out_of_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(tmp_path / "state"))
    token = "private-token-canary"
    url = f"http://127.0.0.1:8123/mission-control/demo#token={token}"

    path = _private_url_handoff(url)

    assert path.parent == tmp_path / "state/handoffs"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8") == url + "\n"
    assert token not in str(path)
    path.unlink()


def test_taskmaster_fixture_is_loadable_and_forced_into_the_wheel() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert configuration["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ] == {"demo/taskmaster": "graphene/_taskmaster"}
    assert configuration["tool"]["hatch"]["build"]["targets"]["sdist"][
        "exclude"
    ] == ["/.claude", "/All_md_Files"]
    assert load_scenario(DEFAULT_SCENARIO_PATH).scenario_id == "taskmaster"


def test_doctor_rejects_policy_bound_to_an_old_head(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    initialize(repository)
    (repository / "README.md").write_text("# Changed\n", encoding="utf-8")
    subprocess.run(("git", "add", "README.md"), cwd=repository, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@graphene.invalid",
            "commit",
            "-q",
            "-m",
            "move head",
        ),
        cwd=repository,
        check=True,
    )

    report = doctor(repository)

    assert report["policy"] == {
        "status": "unavailable",
        "detail": "project policy base differs from repository HEAD",
    }
    assert report["modes"]["scripted-local"]["usable"] is False


def test_doctor_accepts_head_that_only_commits_the_generated_policy(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    initialize(repository)
    subprocess.run(("git", "add", ".graphene/project.json"), cwd=repository, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@graphene.invalid",
            "commit",
            "-q",
            "-m",
            "add graphene policy",
        ),
        cwd=repository,
        check=True,
    )

    assert doctor(repository)["policy"] == {
        "status": "usable",
        "detail": "valid project policy",
    }


def test_doctor_rejects_symlinked_policy_parent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    initialize(repository)
    policy_directory = repository / ".graphene"
    real_directory = tmp_path / "moved-policy"
    policy_directory.rename(real_directory)
    policy_directory.symlink_to(real_directory, target_is_directory=True)

    report = doctor(repository)

    assert report["policy"] == {
        "status": "unavailable",
        "detail": ".graphene must be a real directory",
    }


def test_doctor_rejects_policy_copied_from_another_repository(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = _repository(first_root)
    second = _repository(second_root)
    first_policy, _ = initialize(first)
    second_directory = second / ".graphene"
    second_directory.mkdir()
    (second_directory / "project.json").write_bytes(first_policy.read_bytes())

    report = doctor(second)

    assert report["policy"] == {
        "status": "unavailable",
        "detail": "project policy belongs to another repository",
    }


def test_live_start_fails_without_scripted_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    repository = _repository(tmp_path)
    initialize(repository)
    args = build_parser().parse_args(
        [
            "mission",
            "start",
            "--repo",
            str(repository),
            "--goal",
            "ship it",
            "--driver",
            "gemini-adk",
        ]
    )

    assert handle(args) == 1
    captured = capsys.readouterr()
    assert "no scripted fallback was used" in captured.err
    assert not tuple(state.rglob("attempt-evidence.sqlite3"))


def test_start_identity_binds_the_current_canonical_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    policy_path, policy = initialize(repository)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(tmp_path / "state"))
    default_args = build_parser().parse_args(
        [
            "mission",
            "start",
            "--repo",
            str(repository),
            "--goal",
            load_scenario().goal,
        ]
    )
    explicit_args = build_parser().parse_args(
        [
            "mission",
            "start",
            "--repo",
            str(repository),
            "--goal",
            load_scenario().goal,
            "--command-id",
            "command_start_policy_binding_001",
        ]
    )
    first_default = _start_identity(default_args)
    first_explicit = _start_identity(explicit_args)
    runtime = _mission_runtime(first_explicit[1])
    _bind_start_request(runtime, first_explicit[-1])

    changed = policy.model_copy(update={"retry_limit": policy.retry_limit + 1})
    policy_path.write_bytes(
        canonical_json_bytes(changed.model_dump(mode="json")) + b"\n"
    )
    second_default = _start_identity(default_args)
    second_explicit = _start_identity(explicit_args)

    assert second_default[0] != first_default[0]
    assert second_default[1] != first_default[1]
    assert second_explicit[0] == first_explicit[0]
    assert second_explicit[-1]["policy_sha256"] != first_explicit[-1]["policy_sha256"]
    with pytest.raises(MissionCliError, match="another request"):
        _bind_start_request(runtime, second_explicit[-1])


def test_gemini_start_replays_after_only_policy_file_was_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    _, policy = initialize(repository)
    subprocess.run(("git", "add", ".graphene/project.json"), cwd=repository, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@graphene.invalid",
            "commit",
            "-q",
            "-m",
            "add graphene policy",
        ),
        cwd=repository,
        check=True,
    )
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(tmp_path / "state"))
    args = build_parser().parse_args(
        [
            "mission",
            "start",
            "--repo",
            str(repository),
            "--goal",
            "Propose a bounded change.",
            "--success-criterion",
            "The plan remains within policy.",
            "--driver",
            "gemini-adk",
            "--command-id",
            "command_gemini_policy_commit_retry_001",
        ]
    )
    command_id, mission_id, _, _, loaded_policy, binding = _start_identity(args)
    assert loaded_policy == policy
    runtime = _mission_runtime(mission_id)
    _bind_start_request(runtime, binding)
    existing = SimpleNamespace(
        mission=SimpleNamespace(
            base_sha=policy.base_sha,
            creation_source="operator",
            goal=args.goal,
            policy_id=policy.policy_id,
            success_criteria=("The plan remains within policy.",),
        ),
        policy=SimpleNamespace(
            base_sha=policy.base_sha,
            policy_sha256=binding["policy_sha256"],
            repo_id=policy.repo_id,
            revision=policy.revision,
        ),
    )
    store = object()
    monkeypatch.setattr(mission_cli, "_store", lambda: store)
    monkeypatch.setattr(mission_cli, "_existing_mission_snapshot", lambda *_: existing)
    monkeypatch.setattr(
        mission_cli,
        "_existing_gemini_proposal_value",
        lambda actual_store, actual_snapshot: {
            "result_replayed": actual_store is store and actual_snapshot is existing
        },
    )

    assert mission_cli._start_bound(
        args,
        command_id=command_id,
        mission_id=mission_id,
        policy=policy,
        runtime=runtime,
        binding=binding,
    ) == {"result_replayed": True}


def test_start_request_binding_recovers_exact_interrupted_staging(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    staging = runtime / ".start-request.json.graphene-staging"
    staging.write_bytes(b"interrupted")
    staging.chmod(0o600)
    binding = {"command_id": "command_start_interrupted_001"}

    _bind_start_request(runtime, binding)
    assert (runtime / "start-request.json").read_bytes() == (
        canonical_json_bytes(binding) + b"\n"
    )
    assert not staging.exists()

    os.link(runtime / "start-request.json", staging)
    _bind_start_request(runtime, binding)
    assert not staging.exists()


def test_existing_mission_without_start_binding_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    initialize(repository)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(tmp_path / "state"))
    args = build_parser().parse_args(
        [
            "mission",
            "start",
            "--repo",
            str(repository),
            "--goal",
            load_scenario().goal,
            "--command-id",
            "command_start_missing_binding_001",
        ]
    )
    started = mission_cli._start(args)
    binding = _mission_runtime(str(started["mission_id"])) / "start-request.json"
    binding.unlink()

    with pytest.raises(MissionCliError, match="missing its durable start request"):
        mission_cli._start(args)

    assert not binding.exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["mission", "replan", "mission_retry", "--reason", "scope changed"],
        ["mission", "pause", "mission_retry"],
        ["mission", "resume", "mission_retry"],
        ["mission", "retry", "mission_retry", "--task", "task_retry"],
    ],
)
def test_default_mutation_ids_replay_after_committed_response_loss(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Result:
        def __init__(self, command_id: str) -> None:
            self.command_id = command_id

        def model_dump(self, *, mode: str) -> dict[str, str]:
            assert mode == "json"
            return {"command_id": self.command_id}

    class Store:
        def __init__(self) -> None:
            self.command_ids: list[str] = []

        def head(self, mission_id: str) -> None:
            raise AssertionError("default command identity must not read mutable head")

        def recover_dispatches(self, mission_id: str, *, recorded_at) -> tuple[()]:
            return ()

        def _commit(self, command_id: str) -> Result:
            self.command_ids.append(command_id)
            return Result(command_id)

        def request_replan(self, mission_id: str, command_id: str, **kwargs) -> Result:
            return self._commit(command_id)

        def pause(self, mission_id: str, command_id: str, **kwargs) -> Result:
            return self._commit(command_id)

        def resume(self, mission_id: str, command_id: str, **kwargs) -> Result:
            return self._commit(command_id)

        def retry_task(
            self, mission_id: str, task_id: str, command_id: str, **kwargs
        ) -> Result:
            return self._commit(command_id)

    store = Store()
    monkeypatch.setattr(mission_cli, "_store", lambda: store)
    args = build_parser().parse_args(argv)

    first = mission_cli._mutate(args)
    second = mission_cli._mutate(args)

    assert first == second
    assert store.command_ids == [store.command_ids[0], store.command_ids[0]]
