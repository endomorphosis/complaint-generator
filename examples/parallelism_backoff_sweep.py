import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
import importlib.util
from itertools import product
from typing import Any, Dict, List

# Allow running via: python examples/parallelism_backoff_sweep.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
	sys.path.insert(0, PROJECT_ROOT)

from adversarial_harness import AdversarialHarness
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


def _parse_int_list(s: str) -> List[int]:
	return [int(x.strip()) for x in s.split(",") if x.strip()]


def _parse_float_list(s: str) -> List[float]:
	return [float(x.strip()) for x in s.split(",") if x.strip()]


def _parse_str_list(s: str) -> List[str]:
	return [x.strip() for x in s.split(",") if x.strip()]


def _parse_personality_sets(s: str) -> List[List[str]]:
	# Semicolon-separated CSVs: "cooperative,defensive;vague,detailed"
	sets: List[List[str]] = []
	for part in (s or "").split(";"):
		part = part.strip()
		if not part:
			continue
		sets.append(_parse_str_list(part))
	return sets


def main() -> int:
	parser = argparse.ArgumentParser(description="Empirically sweep parallelism and retry/backoff settings")
	parser.add_argument("--config", default="config.llm_router.json")
	parser.add_argument("--backend-id", default=None)
	parser.add_argument("--state-dir", default="statefiles", help="Base directory for sweep artifacts")
	parser.add_argument("--sweep-id", default=None)
	parser.add_argument("--num-sessions", type=int, default=6)
	parser.add_argument("--max-turns", type=int, default=6)
	parser.add_argument("--parallels", default="1,2,4")
	parser.add_argument("--attempts", default="1,2")
	parser.add_argument("--base-backoffs", default="0.5,1.0")
	parser.add_argument("--max-backoff-s", type=float, default=20.0)
	parser.add_argument("--jitter-s", type=float, default=0.1)
	parser.add_argument(
		"--session-cache-friendly",
		action="store_true",
		help=(
			"Enable a Copilot CLI cache-friendly mode by isolating each session into its own Copilot --config-dir and using --continue. "
			"This reduces prompt-prefix churn across turns without leaking state across parallel sessions."
		),
	)
	parser.add_argument(
		"--personalities",
		default=None,
		help="Comma-separated personalities to cycle through for every run (overrides harness defaults).",
	)
	parser.add_argument(
		"--personality-sets",
		default=None,
		help="Semicolon-separated personality CSVs to sweep as an extra grid dimension (e.g. 'cooperative,defensive;vague,detailed,emotional').",
	)
	parser.add_argument("--denoiser-exploration-enabled", action="store_true")
	parser.add_argument("--denoiser-momentum-enabled", action="store_true")
	parser.add_argument("--denoiser-exploration-epsilon", type=float, default=None)
	parser.add_argument("--denoiser-exploration-top-k", type=int, default=None)
	parser.add_argument("--denoiser-momentum-beta", type=float, default=None)
	parser.add_argument("--denoiser-seed", type=int, default=None)
	args = parser.parse_args()

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
	backend_kwargs_base = _get_llm_router_backend_config(config, args.backend_id)

	sweep_id = args.sweep_id or f"sweep_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
	sweep_dir = os.path.join(args.state_dir, "_sweeps", sweep_id)
	os.makedirs(sweep_dir, exist_ok=True)

	parallels = _parse_int_list(args.parallels)
	attempts = _parse_int_list(args.attempts)
	base_backoffs = _parse_float_list(args.base_backoffs)

	personalities = _parse_str_list(args.personalities) if args.personalities else None
	personality_sets = _parse_personality_sets(args.personality_sets) if args.personality_sets else None
	if personality_sets is None:
		personality_sets = [personalities]  # may be None; means use harness default personalities

	grid = list(product(parallels, attempts, base_backoffs, personality_sets))
	logging.info("Sweep dir: %s", os.path.abspath(sweep_dir))
	logging.info("Grid points: %d", len(grid))

	results = []
	for max_parallel, retry_max_attempts, retry_backoff_base_s, run_personalities in grid:
		label = f"p{max_parallel}_a{retry_max_attempts}_b{retry_backoff_base_s}".replace(".", "p")
		if run_personalities:
			label += "_pers_" + "-".join(run_personalities)
		run_dir = os.path.join(sweep_dir, label)
		os.makedirs(run_dir, exist_ok=True)

		backend_kwargs = {
			**backend_kwargs_base,
			"retry_max_attempts": retry_max_attempts,
			"retry_backoff_base_s": retry_backoff_base_s,
			"retry_backoff_max_s": args.max_backoff_s,
			"retry_jitter_s": args.jitter_s,
		}

		llm_backend_complainant = LLMRouterBackend(**backend_kwargs)
		llm_backend_critic = LLMRouterBackend(**backend_kwargs)

		def _make_session_backend(*, role: str, session_id: str, session_dir: str | None) -> LLMRouterBackend:
			per_call_kwargs: Dict[str, Any] = dict(backend_kwargs)
			if args.session_cache_friendly and session_dir:
				per_call_kwargs["copilot_config_dir"] = os.path.join(session_dir, "_copilot", role, "config")
				per_call_kwargs["continue_session"] = True
				per_call_kwargs.setdefault("copilot_log_dir", os.path.join(session_dir, "_copilot", role, "logs"))
			return LLMRouterBackend(**per_call_kwargs)

		complainant_factory = None
		critic_factory = None
		if args.session_cache_friendly:
			complainant_factory = lambda session_id, session_dir: _make_session_backend(
				role="complainant",
				session_id=session_id,
				session_dir=session_dir,
			)
			critic_factory = lambda session_id, session_dir: _make_session_backend(
				role="critic",
				session_id=session_id,
				session_dir=session_dir,
			)

		def mediator_factory(session_id: str | None = None, session_dir: str | None = None, **kwargs) -> Mediator:
			if args.session_cache_friendly and session_id and session_dir:
				backend = _make_session_backend(role="mediator", session_id=session_id, session_dir=session_dir)
			else:
				backend = LLMRouterBackend(**backend_kwargs)
			return Mediator(backends=[backend], **kwargs)

		harness = AdversarialHarness(
			llm_backend_complainant=llm_backend_complainant,
			llm_backend_critic=llm_backend_critic,
			mediator_factory=mediator_factory,
			max_parallel=max_parallel,
			session_state_dir=run_dir,
			llm_backend_complainant_factory=complainant_factory,
			llm_backend_critic_factory=critic_factory,
		)

		start = time.time()
		batch_results = harness.run_batch(
			num_sessions=args.num_sessions,
			max_turns_per_session=args.max_turns,
			personalities=run_personalities,
		)
		duration_s = time.time() - start

		successes = sum(1 for r in batch_results if r.success)
		failures = sum(1 for r in batch_results if not r.success)

		# SGD report for this run
		session_json_files = _find_session_json_files(run_dir)
		summaries = [_summarize_session(p) for p in session_json_files]
		sgd_report_path = _write_report(run_dir, os.path.join(run_dir, "_reports"), summaries)
		with open(sgd_report_path, "r", encoding="utf-8") as f:
			sgd_report = json.load(f)

		point = {
			"label": label,
			"settings": {
				"max_parallel": max_parallel,
				"retry_max_attempts": retry_max_attempts,
				"retry_backoff_base_s": retry_backoff_base_s,
				"retry_backoff_max_s": args.max_backoff_s,
				"retry_jitter_s": args.jitter_s,
				"personalities": run_personalities,
			},
			"metrics": {
				"batch_duration_seconds": duration_s,
				"successful_sessions": successes,
				"failed_sessions": failures,
				"success_rate": (successes / max(1, args.num_sessions)),
				"throughput_sessions_per_min": (successes / max(1e-9, duration_s)) * 60.0,
			},
			"retry_stats": {
				"complainant": llm_backend_complainant.get_retry_stats(),
				"critic": llm_backend_critic.get_retry_stats(),
			},
			"sgd": {
				"ended_reason_counts": sgd_report.get("ended_reason_counts"),
				"averages": sgd_report.get("averages"),
				"missing_question_category_counts": sgd_report.get("missing_question_category_counts"),
			},
			"paths": {
				"run_dir": os.path.abspath(run_dir),
				"sgd_report": os.path.abspath(sgd_report_path),
			},
		}
		results.append(point)

		summary_line = (
			f"{label}: ok={successes}/{args.num_sessions} "
			f"dur={duration_s:.1f}s thr={point['metrics']['throughput_sessions_per_min']:.1f}/min "
			f"retries={point['retry_stats']['complainant']['retries_total']}+{point['retry_stats']['critic']['retries_total']}"
		)
		print(summary_line)

	out = {
		"generated_at": datetime.utcnow().isoformat(),
		"sweep_id": sweep_id,
		"sweep_dir": os.path.abspath(sweep_dir),
		"config": {
			"backend_id": args.backend_id,
			"num_sessions": args.num_sessions,
			"max_turns": args.max_turns,
			"grid": {
				"parallels": parallels,
				"attempts": attempts,
				"base_backoffs": base_backoffs,
				"max_backoff_s": args.max_backoff_s,
				"jitter_s": args.jitter_s,
			},
		},
		"results": results,
	}

	out_path = os.path.join(sweep_dir, "sweep_results.json")
	with open(out_path, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=2)

	print(f"\nWrote: {out_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
