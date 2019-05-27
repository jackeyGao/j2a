import os
import json
import responder
import logging
import hashlib
import subprocess
import shlex
import time
import uuid
from pathlib import Path
from starlette.websockets import WebSocketDisconnect
from uvicorn.config import get_logger
from datetime import datetime



api = responder.API()
env = os.environ.get('PYENV', 'DEBUG')
jp2a_path = os.environ.get('JP2A', None)

__version__ = 'v0.0.1'
__author__ = "JG (之及)"


def toStr(byte, errors="ignore"):
    return byte.decode('utf-8', errors=errors)


def content_process(output):
    if not output.startswith('<?xml'):
        return output
        
    for line in output.split('\n'):
        if not line.startswith('<span'):
            continue

        if not line.endswith('</pre>'):
            continue

        return line.replace('</pre>', '')

    return output


def run_command(command, timeout=10):
    start_time = time.time()

    process = subprocess.Popen(
        shlex.split(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    stdout = b''
    while True:
        output = process.stdout.readline()

        if time.time() - start_time >= timeout:
            process.kill()
            return -426, f'执行超时, timeout为{timeout}秒', ''

        if output == b'' and process.poll() is not None:
            break
        if output:
            stdout += output

    rc = process.poll()

    return rc, toStr(stdout), toStr(process.stderr.read())


def jp2a(filename, params):
    class_names = ""
    filename = params['filename'] or filename

    if not jp2a_path:
        rc, cmd, err = run_command('which jp2a') 

        if rc != 0:
            return {
                'status': False,
                "output": "jp2a not found",
                "class": class_names
            }
    else:
        cmd = jp2a_path
    
    cmd = f"{cmd.strip()} ./static/images/{filename}.jpeg --width=80"

    if 'background' in params:
        cmd = f'{cmd} --background=' + params["background"]
        class_names += f' {params["background"]}'

    if 'width' in params:
        cmd = f'{cmd} --width=' + params["width"]
        class_names += f' width{params["width"]}'

    if 'colors' in params:
        if params['colors'] == 'html':
            cmd = f'{cmd} --colors --html'
            class_names += f' colors'

        if params['colors'] == 'ansi':
            cmd = f'{cmd} --colors'
            class_names += f' ansi'


    rc, out, err = run_command(cmd)

    if rc == 0:
        return {
            'status': True,
            "output": content_process(out),
            "class": class_names
        }
    else:
       return { 
            'status': True,
            "output": out.strip() + err.strip(),
            "class": class_names
        }


def __initalize_runserver__():
    if env == 'DEBUG':
        log_level = 'info'
    else:
        log_level = 'info'

    logger = get_logger(log_level)

    logger.debug('Running on debug')
    logger.info('Database is ready')


    api.run(address="0.0.0.0", debug=env=='DEBUG', logger=logger)


@api.route('/')
async def index(req, resp):
    resp.html = api.template('index.html')


@api.route('/{filename}')
async def share(req, resp, *, filename):
    resp.html = api.template('index.html', **locals())


@api.route('/ws', websocket=True)
async def websocket(ws):
    await ws.accept()

    filename = ""

    while True:
        try:
            message = await ws.receive()

            ws._raise_on_disconnect(message)

            if 'bytes' in message:
                _content = message['bytes']
                
                filename = hashlib.md5(_content).hexdigest()

                with open(f'./static/images/{filename}.jpeg', 'wb') as f:
                    f.write(_content)

                api.whitenoise.add_files(str(api.static_dir))
                
                await ws.send_json({
                    'type': 'upload',
                    'status': True,
                    'filename': filename,
                    "output": "Upload successfully!"
                })
                continue

            params = json.loads(message['text'])
            class_names = ""
            filename = params['filename'] or filename
            jp2a_resp = jp2a(filename, params)

            await ws.send_json(jp2a_resp)
        except WebSocketDisconnect as e:
            break

    await ws.close()



@api.route('/ping')
async def ping(req, resp):
    resp.media = {
        "_": "pong",
        "version": __version__,
        "author": __author__,
    }


if __name__ == '__main__':
    __initalize_runserver__()
