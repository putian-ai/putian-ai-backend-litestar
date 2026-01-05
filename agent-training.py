import os
from typing import cast

from ace import (
    Curator,
    EnvironmentResult,
    Generator,
    LLMClient,
    OfflineAdapter,
    Playbook,
    Reflector,
    Sample,
    TaskEnvironment,
)
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class SimpleEnvironment(TaskEnvironment):
    """Minimal environment for testing."""

    def evaluate(self, sample, generator_output):
        correct = (
            sample.ground_truth.lower(  # type: ignore
            )
            in generator_output.final_answer.lower()
        )  # type: ignore
        return EnvironmentResult(
            feedback="Correct!" if correct else "Incorrect",
            ground_truth=sample.ground_truth,
        )


def main():
    # Check for API keys
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set (only needed if using OpenAI models)")
    if not os.getenv("GLM_API_KEY") or not os.getenv("GLM_BASE_URL"):
        print("Please set GLM_API_KEY and GLM_BASE_URL in your .env file")
        return

    # 1. Create LLM client(s)
    glm_model = LitellmModel(
        model="openai/glm-4.7",
        api_key=os.getenv("GLM_API_KEY"),
        base_url=os.getenv("GLM_BASE_URL"),
    )

    # 2. Create ACE components
    # Cast LitellmModel to the LLMClient expected by ACE components.
    # LitellmModel conforms at runtime; this cast resolves the Pylance type error.
    glm_client = cast("LLMClient", glm_model)

    adapter = OfflineAdapter(
        playbook=Playbook(),
        generator=Generator(glm_client),
        reflector=Reflector(glm_client),
        curator=Curator(glm_client),
    )

    # 3. Create training samples
    samples = [
        Sample(question="What is 2+2?", ground_truth="4"),
        Sample(question="What color is the sky?", ground_truth="blue"),
        Sample(question="Capital of France?", ground_truth="Paris"),
    ]

    # 4. Run adaptation
    environment = SimpleEnvironment()
    results = adapter.run(samples, environment, epochs=1)

    # 5. Check results
    print(f"Trained on {len(results)} samples")
    print(f"Playbook now has {len(adapter.playbook.bullets())} strategies")

    # Show a few learned strategies
    for bullet in adapter.playbook.bullets()[:2]:
        print(f"\nLearned: {bullet.content}")


if __name__ == "__main__":
    main()
