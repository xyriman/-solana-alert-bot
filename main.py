import discord
import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)
alerted_tokens = set()

DEXTREND_URL = (
    "https://dexscreener.com"
    "/?rankBy=pairAge&order=asc"
    "&chainIds=solana&dexIds=meteora&profile=1"
)

API_URL_TEMPLATE = "https://api.dexscreener.com/tokens/v1/solana/{addresses}"
FETCH_LIMIT = 10
ALERT_DIFF = 0.000001

def safe_int(value):
    try:
        return int(float(value))
    except:
        return 0

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

async def send_alert(name, link, fdv, market_cap, price):
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("❌ Channel not found. Check CHANNEL_ID.")
        return
    embed = discord.Embed(title="🚨 Solana Token Alert", color=0xff9900)
    embed.add_field(name="Token", value=name, inline=False)
    embed.add_field(name="Price", value=f"${price}", inline=True)
    embed.add_field(name="FDV", value=f"${fdv:,}", inline=True)
    embed.add_field(name="Market Cap", value=f"${market_cap:,}", inline=True)
    embed.add_field(name="Link", value=link, inline=False)
    await channel.send(embed=embed)

async def scrape_token_addresses():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(DEXTREND_URL, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        links = soup.select("a[href*='/solana/']")
        addresses = []
        for a in links[:FETCH_LIMIT]:
            href = a.get("href")
            addr = href.split("/")[-1]
            addresses.append(addr)
        return addresses
    except Exception as e:
        print(f"Error scraping: {e}")
        return []

async def check_scraped_tokens():
    while True:
        addresses = await scrape_token_addresses()
        new = [a for a in addresses if a not in alerted_tokens]
        if not new:
            await asyncio.sleep(180)
            continue
        url = API_URL_TEMPLATE.format(addresses=",".join(new))
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as res:
                    data = await res.json()
            for token in data:
                base = token.get("baseToken", {})
                addr = base.get("address")
                name = base.get("name", addr)
                price = token.get("priceUsd")
                mcap = token.get("marketCap")
                fdv = token.get("fdv")
                link = f"https://dexscreener.com/solana/{addr}"
                if addr and addr not in alerted_tokens and should_alert(price, mcap, fdv):
                    alerted_tokens.add(addr)
                    await send_alert(name, link, fdv, mcap, price)
        except Exception as e:
            print(f"Error in scraping alert check: {e}")
        await asyncio.sleep(180)

async def check_api_tokens():
    urls = [
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-boosts/top/v1"
    ]
    while True:
        token_addresses = set()
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url) as res:
                        data = await res.json()
                        for token in data:
                            if token.get("chainId") == "solana":
                                addr = token.get("tokenAddress")
                                if addr:
                                    token_addresses.add(addr)
                except Exception as e:
                    print(f"API error: {e}")
            chunks = list(token_addresses)
            for i in range(0, len(chunks), 30):
                batch = chunks[i:i+30]
                api_url = API_URL_TEMPLATE.format(addresses=",".join(batch))
                try:
                    async with session.get(api_url) as res:
                        tokens = await res.json()
                        for token in tokens:
                            base = token.get("baseToken", {})
                            addr = base.get("address")
                            name = base.get("name", addr)
                            price = token.get("priceUsd")
                            mcap = token.get("marketCap")
                            fdv = token.get("fdv")
                            link = f"https://dexscreener.com/solana/{addr}"
                            if addr and addr not in alerted_tokens and should_alert(price, mcap, fdv):
                                alerted_tokens.add(addr)
                                await send_alert(name, link, fdv, mcap, price)
                except Exception as e:
                    print(f"Token check error: {e}")
        await asyncio.sleep(180)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    asyncio.create_task(check_scraped_tokens())
    asyncio.create_task(check_api_tokens())

client.run(DISCORD_TOKEN)
