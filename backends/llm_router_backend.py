"""
LLM Router Backend

This backend uses the llm_router from ipfs_datasets_py to route LLM requests.
It provides a unified interface for routing requests to various LLM providers.
Includes circuit breaker pattern for resilience against cascading failures.
"""

import sys
import os
import logging
import random
import time
import threading

# Add ipfs_datasets_py to Python path if not already there
ipfs_datasets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ipfs_datasets_py')
if os.path.exists(ipfs_datasets_path) and ipfs_datasets_path not in sys.path:
    sys.path.insert(0, ipfs_datasets_path)

# Also add vendored ipfs_accelerate_py (nested package layout) if present.
ipfs_accelerate_repo_path = os.path.join(ipfs_datasets_path, 'ipfs_accelerate_py')
if os.path.exists(ipfs_accelerate_repo_path) and ipfs_accelerate_repo_path not in sys.path:
    sys.path.insert(0, ipfs_accelerate_repo_path)

logger = logging.getLogger(__name__)

try:
    from ipfs_datasets_py.llm_router import generate_text
except ImportError as e:
    # Fallback if submodule not initialized
    logger.warning("Could not import llm_router from ipfs_datasets_py: %s", e)
    generate_text = None

try:
    from ipfs_datasets_py.optimizers.agentic.production_hardening import CircuitBreaker
except ImportError:
    # Fallback: create a pass-through circuit breaker if not available
    logger.warning("CircuitBreaker not available from optimizers, using pass-through")
    class CircuitBreaker:
        """Pass-through circuit breaker when optimizers module not available."""
        def __init__(self, failure_threshold=5, timeout=60, expected_exception=Exception):
            pass
        def call(self, func, call_args=None, call_kwargs=None):
            call_args = call_args or ()
            call_kwargs = call_kwargs or {}
            return func(*call_args, **call_kwargs)


