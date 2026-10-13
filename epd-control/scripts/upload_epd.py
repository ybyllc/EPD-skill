"""Upload a 400x300 RGB image to the verified UC8176 BWR screen."""
import argparse
import asyncio
import re
import time

from bleak import BleakClient, BleakScanner
from PIL import Image

from inspect_epd import EPD_CHAR


def encode_planes(image):
    if image.size != (400, 300):
        raise ValueError("图片必须为 400×300，不自动裁剪。")
    black = bytearray([255] * 15000)
    red = bytearray([255] * 15000)
    for index, (r, g, b) in enumerate(image.convert("RGB").getdata()):
        offset, bit = divmod(index, 8)
        mask = 1 << (7 - bit)
        if r > 160 and r > g and r > b:
            red[offset] &= ~mask
        elif 0.299 * r + 0.587 * g + 0.114 * b < 140:
            black[offset] &= ~mask
    return bytes(black), bytes(red)


async def upload(args):
    with Image.open(args.image) as image:
        planes = encode_planes(image)
    print(f"扫描 {args.name} …", flush=True)
    device = await BleakScanner.find_device_by_name(args.name, timeout=20)
    if device is None:
        raise RuntimeError("未找到设备，请唤醒屏幕并断开其他连接。")
    async with BleakClient(device, timeout=20) as client:
        config_event, mtu_event = asyncio.Event(), asyncio.Event()
        state = {}

        def notify(sender, data):
            if not config_event.is_set():
                state["config"] = bytes(data)
                config_event.set()
                return
            message = bytes(data).decode("ascii", errors="replace")
            if message.startswith("mtu="):
                match = re.match(r"mtu=(\d+)", message)
                if match:
                    state["mtu"] = int(match.group(1))
                    state["rle"] = "rle=1" in message
                    print("设备传输能力：" + message, flush=True)
                    mtu_event.set()

        await client.start_notify(EPD_CHAR, notify)
        try:
            await asyncio.wait_for(config_event.wait(), 10)
            config = state["config"]
            if len(config) < 8 or config[7] != 3:
                raise RuntimeError("屏幕配置不是已验证的 UC8176 400×300 三色，已停止。")
            await client.write_gatt_char(EPD_CHAR, b"\x01", response=True)
            await asyncio.wait_for(mtu_event.wait(), 10)
            chunk_size = min(state["mtu"], client.mtu_size - 3, 244) - 2
            if chunk_size < 1:
                raise RuntimeError("设备返回的传输长度无效。")
            started = time.monotonic()
            for plane_index, data in enumerate(planes):
                total = (len(data) + chunk_size - 1) // chunk_size
                for number, offset in enumerate(range(0, len(data), chunk_size)):
                    if state["rle"]:
                        flag = plane_index | (2 if offset == 0 else 0)
                    else:
                        flag = (15 if plane_index == 0 else 0) | (0 if offset == 0 else 240)
                    packet = bytes((0x30, flag)) + data[offset:offset + chunk_size]
                    await client.write_gatt_char(EPD_CHAR, packet, response=True)
                    if number % 20 == 0 or number + 1 == total:
                        print(f"{'黑' if plane_index == 0 else '红'}色平面 {number + 1}/{total}", flush=True)
            await client.write_gatt_char(EPD_CHAR, b"\x05", response=True)
            print(f"图片写入完成，刷新指令已确认（传输 {time.monotonic() - started:.1f} 秒）。等待屏幕刷新…", flush=True)
            await asyncio.sleep(25)
        finally:
            if client.is_connected:
                await client.stop_notify(EPD_CHAR)
    print("已断开蓝牙。实际显示效果请查看实体屏幕。", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--name", default="NRF_EPD_A571")
    asyncio.run(upload(parser.parse_args()))
