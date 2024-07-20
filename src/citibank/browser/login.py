import asyncio
import logging
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

from citibank.gmail import Gmail
from citibank.settings import settings

logger = logging.getLogger(__name__)


class CitiAuthHandler:
    user_agent = " ".join(
        [
            "Mozilla/5.0 (X11; Linux x86_64)",
            "AppleWebKit/537.36 (KHTML, like Gecko)",
            "Chrome/120.0.0.0 Safari/537.36",
        ]
    )

    def __init__(self, gmail_client: Gmail, download_directory: str):
        self.download_directory = download_directory
        self.gmail_client = gmail_client
        self.webdriver = self.create_driver()

    def create_driver(self) -> webdriver.Chrome:
        logger.info("Creating Chrome driver")
        options = Options()
        options.add_experimental_option("detach", True)
        options.add_argument(f"--user-agent={self.user_agent}")
        options.add_argument("--window-size=1366,768")
        options.add_argument("--headless=new")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # set download directory
        prefs = {"download.default_directory": self.download_directory}
        options.add_experimental_option("prefs", prefs)

        return webdriver.Chrome(options=options)

    async def get_otp(self) -> str:
        message = await self.gmail_client.wait_for_new_message()
        logger.info("Attempting to retrieve OTP")

        otp = self.gmail_client.extract_otp_from_message(message)

        if not otp:
            raise RuntimeError(f"OTP not found in email: {message.subject[:20]}")

        logger.info("OTP %s retrieved", "****" + otp[-2:])
        return otp

    def execute_auth_flow(self, driver: webdriver.Chrome, username: str, password: str):
        # apply stealth
        stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

        # login page
        logger.info("Opening login page")
        driver.get("https://www.citibank.com.sg/SGGCB/JSO/username/signon/flow.action")
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        logger.info("Clicking 'SIGN ON' button")

        # click on view statements link
        driver.find_element(By.ID, "link_lkSignOn").click()

        view_statements_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "View Electronic Statements"))
        )

        driver.execute_script("arguments[0].click();", view_statements_link)
        time.sleep(0.5)

        # Simultaneously trigger SMS and begin monitoring inbox for new messages
        loop = asyncio.get_event_loop()
        otp_task = loop.create_task(self.get_otp())

        # wait for SMS to be forwarded to email account
        # and then retrieve OTP from email body
        loop.run_until_complete(otp_task)
        otp = otp_task.result()

        sms_container = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "SMSTokenPin0"))
        )
        sms_container.send_keys(otp)

        # download button
        download_button = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//button[@onclick='javascript:goClicked();']")
            )
        )
        download_button.click()

        # proceed button
        proceed_button = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located(
                (By.XPATH, "//button[@onclick='javascript:okPdfWarning();']")
            )
        )
        proceed_button.click()

        return driver

    def login(self) -> webdriver.Chrome:
        try:
            return self.execute_auth_flow(
                driver=self.webdriver,
                username=settings.citibank_user_id,
                password=settings.citibank_password,
            )
        except Exception as err:
            logger.error("Error during login: %s", err)
            raise
