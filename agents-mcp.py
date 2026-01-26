import asyncio
import os

from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    deepseek_model = LitellmModel(
        model="deepseek/deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
    )

    async with MCPServerStdio(
        name="playwright",
        params={
            "command": "bunx",
            "args": ["@playwright/mcp@latest"],
        },
        client_session_timeout_seconds=300,
    ) as server:
        agent = Agent(
            name="Assistant",
            instructions="Use the playwright tool to help user.",
            model=deepseek_model,
            mcp_servers=[server],
        )
        result = await Runner.run(agent, "What's the weather in tokyo?")
    print(result.final_output)  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