class LLMRouterBackend:
    """Backend that uses ipfs_datasets_py's llm_router for LLM routing."""
    
    def __init__(self, id, provider=None, model=None, **config):
        """
        Initialize the LLM Router Backend.
        
        Args:
            id: Backend identifier
            provider: Optional provider name (e.g., 'openrouter', 'local_hf')
            model: Optional model name
            **config: Additional configuration including:
                - retry_max_attempts: Max retry attempts (default: 1)
                - retry_backoff_base_s: Base backoff in seconds (default: 0.5)
                - retry_backoff_max_s: Max backoff in seconds (default: 20.0)
                - retry_jitter_s: Jitter added to backoff (default: 0.1)
                - circuit_breaker_enabled: Enable circuit breaker (default: True)
                - circuit_breaker_failure_threshold: Failures before opening (default: 5)
                - circuit_breaker_timeout: Seconds before half-open (default: 60)
        """
        self.id = id
        self.provider = provider or 'copilot_cli'
        if model is None:
            self.model = 'gpt-5.3-codex' if self.provider == 'codex_cli' else 'gpt-5-mini'
        else:
            self.model = model

        # Retry/backoff tuning. Defaults to no retries for backward compatibility.
        self.retry_max_attempts = int(config.pop('retry_max_attempts', 1) or 1)
        self.retry_backoff_base_s = float(config.pop('retry_backoff_base_s', 0.5) or 0.5)
        self.retry_backoff_max_s = float(config.pop('retry_backoff_max_s', 20.0) or 20.0)
        self.retry_jitter_s = float(config.pop('retry_jitter_s', 0.1) or 0.1)
        self.retryable_error_substrings = list(
            config.pop(
                'retryable_error_substrings',
                [
                    '429',
                    'rate limit',
                    'too many requests',
                    'temporarily unavailable',
                    'timeout',
                    'timed out',
                    'econnreset',
                    'connection reset',
                    'connection aborted',
                    'service unavailable',
                ],
            )
        )

        # Circuit breaker configuration
        self.circuit_breaker_enabled = bool(config.pop('circuit_breaker_enabled', True))
        circuit_breaker_failure_threshold = int(config.pop('circuit_breaker_failure_threshold', 5))
        circuit_breaker_timeout = int(config.pop('circuit_breaker_timeout', 60))

        self.config = config

        self._stats_lock = threading.Lock()
        self._retry_stats = {
            'calls_total': 0,
            'attempts_total': 0,
            'retries_total': 0,
            'backoff_seconds_total': 0.0,
            'failures_total': 0,
            'circuit_breaker_opens': 0,
            'circuit_breaker_rejects': 0,
        }
        
        # Initialize circuit breaker
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_failure_threshold,
            timeout=circuit_breaker_timeout,
            expected_exception=Exception,
        )
        
        # Check if llm_router is available
        if generate_text is None:
            raise ImportError(
                "llm_router not available. Please ensure ipfs_datasets_py submodule "
                "is initialized with: git submodule update --init --recursive"
            )
    
    def __call__(self, text):
        """
        Generate text using the llm_router with circuit breaker protection.
        
        Args:
            text: The prompt text
            
        Returns:
            Generated text response
            
        Raises:
            Exception: If circuit breaker is open or all retries exhausted
        """
        with self._stats_lock:
            self._retry_stats['calls_total'] += 1

        # Wrap the entire retry logic with circuit breaker
        if self.circuit_breaker_enabled:
            try:
                return self._circuit_breaker.call(
                    func=self._generate_with_retry,
                    call_args=(text,),
                )
            except Exception as e:
                # Check if this was a circuit breaker rejection
                if "Circuit breaker is OPEN" in str(e):
                    with self._stats_lock:
                        self._retry_stats['circuit_breaker_rejects'] += 1
                    logger.warning(f"Circuit breaker OPEN for {self.provider}/{self.model}")
                raise
        else:
            # Circuit breaker disabled, call directly
            return self._generate_with_retry(text)

    def _generate_with_retry(self, text):
        """Internal method that implements retry logic."""
        last_error = None
        max_attempts = max(1, self.retry_max_attempts)
        for attempt in range(1, max_attempts + 1):
            with self._stats_lock:
                self._retry_stats['attempts_total'] += 1
            try:
                response = generate_text(
                    prompt=text,
                    provider=self.provider,
                    model_name=self.model,
                    **self.config
                )
                return response
            except Exception as e:
                last_error = e
                retryable = self._is_retryable_error(e)
                if attempt >= max_attempts or not retryable:
                    with self._stats_lock:
                        self._retry_stats['failures_total'] += 1
                        # Track circuit breaker opens (when failure threshold hit)
                        if hasattr(self._circuit_breaker, 'failure_count'):
                            if self._circuit_breaker.failure_count >= self._circuit_breaker.failure_threshold - 1:
                                self._retry_stats['circuit_breaker_opens'] += 1
                    raise Exception(f'llm_router_error: {str(e)}')

                backoff_s = self._compute_backoff_seconds(attempt)
                with self._stats_lock:
                    self._retry_stats['retries_total'] += 1
                    self._retry_stats['backoff_seconds_total'] += float(backoff_s)
                logger.debug(f"Retry {attempt}/{max_attempts} after {backoff_s:.2f}s: {e}")
                time.sleep(backoff_s)

        # Should be unreachable, but keep a safe fallback.
        with self._stats_lock:
            self._retry_stats['failures_total'] += 1
        raise Exception(f'llm_router_error: {str(last_error)}')

    def _compute_backoff_seconds(self, attempt: int) -> float:
        # attempt is 1-based; backoff applies between attempt and attempt+1.
        exp = max(0, attempt - 1)
        base = self.retry_backoff_base_s * (2 ** exp)
        base = min(base, self.retry_backoff_max_s)
        jitter = random.uniform(0.0, max(0.0, self.retry_jitter_s))
        return float(base + jitter)

    def _is_retryable_error(self, error: Exception) -> bool:
        message = str(error or '').lower()
        # unwrap our own wrapper if present
        if message.startswith('llm_router_error:'):
            message = message.split(':', 1)[-1].strip()
        return any(s.lower() in message for s in self.retryable_error_substrings)

    def get_retry_stats(self):
        """Get retry and circuit breaker statistics."""
        with self._stats_lock:
            return dict(self._retry_stats)

    def get_circuit_breaker_state(self):
        """Get current circuit breaker state.
        
        Returns:
            dict with keys: state (CLOSED/OPEN/HALF_OPEN), failure_count, last_failure_time
        """
        if not self.circuit_breaker_enabled or not hasattr(self._circuit_breaker, 'state'):
            return {'state': 'DISABLED', 'failure_count': 0, 'last_failure_time': None}
        
        return {
            'state': self._circuit_breaker.state,
            'failure_count': self._circuit_breaker.failure_count,
            'last_failure_time': self._circuit_breaker.last_failure_time,
        }

    def reset_circuit_breaker(self):
        """Manually reset the circuit breaker to CLOSED state.
        
        Use this to force recovery after fixing underlying issues.
        """
        if self.circuit_breaker_enabled and hasattr(self._circuit_breaker, '_lock'):
            with self._circuit_breaker._lock:
                self._circuit_breaker.state = 'CLOSED'
                self._circuit_breaker.failure_count = 0
                self._circuit_breaker.last_failure_time = None
            logger.info(f"Circuit breaker manually reset for {self.provider}/{self.model}")


# For backward compatibility, create an alias
LLMRouter = LLMRouterBackend
