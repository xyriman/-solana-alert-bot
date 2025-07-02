import discord
import asyncio
import aiohttp
import os
from dotenv import load_dotenv
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

alerted_tokens = set()

def safe_int(value):
    try:
        return int(float(value))
    except:
        return 0

async def send_alert(name, link, fdv, market_cap):
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("❌ Channel not found. Check CHANNEL_ID.")
        return
    embed = discord.Embed(title="🚨 Solana Token Alert", color=0xff9900)
    embed.add_field(name="Token", value=name, inline=False)
    embed.add_field(name="FDV", value=f"${fdv:,}", inline=True)
    embed.add_field(name="Market Cap", value=f"${market_cap:,}", inline=True)
    embed.add_field(name="Link", value=link, inline=False)
    await channel.send(embed=embed)

async def check_tokens(session, token_addresses):
    if not token_addresses:
        return
    url = f"https://api.dexscreener.com/tokens/v1/solana/{','.join(token_addresses)}"
    try:
        async with session.get(url) as res:
            if res.status != 200:
                print(f"Failed to fetch token details: {res.status}")
                return
            data = await res.json()

        for token in data:
            base = token.get("baseToken", {})
            token_address = base.get("address", "")
            if token_address in alerted_tokens:
                continue

            name = base.get("name", "Unknown")
            fdv = safe_int(token.get("fdv"))
            market_cap = safe_int(token.get("marketCap"))
            link = token.get("url", "https://dexscreener.com")

            if fdv != market_cap and fdv > 0 and market_cap > 0:
                alerted_tokens.add(token_address)
                await send_alert(name, link, fdv, market_cap)

    except Exception as e:
        print(f"Error checking tokens: {e}")

async def fetch_and_check():
    dex_urls = [
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-boosts/top/v1"
    ]

    token_addresses = set()

    async with aiohttp.ClientSession() as session:
        for url in dex_urls:
            try:
                async with session.get(url) as res:
                    if res.status != 200:
                        print(f"Failed to fetch from {url}")
                        continue
                    data = await res.json()
                    if isinstance(data, list):
                        for token in data:
                            if token.get("chainId") == "solana":
                                token_address = token.get("tokenAddress")
                                if token_address:
                                    token_addresses.add(token_address)
            except Exception as e:
                print(f"Error fetching from {url}: {e}")

        token_list = list(token_addresses)
        for i in range(0, len(token_list), 30):
            chunk = token_list[i:i + 30]
            await check_tokens(session, chunk)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    while True:
        await fetch_and_check()
        await asyncio.sleep(180)  # every 3 minutes

client.run(DISCORD_TOKEN)

