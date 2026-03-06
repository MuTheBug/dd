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


def find_group_search_input(page):
    """Find the search input on the group participant screen.
    WhatsApp uses various input types depending on version."""

    # Inspect what inputs exist
    try:
        inputs_info = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('input, div[contenteditable="true"]').forEach(el => {
                    if (el.offsetParent !== null) {
                        results.push({
                            tag: el.tagName,
                            type: el.getAttribute('type'),
                            testId: el.getAttribute('data-testid'),
                            placeholder: el.getAttribute('placeholder') || el.getAttribute('title') || '',
                            role: el.getAttribute('role'),
                            ariaLabel: el.getAttribute('aria-label'),
                            tab: el.getAttribute('data-tab'),
                            ce: el.getAttribute('contenteditable'),
                        });
                    }
                });
                return results;
            }
        """)
        print(f"  Available inputs: {inputs_info}")
    except Exception:
        pass

    # Try multiple selectors in priority order
    selectors = [
        # WhatsApp group participant search specific selectors
        'input[data-testid="search-input"]',
        'input[title*="contact"], input[title*="participant"]',
        'input[title*="ابحث"], input[title*="Search"], input[title*="search"]',
        'input[placeholder*="contact"], input[placeholder*="search"]',
        # Contenteditable divs used as search boxes
        'div[contenteditable="true"][data-tab="2"]',
        'div[contenteditable="true"][role="textbox"][title*="search"]',
        'div[contenteditable="true"][role="textbox"][title*="ابحث"]',
        # Generic fallbacks
        'input[type="text"]',
        'div[contenteditable="true"][role="textbox"]',
    ]

    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            print(f"  Using input: {sel} (count={loc.count()})")
            return loc.last if loc.count() > 1 else loc.first

    return None


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

        page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded')
        print("Waiting for WhatsApp Web to load...")
        print("If this is your first time, scan the QR code with your phone.")
        print("You have up to 3 minutes to scan...")

        logged_in = False
        for attempt in range(6):
            try:
                page.wait_for_selector('#side', timeout=30000)
                logged_in = True
                break
            except PwTimeout:
                print(f"  Still waiting for login... ({(attempt+1)*30}s)")

        if not logged_in:
            print("Timeout waiting for WhatsApp login.")
            browser.close()
            return False

        print("WhatsApp loaded successfully!")
        time.sleep(4)

        # ---------------------------------------------------------------
        # Step 1: Initiate chats with each number via direct URL
        # ---------------------------------------------------------------
        valid_phones = []
        print("\nStep 1: Verifying numbers have WhatsApp...")
        for idx, phone in enumerate(phones, 1):
            phone_clean = phone.replace('+', '')
            url = f'https://web.whatsapp.com/send?phone={phone_clean}'
            try:
                print(f"  [{idx}/{len(phones)}] {phone}...", end=' ')
                page.goto(url, wait_until='domcontentloaded')
                time.sleep(4)

                try:
                    popup_ok = page.locator('[data-testid="popup-controls-ok"]')
                    if popup_ok.is_visible(timeout=2000):
                        print("INVALID")
                        popup_ok.click()
                        time.sleep(1)
                        continue
                except Exception:
                    pass

                try:
                    page.wait_for_selector(
                        '[data-testid="conversation-compose-box-input"], '
                        'footer div[contenteditable="true"]',
                        timeout=8000
                    )
                    valid_phones.append(phone)
                    print("OK")
                except PwTimeout:
                    print("FAILED")
                time.sleep(1)
            except Exception as e:
                print(f"ERROR: {e}")

        if not valid_phones:
            print("No valid WhatsApp numbers found.")
            browser.close()
            return False

        print(f"\n{len(valid_phones)} valid numbers confirmed.")

        # ---------------------------------------------------------------
        # Step 2: Return to main page and open "New group"
        # ---------------------------------------------------------------
        page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded')
        time.sleep(5)
        try:
            page.wait_for_selector('#side', timeout=15000)
        except PwTimeout:
            print("Could not return to main page")
            browser.close()
            return False
        time.sleep(3)
        page.keyboard.press('Escape')
        time.sleep(1)

        print("\nStep 2: Opening group creation screen...")

        # The new-chat-outline icon was confirmed working
        group_screen = False

        # Click the new-chat-outline icon (confirmed from previous run)
        print("  Clicking new-chat-outline icon...")
        try:
            compose = page.locator('span[data-icon="new-chat-outline"]')
            if compose.count() > 0:
                compose.first.click()
                time.sleep(2)
                debug_screenshot(page, '03_new_chat_panel')

                # Find "New group" text
                ng = page.get_by_text("New group")
                if ng.count() == 0:
                    ng = page.get_by_text("مجموعة جديدة")
                if ng.count() > 0:
                    ng.first.click(timeout=3000)
                    time.sleep(2)
                    group_screen = True
                    print("  + Group screen opened!")
                else:
                    print("  - 'New group' text not found in panel")
            else:
                print("  - new-chat-outline icon not found")
        except Exception as e:
            print(f"  - Failed: {e}")
            page.keyboard.press('Escape')
            time.sleep(0.5)

        if not group_screen:
            debug_screenshot(page, '03_FAILED')
            print("\nCould not open group creation screen.")
            browser.close()
            return False

        debug_screenshot(page, '04_group_screen')

        # ---------------------------------------------------------------
        # Step 3: Find the participant search input and add contacts
        # ---------------------------------------------------------------
        print("\nStep 3: Adding contacts to group...")
        time.sleep(2)

        search_input = find_group_search_input(page)
        if not search_input:
            print("ERROR: Could not find search input on group screen!")
            debug_screenshot(page, '04_no_input')
            browser.close()
            return False

        added_count = 0
        for phone in valid_phones:
            phone_clean = phone.replace('+', '')
            search_variants = [
                phone_clean,
                phone,
                '0' + phone_clean[3:],
                phone_clean[3:],
            ]

            found = False
            for vi, variant in enumerate(search_variants):
                try:
                    # Re-find the search input each time (DOM may have changed)
                    si = find_group_search_input(page)
                    if not si:
                        print(f"  ! Search input lost")
                        break

                    si.click()
                    time.sleep(0.3)

                    # Clear using keyboard (more reliable than fill for contenteditable)
                    page.keyboard.press('Control+a')
                    time.sleep(0.1)
                    page.keyboard.press('Backspace')
                    time.sleep(0.3)

                    # Type using keyboard (more reliable for both input and contenteditable)
                    page.keyboard.type(variant, delay=40)
                    time.sleep(3)

                    if added_count == 0 and vi == 0:
                        debug_screenshot(page, '05_first_search')

                    # Try to find any clickable contact result
                    result = page.locator(
                        '[data-testid="cell-frame-container"], '
                        'div[role="listitem"], '
                        'div[role="option"], '
                        'div[data-testid="contact-list-item"]'
                    ).first

                    try:
                        result.click(timeout=3000)
                        added_count += 1
                        print(f"  + Added: {phone} (format: {variant})")
                        found = True
                        time.sleep(1)
                        break
                    except PwTimeout:
                        # Clear for next variant
                        page.keyboard.press('Control+a')
                        time.sleep(0.1)
                        page.keyboard.press('Backspace')
                        time.sleep(0.3)

                except Exception as e:
                    print(f"  ! Error searching {variant}: {e}")

            if not found:
                print(f"  - Not found: {phone}")
                # Clear search
                try:
                    page.keyboard.press('Control+a')
                    time.sleep(0.1)
                    page.keyboard.press('Backspace')
                    time.sleep(0.3)
                except Exception:
                    pass

            time.sleep(0.5)

        debug_screenshot(page, '06_after_adding')

        if added_count == 0:
            print("\nNo contacts could be added (not in phone contacts).")
            print(f"\nSave these numbers in your phone and retry:")
            for i, ph in enumerate(valid_phones, 1):
                print(f"  Name: '{group_name} {i}'  Phone: {ph}")
            browser.close()
            return False

        print(f"\n{added_count}/{len(valid_phones)} contacts added.")

        # ---------------------------------------------------------------
        # Step 4: Click next arrow
        # ---------------------------------------------------------------
        print("\nStep 4: Setting up group...")
        try:
            next_btn = page.locator(
                '[data-testid="arrow-forward"], '
                'span[data-icon="arrow-forward"]'
            )
            next_btn.first.click(timeout=5000)
            time.sleep(3)
        except Exception as e:
            print(f"Could not click next: {e}")
            browser.close()
            return False

        # ---------------------------------------------------------------
        # Step 5: Set group name
        # ---------------------------------------------------------------
        print(f"Setting group name: {group_name}")
        try:
            name_input = page.locator(
                'div[contenteditable="true"][role="textbox"]'
            ).first
            name_input.click()
            time.sleep(0.5)
            page.keyboard.type(group_name, delay=30)
            time.sleep(1)
        except Exception as e:
            print(f"Could not set group name: {e}")

        # ---------------------------------------------------------------
        # Step 6: Create group
        # ---------------------------------------------------------------
        try:
            create_btn = page.locator(
                'span[data-icon="checkmark-large"], '
                '[data-testid="create-group-btn"]'
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
