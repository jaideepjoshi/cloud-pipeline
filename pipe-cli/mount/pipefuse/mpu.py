# Copyright 2017-2020 EPAM Systems, Inc. (https://www.epam.com/)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import sys
from abc import abstractmethod, ABCMeta
from collections import namedtuple

import intervals

from fuseutils import MB, GB

_CopyPart = namedtuple('CopyPart', ['start', 'end', 'offset', 'part_number', 'part_path', 'keep'])


class MultipartUpload:
    __metaclass__ = ABCMeta

    @property
    @abstractmethod
    def path(self):
        pass

    @abstractmethod
    def initiate(self):
        pass

    @abstractmethod
    def upload_part(self, buf, offset=None, part_number=None, part_path=None, keep=False):
        pass

    @abstractmethod
    def upload_copy_part(self, start, end, offset=None, part_number=None, part_path=None, keep=False):
        pass

    @abstractmethod
    def complete(self):
        pass

    @abstractmethod
    def abort(self):
        pass


class MultipartUploadDecorator(MultipartUpload):

    def __init__(self, mpu):
        self._mpu = mpu

    @property
    def path(self):
        return self._mpu.path

    def initiate(self):
        self._mpu.initiate()

    def upload_part(self, buf, offset=None, part_number=None, part_path=None, keep=False):
        self._mpu.upload_part(buf, offset, part_number)

    def upload_copy_part(self, start, end, offset=None, part_number=None, part_path=None, keep=False):
        self._mpu.upload_copy_part(start, end, offset, part_number)

    def complete(self):
        self._mpu.complete()

    def abort(self):
        self._mpu.abort()


class _PartialChunk:

    def __init__(self, offset, size):
        self._offset = offset
        self._size = size
        self._buf = bytearray(size)
        self._bounds_interval = intervals.closed(0, self._size)
        self._interval = intervals.empty()

    @property
    def offset(self):
        return self._offset

    def append(self, offset, buf):
        end = offset + len(buf)
        self._buf[offset:end] = buf[:]
        self._interval |= intervals.closed(offset, end)

    def is_full(self):
        return self._missing_interval().is_empty()

    def missing_intervals(self):
        for interval in self._missing_interval():
            yield interval.lower, interval.upper

    def _missing_interval(self):
        return self._interval.complement().intersection(self._bounds_interval)

    def collect(self):
        return self._buf[:self._interval.upper]


