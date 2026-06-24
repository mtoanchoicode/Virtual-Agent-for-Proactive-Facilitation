import asyncio
import subprocess
import base64
import aiofiles

async def exec_command(command: str):
    print(f"[helpers] executing command: {command}")
    loop = asyncio.get_event_loop()

    def run_sync():
        return subprocess.run(command, shell=True, capture_output=True, text=True)

    result = await loop.run_in_executor(None, run_sync)
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise Exception(f"Command failed with code {result.returncode}: {error_msg}")
    return result.stdout

async def audio_file_to_base64(file_path: str) -> str:
    async with aiofiles.open(file_path, mode="rb") as f:
        data = await f.read()
        return base64.b64encode(data).decode("utf-8")
