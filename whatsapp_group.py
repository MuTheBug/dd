"""
WhatsApp Group Creator using Playwright.
Automates creating a WhatsApp group and adding members by phone number.

Usage:
    python whatsapp_group.py --name "Group Name" --phones "+963123456789,+963987654321"

First run will ask you to scan the QR code. Session is saved for subsequent runs.
"""

import argparse
import json
import os
import sys
import time

WA_SESSION_DIR = os.path.join(os.path.dirname(__file__), '.wa_session')


def create_whatsapp_group(group_name, phone_numbers, headless=False):
    """Create a WhatsApp group and add members."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    # Clean phone numbers
    phones = []
    for p in phone_numbers:
        p = p.strip().replace(' ', '').replace('-', '')
        if not p:
            continue
        # Ensure international format
        if p.startswith('0'):
            p = '+963' + p[1:]  # Default to Syria country code
        if not p.startswith('+'):
            p = '+' + p
        phones.append(p)

    if not phones:
        print("No valid phone numbers provided.")
        return False

    print(f"Creating group '{group_name}' with {len(phones)} contacts...")
    print(f"Numbers: {', '.join(phones)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=WA_SESSION_DIR,
            headless=headless,
            args=['--disable-blink-features=AutomationControlled'],
            locale='ar',
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded')

        # Wait for WhatsApp to load (either QR code or main screen)
        print("Waiting for WhatsApp Web to load...")
        print("If this is your first time, scan the QR code with your phone.")

        # Wait for the main chat list to appear (means logged in)
        try:
            page.wait_for_selector('[aria-label="قائمة المحادثات"], [aria-label="Chat list"], [data-testid="chat-list"]', timeout=120000)
        except Exception:
            print("Timeout waiting for WhatsApp to load. Make sure you scanned the QR code.")
            browser.close()
            return False

        print("WhatsApp loaded! Creating group...")
        time.sleep(2)

        # Click the new chat / menu button
        try:
            # Try the "+" or new chat button
            new_chat_btn = page.locator('[data-testid="menu-bar-new-chat"], [aria-label="محادثة جديدة"], [aria-label="New chat"]')
            new_chat_btn.first.click()
            time.sleep(1)
        except Exception as e:
            print(f"Could not find new chat button: {e}")
            browser.close()
            return False

        # Click "New group"
        try:
            new_group_btn = page.locator('[data-testid="new-group-btn"], [aria-label="مجموعة جديدة"], [aria-label="New group"]')
            new_group_btn.first.click()
            time.sleep(1)
        except Exception as e:
            print(f"Could not find new group button: {e}")
            browser.close()
            return False

        # Add contacts by searching phone numbers
        added_count = 0
        for phone in phones:
            try:
                # Type phone number in search box
                search_input = page.locator('[data-testid="search-input"], [title="ابحث عن اسم أو رقم"], [title="Type contact name or number"]')
                search_input.first.fill('')
                time.sleep(0.3)
                search_input.first.fill(phone)
                time.sleep(2)

                # Try to click the contact result
                # Look for contact items in the search results
                contact = page.locator('[data-testid="cell-frame-container"], [data-testid="contact-list-item"]').first
                if contact.is_visible(timeout=3000):
                    contact.click()
                    added_count += 1
                    print(f"  Added: {phone}")
                else:
                    print(f"  Not found: {phone}")
            except Exception as e:
                print(f"  Could not add {phone}: {e}")

            time.sleep(0.5)
            # Clear search
            try:
                search_input.first.fill('')
            except Exception:
                pass
            time.sleep(0.3)

        if added_count == 0:
            print("No contacts could be added. Make sure the numbers are saved in your phone contacts.")
            browser.close()
            return False

        print(f"Added {added_count}/{len(phones)} contacts. Proceeding to create group...")

        # Click the forward/next arrow to proceed
        try:
            next_btn = page.locator('[data-testid="arrow-forward"], [data-icon="arrow-forward"], [aria-label="التالي"], [aria-label="Next"]')
            next_btn.first.click()
            time.sleep(2)
        except Exception as e:
            print(f"Could not click next: {e}")
            browser.close()
            return False

        # Set group name
        try:
            group_name_input = page.locator('[data-testid="group-name-input"], [title="اسم الموضوع"], [title="Group subject"]')
            group_name_input.first.fill(group_name)
            time.sleep(1)
        except Exception as e:
            print(f"Could not set group name: {e}")

        # Click create group (the green checkmark)
        try:
            create_btn = page.locator('[data-testid="create-group-btn"], [data-icon="checkmark-large"], [aria-label="إنشاء مجموعة"], [aria-label="Create group"]')
            create_btn.first.click()
            time.sleep(3)
        except Exception as e:
            print(f"Could not click create: {e}")
            browser.close()
            return False

        print(f"Group '{group_name}' created successfully with {added_count} members!")

        # Keep browser open briefly to confirm
        time.sleep(3)
        browser.close()
        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create WhatsApp group via automation')
    parser.add_argument('--name', required=True, help='Group name')
    parser.add_argument('--phones', required=True, help='Comma-separated phone numbers')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (not recommended for first run)')
    args = parser.parse_args()

    phones = [p.strip() for p in args.phones.split(',') if p.strip()]
    success = create_whatsapp_group(args.name, phones, headless=args.headless)
    sys.exit(0 if success else 1)
