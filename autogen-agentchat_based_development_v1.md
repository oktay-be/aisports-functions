# AutoGen AgentChat - Comprehensive Development Guide

> **Version**: v1
> **Last Updated**: 2024-12-19
> **Source**: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/

---

## Overview

**AutoGen AgentChat** is a high-level API for building **multi-agent applications**, built on top of `autogen-core`. It's the recommended starting point for beginners, offering intuitive defaults with preset **Agents** and **Teams** implementing proven multi-agent design patterns.

---

## Installation

```bash
# Install AgentChat
pip install -U "autogen-agentchat"

# Install model clients (choose what you need)
pip install "autogen-ext[openai]"          # OpenAI
pip install "autogen-ext[azure]"           # Azure OpenAI
pip install "autogen-ext[anthropic]"       # Anthropic (Claude)
pip install "autogen-ext[ollama]"          # Local models via Ollama
```

**Requires Python 3.10+**

---

## Core Concepts

### 1. Model Clients

Supports multiple LLM providers:

```python
# OpenAI
from autogen_ext.models.openai import OpenAIChatCompletionClient
model_client = OpenAIChatCompletionClient(model="gpt-4o")

# Azure OpenAI
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

# Anthropic (Claude)
from autogen_ext.models.anthropic import AnthropicChatCompletionClient
anthropic_client = AnthropicChatCompletionClient(model="claude-3-7-sonnet-20250219")

# Ollama (local)
from autogen_ext.models.ollama import OllamaChatCompletionClient
ollama_client = OllamaChatCompletionClient(model="llama3.2")
```

---

### 2. Agents

All agents share:
- `name`: Unique agent identifier
- `description`: Text description (used for speaker selection)
- `run()` / `run_stream()`: Execute agent on a task
- **Agents are stateful** - call with new messages, not complete history

#### AssistantAgent (Built-in)

A general-purpose agent with LLM and tool capabilities:

```python
from autogen_agentchat.agents import AssistantAgent

async def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: 73°F and Sunny"

agent = AssistantAgent(
    name="weather_agent",
    model_client=model_client,
    tools=[get_weather],
    system_message="You are a helpful assistant.",
    reflect_on_tool_use=True,  # Reflect on tool output
    model_client_stream=True,   # Enable streaming
)

# Run the agent
result = await agent.run(task="What's the weather in NYC?")
```

#### UserProxyAgent

Proxy for human-in-the-loop interaction:

```python
from autogen_agentchat.agents import UserProxyAgent
user_proxy = UserProxyAgent("user_proxy", input_func=input)
```

#### Custom Agents

Extend `BaseChatAgent` and implement:
- `on_messages()`: Response behavior
- `on_reset()`: Reset to initial state
- `produced_message_types`: Possible output message types

```python
from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.messages import TextMessage, BaseChatMessage
from autogen_agentchat.base import Response
from typing import Sequence

class MyCustomAgent(BaseChatAgent):
    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        self._chat_history: list[BaseChatMessage] = []

    @property
    def produced_message_types(self) -> list[type[BaseChatMessage]]:
        return [TextMessage]

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token
    ) -> Response:
        # Store messages
        self._chat_history.extend(messages)
        # Generate response
        response = TextMessage(content="Hello!", source=self.name)
        return Response(chat_message=response)

    async def on_reset(self, cancellation_token) -> None:
        self._chat_history.clear()
```

---

### 3. Teams (Multi-Agent Coordination)

Teams are groups of agents working together. All teams share context between agents.

#### RoundRobinGroupChat

Agents take turns in order:

```python
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.ui import Console

team = RoundRobinGroupChat(
    [primary_agent, critic_agent],
    termination_condition=TextMentionTermination("APPROVE")
)

result = await team.run(task="Write a poem about fall")

# Or stream output
await Console(team.run_stream(task="..."))
```

#### SelectorGroupChat

Model-based dynamic speaker selection - the LLM decides which agent speaks next:

