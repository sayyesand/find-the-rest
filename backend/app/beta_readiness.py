import os
from dataclasses import dataclass

from .benchmark import benchmark_summary
from .reverse_image import configured as reverse_image_configured
from .candidate_media import configured as candidate_media_configured
from .vision_clues import configured as vision_clues_configured


@dataclass(frozen=True)
class BetaGate:
    gate_id: str
    label: str
    passed: bool
    critical: bool
    detail: str


def _configured(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def readiness_summary() -> dict:
    benchmark = benchmark_summary()
    api_key = os.getenv("FIND_THE_REST_API_KEY", "").strip()
    api_key_secure = bool(api_key and api_key != "change-me-for-beta" and len(api_key) >= 16)

    gates = [
        BetaGate(
            "adversarial-benchmark",
            "Adversarial benchmark",
            benchmark["pass_rate"] == 1.0,
            True,
            f'{benchmark["passed"]}/{benchmark["total"]} deterministic adversarial cases pass.',
        ),
        BetaGate(
            "api-auth",
            "Backend API authentication",
            api_key_secure,
            True,
            "A non-default API key of at least 16 characters is configured." if api_key_secure
            else "Set FIND_THE_REST_API_KEY to a non-default value of at least 16 characters.",
        ),
        BetaGate(
            "public-search",
            "Public web discovery",
            _configured("BRAVE_SEARCH_API_KEY"),
            True,
            "Open-web discovery is configured." if _configured("BRAVE_SEARCH_API_KEY")
            else "BRAVE_SEARCH_API_KEY is not configured.",
        ),
        BetaGate(
            "youtube-search",
            "YouTube discovery",
            _configured("YOUTUBE_API_KEY"),
            False,
            "YouTube discovery is configured." if _configured("YOUTUBE_API_KEY")
            else "YOUTUBE_API_KEY is not configured; YouTube-specific discovery will be reduced.",
        ),
        BetaGate(
            "reverse-image",
            "Reverse-image discovery",
            reverse_image_configured(),
            False,
            "Reverse-image gateway passed configuration validation." if reverse_image_configured()
            else "Reverse-image gateway is unavailable or fails configuration validation.",
        ),
        BetaGate(
            "candidate-media",
            "Automatic candidate verification",
            candidate_media_configured(),
            False,
            "Permitted candidate-media gateway passed configuration validation." if candidate_media_configured()
            else "Automatic candidate media verification is not configured.",
        ),
        BetaGate(
            "semantic-visual",
            "Object/logo/scene recognition",
            vision_clues_configured(),
            False,
            "Semantic visual-clue gateway passed configuration validation." if vision_clues_configured()
            else "Semantic object/logo/scene recognition is not configured; coarse local scene clues remain available.",
        ),
        BetaGate(
            "cors-policy",
            "Browser CORS policy",
            not bool(os.getenv("FINDREST_CORS_ORIGINS", "").strip()) or "*" not in os.getenv("FINDREST_CORS_ORIGINS", ""),
            False,
            "CORS is disabled for browsers or restricted to explicit origins."
            if "*" not in os.getenv("FINDREST_CORS_ORIGINS", "")
            else "Wildcard browser CORS is configured; use explicit origins for production.",
        ),
        BetaGate(
            "trusted-hosts",
            "Trusted host filtering",
            bool(os.getenv("FINDREST_TRUSTED_HOSTS", "").strip()),
            False,
            "Host-header filtering is configured."
            if os.getenv("FINDREST_TRUSTED_HOSTS", "").strip()
            else "Set FINDREST_TRUSTED_HOSTS in production to reject unexpected Host headers.",
        ),
        BetaGate(
            "watch-storage",
            "Continuation watch storage",
            True,
            True,
            "SQLite watch storage is built in.",
        ),
        BetaGate(
            "scheduler",
            "Continuation scheduler",
            True,
            False,
            "Scheduler runner and Render cron wiring are included; deployment still determines whether it is running.",
        ),
        BetaGate(
            "push",
            "Push notification delivery",
            _configured("FINDREST_PUSH_ENDPOINT"),
            False,
            "Push gateway is configured." if _configured("FINDREST_PUSH_ENDPOINT")
            else "Push delivery requires a trusted configured APNs gateway.",
        ),
    ]

    critical = [g for g in gates if g.critical]
    critical_passed = sum(1 for g in critical if g.passed)
    passed = sum(1 for g in gates if g.passed)
    beta_ready = critical_passed == len(critical)

    return {
        "beta_ready": beta_ready,
        "critical_passed": critical_passed,
        "critical_total": len(critical),
        "passed": passed,
        "total": len(gates),
        "benchmark_pass_rate": benchmark["pass_rate"],
        "gates": [
            {
                "gate_id": g.gate_id,
                "label": g.label,
                "passed": g.passed,
                "critical": g.critical,
                "detail": g.detail,
            }
            for g in gates
        ],
    }
