from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from atlassian_skills.cli.main import app
from atlassian_skills.core.config import Config
from atlassian_skills.core.errors import ExitCode

ZEPHYR_URL = "https://jira.example.com"
API = "/rest/atm/1.0"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLS_DEFAULT_ZEPHYR_URL", ZEPHYR_URL)
    monkeypatch.setenv("ATLS_DEFAULT_ZEPHYR_TOKEN", "test-token")
    monkeypatch.setattr("atlassian_skills.cli.zephyr.load_config", lambda: Config())


@respx.mock
def test_cli_zephyr_testcase_get_json() -> None:
    respx.get(f"{ZEPHYR_URL}{API}/testcase/JQA-T1").mock(
        return_value=httpx.Response(200, json={"key": "JQA-T1", "name": "Login", "projectKey": "JQA"})
    )

    result = runner.invoke(app, ["zephyr", "testcase", "get", "JQA-T1", "--format", "json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["key"] == "JQA-T1"


@respx.mock
@pytest.mark.parametrize("operation", ["get", "search"])
def test_cli_zephyr_testcase_json_preserves_metadata(operation: str) -> None:
    case = {
        "key": "JQA-T1",
        "updatedOn": "2026-11-12T15:00:00.123Z",
        "majorVersion": 4,
        "latestVersion": False,
    }
    is_get = operation == "get"
    path = "JQA-T1" if is_get else "search"
    respx.get(f"{ZEPHYR_URL}{API}/testcase/{path}").respond(json=case if is_get else [case])

    args = ["get", path] if is_get else ["search"]
    result = runner.invoke(app, ["zephyr", "testcase", *args, "--format=json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    row = data if is_get else data[0]
    assert row["last_modified_on"] == case["updatedOn"]
    assert row["major_version"] == 4
    assert row["latest_version"] is False


@respx.mock
@pytest.mark.parametrize(
    ("args", "body"),
    [
        (["get", "JQA-T1"], b'{ "key": "JQA-T1", "majorVersion": 4 }'),
        (["search"], b'{\n  "results": [{ "key": "JQA-T1", "majorVersion": 4 }]\n}\n'),
    ],
)
def test_cli_zephyr_testcase_raw_preserves_api_body(args: list[str], body: bytes) -> None:
    path = args[-1]
    respx.get(f"{ZEPHYR_URL}{API}/testcase/{path}").respond(content=body)

    result = runner.invoke(app, ["zephyr", "testcase", *args, "--format=raw"])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == body


@respx.mock
def test_cli_zephyr_updated_after_scans_pages_and_filters_timestamps() -> None:
    url = f"{ZEPHYR_URL}{API}/testcase/search"
    query = 'projectKey = "JQA"'
    route = respx.get(url).mock(
        side_effect=[
            httpx.Response(
                200,
                json=[{"key": "JQA-T1", "updatedOn": "2026-11-12T12:00:00-03:00", "name": "Exact cutoff"}],
            ),
            httpx.Response(
                200,
                json={
                    "results": [
                        {"key": "JQA-T2", "createdOn": "2026-11-12T15:00:01Z", "majorVersion": 1, "name": "New"},
                        {"key": "JQA-T3", "lastModifiedOn": "2026-11-12T15:00:02Z", "majorVersion": 2},
                    ]
                },
            ),
            httpx.Response(200, json=[]),
        ]
    )

    result = runner.invoke(
        app,
        [
            "zephyr",
            "testcase",
            "search",
            "--query",
            query,
            "--updated-after",
            "2026-11-12T15:00:00Z",
            "--max-results",
            "2",
            "--fields",
            "name",
            "--format=json",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert [row["key"] for row in rows] == ["JQA-T2", "JQA-T3"]
    assert rows[0]["name"] == "New"
    assert rows[1]["major_version"] == 2
    params = [call.request.url.params for call in route.calls]
    assert [p.get("startAt", "0") for p in params] == ["0", "1", "3"]
    assert all(p["query"] == query and p["maxResults"] == "2" for p in params)
    assert all(
        set(p["fields"].split(","))
        == {"key", "createdOn", "updatedOn", "lastModifiedOn", "majorVersion", "latestVersion", "name"}
        for p in params
    )
    assert "Scanned 3 test cases" in result.stderr


@respx.mock
@pytest.mark.parametrize(
    ("extra_args", "message"),
    [
        (["--updated-after", "yesterday"], "ISO 8601"),
        (["--updated-after", "2026-11-12", "--format=raw"], "--format=raw"),
    ],
)
def test_cli_zephyr_updated_after_rejects_invalid_options(extra_args: list[str], message: str) -> None:
    route = respx.get(f"{ZEPHYR_URL}{API}/testcase/search").respond(json=[])

    result = runner.invoke(app, ["zephyr", "testcase", "search", *extra_args])

    assert result.exit_code == ExitCode.VALIDATION
    assert message in result.stderr
    assert not route.called


@respx.mock
def test_cli_zephyr_updated_after_reports_cases_without_a_date() -> None:
    respx.get(f"{ZEPHYR_URL}{API}/testcase/search").respond(
        json=[{"key": "JQA-T1", "createdOn": None, "updatedOn": None}]
    )

    result = runner.invoke(app, ["zephyr", "testcase", "search", "--updated-after", "2026-11-12", "--format=json"])

    assert result.exit_code == ExitCode.VALIDATION
    assert "JQA-T1" in json.loads(result.stdout)["error"]["message"]


@respx.mock
def test_cli_zephyr_updated_after_stops_if_server_repeats_a_page() -> None:
    route = respx.get(f"{ZEPHYR_URL}{API}/testcase/search").respond(
        json=[{"key": "JQA-T1", "createdOn": "2026-11-13T01:00:00Z"}]
    )

    result = runner.invoke(app, ["--quiet", "zephyr", "testcase", "search", "--updated-after", "2026-11-12"])

    assert result.exit_code == ExitCode.VALIDATION
    assert route.call_count == 2
    assert "repeated a test case page" in result.stderr
    assert "Scanned" not in result.stderr


@respx.mock
def test_cli_zephyr_search_compact() -> None:
    respx.get(f"{ZEPHYR_URL}{API}/testcase/search").mock(
        return_value=httpx.Response(200, json=[{"key": "JQA-T1", "name": "Login", "projectKey": "JQA"}])
    )

    result = runner.invoke(app, ["zephyr", "testcase", "search", "--query", 'projectKey = "JQA"'])

    assert result.exit_code == 0, result.output
    assert "JQA-T1" in result.output


@respx.mock
def test_cli_zephyr_create_dry_run_does_not_hit_api() -> None:
    route = respx.post(f"{ZEPHYR_URL}{API}/testcase").mock(return_value=httpx.Response(500))

    result = runner.invoke(
        app,
        [
            "zephyr",
            "testcase",
            "create",
            "--data-json",
            '{"name":"Login","projectKey":"JQA"}',
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "POST" in result.output
    assert "Login" in result.output
    assert not route.called


def test_cli_zephyr_invalid_data_json_exits_validation() -> None:
    result = runner.invoke(app, ["zephyr", "testcase", "create", "--data-json", "not-json"])

    assert result.exit_code == ExitCode.VALIDATION


@respx.mock
def test_cli_zephyr_testrun_results_json() -> None:
    respx.get(f"{ZEPHYR_URL}{API}/testrun/JQA-R1/testresults").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 7, "testCaseKey": "JQA-T1", "projectKey": "JQA", "status": "Pass"}],
        )
    )

    result = runner.invoke(app, ["zephyr", "testrun", "results", "JQA-R1", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["id"] == 7


@respx.mock
def test_cli_zephyr_environment_list() -> None:
    respx.get(f"{ZEPHYR_URL}{API}/environments").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 1, "name": "QA"}]})
    )

    result = runner.invoke(app, ["zephyr", "environment", "list", "JQA", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["name"] == "QA"


@respx.mock
def test_cli_zephyr_not_found_exit_code() -> None:
    respx.get(f"{ZEPHYR_URL}{API}/testcase/MISSING").mock(return_value=httpx.Response(404, text="missing"))

    result = runner.invoke(app, ["zephyr", "testcase", "get", "MISSING"])

    assert result.exit_code == ExitCode.NOT_FOUND