```python
from autogen_agentchat.teams import SelectorGroupChat

selector_prompt = """Select an agent to perform task.

{roles}

Current conversation context:
{history}

Read the above conversation, then select an agent from {participants} to perform the next task.
Make sure the planner agent has assigned tasks before other agents start working.
Only select one agent.
"""

team = SelectorGroupChat(
    [planning_agent, web_search_agent, data_analyst_agent],
    model_client=model_client,
    termination_condition=termination,
    selector_prompt=selector_prompt,
    allow_repeated_speaker=True,  # Allow same agent multiple turns
)
```

**Key SelectorGroupChat Features:**
- Model-based speaker selection
- Configurable participant roles and descriptions
- Prevention of consecutive turns by the same speaker (optional)
- Customizable selection prompting
- Custom selection function to override model-based selection
- Custom candidate function to narrow-down agents for selection

#### Swarm

Agent-driven handoffs using `HandoffMessage` - agents decide which agent handles the task next:

```python
from autogen_agentchat.teams import Swarm
from autogen_agentchat.conditions import HandoffTermination, TextMentionTermination
from autogen_agentchat.messages import HandoffMessage

# Define a tool
def refund_flight(flight_id: str) -> str:
    """Refund a flight"""
    return f"Flight {flight_id} refunded"

# Create agents with handoff capabilities
travel_agent = AssistantAgent(
    "travel_agent",
    model_client=model_client,
    handoffs=["flights_refunder", "user"],  # Can hand off to these agents
    system_message="""You are a travel agent.
    The flights_refunder is in charge of refunding flights.
    If you need information from the user, handoff to the user.
    Use TERMINATE when the travel planning is complete.""",
)

flights_refunder = AssistantAgent(
    "flights_refunder",
    model_client=model_client,
    handoffs=["travel_agent", "user"],
    tools=[refund_flight],
    system_message="""You are an agent specialized in refunding flights.
    You only need flight reference numbers to refund a flight.
    When the transaction is complete, handoff to the travel agent to finalize.""",
)

# Create termination conditions
termination = HandoffTermination(target="user") | TextMentionTermination("TERMINATE")

# Create the Swarm team
team = Swarm([travel_agent, flights_refunder], termination_condition=termination)

# Run with human-in-the-loop
async def run_team_stream():
    task_result = await Console(team.run_stream(task="I need to refund my flight."))
    last_message = task_result.messages[-1]

    while isinstance(last_message, HandoffMessage) and last_message.target == "user":
        user_message = input("User: ")
        task_result = await Console(
            team.run_stream(
                task=HandoffMessage(
                    source="user",
                    target=last_message.source,
                    content=user_message
                )
            )
        )
        last_message = task_result.messages[-1]
```

**How Swarm Works:**
1. Each agent can generate `HandoffMessage` to signal handoffs
2. The first speaker operates on the task and makes local decisions about handoffs
3. When an agent generates a `HandoffMessage`, the receiving agent takes over
4. Process continues until termination condition is met

#### GraphFlow (Workflows) - Experimental

Directed graph for precise control over agent execution flow:

```python
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
from autogen_agentchat.ui import Console

# Create agents
writer = AssistantAgent("writer", model_client=client,
                        system_message="Draft a short paragraph on climate change.")
editor1 = AssistantAgent("editor1", model_client=client,
                         system_message="Edit the paragraph for grammar.")
editor2 = AssistantAgent("editor2", model_client=client,
                         system_message="Edit the paragraph for style.")
final_reviewer = AssistantAgent("final_reviewer", model_client=client,
                                system_message="Consolidate the edits into a final version.")

# Build the workflow graph
builder = DiGraphBuilder()
builder.add_node(writer).add_node(editor1).add_node(editor2).add_node(final_reviewer)

# Fan-out from writer to editors (parallel)
builder.add_edge(writer, editor1)
builder.add_edge(writer, editor2)

# Fan-in both editors into final reviewer
builder.add_edge(editor1, final_reviewer)
builder.add_edge(editor2, final_reviewer)

# Build and validate the graph
graph = builder.build()

# Create and run the flow
flow = GraphFlow(participants=builder.get_participants(), graph=graph)
await Console(flow.run_stream(task="Write a short paragraph about climate change."))
```

**GraphFlow Capabilities:**
- Sequential chains
- Parallel fan-outs
- Conditional branching
- Loops with safe exit conditions

