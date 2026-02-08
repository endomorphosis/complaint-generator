"""
LLM Router Backend

This backend uses the llm_router from ipfs_datasets_py to route LLM requests.
It provides a unified interface for routing requests to various LLM providers.
"""

import sys
import os

# Add ipfs_datasets_py to Python path if not already there
ipfs_datasets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ipfs_datasets_py')
if os.path.exists(ipfs_datasets_path) and ipfs_datasets_path not in sys.path:
    sys.path.insert(0, ipfs_datasets_path)

try:
    from ipfs_datasets_py.llm_router import generate_text, get_llm_provider
except ImportError as e:
    # Fallback if submodule not initialized
    print(f"Warning: Could not import llm_router from ipfs_datasets_py: {e}")
    generate_text = None
    get_llm_provider = None


class LLMRouterBackend:
    """Backend that uses ipfs_datasets_py's llm_router for LLM routing."""
    
    def __init__(self, id, provider=None, model=None, **config):
        """
        Initialize the LLM Router Backend.
        
        Args:
            id: Backend identifier
            provider: Optional provider name (e.g., 'openrouter', 'local_hf')
            model: Optional model name
            **config: Additional configuration passed to generate_text
        """
        self.id = id
        self.provider = provider
        self.model = model
        self.config = config
        
        # Check if llm_router is available
        if generate_text is None:
            raise ImportError(
                "llm_router not available. Please ensure ipfs_datasets_py submodule "
                "is initialized with: git submodule update --init --recursive"
            )
    
    def __call__(self, text):
        """
        Generate text using the llm_router.
        
        Args:
            text: The prompt text
            
        Returns:
            Generated text response
        """
        try:
            # Use the llm_router to generate text
            response = generate_text(
                prompt=text,
                provider=self.provider,
                model_name=self.model,
                **self.config
            )
            return response
        except Exception as e:
            raise Exception(f'llm_router_error: {str(e)}')


# For backward compatibility, create an alias
LLMRouter = LLMRouterBackend
