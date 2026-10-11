import asyncio
import sys
from scrapli import AsyncScrapli

NODES = {
    "A": {"host": "192.168.100.11", "port": 22, "name": "lab1-sw1"},
    "B": {"host": "192.168.100.12", "port": 22, "name": "lab1-sw2"},
    "C": {"host": "192.168.100.13", "port": 22, "name": "lab1-sw3"},
}

async def check_node(key, node):
    device = {
        "host": node["host"],
        "port": node["port"],
        "auth_username": "admin",
        "auth_password": "admin",
        "auth_strict_key": False,
        "platform": "cisco_iosxe",
        "transport": "asyncssh",
        "timeout_socket": 5,
        "timeout_transport": 5,
        "timeout_ops": 10,
    }
    try:
        async with AsyncScrapli(**device) as conn:
            res = await conn.send_command("show version | include Cisco IOS Software")
            print(f"[OK] {key} ({node['name']} @ {node['host']}): {res.result.strip()}", flush=True)
            return True
    except Exception as e:
        print(f"[FAIL] {key} ({node['name']} @ {node['host']}): {e}", flush=True)
        return False

async def main():
    results = await asyncio.gather(*(check_node(k, v) for k, v in NODES.items()))
    if all(results):
        print("All nodes connected successfully!", flush=True)
        sys.exit(0)
    else:
        print("Some nodes failed to connect.", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
