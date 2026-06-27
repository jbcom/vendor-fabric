# Getting Started

Install the core package when you only need discovery, configuration loading,
and lazy framework selection:

```bash
pip install vendor-fabric
```

Install the runtime extras you actually use:

```bash
pip install "vendor-fabric[crewai]"
pip install "vendor-fabric[langgraph]"
pip install "vendor-fabric[strands]"
```

SecretSync and vendor integrations are optional extras. They do not load during
core package import.

```bash
pip install "vendor-fabric[secrets-sync]"
pip install "vendor-fabric[google]"
pip install "vendor-fabric[slack]"
```

```python
from vendor_fabric.agentic import detect_framework, get_runner

framework = detect_framework()
runner = get_runner(framework)
```

The CLI command installed by the package is `vendor-fabric-agent`.