**When to use GraphFlow:**
- Strict control over agent execution order
- Different outcomes must lead to different next steps
- Deterministic control, conditional branching, or complex multi-step processes

---

### 4. Termination Conditions

```python
from autogen_agentchat.conditions import (
    TextMentionTermination,    # Stop when specific text appears
    MaxMessageTermination,     # Stop after N messages
    HandoffTermination,        # Stop on handoff to target agent
    ExternalTermination,       # Stop from external signal
    SourceMatchTermination,    # Stop when message from specific source
    TokenUsageTermination,     # Stop on token budget
    TimeoutTermination,        # Stop after time limit
)

# Combine with | (OR) or & (AND)
termination = TextMentionTermination("TERMINATE") | MaxMessageTermination(25)

# Examples
text_termination = TextMentionTermination("APPROVE")
max_messages = MaxMessageTermination(max_messages=25)
handoff_termination = HandoffTermination(target="user")

# Combined termination
combined = text_termination | max_messages  # Stops when EITHER condition is met
```

---

### 5. Memory & RAG

Add persistent memory to agents for context retention:

#### ListMemory (Simple)

```python
from autogen_core.memory import ListMemory, MemoryContent, MemoryMimeType

# Initialize user memory
user_memory = ListMemory()

# Add user preferences to memory
await user_memory.add(MemoryContent(
    content="The weather should be in metric units",
    mime_type=MemoryMimeType.TEXT
))

await user_memory.add(MemoryContent(
    content="Meal recipe must be vegan",
    mime_type=MemoryMimeType.TEXT
))

# Create agent with memory
assistant_agent = AssistantAgent(
    name="assistant_agent",
    model_client=model_client,
    tools=[get_weather],
    memory=[user_memory],  # Attach memory
)

# The agent will now consider memory when responding
stream = assistant_agent.run_stream(task="What is the weather in New York?")
await Console(stream)
```

#### ChromaDB Vector Memory (RAG)

```python
from autogen_ext.memory.chromadb import (
    ChromaDBVectorMemory,
    PersistentChromaDBVectorMemoryConfig,
    SentenceTransformerEmbeddingFunctionConfig,
)

chroma_memory = ChromaDBVectorMemory(
    config=PersistentChromaDBVectorMemoryConfig(
        collection_name="preferences",
        persistence_path="/path/to/db",
        k=2,  # Return top k results
        score_threshold=0.4,  # Minimum similarity score
        embedding_function_config=SentenceTransformerEmbeddingFunctionConfig(
            model_name="all-MiniLM-L6-v2"
        ),
    )
)

# Add with metadata
await chroma_memory.add(
    MemoryContent(
        content="The weather should be in metric units",
        mime_type=MemoryMimeType.TEXT,
        metadata={"category": "preferences", "type": "units"},
    )
)

# Use with agent
agent = AssistantAgent(
    name="assistant",
    model_client=model_client,
    memory=[chroma_memory],
)
```

**Available Memory Stores:**
- `ListMemory` - Simple list-based, chronological order
- `ChromaDBVectorMemory` - Vector database with semantic search
- `RedisMemory` - Redis-based vector store

---

### 6. Human-in-the-Loop

#### Option 1: UserProxyAgent (During Run)

Blocks execution until user responds:

```python
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat

model_client = OpenAIChatCompletionClient(model="gpt-4o-mini")
assistant = AssistantAgent("assistant", model_client=model_client)
user_proxy = UserProxyAgent("user_proxy", input_func=input)

termination = TextMentionTermination("APPROVE")
team = RoundRobinGroupChat([assistant, user_proxy], termination_condition=termination)

stream = team.run_stream(task="Write a 4-line poem about the ocean.")
await Console(stream)
```

#### Option 2: Using max_turns (Stop After N Turns)

```python
# Create team with max_turns=1 to stop after each agent response
team = RoundRobinGroupChat([assistant], max_turns=1)

task = "Write a 4-line poem about the ocean."
while True:
    stream = team.run_stream(task=task)
    await Console(stream)

    task = input("Enter your feedback (type 'exit' to leave): ")
    if task.lower().strip() == "exit":
        break
```

#### Option 3: HandoffTermination (Agent Decides to Hand Back)

