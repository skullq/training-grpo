import asyncio
from scrapli import AsyncScrapli

async def test():
    device_params = {
        "host": "192.168.100.11",
        "port": 22,
        "auth_username": "admin",
        "auth_password": "admin",
        "auth_strict_key": False,
        "platform": "cisco_iosxe",
        "transport": "asyncssh",
        "timeout_socket": 10,
        "timeout_transport": 10,
        "timeout_ops": 15,
    }
    print("Testing Scrapli connection to 192.168.100.11...")
    async with AsyncScrapli(**device_params) as conn:
        res = await conn.send_command("show spanning-tree")
        print("Scrapli response received:")
        print(res.result[:200])

if __name__ == "__main__":
    asyncio.run(test())
