import asyncio
import os

from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    glm_model = LitellmModel(
        model="openai/glm-4.7",
        api_key=os.getenv("GLM_API_KEY"),
        base_url=os.getenv("GLM_BASE_URL"),
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
            model=glm_model,
            mcp_servers=[server],
        )
        result = await Runner.run(agent, "What's the weather in tokyo?")
    print(result.final_output)  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
