import itertools
import io
import unittest
import uuid
import zipfile

from stream_unzip import stream_unzip


class TestStreamUnzip(unittest.TestCase):

    def test_methods_and_chunk_sizes(self):
        methods = [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED]
        input_sizes = [1, 7, 65536]
        output_sizes = [1, 7, 65536]

        contents = [
            b'short',
            b''.join([uuid.uuid4().hex.encode() for _ in range(0, 100000)])
        ]

        def yield_input(content, method, input_size):
            file = io.BytesIO()
            with zipfile.ZipFile(file, 'w', method) as zf:
                zf.writestr('first.txt', content)
                zf.writestr('second.txt', content)

            zip_bytes = file.getvalue()

            for i in range(0, len(zip_bytes), input_size):
                yield zip_bytes[i:i + input_size]

        combinations_iter = itertools.product(contents, methods, input_sizes, output_sizes)
        for content, method, input_size, output_size in combinations_iter:
            with self.subTest(content=content[:5], method=method, input_size=input_size, output_size=output_size):
                files = [
                    (name, size, b''.join(chunks))
                    for name, size, chunks in stream_unzip(yield_input(content, method, input_size), chunk_size=output_size)
                ]
                self.assertEqual(files[0][0], b'first.txt')
                self.assertEqual(files[0][1], len(content))
                self.assertEqual(files[0][2], content)
                self.assertEqual(files[1][0], b'second.txt')
                self.assertEqual(files[1][1], len(content))
                self.assertEqual(files[1][2], content)

    def test_break_raises_generator_exit(self):
        input_size = 65536
        content = b''.join([uuid.uuid4().hex.encode() for _ in range(0, 100000)])

        raised_generator_exit = False

        def yield_input():
            nonlocal raised_generator_exit

            file = io.BytesIO()
            with zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('first.txt', content)
                zf.writestr('second.txt', content)

            zip_bytes = file.getvalue()

            try:
                for i in range(0, len(zip_bytes), input_size):
                    yield zip_bytes[i:i + input_size]
            except GeneratorExit:
                raised_generator_exit = True

        for name, size, chunks in stream_unzip(yield_input()):
            for chunk in chunks:
                pass
    
        self.assertFalse(raised_generator_exit)

        for name, size, chunks in stream_unzip(yield_input()):
            for chunk in chunks:
                pass
            break

        self.assertTrue(raised_generator_exit)

    def test_streaming(self):
        contents = b''.join([uuid.uuid4().hex.encode() for _ in range(0, 10000)])
        latest = None

        def yield_input():
            nonlocal latest

            file = io.BytesIO()
            with zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('first.txt', contents)

            zip_bytes = file.getvalue()
            chunk_size = 1

            for i in range(0, len(zip_bytes), chunk_size):
                yield zip_bytes[i:i + chunk_size]
                latest = i

        latest_inputs = [[latest for _ in chunks] for _, _, chunks in stream_unzip(yield_input())][0]

        # Make sure the input is progressing during the output. In test, there
        # are about 100k steps, so checking that it's greater than 1000
        # shouldn't make this test too flakey
        num_steps = 0
        prev_i = 0
        for i in latest_inputs:
            if i != prev_i:
                num_steps += 1
            prev_i = i
        self.assertGreater(num_steps, 1000)

    def test_empty_file(self):
        def yield_input():
            file = io.BytesIO()
            with zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('first.txt', b'')

            yield file.getvalue()

        files = [
            (name, size, b''.join(chunks))
            for name, size, chunks in stream_unzip(yield_input())
        ]

        self.assertEqual(files, [(b'first.txt', 0, b'')])

    def test_python_large(self):
        def yield_input():
            with open('fixtures/python38_zip64.zip', 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk

        num_received_bytes = 0
        for name, size, chunks in stream_unzip(yield_input()):
            for chunk in chunks:
                num_received_bytes += len(chunk)

        self.assertEqual(size, 5000000000)
        self.assertEqual(num_received_bytes, 5000000000)

    def test_macos_single_file(self):
        def yield_input():
            with open('fixtures/macos_10_14_5_single_file.zip', 'rb') as f:
                yield f.read()

        num_received_bytes = 0
        files = [(name, size, b''.join(chunks)) for name, size, chunks in stream_unzip(yield_input())]

        self.assertEqual(len(files), 3)
        self.assertEqual(files[0], (b'contents.txt', None, b'Contents of the zip'))

    def test_macos_multiple_files(self):
        def yield_input():
            with open('fixtures/macos_10_14_5_multiple_files.zip', 'rb') as f:
                yield f.read()

        num_received_bytes = 0
        files = [(name, size, b''.join(chunks)) for name, size, chunks in stream_unzip(yield_input())]

        self.assertEqual(len(files), 5)
        self.assertEqual(files[0], (b'first.txt', None, b'Contents of the first file'))
        self.assertEqual(files[1][0], b'__MACOSX/')
        self.assertEqual(files[2][0], b'__MACOSX/._first.txt')
        self.assertEqual(files[3], (b'second.txt', None, b'Contents of the second file'))
        self.assertEqual(files[4][0], b'__MACOSX/._second.txt')
