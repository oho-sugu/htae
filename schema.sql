CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS streams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  color TEXT NOT NULL,
  emoji TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
  user_id INTEGER,
  stream_id INTEGER,
  PRIMARY KEY (user_id, stream_id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (stream_id) REFERENCES streams(id)
);

CREATE TABLE IF NOT EXISTS posts (
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

CREATE INDEX IF NOT EXISTS idx_posts_geohash ON posts(geohash);
CREATE INDEX IF NOT EXISTS idx_posts_stream ON posts(stream_id);
