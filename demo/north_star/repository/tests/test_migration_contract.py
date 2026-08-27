from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    ROOT / "orders_api" / "request_models.py",
    ROOT / "orders_api" / "api.py",
    ROOT / "orders_api" / "response_models.py",
)
BASELINE_REQUIREMENTS = "pydantic>=2.11,<3\n"
BASELINE_LOCK = (
    "# Compatibility baseline resolved from requirements.in.\npydantic==2.13.4\n"
)
FINAL_REQUIREMENTS = "pydantic==2.13.4\n"
FINAL_LOCK = (
    "# Native Pydantic v2 runtime resolved from requirements.in.\npydantic==2.13.4\n"
)


def test_dependency_declarations_are_a_complete_known_state() -> None:
    declarations = (
        (ROOT / "requirements.in").read_text(encoding="utf-8"),
        (ROOT / "requirements.lock").read_text(encoding="utf-8"),
    )
    assert declarations in {
        (BASELINE_REQUIREMENTS, BASELINE_LOCK),
        (FINAL_REQUIREMENTS, FINAL_LOCK),
    }

    if declarations == (FINAL_REQUIREMENTS, FINAL_LOCK):
        source = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE_PATHS)
        for legacy_api in ("pydantic.v1", ".parse_obj(", ".dict()"):
            assert legacy_api not in source
        assert "model_validate(" in source
        assert "model_dump(" in source
        assert "ConfigDict" in source
        assert "field_validator" in source