class ChunkedMultipartUpload(MultipartUploadDecorator):

    def __init__(self, mpu, original_size, download, chunk_size, min_chunk, max_chunk):
        """
        Chunked multipart upload.

        Cuts all the incoming uploads into chunks of the given size.

        Has a limit on the maximum file size that can be written using chunked multipart upload.
        It can be calculated multiplying chunk size by max chunk number. F.e. for chunk size of 10MB and 10000 chunks
        it will be 100GB, for chunk size of 100MB and 10000 chunks it will be 1TB.

        Fills gaps between uploaded parts with the copy parts of unlimited size.

        :param mpu: Wrapping multipart upload.
        :param original_size: Destination file original size.
        :param download: Function that retrieves content from an object by its path, offset and length.
        :param chunk_size: Size of a single upload part.
        :param min_chunk: Minimum allowed chunk number.
        :param max_chunk: Maximum allowed chunk number.
        """
        super(ChunkedMultipartUpload, self).__init__(mpu)
        self._mpu = mpu
        self._original_size = original_size
        self._download = download
        self._chunk_size = chunk_size
        self._chunks = set()
        self._partial_chunks = {}
        self._min_chunk = min_chunk
        self._max_chunk = max_chunk

    def upload_part(self, buf, offset=None, part_number=None, part_path=None, keep=False):
        chunk = self._resolve_chunk(offset)
        chunk_offset = self._chunk_offset(chunk)
        chunk_shift = offset - chunk_offset
        buf_shift = 0
        while buf_shift < len(buf):
            if chunk_shift or buf_shift + self._chunk_size - chunk_shift > len(buf):
                partial_chunk = self._partial_chunks.get(chunk, None)
                if not partial_chunk:
                    partial_chunk = _PartialChunk(chunk_offset, self._chunk_size)
                    self._partial_chunks[chunk] = partial_chunk
                partial_chunk.append(chunk_shift, buf[buf_shift:buf_shift + self._chunk_size - chunk_shift])
                if partial_chunk.is_full():
                    self._mpu.upload_part(partial_chunk.collect(), partial_chunk.offset, chunk)
                    del self._partial_chunks[chunk]
            else:
                chunk_buf = bytearray(self._chunk_size)
                chunk_buf[chunk_shift:self._chunk_size] = buf[buf_shift:buf_shift + self._chunk_size]
                self._mpu.upload_part(chunk_buf, chunk_offset, chunk)
            buf_shift += self._chunk_size - chunk_shift
            self._chunks.add(chunk)
            chunk += 1
            chunk_offset += self._chunk_size
            chunk_shift = 0

    def _resolve_chunk(self, offset):
        first_chunk = self._min_chunk
        last_chunk = self._max_chunk
        while last_chunk - first_chunk > 1:
            mid_chunk = first_chunk + (last_chunk - first_chunk) / 2
            mid_chunk_offset = self._chunk_offset(mid_chunk)
            if offset > mid_chunk_offset:
                first_chunk = mid_chunk
            elif offset < mid_chunk_offset:
                last_chunk = mid_chunk
            else:
                return mid_chunk
        return last_chunk if offset >= self._chunk_offset(last_chunk) else first_chunk

    def _chunk_offset(self, chunk):
        return (chunk - 1) * self._chunk_size

    def complete(self):
        last_missing_chunk = 1
        for chunk in sorted(self._chunks):
            if chunk > last_missing_chunk:
                missing_start = self._chunk_offset(last_missing_chunk)
                missing_end = self._chunk_offset(chunk)
                self._mpu.upload_copy_part(missing_start, missing_end, missing_start, last_missing_chunk)
            last_missing_chunk = chunk + 1
        last_chunk_end = self._chunk_offset(last_missing_chunk)
        if last_chunk_end < self._original_size:
            self._mpu.upload_copy_part(last_chunk_end, self._original_size, last_chunk_end, last_missing_chunk)
        for chunk_number, partial_chunk in self._partial_chunks.items():
            for missing_start, missing_end in partial_chunk.missing_intervals():
                actual_start = missing_start + partial_chunk.offset
                actual_end = min(missing_end + partial_chunk.offset, self._original_size)
                if actual_end > actual_start:
                    buf = self._download(self.path, actual_start, actual_end - actual_start)
                    partial_chunk.append(missing_start, buf)
            chunk = partial_chunk.collect()
            self._mpu.upload_part(chunk, partial_chunk.offset, chunk_number)
        self._mpu.complete()


class SplittingMultipartCopyUpload(MultipartUploadDecorator):

    def __init__(self, mpu, min_part_size=5 * MB, max_part_size=5 * GB):
        """
        Splitting multipart copy upload.

        Splits copy upload parts into several ones to fit maximum upload part size limit.
        Also takes into the account minimum upload part size.

        :param mpu: Wrapping multipart upload.
        :param min_part_size: Minimum upload part size.
        :param max_part_size: Maximum upload part size.
        """
        super(SplittingMultipartCopyUpload, self).__init__(mpu)
        self._mpu = mpu
        self._min_part_size = min_part_size
        self._max_part_size = max_part_size

    def upload_copy_part(self, start, end, offset=None, part_number=None, part_path=None, keep=False):
        copy_part_length = end - start
        if copy_part_length > self._max_part_size:
            logging.debug('Splitting upload part into pieces for %s' % self.path)
            remaining_length = copy_part_length
            current_offset = offset
            actual_part_number = part_number
            while remaining_length > 0:
                part_size = self._resolve_part_size(remaining_length)
                self._mpu.upload_copy_part(current_offset, current_offset + part_size, current_offset,
                                           actual_part_number)
                remaining_length -= part_size
                current_offset += part_size
                actual_part_number += 1
        else:
            self._mpu.upload_copy_part(start, end, offset, part_number)

    def _resolve_part_size(self, remaining_length):
        if self._min_part_size <= remaining_length <= self._max_part_size:
            return remaining_length
        else:
            return min(self._max_part_size, remaining_length - self._min_part_size)


