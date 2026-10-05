import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server = StdioServerParameters(
        command="npx",
        args=["-y", "@bitget-ai/bitget-agent-mcp", "--read-only"],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for search in ["stock", "equity", "tokenized", "US stock"]:
                print(f"\n=== SEARCH: {search} ===")

                result = await session.call_tool(
                    "discover",
                    {"search": search}
                )

                for content in result.content:
                    print(content)

asyncio.run(main())
