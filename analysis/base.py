from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CreativeTags:
    content_type: str | None  # ugc | talking_head | founder_led | broll_voiceover | …
    structure: str | None     # hook_problem_solution | testimonial | before_after | …
    hook_type: str | None     # problem_first | curiosity_pattern_interrupt | …
    objective: str | None     # awareness | consideration | conversion | retargeting
    description: str | None   # short free-text visual description
    hook_text: str | None     # transcribed/extracted hook or headline
    offer_cta: str | None


class CreativeAnalyzer(ABC):
    """
    One implementation per AI provider (OpenAI, Anthropic, etc.).
    Swappable so providers can be benchmarked against manual ground-truth tags
    before any one is chosen as the default.
    """

    @abstractmethod
    def analyze(
        self,
        file_url: str,
        file_type: str,        # 'video' | 'image' | 'carousel'
        taxonomy: dict,        # current taxonomy values for each dimension
    ) -> CreativeTags: ...
