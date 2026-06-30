from pydantic import BaseModel, Field


class OperatingModelMetric(BaseModel):
    label: str
    value: str


class OperatingModelSummary(BaseModel):
    headline: str
    description: str
    metrics: list[OperatingModelMetric] = Field(default_factory=list)


class OperatingModelStage(BaseModel):
    number: int
    title: str
    activities: list[str] = Field(default_factory=list)


class OperatingModelRisk(BaseModel):
    stage: int
    text: str


class OperatingModelSpec(BaseModel):
    title: str
    subtitle: str = ""
    description: str = ""
    summary: OperatingModelSummary
    stages: list[OperatingModelStage] = Field(min_length=4, max_length=8)
    risks: list[OperatingModelRisk] = Field(default_factory=list)
