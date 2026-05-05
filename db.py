from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "app.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"
GEOHASH_INDEX = {char: index for index, char in enumerate(GEOHASH_ALPHABET)}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        seed_data(connection)


def encode_geohash(lat: float, lon: float, precision: int = 6) -> str:
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    bits = [16, 8, 4, 2, 1]

    geohash: list[str] = []
    bit_index = 0
    char_bits = 0
    is_even_bit = True

    while len(geohash) < precision:
        if is_even_bit:
            midpoint = (lon_interval[0] + lon_interval[1]) / 2
            if lon >= midpoint:
                char_bits |= bits[bit_index]
                lon_interval[0] = midpoint
            else:
                lon_interval[1] = midpoint
        else:
            midpoint = (lat_interval[0] + lat_interval[1]) / 2
            if lat >= midpoint:
                char_bits |= bits[bit_index]
                lat_interval[0] = midpoint
            else:
                lat_interval[1] = midpoint

        is_even_bit = not is_even_bit

        if bit_index < 4:
            bit_index += 1
            continue

        geohash.append(GEOHASH_ALPHABET[char_bits])
        bit_index = 0
        char_bits = 0

    return "".join(geohash)


def decode_geohash(geohash: str) -> tuple[tuple[float, float], tuple[float, float]]:
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    bits = [16, 8, 4, 2, 1]
    is_even_bit = True

    for char in geohash:
        char_value = GEOHASH_INDEX[char]

        for bit in bits:
            if is_even_bit:
                midpoint = (lon_interval[0] + lon_interval[1]) / 2
                if char_value & bit:
                    lon_interval[0] = midpoint
                else:
                    lon_interval[1] = midpoint
            else:
                midpoint = (lat_interval[0] + lat_interval[1]) / 2
                if char_value & bit:
                    lat_interval[0] = midpoint
                else:
                    lat_interval[1] = midpoint

            is_even_bit = not is_even_bit

    return (lat_interval[0], lat_interval[1]), (lon_interval[0], lon_interval[1])


def geohash_neighbors(geohash: str) -> list[str]:
    lat_interval, lon_interval = decode_geohash(geohash)
    lat_step = lat_interval[1] - lat_interval[0]
    lon_step = lon_interval[1] - lon_interval[0]
    center_lat = (lat_interval[0] + lat_interval[1]) / 2
    center_lon = (lon_interval[0] + lon_interval[1]) / 2

    hashes: list[str] = []
    precision = len(geohash)

    for lat_offset in (1, 0, -1):
        lat = max(-90.0, min(90.0, center_lat + (lat_step * lat_offset)))

        for lon_offset in (-1, 0, 1):
            lon = center_lon + (lon_step * lon_offset)

            if lon < -180.0:
                lon += 360.0
            elif lon > 180.0:
                lon -= 360.0

            hashes.append(encode_geohash(lat, lon, precision=precision))

    return hashes


def seed_data(connection: sqlite3.Connection) -> None:
    demo_hash = hash_password("demo")
    user = connection.execute(
        "SELECT id FROM users WHERE username = ?",
        ("demo",),
    ).fetchone()

    if user is None:
        cursor = connection.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("demo", demo_hash),
        )
        user_id = cursor.lastrowid
    else:
        user_id = user["id"]
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ? AND password_hash != ?
            """,
            (demo_hash, user_id, demo_hash),
        )

    stream = connection.execute(
        "SELECT id FROM streams WHERE id = 1"
    ).fetchone()

    if stream is None:
        connection.execute(
            """
            INSERT INTO streams (id, user_id, name, description, color, emoji)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, user_id, "General", "Default demo stream", "#3498db", "📍"),
        )

    connection.execute(
        "INSERT OR IGNORE INTO subscriptions (user_id, stream_id) VALUES (?, ?)",
        (user_id, 1),
    )

    other_user = connection.execute(
        "SELECT id FROM users WHERE username = ?",
        ("alice",),
    ).fetchone()

    if other_user is None:
        cursor = connection.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("alice", demo_hash),
        )
        other_user_id = cursor.lastrowid
    else:
        other_user_id = other_user["id"]
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ? AND password_hash != ?
            """,
            (demo_hash, other_user_id, demo_hash),
        )

    other_stream = connection.execute(
        "SELECT id FROM streams WHERE user_id = ? AND name = ?",
        (other_user_id, "Neighborhood"),
    ).fetchone()

    if other_stream is None:
        connection.execute(
            """
            INSERT INTO streams (user_id, name, description, color, emoji)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                other_user_id,
                "Neighborhood",
                "Nearby places and local notes",
                "#2ecc71",
                "🌳",
            ),
        )
