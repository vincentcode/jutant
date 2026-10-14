"""The HR systems, as the pack's MCP server reaches them.

`build(mode)`: `fake` (the dummy HR system in memory, for development, tests and evals) or
`real` (HTTP clients, configured by JUTANT_HR_RECORDS_*, JUTANT_HR_LEAVE_* and
JUTANT_HR_HELPDESK_*; see `http.HrHttp.from_env`). Until the organisation's HR systems are
known, `real` can run against `packs.hr.mock_hr`.
"""

import os
from dataclasses import dataclass

from packs.hr.adapters.base import HelpdeskClient, HrRecordsClient, LeaveClient


@dataclass(frozen=True)
class HrSystems:
    records: HrRecordsClient
    leave: LeaveClient
    helpdesk: HelpdeskClient


def build(mode: str | None = None) -> HrSystems:
    """`mode` defaults to the JUTANT_HR_ADAPTERS environment variable, then `fake`."""
    mode = mode or os.environ.get("JUTANT_HR_ADAPTERS", "fake")
    if mode == "fake":
        from packs.hr.adapters.fake import DummyHr

        hr = DummyHr()
        return HrSystems(hr, hr, hr)
    if mode == "real":
        from packs.hr.adapters.http import HrHttp, HttpHelpdesk, HttpHrRecords, HttpLeave

        return HrSystems(
            HttpHrRecords(HrHttp.from_env("RECORDS")),
            HttpLeave(HrHttp.from_env("LEAVE")),
            HttpHelpdesk(HrHttp.from_env("HELPDESK")),
        )
    raise ValueError(f"JUTANT_HR_ADAPTERS must be 'fake' or 'real', not {mode!r}")