class DownloadingMultipartCopyUpload(MultipartUploadDecorator):

    def __init__(self, mpu, download):
        """
        Downloading multipart copy upload.

        Downloads all copy parts from original file and uploads them as regular parts.

        :param mpu: Wrapping multipart upload.
        :param download: Function that retrieves content from an object by its path, offset and length.
        """
        super(DownloadingMultipartCopyUpload, self).__init__(mpu)
        self._mpu = mpu
        self._download = download

    def upload_copy_part(self, start, end, offset=None, part_number=None, part_path=None, keep=False):
        self._mpu.upload_part(self._download(self.path, start, end - start), offset, part_number, part_path, keep)


class AppendOptimizedCompositeMultipartCopyUpload(MultipartUploadDecorator):

    def __init__(self, mpu, original_size, chunk_size, download):
        """
        Append optimized composite multipart copy upload.
        
        Uses original object as a pre uploaded composite part in case of append writes.
        In order to do so it adjusts the first of the already uploaded chunks.

        Uploads copy parts as regular parts using content of the original file.

        :param mpu: Wrapping composite multipart upload.
        :param original_size: Destination file original size.
        :param chunk_size: Size of a single upload part.
        :param download: Function that retrieves content from an object by its path, offset and length.
        """
        super(AppendOptimizedCompositeMultipartCopyUpload, self).__init__(mpu)
        self._mpu = mpu
        self._original_size = original_size
        self._chunk_size = chunk_size
        self._download = download
        self._copy_parts = []
        self._chunks = []
        self._first_chunk = sys.maxint
        self._first_chunk_offset = 0

    def upload_part(self, buf, offset=None, part_number=None, part_path=None, keep=False):
        self._mpu.upload_part(buf, offset, part_number, part_path)
        if part_number < self._first_chunk:
            self._first_chunk = part_number
            self._first_chunk_offset = offset

    def upload_copy_part(self, start, end, offset=None, part_number=None, part_path=None, keep=False):
        self._copy_parts.append(_CopyPart(start, end, offset, part_number, part_path, keep))

    def complete(self):
        prefix_copy_part = self._extract_prefix()
        if prefix_copy_part:
            self._adjust_first_uploaded_part(self._copy_parts[-1].end)
            self._upload_copy_part(prefix_copy_part)
        else:
            self._upload_parts(self._copy_parts)
        self._mpu.complete()

    def _extract_prefix(self):
        if self._copy_parts:
            sorted_copy_parts = sorted(self._copy_parts, key=lambda copy_part: copy_part.offset)
            if sorted_copy_parts[-1].end + self._chunk_size >= self._original_size:
                return _CopyPart(0, self._original_size, offset=0, part_number=1,
                                 part_path=self.path, keep=True)
        return None

    def _adjust_first_uploaded_part(self, prefix_end):
        diff_offset = self._original_size - prefix_end
        if diff_offset > 0:
            part_path = self._mpu.composite_part_path(self._first_chunk)
            self._mpu.upload_part(self._download(part_path, diff_offset, self._chunk_size),
                                  offset=self._first_chunk_offset, part_number=self._first_chunk,
                                  part_path=part_path)

    def _upload_copy_part(self, copy_part):
        self._mpu.upload_copy_part(copy_part.start, copy_part.end, offset=copy_part.offset,
                                   part_number=copy_part.part_number, part_path=copy_part.part_path,
                                   keep=copy_part.keep)
    
    def _upload_parts(self, copy_parts):
        for copy_part in copy_parts:
            self._mpu.upload_part(self._download(self.path, copy_part.start, copy_part.end - copy_part.start),
                                  offset=copy_part.offset, part_number=copy_part.part_number, 
                                  part_path=copy_part.part_path, keep=copy_part.keep)


