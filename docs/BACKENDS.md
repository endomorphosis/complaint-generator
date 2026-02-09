# Backend Systems

Complete guide to the backend systems that power the complaint generator's LLM routing and integrations.

## Overview

The complaint generator uses a flexible backend architecture that supports multiple LLM providers through a unified interface. The system includes:

1. **LLM Router Backend** - Multi-provider routing with automatic fallback
2. **Provider-Specific Backends** - Direct integrations with OpenAI, HuggingFace, etc.
3. **Workstation Backend** - Local model inference
4. **IPFS Integration** - Distributed storage and content addressing

## LLM Router Backend (`backends/llm_router_backend.py`)

The primary backend that routes requests to multiple LLM providers with automatic fallback.

### Supported Providers

- **OpenRouter** - Access to multiple models through a unified API
- **HuggingFace** - Open-source models via HuggingFace API
- **Copilot CLI** - GitHub Copilot integration
- **Codex** - OpenAI Codex models
- **Gemini** - Google Gemini models
- **Claude** - Anthropic Claude models
- **Workstation** - Local model inference

### Configuration

Configure via JSON configuration file (e.g., `config.llm_router.json`):

```json
{
  "BACKENDS": [
    {
      "id": "llm-router",
      "type": "llm_router",
      "provider": "copilot_cli",
      "model": "gpt-5-mini",
      "max_tokens": 128,
      "temperature": 0.7
    }
  ],
  "MEDIATOR": {
    "backends": ["llm-router"]
  }
}
```

### Key Parameters

- **provider** - LLM provider to use (required)
- **model** - Specific model name (required)
- **max_tokens** - Maximum response length (default: 128)
- **temperature** - Sampling temperature 0.0-1.0 (default: 0.7)
- **top_p** - Nucleus sampling parameter (optional)
- **frequency_penalty** - Penalize token frequency (optional)
- **presence_penalty** - Penalize token presence (optional)

### Usage

```python
from backends import LLMRouterBackend

backend = LLMRouterBackend(
    id='llm-router',
    provider='copilot_cli',
    model='gpt-5-mini',
    max_tokens=256,
    temperature=0.7
)

# Generate text
response = backend.generate(
    prompt="Extract legal claims from: [complaint text]",
    max_tokens=500
)

print(response)
```

### Automatic Fallback

The LLM Router automatically falls back to alternative providers if the primary provider fails:

```python
# Configure with fallback chain
backend = LLMRouterBackend(
    id='llm-router',
    provider='copilot_cli',  # Primary
    fallback_providers=['openai', 'huggingface'],  # Fallbacks
    model='gpt-5-mini'
)

# Request will try copilot_cli first, then openai, then huggingface
response = backend.generate(prompt)
```

### Rate Limiting

Built-in rate limiting prevents API throttling:

```python
backend = LLMRouterBackend(
    id='llm-router',
    provider='openai',
    model='gpt-4',
    rate_limit=60,  # Requests per minute
    rate_limit_window=60  # Window in seconds
)
```

### Batch Processing

Support for parallel batch requests:

```python
prompts = [
    "Analyze complaint 1...",
    "Analyze complaint 2...",
    "Analyze complaint 3..."
]

responses = backend.batch_generate(
    prompts=prompts,
    max_workers=4,  # Parallel workers
    timeout=30  # Timeout per request
)

for prompt, response in zip(prompts, responses):
    print(f"Prompt: {prompt[:50]}...")
    print(f"Response: {response[:100]}...\n")
```

## OpenAI Backend (`backends/openai.py`, `backends/openaibackend.py`)

Direct integration with OpenAI's API.

### Configuration

```json
{
  "BACKENDS": [
    {
      "id": "openai",
      "type": "openai",
      "api_key": "${OPENAI_API_KEY}",
      "model": "gpt-4",
      "max_tokens": 500
    }
  ]
}
```

### Environment Variables

```bash
export OPENAI_API_KEY="sk-..."
```

### Usage

```python
from backends import OpenAIBackend

backend = OpenAIBackend(
    id='openai',
    api_key='sk-...',
    model='gpt-4',
    max_tokens=500
)

response = backend.generate(prompt="Your prompt here")
```

## HuggingFace Backend (`backends/huggingface.py`)

Integration with HuggingFace's model hub.

### Configuration

```json
{
  "BACKENDS": [
    {
      "id": "huggingface",
      "type": "huggingface",
      "api_key": "${HUGGINGFACE_API_KEY}",
      "model": "mistralai/Mistral-7B-Instruct-v0.1",
      "max_tokens": 500
    }
  ]
}
```

### Environment Variables

```bash
export HUGGINGFACE_API_KEY="hf_..."
```

### Usage

```python
from backends import HuggingFaceBackend

backend = HuggingFaceBackend(
    id='huggingface',
    api_key='hf_...',
    model='mistralai/Mistral-7B-Instruct-v0.1',
    max_tokens=500
)

response = backend.generate(prompt="Your prompt here")
```

