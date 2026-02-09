# Using LLM Router Backend

The complaint-generator now includes a backend that uses the `llm_router` from the `ipfs_datasets_py` submodule to route LLM requests. This provides a unified interface for working with multiple LLM providers.

## Features

- **Multiple Provider Support**: Route requests to OpenRouter, local HuggingFace models, and more
- **Automatic Fallback**: Falls back to local models if remote providers are unavailable
- **Provider Caching**: Efficiently reuses provider instances
- **Configurable**: Supports custom configuration per backend

## Configuration

### Basic Usage

Add the LLM Router backend to your `config.llm_router.json`:

```json
{
    "BACKENDS": [
        {
            "id": "llm-router",
            "type": "llm_router",
            "provider": "copilot_cli",
            "model": "gpt-5-mini",
            "max_tokens": 128
        }
    ],
    "MEDIATOR": {
        "backends": ["llm-router"]
    }
}
```

### Using OpenRouter

To use OpenRouter (requires API key):

```json
{
    "BACKENDS": [
        {
            "id": "llm-router-openrouter",
            "type": "llm_router",
            "provider": "openrouter",
            "model": "anthropic/claude-2",
            "max_tokens": 256
        }
    ]
}
```

Set the environment variable:
```bash
export OPENROUTER_API_KEY="your-api-key"
```

### Auto-detect Provider

Let the router automatically detect the best available provider:

```json
{
    "BACKENDS": [
        {
            "id": "llm-router-auto",
            "type": "llm_router",
            "max_tokens": 256
        }
    ]
}
```

The router will try providers in this order:
1. ipfs_accelerate_py (if available)
2. OpenRouter (if API key is set)
3. Other CLI providers
4. Local HuggingFace models

## Supported Providers

- `local_hf` / `huggingface` - Local HuggingFace transformers
- `openrouter` - OpenRouter API
- `codex_cli` - OpenAI Codex CLI
- `copilot_cli` - GitHub Copilot CLI
- `gemini_cli` - Google Gemini CLI
- `claude_code` - Claude Code CLI
- Auto-detect (no provider specified)

## Environment Variables

- `IPFS_DATASETS_PY_LLM_PROVIDER` - Force a specific provider
- `IPFS_DATASETS_PY_LLM_MODEL` - Default model name
- `OPENROUTER_API_KEY` - OpenRouter API key
- `IPFS_DATASETS_PY_ENABLE_IPFS_ACCELERATE` - Enable accelerate provider

## Example in run.py

Update your `run.py` to use the LLM Router backend:

```python
from backends import LLMRouterBackend

# ... existing code ...

for backend_id in config_mediator['backends']:
    backend_config = next((conf for conf in config_backends if conf['id'] == backend_id), None)
    
    if not backend_config:
        log.error('missing backend configuration "%s" - cannot continue' % backend_id)
        exit(-1)
    
    if backend_config['type'] == 'llm_router':
        backend = LLMRouterBackend(**backend_config)
    elif backend_config['type'] == 'openai':
        backend = OpenAIBackend(**backend_config)
    # ... other backend types ...
    
    backends.append(backend)
```

## Testing

Run the tests to verify the LLM Router backend:

```bash
pytest tests/test_llm_router_backend.py -v
```

## Benefits

1. **Unified Interface**: Single backend type for multiple LLM providers
2. **Flexible**: Easy to switch providers without changing code
3. **Reliable**: Automatic fallback to local models
4. **Modern**: Uses the well-maintained ipfs_datasets_py package
5. **Test-Friendly**: Easy to mock for testing

## Troubleshooting

### Submodule Not Initialized

If you see an error about missing `ipfs_datasets_py`:

```bash
git submodule update --init --recursive
```

### Missing Dependencies

For local HuggingFace models:
```bash
pip install transformers torch
```

For OpenRouter:
```bash
export OPENROUTER_API_KEY="your-api-key"
```

## Next Steps

- Add more backends using different providers
- Configure provider-specific options
- Integrate with ipfs_accelerate_py for distributed inference
- Add model-specific configurations
