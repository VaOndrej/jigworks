"""Hub-only response models that are not part of the frozen contracts.

`GET /api/analytics/overview` serves the key numbers of the Workflows and Runs & analytics
tabs (gate pass on the first try, median time to PR, cost per day by token type). Only
hub-web reads it; the runner and the extension never do, so it does not belong in the seam.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GroupStats(_Model):
    runs: int
    costUsd: float
    costPerRunUsd: float | None = None
    gateRuns: int
    gatePassFirstTry: float | None = None
    medianTimeToPrSec: float | None = None
    medianHumanWaitSec: float | None = None


class WorkflowStats(GroupStats):
    workflowId: str
    running: int


class ReleaseStats(GroupStats):
    release: str


class DayCost(_Model):
    day: str
    input: float
    output: float
    cache_write: float
    cache_read: float


class Overview(GroupStats):
    from_: AwareDatetime = Field(alias="from")
    to: AwareDatetime
    costLabel: str
    previousRuns: int
    running: int
    waitingHuman: int
    pausedUsageLimit: int
    oldestWaitingSince: AwareDatetime | None = None
    costByDay: list[DayCost]
    workflows: list[WorkflowStats]
    releases: list[ReleaseStats]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)



class SampleDataRemoved(_Model):
    """Hub-only: what `POST /api/admin/remove-sample-data` deleted."""

    runs: int
    releases: int
    workflows: int
    blobBundles: int
