import os
import json
import responder
import logging
import subprocess
import shlex
import time
import uuid
from starlette.websockets import WebSocketDisconnect
from uvicorn.config import get_logger
from datetime import datetime


api = responder.API()
env = os.environ.get('PYENV', 'DEBUG')
jp2a = os.environ.get('JP2A', None)

__version__ = 'v0.0.1'
__author__ = "JG (之及)"


def toStr(byte, errors="ignore"):
    return byte.decode('utf-8', errors=errors)


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

                filename = uuid.uuid4().hex

                with open(f'{filename}.jpeg', 'wb') as f:
                    f.write(_content)
                
                await ws.send_json({
                    'type': 'upload',
                    'status': True,
                    "output": "Upload successfully!"
                })
                continue

            
            params = json.loads(message['text'])
            class_names = ""

            if not jp2a:
                rc, cmd, err = run_command('which jp2a') 

                if rc != 0:
                    await ws.send_json({
                        'status': False,
                        "output": "jp2a not found",
                        "class": class_names
                    })
            else:
                cmd = jp2a
            
            cmd = f"{cmd.strip()} {filename}.jpeg --width=80"

            if 'background' in params:
                cmd = f'{cmd} --background=' + params["background"]
                class_names += f' {params["background"]}'

            if 'width' in params:
                cmd = f'{cmd} --width=' + params["width"]
                class_names += f' width{params["width"]}'

            rc, out, err = run_command(cmd)

            if rc == 0:
                await ws.send_json({
                    'status': True,
                    "output": out,
                    "class": class_names
                })
            else:
                await ws.send_json({
                    'status': True,
                    "output": out.strip() + err.strip(),
                    "class": class_names
                })
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
