# syntax=docker/dockerfile:1
#
# Atlas OS — minimal container for the `atlas` CLI tools.
#
# There is no bundled dashboard application to serve (the public repo ships only
# a static, single-file ops dashboard at templates/ops-dashboard.html). This
# image instead packages the `atlas` command and the pipeline scripts so you can
# run the vault/RAG/git/health tooling in an isolated, reproducible environment.
#
# Build:
#   docker build -t atlas-os .
#   docker build -t atlas-os --build-arg EXTRAS=".[all]" .   # include trading + pdf
#
# Run (mount your vault, load your .env):
#   docker run --rm -it \
#     --env-file .env \
#     -v "$HOME/Documents/Obsidian/MyVault:/vault" \
#     -e VAULT_PATH=/vault \
#     atlas-os doctor
#
# A local LLM on the host (LM Studio / Ollama) is reachable from the container at
# host.docker.internal — set EMBED_HOST=host.docker.internal in your .env.

FROM python:3.11-slim AS base

# git is needed by `atlas commit` / `atlas changelog` (they shell out to git).
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached) using the project metadata only.
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY atlas_os ./atlas_os

# Which extras to install: "." = core only; ".[all]" = trading + pdf.
ARG EXTRAS="."
RUN pip install --no-cache-dir "${EXTRAS}"

# Copy the operational resources the CLI drives.
COPY scripts ./scripts
COPY schemas ./schemas
COPY templates ./templates
COPY skills ./skills

# Vaults are mounted here by default (see docker-compose.yml).
ENV VAULT_PATH=/vault
VOLUME ["/vault"]

# `atlas` is the entrypoint; the CMD is the default subcommand.
ENTRYPOINT ["atlas"]
CMD ["doctor"]
