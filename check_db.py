import sqlite3

conn = sqlite3.connect('memory/studio.db')
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:")
for table in tables:
    print(f"  - {table[0]}")

# Check scene_frames table
print("\nScene Frames:")
cursor.execute("SELECT id, season_num, episode_num, scene_num, frame_num, status, cv_score, image_url FROM scene_frames")
frames = cursor.fetchall()
for frame in frames:
    print(f"  Frame {frame[0]}: S{frame[1]}E{frame[2]} Scene {frame[3]} Frame {frame[4]} - {frame[5]} (CV: {frame[6]}) Image: {frame[7][:50] if frame[7] else 'None'}")

conn.close()
