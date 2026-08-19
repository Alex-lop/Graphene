FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a

RUN python -m pip install --no-cache-dir pytest==9.1.1

ENV PATH=/usr/local/bin:/usr/bin:/bin \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

USER 65532:65532
WORKDIR /workspace
