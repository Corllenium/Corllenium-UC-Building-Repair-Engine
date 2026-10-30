"""Static server for the local dashboard export that can open paths longer than 260 characters on Windows.

`python -m http.server` answers 404 for the deep preview files (MTL, textures), so the model preview fails.
"""
import argparse
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class LongPathHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        translated = super().translate_path(path)
        if os.name == 'nt' and not translated.startswith('\\\\?\\'):
            translated = '\\\\?\\' + os.path.abspath(translated)
        return translated

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4192)
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    handler = functools.partial(LongPathHandler, directory=os.path.abspath(args.root))
    ThreadingHTTPServer(('127.0.0.1', args.port), handler).serve_forever()


if __name__ == '__main__':
    main()
