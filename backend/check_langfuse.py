import langfuse
print(f"Version: {langfuse.__version__}")
# Try known import paths
paths = [
    "langfuse.callback",
    "langfuse.callbacks",
    "langfuse.langchain",
    "langfuse.decorators",
    "langfuse.openai",
]
for p in paths:
    try:
        __import__(p)
        print(f"  OK: {p}")
    except ImportError:
        print(f"  MISS: {p}")
