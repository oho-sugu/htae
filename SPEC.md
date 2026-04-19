# HTAE - Geo Stream SNS - Spec.md

## 1. Overview

This project is a simple GIS-based SNS application for sharing location-based posts.

### Goals

* Learn spatial data handling (lat/lon, GeoHash)
* Implement simple map visualization
* Export data in GeoJSON format
* Keep system simple and runnable locally

### Constraints

* Single instance (local PC)
* SQLite only for lightweight implementation and execution
* No real-time features
* No authentication complexity

---

## 2. Tech Stack

### Backend

* Python
* FastAPI
* SQLite
* uv
* No ORM

### Frontend

* HTML + Vanilla JS
* Leaflet

### Development environment

 * Windows PC and Mac OS and Linux
 * Easy setup and run localy

### Architecture

[ Browser ]
    ↓ HTTP
[ FastAPI ]
    ↓ Simple Raw SQL
[ SQLite ]

FastAPI own API and static file publication
Single page application

---

## 3. Data Model

## 3.1 Users

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL
);
```

---

## 3.2 Streams

```sql
CREATE TABLE streams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  color TEXT NOT NULL,
  emoji TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 3.3 Subscriptions

```sql
CREATE TABLE subscriptions (
  user_id INTEGER,
  stream_id INTEGER,
  PRIMARY KEY (user_id, stream_id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (stream_id) REFERENCES streams(id)
);
```

---

## 3.4 Posts

```sql
CREATE TABLE posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  stream_id INTEGER NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  geohash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  text TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (stream_id) REFERENCES streams(id)
);
```

---

## 3.5 Indexes

```sql
CREATE INDEX idx_posts_geohash ON posts(geohash);
CREATE INDEX idx_posts_stream ON posts(stream_id);
```

---

## 4. Constants

### Colors (fixed set)

```
#e74c3c
#3498db
#2ecc71
#f1c40f
#9b59b6
#e67e22
#1abc9c
#34495e
```

---

### Emojis (fixed set)

```
☕ 🍜 🌳 📍 ⭐ 🏠 🛒 📷 🎉
```

---

## 5. GeoHash Strategy

### Precision

* 6 characters (~1km)

### Storage

* Generated at post creation

### Query

* Center geohash + 8 neighbors

```sql
SELECT *
FROM posts
WHERE geohash IN (?, ?, ..., ?);
```

---

## 6. API Design

### 6.1 Auth

#### POST /login

Request:

```json
{
  "username": "user1",
  "password": "plain"
}
```

Response:

```json
{
  "user_id": 1
}
```

---

## 6.2 Streams

### GET /streams

Return all streams

---

### POST /streams

Request:

```json
{
  "name": "Cafe",
  "description": "Coffee spots",
  "color": "#e74c3c",
  "emoji": "☕"
}
```

---

### GET /streams/{id}

Return stream info

---

## 6.3 Subscriptions

### GET /subscriptions

Return subscribed stream IDs

---

### POST /subscriptions

```json
{
  "stream_id": 1
}
```

---

## 6.4 Posts

### POST /posts

```json
{
  "stream_id": 1,
  "lat": 35.68,
  "lon": 139.76,
  "text": "hello"
}
```

Behavior:

* Generate geohash
* Insert into DB

---

### GET /posts

Query:

```
lat=...
lon=...
```

Behavior:

* Compute geohash neighbors
* Return matching posts

Response:

```json
[
  {
    "id": 1,
    "lat": 35.68,
    "lon": 139.76,
    "text": "hello",
    "stream": {
      "id": 1,
      "name": "Cafe",
      "color": "#e74c3c",
      "emoji": "☕"
    }
  }
]
```

---

### GET /streams/{id}/posts

Return all posts for stream

---

## 6.5 GeoJSON Export

### GET /streams/{id}/export

Response:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [139.76, 35.68]
      },
      "properties": {
        "user_id": 1,
        "text": "hello",
        "timestamp": "..."
      }
    }
  ]
}
```

---

## 7. UI Design

### Layout

* Top-left: Filter button (☰)
* Top-right: Login Function, When user not login: login button, user logged in: user name and logout button
* Main: Map
* Bottom-right: Post button

---

## 7.1 Filter Panel (slide from left)

* Checkbox list of streams
* Grouped:

  * Owned streams
  * Subscribed streams
  * All other streams
* Default: Owned and Subscribed are checked
* Front-end side filter

---

## 7.2 Post Flow

1. Click "Post"
2. Show modal
3. Select stream
4. Text input
5. Submit

---

## 7.3 Map Rendering

* Use Leaflet
* Each post rendered as marker
* Style:

  * emoji + color setting in stream property

---

## 8. Filtering Logic

Client-side only:

```js
posts.filter(p => activeStreams.has(p.stream.id))
```

---

## 9. Validation Rules

### Stream

* color must be in predefined list
* emoji must be in predefined list

### Post

* lat: -90 to 90
* lon: -180 to 180

---

## 10. Non-Goals

* Real-time updates
* Friend system
* Ranking / popularity
* Clustering
* Post expiration
* Privacy masking

---

## 11. Development Steps (Recommended)

1. Basic FastAPI app
2. DB initialization
3. POST /posts
4. GET /posts (no geohash first)
5. Leaflet map display
6. Add geohash filtering
7. Add streams
8. Add UI filter
9. Add export

---

## 12. Notes

* Keep everything minimal
* Prefer clarity over optimization
* Do not over-engineer
