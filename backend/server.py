"""Local HTTP server + assembled-PCB reference inspection API. Bind to loopback only by default."""
from __future__ import annotations
import argparse
import base64
import binascii
import io
import json
import math
import mimetypes
import sys
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from PIL import Image, ImageOps, UnidentifiedImageError
from inspection import PCBAInspector

ROOT = Path(__file__).resolve().parent.parent
Image.MAX_IMAGE_PIXELS = 20_000_000
warnings.simplefilter('error', Image.DecompressionBombWarning)
DETECTOR = None
MAX_BODY = 24 * 1024 * 1024

class Handler(BaseHTTPRequestHandler):
    server_version = 'PCBInspector/2.0'
    def json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = unquote(urlparse(self.path).path)
        if route == '/api/health':
            return self.json({'app': 'PCB Inspector', 'version': '2.0.0', 'model': DETECTOR.health()})
        if route == '/api/samples':
            path = ROOT / 'samples/manifest.json'
            return self.json(json.loads(path.read_text(encoding='utf-8')) if path.exists() else [])
        if route.startswith('/api/'):
            return self.json({'error': 'API не найден'}, 404)
        base = ROOT / ('samples' if route.startswith('/samples/') else 'frontend')
        relative = route.removeprefix('/samples/') if route.startswith('/samples/') else route.lstrip('/') or 'index.html'
        target = (base / relative).resolve()
        if not target.is_relative_to(base.resolve()) or not target.is_file():
            return self.json({'error': 'Файл не найден'}, 404)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(target)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if urlparse(self.path).path != '/api/analyze':
            return self.json({'error': 'API не найден'}, 404)
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.json({'error': 'Недопустимый источник запроса'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_BODY:
                return self.json({'error': 'Размер запроса должен быть от 1 байта до 24 МБ'}, 413)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Ожидался JSON-объект')
            threshold = float(payload.get('threshold', 0.4))
            if not math.isfinite(threshold) or not 0.1 <= threshold <= 0.9:
                raise ValueError('Порог должен быть от 0.1 до 0.9')
            if payload.get('same_board_confirmed') is not True:
                raise ValueError('Подтвердите, что эталон и проверяемая плата одной модели и ревизии')
            variant = payload.get('variant', '')
            if not isinstance(variant, str) or not variant.strip() or len(variant) > 120:
                raise ValueError('Укажите модель и ревизию платы (до 120 символов)')
            min_area = payload.get('min_area', 40)
            if isinstance(min_area, bool) or not isinstance(min_area, int) or not 8 <= min_area <= 10000:
                raise ValueError('Минимальная площадь должна быть целым числом от 8 до 10000 px')
            roi = payload.get('roi')
            if roi is not None:
                if not isinstance(roi, list) or len(roi) != 4:
                    raise ValueError('ROI должен быть [x1,y1,x2,y2] в диапазоне 0..1')
                roi = [float(v) for v in roi]
                if not all(math.isfinite(v) and 0 <= v <= 1 for v in roi) or roi[2]-roi[0] < .02 or roi[3]-roi[1] < .02:
                    raise ValueError('Некорректная область проверки')
            def decode_image(field):
                encoded = payload.get(field, '')
                if not isinstance(encoded, str):
                    raise ValueError('Изображение должно быть data URL')
                prefix, value = encoded.split(',', 1)
                if prefix not in ('data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'):
                    raise ValueError('Поддерживаются JPEG, PNG и WebP')
                binary = base64.b64decode(value, validate=True)
                with Image.open(io.BytesIO(binary)) as source:
                    if source.width < 32 or source.height < 32 or source.width * source.height > Image.MAX_IMAGE_PIXELS:
                        raise ValueError('Допустимый размер изображения от 32×32 до 20 мегапикселей')
                    return ImageOps.exif_transpose(source).convert('RGB')
            image = decode_image('image')
            reference = decode_image('reference')
            result = DETECTOR.predict(image, reference, threshold, min_area, roi)
            result['variant'] = variant.strip()
            return self.json(result)
        except (ValueError, TypeError, KeyError, binascii.Error, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            return self.json({'error': 'Не удалось прочитать запрос: ' + str(exc)}, 400)
        except RuntimeError as exc:
            return self.json({'error': str(exc)}, 503)
        except Exception as exc:
            print(f'Inference failed: {exc}', file=sys.stderr)
            return self.json({'error': 'Ошибка анализа. Проверьте консоль сервера и конфигурацию модели.'}, 500)

def main():
    global DETECTOR
    parser = argparse.ArgumentParser(description='PCB Inspector local server')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    DETECTOR = PCBAInspector(ROOT / 'config/inspection.json')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        raise SystemExit(f'Не удалось открыть порт {args.port}: {exc}. Используйте --port 8766')
    print(f'PCB Inspector: http://127.0.0.1:{args.port}', flush=True)
    print('Анализатор: ' + ('готов' if DETECTOR.health()['ready'] else DETECTOR.error), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nСервер остановлен')
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
