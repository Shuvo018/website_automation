import base64
import re
import time
import logging
import datetime
from playwright.sync_api import sync_playwright
from gmail_auth import authenticate_gmail
from googleapiclient.errors import HttpError
from shared import read_credentials

service = None
browser = None
context = None
playwright = None
initialized = False

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

TARGET_LINK = "https://myfamilytree.io/articles/52?sub1=_LB&sub2=r2mLB"
AVOID_LINK = "https://support.google.com/mail/answer/1311182?hl=en"
MAX_RETRIES = 1
RETRY_DELAY = 2
EMAIL_CHECK_INTERVAL = 10

TREMENDOUS_PATTERN = r'https://www\.tremendous\.com/rewards/[^\s"\'<>]+'

def initialize():
    global service, browser, context, playwright, initialized
    if initialized:
        return

    logging.info("Initializing Gmail bot...")
    try:
        service = authenticate_gmail(max_retries=3)
        
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--disable-translate",
                "--hide-scrollbars",
                "--mute-audio"
            ])
        context = browser.new_context()
        blank_page = context.new_page()
        blank_page.goto("about:blank")

        mark_all_unread_as_read(service, label='INBOX')
        mark_all_unread_as_read(service, label='SPAM')

        initialized = True
    except Exception as e:
        logging.error(f"Failed to initialize Gmail bot: {e}")
        cleanup_resources()
        raise

def cleanup_resources():
    global browser, context, playwright, initialized
    try:
        if context:
            context.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")
    finally:
        initialized = False
        logging.info("Resources cleaned up")

def reinitialize_service():
    global service
    try:
        logging.info("Reinitializing Gmail service...")
        service = authenticate_gmail(max_retries=3)
        logging.info("Gmail service reinitialized successfully")
        return True
    except Exception as e:
        logging.error(f"Failed to reinitialize Gmail service: {e}")
        return False

def get_unread_emails(service, label='INBOX', max_retries=3):
    for attempt in range(max_retries):
        try:
            results = service.users().messages().list(
                userId='me',
                labelIds=[label],
                q='is:unread'
            ).execute()
            return results.get('messages', [])
        except HttpError as e:
            logging.error(f"Gmail API error: {e}")
            if '401' in str(e) or 'invalid_grant' in str(e) or 'Invalid Credentials' in str(e):
                logging.warning("Token appears to be expired or invalid. Attempting to refresh...")
                if reinitialize_service():
                    continue
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached. Returning an empty list.")
                return []
        except ConnectionResetError as e:
            logging.error(f"Connection reset error: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached. Returning an empty list.")
                return []
        except Exception as e:
            logging.error(f"Unexpected error in get_unread_emails: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached. Returning an empty list.")
                return []

def decode_email_body(data):
    try:
        padding = len(data) % 4
        if padding:
            data += '=' * (4 - padding)
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    except Exception as e:
        logging.error(f"Error decoding email body: {e}")
        return ""

def save_tremendous_link(link, span_text=""):
    try:
        Email = read_credentials().get("EMAIL")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open("../Redeem.txt", "a") as f:
                f.write(f"{current_time} - {link} - {span_text} - {Email}\n")
        except FileNotFoundError:
            with open("../Redeem.txt", "w") as f:
                f.write(f"{current_time} - {link} - {span_text} - {Email}\n")
                
        logging.info(f"Saved Tremendous link to Redeem.txt: {link} - {span_text}")
        return True
    except Exception as e:
        logging.error(f"Error saving Tremendous link: {e}")
        return False

def check_and_save_tremendous_links(html_content):
    found_links = []
    
    try:
        tremendous_links = re.findall(TREMENDOUS_PATTERN, html_content)
        
        for link in tremendous_links:
            span_text = ""
            
            a_tag_pattern = f'<a [^>]*?href="({re.escape(link)})".*?>(.*?)</a>'
            a_tag_match = re.search(a_tag_pattern, html_content, re.DOTALL)
            
            if a_tag_match:
                a_tag_content = a_tag_match.group(2)
                
                span_pattern = r'<span[^>]*?>(.*?)</span>'
                span_match = re.search(span_pattern, a_tag_content, re.DOTALL)
                
                if span_match:
                    span_text = span_match.group(1).strip()
                    span_text = re.sub(r'<[^>]+>', '', span_text)
                else:
                    span_text = re.sub(r'<[^>]+>', '', a_tag_content).strip()
            
            if not span_text:
                span_text = extract_text_around_link(html_content, link, chars=50)
            
            save_tremendous_link(link, span_text)
            found_links.append(link)
            
        return found_links
    except Exception as e:
        logging.error(f"Error in check_and_save_tremendous_links: {e}")
        tremendous_links = re.findall(TREMENDOUS_PATTERN, html_content)
        for link in tremendous_links:
            logging.info(f"Found Tremendous reward link (fallback): {link}")
            save_tremendous_link(link, "")
            found_links.append(link)
        return found_links

def extract_text_around_link(html_content, link, chars=100):
    try:
        link_pos = html_content.find(link)
        if link_pos == -1:
            return ""
        
        start_pos = max(0, link_pos - chars)
        end_pos = min(len(html_content), link_pos + len(link) + chars)
        
        text_segment = html_content[start_pos:end_pos]
        
        text_segment = re.sub(r'<[^>]+>', ' ', text_segment)
        
        text_segment = re.sub(r'\s+', ' ', text_segment).strip()
        
        return text_segment
    except Exception as e:
        logging.error(f"Error extracting text around link: {e}")
        return ""

