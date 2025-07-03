import discord
import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

DEXTREND_URL = (
    "https://dexscreener.com"
    "/?rankBy=pairAge&order=asc"
    "&chainIds=solana&dexIds=meteora&profile=1"
)
API_URL_TEMPLATE = "https://api.dexscreener.com/tokens/v1/solana/{addresses}"
FETCH_LIMIT = 10  # Number of tokens to check each cycle
ALERT_DIFF = 0.000001  # Threshold for price/mcap alert

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
seen_tokens = set()

def should_alert(price, mcap, fdv):
    try:
        price = float(price)
        mcap = float(mcap)
        fdv = float(fdv)
    except (TypeError, ValueError):
        return False

    if abs(fdv - mcap) >= 1:
        return True

    price_scaled = price * 1e9
    price_digits = str(int(price_scaled))[:4]
    mcap_digits = str(int(mcap))[:4]
    if price_digits != mcap_digits:
        if abs(price_scaled - mcap) >= ALERT_DIFF * 1e9:
            return True

    return False

async def get_token_addresses():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(DEXTREND_URL, headers={"User-Agent":"Mozilla/5.0"}) as resp:
                text = await resp.text()
        soup = BeautifulSoup(text, "html.parser")
        links = soup.select("a[href*='/solana/']")
        addresses = []
        for a in links[:FETCH_LIMIT]:
            href = a.get("href")
            addr = href.split("/")[-1]
            addresses.append(addr)
        return addresses
    except Exception as e:
        print(f"Error scraping token addresses: {e}")
        return []

async def fetch_token_data(addresses):
    if not addresses:
        return []
    url = API_URL_TEMPLATE.format(addresses=",".join(addresses))
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.json()
    except Exception as e:
        print(f"Error fetching token data: {e}")
        return []

async def check_tokens_loop():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)

    while True:
        token_addresses = await get_token_addresses()
        new_tokens = [t for t in token_addresses if t not in seen_tokens]

        if new_tokens:
            token_data_list = await fetch_token_data(new_tokens)

            for token_data in token_data_list:
                base_token = token_data.get("baseToken", {})
                addr = base_token.get("address")
                name = base_token.get("name", addr)
                price = token_data.get("priceUsd")
                market_cap = token_data.get("marketCap")
                fdv = token_data.get("fdv")

                if addr and should_alert(price, market_cap, fdv):
                    seen_tokens.add(addr)
                    msg = (
                        f"🚨 **Mismatch detected** for **{name}**\n"
                        f"Price USD: `{price}`\n"
                        f"Market Cap: `{market_cap}`\n"
                        f"FDV: `{fdv}`\n"
                        f"<https://dexscreener.com/solana/{addr}>"
                    )
                    await channel.send(msg)

        await asyncio.sleep(180)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.loop.create_task(check_tokens_loop())

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)


