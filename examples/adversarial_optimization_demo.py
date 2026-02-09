import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict

# Allow running via: python examples/adversarial_optimization_demo.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
	sys.path.insert(0, PROJECT_ROOT)

from adversarial_harness import AdversarialHarness, Critic, Optimizer
from adversarial_harness.session import SessionResult
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


def _prompt_multiline(prompt: str) -> str:
	print(prompt)
	print("(finish input with an empty line)")
	lines = []
	while True:
		line = input("> ")
		if line == "":
			break
		lines.append(line)
	return "\n".join(lines).strip()


def _safe_session_id(text: str) -> str:
	allowed = []
	for ch in text:
		if ch.isalnum() or ch in ("-", "_", "."):
			allowed.append(ch)
		else:
			allowed.append("_")
	return "".join(allowed)


def _write_jsonl_line(fp, obj: Dict[str, Any]) -> None:
	fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
	fp.flush()


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Interactive multi-turn mediator chat; saves JSONL history and prints an optimization report"
	)
	parser.add_argument(
		"--mode",
		choices=["interactive", "batch"],
		default="interactive",
		help="Run an interactive session or an automated adversarial batch",
	)
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
	parser.add_argument("--max-turns", type=int, default=3)
	parser.add_argument(
		"--session-id",
		default=None,
		help="Optional session id (default: timestamp-based)",
	)
	parser.add_argument("--num-sessions", type=int, default=3, help="(batch mode) number of sessions")
	parser.add_argument("--max-parallel", type=int, default=1, help="(batch mode) parallel sessions")
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO)

	config = _load_config(args.config)
	backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)

	if args.mode == "batch":
		llm_backend_complainant = LLMRouterBackend(**backend_kwargs)
		llm_backend_critic = LLMRouterBackend(**backend_kwargs)

		def mediator_factory() -> Mediator:
			return Mediator(backends=[LLMRouterBackend(**backend_kwargs)])

		harness = AdversarialHarness(
			llm_backend_complainant=llm_backend_complainant,
			llm_backend_critic=llm_backend_critic,
			mediator_factory=mediator_factory,
			max_parallel=args.max_parallel,
			session_state_dir=os.path.join(PROJECT_ROOT, "statefiles"),
		)
		results = harness.run_batch(num_sessions=args.num_sessions, max_turns_per_session=args.max_turns)
		report = Optimizer().analyze(results)
		print(json.dumps(report.to_dict(), indent=2))
		return 0

	# interactive mode
	session_id = args.session_id or f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
	session_id = _safe_session_id(session_id)
	session_dir = os.path.join(PROJECT_ROOT, "statefiles", session_id)
	os.makedirs(session_dir, exist_ok=True)

	chat_jsonl_path = os.path.join(session_dir, "chat.jsonl")
	session_json_path = os.path.join(session_dir, "session.json")
	report_json_path = os.path.join(session_dir, "optimization_report.json")

	logging.info("Session folder: %s", session_dir)

	llm_backend = LLMRouterBackend(**backend_kwargs)
	mediator = Mediator(backends=[llm_backend])
	critic = Critic(llm_backend)

	initial_complaint = _prompt_multiline("Paste/enter the initial complaint text:")
	if not initial_complaint:
		raise SystemExit("No complaint text provided")

	conversation_history: list[dict[str, Any]] = []
	start_time = time.time()

	with open(chat_jsonl_path, "a", encoding="utf-8") as chat_fp:
		_write_jsonl_line(
			chat_fp,
			{
				"timestamp": datetime.utcnow().isoformat(),
				"role": "complainant",
				"type": "initial_complaint",
				"content": initial_complaint,
			},
		)

		status = mediator.start_three_phase_process(initial_complaint)
		questions = status.get("initial_questions") or []
		turns = 0
		questions_asked = 0

		while turns < args.max_turns:
			if not questions:
				logging.info("No more questions; ending session")
				break

			question = questions[0]
			question_text = question.get("question") if isinstance(question, dict) else str(question)

			print("\nMediator question:")
			print(question_text)

			conversation_history.append(
				{
					"role": "mediator",
					"type": "question",
					"content": question_text,
				}
			)
			_write_jsonl_line(
				chat_fp,
				{
					"timestamp": datetime.utcnow().isoformat(),
					"role": "mediator",
					"type": "question",
					"content": question_text,
				},
			)

			answer = _prompt_multiline("Your answer:")
			conversation_history.append(
				{
					"role": "complainant",
					"type": "answer",
					"content": answer,
				}
			)
			_write_jsonl_line(
				chat_fp,
				{
					"timestamp": datetime.utcnow().isoformat(),
					"role": "complainant",
					"type": "answer",
					"content": answer,
				},
			)

			status = mediator.process_denoising_answer(question, answer)
			questions = status.get("next_questions") or []

			turns += 1
			questions_asked += 1
			if status.get("converged") or status.get("ready_for_evidence_phase"):
				logging.info("Mediator indicates convergence/phase transition; ending session")
				break

	final_state = mediator.get_three_phase_status()
	critic_score = critic.evaluate_session(
		initial_complaint,
		conversation_history,
		final_state,
		context={"mode": "interactive", "session_id": session_id},
	)

	duration = time.time() - start_time
	session_result = SessionResult(
		session_id=session_id,
		timestamp=datetime.utcnow().isoformat(),
		seed_complaint={"mode": "interactive", "_meta": {"max_turns": args.max_turns}},
		initial_complaint_text=initial_complaint,
		conversation_history=conversation_history,
		num_questions=questions_asked,
		num_turns=turns,
		final_state=final_state,
		critic_score=critic_score,
		duration_seconds=duration,
		success=True,
	)

	with open(session_json_path, "w", encoding="utf-8") as f:
		json.dump(session_result.to_dict(), f, ensure_ascii=False, indent=2)

	report = Optimizer().analyze([session_result])
	with open(report_json_path, "w", encoding="utf-8") as f:
		json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

	print("\nOptimization report:")
	print(json.dumps(report.to_dict(), indent=2))
	print("\nSaved:")
	print(f"- {chat_jsonl_path}")
	print(f"- {session_json_path}")
	print(f"- {report_json_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
