"""The Docker facade forwards exactly; it never owns or edits resource state."""

from unittest.mock import patch

from typer.testing import CliRunner

from copilot_cli.services.docker.commands import app


def test_resource_facade_preserves_arguments_and_exit_code():
    with patch("subprocess.call", return_value=7) as call:
        result = CliRunner().invoke(
            app, ["tests", "run", "--task", "TASK-179", "--", "pytest", "-q"]
        )
    assert result.exit_code == 7
    call.assert_called_once_with(
        ["cc", "resources", "run", "--task", "TASK-179", "--", "pytest", "-q"]
    )
