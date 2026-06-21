from pydantic import BaseModel, Field
from typing import Optional


class StoryCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    topic: str = Field(..., min_length=3, max_length=200)
    language: Optional[str] = Field(default="fr")


class EpisodeRequest(BaseModel):
    story_id: str
    episode_number: Optional[int] = None  # auto-increments if omitted
    render_video: Optional[bool] = Field(default=False)


class WorldState(BaseModel):
    tension: int
    mystery_level: int


class Episode(BaseModel):
    episode_number: int
    hook: str
    body: list[str]
    cliffhanger: str
    world_state_snapshot: dict
    full_script: str
    video_path: Optional[str] = None


class StorySummary(BaseModel):
    id: str
    title: str
    topic: str
    episode_count: int
    created_at: str


class StoryDetail(BaseModel):
    id: str
    title: str
    topic: str
    language: str
    universe: dict
    characters: list[dict]
    episodes: list[Episode]
    world_state: WorldState
    created_at: str