class CompositeMultipartUpload(MultipartUpload):

    def __init__(self, bucket, path, new_mpu, mv, max_composite_parts=32):
        """
        Composite object multipart upload.
        
        Uploads each part as an independent file then merges all the files into a single composite one.
        
        Takes into the account maximum allowed composite object parts.

        :param bucket: Destination bucket name.
        :param path: Destination bucket relative path.
        :param new_mpu: Function that instantiates new multipart upload.
        :param mv: Function that moves object within bucket.
        :param max_composite_parts: Number of allowed composite object parts.
        """
        self._bucket = bucket
        self._path = path
        self._new_mpu = new_mpu
        self._mv = mv
        self._max_composite_parts = max_composite_parts
        self._bucket_object = None
        self._blob_object = None
        self._mpus = {}

    @property
    def path(self):
        return self._path

    def initiate(self):
        pass

    def upload_part(self, buf, offset=None, part_number=None, part_path=None, keep=False):
        mpu_number = self._mpu_number(part_number)
        mpu = self._get_mpu(mpu_number)
        mpu.upload_part(buf, offset, part_number, self._part_path(mpu_number, part_number), keep)

    def _mpu_number(self, part_number):
        return (part_number - 1) / self._max_composite_parts + 1

    def _get_mpu(self, mpu_number):
        mpu = self._mpus.get(mpu_number, None)
        if not mpu:
            mpu_path = self._mpu_path(mpu_number)
            mpu = self._new_mpu(mpu_path)
            mpu.initiate()
            self._mpus[mpu_number] = mpu
        return mpu

    def upload_copy_part(self, start, end, offset=None, part_number=None, part_path=None, keep=False):
        mpu_number = self._mpu_number(part_number)
        mpu = self._get_mpu(mpu_number)
        mpu.upload_copy_part(start, end, offset, part_number, part_path, keep)

    def complete(self):
        for mpu in self._mpus.values():
            mpu.complete()
        self._compose([(mpu_number, self._mpus[mpu_number]) for mpu_number in sorted(self._mpus.keys())])

    def _compose(self, mpus):
        if not mpus:
            return
        remaining_mpus = list(mpus)
        composed_mpu = None
        while remaining_mpus:
            if composed_mpu:
                merging_mpus = remaining_mpus[:self._max_composite_parts - 1]
                composed_mpu = self._merge([(0, composed_mpu)] + merging_mpus)
                remaining_mpus = remaining_mpus[self._max_composite_parts - 1:]
            else:
                merging_mpus = remaining_mpus[:self._max_composite_parts]
                composed_mpu = self._merge(merging_mpus)
                remaining_mpus = remaining_mpus[self._max_composite_parts:]
            for mpu_number, _ in merging_mpus:
                del self._mpus[mpu_number]
        self._mv(composed_mpu.path, self._path)

    def _merge(self, mpus):
        merged_mpu = self._new_mpu(self._merged_mpu_path(mpus[0][0], mpus[-1][0]))
        merged_mpu.initiate()
        for mpu_number, mpu in mpus:
            merged_mpu.upload_copy_part(None, None, None, mpu_number, mpu.path)
        merged_mpu.complete()
        return merged_mpu

    def abort(self):
        for mpu in self._mpus.values():
            mpu.abort()

    def composite_part_path(self, part_number):
        return self._part_path(self._mpu_number(part_number), part_number)

    def _mpu_path(self, mpu_number):
        return '%s_%s_%d.tmp' % (self._path, self._hashed_path(), mpu_number)

    def _part_path(self, mpu_number, part_number):
        return '%s_%s_%d.%d.tmp' % (self._path, self._hashed_path(), mpu_number, part_number)

    def _merged_mpu_path(self, left_mpu_number, right_mpu_number):
        return '%s_%s_%d:%d.tmp' % (self._path, self._hashed_path(), left_mpu_number, right_mpu_number)

    def _hashed_path(self):
        return str(abs(hash(self._path)))


class TruncatingMultipartCopyUpload(MultipartUploadDecorator):

    def __init__(self, mpu, length, min_part_number=1):
        """
        Truncating multipart copy upload.

        Truncates the file length to the given size which has to be smaller then the original one.

        :param mpu: Wrapping multipart upload.
        :param length: Target size of the truncating file.
        :param min_part_number: Minimal allowed part number. Same as minimum allowed chunk number.
        """
        super(TruncatingMultipartCopyUpload, self).__init__(mpu)
        self._mpu = mpu
        self._length = length
        self._min_part_number = min_part_number

    def complete(self):
        self._mpu.upload_copy_part(start=0, end=self._length, offset=0, part_number=self._min_part_number)
        self._mpu.complete()
