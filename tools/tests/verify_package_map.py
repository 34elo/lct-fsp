#!/usr/bin/env python3
"""Verify that all skill slugs in package_map.yaml exist in skills.yaml."""

import sys
from pathlib import Path

import yaml


def main():
    """Load both files and verify skill slug references."""
    base_dir = Path(__file__).parent.parent.parent

    # Load skills
    skills_path = base_dir / "data/taxonomy/skills.yaml"
    with open(skills_path, encoding="utf-8") as f:
        skills_doc = yaml.safe_load(f) or {}

    skill_slugs = {skill["slug"] for skill in skills_doc.get("skills", [])}
    print(f"Loaded {len(skill_slugs)} skills from skills.yaml")

    # Load package map
    package_map_path = base_dir / "data/taxonomy/package_map.yaml"
    with open(package_map_path, encoding="utf-8") as f:
        package_doc = yaml.safe_load(f) or {}

    packages = package_doc.get("packages", {})
    print(f"Loaded {len(packages)} packages from package_map.yaml")

    # Verify each skill slug exists
    missing_skills = set()
    for package_name, skill_slug in packages.items():
        if skill_slug not in skill_slugs:
            missing_skills.add(skill_slug)
            print(f"❌ Missing skill: {package_name} → {skill_slug}")

    # Report results
    if missing_skills:
        print(f"\n❌ Found {len(missing_skills)} missing skill slug(s):")
        for slug in sorted(missing_skills):
            print(f"  - {slug}")
        return 1
    else:
        print(f"\n✓ All {len(set(packages.values()))} unique skill slugs exist in skills.yaml")
        return 0


if __name__ == "__main__":
    sys.exit(main())
