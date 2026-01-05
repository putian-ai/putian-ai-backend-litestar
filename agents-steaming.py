import asyncio
import os
import random
from agents import Agent, ItemHelpers, Runner, function_tool

# Use the same LitellmModel configuration used in the project so this
# small script runs against the GLM model when available via env vars.
from agents.extensions.models.litellm_model import LitellmModel
from openai.types.responses import ResponseTextDeltaEvent
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from a .env file if present


@function_tool
def how_many_jokes() -> int:
    return random.randint(1, 10)


async def main():
    # Configure GLM model from environment variables (fallbacks to None)
    glm_model = LitellmModel(
        model="openai/glm-4.7",
        api_key=os.getenv("GLM_API_KEY"),
        base_url=os.getenv("GLM_BASE_URL"),
    )

    agent = Agent(
        name="Joker",
        instructions="First call the `how_many_jokes` tool, then tell that many jokes.",
        model=glm_model,
        tools=[how_many_jokes],
    )

    result = Runner.run_streamed(
        agent,
        input="Hello, how many jokes can you tell me(use tool)?",
    )
    print("=== Run starting ===")

    async for event in result.stream_events():
        # The raw response event contains the text deltas
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            print(event.data.delta, end="", flush=True)
        # When the agent updates, print that
        elif event.type == "agent_updated_stream_event":
            print(f"Agent updated: {event.new_agent.name}")
            continue
        # When items are generated, print them
        elif event.type == "run_item_stream_event":
            if event.item.type == "tool_call_item":
                print("-- Tool was called")
            elif event.item.type == "tool_call_output_item":
                print(f"-- Tool output: {event.item.output}")
            elif event.item.type == "message_output_item":
                print(f"-- Message output:\n {ItemHelpers.text_message_output(event.item)}")
            else:
                pass  # Ignore other event types

    print("=== Run complete ===")


if __name__ == "__main__":
    asyncio.run(main())


"""
message output:

-- Tool was called
-- Message output:
 

I'll check how many jokes I can tell you using the tool.

-- Tool output: 6
-- Message output:


I can tell you 6 jokes! Here they are:

1. Why don't scientists trust atoms? Because they make up everything!

2. What do you call a fake noodle? An impasta!

3. Why did the scarecrow win an award? Because he was outstanding in his field!

4. What do you call a bear with no teeth? A gummy bear!

5. Why don't eggs tell jokes? They'd crack each other up!

6. What do you call a sleeping bull? A bulldozer!
=== Run complete ===
"""
