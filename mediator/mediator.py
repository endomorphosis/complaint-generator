from time import time
from .strings import user_prompts
from .state import State
from .inquiries import Inquiries
from .complaint import Complaint
from .exceptions import UserPresentableException
from .legal_hooks import (
	LegalClassificationHook,
	StatuteRetrievalHook,
	SummaryJudgmentHook,
	QuestionGenerationHook
)
from .evidence_hooks import (
	EvidenceStorageHook,
	EvidenceStateHook,
	EvidenceAnalysisHook
)
from .legal_authority_hooks import (
	LegalAuthoritySearchHook,
	LegalAuthorityStorageHook,
	LegalAuthorityAnalysisHook
)


class Mediator:
	def __init__(self, backends, evidence_db_path=None, legal_authority_db_path=None):
		self.backends = backends
		self.inquiries = Inquiries(self)
		self.complaint = Complaint(self)
		
		# Initialize legal hooks
		self.legal_classifier = LegalClassificationHook(self)
		self.statute_retriever = StatuteRetrievalHook(self)
		self.summary_judgment = SummaryJudgmentHook(self)
		self.question_generator = QuestionGenerationHook(self)
		
		# Initialize evidence hooks
		self.evidence_storage = EvidenceStorageHook(self)
		self.evidence_state = EvidenceStateHook(self, db_path=evidence_db_path)
		self.evidence_analysis = EvidenceAnalysisHook(self)
		
		# Initialize legal authority hooks
		self.legal_authority_search = LegalAuthoritySearchHook(self)
		self.legal_authority_storage = LegalAuthorityStorageHook(self, db_path=legal_authority_db_path)
		self.legal_authority_analysis = LegalAuthorityAnalysisHook(self)
		
		self.reset()


	def reset(self):
		self.state = State()
		# self.inquiries.register(user_prompts['genesis_question'])

	def resume(self, state):
		self.state = state


	def get_state(self):
		state = self.state.serialize()
		return self.state.serialize()


	def set_state(self, serialized):
		self.state = State.from_serialized(serialized)

	def response(self):
		return "I'm sorry, I don't understand. Please try again."

	def io(self, text):
		self.log('user_input', text=text)

		try:
			output = self.process(text)
			self.log('user_output', text=output)
		except Exception as exception:
			self.log('io_error', error=str(exception))
			raise exception

		return output


	def process(self, text):
		if not self.state:
			raise UserPresentableException(
				'no-context',
				'No internal state given. Either create new, or resume.'
			)

		if text:
			self.inquiries.answer(text)

		if not self.inquiries.get_next():
			self.complaint.generate()
			self.inquiries.generate()

			if self.inquiries.is_complete():
				return self.finalize()

		return self.inquiries.get_next()['question']


	def finalize(self):
		raise UserPresentableException(
			'not-implemented',
			'The Q&A has been completed. The follow-up flow has not yet been implemented.'
		)

	def analyze_complaint_legal_issues(self):
		"""
		Analyze complaint and classify legal issues.
		
		Returns classification, statutes, requirements, and generated questions.
		"""
		if not self.state.complaint:
			raise UserPresentableException(
				'no-complaint',
				'No complaint available to analyze. Generate complaint first.'
			)
		
		# Step 1: Classify the legal issues
		self.log('legal_analysis', step='classification')
		classification = self.legal_classifier.classify_complaint(self.state.complaint)
		self.state.legal_classification = classification
		
		# Step 2: Retrieve applicable statutes
		self.log('legal_analysis', step='statute_retrieval')
		statutes = self.statute_retriever.retrieve_statutes(classification)
		self.state.applicable_statutes = statutes
		
		# Step 3: Generate summary judgment requirements
		self.log('legal_analysis', step='requirements_generation')
		requirements = self.summary_judgment.generate_requirements(classification, statutes)
		self.state.summary_judgment_requirements = requirements
		
		# Step 4: Generate targeted questions
		self.log('legal_analysis', step='question_generation')
		questions = self.question_generator.generate_questions(requirements, classification)
		self.state.legal_questions = questions
		
		return {
			'classification': classification,
			'statutes': statutes,
			'requirements': requirements,
			'questions': questions
		}
	
	def get_legal_analysis(self):
		"""Get the current legal analysis results."""
		return {
			'classification': getattr(self.state, 'legal_classification', None),
			'statutes': getattr(self.state, 'applicable_statutes', None),
			'requirements': getattr(self.state, 'summary_judgment_requirements', None),
			'questions': getattr(self.state, 'legal_questions', None)
		}
	
	def submit_evidence(self, data: bytes, evidence_type: str,
	                   user_id: str = None,
	                   description: str = None,
	                   claim_type: str = None,
	                   metadata: dict = None):
		"""
		Submit evidence for the user's case.
		
		Args:
			data: Evidence data as bytes
			evidence_type: Type of evidence (document, image, video, text, etc.)
			user_id: User identifier (defaults to state username)
			description: Description of the evidence
			claim_type: Which claim this evidence supports
			metadata: Additional metadata
			
		Returns:
			Dictionary with evidence information including CID and record ID
		"""
		# Use username from state if user_id not provided
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		# Store in IPFS
		self.log('evidence_submission', user_id=user_id, type=evidence_type)
		evidence_info = self.evidence_storage.store_evidence(data, evidence_type, metadata)
		
		# Get complaint ID if available
		complaint_id = getattr(self.state, 'complaint_id', None)
		
		# Store state in DuckDB
		record_id = self.evidence_state.add_evidence_record(
			user_id=user_id,
			evidence_info=evidence_info,
			complaint_id=complaint_id,
			claim_type=claim_type,
			description=description
		)
		
		result = {
			**evidence_info,
			'record_id': record_id,
			'user_id': user_id,
			'description': description,
			'claim_type': claim_type
		}
		
		self.log('evidence_submitted', cid=evidence_info['cid'], record_id=record_id)
		
		return result
	
	def submit_evidence_file(self, file_path: str, evidence_type: str,
	                        user_id: str = None,
	                        description: str = None,
	                        claim_type: str = None,
	                        metadata: dict = None):
		"""
		Submit evidence from a file.
		
		Args:
			file_path: Path to evidence file
			evidence_type: Type of evidence
			user_id: User identifier
			description: Description of the evidence
			claim_type: Which claim this evidence supports
			metadata: Additional metadata
			
		Returns:
			Dictionary with evidence information including CID and record ID
		"""
		# Read file and submit
		with open(file_path, 'rb') as f:
			data = f.read()
		
		# Add filename to metadata
		file_metadata = metadata or {}
		file_metadata['filename'] = file_path
		
		return self.submit_evidence(
			data=data,
			evidence_type=evidence_type,
			user_id=user_id,
			description=description,
			claim_type=claim_type,
			metadata=file_metadata
		)
	
	def get_user_evidence(self, user_id: str = None):
		"""
		Get all evidence for a user.
		
		Args:
			user_id: User identifier (defaults to state username)
			
		Returns:
			List of evidence records
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		return self.evidence_state.get_user_evidence(user_id)
	
	def retrieve_evidence(self, cid: str):
		"""
		Retrieve evidence data by CID.
		
		Args:
			cid: Content ID of the evidence
			
		Returns:
			Evidence data as bytes
		"""
		return self.evidence_storage.retrieve_evidence(cid)
	
	def analyze_evidence(self, user_id: str = None, claim_type: str = None):
		"""
		Analyze evidence for a claim.
		
		Args:
			user_id: User identifier (defaults to state username)
			claim_type: Claim type to analyze evidence for
			
		Returns:
			Analysis results
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		if claim_type:
			return self.evidence_analysis.analyze_evidence_for_claim(user_id, claim_type)
		else:
			# Return general evidence stats
			return self.evidence_state.get_evidence_statistics(user_id)
	
	def search_legal_authorities(self, query: str, claim_type: str = None,
	                            jurisdiction: str = None,
	                            search_all: bool = False):
		"""
		Search for relevant legal authorities.
		
		Args:
			query: Search query (e.g., "civil rights violations")
			claim_type: Optional claim type to focus search
			jurisdiction: Optional jurisdiction filter
			search_all: If True, search all sources; if False, use targeted search
			
		Returns:
			Dictionary with search results by source type
		"""
		if search_all:
			return self.legal_authority_search.search_all_sources(
				query, claim_type, jurisdiction
			)
		else:
			# Default to US Code search
			results = {
				'statutes': self.legal_authority_search.search_us_code(query),
				'regulations': [],
				'case_law': [],
				'web_archives': []
			}
			return results
	
	def store_legal_authorities(self, authorities: Dict[str, List[Dict]], 
	                           claim_type: str = None,
	                           search_query: str = None,
	                           user_id: str = None):
		"""
		Store found legal authorities in DuckDB.
		
		Args:
			authorities: Dictionary with authorities by type (from search_legal_authorities)
			claim_type: Optional claim type these authorities support
			search_query: Original search query
			user_id: User identifier (defaults to state username)
			
		Returns:
			Dictionary with count of stored authorities by type
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		complaint_id = getattr(self.state, 'complaint_id', None)
		
		stored_counts = {}
		for auth_type, auth_list in authorities.items():
			if auth_list:
				# Add type info to each authority
				for auth in auth_list:
					auth['type'] = auth_type.rstrip('s')  # statutes -> statute
				
				record_ids = self.legal_authority_storage.add_authorities_bulk(
					auth_list, user_id, complaint_id, claim_type, search_query
				)
				stored_counts[auth_type] = len(record_ids)
				
				self.log('legal_authorities_stored',
					type=auth_type, count=len(record_ids), claim_type=claim_type)
		
		return stored_counts
	
	def get_legal_authorities(self, user_id: str = None, claim_type: str = None):
		"""
		Get stored legal authorities.
		
		Args:
			user_id: User identifier (defaults to state username)
			claim_type: Optional claim type to filter by
			
		Returns:
			List of legal authority records
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		if claim_type:
			return self.legal_authority_storage.get_authorities_by_claim(user_id, claim_type)
		else:
			return self.legal_authority_storage.get_all_authorities(user_id)
	
	def analyze_legal_authorities(self, claim_type: str, user_id: str = None):
		"""
		Analyze stored legal authorities for a claim.
		
		Args:
			claim_type: Claim type to analyze
			user_id: User identifier (defaults to state username)
			
		Returns:
			Analysis with recommendations
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		return self.legal_authority_analysis.analyze_authorities_for_claim(user_id, claim_type)
	
	def research_case_automatically(self, user_id: str = None):
		"""
		Automatically research legal authorities for the case.
		
		This method:
		1. Analyzes the complaint to identify claims
		2. Searches for relevant legal authorities
		3. Stores the authorities in DuckDB
		
		Args:
			user_id: User identifier (defaults to state username)
			
		Returns:
			Dictionary with research results
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		# First, analyze the complaint if not already done
		if not hasattr(self.state, 'legal_classification'):
			if not self.state.complaint:
				return {'error': 'No complaint available. Generate complaint first.'}
			self.analyze_complaint_legal_issues()
		
		classification = self.state.legal_classification
		results = {
			'claim_types': classification.get('claim_types', []),
			'authorities_found': {},
			'authorities_stored': {}
		}
		
		# Search for authorities for each claim type
		for claim_type in classification.get('claim_types', []):
			self.log('auto_research', claim_type=claim_type)
			
			# Search all sources
			search_results = self.search_legal_authorities(
				query=claim_type,
				claim_type=claim_type,
				search_all=True
			)
			
			# Store results
			stored_counts = self.store_legal_authorities(
				search_results,
				claim_type=claim_type,
				search_query=claim_type,
				user_id=user_id
			)
			
			results['authorities_found'][claim_type] = {
				k: len(v) for k, v in search_results.items()
			}
			results['authorities_stored'][claim_type] = stored_counts
		
		self.log('auto_research_complete', results=results)
		
		return results


	def query_backend(self, prompt):
		backend = self.backends[0]

		try:
			response = backend(prompt)
		except Exception as exception:
			self.log('backend_error', backend=backend.id, prompt=prompt, error=str(exception))
			raise exception

		self.log('backend_query', backend=backend.id, prompt=prompt, response=response)

		return response
		


	def log(self, type, **data):
		self.state.log.append({
			'time': int(time()),
			'type': type,
			**data
		})