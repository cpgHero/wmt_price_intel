"""Build a read-only Walmart/nearby-retailer panel from the location master."""

import asyncio
import json
import math
import os
from collections import Counter, defaultdict

from sqlalchemy import text

from rci_db import DatabaseProbe

RETAILERS = (
    "walmart_us",
    "bjs_us",
    "costco_us",
    "cvs_us",
    "kroger_us",
    "meijer_us",
    "sams_club_us",
    "target_us",
    "walgreens_us",
)
COMPETITORS = set(RETAILERS) - {"walmart_us"}


def miles(a, b):
    radius = 3958.7613
    lat1, lon1 = math.radians(a["latitude"]), math.radians(a["longitude"])
    lat2, lon2 = math.radians(b["latitude"]), math.radians(b["longitude"])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


async def main():
    database = DatabaseProbe(os.environ["DATABASE_URL"])
    async with database.engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT retailer_id, store_number, zipcode, city, state,
                           latitude, longitude, status, collection_eligible,
                           collection_eligibility_reason
                    FROM retailer_location
                    WHERE retailer_id = ANY(:retailers)
                      AND country = 'USA'
                      AND latitude IS NOT NULL
                      AND longitude IS NOT NULL
                    """
                    ),
                    {"retailers": list(RETAILERS)},
                )
            )
            .mappings()
            .all()
        )
    await database.dispose()

    locations = [dict(row) for row in rows]
    counts = {}
    for retailer in RETAILERS:
        retailer_rows = [row for row in locations if row["retailer_id"] == retailer]
        counts[retailer] = {
            "rows": len(retailer_rows),
            "active": sum(str(row["status"]).lower() == "active" for row in retailer_rows),
            "collection_eligible": sum(bool(row["collection_eligible"]) for row in retailer_rows),
            "ineligibility_reasons": Counter(
                row["collection_eligibility_reason"] or "eligible" for row in retailer_rows
            ),
        }

    valid = [row for row in locations if str(row["status"]).lower() == "active"]
    walmart = [row for row in valid if row["retailer_id"] == "walmart_us"]
    competitors = [row for row in valid if row["retailer_id"] in COMPETITORS]
    cell = 0.1
    buckets = defaultdict(list)
    for row in competitors:
        buckets[(int(row["latitude"] / cell), int(row["longitude"] / cell))].append(row)

    coverage = []
    for anchor in walmart:
        lat_cell = int(anchor["latitude"] / cell)
        lon_cell = int(anchor["longitude"] / cell)
        nearest = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for candidate in buckets.get((lat_cell + dy, lon_cell + dx), ()):
                    distance = miles(anchor, candidate)
                    if distance > 5:
                        continue
                    retailer = candidate["retailer_id"]
                    if retailer not in nearest or distance < nearest[retailer][0]:
                        nearest[retailer] = (distance, candidate)
        if nearest:
            coverage.append((anchor, nearest))

    uncovered = set(COMPETITORS)
    selected = []
    while uncovered:
        options = [
            (len(set(nearest) & uncovered), anchor, nearest)
            for anchor, nearest in coverage
            if set(nearest) & uncovered
        ]
        if not options:
            break
        options.sort(key=lambda row: (-row[0], row[1]["state"], row[1]["store_number"]))
        _, anchor, nearest = options[0]
        selected.append((anchor, nearest))
        uncovered -= set(nearest)

    top = sorted(
        coverage,
        key=lambda row: (-len(row[1]), row[0]["state"], row[0]["store_number"]),
    )[:20]

    def serialize(items):
        result = []
        for anchor, nearest in items:
            result.append(
                {
                    "walmart": {
                        key: anchor[key] for key in ("store_number", "zipcode", "city", "state")
                    },
                    "nearby": {
                        retailer: {
                            "distance_miles": round(distance, 3),
                            **{
                                key: location[key]
                                for key in ("store_number", "zipcode", "city", "state")
                            },
                            "collection_eligible": bool(location["collection_eligible"]),
                            "eligibility_reason": location["collection_eligibility_reason"],
                        }
                        for retailer, (distance, location) in sorted(nearest.items())
                    },
                }
            )
        return result

    print(
        json.dumps(
            {
                "counts": {
                    retailer: {
                        **{
                            key: value
                            for key, value in data.items()
                            if key != "ineligibility_reasons"
                        },
                        "ineligibility_reasons": dict(data["ineligibility_reasons"]),
                    }
                    for retailer, data in counts.items()
                },
                "greedy_panel": serialize(selected),
                "uncovered_retailers": sorted(uncovered),
                "top_walmart_anchors": serialize(top),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
