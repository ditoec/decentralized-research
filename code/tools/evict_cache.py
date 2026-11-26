#!/usr/bin/env python3
"""Drop our own files from the page cache (posix_fadvise DONTNEED; no root, touches nothing else).

On the GB10 unified memory, CUDA context creation can fail with out of memory while page cache is
high even though MemAvailable is fine (2026-11-26). Usage: evict_cache.py "<glob>" ...
"""
n = 0
for pat in sys.argv[1:]:
    for d in glob.glob(os.path.expanduser(pat)):
        for root, _, files in os.walk(d):
            for f in files:
                try:
                    fd = os.open(os.path.join(root, f), os.O_RDONLY)
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED); os.close(fd); n += 1
                except OSError:
                    pass
print("evicted", n, "files")
