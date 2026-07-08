from datetime import datetime
from typing import Annotated, Union

from pydantic import BaseModel, Field

from app.models.feed import LiquidComponent, PowderComponent

# Presets hold measured components only — latch minutes vary every feed.
PresetComponent = Annotated[
    Union[LiquidComponent, PowderComponent], Field(discriminator="kind")
]


class FeedPresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    components: list[PresetComponent] = Field(min_length=1, max_length=8)


class FeedPreset(FeedPresetIn):
    id: str
    created_at: datetime
