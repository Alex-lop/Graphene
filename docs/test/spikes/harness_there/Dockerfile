# Placement B's image: the leaf's sandbox base (python:3.12, as sandbox.IMAGE) with OpenCode headless.
# OpenCode 1.18.31 is the version kreuzhofer/nebius-token-factory-sandboxes-demos pins
# (examples/python/codingagent_demo/build_image.py), taken the same way: the platform binary from npm's
# registry, checked against the sha512 npm publishes for it. amd64 uses the -baseline build, as that repo
# does; arm64 (Docker Desktop on an Apple machine) uses opencode-linux-arm64.
#   docker build -t graphene-harness-there:opencode-1.18.31 docs/test/spikes/harness_there
FROM python:3.12
ARG TARGETARCH
ARG VERSION=1.18.31
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends ripgrep && rm -rf /var/lib/apt/lists/*
RUN python3 - <<'EOF'
import base64, hashlib, io, os, tarfile, urllib.request
arch = os.environ.get("TARGETARCH") or "amd64"
version = os.environ["VERSION"]
package, digest = {
    "amd64": ("opencode-linux-x64-baseline",
              "T/hyCHb7gSCuJzLDXs8YfEhjelUes2zkWFPTGEdBPqV/eKrKbEo9U1YdA/WvntjXv0I6k+blZEID54QIcF7Djw=="),
    "arm64": ("opencode-linux-arm64",
              "tLTZlOeWz4u48WQWg7PhKTn4gIXPHf7xaiWSHcmci1O3qKXEDLv/TaMzmqIuMChdwtflu2PSNIC00W+Hij/IkA=="),
}[arch]
raw = urllib.request.urlopen(f"https://registry.npmjs.org/{package}/-/{package}-{version}.tgz", timeout=120).read()
assert base64.b64encode(hashlib.sha512(raw).digest()).decode() == digest, "OpenCode archive integrity mismatch"
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
    data = archive.extractfile("package/bin/opencode").read()
with open("/usr/local/bin/opencode", "wb") as out:
    out.write(data)
os.chmod("/usr/local/bin/opencode", 0o755)
EOF
RUN test "$(opencode --version)" = "$VERSION"
