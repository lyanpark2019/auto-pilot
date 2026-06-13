"""Single source of truth: project ↔ vault ↔ NotebookLM mapping."""
from __future__ import annotations

from typing import Any

# Domain → vault info
DOMAINS: dict[str, dict[str, Any]] = {
    "sportic365": {
        "vault": "sportic365-Vault",
        "absorbs_vaults": ["Sportic", "SporTic365"],
        "sub_projects": [
            "sportic365",
            "sportic365-API",
            "sportic365-web",
            "sportic365-app",
            "sportic365-chat",
            "sportic365-evolution",
            "sportic365-paperclip",
        ],
        "notebooklm_cats_absorb": ["sportic-projects", "match-analysis"],
        "primary_input_repo": "sportic365",
    },
    "pickl": {
        "vault": "pickl-Vault",
        "absorbs_vaults": ["PickL-Vault"],
        "sub_projects": ["lyan/PickL", "lyan/PickL-API", "lyan/pickl-llm", "lyan/pickl-crawler", "lyan/pickl-llm-wt"],
        "notebooklm_cats_absorb": ["pickl-projects", "lotto"],
        "primary_input_repo": "lyan/PickL",
    },
    "clai": {
        "vault": "clai-Vault",
        "absorbs_vaults": ["CLAI"],
        "sub_projects": ["lyan/clai", "lyan/clai-api", "lyan/clai-web"],
        "notebooklm_cats_absorb": [],
        "primary_input_repo": "lyan/clai",
    },
    "agitrade": {
        "vault": "agitrade-Vault",
        "absorbs_vaults": [],
        "sub_projects": ["agitrade"],
        "notebooklm_cats_absorb": ["agri-trade"],
        "primary_input_repo": "agitrade",
    },
    "fyqro": {
        "vault": "fyqro-Vault",
        "absorbs_vaults": [],
        "sub_projects": ["fyqro/fyqro-admin", "fyqro/fyqro-b2b", "fyqro/fyqro-llm", "fyqro/fyqro-web"],
        "notebooklm_cats_absorb": [],
        "primary_input_repo": "fyqro",
    },
    "proto": {
        "vault": "proto-Vault",
        "absorbs_vaults": [],
        "sub_projects": ["proto", "proto-sync"],
        "notebooklm_cats_absorb": [],
        "primary_input_repo": "proto",
    },
    "ga4-collector": {
        "vault": "ga4-collector-Vault",
        "absorbs_vaults": ["ga4-collector"],
        "sub_projects": ["ga4-collector"],
        "notebooklm_cats_absorb": [],
        "primary_input_repo": "ga4-collector",
    },
    "EC2": {
        "vault": "EC2-Vault",
        "absorbs_vaults": [],
        "sub_projects": ["EC2"],
        "notebooklm_cats_absorb": [],
        "primary_input_repo": "EC2",
    },
    "misc-codebase": {
        "vault": "misc-codebase-Vault",
        "absorbs_vaults": [],
        "sub_projects": ["marketing", "design", "natstat", "notebook", "lyan/oklo", "lyan/invoice"],
        "notebooklm_cats_absorb": [],
        "primary_input_repo": "natstat",
    },
}

# Vaults to back up in Phase 1 (SSoT — kept here, not in phase01_backup.py)
VAULTS_TO_BACKUP = ["CLAI", "ga4-collector", "PickL-Vault", "Sportic", "SporTic365", "NotebookLM-Archive"]

# Sportic/ sub-vaults absorbed into sportic365-Vault/_sub-projects/ in Phase 3
SPORTIC_SUB_DIRS = ["sportic365-API", "sportic365-studio", "sportic365-syndicator", "sportic365-notebooklm"]

# Simple renames (Phase 2): old vault dir → new name
SIMPLE_RENAMES = {
    "CLAI": "clai-Vault",
    "ga4-collector": "ga4-collector-Vault",
    "PickL-Vault": "pickl-Vault",
}

# NotebookLM categories that stay in NotebookLM-Archive (generic knowledge)
NBM_GENERIC_KEEP = ["ai-libraries", "llm-research"]

# NotebookLM live notebooks to create per domain (name → source URLs / topic).
# Empty source list means "skeleton notebook only — user adds sources later".
NBM_NEW_NOTEBOOKS: dict[str, list[dict[str, str]]] = {
    "sportic365": [
        {"name": "sportic365-app-mobile", "topic": "React Native mobile architecture"},
        {"name": "sportic365-evolution", "topic": "feature evolution + experiments"},
    ],
    "clai": [
        {"name": "clai-architecture", "topic": "CLAI invoice automation system architecture"},
        {"name": "clai-llm-research", "topic": "LLM/agent patterns for clai"},
    ],
    "agitrade": [
        {"name": "agitrade-product-spec", "topic": "AgriTrade platform spec + research"},
    ],
    "fyqro": [
        {"name": "fyqro-platform", "topic": "fyqro multi-app platform architecture"},
    ],
    "proto": [
        {"name": "proto-crawler-arch", "topic": "Proto crawler + sync architecture"},
    ],
    "ga4-collector": [
        {"name": "ga4-collector-runbook", "topic": "GA4 collector ops runbook"},
    ],
    "EC2": [
        {"name": "sportic-server-ops", "topic": "Sportic prod/dev server ops + automation"},
    ],
}

PASS_THRESHOLD = 95
MAX_VAULT_BUILD_ROUNDS = 8
