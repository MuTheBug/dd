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

                # Check for invalid number popup
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

        # Press Escape to close any open panels
        page.keyboard.press('Escape')
        time.sleep(1)

        print("\nStep 2: Opening group creation screen...")

        # Inspect available header icons for debugging
        try:
            icons = page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('header span[data-icon], header [data-testid], #side header span[data-icon]').forEach(el => {
                        results.push({
                            tag: el.tagName,
                            dataIcon: el.getAttribute('data-icon'),
                            testId: el.getAttribute('data-testid'),
                            ariaLabel: el.getAttribute('aria-label'),
                            title: el.getAttribute('title'),
                        });
                    });
                    return results;
                }
            """)
            print(f"  Found header icons: {icons}")
        except Exception:
            pass

        debug_screenshot(page, '02_before_menu')

        # ------- Try to open "New group" -------
        group_screen = False

        # APPROACH 1: Click the ⋮ (three-dot) menu via data-icon
        print("  Approach 1: Three-dot menu...")
        try:
            # Find the menu/more icon in the header area
            menu_icon = page.locator(
                'span[data-icon="menu"], '
                'span[data-icon="more"], '
                '[data-testid="menu"], '
                '[data-testid="menu-bar-menu"]'
            )
            if menu_icon.count() > 0:
                menu_icon.first.click()
                time.sleep(1.5)
                debug_screenshot(page, '03a_menu_dropdown')

                # Find "New group" in the dropdown
                ng = page.get_by_text("New group")
                if ng.count() == 0:
                    ng = page.get_by_text("مجموعة جديدة")
                ng.first.click(timeout=3000)
                time.sleep(2)
                group_screen = True
                print("    + Success!")
            else:
                print("    - Menu icon not found")
        except Exception as e:
            print(f"    - Failed: {e}")
            page.keyboard.press('Escape')
            time.sleep(0.5)

        # APPROACH 2: Click the ⊞ (new chat/compose) button
        if not group_screen:
            print("  Approach 2: New chat button...")
            try:
                compose = page.locator(
                    'span[data-icon="new-chat-outline"], '
                    'span[data-icon="chat"], '
                    'span[data-icon="new-chat"], '
                    '[data-testid="menu-bar-new-chat"]'
                )
                if compose.count() > 0:
                    compose.first.click()
                    time.sleep(2)
                    debug_screenshot(page, '03b_new_chat_panel')

                    ng = page.get_by_text("New group")
                    if ng.count() == 0:
                        ng = page.get_by_text("مجموعة جديدة")
                    ng.first.click(timeout=3000)
                    time.sleep(2)
                    group_screen = True
                    print("    + Success!")
                else:
                    print("    - Compose button not found")
            except Exception as e:
                print(f"    - Failed: {e}")
                page.keyboard.press('Escape')
                time.sleep(0.5)

        # APPROACH 3: Click ALL span[data-icon] in the header until we find the right one
        if not group_screen:
            print("  Approach 3: Trying all header icons...")
            try:
                all_icons = page.locator('#side span[data-icon]')
                count = all_icons.count()
                print(f"    Found {count} icons in #side")
                for i in range(count):
                    icon = all_icons.nth(i)
                    icon_name = icon.get_attribute('data-icon')
                    print(f"    Trying icon [{i}]: {icon_name}")
                    try:
                        icon.click()
                        time.sleep(1.5)

                        # Check if "New group" text appeared anywhere
                        ng = page.get_by_text("New group")
                        if ng.count() == 0:
                            ng = page.get_by_text("مجموعة جديدة")
                        if ng.count() > 0:
                            debug_screenshot(page, f'03c_found_at_icon_{i}')
                            ng.first.click(timeout=3000)
                            time.sleep(2)
                            group_screen = True
                            print(f"    + Success via icon [{i}]: {icon_name}!")
                            break
                        else:
                            page.keyboard.press('Escape')
                            time.sleep(0.5)
                    except Exception:
                        page.keyboard.press('Escape')
                        time.sleep(0.5)
            except Exception as e:
                print(f"    - Failed: {e}")

        # APPROACH 4: Use JavaScript to find and click "New group" wherever it is
        if not group_screen:
            print("  Approach 4: JavaScript brute force...")
            try:
                # First, try clicking the + icon at approximate position
                # From screenshot, + icon is at roughly x=478, y=31
                page.mouse.click(478, 31)
                time.sleep(2)
                debug_screenshot(page, '03d_after_plus_click')

                found = page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('span, div, button, li');
                        for (const el of els) {
                            const text = (el.textContent || '').trim();
                            if (text === 'New group' || text === 'مجموعة جديدة') {
                                if (el.offsetParent !== null) {  // is visible
                                    el.click();
                                    return text;
                                }
                            }
                        }
                        return null;
                    }
                """)
                if found:
                    time.sleep(2)
                    group_screen = True
                    print(f"    + Success! Clicked: {found}")
                else:
                    print("    - 'New group' text not found on page")
            except Exception as e:
                print(f"    - Failed: {e}")

        if not group_screen:
            debug_screenshot(page, '03_ALL_FAILED')
            print("\nERROR: Could not open group creation screen.")
            print("Check wa_debug screenshots for diagnosis.")

            # Dump all visible text for debugging
            try:
                texts = page.evaluate("""
                    () => {
                        const results = [];
                        document.querySelectorAll('[data-icon], [data-testid]').forEach(el => {
                            if (el.offsetParent !== null) {
                                results.push({
                                    icon: el.getAttribute('data-icon'),
                                    testId: el.getAttribute('data-testid'),
                                    text: (el.textContent || '').trim().substring(0, 50)
                                });
                            }
                        });
                        return results;
                    }
                """)
                print("\nVisible elements with data-icon/data-testid:")
                for t in texts[:30]:
                    print(f"  {t}")
            except Exception:
                pass

            browser.close()
            return False

        # ---------------------------------------------------------------
        # Step 3: Verify we're on the group creation screen
        # The group screen should have "Add participants" or similar heading
        # ---------------------------------------------------------------
        debug_screenshot(page, '04_group_screen')
        print("\nStep 3: On group creation screen. Adding contacts...")

        # Wait a moment for the participant search to be ready
        time.sleep(1)

        # Find the search input specifically in the group creation panel
        # This should NOT be the main search bar
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
                    # Target the search input - prefer the one inside the panel, not the main search
                    # The group creation panel typically uses a different input
                    search_inputs = page.locator('input[type="text"]')
                    search_count = search_inputs.count()

                    # Use the LAST input (most likely the group participant search)
                    # or any input that's not the main search bar
                    search = search_inputs.last if search_count > 1 else search_inputs.first

                    search.click()
                    time.sleep(0.2)
                    search.fill('')
                    time.sleep(0.2)
                    search.type(variant, delay=40)
                    time.sleep(2.5)

                    if added_count == 0 and vi == 0:
                        debug_screenshot(page, '05_search')

                    # Try to find any clickable result
                    result = page.locator(
                        '[data-testid="cell-frame-container"], '
                        'div[role="listitem"], '
                        'div[role="option"]'
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
            try:
                page.locator('input[type="text"]').last.fill('')
            except Exception:
                pass
            time.sleep(0.3)

        debug_screenshot(page, '06_after_search')

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
            name_input.type(group_name, delay=30)
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
