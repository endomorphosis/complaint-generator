from pathlib import Path
import re

from .strings import model_prompts


class Complaint:
	def __init__(self, mediator):
		self.m = mediator
		self._max_answer_chars = 3000

	def _normalize_whitespace(self, value):
		return re.sub(r'\s+', ' ', str(value or '')).strip()

	def _looks_low_signal(self, answer):
		text = self._normalize_whitespace(answer).lower()
		if not text:
			return True
		if text in {'skip', 'defer', 'defer for later', 'unknown', 'n/a', 'na'}:
			return True
		if len(text) <= 64 and any(
			phrase in text
			for phrase in (
				'check the email',
				'check emails',
				'refer to email',
				'refer to the email',
				'refer to the timeline',
				'use emails to check',
			)
		):
			return True
		if len(text) <= 28 and text in {'yes', 'no', 'continue'}:
			return True
		return False

	def _trim_answer(self, answer):
		normalized = self._normalize_whitespace(answer)
		if len(normalized) <= self._max_answer_chars:
			return normalized
		return normalized[: self._max_answer_chars].rstrip() + ' [truncated]'

	def _workspace_root(self):
		# complaint.py is in complaint-generator/mediator, parent of complaint-generator is workspace root
		return Path(__file__).resolve().parents[2]

	def _collect_workspace_evidence_context(self):
		workspace_root = self._workspace_root()
		evidence_dirs = (
			'hacc_research',
			'hacc_website',
			'legal_data',
			'research_data',
		)
		lines = ['Workspace Evidence Snapshot:']
		for directory_name in evidence_dirs:
			directory = workspace_root / directory_name
			if not directory.exists() or not directory.is_dir():
				lines.append(f'- {directory_name}: unavailable')
				continue
			file_count = 0
			sample = []
			for path in directory.rglob('*'):
				if not path.is_file():
					continue
				file_count += 1
				if len(sample) < 4:
					relative_path = path.relative_to(workspace_root)
					sample.append(str(relative_path))
			if sample:
				lines.append(f"- {directory_name}: {file_count} files (examples: {', '.join(sample)})")
			else:
				lines.append(f'- {directory_name}: 0 files')
		return '\n'.join(lines)

	def _build_prompt_inquiries(self):
		inquiries = []
		seen_question_answer = set()
		seen_answer_normalized = set()

		for inquiry in getattr(self.m.state, 'inquiries', []):
			if not isinstance(inquiry, dict):
				continue
			question = self._normalize_whitespace(inquiry.get('question', ''))
			answer = inquiry.get('answer')
			if self._looks_low_signal(answer):
				continue
			answer_clean = self._trim_answer(answer)
			qa_key = (question.lower(), answer_clean.lower())
			if qa_key in seen_question_answer:
				continue
			if len(answer_clean) >= 240:
				# Deduplicate repeated long narratives that often show up in timeline follow-ups.
				answer_key = answer_clean.lower()
				if answer_key in seen_answer_normalized:
					continue
				seen_answer_normalized.add(answer_key)
			seen_question_answer.add(qa_key)

			inquiries.append(model_prompts['inquiry_block'].format(
				lawyer=question,
				plaintiff=answer_clean,
			))

		return inquiries

	def _build_support_context(self):
		support_chunks = []
		if hasattr(self.m, 'build_drafting_support_context'):
			support_context = self.m.build_drafting_support_context()
			support_context = str(support_context or '').strip()
			if support_context:
				support_chunks.append(support_context)

		workspace_context = self._collect_workspace_evidence_context()
		if workspace_context:
			support_chunks.append(workspace_context)

		return '\n\n'.join(chunk for chunk in support_chunks if chunk)

	
	def generate(self):
		inquiries = self._build_prompt_inquiries()
		support_context = self._build_support_context()

		self.m.state.complaint = self.m.query_backend(
			model_prompts['summarize_complaint'].format(
				inquiries='\n'.join(inquiries),
				support_context=support_context,
			)
		)

