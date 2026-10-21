#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
TEMP_ROOT="${ROOT_DIR}/statefiles"

mkdir -p "${TEMP_ROOT}"

export PATH="${ROOT_DIR}/.venv/bin:${PATH}"
export TMPDIR="${TEMP_ROOT}"
export COMPLAINT_GENERATOR_TMPDIR="${TEMP_ROOT}"
export COMPLAINT_GENERATOR_APPLICATION_TYPE="cli"
export COMPLAINT_GENERATOR_MEDIATOR_BACKENDS="llm-router-grok-4.7"
export COMPLAINT_GENERATOR_ROUTER_PROGRESS=1
export COMMON_CRAWL_AUTO_CLONE_SOURCE=0
export PYTHONDONTWRITEBYTECODE=1
export PYTHONWARNINGS="ignore::SyntaxWarning"

if [[ -x "${VENV_PYTHON}" ]]; then
	PYTHON="${VENV_PYTHON}"
else
	PYTHON="$(command -v python3)"
fi

cd "${ROOT_DIR}"
exec "${PYTHON}" -m applications.complaint_cli chat "$@"
