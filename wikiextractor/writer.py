import bz2
import os
from io import TextIOWrapper


class NextFile(object):
    """
    Synchronous generation of next available file name.
    Name will have the form AB/wiki_56
    """

    def __init__(self, path_name: str, filesPerDir: int = 100) -> None:
        self.path_name = path_name
        self.filesPerDir = filesPerDir
        self.dir_index = -1
        self.file_index = -1

    def __next__(self) -> None:
        self.file_index = (self.file_index + 1) % self.filesPerDir
        if self.file_index == 0:
            self.dir_index += 1
        dirname = self.int2base26()
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        return self.filepath()

    def int2base26(self) -> str:
        n = self.dir_index
        chars = []
        while True:
            chars.append(chr(ord('A') + (n % 26)))
            n //= 26
            if n <= 0:
                break
        return os.path.join(self.path_name, "".join(reversed(chars)))

    def filepath(self) -> None:
        file_number = format(self.file_index, f"0{len(str(self.filesPerDir))}d")
        return f'{self.int2base26()}/wiki_{file_number}'


class OutputSplitter(object):
    """
    File-like object, that splits output to multiple files of a given max size.
    """
    def __init__(self, nextFile: NextFile, max_file_size: int = 0, compress: bool = True) -> None:
        self.nextFile = nextFile
        self.compress = compress
        self.max_file_size = max_file_size
        self.file = self.open(next(self.nextFile))

    def reserve(self, size: int) -> None:
        if self.file.tell() + size > self.max_file_size:
            self.close()
            self.file = self.open(next(self.nextFile))

    def write(self, data: str) -> None:
        self.reserve(len(data))
        self.file.write(data)

    def close(self) -> None:
        self.file.close()

    def open(self, filename: str) -> TextIOWrapper:
        if self.compress:
            return bz2.BZ2File(filename + '.bz2', 'w')
        else:
            return open(filename, 'w')
