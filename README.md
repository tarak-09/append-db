# PyCask

PyCask is an embedded key-value database for Python, implementing an append-only log with an in-memory index. It is based on the Bitcask design pattern, which guarantees O(1) read performance requiring only a single disk seek.

## Why it exists?

Sometimes you need a simple, fast embedded database without the overhead of setting up a client-server database like Redis or PostgreSQL. PyCask provides extreme simplicity, high write throughput (append-only), and lightning-fast reads. It reclaims disk space gracefully via an online compaction process.

## Features

- **O(1) Reads:** Every read requires at most one disk seek.
- **High Write Throughput:** Writes are purely append-only operations.
- **Crash Resilience:** Index is built entirely from data files on startup.
- **Transparent Compression:** Values are automatically compressed using zlib if it reduces storage footprint, saving disk space with minimal CPU overhead.
- **Fast Startup (Hint Files):** Compaction generates hint files containing only keys and metadata. Startup scans these lightweight hint files instead of full data files, significantly reducing load time.
- **Non-blocking Compaction:** Merge and reclaim space from deleted or overwritten keys concurrently, without blocking reads and writes.
- **Simple CLI:** Provides a basic command-line interface for interaction.

## Installation

You can install PyCask from source. Assuming you have `uv` or `pip`:

```bash
uv pip install -e .
```

## Usage (Python API)

```python
from pycask import PyCask

# Open or create a new database in the specified directory
with PyCask('./my_data') as db:
    
    # Keys and values must be bytes
    db.set(b'user_123', b'{"name": "Alice", "age": 30}')
    
    # Get a value (returns bytes)
    value = db.get(b'user_123')
    print(value) # Output: b'{"name": "Alice", "age": 30}'
    
    # Delete a key
    db.delete(b'user_123')
    
    # Compact the database to reclaim space
    db.compact()
```

## Usage (CLI)

After installation, the `pycask` command will be available.

```bash
# Set a value
$ pycask -d ./data_dir set mykey "Hello, World!"
OK: Set 'mykey'

# Get a value
$ pycask -d ./data_dir get mykey
Hello, World!

# Delete a value
$ pycask -d ./data_dir delete mykey
OK: Deleted 'mykey'

# Compact the database
$ pycask -d ./data_dir compact
OK: Compaction complete
```

## Running Tests

To run the test suite, install the development dependencies and run `pytest`:

```bash
uv pip install -e ".[dev]"
uv run pytest
```
