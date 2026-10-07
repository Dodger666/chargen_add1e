#!/usr/bin/env python3
"""Super simple FastAPI wrapper around rollhero.py.

Run with:
    uvicorn app:app --reload

Then open http://127.0.0.1:8000/docs to try it out.
"""

from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse

from rollhero import Character

app = FastAPI(title="rollhero", description="Generate AD&D-1e style characters.")


@app.get("/", response_class=PlainTextResponse)
def root():
    return (
        "rollhero API\n"
        "GET /roll  e.g. /roll?character_class=fighter&xp=12000\n"
        "See /docs for interactive usage."
    )


@app.get("/roll", response_class=PlainTextResponse)
def roll(
    character_class: Optional[str] = Query(
        None,
        description="Class: fighter, thief, cleric, magicuser, assassin, druid, "
        "paladin, illusionist, ranger, monk. Multiclass joined with '|', e.g. 'fighter|thief'.",
        examples=["fighter"],
    ),
    species: Optional[str] = Query(
        None,
        description="Species: human, halfling, dwarf, gnome, elf, half-orc, half-elf.",
        examples=["elf"],
    ),
    xp: Optional[int] = Query(
        None,
        ge=0,
        description="Experience points. Without it the character is level 1.",
        examples=[12000],
    ),
    seed: Optional[int] = Query(
        None,
        description="Seed for deterministic generation.",
        examples=[1],
    ),
    name: Optional[str] = Query(
        None,
        description="Character name.",
        examples=["Bob"],
    ),
    STR: Optional[int] = Query(None, description="Force STR attribute.", examples=[17]),
    DEX: Optional[int] = Query(None, description="Force DEX attribute."),
    CON: Optional[int] = Query(None, description="Force CON attribute."),
    INT: Optional[int] = Query(None, description="Force INT attribute."),
    WIS: Optional[int] = Query(None, description="Force WIS attribute."),
    CHA: Optional[int] = Query(None, description="Force CHA attribute."),
):
    """Generate a character sheet. All parameters are optional."""
    parts = []

    if character_class:
        parts.append(character_class)
    if species:
        parts.append(species)
    if xp is not None:
        parts.append(f"xp{xp}")
    if seed is not None:
        parts.append(f"seed{seed}")
    if name:
        parts.append(f"name={name}")
    for attr, value in (
        ("STR", STR),
        ("DEX", DEX),
        ("CON", CON),
        ("INT", INT),
        ("WIS", WIS),
        ("CHA", CHA),
    ):
        if value is not None:
            parts.append(f"{attr}={value}")

    command_line = " ".join(parts)
    char = Character.generate(command_line)
    return char.to_text_sheet()
