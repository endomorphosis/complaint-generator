#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
TEMP_ROOT="${ROOT_DIR}/statefiles"

mkdir -p "${TEMP_ROOT}"

if [[ $# -gt 0 ]]; then
	CONFIG_PATH="$1"
else
	CONFIG_PATH="${ROOT_DIR}/config.llm_router.json"
fi

export PATH="${ROOT_DIR}/.venv/bin:${PATH}"
export TMPDIR="${TEMP_ROOT}"
export COMPLAINT_GENERATOR_TMPDIR="${TEMP_ROOT}"
export COMPLAINT_GENERATOR_APPLICATION_TYPE="cli"
export COMPLAINT_GENERATOR_MEDIATOR_BACKENDS="llm-router-grok-4.7"
export COMPLAINT_GENERATOR_ROUTER_PROGRESS=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONWARNINGS="ignore::SyntaxWarning"

if [[ -x "${VENV_PYTHON}" ]]; then
	PYTHON="${VENV_PYTHON}"
else
	PYTHON="$(command -v python3)"
fi

exec "${PYTHON}" "${ROOT_DIR}/run.py" --config "${CONFIG_PATH}"
