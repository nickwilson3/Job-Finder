"""File-system helpers and credential encryption for per-user data."""
import json
import os
from pathlib import Path

import yaml
from cryptography.fernet import Fernet

USER_DATA_ROOT = Path(__file__).parent.parent / "user_data"

def _get_fernet() -> "Fernet":
    key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY not set — cannot store credentials securely.")
    return Fernet(key.encode())


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def user_dir(user_id: int) -> Path:
    return USER_DATA_ROOT / str(user_id)


def ensure_user_dirs(user_id: int) -> Path:
    base = user_dir(user_id)
    for sub in ("inputs", "outputs/applications", "config", "logs"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def inputs_dir(user_id: int) -> Path:
    return user_dir(user_id) / "inputs"


def outputs_dir(user_id: int) -> Path:
    return user_dir(user_id) / "outputs"


def config_dir(user_id: int) -> Path:
    return user_dir(user_id) / "config"


def log_path(user_id: int) -> Path:
    return user_dir(user_id) / "logs" / "run.log"


def google_token_path(user_id: int) -> Path:
    return inputs_dir(user_id) / "google_token.json"


# ---------------------------------------------------------------------------
# YAML config helpers
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "cities": [],
    "job_titles": [],
    "keywords": [],
    "exclude_keywords": [],
    "filters": {
        "employment_type": "full-time",
        "remote_options": ["remote", "hybrid", "on-site"],
        "posted_within_days": 30,
    },
    "sources": {"linkedin": True, "company_sites": True},
    "max_jobs_per_run": 50,
    "max_companies_to_check": 100,
    "output": {"applications_dir": "outputs/applications"},
}

DEFAULT_CRITERIA = {
    "candidate": {
        "name": "",
        "target_titles": [],
        "years_of_experience": 0,
        "experience_level": "Entry",
        "skills": {"strong": [], "familiar": []},
        "industries": [],
        "soft_skills": [],
    },
    "location": {
        "preferred_cities": [],
        "work_arrangement": ["remote", "hybrid", "on-site"],
        "willing_to_relocate": False,
    },
    "requirements": {
        "must_have_keywords": [],
        "deal_breakers": [],
        "employment_type": "full-time",
        "posted_within_days": 30,
    },
    "scoring_weights": {
        "skills_match": 40,
        "experience_level": 20,
        "title_alignment": 20,
        "industry_fit": 10,
        "location_fit": 10,
    },
    "min_score_to_tailor": 50,
    "strong_match_threshold": 85,
}


def read_settings(user_id: int) -> dict:
    path = config_dir(user_id) / "settings.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return dict(DEFAULT_SETTINGS)


def write_settings(user_id: int, data: dict) -> None:
    path = config_dir(user_id) / "settings.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def read_criteria(user_id: int) -> dict:
    path = config_dir(user_id) / "criteria.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return dict(DEFAULT_CRITERIA)


def write_criteria(user_id: int, data: dict) -> None:
    path = config_dir(user_id) / "criteria.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# LinkedIn credential encryption
# ---------------------------------------------------------------------------

def encrypt_linkedin_creds(email: str, password: str) -> str:
    payload = json.dumps({"email": email, "password": password})
    return _get_fernet().encrypt(payload.encode()).decode()


def decrypt_linkedin_creds(encrypted: str) -> dict:
    data = _get_fernet().decrypt(encrypted.encode())
    return json.loads(data)
