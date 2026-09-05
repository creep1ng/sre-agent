#!/usr/bin/env python3
"""Validate HT/HU issue forms and render a no-write draft preview."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import yaml

ORDER = [
    "Problema",
    "Resultado observable",
    "Contratos",
    "Entregables",
    "Criterios de aceptación",
    "Evidencia de aceptación",
    "Definition of Ready",
    "Fuera de alcance",
    "Decisiones abiertas",
]
ROOT = Path(__file__).parents[1]
EXPECTED_FORM = {
    "ht": ("[HT-XX] ", "type: technical task"),
    "hu": ("[HU-XX] ", "type: user story"),
}


def fields(document: dict) -> list[dict]:
    return [item for item in document["body"] if item["type"] != "markdown"]


def validate(document: dict, kind: str) -> None:
    items = fields(document)
    labels = [item["attributes"]["label"] for item in items]
    if labels != ORDER:
        raise ValueError(f"{kind}: field order is {labels}, expected {ORDER}")
    if any(
        item["type"] != "textarea"
        or not item.get("validations", {}).get("required")
        for item in items
    ):
        raise ValueError(f"{kind}: every planning field must be a required textarea")
    ids = {item["id"] for item in items}
    expected_title, expected_label = EXPECTED_FORM[kind]
    if {"planning", "dependencies"} & ids:
        raise ValueError(f"{kind}: metadata must not be a body field")
    if document.get("title") != expected_title or document.get("labels") != [expected_label]:
        raise ValueError(f"{kind}: title prefix or type label is incorrect")
    dor = next(item for item in items if item["id"] == "definition_of_ready")
    dor_description = dor["attributes"]["description"].lower()
    if dor["type"] != "textarea" or "puede publicarse" not in dor_description:
        raise ValueError(f"{kind}: DoR must allow unresolved prerequisites")
    evidence = next(
        item for item in items if item["id"] == "acceptance_evidence"
    )["attributes"]["description"].lower()
    if not all(word in evidence for word in ("comandos", "capturas", "video")):
        raise ValueError(f"{kind}: evidence must include functional proof methods")
    if "tests solos no bastan" not in evidence:
        raise ValueError(f"{kind}: evidence must be functional, not tests alone")
    guide = document["body"][0]["attributes"]["value"].lower()
    metadata_terms = ("github projects", "labels", "assignees", "blocked by", "blocks")
    if not all(value in guide for value in metadata_terms):
        raise ValueError(f"{kind}: project/native metadata guidance is incomplete")


def preview(document: dict) -> str:
    values = {
        "Problema": "Necesidad y contexto concretos.",
        "Resultado observable": (
            "**Como** rol, **quiero** capacidad **para** beneficio verificable."
        ),
        "Contratos": "Contrato identificado.",
        "Entregables": "Artefacto entregable.",
        "Criterios de aceptación": "- [ ] Criterio funcional verificable.",
        "Evidencia de aceptación": "Comando, captura o video del resultado funcional.",
        "Definition of Ready": "- [ ] Contrato externo pendiente: #123\n- [x] Riesgo identificado.",
        "Fuera de alcance": "No incluye capacidades adyacentes.",
        "Decisiones abiertas": "Ninguna.",
    }
    sections = []
    for item in fields(document):
        label = item["attributes"]["label"]
        sections.append(f"### {label}\n{values[label]}")
    return "\n\n".join(sections)


def assert_rejected(document: dict, reason: str, kind: str) -> None:
    try:
        validate(document, kind)
    except ValueError:
        return
    raise AssertionError(f"negative {reason} fixture was accepted")


def load_documents() -> dict[str, dict]:
    template_dir = ROOT / ".github/ISSUE_TEMPLATE"
    return {
        kind: yaml.safe_load((template_dir / f"{kind}.yml").read_text())
        for kind in ("ht", "hu")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", choices=("ht", "hu"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    documents = load_documents()
    for kind, document in documents.items():
        validate(document, kind)
    if args.self_test:
        invalid_dor = deepcopy(documents["ht"])
        invalid_dor["body"][7]["type"] = "checkboxes"
        assert_rejected(invalid_dor, "DoR", "ht")
        invalid_order = deepcopy(documents["hu"])
        invalid_order["body"][1], invalid_order["body"][2] = (
            invalid_order["body"][2],
            invalid_order["body"][1],
        )
        assert_rejected(invalid_order, "field order", "hu")
        invalid_metadata = deepcopy(documents["hu"])
        invalid_metadata["body"][-1]["id"] = "planning"
        assert_rejected(invalid_metadata, "metadata", "hu")
        invalid_label = deepcopy(documents["ht"])
        invalid_label["labels"] = ["type: user story"]
        assert_rejected(invalid_label, "type label", "ht")
    if args.preview:
        print(preview(documents[args.preview]))
    print("Issue forms valid; unresolved DoR draft is accepted.")


if __name__ == "__main__":
    main()
