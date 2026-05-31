import sys
from pathlib import Path

import pytest

# Make src/ importable in tests without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_token_manager(mocker):
    tm = mocker.AsyncMock()
    tm.get_token.return_value = "test-token"
    return tm


@pytest.fixture
def mock_opc_client(mocker):
    client = mocker.AsyncMock()
    client.fetch_activities.return_value = [
        {"activityId": "A1000", "name": "Design", "status": "Not Started", "wbsId": "W1"},
        {"activityId": "A1010", "name": "Build", "status": "In Progress", "wbsId": "W1"},
    ]
    client.fetch_wbs.return_value = [
        {"wbsId": "W1", "name": "Phase 1", "parentWbsId": None},
    ]
    client.fetch_relationships.return_value = [
        {"relationshipId": "R1", "predecessorActivityId": "A1000", "successorActivityId": "A1010", "type": "FS", "lag": 0},
    ]
    client.fetch_calendars.return_value = [
        {"calendarId": "CAL1", "name": "Standard", "type": "Global"},
    ]
    return client
