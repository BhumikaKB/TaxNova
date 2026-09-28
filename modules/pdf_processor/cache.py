"""
In-memory cache for extracted PDF text, keyed by a hash of the file's
bytes (not filename - two different filenames with identical content
should hit the same cache entry, and a re-upload of the same file
under any name should skip re-parsing).

PRODUCTION NOTE (see scalability section in the project docs): this
is a single-process dict cache, which works for a student deployment
or a single Flask instance but will NOT be shared across multiple
worker processes/machines. When this app scales past one process
(e.g. gunicorn with >1 worker, or multiple hosts behind a load
balancer), swap this for Redis with the same get/set interface -
the extractor code calling into this module wouldn't need to change.
"""

import hashlib
from collections import OrderedDict

_MAX_ENTRIES = 200
_cache = OrderedDict()


def hash_file_bytes(file_bytes):
    return hashlib.sha256(file_bytes).hexdigest()


def get_cached_text(file_hash):
    if file_hash in _cache:
        _cache.move_to_end(file_hash)
        return _cache[file_hash]
    return None


def set_cached_text(file_hash, text):
    _cache[file_hash] = text
    _cache.move_to_end(file_hash)
    if len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)  # evict oldest