```python
# Agent can hand off to "user" when it needs input
agent = AssistantAgent(
    "assistant",
    model_client=model_client,
    handoffs=["user"],
    system_message="Hand off to user when you need more information."
)

team = Swarm([agent], termination_condition=HandoffTermination("user"))
```

---

### 7. State Management

Save and restore team state for persistence:

```python
# Save state
state = await team.save_state()

# Store state (e.g., in database, file)
import json
with open("team_state.json", "w") as f:
    json.dump(state, f)

# Later: restore
with open("team_state.json", "r") as f:
    state = json.load(f)
await team.load_state(state)

# Reset for completely new task (clears history)
await team.reset()
```

---

### 8. Logging & Tracing

```python
import logging
from autogen_core import EVENT_LOGGER_NAME

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(EVENT_LOGGER_NAME)
logger.setLevel(logging.INFO)

# Custom handler
handler = logging.FileHandler("autogen.log")
handler.setLevel(logging.INFO)
logger.addHandler(handler)
```

---

### 9. Serializing Components

Components can be serialized for deployment:

```python
from autogen_agentchat.agents import AssistantAgent

# Get component config
config = agent.dump_component()

# Recreate from config
restored_agent = AssistantAgent.load_component(config)
```

---

## Quick Start Example

```python
import asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient

async def main():
    model = OpenAIChatCompletionClient(model="gpt-4o")

    writer = AssistantAgent(
        "writer",
        model_client=model,
        system_message="Write creative content."
    )
    critic = AssistantAgent(
        "critic",
        model_client=model,
        system_message="Critique and say APPROVE when satisfied."
    )

    team = RoundRobinGroupChat(
        [writer, critic],
        termination_condition=TextMentionTermination("APPROVE")
    )

    await Console(team.run_stream(task="Write a haiku about AI"))
    await model.close()

asyncio.run(main())
```

---

## Design Patterns Summary

| Pattern | Team Type | Use Case |
|---------|-----------|----------|
| **Reflection** | RoundRobinGroupChat | Writer + Critic iterating until approval |
| **Dynamic Routing** | SelectorGroupChat | Model picks next speaker based on context |
| **Agent Handoffs** | Swarm | Agents delegate tasks to specialists |
| **Structured Workflows** | GraphFlow | Deterministic pipelines with branching |
| **Human Feedback** | UserProxyAgent / HandoffTermination | Interactive applications |

---

## Integration Examples

- **FastAPI**: https://github.com/microsoft/autogen/tree/main/python/samples/agentchat_fastapi
- **ChainLit**: https://github.com/microsoft/autogen/tree/main/python/samples/agentchat_chainlit
- **Streamlit**: https://github.com/microsoft/autogen/tree/main/python/samples/agentchat_streamlit

---

## Resources

- **GitHub**: https://github.com/microsoft/autogen
- **Documentation**: https://microsoft.github.io/autogen/stable/
- **Discord**: https://aka.ms/autogen-discord
- **API Reference**: https://microsoft.github.io/autogen/stable/reference/

---

## Message Types Reference

```python
from autogen_agentchat.messages import (
    TextMessage,           # Basic text message
    HandoffMessage,        # Agent-to-agent handoff
    ToolCallRequestEvent,  # Tool call request
    ToolCallExecutionEvent,# Tool execution result
    StopMessage,           # Termination signal
    BaseChatMessage,       # Base class for all messages
    BaseAgentEvent,        # Base class for agent events
)
```

---

## Best Practices

1. **Agent Names & Descriptions**: Use meaningful names and descriptions - they're used for speaker selection
2. **System Messages**: Be specific about agent roles and capabilities
3. **Termination Conditions**: Always define clear termination conditions to prevent infinite loops
4. **Tool Functions**: Use clear docstrings - they help the LLM understand tool usage
5. **Memory**: Use memory for context that should persist across conversations
6. **State Management**: Save state for long-running or resumable workflows
7. **Parallel Tool Calls**: Disable if using Swarm to avoid unexpected handoff behavior:
   ```python
   model_client = OpenAIChatCompletionClient(model="gpt-4o", parallel_tool_calls=False)
   ```