## Workstation Backend (`backends/workstation.py`)

Local model inference using GGUF models with llama.cpp.

### Configuration

```json
{
  "BACKENDS": [
    {
      "id": "workstation",
      "type": "workstation",
      "model_path": "/path/to/model.gguf",
      "n_ctx": 4096,
      "n_threads": 8
    }
  ]
}
```

### Usage

```python
from backends import WorkstationBackend

backend = WorkstationBackend(
    id='workstation',
    model_path='/path/to/model.gguf',
    n_ctx=4096,
    n_threads=8
)

response = backend.generate(prompt="Your prompt here")
```

### Advantages

- **No API costs** - Run models locally
- **Privacy** - Data never leaves your machine
- **Offline capability** - Works without internet
- **Customization** - Full control over model parameters

## IPFS Integration (`ipfs_datasets_py` submodule)

The system integrates with IPFS (InterPlanetary File System) for distributed, content-addressable storage.

### Features

- **Evidence Storage** - Store evidence immutably on IPFS
- **Content Addressing** - Reference evidence by cryptographic hash (CID)
- **Distributed Storage** - Evidence is replicated across IPFS nodes
- **Verification** - Content integrity guaranteed by CID

### Usage

```python
from mediator import Mediator

mediator = Mediator(backends=[backend])

# Submit evidence to IPFS
result = mediator.submit_evidence(
    data=b"Document content...",
    evidence_type='document',
    description='Performance review',
    claim_type='wrongful_termination'
)

print(f"Evidence CID: {result['cid']}")

# Retrieve evidence by CID
evidence = mediator.get_evidence_by_cid(result['cid'])
print(f"Retrieved: {evidence['description']}")
```

### Configuration

IPFS integration is configured via the `ipfs_datasets_py` submodule. No additional configuration needed - the system automatically initializes IPFS when available.

## Backend Selection Strategy

### By Use Case

- **Production Applications** - Use LLM Router with OpenRouter or OpenAI
- **Development/Testing** - Use Copilot CLI for free access
- **Privacy-Sensitive** - Use Workstation backend with local models
- **Cost-Conscious** - Use HuggingFace or local models
- **Research** - Use LLM Router with multiple providers for comparison

### By Performance

- **Fastest** - OpenAI GPT-4 Turbo, Claude 3
- **Best Quality** - OpenAI GPT-4, Claude 3 Opus
- **Most Economical** - HuggingFace, local models
- **Most Reliable** - LLM Router with fallback chain

### By Features

- **Batch Processing** - LLM Router with parallel workers
- **Long Context** - Claude 3 (100k tokens), GPT-4 Turbo (128k tokens)
- **Function Calling** - OpenAI GPT-4, GPT-3.5-turbo
- **Fine-Tuning** - OpenAI, HuggingFace

## Error Handling

All backends implement consistent error handling:

```python
from backends import LLMRouterBackend
from backends.exceptions import (
    BackendError,
    RateLimitError,
    AuthenticationError,
    ModelNotFoundError
)

backend = LLMRouterBackend(id='llm', provider='openai', model='gpt-4')

try:
    response = backend.generate(prompt)
except RateLimitError as e:
    print(f"Rate limit exceeded: {e}")
    # Wait and retry
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
    # Check API key
except ModelNotFoundError as e:
    print(f"Model not found: {e}")
    # Try different model
except BackendError as e:
    print(f"Backend error: {e}")
    # Fallback to alternative backend
```

## Monitoring and Logging

Enable verbose logging for debugging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)

backend = LLMRouterBackend(
    id='llm',
    provider='openai',
    model='gpt-4',
    verbose=True  # Enable verbose logging
)

# Now all API calls will be logged
response = backend.generate(prompt)
```

## Testing

Backends include comprehensive test coverage:

```bash
# Test LLM Router backend
pytest tests/test_llm_router_backend.py -v

# Test all backends
pytest tests/test_backends.py -v
```

## Best Practices

1. **Use Configuration Files** - Store backend config in JSON files, not code
2. **Environment Variables** - Store API keys in environment variables, never in code
3. **Enable Fallbacks** - Configure fallback providers for reliability
4. **Monitor Costs** - Track API usage and costs
5. **Cache Responses** - Cache LLM responses when possible to reduce costs
6. **Implement Retries** - Use exponential backoff for transient failures
7. **Test Locally First** - Test with local models before deploying to production
8. **Use Appropriate Models** - Match model capabilities to task requirements

## See Also

- [docs/LLM_ROUTER.md](LLM_ROUTER.md) - Detailed LLM Router documentation
- [config.llm_router.json](../config.llm_router.json) - Example configuration
- [tests/test_llm_router_backend.py](../tests/test_llm_router_backend.py) - Backend tests
- [ipfs_datasets_py/](../ipfs_datasets_py/) - IPFS integration submodule
