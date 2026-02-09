import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
import importlib.util
from typing import Any, Dict

# Allow running via: python examples/batch_sgd_cycle.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
	sys.path.insert(0, PROJECT_ROOT)

from adversarial_harness import AdversarialHarness, Optimizer
from backends import LLMRouterBackend
from mediator import Mediator


def _load_session_sgd_report_module():
	path = os.path.join(PROJECT_ROOT, "examples", "session_sgd_report.py")
	spec = importlib.util.spec_from_file_location("session_sgd_report", path)
	if not spec or not spec.loader:
		raise RuntimeError(f"Unable to load session_sgd_report.py from {path}")
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)  # type: ignore[attr-defined]
	return module


_sgd = _load_session_sgd_report_module()
_find_session_json_files = _sgd._find_session_json_files
_summarize_session = _sgd._summarize_session
_write_report = _sgd._write_report


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

	backend_kwargs = dict(backend_config)
	backend_kwargs.pop("type", None)
	return backend_kwargs


def main() -> int:
	parser = argparse.ArgumentParser(description="Run an adversarial batch, persist sessions, then generate an SGD report")
	parser.add_argument("--config", default="config.llm_router.json")
	parser.add_argument("--backend-id", default=None, help="Backend id from config.BACKENDS")
	parser.add_argument("--state-dir", default="statefiles", help="Directory to write session_* artifacts")
	parser.add_argument("--run-id", default=None, help="Optional run id; creates <state-dir>/_runs/<run-id>")
	parser.add_argument("--num-sessions", type=int, default=5)
	parser.add_argument("--max-turns", type=int, default=8)
	parser.add_argument("--max-parallel", type=int, default=2)
	parser.add_argument(
		"--personalities",
		default=None,
		help="Comma-separated complainant personalities to cycle through (e.g. cooperative,defensive,vague).",
	)
	parser.add_argument("--retry-max-attempts", type=int, default=1)
	parser.add_argument("--retry-backoff-base-s", type=float, default=0.5)
	parser.add_argument("--retry-backoff-max-s", type=float, default=20.0)
	parser.add_argument("--retry-jitter-s", type=float, default=0.1)
	parser.add_argument("--denoiser-exploration-enabled", action="store_true")
	parser.add_argument("--denoiser-momentum-enabled", action="store_true")
	parser.add_argument("--denoiser-exploration-epsilon", type=float, default=None)
	parser.add_argument("--denoiser-exploration-top-k", type=int, default=None)
	parser.add_argument("--denoiser-momentum-beta", type=float, default=None)
	parser.add_argument("--denoiser-seed", type=int, default=None)
	args = parser.parse_args()

	personalities = None
	if args.personalities:
		personalities = [p.strip() for p in args.personalities.split(",") if p.strip()]

	if args.denoiser_exploration_enabled:
		os.environ["CG_DENOISER_EXPLORATION_ENABLED"] = "1"
	if args.denoiser_momentum_enabled:
		os.environ["CG_DENOISER_MOMENTUM_ENABLED"] = "1"
	if args.denoiser_exploration_epsilon is not None:
		os.environ["CG_DENOISER_EXPLORATION_EPSILON"] = str(args.denoiser_exploration_epsilon)
	if args.denoiser_exploration_top_k is not None:
		os.environ["CG_DENOISER_EXPLORATION_TOP_K"] = str(args.denoiser_exploration_top_k)
	if args.denoiser_momentum_beta is not None:
		os.environ["CG_DENOISER_MOMENTUM_BETA"] = str(args.denoiser_momentum_beta)
	if args.denoiser_seed is not None:
		os.environ["CG_DENOISER_SEED"] = str(args.denoiser_seed)

	logging.basicConfig(level=logging.INFO)

	config = _load_config(args.config)
	backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)

	run_id = args.run_id or f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
	run_dir = os.path.join(args.state_dir, "_runs", run_id)
	os.makedirs(run_dir, exist_ok=True)

	logging.info("Run directory: %s", os.path.abspath(run_dir))

	# Retry/backoff settings are passed through as kwargs.
	backend_kwargs = {
		**backend_kwargs,
		"retry_max_attempts": args.retry_max_attempts,
		"retry_backoff_base_s": args.retry_backoff_base_s,
		"retry_backoff_max_s": args.retry_backoff_max_s,
		"retry_jitter_s": args.retry_jitter_s,
	}

	llm_backend_complainant = LLMRouterBackend(**backend_kwargs)
	llm_backend_critic = LLMRouterBackend(**backend_kwargs)

	def mediator_factory(**kwargs) -> Mediator:
		return Mediator(backends=[LLMRouterBackend(**backend_kwargs)], **kwargs)

	harness = AdversarialHarness(
		llm_backend_complainant=llm_backend_complainant,
		llm_backend_critic=llm_backend_critic,
		mediator_factory=mediator_factory,
		max_parallel=args.max_parallel,
		session_state_dir=run_dir,
	)

	start = time.time()
	results = harness.run_batch(
		num_sessions=args.num_sessions,
		max_turns_per_session=args.max_turns,
		personalities=personalities,
	)
	duration_s = time.time() - start

	opt_report = Optimizer().analyze(results)
	optimizer_dict = opt_report.to_dict()

	# SGD report over persisted sessions
	session_json_files = _find_session_json_files(run_dir)
	summaries = [_summarize_session(p) for p in session_json_files]
	sgd_report_path = _write_report(run_dir, os.path.join(run_dir, "_reports"), summaries)

	sgd_report = {}
	try:
		with open(sgd_report_path, "r", encoding="utf-8") as f:
			sgd_report = json.load(f)
	except Exception:
		sgd_report = {}

	graphs_health = None
	try:
		graphs = sgd_report.get("graphs") if isinstance(sgd_report, dict) else None
		if isinstance(graphs, dict):
			kg = graphs.get("knowledge_graph") if isinstance(graphs.get("knowledge_graph"), dict) else {}
			dg = graphs.get("dependency_graph") if isinstance(graphs.get("dependency_graph"), dict) else {}
			graphs_health = (
				f"kg_files={kg.get('sessions_with_file')}/{sgd_report.get('num_sessions')} "
				f"kg_empty={kg.get('sessions_empty')}/{kg.get('sessions_with_file')} "
				f"dg_files={dg.get('sessions_with_file')}/{sgd_report.get('num_sessions')} "
				f"dg_empty={dg.get('sessions_empty')}/{dg.get('sessions_with_file')}"
			)
	except Exception:
		graphs_health = None

	graphs_dynamics_health = None
	try:
		def _fmt_delta(value: Any) -> str:
			if isinstance(value, (int, float)):
				return f"{value:+.2f}"
			return "n/a"

		kg_ent_d = optimizer_dict.get("kg_avg_entities_delta_per_iter")
		kg_rel_d = optimizer_dict.get("kg_avg_relationships_delta_per_iter")
		kg_gaps_d = optimizer_dict.get("kg_avg_gaps_delta_per_iter")
		kg_gaps_nondec = optimizer_dict.get("kg_sessions_gaps_not_reducing")

		if any(isinstance(v, (int, float)) for v in (kg_ent_d, kg_rel_d, kg_gaps_d)) or isinstance(kg_gaps_nondec, int):
			denom = args.num_sessions if isinstance(args.num_sessions, int) and args.num_sessions > 0 else "n/a"
			nondec_s = kg_gaps_nondec if isinstance(kg_gaps_nondec, int) else "n/a"
			graphs_dynamics_health = (
				f"kg_entΔ={_fmt_delta(kg_ent_d)} "
				f"kg_relΔ={_fmt_delta(kg_rel_d)} "
				f"kg_gapsΔ={_fmt_delta(kg_gaps_d)} "
				f"kg_gaps_nondec={nondec_s}/{denom}"
			)
	except Exception:
		graphs_dynamics_health = None

	payload = {
		"run_id": run_id,
		"run_dir": os.path.abspath(run_dir),
		"config": {
			"backend_id": args.backend_id,
			"num_sessions": args.num_sessions,
			"max_turns": args.max_turns,
			"max_parallel": args.max_parallel,
			"personalities": personalities,
			"retry_max_attempts": args.retry_max_attempts,
			"retry_backoff_base_s": args.retry_backoff_base_s,
			"retry_backoff_max_s": args.retry_backoff_max_s,
			"retry_jitter_s": args.retry_jitter_s,
		},
		"timing": {
			"batch_duration_seconds": duration_s,
		},
		"optimizer_report": optimizer_dict,
		"sgd_report_path": os.path.abspath(sgd_report_path),
		"sgd_graphs": (sgd_report.get("graphs") if isinstance(sgd_report, dict) else None),
		"graphs_health": graphs_health,
		"graphs_dynamics_health": graphs_dynamics_health,
		"retry_stats": {
			"complainant": llm_backend_complainant.get_retry_stats(),
			"critic": llm_backend_critic.get_retry_stats(),
		},
	}

	out_path = os.path.join(run_dir, "cycle_summary.json")
	with open(out_path, "w", encoding="utf-8") as f:
		json.dump(payload, f, ensure_ascii=False, indent=2)

	print(json.dumps(payload, indent=2))
	print(f"\nWrote: {out_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
