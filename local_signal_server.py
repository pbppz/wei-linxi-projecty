# local_signal_server.py - 修复版本地信令服务器
import asyncio
import websockets
import json
import hashlib
from datetime import datetime
import secrets

# 配置
LOCAL_PORT = 8765
STATUS_PORT = 8766
SERVER_TOKEN = secrets.token_urlsafe(16)  # 服务器自身令牌

# 存储连接映射
connections = {}
print(f"[本地信令服务器] 启动令牌: {SERVER_TOKEN}")

async def register_connection(websocket):
    """
    处理新连接 - 修正版
    移除了不兼容的 'path' 参数
    """
    client_id = None
    client_ip = "unknown"
    
    try:
        # 获取客户端IP信息
        try:
            client_ip = websocket.remote_address[0]
        except:
            pass
            
        print(f"[服务器] 新连接尝试，来自: {client_ip}")
        
        # 1. 接收客户端注册信息
        data = await websocket.recv()
        message = json.loads(data)
        
        if message.get('type') == 'register':
            client_id = message['client_id']
            token_hash = message.get('token_hash', '')
            
            # 存储连接信息
            connections[client_id] = {
                'websocket': websocket,
                'ip': client_ip,
                'token_hash': token_hash[:8] if token_hash else '',
                'registered_at': datetime.now().isoformat()
            }
            
            print(f"[服务器] 客户端注册成功: {client_id}")
            print(f"        IP: {client_ip}, 令牌: {token_hash[:8]}...")
            
            # 发送注册确认
            await websocket.send(json.dumps({
                'type': 'registered',
                'server_token': SERVER_TOKEN,
                'client_id': client_id,
                'timestamp': datetime.now().isoformat(),
                'message': '注册成功，等待远程连接'
            }))
            
            # 2. 保持连接活跃，转发消息
            async for msg in websocket:
                try:
                    msg_data = json.loads(msg)
                    msg_type = msg_data.get('type')
                    
                    print(f"[服务器] 收到 {client_id} 的消息: {msg_type}")
                    
                    if msg_type == 'ping':
                        # 回应心跳
                        await websocket.send(json.dumps({
                            'type': 'pong',
                            'timestamp': datetime.now().isoformat()
                        }))
                        
                    elif msg_type == 'handshake':
                        # 握手请求，转发给其他客户端
                        target_id = msg_data.get('target')
                        source = msg_data.get('source', 'unknown')
                        
                        if target_id and target_id in connections:
                            # 转发握手请求
                            await connections[target_id]['websocket'].send(msg)
                            print(f"[服务器] 转发握手: {source} -> {target_id}")
                        else:
                            print(f"[服务器] 未知目标: {target_id}")
                            
                    elif msg_type == 'forward':
                        # 通用消息转发
                        target_id = msg_data.get('target')
                        if target_id and target_id in connections:
                            await connections[target_id]['websocket'].send(
                                json.dumps(msg_data.get('payload', {}))
                            )
                            
                    elif msg_type == 'shutdown':
                        # 关闭连接
                        print(f"[服务器] 客户端 {client_id} 请求关闭")
                        await websocket.send(json.dumps({
                            'type': 'shutdown_ack',
                            'message': '连接关闭确认'
                        }))
                        break
                        
                except json.JSONDecodeError as e:
                    print(f"[服务器] JSON解析错误: {e}")
                    print(f"原始消息: {msg[:100]}...")
                except Exception as e:
                    print(f"[服务器] 消息处理错误: {e}")
                    
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[服务器] 连接关闭: {client_id}, 原因: {e}")
    except Exception as e:
        print(f"[服务器] 处理连接时出错: {e}")
    finally:
        # 清理连接记录
        if client_id and client_id in connections:
            del connections[client_id]
            print(f"[服务器] 清理客户端: {client_id}")

async def status_server(websocket):
    """状态查询接口"""
    try:
        await websocket.send(json.dumps({
            'type': 'status',
            'server': 'local_signal_server',
            'version': '1.0',
            'clients_count': len(connections),
            'clients': list(connections.keys()),
            'server_token': SERVER_TOKEN[:8],
            'timestamp': datetime.now().isoformat(),
            'ports': {
                'main': LOCAL_PORT,
                'status': STATUS_PORT
            }
        }))
    except Exception as e:
        print(f"[状态服务器] 错误: {e}")

async def main():
    """启动服务器"""
    print("\n" + "="*60)
    print("🚀 本地信令服务器 v1.0 - 修复版")
    print("="*60)
    print(f"主服务端口: ws://localhost:{LOCAL_PORT}")
    print(f"状态查询端口: ws://localhost:{STATUS_PORT}")
    print(f"服务器令牌: {SERVER_TOKEN[:8]}...")
    print(f"仅接受 localhost 连接，对外不可见")
    print("="*60)
    
    # 启动主服务器
    main_server = await websockets.serve(
        register_connection, 
        "localhost", 
        LOCAL_PORT
    )
    
    # 启动状态查询服务器
    status_server_instance = await websockets.serve(
        status_server,
        "localhost",
        STATUS_PORT
    )
    
    print(f"[服务器] 主服务已启动: ws://localhost:{LOCAL_PORT}")
    print(f"[服务器] 状态服务已启动: ws://localhost:{STATUS_PORT}")
    print("\n✅ 服务器准备就绪，等待客户端连接...")
    print("按 Ctrl+C 停止服务器")
    print("="*60)
    
    # 保持服务器运行
    try:
        await asyncio.Future()  # 永久运行
    except asyncio.CancelledError:
        print("\n[服务器] 正在关闭...")
    finally:
        # 关闭服务器
        main_server.close()
        status_server_instance.close()
        await main_server.wait_closed()
        await status_server_instance.wait_closed()
        print("[服务器] 已完全关闭")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[服务器] 被用户中断，正在关闭...")
    except Exception as e:
        print(f"[服务器] 运行时错误: {e}")
    finally:
        print("[服务器] 程序结束")