from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from db import encode_geohash, geohash_neighbors, get_connection, init_db


DEMO_USER_ID = 1
BASE_DIR = Path(__file__).resolve().parent


class StreamCreate(BaseModel):
    name: str
    description: str | None = None
    color: str
    emoji: str

    @field_validator("name", "color", "emoji")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class SubscriptionCreate(BaseModel):
    stream_id: int


class PostCreate(BaseModel):
    stream_id: int
    lat: float
    lon: float
    text: str

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, value: float) -> float:
        if not -90 <= value <= 90:
            raise ValueError("lat must be between -90 and 90")
        return value

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, value: float) -> float:
        if not -180 <= value <= 180:
            raise ValueError("lon must be between -180 and 180")
        return value


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="HTAE Backend", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/streams")
def list_streams():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
              s.id,
              s.user_id,
              s.name,
              s.description,
              s.color,
              s.emoji,
              u.username AS owner_username
            FROM streams AS s
            JOIN users AS u ON u.id = s.user_id
            ORDER BY s.id ASC
            """
        ).fetchall()

    return [serialize_stream(row) for row in rows]


@app.post("/streams")
def create_stream(payload: StreamCreate):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO streams (user_id, name, description, color, emoji)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                DEMO_USER_ID,
                payload.name,
                payload.description,
                payload.color,
                payload.emoji,
            ),
        )
        stream_id = cursor.lastrowid
        connection.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, stream_id) VALUES (?, ?)",
            (DEMO_USER_ID, stream_id),
        )
        row = connection.execute(
            """
            SELECT
              s.id,
              s.user_id,
              s.name,
              s.description,
              s.color,
              s.emoji,
              u.username AS owner_username
            FROM streams AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (stream_id,),
        ).fetchone()

    return serialize_stream(row)


@app.get("/subscriptions")
def list_subscriptions():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT stream_id
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY stream_id ASC
            """,
            (DEMO_USER_ID,),
        ).fetchall()

    return [row["stream_id"] for row in rows]


@app.post("/subscriptions")
def create_subscription(payload: SubscriptionCreate):
    with get_connection() as connection:
        stream = connection.execute(
            "SELECT id FROM streams WHERE id = ?",
            (payload.stream_id,),
        ).fetchone()
        if stream is None:
            raise HTTPException(status_code=404, detail="Stream not found")

        connection.execute(
            """
            INSERT OR IGNORE INTO subscriptions (user_id, stream_id)
            VALUES (?, ?)
            """,
            (DEMO_USER_ID, payload.stream_id),
        )

    return {"stream_id": payload.stream_id}


@app.get("/streams/{stream_id}/export")
def export_stream(stream_id: int):
    with get_connection() as connection:
        stream = connection.execute(
            "SELECT id FROM streams WHERE id = ?",
            (stream_id,),
        ).fetchone()
        if stream is None:
            raise HTTPException(status_code=404, detail="Stream not found")

        rows = connection.execute(
            """
            SELECT id, user_id, lat, lon, text, created_at
            FROM posts
            WHERE stream_id = ?
            ORDER BY id ASC
            """,
            (stream_id,),
        ).fetchall()

    return {
        "type": "FeatureCollection",
        "features": [serialize_geojson_feature(row) for row in rows],
    }


@app.post("/posts")
def create_post(payload: PostCreate):
    created_at = datetime.now(timezone.utc).isoformat()
    geohash = encode_geohash(payload.lat, payload.lon, precision=6)

    with get_connection() as connection:
        stream = connection.execute(
            """
            SELECT
              s.id,
              s.user_id
            FROM streams AS s
            WHERE s.id = ?
            """,
            (payload.stream_id,),
        ).fetchone()
        if stream is None:
            raise HTTPException(status_code=404, detail="Stream not found")
        if stream["user_id"] != DEMO_USER_ID:
            raise HTTPException(
                status_code=403,
                detail="You can only post to your own streams",
            )

        cursor = connection.execute(
            """
            INSERT INTO posts (user_id, stream_id, lat, lon, geohash, created_at, text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEMO_USER_ID,
                payload.stream_id,
                payload.lat,
                payload.lon,
                geohash,
                created_at,
                payload.text,
            ),
        )

        row = connection.execute(
            """
            SELECT
              p.id,
              p.lat,
              p.lon,
              p.text,
              s.id AS stream_id,
              s.name AS stream_name,
              s.color AS stream_color,
              s.emoji AS stream_emoji
            FROM posts AS p
            JOIN streams AS s ON s.id = p.stream_id
            WHERE p.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return serialize_post(row)


@app.get("/posts")
def list_posts(lat: float | None = None, lon: float | None = None):
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=400, detail="lat and lon must be provided together")

    if lat is not None and not -90 <= lat <= 90:
        raise HTTPException(status_code=400, detail="lat must be between -90 and 90")

    if lon is not None and not -180 <= lon <= 180:
        raise HTTPException(status_code=400, detail="lon must be between -180 and 180")

    query = """
        SELECT
          p.id,
          p.lat,
          p.lon,
          p.text,
          s.id AS stream_id,
          s.name AS stream_name,
          s.color AS stream_color,
          s.emoji AS stream_emoji
        FROM posts AS p
        JOIN streams AS s ON s.id = p.stream_id
    """
    parameters: list[str | float] = []

    if lat is not None and lon is not None:
        center_geohash = encode_geohash(lat, lon, precision=6)
        target_geohashes = geohash_neighbors(center_geohash)
        placeholders = ", ".join("?" for _ in target_geohashes)
        query += f" WHERE p.geohash IN ({placeholders})"
        parameters.extend(target_geohashes)

    query += " ORDER BY p.id DESC"

    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [serialize_post(row) for row in rows]


def serialize_post(row) -> dict:
    return {
        "id": row["id"],
        "lat": row["lat"],
        "lon": row["lon"],
        "text": row["text"],
        "stream": {
            "id": row["stream_id"],
            "name": row["stream_name"],
            "color": row["stream_color"],
            "emoji": row["stream_emoji"],
        },
    }


def serialize_stream(row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "description": row["description"],
        "color": row["color"],
        "emoji": row["emoji"],
        "owner_username": row["owner_username"],
    }


def serialize_geojson_feature(row) -> dict:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [row["lon"], row["lat"]],
        },
        "properties": {
            "user_id": row["user_id"],
            "text": row["text"],
            "timestamp": row["created_at"],
        },
    }
