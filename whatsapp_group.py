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

        # Wait for login - use a broad selector and long timeout for QR scanning
        # The side panel appears after successful login
        logged_in = False
        for attempt in range(6):  # 6 attempts x 30s = 3 minutes total
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
        time.sleep(3)  # Let everything settle

        # Step 1: Click new chat button
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

        # Step 2: Click "New group"
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

        # Step 3: Add contacts by searching phone numbers
        added_count = 0
        for phone in phones:
            try:
                # Find the search/input box for adding contacts
                search = page.locator(
                    'input[data-testid="search-input"], '
                    'input[title*="ابحث"], input[title*="search"], '
                    'input[title*="Type"], input[type="text"]'
                ).first

                # Clear and type the phone number
                search.click()
                time.sleep(0.3)
                search.fill('')
                time.sleep(0.3)
                search.type(phone, delay=50)
                time.sleep(2.5)

                # Try to find and click a contact result
                contact = page.locator(
                    '[data-testid="cell-frame-container"], '
                    '[data-testid="contact-list-item"], '
                    'div[role="listitem"], '
                    'div[role="option"]'
                ).first

                try:
                    contact.click(timeout=4000)
                    added_count += 1
                    print(f"  + Added: {phone}")
                except PwTimeout:
                    print(f"  - Not found: {phone} (not in contacts)")
            except Exception as e:
                print(f"  ! Error adding {phone}: {e}")

            time.sleep(0.5)
            # Clear search for next number
            try:
                s = page.locator(
                    'input[data-testid="search-input"], '
                    'input[title*="ابحث"], input[title*="search"], '
                    'input[type="text"]'
                ).first
                s.fill('')
            except Exception:
                pass
            time.sleep(0.5)

        if added_count == 0:
            print("No contacts could be added. Numbers must be saved in your phone contacts.")
            browser.close()
            return False

        print(f"Added {added_count}/{len(phones)} contacts. Creating group...")

        # Step 4: Click next/forward arrow
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

        # Step 5: Set group name
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

        # Step 6: Click create group (green checkmark)
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

        print(f"Group '{group_name}' created successfully with {added_count} members!")

        # Keep browser open for a moment so user can verify
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
