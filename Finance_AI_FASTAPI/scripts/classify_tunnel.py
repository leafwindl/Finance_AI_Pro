#!/usr/bin/env python3
"""
classify_tunnel.py — 远程六库分类模型 SSH 隧道（本地端口转发）

把本地 127.0.0.1:8001 转发到服务器 127.0.0.1:8000（分类推理服务），
Gateway 只需 httpx 调 http://127.0.0.1:8001/classify_batch 即可，零依赖。

不改服务器任何东西；隧道退出即关闭连接。

运行（系统 python，需已装 paramiko；密码用环境变量 REMOTE_SSH_PASS）：
    $env:REMOTE_SSH_PASS = "服务器密码"
    python scripts/classify_tunnel.py
    python scripts/classify_tunnel.py --local-port 8001

验证：另开终端 curl http://127.0.0.1:8001/health
"""

import argparse
import os
import socket
import sys
import threading

LOCAL_HOST = "127.0.0.1"
REMOTE_HOST = "172.22.121.55"
REMOTE_SSH_PORT = 50009
REMOTE_USER = "root"
REMOTE_TARGET = ("127.0.0.1", 8000)  # 服务器本机的分类推理服务


def _pipe(src, dst):
    """双向转发一个方向的数据。"""
    try:
        while True:
            data = src.recv(65535)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass


def _handle_conn(local_sock, transport):
    """为一条本地连接打开到服务器 127.0.0.1:8000 的 direct-tcpip 通道。"""
    try:
        chan = transport.open_channel(
            "direct-tcpip", REMOTE_TARGET, local_sock.getpeername()
        )
    except Exception as exc:
        print(f"[tunnel] 打开远程通道失败: {exc}", file=sys.stderr)
        try:
            local_sock.close()
        except Exception:
            pass
        return
    threading.Thread(target=_pipe, args=(local_sock, chan), daemon=True).start()
    threading.Thread(target=_pipe, args=(chan, local_sock), daemon=True).start()


def main() -> int:
    p = argparse.ArgumentParser(description="远程分类模型 SSH 隧道")
    p.add_argument("--local-port", type=int, default=8001, help="本地监听端口（默认 8001）")
    p.add_argument("--host", default=REMOTE_HOST, help="服务器地址")
    p.add_argument("--ssh-port", type=int, default=REMOTE_SSH_PORT, help="SSH 端口")
    p.add_argument("--user", default=REMOTE_USER, help="SSH 用户")
    args = p.parse_args()

    password = os.environ.get("REMOTE_SSH_PASS", "")
    if not password:
        print("错误：请设置环境变量 REMOTE_SSH_PASS 提供服务器密码", file=sys.stderr)
        return 1

    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            args.host, port=args.ssh_port, username=args.user,
            password=password, timeout=20,
        )
    except Exception as exc:
        print(f"SSH 连接失败: {exc}", file=sys.stderr)
        return 1

    transport = client.get_transport()

    listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listen.bind((LOCAL_HOST, args.local_port))
    except OSError as exc:
        print(f"本地端口 {args.local_port} 绑定失败（可能已被占用）: {exc}", file=sys.stderr)
        client.close()
        return 1
    listen.listen(100)

    print(
        f"SSH 隧道就绪: {LOCAL_HOST}:{args.local_port} "
        f"-> {args.host}:{REMOTE_TARGET[1]}  (Ctrl+C 退出)"
    )
    print("测试: curl http://127.0.0.1:%d/health" % args.local_port)

    try:
        while True:
            local_sock, _ = listen.accept()
            threading.Thread(
                target=_handle_conn, args=(local_sock, transport), daemon=True
            ).start()
    except KeyboardInterrupt:
        print("\n隧道已停止")
    finally:
        try:
            listen.close()
        except Exception:
            pass
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
