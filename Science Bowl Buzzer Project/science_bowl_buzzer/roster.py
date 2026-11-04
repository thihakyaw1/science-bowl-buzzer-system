from __future__ import annotations


def validate_roster(rows: list[dict]) -> dict[str, dict]:
    result = {}
    ids = set()
    for row in rows:
        port_text = str(row.get("port", "")).strip().upper().removeprefix("P")
        if not port_text:
            continue
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError(f"Invalid port: {port_text}") from exc
        if port not in range(1, 17) or str(port) in result:
            raise ValueError(f"Invalid or repeated port P{port}")
        person_id = str(row.get("person_id", "")).strip()
        name = str(row.get("name", "")).strip()
        if len(name) > 80 or len(person_id) > 80:
            raise ValueError("Player IDs and names must be at most 80 characters")
        if name and not person_id:
            raise ValueError(f"P{port}: enter a permanent player ID with the name")
        if person_id and name:
            if person_id in ids:
                raise ValueError(f"Player ID {person_id} is assigned to two ports")
            ids.add(person_id)
        result[str(port)] = {"person_id": person_id if name else "", "name": name}
    if len(result) != 16:
        raise ValueError("Roster must contain exactly one row for each port P1–P16")
    return result
