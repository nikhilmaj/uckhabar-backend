import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

from services.db_service import DatabaseService
from config import settings
import firebase_admin
from firebase_admin import credentials, auth

async def main():
    if len(sys.argv) < 2:
        print("Usage: python delete_user.py <uid>")
        sys.exit(1)
        
    uid = sys.argv[1]
    
    # Initialize Firebase Admin if not already initialized
    if not firebase_admin._apps:
        # Assuming the backend's default initialization works for the script
        # Alternatively, using credentials from GOOGLE_APPLICATION_CREDENTIALS
        try:
            firebase_admin.initialize_app(options={'projectId': settings.GCP_PROJECT_ID})
        except Exception as e:
            # If default fails, maybe try with explicit credential if available
            try:
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred, {'projectId': settings.GCP_PROJECT_ID})
            except Exception as e2:
                print(f"Failed to initialize Firebase Admin SDK: {e2}")
                sys.exit(1)

    db = DatabaseService(project_id=settings.GCP_PROJECT_ID)
    
    print(f"Deleting user {uid}...")
    
    try:
        await db.delete_user_profile(uid)
        print("✅ Deleted user profile from Firestore.")
    except Exception as e:
        print(f"⚠️ Failed to delete user profile: {e}")
        
    try:
        await db.delete_user_feed(uid)
        print("✅ Deleted user feed from Firestore.")
    except Exception as e:
        print(f"⚠️ Failed to delete user feed: {e}")
        
    try:
        auth.delete_user(uid)
        print("✅ Deleted user from Firebase Auth.")
    except Exception as e:
        print(f"⚠️ Failed to delete user from Firebase Auth: {e}")

    print("Cleanup complete.")

if __name__ == "__main__":
    asyncio.run(main())
