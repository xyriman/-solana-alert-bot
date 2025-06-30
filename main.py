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

def extract_significant_digits(price_str, digits=4):
    try:
        price = float(price_str)
        if price == 0:
            return "0000"
        formatted = f"{price:.12f}".replace('.', '').lstrip('0')
        return formatted[:digits].ljust(digits, '0')
    except:
        return "0000"

async def send_alert(name, link, price_usd, fdv, market_cap, price_4, mcap_4):
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("❌ Channel not found. Check CHANNEL_ID.")
        return
    embed = discord.Embed(title="🚨 Solana Token Alert", color=0xff9900)
    embed.add_field(name="Token", value=name, inline=False)
    embed.add_field(name="Price (USD)", value=price_usd, inline=True)
    embed.add_field(name="FDV", value=f"${fdv:,}", inline=True)
    embed.add_field(name="Market Cap", value=f"${market_cap:,}", inline=True)
    embed.add_field(name="🔢 Price Digits", value=price_4, inline=True)
    embed.add_field(name="🔢 MCap Digits", value=mcap_4, inline=True)
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
            price_usd = token.get("priceUsd", "0")
            fdv = safe_int(token.get("fdv"))
            market_cap = safe_int(token.get("marketCap"))
            price_digits = extract_significant_digits(price_usd)
            mcap_digits = str(market_cap)[:4].ljust(4, '0')

            try:
                price_num = int(price_digits)
                mcap_num = int(mcap_digits)
            except ValueError:
                price_num = 0
                mcap_num = 0

            threshold = 10  # Allowable difference in digits

            link = token.get("url", "https://dexscreener.com")

            if fdv != market_cap or abs(price_num - mcap_num) > threshold:
                alerted_tokens.add(token_address)
                await send_alert(name, link, price_usd, fdv, market_cap, price_digits, mcap_digits)

    except Exception as e:
        print(f"Error checking tokens: {e}")

async def fetch_and_check():
    urls = [
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-boosts/top/v1"
    ]

    token_addresses = set()

    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url) as res:
                    if res.status != 200:
                        print(f"Failed to fetch from {url}")
                        continue
                    data = await res.json()

                    if not isinstance(data, list):
                        print(f"Unexpected format from {url}: expected list")
                        continue

                    for token in data:
                        if isinstance(token, dict) and token.get("chainId") == "solana":
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
        await asyncio.sleep(180)  # Check every 3 minutes

client.run(DISCORD_TOKEN)
