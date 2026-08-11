import pytest

from reviewlatch.app import app
from reviewlatch.models import GoldenContract


@pytest.mark.xfail(strict=True, reason="Phase 1 must implement the frozen local vertical slice")
def test_all_golden_api_routes_exist():
    contract = GoldenContract.model_validate_json(
        open("contracts/golden_path.json", encoding="utf-8").read()
    )
    actual = {(method, route.path) for route in app.routes for method in route.methods or ()}
    expected = {(endpoint.method, endpoint.path) for endpoint in contract.api}
    assert expected <= actual