def extract_link_from_email(service, message_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
            payload = msg.get("payload", {})
            parts = payload.get("parts", [])
            data = None

            for part in parts:
                if part.get("mimeType") == "text/html":
                    data = part["body"].get("data")
                    break

            if not data:
                data = payload.get("body", {}).get("data")

            if data:
                html = decode_email_body(data)
                
                tremendous_links = check_and_save_tremendous_links(html)
                
                if tremendous_links:
                    return None
                
                links = re.findall(r'href="(https?://[^"]+)"', html)
                return links[0] if links else None
            return None
        except HttpError as e:
            logging.error(f"Gmail API error in extract_link: {e}")
            if '401' in str(e) or 'invalid_grant' in str(e) or 'Invalid Credentials' in str(e):
                logging.warning("Token appears to be expired or invalid. Attempting to refresh...")
                if reinitialize_service():
                    continue
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached. Returning None.")
                return None
        except Exception as e:
            logging.error(f"Error extracting link: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return None

def mark_email_as_read(service, email_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            service.users().messages().modify(userId="me", id=email_id, body={"removeLabelIds": ["UNREAD"]}).execute()
            logging.info(f"Marked email {email_id} as read.")
            return True
        except HttpError as e:
            logging.error(f"Gmail API error in mark_email_as_read: {e}")
            if '401' in str(e) or 'invalid_grant' in str(e) or 'Invalid Credentials' in str(e):
                logging.warning("Token appears to be expired or invalid. Attempting to refresh...")
                if reinitialize_service():
                    continue
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached. Failed to mark email as read.")
                return False
        except Exception as e:
            logging.error(f"Error marking email as read: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return False

def open_link_in_multiple_tabs(context, link, num_tabs=3, close_delay=3):
    try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                pages_handle_error = []
                target_match = False
                for i in range(num_tabs):
                    try:
                        page = context.new_page()
                        pages_handle_error.append(page)
                        page.goto(link, timeout=20000)
                        logging.info(f" Opened tab {i+1}")
                        
                        time.sleep(1)
                        current_url = page.url
                        if current_url == TARGET_LINK:
                            target_match = True
                            break
                    except Exception as e:
                        logging.warning(f" Tab {i+1} failed: {str(e)[:100]}...")
                time.sleep(close_delay)
                for i, page in enumerate(pages_handle_error):
                    try:
                        page.close()
                        logging.info(f" Closed tab {i+1}")
                    except Exception as e:
                        logging.warning(f" Error closing tab: {str(e)[:100]}...")
                if target_match:
                    return True
            except Exception as e:
                logging.warning(f"Playwright error on attempt {attempt}: {str(e)[:100]}...")

        return False
    except Exception as e:
        logging.error(f"Unexpected error in open_link_in_multiple_tabs: {str(e)[:100]}...")
        return False

def mark_all_unread_as_read(service, label='INBOX', max_retries=3):
    for attempt in range(max_retries):
        try:
            messages = get_unread_emails(service, label)
            if messages:
                for msg in messages:
                    email_id = msg.get('id')
                    
                    try:
                        email_data = service.users().messages().get(userId='me', id=email_id, format='metadata').execute()
                        headers = email_data.get('payload', {}).get('headers', [])
                        sender = ""
                        for header in headers:
                            if header.get('name', '').lower() in ['from', 'sender']:
                                sender = header.get('value', '')
                                break
                        if "Rate2Make via Treme" in sender:
                            continue
                        mark_email_as_read(service, email_id)
                    except Exception as e:
                        logging.error(f"Error processing email {email_id}: {e}")
                
                logging.info(f"Processed all unread emails in {label}")
            else:
                logging.info(f"No unread emails to process in {label}.")
            return True
        except HttpError as e:
            logging.error(f"Gmail API error in mark_all_unread_as_read: {e}")
            if '401' in str(e) or 'invalid_grant' in str(e) or 'Invalid Credentials' in str(e):
                logging.warning("Token appears to be expired or invalid. Attempting to refresh...")
                if reinitialize_service():
                    continue
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached. Failed to mark all unread emails as read.")
                return False
        except Exception as e:
            logging.error(f"Error marking all unread emails as read in {label}: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return False
            
def process_unread_emails(start_event=False):
    global initialized, service
    
    if not start_event:
        return
    
    try:
        if not initialized:
            initialize()
        elif service is None:
            reinitialize_service()
        
        max_check_count = 12
        check_count = 0
        
        while check_count < max_check_count:
            check_count += 1

            logging.info("Checking for unread emails...")
            messages = get_unread_emails(service, label='INBOX') 
            if not messages:
                messages = get_unread_emails(service, label='SPAM')
            
            if not messages:
                if check_count < max_check_count:
                    logging.info(f"No unread emails. Waiting {EMAIL_CHECK_INTERVAL} seconds...")
                    time.sleep(EMAIL_CHECK_INTERVAL)
                    continue
                else:
                    logging.info("Reached maximum check count with no emails found.")
                    return

            for msg in messages:
                email_id = msg.get('id')
                link = extract_link_from_email(service, email_id)
                mark_email_as_read(service, email_id)
                if not link:
                    continue

                logging.info(f"Found Link: {link}")
                matched = open_link_in_multiple_tabs(context, link)
                if matched:
                    logging.info("Target matched!")
                    return
                else:
                    logging.warning("Target did not match")

    except Exception as e:
        logging.error(f"Error in process_unread_emails: {e}")
        cleanup_resources()
        return

def run_gmail_bot():
    try:
        process_unread_emails(True)
    except Exception as e:
        logging.error(f"Error running Gmail bot: {e}")
        cleanup_resources()

if __name__ == "__main__":
    run_gmail_bot()