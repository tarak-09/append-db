from pycask import PyCask
import os

with PyCask('./test_db_hint', max_file_size=100) as db:
    db.set(b'key1', b'a' * 50)
    db.set(b'key2', b'b' * 50)
    db.set(b'key3', b'c' * 50)
    db.compact()

print("Files in db:", os.listdir('./test_db_hint'))

with PyCask('./test_db_hint') as db:
    print("key1:", db.get(b'key1'))
