import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import logging
from shared import shared_state, read_credentials, start_task_event

logging.basicConfig(level=logging.INFO, format="%(message)s")

credentials = read_credentials()
EMAIL = credentials.get("EMAIL")
PASSWORD = credentials.get("PASSWORD")

LOGIN_URL = "https://earn.ratetomake.com/login"
TARGET_URL = "https://earn.ratetomake.com/my-tasks"
NO_CONDITION_LIMIT = 2

redeem_clicked = False

async def try_click(page, selector, timeout=2000):
    try:
        await page.locator(selector).click(timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception as e:
        logging.error(f"Error clicking {selector}: {e}")
        return False

async def try_locator(page, selector, timeout=2000):
    try:
        await page.locator(selector).wait_for(state="visible", timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception as e:
        logging.error(f"Error locating {selector}: {e}")
        return False
async def show_points_in_terminal(page):
    try:
        locator = page.locator("div.text-center.text-blue.mb-1.font-medium")
        if await locator.is_visible(timeout=5000):
            points_text = await locator.inner_text()
            current_point_str = points_text.strip().split("/")[0].strip()
            current_point = int(current_point_str.replace(",", ""))  # Remove commas

            if shared_state.last_point_value is None:
                shared_state.last_point_value = current_point
            logging.info(f"P: {points_text} || inc: {current_point - shared_state.last_point_value} || {EMAIL}")
        else:
                logging.warning("Points not visible.")
    except Exception as e:
        logging.warning(f"Error showing points: {e}")

async def login(page):
    logging.info("Attempting login...")
    await page.goto(LOGIN_URL)
    await page.fill('input[name="email"]', EMAIL)
    await page.fill('input[name="password"]', PASSWORD)
    await page.locator(".jelly").click()
    await page.wait_for_url(TARGET_URL, timeout=15000)
    logging.info("Logged in successfully!")

async def run():
    last_flag_state = None

    def update_flag(new_state: bool):
        nonlocal last_flag_state
        if shared_state.flag != new_state:
            shared_state.flag = new_state
            start_task_event.set()
            last_flag_state = new_state
    
    global redeem_clicked
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--window-size=400,350",
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
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()

        page.on("load", lambda: asyncio.create_task(show_points_in_terminal(page)))

        await page.goto(LOGIN_URL)

        await show_points_in_terminal(page)

        async def handle_logout(page):
            try:
                logging.warning("Detected logout. Re-logging in...")
                await login(page)
                await reapply_page_settings(page)
            except Exception as e:
                while page.url != TARGET_URL:
                    try:
                        await login(page)
                        await reapply_page_settings(page)
                        await asyncio.sleep(10)
                    except Exception as retry_error:
                        logging.error(f"Retry failed: {retry_error}")

        async def reapply_page_settings(page):
            await show_points_in_terminal(page)

        try:
            await login(page)
        except Exception:
            await handle_logout(page)

        no_condition_counter = 0
        while True:
            if page.url != TARGET_URL:
                await handle_logout(page)
                continue

            action_taken = False
            update = False
            await reapply_page_settings(page)
            # start task button
            if await try_locator(page, "//a[span[contains(text(), 'Start Task')]]", timeout=1000):
                logging.info("'Start Task' button appeared. Clicking it immediately.")
                await try_click(page, "//a[span[contains(text(), 'Start Task')]]")
                
                action_taken = True
                update_flag(True)
                update = True

                await asyncio.sleep(2)

                for _ in range(27):
                    if await try_click(page, "//button[contains(@class, 'notice-button') and contains(text(), 'View Progress')]"):
                        logging.info("Clicked 'View Progress' during wait.")
                        action_taken = True
                        break
                    else:
                        await asyncio.sleep(3)
                # Skip button handling
                if await try_click(page, "//button[contains(@class, 'text-blue') and text()='skip']"):
                    logging.info("Clicked 'Skip' button wait.")
                    action_taken = True
                continue
            # 2.5. Continue Task link
            continue_task_selector = "//a[@href='/complete-task' and span[text()='Continue Task']]"
            if await try_click(page, continue_task_selector):
                logging.info("Clicked 'Continue Task'")
                action_taken = True
                continue

            if await try_click(page, "//button[contains(@class, 'notice-button') and contains(text(), 'View Progress')]"):
                logging.info("Clicked 'View Progress'")
                action_taken = True
                continue
            # 2. Keep Going button
            if await try_click(page, "//button[contains(@class, 'notice-button') and text()='Keep Going']"):
                logging.info("Clicked 'Keep Going'")
                action_taken = True
                continue

            # "I will check my email" button
            if await try_click(page, "//button[contains(@class, 'notice-button') and text()='I will check my email']"):
                logging.info("Clicked 'I will check my email'")
                action_taken = True
                continue

            # 5  Redeem Reward button (click only once)
            if not redeem_clicked:
                button_25000 = page.locator("//button[.//span[text()='Redeem Reward (25,000 Points)']]")
                if await button_25000.is_visible():
                    logging.info("Clicking Redeem Reward (25,000 Points)")
                    await button_25000.click()

                    redeem_clicked = True
                    action_taken = True

                    update_flag(True)
                    update = True
                if not redeem_clicked:
                    button_50000 = page.locator("//button[.//span[text()='Redeem Reward (50,000 Points)']]")
                    if await button_50000.is_visible():
                        logging.info("Clicking Redeem Reward (50,000 Points)")
                        await button_50000.click()

                        redeem_clicked = True
                        action_taken = True
                        update_flag(True)
                        update = True
            # 2.7. "I will check my email" button
            if await try_click(page, "//button[contains(@class, 'notice-button') and text()='I will check my email']"):
                logging.info("Clicked 'I will check my email'")
                action_taken = True
                continue

            if not action_taken:
                logging.info("Fast rechecking...")
                no_condition_counter += 1
                await asyncio.sleep(5)
                if no_condition_counter >= NO_CONDITION_LIMIT:
                    logging.warning("Refreshing page...")
                    await page.reload()
                    no_condition_counter = 0
            if not update:
                update_flag(False)
if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.info("Script manually stopped by user.")
