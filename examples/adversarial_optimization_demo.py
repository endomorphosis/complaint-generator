import argparse
import json
import logging
import os
import sys
from typing import Any, Dict

# Allow running via: python examples/adversarial_optimization_demo.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
	sys.path.insert(0, PROJECT_ROOT)

from adversarial_harness import AdversarialHarness, Optimizer
from backends import LLMRouterBackend
from mediator import Mediator


def _load_config(path: str) -> Dict[str, Any]:
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def _get_llm_router_backend_config(config: Dict[str, Any], backend_id: str | None) -> Dict[str, Any]:
	backend_ids = config.get("MEDIATOR", {}).get("backends", [])
	if not backend_id:
		backend_id = backend_ids[0] if backend_ids else None
	if not backend_id:
		raise ValueError("No backend id specified and config.MEDIATOR.backends is empty")

	backends = config.get("BACKENDS", [])
	backend_config = next((b for b in backends if b.get("id") == backend_id), None)
	if not backend_config:
		raise ValueError(f"Backend id not found in config.BACKENDS: {backend_id}")
	if backend_config.get("type") != "llm_router":
		raise ValueError(f"Backend {backend_id} must have type 'llm_router'")

	# Avoid passing config keys that aren't meaningful to the router.
	backend_kwargs = dict(backend_config)
	backend_kwargs.pop("type", None)
	return backend_kwargs


def main() -> int:
	parser = argparse.ArgumentParser(description="Run a small adversarial batch and print an optimization report")
	parser.add_argument(
		"--config",
		default="config.llm_router.json",
		help="Path to JSON config (default: config.llm_router.json)",
	)
	parser.add_argument(
		"--backend-id",
		default=None,
		help="Backend id to use (default: first entry in MEDIATOR.backends)",
	)
	parser.add_argument("--num-sessions", type=int, default=1)
	parser.add_argument("--max-turns", type=int, default=3)
	parser.add_argument("--max-parallel", type=int, default=1)
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO)

	config = _load_config(args.config)
	backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)

	def mediator_factory() -> Mediator:
		return Mediator(backends=[LLMRouterBackend(**backend_kwargs)])

	llm_backend_complainant = LLMRouterBackend(**backend_kwargs)
	llm_backend_critic = LLMRouterBackend(**backend_kwargs)

	harness = AdversarialHarness(
		llm_backend_complainant=llm_backend_complainant,
		llm_backend_critic=llm_backend_critic,
		mediator_factory=mediator_factory,
		max_parallel=args.max_parallel,
	)

	results = harness.run_batch(num_sessions=args.num_sessions, max_turns_per_session=args.max_turns)
	report = Optimizer().analyze(results)
	print(json.dumps(report.to_dict(), indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
