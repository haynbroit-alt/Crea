from pydantic import BaseModel, Field
from typing import Optional


class VideoRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200, description="Sujet de la vidéo")
    language: Optional[str] = Field(default="fr", description="Langue du script (fr/en)")
    style: Optional[str] = Field(default="viral", description="Style: viral, educational, storytelling")


class Scene(BaseModel):
    index: int
    text: str
    visual_keywords: list[str]
    duration_hint: str


class Script(BaseModel):
    hook: str
    body: list[str]
    conclusion: str


class SEOData(BaseModel):
    titles: list[str]
    description: str
    hashtags: list[str]


class VideoPlan(BaseModel):
    topic: str
    language: str
    style: str
    script: Script
    scenes: list[Scene]
    seo: SEOData
    format: str
    estimated_duration: str
    status: str
