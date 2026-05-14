from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from pydantic import BaseModel, field_validator

from db import encode_geohash, geohash_neighbors, get_connection, init_db

BASE_DIR = Path(__file__).resolve().parent


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def require_user(connection, user_id: int):
    user = connection.execute(
        "SELECT id, username FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid user_id")
    return user


class Credentials(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value


class StreamCreate(BaseModel):
    user_id: int
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
    user_id: int
    stream_id: int


class PostCreate(BaseModel):
    user_id: int
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
security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "PLATEAU")
    correct_password = secrets.compare_digest(credentials.password, "UT2026")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/")
def index(authuser: str = Depends(get_current_username)):
    return FileResponse(BASE_DIR / "index.html")


@app.post("/users")
def create_user(payload: Credentials, authuser: str = Depends(get_current_username)):
    password_hash = hash_password(payload.password)

    with get_connection() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
                """,
                (payload.username, password_hash),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Username already exists") from error

    return {"user_id": cursor.lastrowid, "username": payload.username}


@app.post("/login")
def login(payload: Credentials, authuser: str = Depends(get_current_username)):
    with get_connection() as connection:
        user = connection.execute(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE username = ?
            """,
            (payload.username,),
        ).fetchone()

    if user is None or user["password_hash"] != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {"user_id": user["id"], "username": user["username"]}


@app.get("/streams")
def list_streams(user_id: int, authuser: str = Depends(get_current_username)):
    with get_connection() as connection:
        require_user(connection, user_id)
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
def create_stream(payload: StreamCreate, authuser: str = Depends(get_current_username)):
    with get_connection() as connection:
        require_user(connection, payload.user_id)
        cursor = connection.execute(
            """
            INSERT INTO streams (user_id, name, description, color, emoji)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload.user_id,
                payload.name,
                payload.description,
                payload.color,
                payload.emoji,
            ),
        )
        stream_id = cursor.lastrowid
        connection.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, stream_id) VALUES (?, ?)",
            (payload.user_id, stream_id),
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
def list_subscriptions(user_id: int, authuser: str = Depends(get_current_username)):
    with get_connection() as connection:
        require_user(connection, user_id)
        rows = connection.execute(
            """
            SELECT stream_id
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY stream_id ASC
            """,
            (user_id,),
        ).fetchall()

    return [row["stream_id"] for row in rows]


@app.post("/subscriptions")
def create_subscription(payload: SubscriptionCreate, authuser: str = Depends(get_current_username)):
    with get_connection() as connection:
        require_user(connection, payload.user_id)
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
            (payload.user_id, payload.stream_id),
        )

    return {"stream_id": payload.stream_id}


@app.get("/streams/{stream_id}/export")
def export_stream(stream_id: int, user_id: int, authuser: str = Depends(get_current_username)):
    with get_connection() as connection:
        require_user(connection, user_id)
        stream = connection.execute(
            """
            SELECT id, name
            FROM streams
            WHERE id = ?
            """,
            (stream_id,),
        ).fetchone()
        if stream is None:
            raise HTTPException(status_code=404, detail="Stream not found")

        rows = connection.execute(
            """
            SELECT
              p.id,
              p.user_id,
              p.lat,
              p.lon,
              p.text,
              p.created_at,
              u.username
            FROM posts AS p
            JOIN users AS u ON u.id = p.user_id
            WHERE p.stream_id = ?
            ORDER BY p.id ASC
            """,
            (stream_id,),
        ).fetchall()

    filename = f'stream_{stream_id}.geojson'

    return JSONResponse(
        content={
            "type": "FeatureCollection",
            "features": [serialize_geojson_feature(row) for row in rows],
        },
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@app.post("/posts")
def create_post(payload: PostCreate, authuser: str = Depends(get_current_username)):
    created_at = datetime.now(timezone.utc).isoformat()
    geohash = encode_geohash(payload.lat, payload.lon, precision=6)

    with get_connection() as connection:
        require_user(connection, payload.user_id)
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
        if stream["user_id"] != payload.user_id:
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
                payload.user_id,
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
def list_posts(user_id: int, lat: float | None = None, lon: float | None = None, authuser: str = Depends(get_current_username)):
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
        LEFT JOIN subscriptions AS sub
          ON sub.stream_id = s.id
         AND sub.user_id = ?
    """
    parameters: list[int | str | float] = [user_id]
    filters = ["(s.user_id = ? OR sub.user_id IS NOT NULL)"]
    parameters.append(user_id)

    if lat is not None and lon is not None:
        center_geohash = encode_geohash(lat, lon, precision=6)
        target_geohashes = geohash_neighbors(center_geohash)
        placeholders = ", ".join("?" for _ in target_geohashes)
        filters.append(f"p.geohash IN ({placeholders})")
        parameters.extend(target_geohashes)

    query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY p.id DESC"

    with get_connection() as connection:
        require_user(connection, user_id)
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
            "id": row["id"],
            "user_id": row["user_id"],
            "text": row["text"],
            "created_at": row["created_at"],
            "username": row["username"],
        },
    }
