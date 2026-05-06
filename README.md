# HTAE

!!!!!!!!!!!!!  CAUTION  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
THIS IS JUST MINIMUM SAMPLE APPLICATION FOR EDUCATION
NOT FOR PRODUCTION/COMMERCIAL-USE BECAUSE OF POOR SECURITY AND POOR DATA HANDLING
NO WARRANTY AND NO SUPPORT
DO NOT USE FOR SERIOUS PURPOSE


HTAE is a small location-based SNS app built with FastAPI, SQLite, and a single-page HTML frontend. 
Users can create accounts, log in, create streams, subscribe to streams, post location-tagged messages, and export stream posts as GeoJSON.

## Stack

- Python 3.12+
- FastAPI
- Uvicorn
- SQLite
- Leaflet

## Features

- Local account creation and login
- Login state stored in `localStorage`
- Owned streams and stream subscriptions
- Location-based posts with geohash indexing
- Browser geolocation for initial map centering and posting
- GeoJSON export with download headers for GIS tools

## Project Files

- [main.py](/home/oho_s/repo/htae/main.py): FastAPI app and API routes
- [db.py](/home/oho_s/repo/htae/db.py): database setup, seed data, geohash helpers
- [schema.sql](/home/oho_s/repo/htae/schema.sql): SQLite schema
- [index.html](/home/oho_s/repo/htae/index.html): frontend UI and client-side logic
- [SPEC.md](/home/oho_s/repo/htae/SPEC.md): project spec

## Setup

Install dependencies:

```bash
uv sync
```

## Run

Start the app locally:

```bash
uv run uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

The app initializes `app.db` automatically on startup.

## Seed Data

The app seeds a small demo dataset on startup:

- `demo` / `demo`
- `alice` / `demo`

These accounts are stored with SHA-256 password hashes in the database.

## How It Works

### Authentication

- `POST /users` creates an account
- `POST /login` logs in
- The frontend stores `user_id` and `username` in `localStorage`
- Logout clears local state and returns the user to the login screen

### Streams

- Users can create their own streams
- New streams are automatically subscribed by their owner
- The stream panel shows owned streams and other streams
- Streams can be exported as `.geojson`

### Posts

- Posts belong to a user and a stream
- Users can only post to streams they own
- Post creation uses the browser geolocation API
- Post listing is limited to streams the user owns or subscribes to

### Export

- `GET /streams/{stream_id}/export?user_id=...`
- Returns a GeoJSON `FeatureCollection`
- Adds `Content-Disposition` so browsers download the file
- Coordinates are exported as `[lon, lat]`

## API Summary

### Auth

- `POST /users`
- `POST /login`

### Streams

- `GET /streams?user_id=...`
- `POST /streams`
- `GET /streams/{stream_id}/export?user_id=...`

### Subscriptions

- `GET /subscriptions?user_id=...`
- `POST /subscriptions`

### Posts

- `GET /posts?user_id=...`
- `GET /posts?user_id=...&lat=...&lon=...`
- `POST /posts`

## Database

SQLite tables:

- `users`
- `streams`
- `subscriptions`
- `posts`

The schema lives in [schema.sql](/home/oho_s/repo/htae/schema.sql).

## Notes

- This app uses minimal local auth only. There is no JWT, OAuth, or server-side session management.
- The frontend depends on browser geolocation permissions for initial centering and post creation.
- If geolocation is denied, the map falls back to the default location and the app still loads normally.
