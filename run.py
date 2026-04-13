import argparse
import json
import os
import tempfile
import warnings
from pathlib import Path


warnings.filterwarnings(
	"ignore",
	category=SyntaxWarning,
	module=r"pydub(\..*)?$",
)
warnings.filterwarnings(
	"ignore",
	category=RuntimeWarning,
	module=r"pydub(\..*)?$",
	message=r"Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work",
)
warnings.filterwarnings(
	"ignore",
	category=SyntaxWarning,
	module=r"newspaper(\..*)?$",
)


def _configure_runtime_tempdir_early() -> str:
	root = Path(__file__).resolve().parent
	candidates = [
		Path(os.environ.get("COMPLAINT_GENERATOR_TMPDIR", "")).expanduser() if os.environ.get("COMPLAINT_GENERATOR_TMPDIR") else None,
		root / "statefiles",
		root / "tmp",
	]
	for candidate in candidates:
		if candidate is None:
			continue
		try:
			candidate.mkdir(parents=True, exist_ok=True)
			probe = candidate / ".tmp-write-probe"
			probe.write_text("ok")
			probe.unlink()
			resolved = str(candidate)
			os.environ["TMPDIR"] = resolved
			os.environ.setdefault("TEMP", resolved)
			os.environ.setdefault("TMP", resolved)
			tempfile.tempdir = resolved
			return resolved
		except Exception:
			continue
	return ""


_configure_runtime_tempdir_early()

from applications import normalize_application_types, start_configured_applications
from backends import LLMRouterBackend, WorkstationBackendDatabases, WorkstationBackendModels
from lib.log import init_logging, make_logger
from mediator import Mediator


def _normalize_cli_mediator_backends(config_backends, config_mediator, config_application):
	application_types = normalize_application_types(config_application.get('type', []))
	if 'cli' not in application_types:
		return
	if os.environ.get('COMPLAINT_GENERATOR_USE_LEGACY_CLI_BACKEND', '').strip().lower() in {'1', 'true', 'yes'}:
		return
	backend_ids = list(config_mediator.get('backends') or [])
	if backend_ids != ['llm-router']:
		return
	legacy_backend = next((conf for conf in config_backends if conf.get('id') == 'llm-router'), None)
	preferred_backend = next((conf for conf in config_backends if conf.get('id') == 'llm-router-codex'), None)
	if not isinstance(legacy_backend, dict) or not isinstance(preferred_backend, dict):
		return
	if str(legacy_backend.get('type') or '').strip() != 'llm_router':
		return
	if str(legacy_backend.get('provider') or '').strip() != 'codex':
		return
	if str(preferred_backend.get('type') or '').strip() != 'llm_router':
		return
	if str(preferred_backend.get('provider') or '').strip() != 'codex_cli':
		return
	config_mediator['backends'] = ['llm-router-codex']


def _apply_runtime_config_overrides(config_mediator, config_application):
	override_application_type = os.environ.get('COMPLAINT_GENERATOR_APPLICATION_TYPE', '').strip()
	if override_application_type:
		config_application['type'] = [item.strip() for item in override_application_type.split(',') if item.strip()]
	override_backends = os.environ.get('COMPLAINT_GENERATOR_MEDIATOR_BACKENDS', '').strip()
	if override_backends:
		config_mediator['backends'] = [item.strip() for item in override_backends.split(',') if item.strip()]


def _configure_runtime_tempdir() -> str:
	return _configure_runtime_tempdir_early()


def main(argv=None):
	_configure_runtime_tempdir()
	parser = argparse.ArgumentParser(description='Complaint Generator')
	parser.add_argument(
		'--config',
		default=os.environ.get('COMPLAINT_GENERATOR_CONFIG', 'config.llm_router.json'),
		help='Path to configuration JSON (default: config.llm_router.json)'
	)
	args = parser.parse_args(argv)

	if not os.path.exists(args.config):
		raise FileNotFoundError(f'Config not found: {args.config}')

	with open(args.config) as f:
		config = json.load(f)
		config_backends = config['BACKENDS']
		config_mediator = config['MEDIATOR']
		config_application = config['APPLICATION']
		config_log = config['LOG']
		_apply_runtime_config_overrides(config_mediator, config_application)
		_normalize_cli_mediator_backends(config_backends, config_mediator, config_application)

	init_logging(level=config_log['level'])
	log = make_logger('main')

	log.info('log level is set to: %s' % config_log['level'])
	log.info('config is loaded successfully')
	application_types = normalize_application_types(config_application.get('type', []))
	all_autopatch = application_types and all(app_type == 'adversarial-autopatch' for app_type in application_types)
	autopatch_demo_backend = bool(config_application.get('demo_backend', False))
	requires_live_backends = not (all_autopatch and autopatch_demo_backend)

	if requires_live_backends:
		log.info('creating mediator with backends: %s' % ', '.join(config_mediator['backends']))
	else:
		log.info('launching adversarial-autopatch without live mediator backends')

	backends = []

	if requires_live_backends:
		for backend_id in config_mediator['backends']:
			backend_config = next((conf for conf in config_backends if conf['id'] == backend_id), None)

			if not backend_config:
				log.error('missing backend configuration "%s" - cannot continue' % backend_id)
				return -1

			if backend_config['type'] == 'openai':
				log.warning('backend type "openai" is deprecated; routing via llm_router instead')
				cfg = dict(backend_config)
				model = cfg.get('model') or cfg.get('engine')
				cfg.pop('api_key', None)
				cfg.pop('engine', None)
				backend = LLMRouterBackend(id=cfg.get('id', backend_id), provider=cfg.get('provider', 'openai'), model=model, **{k: v for k, v in cfg.items() if k not in ('id', 'type', 'provider', 'model')})
			elif backend_config['type'] == 'huggingface':
				log.warning('backend type "huggingface" is deprecated; routing via llm_router instead')
				cfg = dict(backend_config)
				model = cfg.get('model') or cfg.get('engine')
				cfg.pop('api_key', None)
				cfg.pop('engine', None)
				backend = LLMRouterBackend(id=cfg.get('id', backend_id), provider=cfg.get('provider', 'huggingface_router'), model=model, **{k: v for k, v in cfg.items() if k not in ('id', 'type', 'provider', 'model')})
			elif backend_config['type'] == 'workstation':
				backendDatabases = WorkstationBackendDatabases(**backend_config)
				backendModels = WorkstationBackendModels(**backend_config)
				backend = backendModels
			elif backend_config['type'] == 'llm_router':
				try:
					backend = LLMRouterBackend(**backend_config)
				except ImportError:
					if all_autopatch:
						log.error(
							'live adversarial-autopatch requires llm_router; initialize ipfs_datasets_py submodules or use config.adversarial_autopatch_demo.json'
						)
					raise
			else:
				log.error('unknown backend type: %s' % backend_config['type'])
				return -1
			backends.append(backend)

	mediator = Mediator(backends=backends) if requires_live_backends else object()

	try:
		start_configured_applications(mediator, config_application)
	except ValueError as exc:
		log.error(str(exc))
		return -1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
	
