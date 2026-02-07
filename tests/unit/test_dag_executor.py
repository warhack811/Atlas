import pytest
from unittest.mock import patch
from Atlas.dag_executor import DAGExecutor

class TestDAGExecutor:
    @patch('Atlas.dag_executor.ToolRegistry')
    def test_inject_dependencies_happy_path(self, mock_tool_registry):
        # Setup
        executor = DAGExecutor()
        prompt = "Result of task 1 is {t1.output}"
        executed_tasks = {
            "t1": {"output": "Success", "status": "success"}
        }

        # Execution
        result = executor._inject_dependencies(prompt, executed_tasks)

        # Assertion
        assert result == "Result of task 1 is Success"

    @patch('Atlas.dag_executor.ToolRegistry')
    def test_inject_dependencies_multiple(self, mock_tool_registry):
        # Setup
        executor = DAGExecutor()
        prompt = "{t1.output} + {t2.output} = {t3.output}"
        executed_tasks = {
            "t1": {"output": "1", "status": "success"},
            "t2": {"output": "2", "status": "success"},
            "t3": {"output": "3", "status": "success"},
        }

        # Execution
        result = executor._inject_dependencies(prompt, executed_tasks)

        # Assertion
        assert result == "1 + 2 = 3"

    @patch('Atlas.dag_executor.ToolRegistry')
    def test_inject_dependencies_missing_task(self, mock_tool_registry):
        # Setup
        executor = DAGExecutor()
        prompt = "Task {t1.output} is missing"
        executed_tasks = {}

        # Execution
        result = executor._inject_dependencies(prompt, executed_tasks)

        # Assertion
        assert result == "Task {t1.output} is missing"

    @patch('Atlas.dag_executor.ToolRegistry')
    def test_inject_dependencies_failed_task(self, mock_tool_registry):
        # Setup
        executor = DAGExecutor()
        prompt = "Task 1 status: {t1.output}"
        executed_tasks = {
            "t1": {"output": None, "status": "failed"}
        }

        # Execution
        result = executor._inject_dependencies(prompt, executed_tasks)

        # Assertion
        assert result == "Task 1 status: [Hata: t1 verisi alınamadı]"

    @patch('Atlas.dag_executor.ToolRegistry')
    def test_inject_dependencies_non_string_output(self, mock_tool_registry):
        # Setup
        executor = DAGExecutor()
        prompt = "The number is {t1.output}"
        executed_tasks = {
            "t1": {"output": 42, "status": "success"}
        }

        # Execution
        result = executor._inject_dependencies(prompt, executed_tasks)

        # Assertion
        assert result == "The number is 42"

    @patch('Atlas.dag_executor.ToolRegistry')
    def test_inject_dependencies_no_placeholders(self, mock_tool_registry):
        # Setup
        executor = DAGExecutor()
        prompt = "No placeholders here"
        executed_tasks = {
            "t1": {"output": "Success", "status": "success"}
        }

        # Execution
        result = executor._inject_dependencies(prompt, executed_tasks)

        # Assertion
        assert result == "No placeholders here"

    @patch('Atlas.dag_executor.ToolRegistry')
    def test_inject_dependencies_invalid_patterns(self, mock_tool_registry):
        # Setup
        executor = DAGExecutor()
        prompt = "{t1output} {t1.input} {t1_output}"
        executed_tasks = {
            "t1": {"output": "Success", "status": "success"}
        }

        # Execution
        result = executor._inject_dependencies(prompt, executed_tasks)

        # Assertion
        assert result == "{t1output} {t1.input} {t1_output}"
