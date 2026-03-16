import asyncio
from telethon import TelegramClient
from data.const import TELEGRAM_CHANNELS
from data.const import TELEGRAM_API_ID, TELEGRAM_API_HASH

PHONE = '+380689451550'   # твой номер, только для первой авторизации


async def main():
    client = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)

    await client.start(phone=PHONE)

    print("Авторизация прошла")

    entity = await client.get_entity("@Fashionista_drop")
    print(entity)

asyncio.run(main())