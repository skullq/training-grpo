import asyncio
import logging
from scrapli import AsyncScrapli

logging.basicConfig(level=logging.DEBUG)

async def test():
    device = {
        "host": "192.168.100.11",
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
            print("Connected!", flush=True)
            res = await conn.send_command("show spanning-tree summary")
            print("Command output:", res.result, flush=True)
    except Exception as e:
        print("Error:", e, flush=True)

if __name__ == "__main__":
    asyncio.run(test())
