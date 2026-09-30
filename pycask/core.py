import os
import struct
import time
import zlib
import glob
from threading import RLock
from typing import Optional

HEADER_FMT = '<IQHIB'
HEADER_SIZE = struct.calcsize(HEADER_FMT)

FLAG_NORMAL = 0
FLAG_TOMBSTONE = 1

class PyCaskError(Exception):
    pass

class PyCask:
    """
    Embedded key-value database implementing an append-only log with an in-memory index.
    Based on the Bitcask design pattern.
    """
    def __init__(self, directory: str, max_file_size: int = 1024 * 1024 * 100):
        self.directory = directory
        self.max_file_size = max_file_size
        self.keydir = {}  # key -> (file_id, value_size, value_pos, timestamp)
        self.lock = RLock()
        self.active_file_id = None
        self.active_file = None
        self.active_file_size = 0
        
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)
            
        self._load_indexes()

    def _get_data_files(self):
        files = glob.glob(os.path.join(self.directory, '*.data'))
        data_files = []
        for f in files:
            basename = os.path.basename(f)
            try:
                file_id = int(basename.split('.')[0])
                data_files.append((file_id, f))
            except ValueError:
                pass
        return sorted(data_files)
        
    def _load_indexes(self):
        data_files = self._get_data_files()
        
        for file_id, path in data_files:
            with open(path, 'rb') as f:
                while True:
                    header_bytes = f.read(HEADER_SIZE)
                    if not header_bytes or len(header_bytes) < HEADER_SIZE:
                        break
                        
                    crc, ts, ksz, vsz, flags = struct.unpack(HEADER_FMT, header_bytes)
                    
                    key = f.read(ksz)
                    if len(key) < ksz:
                        break
                        
                    value_pos = f.tell()
                    
                    # Verify CRC if needed, skipping for performance during load
                    # Seek past the value
                    f.seek(vsz, os.SEEK_CUR)
                    
                    if flags == FLAG_TOMBSTONE:
                        if key in self.keydir:
                            del self.keydir[key]
                    else:
                        self.keydir[key] = (file_id, vsz, value_pos, ts)
                        
        if data_files:
            last_file_id, last_path = data_files[-1]
            self.active_file_size = os.path.getsize(last_path)
            if self.active_file_size >= self.max_file_size:
                self._open_new_active_file()
            else:
                self.active_file_id = last_file_id
                self.active_file = open(last_path, 'ab')
        else:
            self._open_new_active_file()

    def _open_new_active_file(self):
        if self.active_file:
            self.active_file.close()
        
        new_id = int(time.time() * 1000000)
        if self.active_file_id is not None and new_id <= self.active_file_id:
            new_id = self.active_file_id + 1
            
        self.active_file_id = new_id
        path = os.path.join(self.directory, f"{self.active_file_id}.data")
        self.active_file = open(path, 'ab')
        self.active_file_size = 0
        
    def _encode_record(self, key: bytes, value: bytes, flags: int = FLAG_NORMAL):
        ts = int(time.time() * 1000000)
        ksz = len(key)
        vsz = len(value)
        
        payload = struct.pack('<QHIB', ts, ksz, vsz, flags) + key + value
        crc = zlib.crc32(payload) & 0xffffffff
        
        header = struct.pack('<IQHIB', crc, ts, ksz, vsz, flags)
        return header + key + value, ts
        
    def set(self, key: bytes, value: bytes):
        if not isinstance(key, bytes) or not isinstance(value, bytes):
            raise TypeError("Key and value must be bytes")
            
        if len(key) > 65535:
            raise ValueError("Key is too large (max 65535 bytes)")
            
        with self.lock:
            record_bytes, ts = self._encode_record(key, value, FLAG_NORMAL)
            record_size = len(record_bytes)
            
            if self.active_file_size + record_size > self.max_file_size:
                self._open_new_active_file()
                
            value_pos = self.active_file_size + HEADER_SIZE + len(key)
            
            self.active_file.write(record_bytes)
            self.active_file.flush()
            
            self.keydir[key] = (self.active_file_id, len(value), value_pos, ts)
            self.active_file_size += record_size
            
    def get(self, key: bytes) -> Optional[bytes]:
        if not isinstance(key, bytes):
            raise TypeError("Key must be bytes")
            
        with self.lock:
            if key not in self.keydir:
                return None
                
            file_id, vsz, value_pos, ts = self.keydir[key]
            
            path = os.path.join(self.directory, f"{file_id}.data")
            if not os.path.exists(path):
                raise PyCaskError(f"Data file {file_id}.data not found")
                
            with open(path, 'rb') as f:
                f.seek(value_pos)
                value = f.read(vsz)
                
                # Check consistency
                if len(value) != vsz:
                    raise PyCaskError("Incomplete read from data file")
                    
                return value
                
    def delete(self, key: bytes):
        if not isinstance(key, bytes):
            raise TypeError("Key must be bytes")
            
        with self.lock:
            if key not in self.keydir:
                return
                
            record_bytes, _ = self._encode_record(key, b"", FLAG_TOMBSTONE)
            record_size = len(record_bytes)
            
            if self.active_file_size + record_size > self.max_file_size:
                self._open_new_active_file()
                
            self.active_file.write(record_bytes)
            self.active_file.flush()
            
            self.active_file_size += record_size
            del self.keydir[key]
            
    def compact(self):
        with self.lock:
            data_files = self._get_data_files()
            files_to_compact = [f for f in data_files if f[0] != self.active_file_id]
            
            if not files_to_compact:
                return
                
            compact_dir = os.path.join(self.directory, 'compact')
            if not os.path.exists(compact_dir):
                os.makedirs(compact_dir)
                
            compact_file_id = int(time.time() * 1000000)
            compact_path = os.path.join(compact_dir, f"{compact_file_id}.data")
            
            compact_file = open(compact_path, 'ab')
            compact_size = 0
            
            new_keydir_entries = {}
            
            for key, (file_id, vsz, value_pos, ts) in self.keydir.items():
                if file_id in [f[0] for f in files_to_compact]:
                    old_path = os.path.join(self.directory, f"{file_id}.data")
                    with open(old_path, 'rb') as f:
                        f.seek(value_pos)
                        value = f.read(vsz)
                        
                    record_bytes, new_ts = self._encode_record(key, value, FLAG_NORMAL)
                    new_value_pos = compact_size + HEADER_SIZE + len(key)
                    compact_file.write(record_bytes)
                    compact_size += len(record_bytes)
                    
                    new_keydir_entries[key] = (compact_file_id, vsz, new_value_pos, new_ts)
                    
            compact_file.close()
            
            final_compact_path = os.path.join(self.directory, f"{compact_file_id}.data")
            os.rename(compact_path, final_compact_path)
            
            for file_id, path in files_to_compact:
                os.remove(path)
                
            for key, entry in new_keydir_entries.items():
                self.keydir[key] = entry
                
    def close(self):
        with self.lock:
            if self.active_file:
                self.active_file.close()
                self.active_file = None
                
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
