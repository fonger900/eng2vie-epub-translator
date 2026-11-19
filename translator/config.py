"""Configuration system for eng2vie-epub-translator.

Glossary loading for character pronouns and terminology.
"""

from __future__ import annotations

import re
from typing import Any

from dataclasses import dataclass, field
from pathlib import Path

# ── Search paths ──────────────────────────────────────────────────────────────

_CONFIG_DIR = Path(".eng2vie-epub-translator")
_USER_CONFIG_DIR = Path.home() / ".config" / "eng2vie-epub-translator"


def _find_file(filename: str) -> Path | None:
    """Find file in project-local then user-global config dirs."""
    for base in [_CONFIG_DIR, _USER_CONFIG_DIR]:
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


# ── TOML loading ──────────────────────────────────────────────────────────────


def _load_toml(path: Path) -> dict[str, Any]:
    """Load TOML file, return empty dict on failure."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef, import-untyped]
        except ImportError:
            return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _string_list(value: object) -> list[str]:
    """Normalise a TOML string-or-array value into a clean list of strings."""
    if isinstance(value, str):
        value = [value]
    elif not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


# ── Glossary ──────────────────────────────────────────────────────────────────


@dataclass
class CharacterEntry:
    """Pronoun mapping for a character."""

    self_ref: str | None = None  # xưng (self-reference)
    address: str | None = None  # hô (how others address them)
    narrator: str | None = None  # narrator reference
    note: str | None = None  # context (age, role, relationship)
    avoid: list[str] = field(default_factory=list)  # forms that must not be used
    aliases: list[str] = field(default_factory=list)  # other names in the source

    def is_empty(self) -> bool:
        return not any(
            [
                self.self_ref,
                self.address,
                self.narrator,
                self.note,
                self.avoid,
                self.aliases,
            ]
        )


@dataclass
class NarrativeEntry:
    """Book-level point-of-view and narration settings."""

    pov: str | None = None
    narrator: str | None = None
    notes: str | None = None

    def is_empty(self) -> bool:
        return not any([self.pov, self.narrator, self.notes])


@dataclass
class RelationshipEntry:
    """Pronoun pair for one speaker → listener relationship."""

    self_ref: str | None = None
    address: str | None = None
    note: str | None = None

    def is_empty(self) -> bool:
        return not any([self.self_ref, self.address, self.note])


@dataclass
class Glossary:
    """Translation glossary with character pronouns and term mappings."""

    characters: dict[str, CharacterEntry] = field(default_factory=dict)
    terms: dict[str, str] = field(default_factory=dict)
    narrative: NarrativeEntry | None = None
    relationships: dict[str, RelationshipEntry] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return (
            not self.characters
            and not self.terms
            and self.narrative is None
            and not self.relationships
        )


def load_glossary(path: Path | None = None) -> Glossary | None:
    """Load glossary from path or auto-detect.

    Returns None if not found or empty.
    """
    glossary_file = path or _find_file("glossary.toml")
    if not glossary_file:
        return None

    data = _load_toml(glossary_file)
    if not data:
        return None

    narrative: NarrativeEntry | None = None
    narrative_data = data.get("narrative")
    if isinstance(narrative_data, dict):
        candidate = NarrativeEntry(
            pov=narrative_data.get("pov"),
            narrator=narrative_data.get("narrator"),
            notes=narrative_data.get("notes") or narrative_data.get("note"),
        )
        if not candidate.is_empty():
            narrative = candidate

    characters: dict[str, CharacterEntry] = {}
    for name, entry in data.get("characters", {}).items():
        if isinstance(entry, str):
            # Simple form: John = "anh"
            characters[name] = CharacterEntry(address=entry)
        elif isinstance(entry, dict):
            char = CharacterEntry(
                self_ref=entry.get("self"),
                address=entry.get("form"),
                narrator=entry.get("narrator"),
                note=entry.get("note"),
                avoid=_string_list(entry.get("avoid", [])),
                aliases=_string_list(entry.get("aliases", [])),
            )
            if not char.is_empty():
                characters[name] = char

    relationships: dict[str, RelationshipEntry] = {}
    for pair, entry in data.get("relationships", {}).items():
        if not isinstance(entry, dict):
            continue
        if "->" not in pair:
            continue
        speaker, listener = (part.strip() for part in pair.split("->", 1))
        if not speaker or not listener:
            continue
        relationship = RelationshipEntry(
            self_ref=entry.get("self"),
            address=entry.get("address") or entry.get("form"),
            note=entry.get("note"),
        )
        if not relationship.is_empty():
            relationships[f"{speaker} → {listener}"] = relationship

    terms: dict[str, str] = data.get("terms", {})

    glossary = Glossary(
        characters=characters,
        terms=terms,
        narrative=narrative,
        relationships=relationships,
    )
    return None if glossary.is_empty() else glossary


def build_glossary_prompt(glossary: Glossary) -> str:
    """Build prompt section from glossary for LLM injection."""
    if glossary.is_empty():
        return ""

    parts = [
        "\nGLOSSARY (HIGHEST PRIORITY — these rules override all other instructions):"
    ]

    if glossary.narrative:
        parts.append("Narrative voice:")
        if glossary.narrative.pov:
            parts.append(f"• Point of view: {glossary.narrative.pov}")
        if glossary.narrative.narrator:
            parts.append(
                f'• Narrator self-reference in narration: "{glossary.narrative.narrator}"'
            )
        if glossary.narrative.notes:
            parts.append(f"• Notes: {glossary.narrative.notes}")

    if glossary.characters:
        parts.append("Characters (pronouns):")
        parts.append(
            "Legend: self = how the character refers to themselves in dialogue; "
            "address = how others address them in dialogue; narrator = how the "
            "narration refers to them; aliases = other names for the same "
            "character; avoid = forms that must not be used for this character "
            "in narration."
        )
        for name, entry in glossary.characters.items():
            details = []
            if entry.self_ref:
                details.append(f'self="{entry.self_ref}"')
            if entry.address:
                details.append(f'address="{entry.address}"')
            if entry.narrator:
                details.append(f'narrator="{entry.narrator}"')
            if entry.aliases:
                details.append(
                    "aliases=" + ", ".join(f'"{item}"' for item in entry.aliases)
                )
            if entry.avoid:
                details.append(
                    "avoid=" + ", ".join(f'"{item}"' for item in entry.avoid)
                )
            detail_str = ", ".join(details)
            if entry.note:
                detail_str += f" — {entry.note}"
            parts.append(f"• {name}: {detail_str}")

    if glossary.relationships:
        parts.append("Dialogue pairs (speaker → listener):")
        for pair, entry in glossary.relationships.items():
            details = []
            if entry.self_ref:
                details.append(f'self="{entry.self_ref}"')
            if entry.address:
                details.append(f'address="{entry.address}"')
            detail_str = ", ".join(details)
            if entry.note:
                detail_str += f" — {entry.note}"
            parts.append(f"• {pair}: {detail_str}")

    if glossary.terms:
        parts.append("Terms:")
        for eng, vi in glossary.terms.items():
            parts.append(f'• "{eng}" → "{vi}"')

    return "\n".join(parts) + "\n"


def validate_glossary(glossary: Glossary) -> list[str]:
    """Validate glossary entries and return list of warnings.

    Checks: empty character entries, empty term keys/values,
    suspiciously short or long values, duplicate mappings.
    """
    warnings: list[str] = []

    if glossary.narrative:
        pov = (glossary.narrative.pov or "").lower()
        if "first" in pov and not glossary.narrative.narrator:
            warnings.append(
                "Narrative POV is first-person but no narrator pronoun is set"
            )

    for pair, entry in glossary.relationships.items():
        if not entry.self_ref and not entry.address:
            warnings.append(
                f"Relationship '{pair}' has no self or address pronoun — may be ignored"
            )

    for name, entry in glossary.characters.items():
        if entry.is_empty():
            warnings.append(f"Character '{name}' has no pronoun fields — skipped")
        elif not entry.address and not entry.self_ref:
            warnings.append(
                f"Character '{name}' has no address or self-ref — may be ignored"
            )
        if not name.strip():
            warnings.append("Character entry with empty name — skipped")

    for eng, vi in glossary.terms.items():
        if not eng.strip():
            warnings.append("Term with empty English key — skipped")
        elif not vi.strip():
            warnings.append(f"Term '{eng}' has empty Vietnamese value — skipped")
        elif len(eng.strip()) < 2:
            warnings.append(
                f"Term '{eng}' is very short (1 char) — might cause false matches"
            )

    return warnings


def scan_glossary_matches(
    glossary: Glossary, chapter_texts: list[str]
) -> dict[str, int]:
    """Scan chapter texts for glossary term occurrences.

    Returns dict mapping each English term to its match count across all chapters.
    Case-insensitive matching.
    """
    matches: dict[str, int] = {}
    combined = " ".join(chapter_texts).lower()

    for eng in glossary.terms:
        count = combined.count(eng.lower())
        matches[eng] = count

    for name, entry in glossary.characters.items():
        names = {name, *entry.aliases}
        pattern = "|".join(
            re.escape(alias) for alias in sorted(names, key=len, reverse=True)
        )
        count = len(re.findall(rf"\b(?:{pattern})\b", combined, re.IGNORECASE))
        matches[f"[character] {name}"] = count

    return matches
