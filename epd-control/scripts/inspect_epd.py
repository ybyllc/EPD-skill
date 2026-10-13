"""Read EPD firmware/configuration without uploading or refreshing an image."""
import argparse
import asyncio
import json
from pathlib import Path

from bleak import BleakClient, BleakScanner

EPD_CHAR = "62750002-d828-918d-fb46-b6c11c675aec"
VERSION_CHAR = "62750003-d828-918d-fb46-b6c11c675aec"
CONFIG_FIELDS = (
    "mosi_pin", "sclk_pin", "cs_pin", "dc_pin", "rst_pin", "busy_pin",
    "bs_pin", "model_id", "wakeup_pin", "led_pin", "en_pin",
    "display_mode", "week_start",
)


async def inspect(args):
    print(f"扫描 {args.name} …", flush=True)
    device = await BleakScanner.find_device_by_name(args.name, timeout=args.timeout)
    if device is None:
        raise RuntimeError("未发现目标设备；请唤醒屏幕，并断开其他手机或网页的连接。")
    result = {"name": device.name, "address": device.address}
    async with BleakClient(device, timeout=args.timeout) as client:
        version_char = client.services.get_characteristic(VERSION_CHAR)
        if version_char is not None:
            version = await client.read_gatt_char(version_char)
            result["firmware_hex"] = bytes(version).hex()
            if bytes(version).startswith(b"v"):
                result["firmware_text"] = bytes(version).rstrip(b"\0").decode("ascii", errors="replace")
        else:
            result["firmware_hex"] = None
        received = asyncio.Event()

        def notify(sender, data):
            if not received.is_set():
                result["config_hex"] = bytes(data).hex()
                result["config"] = dict(zip(CONFIG_FIELDS, data))
                result["config_extra_hex"] = bytes(data[len(CONFIG_FIELDS):]).hex()
                received.set()

        await client.start_notify(EPD_CHAR, notify)
        try:
            await asyncio.wait_for(received.wait(), timeout=10)
        finally:
            await client.stop_notify(EPD_CHAR)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="NRF_EPD_A571")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--output", help="保存实际读取的设备信息到 JSON")
    try:
        asyncio.run(inspect(parser.parse_args()))
    except (RuntimeError, asyncio.TimeoutError) as exc:
        raise SystemExit(f"探测失败：{exc}")
