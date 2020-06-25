import io
import logging
from abc import abstractmethod, ABCMeta

from pipefuse import fuseutils
from pipefuse.fsclient import FileSystemClient, FileSystemClientDecorator
from pipefuse.fuseutils import MB

_ANY_ERROR = Exception


class StorageLowLevelFileSystemClient(FileSystemClient):
    __metaclass__ = ABCMeta

    def exists(self, path):
        pass

    def mkdir(self, path):
        pass

    def rmdir(self, path):
        pass

    def upload_range(self, fh, buf, path, offset):
        pass

    def flush(self, fh, path):
        pass

    @abstractmethod
    def new_mpu(self, source_path, file_size, download):
        pass


class StorageHighLevelFileSystemClient(FileSystemClientDecorator):

    def __init__(self, inner):
        """
        Cloud storage high level file system client.

        It contains most of the common code between all cloud storage provider implementations.

        :param inner: Decorating storage low level file system client.
        """
        super(StorageHighLevelFileSystemClient, self).__init__(inner)
        self._inner = inner
        self._delimiter = '/'
        self._single_upload_size = 5 * MB
        self._mpus = {}

    def exists(self, path):
        return len(self.ls(path)) > 0

    def upload(self, buf, path):
        destination_path = path.lstrip(self._delimiter)
        self._inner.upload(buf, destination_path)

    def delete(self, path):
        source_path = path.lstrip(self._delimiter)
        self._inner.delete(source_path)

    def mv(self, old_path, path):
        source_path = old_path.lstrip(self._delimiter)
        destination_path = path.lstrip(self._delimiter)
        folder_source_path = fuseutils.append_delimiter(source_path)
        if self.exists(folder_source_path):
            self._mvdir(folder_source_path, destination_path)
        else:
            self._mvfile(source_path, destination_path)

    def _mvdir(self, old_path, path):
        for file in self.ls(fuseutils.append_delimiter(old_path), depth=-1):
            relative_path = fuseutils.without_prefix(file.name, old_path)
            destination_path = fuseutils.join_path_with_delimiter(path, relative_path)
            self._mvfile(file.name, destination_path)

    def _mvfile(self, source_path, destination_path):
        self._inner.mv(source_path, destination_path)

    def mkdir(self, path):
        synthetic_file_path = fuseutils.join_path_with_delimiter(path, '.DS_Store')
        self.upload([], synthetic_file_path)

    def rmdir(self, path):
        for file in self.ls(fuseutils.append_delimiter(path), depth=-1):
            self.delete(file.name)

    def download_range(self, fh, buf, path, offset=0, length=0):
        source_path = path.lstrip(self._delimiter)
        self._inner.download_range(fh, buf, source_path, offset, length)

    def upload_range(self, fh, buf, path, offset=0):
        source_path = path.lstrip(self._delimiter)
        mpu = self._mpus.get(path, None)
        try:
            if not mpu:
                file_size = self.attrs(path).size
                buf_size = len(buf)
                if buf_size < self._single_upload_size and file_size < self._single_upload_size:
                    logging.info('Using single range upload approach')
                    self._upload_single_range(fh, buf, source_path, offset, file_size)
                else:
                    logging.info('Using multipart upload approach')
                    mpu = self._inner.new_mpu(source_path, file_size, self._generate_region_download_function())
                    self._mpus[path] = mpu
                    mpu.initiate()
                    mpu.upload_part(buf, offset)
            else:
                mpu.upload_part(buf, offset)
        except _ANY_ERROR:
            if mpu:
                mpu.abort()
                del self._mpus[path]
            raise

    def _generate_region_download_function(self):
        def download(path, region_offset, region_length):
            with io.BytesIO() as buf:
                self.download_range(None, buf, path, region_offset, region_length)
                return buf.getvalue()
        return download

    def _upload_single_range(self, fh, buf, path, offset, file_size):
        if file_size:
            with io.BytesIO() as original_buf:
                self.download_range(fh, original_buf, path, offset=0, length=file_size)
                modified_bytes = bytearray(original_buf.getvalue())
        else:
            modified_bytes = bytearray()
        modified_bytes[offset: offset + len(buf)] = buf
        logging.info('Uploading range %d-%d for %s' % (offset, offset + len(buf), path))
        self.upload(modified_bytes, path)

    def flush(self, fh, path):
        mpu = self._mpus.get(path, None)
        if mpu:
            try:
                mpu.complete()
            except _ANY_ERROR:
                mpu.abort()
                raise
            finally:
                del self._mpus[path]

    def truncate(self, fh, path, length):
        source_path = path.lstrip(self._delimiter)
        self._inner.truncate(fh, source_path, length)
