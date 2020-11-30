# Some useful functions
import os

def size2integer(bytes, minimum=None):
    power = 'kmg'.find(bytes[-1].lower()) + 1
    file_size = int(bytes[:-1]) * 1024 ** power
    if minimum is not None and file_size < minimum:
        raise ValueError('Provided file_size is too small')
    return file_size

def hook_compressed_encoded(filename, mode):
    encoding="utf-8"
    ext = os.path.splitext(filename)[1]
    if ext == '.gz':
        import gzip
        return gzip.open(filename, mode+"t", encoding=encoding)
    elif ext == '.bz2':
        import bz2
        return bz2.open(filename, mode+"t", encoding=encoding)
    else:
        import io
        return io.open(filename, mode, encoding=encoding)