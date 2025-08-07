import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# Only create client if we have valid credentials
if url and key:
    supabase: Client = create_client(url, key)
else:
    supabase = None
    print(f"WARNING: Supabase credentials not found. URL: {url}, Key: {'***' if key else 'None'}")
