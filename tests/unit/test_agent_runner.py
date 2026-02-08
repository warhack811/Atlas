import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from Atlas.agent_runner import AgentRunner
from Atlas.schemas import OrchestrationPlan, TaskSpec

@pytest.fixture
def mock_orchestrator():
    mock = AsyncMock()
    with patch("Atlas.agent_runner.orchestrator", mock):
        yield mock

@pytest.fixture
def mock_dag_executor():
    mock = AsyncMock()
    # Mocking stream generator
    async def mock_stream(*args, **kwargs):
        yield {"type": "task_result", "result": {"type": "tool", "tool_name": "search", "output": "Search Result 1"}}

    # execute_plan_stream calls are not awaited, they return an async iterator
    # side_effect works for calling the function, but since it's an async generator...
    # The actual code does: `async for event in dag_executor.execute_plan_stream(...)`
    # So `dag_executor.execute_plan_stream` must be a function that returns an async generator.

    mock.execute_plan_stream = mock_stream

    with patch("Atlas.agent_runner.dag_executor", mock):
        yield mock

@pytest.mark.asyncio
async def test_agent_runner_loop(mock_orchestrator, mock_dag_executor):
    runner = AgentRunner()

    # 1. Step: Returns a Tool Task
    plan_step_1 = OrchestrationPlan(
        intent="search",
        tasks=[TaskSpec(id="t1", type="tool", tool_name="search")],
        user_thought="Looking for info"
    )

    # 2. Step: Returns a Generation Task (Loop End)
    plan_step_2 = OrchestrationPlan(
        intent="general",
        tasks=[TaskSpec(id="t2", type="generation", instruction="Answer")],
        user_thought="Found info, answering"
    )

    mock_orchestrator.plan.side_effect = [plan_step_1, plan_step_2]

    events = []
    async for event in runner.run_loop("sid", "msg", "uid"):
        events.append(event)

    # Verify sequence
    # 1. Think (Thought event)
    # 2. Act (DAG Stream -> Task Result)
    # 3. Loop (Think again)
    # 4. Final Answer (Loop Done)

    assert events[0]["type"] == "thought"
    assert "Looking for info" in events[0]["step"]["content"]

    # Check if tool result was captured in history
    # The runner calls dag_executor which yields results.
    # We mocked it to yield one result.

    assert events[-1]["type"] == "loop_done"
    assert mock_orchestrator.plan.call_count == 2

@pytest.mark.asyncio
async def test_agent_runner_max_steps(mock_orchestrator, mock_dag_executor):
    runner = AgentRunner()
    runner.MAX_STEPS = 2

    # Always return a tool task (Infinite loop simulation)
    infinite_plan = OrchestrationPlan(
        intent="search",
        tasks=[TaskSpec(id="t1", type="tool", tool_name="search")]
    )
    mock_orchestrator.plan.return_value = infinite_plan

    events = []
    async for event in runner.run_loop("sid", "msg", "uid"):
        events.append(event)

    # Should end with error or loop_done with warning
    error_event = next((e for e in events if e["type"] == "error"), None)
    assert error_event is not None
    # Turkish characters can be tricky in assertion strings if encodings vary,
    # but based on the log, it seems correct. Let's check for "maksimum adım" lower case to be safe.
    assert "maksimum adım" in error_event["content"].lower()
