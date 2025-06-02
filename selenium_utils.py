# Selenium related helpers and XPath definitions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Centralised dictionary of XPaths used by the application
xpaths = {
    'search_bar': '//*[@id="search-input-wrap"]/input',
    'songs_parent': '//*[@id="page-wrapper"]/ion-router-outlet/app-page-search/ion-content/div/div/div/app-search/div',
    'song_title': './div/a/div/h5',
    'song_text3': './div/a/div/span/span',
    'song_text2': './div/a/div/span',
    'song_image': './div/div[1]/div/app-product-audio-preview-image/div/img',
    'click_song': '//*[@id="page-wrapper"]/ion-router-outlet/app-page-search/ion-content/div/div/div/app-search/div/app-product-list-item[{index}]/div/a/div',
    'chords_button': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[1]/button',
    'orchestration_header': "//h3[contains(text(), 'Orchestration')]/ancestor::div[4]",
    'key_button': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[3]/app-product-selector-key/div/button',
    'key_parent': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[3]/app-product-selector-key/div/ul',
    'parts_button': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[2]/div/button',
    'parts_parent': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[2]/div/ul',
    'parts_list': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content//ul/li/button',
    'image_element': '//*[@id="preview-sheets"]/div/div[1]/div/img',
    'next_button': "//button[contains(@class, 'sheet-nav-gradient-button-right')]",
}


class SeleniumHelper:
    """Utility methods for common Selenium operations."""

    @staticmethod
    def click_element(driver, xpath, timeout=2, log_func=None):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            element.click()
            return True
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error clicking element at xpath: {xpath} - {str(e)}")
            return False

    @staticmethod
    def find_element(driver, xpath, timeout=2, log_func=None):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return element
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error finding element at xpath: {xpath} - {str(e)}")
            return None

    @staticmethod
    def find_elements(driver, xpath, timeout=2, log_func=None):
        try:
            elements = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((By.XPATH, xpath))
            )
            return elements
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error finding elements at xpath: {xpath} - {str(e)}")
            return []

    @staticmethod
    def send_keys_to_element(driver, xpath, keys, timeout=2, log_func=None):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            element.clear()
            element.send_keys(keys)
            return True
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error sending keys to element at xpath: {xpath} - {str(e)}")
            return False

    @staticmethod
    def click_dynamic_element(driver, xpath_template, index, timeout=2, log_func=None):
        xpath = xpath_template.format(index=index)
        return SeleniumHelper.click_element(driver, xpath, timeout=timeout, log_func=log_func)
