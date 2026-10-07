import os
import shutil
import tempfile
import threading
import time
import pytest
from pycask import PyCask, PyCaskError

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

def test_set_and_get(temp_dir):
    with PyCask(temp_dir) as db:
        db.set(b"key1", b"value1")
        assert db.get(b"key1") == b"value1"
        assert db.get(b"key2") is None

def test_delete(temp_dir):
    with PyCask(temp_dir) as db:
        db.set(b"key1", b"value1")
        db.delete(b"key1")
        assert db.get(b"key1") is None

def test_persistence(temp_dir):
    # Write some data
    with PyCask(temp_dir) as db:
        db.set(b"key1", b"value1")
        db.set(b"key2", b"value2")
        db.delete(b"key1")
    
    # Reload and check
    with PyCask(temp_dir) as db:
        assert db.get(b"key1") is None
        assert db.get(b"key2") == b"value2"

def test_file_rollover(temp_dir):
    # Set a very small max_file_size to force rollover
    with PyCask(temp_dir, max_file_size=100) as db:
        db.set(b"key1", b"a" * 50)
        db.set(b"key2", b"b" * 50)
        db.set(b"key3", b"c" * 50)
        
        # Check that we have multiple data files
        files = os.listdir(temp_dir)
        data_files = [f for f in files if f.endswith('.data')]
        assert len(data_files) > 1
        
        assert db.get(b"key1") == b"a" * 50
        assert db.get(b"key2") == b"b" * 50
        assert db.get(b"key3") == b"c" * 50

def test_compaction(temp_dir):
    with PyCask(temp_dir, max_file_size=200) as db:
        # Write many updates to the same key to create garbage
        for i in range(10):
            db.set(b"key_changing", f"value_{i}".encode())
            
        db.set(b"key_stable", b"stable_value")
        
        # Force a file rollover by writing a large key so that previous files can be compacted
        large_uncompressible = os.urandom(300)
        db.set(b"key_large", large_uncompressible)
        
        # Current data files
        files_before = [f for f in os.listdir(temp_dir) if f.endswith('.data')]
        assert len(files_before) > 1
        
        db.compact()
        
        # Verify data is still intact
        assert db.get(b"key_changing") == b"value_9"
        assert db.get(b"key_stable") == b"stable_value"
        assert db.get(b"key_large") == large_uncompressible

def test_type_errors(temp_dir):
    with PyCask(temp_dir) as db:
        with pytest.raises(TypeError):
            db.set("string_key", b"value")
        with pytest.raises(TypeError):
            db.get("string_key")
        with pytest.raises(TypeError):
            db.delete("string_key")

def test_concurrent_compaction(temp_dir):
    with PyCask(temp_dir, max_file_size=500) as db:
        # Write some data to force multiple files
        for i in range(50):
            db.set(f"key_{i}".encode(), b"value")
            
        def compact_worker():
            db.compact()
            
        # Start compaction in a background thread
        t = threading.Thread(target=compact_worker)
        t.start()
        
        # Concurrently write and update data while compaction is running
        for i in range(50, 100):
            db.set(f"key_{i}".encode(), b"value_new")
            
        # Update a key that is in the old files being compacted
        db.set(b"key_0", b"value_updated")
        
        t.join()
        
        # Verify both old compacted data and new concurrent writes exist correctly
        assert db.get(b"key_1") == b"value"
        assert db.get(b"key_0") == b"value_updated"
        assert db.get(b"key_99") == b"value_new"

def test_hint_files(temp_dir):
    with PyCask(temp_dir, max_file_size=200) as db:
        db.set(b"key1", b"value1")
        db.set(b"key2", b"value2")
        db.set(b"key_large", os.urandom(300))
        
        db.compact()
        
    files = os.listdir(temp_dir)
    hint_files = [f for f in files if f.endswith('.hint')]
    assert len(hint_files) == 1
    
    # Reload and check (it should use the hint file)
    with PyCask(temp_dir) as db:
        assert db.get(b"key1") == b"value1"
        assert db.get(b"key2") == b"value2"

def test_compression(temp_dir):
    with PyCask(temp_dir) as db:
        compressible_value = b"a" * 1000
        uncompressible_value = os.urandom(1000)
        
        db.set(b"comp", compressible_value)
        db.set(b"uncomp", uncompressible_value)
        
        # Check sizes in keydir
        comp_vsz = db.keydir[b"comp"][1]
        uncomp_vsz = db.keydir[b"uncomp"][1]
        
        assert comp_vsz < 1000  # Should be compressed significantly
        assert uncomp_vsz >= 1000 # Should not be compressed
        
        assert db.get(b"comp") == compressible_value
        assert db.get(b"uncomp") == uncompressible_value
