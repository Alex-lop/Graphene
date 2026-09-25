"""The calls Graphene makes to ConTree fit the SDK version the `sandbox` extra pins. There is no live
sandbox in CI (Sandboxes are in beta, by request), so this is what CI can hold: every call sandbox.Contree
makes binds to the pinned SDK's own signatures, and its answers are read the way that SDK returns them."""

import inspect

import pytest

contree_sdk = pytest.importorskip("contree_sdk")

from contree_sdk import ContreeSync  # noqa: E402
from contree_sdk.sdk.managers.images import ImagesManagerSync  # noqa: E402
from contree_sdk.sdk.objects.image import ContreeImageSync  # noqa: E402

from graphene_map import sandbox  # noqa: E402


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
    box = sandbox.Contree()
    assert box.run("img-1", "echo hi", {"/tmp/f": b"x"}, 60) == ("img-2", 3, "out\nerr\n")
    assert box.read("img-2", "/work/a.py") == b"content"
    assert calls[0] == ("oci", sandbox.IMAGE)
    assert calls[1][2] == {"shell": "echo hi", "files": {"/tmp/f": b"x"}, "timeout": 60, "disposable": False,
                           "truncate_output_at": sandbox.OUTPUT}  # fmt: skip
    assert box.ops == 3
