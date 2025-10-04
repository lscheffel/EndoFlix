from db import Database

db = Database()
try:
    # Check counts
    videos = db.execute_query("SELECT COUNT(*) FROM endoflix_files")
    print("Videos count:", videos)

    playlists = db.execute_query("SELECT COUNT(*) FROM endoflix_playlist")
    print("Playlists count:", playlists)

    sessions = db.execute_query("SELECT COUNT(*) FROM endoflix_session")
    print("Sessions count:", sessions)

except Exception as e:
    print(f"Error: {e}")