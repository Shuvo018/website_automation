import os
import time
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

def authenticate_gmail(max_retries=3):
    for attempt in range(max_retries):
        try:
            creds = None
            if os.path.exists("token.json"):
                try:
                    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
                except Exception as e:
                    logging.error(f"Error loading credentials from token.json: {e}")
                    if os.path.exists("token.json"):
                        os.remove("token.json")
                    creds = None
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        logging.error(f"Error refreshing token: {e}")
                        creds = None
                if not creds or not creds.valid:
                    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                    creds = flow.run_local_server(port=8080)

                try:
                    with open("token.json", "w") as token:
                        token.write(creds.to_json())
                except Exception as e:
                    logging.error(f"Error saving token: {e}")

            service = build("gmail", "v1", credentials=creds)
            service.users().getProfile(userId='me').execute()
            return service

        except HttpError as e:
            logging.error(f"Google API error during authentication (attempt {attempt+1}/{max_retries}): {e}")
            if 'invalid_grant' in str(e) or 'Invalid Credentials' in str(e) or '401' in str(e):
                logging.warning("Token appears to be invalid. Removing token.json and trying again...")
                if os.path.exists("token.json"):
                    os.remove("token.json")
                time.sleep(1)
            elif attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached for authentication.")
                raise
        except Exception as e:
            logging.error(f"Unexpected error during authentication (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached for authentication.")
                raise

    raise Exception("Failed to authenticate with Gmail API after multiple attempts")

if __name__ == "__main__":
    try:
        service = authenticate_gmail()
        print("Gmail API authentication successful!")
    except Exception as e:
        print(f"Authentication failed: {e}")