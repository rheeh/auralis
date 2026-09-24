#!/usr/bin/env python3
"""Start/reuse the local workspace. No dependency install, tests or model calls."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '.local-data'
FRONT = 'http://127.0.0.1:5176'
BACK = 'http://127.0.0.1:8200'
HTTP = build_opener(ProxyHandler({}))


def get(path, origin=False):
    request = Request(path, headers={'Origin': FRONT} if origin else {})
    with HTTP.open(request, timeout=3) as response:
        return response.read().decode('utf-8')


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def verify_owner(port, directory, database=None):
    """Never reuse another checkout/database just because the port is open."""
    pids = subprocess.check_output(['/usr/sbin/lsof', '-t', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN'], text=True).split()
    for pid in set(pids):
        cwd = subprocess.check_output(['/usr/sbin/lsof', '-a', '-p', pid, '-d', 'cwd', '-Fn'], text=True)
        if f'n{directory}\n' not in cwd:
            raise RuntimeError(f'端口 {port} 被其他程序或仓库占用；没有停止它，也没有切换端口。')
        if database:
            files = subprocess.check_output(['/usr/sbin/lsof', '-p', pid, '-Fn'], text=True)
            if f'n{database}\n' not in files:
                raise RuntimeError(f'端口 {port} 未使用预期数据目录 {DATA}，已停止打开。')


def ensure(port, command, cwd, logfile, probe, env):
    if listening(port):
        verify_owner(port, cwd, DATA / 'app_test.db' if port == 8200 else None)
        probe()
        print(f'复用服务：{port}')
        return
    with logfile.open('ab') as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{port} 启动退出，请查看 {logfile}')
        try:
            probe()
            verify_owner(port, cwd, DATA / 'app_test.db' if port == 8200 else None)
            print(f'已启动服务：{port}')
            return
        except (OSError, ValueError, RuntimeError):
            time.sleep(.3)
    raise RuntimeError(f'{port} 未在 30 秒内就绪，请查看 {logfile}；再次双击可重试连接。')


def check_backend():
    value = json.loads(get(BACK + '/health', origin=True))
    if value.get('application') != 'auralis' or not value.get('ready'):
        raise RuntimeError('8200 不是就绪的 Auralis 服务。')


def check_frontend():
    source = get(FRONT + '/src/api/config.js')
    if 'IS_STATIC_DEMO' not in source or 'API_BASE_URL' not in source:
        raise RuntimeError('5176 不是 Auralis 开发网页。')
    # Vite serializes its effective environment on the first line.
    envline = next((line for line in source.splitlines() if line.startswith('import.meta.env = ')), '')
    config, _ = json.JSONDecoder().raw_decode(envline.removeprefix('import.meta.env = '))
    if config.get('MODE') != 'development' or config.get('VITE_API_BASE_URL', BACK).rstrip('/') != BACK:
        raise RuntimeError('5176 指向测试或 Demo 环境；请关闭该前端后重新启动。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-open', action='store_true', help='只启动和核对服务，不打开浏览器')
    args = parser.parse_args()
    python = ROOT / 'SonicVale/.venv/bin/python'
    vite = ROOT / 'sonicvale-front/node_modules/vite/bin/vite.js'
    node = shutil.which('node')
    if not python.is_file() or not vite.is_file() or not node:
        raise RuntimeError('本地运行依赖不完整，请先按 README 安装；快捷入口不会自动安装或升级。')
    if not (DATA / 'app_test.db').is_file():
        raise RuntimeError(f'找不到现有项目数据库：{DATA}/app_test.db；已停止，避免误建空库。')
    logs = DATA / 'launcher'
    logs.mkdir(exist_ok=True)
    with (logs / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        env = dict(os.environ, AURALIS_CONFIG_DIR=str(DATA), VITE_API_BASE_URL=BACK)
        for key in ('AURALIS_TEST_OFFLINE', 'AURALIS_INSTANCE_TOKEN', 'PYTHONPATH'):
            env.pop(key, None)
        ensure(8200, [str(python), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8200'],
               ROOT / 'SonicVale', logs / 'backend.log', check_backend, env)
        ensure(5176, [node, str(vite), '--host', '127.0.0.1', '--port', '5176', '--strictPort'],
               ROOT / 'sonicvale-front', logs / 'frontend.log', check_frontend, env)
        projects = json.loads(get(BACK + '/projects/', origin=True))
        assets = json.loads(get(BACK + '/sound-library/assets', origin=True))
        for response in (projects, assets):
            if response.get('code') != 200 or not isinstance(response.get('data'), list):
                raise RuntimeError('项目或素材读取失败，未完成基础检查。')
        print(f"基础检查通过：{len(projects['data'])} 个项目，{len(assets['data'])} 项素材。")
        print(f'项目：{FRONT}/#/projects\n素材：{FRONT}/#/sound-library\n数据：{DATA}')
        if not args.no_open:
            command = ['/usr/bin/open']
            if Path('/Applications/Tabbit Browser.app').exists():
                command += ['-a', 'Tabbit Browser']
            subprocess.run([*command, FRONT + '/#/projects'], check=True)
        print('Auralis 已就绪，可以关闭此终端窗口。服务在后台运行，重复双击会复用。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'无法打开 Auralis：{error}', file=sys.stderr)
        sys.exit(1)
