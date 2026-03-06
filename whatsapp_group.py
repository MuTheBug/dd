"""
WhatsApp Group Creator using Playwright.
Automates creating a WhatsApp group and adding members by phone number.

Usage:
    python whatsapp_group.py --name "Group Name" --phones "+963123456789,+963987654321"

First run will ask you to scan the QR code. Session is saved for subsequent runs.
"""

import argparse
import os
import sys
import time

WA_SESSION_DIR = os.path.join(os.path.dirname(__file__), '.wa_session')


def create_whatsapp_group(group_name, phone_numbers, headless=False):
    """Create a WhatsApp group and add members."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    # Clean phone numbers
    phones = []
    for p in phone_numbers:
        p = p.strip().replace(' ', '').replace('-', '')
        if not p:
            continue
        if p.startswith('0'):
            p = '+963' + p[1:]
        if not p.startswith('+'):
            p = '+' + p
        phones.append(p)

    if not phones:
        print("No valid phone numbers provided.")
        return False

    print(f"Creating group '{group_name}' with {len(phones)} contacts...")

    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=WA_SESSION_DIR,
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ],
            locale='ar',
            viewport={'width': 1280, 'height': 900},
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        # Navigate to WhatsApp Web
        page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded')
        print("Waiting for WhatsApp Web to load...")
        print("If this is your first time, scan the QR code with your phone.")
        print("You have up to 3 minutes to scan...")

        # Wait for login
        logged_in = False
        for attempt in range(6):
            try:
                page.wait_for_selector(
                    '#side, [data-testid="chat-list"], [aria-label="Chat list"], '
                    '[aria-label="قائمة المحادثات"]',
                    timeout=30000
                )
                logged_in = True
                break
            except PwTimeout:
                print(f"  Still waiting for login... ({(attempt+1)*30}s)")
                continue

        if not logged_in:
            print("Timeout waiting for WhatsApp login. Please try again.")
            browser.close()
            return False

        print("WhatsApp loaded successfully!")
        time.sleep(3)

        # ---------------------------------------------------------------
        # Step 1: Initiate chats with all numbers first so they appear
        # as recent contacts. Use the /send?phone= URL approach.
        # ---------------------------------------------------------------
        valid_phones = []
        print("Initiating chats with contacts...")
        for idx, phone in enumerate(phones, 1):
            phone_clean = phone.replace('+', '')
            url = f'https://web.whatsapp.com/send?phone={phone_clean}'
            try:
                print(f"  [{idx}/{len(phones)}] Opening chat with {phone}...")
                page.goto(url, wait_until='domcontentloaded')
                time.sleep(3)

                # Check for invalid number popup
                try:
                    invalid = page.locator('[data-testid="popup-controls-ok"]')
                    if invalid.is_visible(timeout=2000):
                        print(f"    - Invalid number: {phone}")
                        invalid.click()
                        time.sleep(1)
                        continue
                except Exception:
                    pass

                # Wait for the chat compose box to appear
                try:
                    page.wait_for_selector(
                        '[data-testid="conversation-compose-box-input"], '
                        'footer div[contenteditable="true"]',
                        timeout=10000
                    )
                    valid_phones.append(phone)
                    print(f"    + Chat ready for {phone}")
                except PwTimeout:
                    print(f"    - Could not open chat for {phone}")

                time.sleep(1)
            except Exception as e:
                print(f"    ! Error with {phone}: {e}")

        if not valid_phones:
            print("No valid WhatsApp numbers found.")
            browser.close()
            return False

        # ---------------------------------------------------------------
        # Step 2: Go back to main page and create group
        # ---------------------------------------------------------------
        page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded')
        time.sleep(4)
        try:
            page.wait_for_selector('#side', timeout=15000)
        except PwTimeout:
            print("Could not return to main page")
            browser.close()
            return False
        time.sleep(2)

        # ---------------------------------------------------------------
        # Step 3: Open new chat -> New group
        # ---------------------------------------------------------------
        print("Opening new chat menu...")
        try:
            new_chat = page.locator(
                '[data-testid="menu-bar-new-chat"], '
                '[aria-label="محادثة جديدة"], [aria-label="New chat"], '
                'div[title="محادثة جديدة"], div[title="New chat"]'
            )
            new_chat.first.click(timeout=10000)
            time.sleep(2)
        except Exception as e:
            print(f"Could not find new chat button: {e}")
            browser.close()
            return False

        print("Selecting 'New group'...")
        try:
            new_group = page.locator(
                '[data-testid="btn-new-group"], '
                'div[role="button"]:has-text("مجموعة جديدة"), '
                'div[role="button"]:has-text("New group"), '
                'span:has-text("مجموعة جديدة"), '
                'span:has-text("New group")'
            )
            new_group.first.click(timeout=10000)
            time.sleep(2)
        except Exception as e:
            print(f"Could not find new group button: {e}")
            browser.close()
            return False

        # ---------------------------------------------------------------
        # Step 4: Search and add each contact
        # Try multiple search formats for each number
        # ---------------------------------------------------------------
        added_count = 0
        for phone in valid_phones:
            phone_clean = phone.replace('+', '')
            # Try different search formats
            search_variants = [
                phone,                      # +963992129149
                phone_clean,                # 963992129149
                '0' + phone_clean[3:],      # 0992129149 (local format)
                phone_clean[3:],            # 992129149 (without country code)
            ]

            found = False
            for variant in search_variants:
                try:
                    search = page.locator(
                        'input[data-testid="search-input"], '
                        'input[title*="ابحث"], input[title*="search"], '
                        'input[title*="Type"], input[type="text"]'
                    ).first

                    search.click()
                    time.sleep(0.2)
                    search.fill('')
                    time.sleep(0.3)
                    search.type(variant, delay=40)
                    time.sleep(2)

                    # Look for any clickable contact result
                    # Take screenshot for debugging on first attempt
                    if added_count == 0 and variant == search_variants[0]:
                        try:
                            page.screenshot(path=os.path.join(os.path.dirname(__file__), 'wa_debug.png'))
                            print("  (Debug screenshot saved as wa_debug.png)")
                        except Exception:
                            pass

                    contact = page.locator(
                        '[data-testid="cell-frame-container"], '
                        '[data-testid="contact-list-item"], '
                        'div[role="listitem"], '
                        'div[role="option"], '
                        'div._ajv6, '
                        'div.matched-text'
                    ).first

                    try:
                        contact.click(timeout=3000)
                        added_count += 1
                        print(f"  + Added: {phone} (searched: {variant})")
                        found = True
                        break
                    except PwTimeout:
                        pass

                    # Clear search
                    search.fill('')
                    time.sleep(0.3)
                except Exception:
                    pass

            if not found:
                print(f"  - Not found: {phone} (tried all formats)")

            time.sleep(0.5)
            # Always clear search
            try:
                page.locator(
                    'input[data-testid="search-input"], '
                    'input[type="text"]'
                ).first.fill('')
            except Exception:
                pass
            time.sleep(0.3)

        if added_count == 0:
            print("\nNo contacts could be added to the group.")
            print("This usually means the numbers are not saved in your phone contacts.")
            print("WhatsApp requires contacts to be saved in your phone to add to groups.")
            print(f"\nPlease save these numbers in your phone contacts and try again:")
            for i, phone in enumerate(valid_phones, 1):
                print(f"  Save as '{group_name} {i}': {phone}")
            browser.close()
            return False

        print(f"\nAdded {added_count}/{len(valid_phones)} contacts. Proceeding...")

        # ---------------------------------------------------------------
        # Step 5: Click next/forward arrow
        # ---------------------------------------------------------------
        try:
            next_btn = page.locator(
                '[data-testid="arrow-forward"], '
                'span[data-icon="arrow-forward"], '
                '[aria-label="التالي"], [aria-label="Next"]'
            )
            next_btn.first.click(timeout=5000)
            time.sleep(3)
        except Exception as e:
            print(f"Could not click next: {e}")
            browser.close()
            return False

        # ---------------------------------------------------------------
        # Step 6: Set group name
        # ---------------------------------------------------------------
        print(f"Setting group name: {group_name}")
        try:
            name_input = page.locator(
                'div[data-testid="group-name-input"], '
                'div[contenteditable="true"][title*="اسم"], '
                'div[contenteditable="true"][title*="subject"], '
                'div[contenteditable="true"][role="textbox"]'
            ).first
            name_input.click()
            time.sleep(0.5)
            name_input.type(group_name, delay=30)
            time.sleep(1)
        except Exception as e:
            print(f"Could not set group name: {e}")

        # ---------------------------------------------------------------
        # Step 7: Click create group
        # ---------------------------------------------------------------
        try:
            create_btn = page.locator(
                '[data-testid="create-group-btn"], '
                'span[data-icon="checkmark-large"], '
                '[aria-label="Create group"], '
                '[aria-label="إنشاء مجموعة"]'
            )
            create_btn.first.click(timeout=5000)
            time.sleep(4)
        except Exception as e:
            print(f"Could not click create: {e}")
            browser.close()
            return False

        print(f"\nGroup '{group_name}' created successfully with {added_count} members!")
        time.sleep(5)
        browser.close()
        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create WhatsApp group via automation')
    parser.add_argument('--name', required=True, help='Group name')
    parser.add_argument('--phones', required=True, help='Comma-separated phone numbers')
    parser.add_argument('--headless', action='store_true', help='Run headless (not for first run)')
    args = parser.parse_args()

    phones = [p.strip() for p in args.phones.split(',') if p.strip()]
    success = create_whatsapp_group(args.name, phones, headless=args.headless)
    sys.exit(0 if success else 1)
