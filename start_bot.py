import threading
import asyncio
import logging
import os
import time
import sys
from gmail_bot import process_unread_emails, cleanup_resources
from auto import run as auto_run
from shared import shared_state, read_credentials, start_task_event

def set_terminal_size(columns=80, lines=20):
    os.system(f"mode con: cols={columns} lines={lines}")

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def auto_clear_terminal():
    while True:
        try:
            time.sleep(60)
            clear_terminal()
        except Exception as e:
            logging.error(f"Error in terminal clearing thread: {e}")
            time.sleep(60)

def run_gmail_bot_forever():
    consecutive_errors = 0
    while True:
        try:
            start_task_event.wait()
            if shared_state.flag:
                logging.info("Gmail Bot is running...")
                try:
                    process_unread_emails(start_event=shared_state.flag)
                    shared_state.flag = False
                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    logging.error(f"Error in Gmail Bot (error #{consecutive_errors}): {e}")
                    if consecutive_errors >= 3:
                        logging.warning("Multiple consecutive errors detected. Cleaning up resources...")
                        cleanup_resources()
                        consecutive_errors = 0
                        
                    error_delay = min(30, 5 * consecutive_errors)
                    logging.info(f"Waiting {error_delay}s before continuing...")
                    time.sleep(error_delay)
            start_task_event.clear()
        except Exception as e:
            logging.error(f"Critical error in Gmail Bot outer loop: {e}")
            time.sleep(10)

def run_auto_forever():
    logging.info("Starting Ratetomake Bot loop...")
    consecutive_errors = 0
    while True:
        try:
            asyncio.run(auto_run())
            consecutive_errors = 0
        except asyncio.CancelledError:
            logging.info("Auto Bot task was cancelled. Restarting...")
        except Exception as e:
            consecutive_errors += 1
            logging.error(f"Auto Bot error (error #{consecutive_errors}): {e}")
             
            error_delay = min(60, 5 * consecutive_errors)
            logging.info(f"Waiting {error_delay}s before restarting Auto Bot...")
            time.sleep(error_delay)


def startr2m():
    try:
        set_terminal_size(60, 15)
        credentials = read_credentials()
        EMAIL = credentials.get("EMAIL")
        
        # Set window title
        if os.name == 'nt':
            os.system(f"title {EMAIL}")
        else:
            print(f"\033]0;{EMAIL}\007")
        
        shared_state.flag = True
        start_task_event.set()
        
        # Create and start threads
        gmail_thread = threading.Thread(target=run_gmail_bot_forever, name="GmailBot", daemon=True)
        auto_thread = threading.Thread(target=run_auto_forever, name="AutoBot", daemon=True)
        clear_thread = threading.Thread(target=auto_clear_terminal, name="ClearTerminal", daemon=True)

        gmail_thread.start()
        auto_thread.start()
        clear_thread.start()

        gmail_thread.join()
        auto_thread.join()
        
    except KeyboardInterrupt:
        logging.info("Program terminated by user")
    except Exception as e:
        logging.critical(f"Critical error in main function: {e}")
def main():
        documents_folder = os.path.join(os.environ["USERPROFILE"], "Documents")
        file_path = os.path.join(documents_folder, "autopasskey.txt")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                key = f.read().strip()
            if key == "xyz@#8899":
                startr2m()

if __name__ == "__main__":
    main()