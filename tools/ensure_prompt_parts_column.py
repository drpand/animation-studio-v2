import sqlite3


def main():
    conn = sqlite3.connect("memory/studio.db")
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(scene_frames)")
    cols = [r[1] for r in cur.fetchall()]
    print("before_has_prompt_parts_json=", "prompt_parts_json" in cols)

    if "prompt_parts_json" not in cols:
        cur.execute("ALTER TABLE scene_frames ADD COLUMN prompt_parts_json TEXT DEFAULT ''")
        conn.commit()
        print("added prompt_parts_json")

    cur.execute("PRAGMA table_info(scene_frames)")
    cols = [r[1] for r in cur.fetchall()]
    print("after_has_prompt_parts_json=", "prompt_parts_json" in cols)

    conn.close()


if __name__ == "__main__":
    main()
