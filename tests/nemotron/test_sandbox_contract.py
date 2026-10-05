"""The calls Graphene makes to ConTree fit the SDK version the `sandbox` extra pins. There is no live
sandbox in CI (Sandboxes are in beta, by request), so this is what CI can hold: every call sandbox.Contree
makes binds to the pinned SDK's own signatures, and its answers are read the way that SDK returns them."""

import inspect

import pytest

contree_sdk = pytest.importorskip("contree_sdk")

from contree_sdk import ContreeSync  # noqa: E402
from contree_sdk.sdk.managers.images import ImagesManagerSync  # noqa: E402
from contree_sdk.sdk.objects.image import ContreeImageSync  # noqa: E402

from graphene_map.nemotron import night, sandbox  # noqa: E402


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
    from fake_faults import Forbidding, persons_shell

    from graphene_map.nemotron import tokenfactory as tf

    persons_shell(monkeypatch)
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

    from fake_faults import persons_shell

    persons_shell(monkeypatch)
    monkeypatch.setattr(contree_sdk, "ContreeSync", lambda: Sdk())
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    assert sandbox.Contree().run("img-1", "sleep 999", {}, 5) == ("img-1", 124, sandbox.TIMED_OUT)


def test_whoami_says_before_any_leaf_whether_the_project_is_refused(monkeypatch):
    """sandbox.refused, which `graphene init` asks: whoami's 403 or a grant a leaf uses listed as not
    given is the refusal a leaf would meet, with ConTree's own reason; a 401 or no answer is not a sandbox
    that works either, and is said as `graphene key check` says it. None only when whoami grants what a
    leaf uses. Stubs only; nothing is sent."""
    from contree_sdk.sdk.exceptions import ApiStatusCodeError, ForbiddenError
    from fake_faults import Forbidding

    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    monkeypatch.setattr(contree_sdk, "ContreeSync", Forbidding)
    assert sandbox.refused() == REFUSED.format("its key lacks import, spawn there")
    monkeypatch.setattr(Forbidding, "GRANTS", {"import": True, "list": True, "spawn": True, "cancel": False})
    assert sandbox.refused() is None  # a grant no leaf uses

    def asking(error):
        def sdk(token=None):
            def whoami(refresh=False):
                raise error

            return type("Sdk", (), {"get_token_info": staticmethod(whoami)})()

        return sdk

    monkeypatch.setattr(contree_sdk, "ContreeSync", asking(ForbiddenError()))
    assert sandbox.refused() == REFUSED.format(sandbox.NO_GRANT)
    monkeypatch.setattr(contree_sdk, "ContreeSync", asking(ForbiddenError(error="not\nin  the beta")))
    assert sandbox.refused() == REFUSED.format(sandbox.NO_GRANT) + "; ConTree said: not in the beta"
    monkeypatch.setattr(contree_sdk, "ContreeSync", asking(ApiStatusCodeError(status=401, error="bad")))
    assert sandbox.refused() == "Sandboxes: the key was not accepted (401)"
    monkeypatch.setattr(contree_sdk, "ContreeSync", asking(OSError("offline")))
    assert sandbox.refused() == "Sandboxes: could not be reached (OSError: offline)"
    monkeypatch.setattr(Forbidding, "GRANTS", {"import": True, "list": True})  # spawn not named at all
    monkeypatch.setattr(contree_sdk, "ContreeSync", Forbidding)
    assert sandbox.refused() == REFUSED.format("its key lacks spawn there")


def test_a_leafs_refusal_carries_contrees_own_reason_without_the_key_or_the_project(monkeypatch):
    """A 403 on an operation is said with the server's reason (ForbiddenError.error), masked as every
    ConTree message is (``_unkeyed``), in one line. Stubs only; the key and the project are made up."""
    from contree_sdk.sdk.exceptions import ForbiddenError
    from fake_faults import Forbidding, persons_shell

    key, project = "Kq7" + "w" * 30, "proj-planted-0042"

    class Saying(Forbidding):
        def __init__(self, token=None):
            super().__init__(token)

            def refuse(*_, **__):
                raise ForbiddenError(error=f"project {project} is not\nin the beta (token {key})")

            self.images.oci = refuse

    persons_shell(monkeypatch)
    monkeypatch.setattr(contree_sdk, "ContreeSync", Saying)
    monkeypatch.setenv("NEBIUS_API_KEY", key)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", project)
    with pytest.raises(sandbox.Refused) as no:
        sandbox.Contree()
    assert str(no.value) == (REFUSED.format("its key lacks import, spawn there")
                             + "; ConTree said: project … is not in the beta (token …)")  # fmt: skip


def test_a_contree_error_whose_body_echoes_the_key_or_the_project_is_said_without_them(monkeypatch):
    """A gateway page that echoes the request's headers comes back from contree-sdk as its own error, whose
    message is the page. It is said as ConTree's error, with the key, the project id and anything shaped
    like a key taken out before it is cut, as Token Factory's is (tokenfactory._request): that message is
    a leaf's reason, the run's output, the pane and the log. The SDK's time limit still reaches _run as it
    is. Stubs only; the key and the project are made up."""
    from contree_sdk.sdk.exceptions import ApiStatusCodeError
    from fake_faults import persons_shell

    key, project = "Kq7" + "w" * 30, "proj-planted-0042"
    page = f"Bad Gateway. Request headers: Authorization: Bearer {key}; Project: {project}; " + "x" * 400

    class Image:
        def run(self, **_):
            raise ApiStatusCodeError(status=502, error=page)

    class Sdk:
        images = type("Images", (), {"oci": lambda self, ref: Image(), "use": lambda self, ref: Image()})()

    persons_shell(monkeypatch)
    monkeypatch.setattr(contree_sdk, "ContreeSync", lambda: Sdk())
    monkeypatch.setenv("NEBIUS_API_KEY", key)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", project)
    with pytest.raises(RuntimeError) as no:
        sandbox.Contree().run("img-1", "true", {}, 5)
    said = str(no.value)
    assert key not in said and project not in said and "Kq7" not in said, said
    assert said.startswith("ConTree answered with an error (ApiStatusCodeError): ") and "status=502" in said
    assert "Authorization: Bearer …" in said and len(said) <= 400


def test_the_sdks_token_life_warning_is_dropped_only_when_the_key_signs_the_client(caplog, monkeypatch):
    """Live on 2 Oct, `graphene init` printed contree-sdk's "Token expires in 0 hours", about a 300 s token
    minted per read, not the key. It is dropped for a client the key signs, and only that line: a `contree
    auth` profile's token may really expire, and the SDK's other warnings still come through."""
    import logging

    import contree_sdk

    from graphene_map.nemotron import sandbox

    monkeypatch.setattr(contree_sdk, "ContreeSync", lambda **_: object())
    log = logging.getLogger("contree_sdk.sdk.client._base")
    monkeypatch.setattr(log, "filters", [])

    def said():
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=log.name):
            for line in ("Token expires in 0 hours", "Token expires in 5 hours", "Timeout 900s exceeds"):
                log.warning(line)
        return [r.getMessage() for r in caplog.records]

    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    sandbox._client()  # a profile's client: nothing dropped
    assert said() == ["Token expires in 0 hours", "Token expires in 5 hours", "Timeout 900s exceeds"]
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-key")
    sandbox._client()
    assert said() == ["Token expires in 5 hours", "Timeout 900s exceeds"]
