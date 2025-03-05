import time
import re
import os
import traceback
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
import urllib.parse
from selenium.webdriver.chrome.options import Options
import csv
from ip_rotator import IPRotator

class AlienwareClaimer:
    def __init__(self, url, signals, ip_rotator=IPRotator):
        self.original_url = url
        self.signals = signals
        self.ip_rotator = ip_rotator
        self.MAX_RETRY = 4  # Increased retry attempts
        self.TIMEOUT = 60   # Increased timeout
        self.offer_name = self.extract_offer_name(url)
        self.claimed_keys = []  # Track claimed keys
        self.claimed_emails = self._load_claimed_emails()

    def _load_claimed_emails(self):
        # Load previously claimed emails for this offer
        sanitized_filename = "".join(x for x in self.offer_name if x.isalnum() or x in [' ', '-']).rstrip()
        log_filename = f"{sanitized_filename}_claimed_keys.txt"
        
        claimed_emails = set()
        if os.path.exists(log_filename):
            with open(log_filename, 'r') as file:
                for line in file:
                    email_match = re.search(r'Email: (.+?) \|', line)
                    if email_match:
                        claimed_emails.add(email_match.group(1).strip())
        
        return claimed_emails

    def extract_offer_name(self, url):
        parts = url.split('Giveaway/')
        return parts[1].replace('-', ' ').title() if len(parts) > 1 else "Unknown Offer"

    def get_chrome_options(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")
        
        # Performance and bypass detection optimizations
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        return chrome_options

    def generate_login_link(self):
        parsed_url = urllib.parse.urlparse(self.original_url)
        return_path = parsed_url.path
        login_base = parsed_url.scheme + "://" + parsed_url.netloc + "/login"
        encoded_return = urllib.parse.quote(return_path)
        return f"{login_base}?return={encoded_return}"

    def perform_login(self, driver, email, password):
        for attempt in range(self.MAX_RETRY):
            try:
                # Check if email was already used
                if email in self.claimed_emails:
                    self.signals.log_signal.emit(f"⏩ Skipping {email} - already claimed key for this offer")
                    return False

                # Locate login fields with multiple strategies
                login_strategies = [
                    lambda: driver.find_element(By.ID, "_username"),
                    lambda: driver.find_element(By.NAME, "username"),
                    lambda: driver.find_element(By.CSS_SELECTOR, "input[type='email']")
                ]

                password_strategies = [
                    lambda: driver.find_element(By.ID, "_password"),
                    lambda: driver.find_element(By.NAME, "password"),
                    lambda: driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                ]

                login_button_strategies = [
                    lambda: driver.find_element(By.ID, "_login"),
                    lambda: driver.find_element(By.XPATH, "//button[contains(text(), 'Login')]"),
                    lambda: driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                ]

                # Try different element location strategies
                email_input = None
                for strategy in login_strategies:
                    try:
                        email_input = strategy()
                        break
                    except Exception:
                        continue

                if not email_input:
                    self.signals.log_signal.emit(f"❌ Could not find email input (Attempt {attempt + 1})")
                    continue

                email_input.clear()
                email_input.send_keys(email)

                # Find password input
                password_input = None
                for strategy in password_strategies:
                    try:
                        password_input = strategy()
                        break
                    except Exception:
                        continue

                if not password_input:
                    self.signals.log_signal.emit(f"❌ Could not find password input (Attempt {attempt + 1})")
                    continue

                password_input.clear()
                password_input.send_keys(password)

                # Find login button
                login_btn = None
                for strategy in login_button_strategies:
                    try:
                        login_btn = strategy()
                        login_btn.click()
                        break
                    except Exception:
                        continue

                if not login_btn:
                    self.signals.log_signal.emit(f"❌ Could not find login button (Attempt {attempt + 1})")
                    continue

                # Wait and verify login
                time.sleep(3)
                current_url = driver.current_url
                target_url = self.original_url

                current_path = urllib.parse.urlparse(current_url).path
                target_path = urllib.parse.urlparse(target_url).path

                if current_path == target_path or self.original_url in current_url:
                    self.signals.log_signal.emit(f"✅ Successfully logged in (Attempt {attempt + 1})")
                    return True

                self.signals.log_signal.emit(f"❌ Login failed. Current URL: {current_url} (Attempt {attempt + 1})")
                
            except Exception as e:
                self.signals.log_signal.emit(f"❗ Login error: {str(e)} (Attempt {attempt + 1})")
            
            time.sleep(2)  # Wait between attempts

        return False

    def claim_key(self, email, password, *args, **kwargs):
        """
        Claim key method with flexible arguments to handle potential additional parameters
        
        :param email: User email
        :param password: User password
        :param args: Additional positional arguments
        :param kwargs: Additional keyword arguments
        :return: Claimed key or None
        """
        driver = None
        retry_count = 0
        try:
            # Skip if email was already used
            if email in self.claimed_emails:
                self.signals.log_signal.emit(f"⏩ Skipping {email} - already claimed key for this offer")
                return None

            login_link = self.generate_login_link()
            
            chrome_options = self.get_chrome_options()
            driver = uc.Chrome(options=chrome_options)
            driver.get(login_link)

            if not self.perform_login(driver, email, password):
                self.signals.log_signal.emit("❌ Login failed after multiple attempts")
                return None

            driver.get(self.original_url)
            time.sleep(2)

            for attempt in range(self.MAX_RETRY):
                self.signals.log_signal.emit(f"🔍 Attempting to claim key (Attempt {attempt + 1})")
                
                # Check for existing key first
                existing_key = self.extract_existing_key(driver)
                if existing_key:
                    self.save_key_and_email(email, existing_key)
                    return existing_key

                # Advanced key claiming strategies
                key_claiming_strategies = [
                    self._strategy_direct_get_key,
                    self._strategy_click_get_key,
                    self._strategy_javascript_get_key
                ]

                key = None
                for strategy in key_claiming_strategies:
                    try:
                        key = strategy(driver)
                        if key:
                            break
                    except Exception as e:
                        self.signals.log_signal.emit(f"❗ Strategy failed: {str(e)}")

                if key:
                    self.save_key_and_email(email, key)
                    return key

                # If key not found, check availability or rotate IP
                if self.is_key_unavailable(driver):
                    self.signals.log_signal.emit("🔄 Key unavailable. Attempting mitigation...")
                    
                    # Increment retry count and check for IP rotation
                    retry_count += 1
                    
                    # Rotate IP after 2 unsuccessful attempts
                    if retry_count >= 2:
                        # Multiple IP rotation strategies
                        if hasattr(self, 'ip_rotator') and self.ip_rotator:
                            self.signals.log_signal.emit(f"🌐 Rotating IP (Attempt {retry_count})")
                            self.ip_rotator.rotate_ip(self)
                            
                            # Reset retry count after IP rotation
                            retry_count = 0
                        else:
                            self.signals.log_signal.emit("❌ No IP rotator configured")
                    
                    # Additional mitigation techniques
                    driver.refresh()
                    time.sleep(3)
                    driver.execute_script("window.localStorage.clear();")
                    driver.execute_script("window.sessionStorage.clear();")
                    
                    continue

                # Wait before next attempt
                time.sleep(3)

            self.signals.log_signal.emit("❌ Could not claim key after multiple attempts")
            return None

        except Exception as e:
            self.signals.log_signal.emit(f"❗ Key claiming error: {traceback.format_exc()}")
            return None
        finally:
            if driver:
                driver.quit()

    def _strategy_direct_get_key(self, driver):
        """Direct method to find and click 'Get Key' button"""
        get_key_strategies = [
            lambda: driver.find_element(By.ID, "giveaway-get-key"),
            lambda: driver.find_element(By.XPATH, "//button[contains(text(), 'Get Key')]"),
            lambda: driver.find_element(By.CSS_SELECTOR, "button.get-key-btn")
        ]

        for strategy in get_key_strategies:
            try:
                get_key_button = strategy()
                get_key_button.click()
                time.sleep(2)
                
                # Try to extract key immediately after clicking
                key = self.extract_key_from_page(driver)
                if key:
                    return key
            except Exception:
                continue
        return None

    def _strategy_click_get_key(self, driver):
        """Alternative click method with wait"""
        try:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Get Key')]"))
            ).click()
            time.sleep(3)
            return self.extract_key_from_page(driver)
        except Exception:
            return None

    def _strategy_javascript_get_key(self, driver):
        """JavaScript method to trigger key retrieval"""
        try:
            driver.execute_script("""
                let buttons = document.querySelectorAll('button');
                for (let btn of buttons) {
                    if (btn.textContent.includes('Get Key')) {
                        btn.click();
                        break;
                    }
                }
            """)
            time.sleep(3)
            return self.extract_key_from_page(driver)
        except Exception:
            return None

    def is_key_unavailable(self, driver):
        unavailable_phrases = [
            "Unfortunately, a key could not be assigned to you",
            "No keys available",
            "Key already issued",
            "Already claimed",
            "key unavailable",
            "requesting"
        ]
        
        try:
            page_source = driver.page_source.lower()
            
            for phrase in unavailable_phrases:
                if phrase.lower() in page_source:
                    return True
            
            # Check for specific elements or classes that might indicate unavailability
            try:
                driver.find_element(By.CSS_SELECTOR, ".key-unavailable")
                return True
            except:
                pass
        except Exception as e:
            self.signals.log_signal.emit(f"❗ Availability check error: {str(e)}")
        
        return False

    def extract_existing_key(self, driver):
        """Extract already claimed key if present"""
        key_extraction_script = """
        const keyElements = document.querySelectorAll('p, div, span');
        for (let el of keyElements) {
            const keyMatch = el.textContent.match(/Key:\\s*([A-Z0-9\\-]+)/);
            if (keyMatch) return keyMatch[1];
        }
        return null;
        """
        key = driver.execute_script(key_extraction_script)
        
        if not key:
            page_source = driver.page_source
            key_match = re.search(r'Key:\s*([A-Z0-9\-]+)', page_source)
            key = key_match.group(1) if key_match else None

        return key

    def extract_key_from_page(self, driver):
        """Multiple methods to extract key from page"""
        key_extraction_methods = [
            # JavaScript extraction in notification container
            lambda: driver.execute_script("""
                const notifyContainer = document.querySelector('div[data-notify="container"]');
                if (notifyContainer) {
                    const keyElement = notifyContainer.querySelector('[data-notify="message"] p');
                    if (keyElement && keyElement.textContent.includes('Key:')) {
                        const keyMatch = keyElement.textContent.match(/Key:\\s*([A-Z0-9\\-]+)/);
                        return keyMatch ? keyMatch[1] : null;
                    }
                }
                return null;
            """),
            
            # Regular expression on page source
            lambda: self._regex_key_extraction(driver.page_source),
            
            # Alternative JavaScript extraction
            lambda: driver.execute_script("""
                const elements = document.querySelectorAll('*');
                for (let el of elements) {
                    if (el.textContent.includes('Key:')) {
                        const keyMatch = el.textContent.match(/Key:\\s*([A-Z0-9\\-]+)/);
                        if (keyMatch) return keyMatch[1];
                    }
                }
                return null;
            """)
        ]

        for method in key_extraction_methods:
            try:
                key = method()
                if key:
                    return key
            except Exception:
                continue

        return None

    def _regex_key_extraction(self, page_source):
        """Specialized regex key extraction"""
        key_patterns = [
            r'Key:\s*([A-Z0-9\-]+)',
            r'Game Key:\s*([A-Z0-9\-]+)',
            r'Serial:\s*([A-Z0-9\-]+)'
        ]
        
        for pattern in key_patterns:
            key_match = re.search(pattern, page_source)
            if key_match:
                return key_match.group(1)
        
        return None

    def save_key_and_email(self, email, key):
        """Save claimed key details to file"""
        # Sanitize filename
        sanitized_filename = "".join(x for x in self.offer_name if x.isalnum() or x in [' ', '-']).rstrip()
        log_filename = f"{sanitized_filename}_claimed_keys.txt"
        
        # Track claimed keys
        claimed_key_info = {"email": email, "key": key, "offer": self.offer_name}
        self.claimed_keys.append(claimed_key_info)
        
        # Add email to claimed emails set
        self.claimed_emails.add(email)

        # Save to file
        with open(log_filename, "a") as file:
            file.write(f"Email: {email} | Key: {key} | Offer: {self.offer_name}\n")
        
        # Emit signal with key information
        self.signals.log_signal.emit(f"💾 Saved key for {self.offer_name}")
        self.signals.key_found_signal.emit((email, key))

    def export_all_keys(self, filename=None):
        if not self.claimed_keys:
            return None

        if not filename:
            # Create a default filename based on the offer
            sanitized_filename = "".join(x for x in self.offer_name if x.isalnum() or x in [' ', '-']).rstrip()
            filename = f"{sanitized_filename}_all_keys.csv"

        try:
            import csv
            with open(filename, 'w', newline='') as csvfile:
                fieldnames = ['Email', 'Key', 'Offer']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for key_info in self.claimed_keys:
                    writer.writerow({
                        'Email': key_info['email'], 
                        'Key': key_info['key'], 
                        'Offer': key_info['offer']
                    })
            
            return filename
        except Exception as e:
            self.signals.log_signal.emit(f"❌ Failed to export keys: {str(e)}")
            return None