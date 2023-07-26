import json
import os
import uuid
from datetime import timedelta
from typing import Literal, Optional
import requests

import structlog
from django.conf import settings
from prometheus_client import Counter, Summary
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.wait import WebDriverWait
from sentry_sdk import capture_exception, configure_scope, push_scope

from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.utils import ChromeType

from posthog.caching.fetch_from_cache import synchronously_update_cache
from posthog.logging.timing import timed
from posthog.metrics import LABEL_TEAM_ID
from posthog.models.exported_asset import ExportedAsset, get_public_access_token, save_content
from posthog.utils import absolute_uri

logger = structlog.get_logger(__name__)

IMAGE_EXPORT_SUCCEEDED_COUNTER = Counter(
    "image_exporter_task_succeeded",
    "An image export task succeeded",
    labelnames=[LABEL_TEAM_ID],
)

IMAGE_EXPORT_FAILED_COUNTER = Counter(
    "image_exporter_task_failure",
    "An image export task failed",
    labelnames=[LABEL_TEAM_ID],
)

IMAGE_EXPORT_TIMER = Summary(
    "image_exporter_task_success_time",
    "Number of seconds it took to export an image",
    labelnames=[LABEL_TEAM_ID],
)

TMP_DIR = "/tmp"  # NOTE: Externalise this to ENV var

ScreenWidth = Literal[800, 1920]
CSSSelector = Literal[".InsightCard", ".ExportedInsight"]


# NOTE: We purporsefully DONT re-use the driver. It would be slightly faster but would keep an in-memory browser
# window permanently around which is unnecessary
def get_driver() -> webdriver.Chrome:
    options = Options()
    options.headless = True
    options.add_argument("--force-device-scale-factor=2")  # Scale factor for higher res image
    options.add_argument("--use-gl=swiftshader")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")  # This flag can make things slower but more reliable

    if os.environ.get("CHROMEDRIVER_BIN"):
        return webdriver.Chrome(os.environ["CHROMEDRIVER_BIN"], options=options)

    return webdriver.Chrome(
        service=Service(ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install()),
        options=options,
    )


def _export_to_png(exported_asset: ExportedAsset) -> None:
    """
    Exporting an Insight means:
    1. Loading the Insight from the web app in a dedicated rendering mode
    2. Waiting for the page to have fully loaded before taking a screenshot to disk
    3. Loading that screenshot into memory and saving the data representation to the relevant Insight
    4. Cleanup: Remove the old file and close the browser session
    """

    image_path = None

    try:
        if not settings.SITE_URL:
            raise Exception(
                "The SITE_URL is not set. The exporter must have HTTP access to the web app in order to work"
            )

        image_id = str(uuid.uuid4())
        image_path = os.path.join(TMP_DIR, f"{image_id}.png")

        if not os.path.exists(TMP_DIR):
            os.makedirs(TMP_DIR)

        access_token = get_public_access_token(exported_asset, timedelta(minutes=15))

        screenshot_width: ScreenWidth
        wait_for_css_selector: CSSSelector

        if exported_asset.insight is not None:
            url_to_render = absolute_uri(f"/exporter?token={access_token}&legend")
            wait_for_css_selector = ".ExportedInsight"
            screenshot_width = 800
        elif exported_asset.dashboard is not None:
            url_to_render = absolute_uri(f"/exporter?token={access_token}")
            wait_for_css_selector = ".InsightCard"
            screenshot_width = 1920
        else:
            raise Exception(f"Export is missing required dashboard or insight ID")

        logger.info("exporting_asset", asset_id=exported_asset.id, render_url=url_to_render)

        _screenshot_asset(image_path, url_to_render, screenshot_width, wait_for_css_selector)

        with open(image_path, "rb") as image_file:
            image_data = image_file.read()

        save_content(exported_asset, image_data)

        os.remove(image_path)

    except Exception as err:
        # Ensure we clean up the tmp file in case anything went wrong
        if image_path and os.path.exists(image_path):
            os.remove(image_path)

        if settings.SITE_URL:
            log_error_if_url_not_reachable(settings.SITE_URL)

        raise err


def _screenshot_asset(
    image_path: str, url_to_render: str, screenshot_width: ScreenWidth, wait_for_css_selector: CSSSelector
) -> None:
    driver: Optional[webdriver.Chrome] = None
    try:
        driver = get_driver()
        driver.set_window_size(screenshot_width, screenshot_width * 0.5)
        driver.get(url_to_render)
        WebDriverWait(driver, 20).until(lambda x: x.find_element_by_css_selector(wait_for_css_selector))
        # Also wait until nothing is loading
        try:
            WebDriverWait(driver, 20).until_not(lambda x: x.find_element_by_class_name("Spinner"))
        except TimeoutException:
            capture_exception()
        height = driver.execute_script("return document.body.scrollHeight")
        driver.set_window_size(screenshot_width, height)
        driver.save_screenshot(image_path)
    except Exception as e:
        if driver:
            # To help with debugging, add a screenshot and any chrome logs
            with configure_scope() as scope:
                # If we encounter issues getting extra info we should silenty fail rather than creating a new exception
                try:
                    all_logs = [x for x in driver.get_log("browser")]
                    scope.add_attachment(json.dumps(all_logs).encode("utf-8"), "logs.txt")
                except Exception:
                    pass
                try:
                    driver.save_screenshot(image_path)
                    scope.add_attachment(None, None, image_path)
                except Exception:
                    pass
                capture_exception(e)

        raise e
    finally:
        if driver:
            driver.quit()


@timed("image_exporter")
def export_image(exported_asset: ExportedAsset) -> None:
    with push_scope() as scope:
        scope.set_tag("team_id", exported_asset.team if exported_asset else "unknown")
        scope.set_tag("asset_id", exported_asset.id if exported_asset else "unknown")

        try:
            if exported_asset.insight:
                # NOTE: Dashboards are regularly updated but insights are not
                # so, we need to trigger a manual update to ensure the results are good
                synchronously_update_cache(exported_asset.insight, exported_asset.dashboard)

            if exported_asset.export_format == "image/png":
                with IMAGE_EXPORT_TIMER.labels(team_id=exported_asset.team.id).time():
                    _export_to_png(exported_asset)
                IMAGE_EXPORT_SUCCEEDED_COUNTER.labels(team_id=exported_asset.team.id).inc()
            else:
                raise NotImplementedError(
                    f"Export to format {exported_asset.export_format} is not supported for insights"
                )
        except Exception as e:
            if exported_asset:
                team_id = str(exported_asset.team.id)
            else:
                team_id = "unknown"

            capture_exception(e)

            logger.error("image_exporter.failed", exception=e, exc_info=True)
            IMAGE_EXPORT_FAILED_COUNTER.labels(team_id=team_id).inc()
            raise e


def log_error_if_url_not_reachable(url: str) -> None:
    """
    Attempt to GET a URL and log an error if it's not reachable
    or if the HTTP status code indicates an error
    """

    try:
        if not url:
            raise Exception("No url provided to log_error_if_url_not_reachable")

        # try to request the url
        response = requests.get(url, timeout=5)

        # if the status code is an error, log it
        if response.status_code >= 400:
            logger.error("get_url_error_status", url=url, status_code=response.status_code)
    except Exception as e:
        logger.error("get_url_exception", exception=e, url=url)
