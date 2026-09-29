"""The calls Graphene makes to ConTree fit the SDK version the `sandbox` extra pins. There is no live
sandbox in CI (Sandboxes are in beta, by request), so this is what CI can hold: every call sandbox.Contree
makes binds to the pinned SDK's own signatures, and its answers are read the way that SDK returns them."""

import inspect

import pytest

contree_sdk = pytest.importorskip("contree_sdk")

from contree_sdk import ContreeSync  # noqa: E402
from contree_sdk.sdk.managers.images import ImagesManagerSync  # noqa: E402
from contree_sdk.sdk.objects.image import ContreeImageSync  # noqa: E402

from graphene_map import night, sandbox  # noqa: E402


def test_every_call_binds_to_the_pinned_sdk():
    inspect.signature(ContreeSync.__init__).bind(None)  # credentials from the environment or the profile
    inspect.signature(ImagesManagerSync.oci).bind(None, sandbox.IMAGE)
    inspect.signature(ImagesManagerSync.use).bind(None, "an-image-uuid")
    inspect.signature(ContreeImageSync.run).bind(
        None, shell="true", files={"/tmp/graphene/x": b"data"}, timeout=10.0, disposable=False,
        truncate_output_at=sandbox.OUTPUT,
    )  # fmt: skip
    inspect.signature(ContreeImageSync.wait).bind(None)
    inspect.signature(ContreeImageSync.read).bind(None, "/work/app.py")


def test_its_answers_are_read_as_the_sdk_gives_them(monkeypatch):
    calls = []

    class Done:
        uuid, exit_code, stdout, stderr = "img-2", 3, "out\n", "err\n"

    class Image:
        def __init__(self, ref):
            self.ref = ref

        def run(self, **kw):
            calls.append(("run", self.ref, kw))
            return self

        def wait(self):
            return Done()

        def read(self, path):
            calls.append(("read", self.ref, path))
            return b"content"

    class Images:
        def oci(self, ref):
            calls.append(("oci", ref))
            return Image(ref)

        def use(self, ref):
            return Image(ref)

    class Sdk:
        images = Images()

    monkeypatch.setattr(contree_sdk, "ContreeSync", lambda: Sdk())
    for mark in night.MARKS:  # ConTree is the real service, stub or not: this is the person's shell
        monkeypatch.delenv(mark, raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    box = sandbox.Contree()
    assert box.run("img-1", "echo hi", {"/tmp/f": b"x"}, 60) == ("img-2", 3, "out\nerr\n")
    assert box.read("img-2", "/work/a.py") == b"content"
    assert calls[0] == ("oci", sandbox.IMAGE)
    assert calls[1][2] == {"shell": "echo hi", "files": {"/tmp/f": b"x"}, "timeout": 60, "disposable": False,
                           "truncate_output_at": sandbox.OUTPUT}  # fmt: skip
    assert box.ops == 3


def test_without_credentials_it_says_so_before_the_sdk_sends_a_variable_name_as_the_token(
    monkeypatch, tmp_path
):
    for name in ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CONTREE_HOME", str(tmp_path))  # no saved profile
    with pytest.raises(RuntimeError, match="ConTree needs a key .* and NEBIUS_PROJECT_ID"):
        sandbox.Contree()


REFUSED = ("Sandboxes refused this project (403): {}; request access at "
           "tokenfactory.nebius.com/sandboxes/about")  # fmt: skip


def test_a_project_sandboxes_refuse_is_said_with_what_its_key_lacks_and_what_to_do(monkeypatch):
    """Rung 1 met it live (2026-09-29): ConTree answered 403 to the project. The SDK's own ForbiddenError,
    from a stub (nothing is sent), becomes one refusal naming what the key lacks (whoami), and it is
    Token Factory's kind of refusal, which every caller says as it is. Without whoami's grants, the project
    id is the other suspect: ConTree answers a made-up key and project with a 403 too."""
    from fake_faults import Forbidding

    from graphene_map import tokenfactory as tf

    monkeypatch.setattr(contree_sdk, "ContreeSync", Forbidding)
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    with pytest.raises(sandbox.Refused) as no:
        sandbox.Contree()
    assert str(no.value) == REFUSED.format("its key lacks import, spawn there")
    assert isinstance(no.value, tf.Unreachable)

    class Blind(Forbidding):
        def __init__(self, token=None):
            super().__init__(token)
            self.get_token_info = lambda refresh=False: 1 / 0

    monkeypatch.setattr(contree_sdk, "ContreeSync", Blind)
    with pytest.raises(sandbox.Refused) as no:
        sandbox.Contree()
    assert str(no.value) == REFUSED.format(sandbox.NO_GRANT)
    assert "or NEBIUS_PROJECT_ID is not its project" in str(no.value)


def test_an_operation_past_its_time_is_the_commands_exit_124_as_in_docker(monkeypatch):
    """The SDK stops waiting at the time limit, cancels the operation and raises OperationTimedOutError:
    that is the box's own time limit, which Docker says as exit 124 on the image it was given, and
    Sandbox.run then brings nothing back (decision 73), instead of ending the leaf."""
    import uuid

    from contree_sdk.sdk.exceptions import OperationTimedOutError

    class Image:
        def run(self, **_):
            return self

        def wait(self):
            raise OperationTimedOutError(operation_uuid=uuid.uuid4())

    class Sdk:
        images = type("Images", (), {"oci": lambda self, ref: Image(), "use": lambda self, ref: Image()})()

    monkeypatch.setattr(contree_sdk, "ContreeSync", lambda: Sdk())
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    assert sandbox.Contree().run("img-1", "sleep 999", {}, 5) == ("img-1", 124, sandbox.TIMED_OUT)
