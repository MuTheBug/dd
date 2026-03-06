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
DEBUG_DIR = os.path.dirname(__file__)


def debug_screenshot(page, name):
    """Save a debug screenshot."""
    try:
        path = os.path.join(DEBUG_DIR, f'wa_debug_{name}.png')
        page.screenshot(path=path)
        print(f"  [screenshot: wa_debug_{name}.png]")
    except Exception:
        pass


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
            locale='en-US',
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
                    '#side, [data-testid="chat-list"]',
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
        time.sleep(4)
        debug_screenshot(page, '01_loaded')

        # ---------------------------------------------------------------
        # Step 1: Initiate chats with all numbers first via direct URL
        # This ensures the numbers appear as "recent" in contact search
        # ---------------------------------------------------------------
        valid_phones = []
        print("\nStep 1: Initiating chats with each number...")
        for idx, phone in enumerate(phones, 1):
            phone_clean = phone.replace('+', '')
            url = f'https://web.whatsapp.com/send?phone={phone_clean}'
            try:
                print(f"  [{idx}/{len(phones)}] {phone}...")
                page.goto(url, wait_until='domcontentloaded')
                time.sleep(4)

                # Check for invalid number popup
                try:
                    popup_ok = page.locator('[data-testid="popup-controls-ok"]')
                    if popup_ok.is_visible(timeout=2000):
                        print(f"    - Invalid number")
                        popup_ok.click()
                        time.sleep(1)
                        continue
                except Exception:
                    pass

                # Wait for chat to load
                try:
                    page.wait_for_selector(
                        '[data-testid="conversation-compose-box-input"], '
                        'footer div[contenteditable="true"]',
                        timeout=8000
                    )
                    valid_phones.append(phone)
                    print(f"    + OK")
                except PwTimeout:
                    print(f"    - Chat did not open")
                time.sleep(1)
            except Exception as e:
                print(f"    ! Error: {e}")

        if not valid_phones:
            print("No valid WhatsApp numbers found.")
            browser.close()
            return False

        print(f"\n{len(valid_phones)} valid numbers confirmed.")

        # ---------------------------------------------------------------
        # Step 2: Return to main page
        # ---------------------------------------------------------------
        page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded')
        time.sleep(5)
        try:
            page.wait_for_selector('#side', timeout=15000)
        except PwTimeout:
            print("Could not return to main page")
            browser.close()
            return False
        time.sleep(2)

        # ---------------------------------------------------------------
        # Step 3: Open "New group" via the three-dot menu (⋮)
        # The current WhatsApp Web uses a menu button at top of chat list
        # ---------------------------------------------------------------
        print("\nStep 2: Opening New Group...")
        debug_screenshot(page, '02_main_page')

        # Try approach A: three-dot menu -> New group
        group_screen_opened = False

        # Method 1: Click the three-dot menu button
        print("  Trying menu button (⋮)...")
        try:
            menu_btn = page.locator(
                '[data-testid="menu"], '
                '[aria-label="Menu"], '
                'header button[aria-label="Menu"], '
                'div#side header span[data-icon="menu"]'
            )
            # Also try the more general three-dot / kebab menu
            if menu_btn.count() == 0:
                menu_btn = page.locator('header span[data-icon]').last
            menu_btn.first.click(timeout=5000)
            time.sleep(1.5)
            debug_screenshot(page, '03_menu_open')

            # Look for "New group" in the dropdown menu
            new_group_item = page.locator(
                'li:has-text("New group"), '
                'li:has-text("مجموعة جديدة"), '
                'div[role="menuitem"]:has-text("New group"), '
                'div[role="menuitem"]:has-text("مجموعة جديدة"), '
                'div[aria-label="New group"], '
                'div[aria-label="مجموعة جديدة")'
            )
            new_group_item.first.click(timeout=5000)
            time.sleep(2)
            group_screen_opened = True
            print("    + Opened via menu")
        except Exception as e:
            print(f"    - Menu method failed: {e}")

        # Method 2: Click the + (new chat) button, then "New group"
        if not group_screen_opened:
            print("  Trying new chat button (+)...")
            try:
                # Try multiple selectors for the new chat / compose button
                new_chat_btn = page.locator(
                    '[data-testid="menu-bar-new-chat"], '
                    '[aria-label="New chat"], '
                    '[aria-label="محادثة جديدة"], '
                    'div[title="New chat"], '
                    'div[title="محادثة جديدة"], '
                    'header button >> nth=0'
                )
                new_chat_btn.first.click(timeout=5000)
                time.sleep(2)
                debug_screenshot(page, '03b_new_chat')

                new_group_opt = page.locator(
                    '[data-testid="btn-new-group"], '
                    ':text("New group"), '
                    ':text("مجموعة جديدة")'
                )
                new_group_opt.first.click(timeout=5000)
                time.sleep(2)
                group_screen_opened = True
                print("    + Opened via new chat button")
            except Exception as e:
                print(f"    - New chat method failed: {e}")

        # Method 3: Try keyboard shortcut or direct click using JS
        if not group_screen_opened:
            print("  Trying via JavaScript click...")
            try:
                # Find all buttons/clickable elements with relevant text
                page.evaluate("""
                    () => {
                        const allElements = document.querySelectorAll('span, div, button');
                        for (const el of allElements) {
                            const text = el.textContent.trim();
                            if (text === 'New group' || text === 'مجموعة جديدة') {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                time.sleep(2)
                debug_screenshot(page, '03c_js_click')
                group_screen_opened = True
                print("    + Opened via JS")
            except Exception as e:
                print(f"    - JS method failed: {e}")

        if not group_screen_opened:
            debug_screenshot(page, '03_FAILED')
            print("\nCould not open group creation screen.")
            print("Check wa_debug_03_FAILED.png for current state.")
            browser.close()
            return False

        debug_screenshot(page, '04_group_screen')
        time.sleep(1)

        # ---------------------------------------------------------------
        # Step 4: Search and add each contact
        # ---------------------------------------------------------------
        print("\nStep 3: Adding contacts to group...")
        added_count = 0

        for phone in valid_phones:
            phone_clean = phone.replace('+', '')
            # Try multiple search formats
            search_variants = [
                phone_clean,                # 963992129149
                phone,                      # +963992129149
                '0' + phone_clean[3:],      # 0992129149
                phone_clean[3:],            # 992129149
            ]

            found = False
            for vi, variant in enumerate(search_variants):
                try:
                    # Find any text input on the page (the participant search box)
                    search = page.locator('input[type="text"], input[role="searchbox"]').first
                    search.click()
                    time.sleep(0.2)
                    search.fill('')
                    time.sleep(0.2)
                    search.type(variant, delay=40)
                    time.sleep(2.5)

                    if added_count == 0 and vi == 0:
                        debug_screenshot(page, '05_first_search')

                    # Try clicking any result that appears (excluding "no results" type messages)
                    result = page.locator(
                        '[data-testid="cell-frame-container"], '
                        '[data-testid="contact-list-item"], '
                        'div[role="listitem"], '
                        'div[role="option"], '
                        'div[tabindex="-1"][class*="matched"]'
                    ).first

                    try:
                        result.click(timeout=3000)
                        added_count += 1
                        print(f"  + Added: {phone}")
                        found = True
                        break
                    except PwTimeout:
                        pass

                    search.fill('')
                    time.sleep(0.3)
                except Exception:
                    pass

            if not found:
                print(f"  - Not found: {phone}")

            time.sleep(0.3)
            # Clear search
            try:
                page.locator('input[type="text"], input[role="searchbox"]').first.fill('')
            except Exception:
                pass
            time.sleep(0.3)

        debug_screenshot(page, '06_after_adding')

        if added_count == 0:
            print("\nNo contacts could be added.")
            print("The numbers are not in your phone contacts.")
            print(f"\nPlease save these numbers in your phone:")
            for i, phone in enumerate(valid_phones, 1):
                print(f"  Name: '{group_name} {i}'  Phone: {phone}")
            print("\nAfter saving, try again.")
            browser.close()
            return False

        print(f"\n{added_count}/{len(valid_phones)} contacts added.")

        # ---------------------------------------------------------------
        # Step 5: Click next/forward arrow
        # ---------------------------------------------------------------
        print("\nStep 4: Proceeding to group info...")
        try:
            next_btn = page.locator(
                '[data-testid="arrow-forward"], '
                'span[data-icon="arrow-forward"], '
                '[aria-label="Next"], [aria-label="التالي"]'
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

        print(f"\nGroup '{group_name}' created with {added_count} members!")
        debug_screenshot(page, '07_done')
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
