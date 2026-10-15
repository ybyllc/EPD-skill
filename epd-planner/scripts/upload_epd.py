"""Upload a 400x300 image; negotiate legacy/bit flags and optional RLE."""
import argparse
import asyncio
import re
import time

from bleak import BleakClient, BleakScanner, BleakError
from PIL import Image
from inspect_epd import EPD_CHAR


def encode_planes(image):
    if image.size != (400, 300):
        raise ValueError("图片必须为 400×300，不自动裁剪。")
    rgba = image.convert("RGBA")
    image = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")
    black, red = bytearray([255] * 15000), bytearray([255] * 15000)
    raw = image.tobytes()
    for index in range(120000):
        r, g, b = raw[index*3:index*3+3]
        mask = 1 << (7-index % 8)
        if r > 160 and r > g and r > b:
            red[index//8] &= ~mask
        elif .299*r + .587*g + .114*b < 140:
            black[index//8] &= ~mask
    return bytes(black), bytes(red)


def rle_compress(data):
    out = bytearray()
    i = 0
    while i < len(data):
        run = 1
        while i+run < len(data) and run < 130 and data[i+run] == data[i]:
            run += 1
        if run >= 3:
            out.extend((0x80 | (run-3), data[i]))
            i += run
        else:
            start = i
            while i < len(data) and i-start < 128:
                if i+2 < len(data) and data[i] == data[i+1] == data[i+2]:
                    break
                i += 1
            out.append(i-start-1)
            out.extend(data[start:i])
    return bytes(out)


def rle_chunks(data, max_chunk):
    """Bound encoded AND decoded packet size (firmware has a 255-byte buffer)."""
    if max_chunk < 2:
        raise ValueError("RLE requires at least 2 payload bytes")
    # Compress <=255 source bytes independently; never split a codeword.
    chunks = []
    for offset in range(0, len(data), 255):
        encoded = rle_compress(data[offset:offset+255])
        packet = bytearray()
        i = 0
        while i < len(encoded):
            ctrl = encoded[i]
            size = 2 if ctrl & 128 else ctrl+2
            if size > max_chunk:
                # Split a literal into MTU-sized literal codewords.
                literal = encoded[i+1:i+size]
                words = [bytes((len(literal[j:j+max_chunk-1])-1,)) + literal[j:j+max_chunk-1]
                         for j in range(0, len(literal), max_chunk-1)]
            else:
                words = [encoded[i:i+size]]
            for word in words:
                if len(packet)+len(word) > max_chunk:
                    chunks.append(bytes(packet))
                    packet.clear()
                packet.extend(word)
            i += size
        if packet:
            chunks.append(bytes(packet))
    return chunks


def build_blocks(planes, chunk_size, use_rle, modern=True):
    if chunk_size < 1 or (use_rle and not modern):
        raise ValueError("Invalid packet size or RLE on legacy protocol")
    blocks = []
    for plane, data in enumerate(planes):
        pieces = rle_chunks(data, chunk_size) if use_rle else [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
        for number, piece in enumerate(pieces):
            if modern:
                flag = plane | (2 if number == 0 else 0) | (4 if use_rle else 0)
            else:
                flag = (15 if plane == 0 else 0) | (240 if number else 0)
            blocks.append((flag, piece))
    return blocks


async def upload(args, progress):
    with Image.open(args.image) as image:
        planes = encode_planes(image)
    target = args.address or args.name
    print(f"扫描 {target} …", flush=True)
    # An explicit address selects a device; never fall back to another name.
    device = await (BleakScanner.find_device_by_address(target, timeout=20) if args.address
                    else BleakScanner.find_device_by_name(target, timeout=20))
    if device is None:
        raise RuntimeError("未找到设备，请唤醒屏幕并断开其他连接。")
    async with BleakClient(device, timeout=20) as client:
        config_event, mtu_event = asyncio.Event(), asyncio.Event()
        state = {}
        def notify(sender, data):
            raw = bytes(data)
            message = raw.decode("ascii", errors="replace")
            if message.startswith("mtu="):
                match = re.match(r"mtu=(\d+)", message)
                if match:
                    state["mtu"] = int(match.group(1))
                    state["modern"] = bool(re.search(r"\brle=1\b", message))
                    mtu_event.set()
            elif not config_event.is_set() and len(raw) >= 8:
                state["config"] = raw
                config_event.set()
        await client.start_notify(EPD_CHAR, notify)
        try:
            await asyncio.wait_for(config_event.wait(), 10)
            if state["config"][7] != 3:
                raise RuntimeError("型号不是已验证的 UC8176 400×300 三色，停止。")
            await client.write_gatt_char(EPD_CHAR, b"\x01", response=True)
            await asyncio.wait_for(mtu_event.wait(), 10)
            chunk_size = min(state["mtu"], client.mtu_size-3, 244)-2
            use_rle = state["modern"] and not args.no_rle
            blocks = build_blocks(planes, chunk_size, use_rle, state["modern"])
            print(f"共 {len(blocks)} 块 / {sum(len(p) for _, p in blocks)} 字节，RLE={use_rle}", flush=True)
            print(f"INIT 后等待 {args.settle} 秒…", flush=True)
            await asyncio.sleep(args.settle)
            started = time.monotonic()
            progress["writing"] = True
            for flag, payload in blocks:
                await client.write_gatt_char(EPD_CHAR, bytes((0x30, flag))+payload, response=True)
            # Set BEFORE await: a lost response does not prove refresh was not sent.
            progress["refresh_attempted"] = True
            await client.write_gatt_char(EPD_CHAR, b"\x05", response=True)
            print(f"刷新指令已确认（传输 {time.monotonic()-started:.1f} 秒）。", flush=True)
            await asyncio.sleep(25)
        finally:
            if client.is_connected:
                try:
                    await client.stop_notify(EPD_CHAR)
                except (BleakError, OSError):
                    pass
    print("上传完成；实体显示效果仍需查看屏幕。", flush=True)


async def run(args):
    for attempt in range(2):
        progress = {"writing": False, "refresh_attempted": False}
        try:
            await upload(args, progress)
            return
        except (BleakError, OSError, asyncio.TimeoutError) as exc:
            if progress["refresh_attempted"]:
                raise RuntimeError("已尝试发送刷新，结果可能未知；为避免重复刷新，不自动重传。") from exc
            if isinstance(exc, asyncio.TimeoutError) and not progress["writing"]:
                raise RuntimeError("配置/能力查询超时，停止，不猜测协议。") from exc
            if attempt:
                raise
            print(f"连接/写入中断：{exc}；未尝试刷新，5秒后整图重试一次。", flush=True)
            await asyncio.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--name", default="NRF_EPD_A571", help="目标广播名；其他设备请明确指定")
    parser.add_argument("--address", help="显式指定目标地址（macOS使用系统设备UUID）；优先于名字，无默认地址")
    parser.add_argument("--settle", type=float, default=8, help="INIT后等待秒数，默认8，仅排查时调整")
    parser.add_argument("--no-rle", action="store_true", help="关闭压缩但保留设备协商出的协议格式")
    args = parser.parse_args()
    if args.settle < 0:
        parser.error("--settle must be non-negative")
    asyncio.run(run(args))
