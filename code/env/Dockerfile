# syntax=docker/dockerfile:1
# Research image for the DGX Sparks (arm64). The same env/setup_env.sh builds the identical
# environment on RunPod pods (x86-64), where we cannot push a custom image; see runbook §1.2.
#
#   docker build -f env/Dockerfile --build-arg STACK=main -t esj-research:main --label research=esj .
#
# Build context: the code/ directory. The image holds the venv and ComfyUI; models and run
# data are bind-mounted from the host research folder (never from production model folders).
FROM ubuntu:24.04
ARG STACK=main
ENV ESJ_HOME=/opt/esj DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/esj/code
COPY pyproject.toml README.md ./
COPY env ./env
COPY tools ./tools
COPY trajver ./trajver
COPY comfyui_trajectory ./comfyui_trajectory
# the uv download cache is a BuildKit cache mount, so a failed build keeps what it downloaded
RUN --mount=type=cache,target=/opt/esj/.uv-cache,id=esj-uv bash env/setup_env.sh ${STACK}
ENV TRAJVER_COMFYUI=/opt/esj/ComfyUI PATH=/opt/esj/venv-${STACK}/bin:$PATH
LABEL research=esj
