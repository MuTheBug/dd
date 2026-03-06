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
        print("You have up to 3 minutes to scan QR if needed...")

        logged_in = False
        for attempt in range(6):
            try:
                page.wait_for_selector('#side', timeout=30000)
                logged_in = True
                break
            except PwTimeout:
                print(f"  Still waiting... ({(attempt+1)*30}s)")

        if not logged_in:
            print("Timeout waiting for login.")
            browser.close()
            return False

        print("WhatsApp loaded!")
        time.sleep(4)

        # ---------------------------------------------------------------
        # Step 1: Verify numbers have WhatsApp via direct URL
        # ---------------------------------------------------------------
        valid_phones = []
        print("\nStep 1: Verifying numbers...")
        for idx, phone in enumerate(phones, 1):
            phone_clean = phone.replace('+', '')
            try:
                print(f"  [{idx}/{len(phones)}] {phone}...", end=' ')
                page.goto(f'https://web.whatsapp.com/send?phone={phone_clean}',
                          wait_until='domcontentloaded')
                time.sleep(4)
                try:
                    popup = page.locator('[data-testid="popup-controls-ok"]')
                    if popup.is_visible(timeout=2000):
                        print("INVALID")
                        popup.click()
                        time.sleep(1)
                        continue
                except Exception:
                    pass
                try:
                    page.wait_for_selector(
                        '[data-testid="conversation-compose-box-input"], '
                        'footer div[contenteditable="true"]',
                        timeout=8000)
                    valid_phones.append(phone)
                    print("OK")
                except PwTimeout:
                    print("FAILED")
                time.sleep(1)
            except Exception as e:
                print(f"ERROR: {e}")

        if not valid_phones:
            print("No valid WhatsApp numbers.")
            browser.close()
            return False

        print(f"{len(valid_phones)} valid numbers.")

        # ---------------------------------------------------------------
        # Step 2: Open group creation screen
        # ---------------------------------------------------------------
        page.goto('https://web.whatsapp.com/', wait_until='domcontentloaded')
        time.sleep(5)
        try:
            page.wait_for_selector('#side', timeout=15000)
        except PwTimeout:
            browser.close()
            return False
        time.sleep(3)
        page.keyboard.press('Escape')
        time.sleep(1)

        print("\nStep 2: Opening group creation...")
        # Click new-chat-outline (confirmed working)
        try:
            page.locator('span[data-icon="new-chat-outline"]').first.click()
            time.sleep(2)
            ng = page.get_by_text("New group")
            if ng.count() == 0:
                ng = page.get_by_text("مجموعة جديدة")
            ng.first.click(timeout=3000)
            time.sleep(3)
            print("  Group screen opened!")
        except Exception as e:
            print(f"  Failed to open group screen: {e}")
            browser.close()
            return False

        debug_screenshot(page, '04_group_screen')

        # ---------------------------------------------------------------
        # Step 3: Add contacts by typing in "Search name or number" input
        # From the screenshot we can see:
        #   - The page shows "Add group members"
        #   - Input placeholder: "Search name or number"
        #   - Contacts listed below alphabetically
        # ---------------------------------------------------------------
        print("\nStep 3: Adding contacts...")
        time.sleep(1)

        added_count = 0

        # Search input is: <input type="text" placeholder="Search name or number">

        def find_and_focus_search():
            """Find and focus the search input, return True if focused."""
            focused = page.evaluate("""
                () => {
                    // Direct: find input by placeholder attribute
                    const input = document.querySelector(
                        'input[placeholder*="Search name"], ' +
                        'input[placeholder*="ابحث عن اسم"]'
                    );
                    if (input) {
                        input.focus();
                        input.click();
                        return {found: true, tag: 'INPUT',
                                placeholder: input.placeholder};
                    }
                    // Fallback: any visible contenteditable in left panel
                    const ce = document.querySelector(
                        '[contenteditable="true"][role="textbox"]'
                    );
                    if (ce && ce.offsetParent) {
                        ce.focus();
                        ce.click();
                        return {found: true, tag: 'CE'};
                    }
                    return {found: false};
                }
            """)
            print(f"    focus result: {focused}")
            return focused.get('found', False)

        def type_in_search(text):
            """Type text into the currently focused search input."""
            # Clear first
            page.keyboard.press('Control+a')
            time.sleep(0.1)
            page.keyboard.press('Backspace')
            time.sleep(0.2)
            # Type the search text
            page.keyboard.type(text, delay=50)

        def clear_search():
            """Clear the search input."""
            find_and_focus_search()
            time.sleep(0.2)
            page.keyboard.press('Control+a')
            time.sleep(0.1)
            page.keyboard.press('Backspace')
            time.sleep(0.3)

        def click_search_result():
            """Click the first contact in the search results list.

            After typing in the search box, the contact list filters.
            We need to click a result from the scrollable list, NOT the
            chips of already-added contacts above the search input.

            Strategy: use JS to find div[role="button"] elements that are
            positioned below the search input (in the results area).
            """
            clicked = page.evaluate("""
                () => {
                    // Find the search input to get its position
                    const searchInput = document.querySelector(
                        'input[placeholder*="Search"], input[placeholder*="ابحث"], ' +
                        'div[contenteditable="true"][role="textbox"]'
                    );
                    if (!searchInput) return 'no_search_input';

                    const searchRect = searchInput.getBoundingClientRect();

                    // Find all div[role="button"] below the search input
                    // These are contact results, not chips
                    const buttons = document.querySelectorAll('div[role="button"]');
                    for (const btn of buttons) {
                        const rect = btn.getBoundingClientRect();
                        // Must be below search input and in the left panel (x < 600)
                        // and have reasonable height (contact items are ~60-72px)
                        if (rect.top > searchRect.bottom + 10 &&
                            rect.left < 600 &&
                            rect.height > 40 && rect.height < 100 &&
                            rect.width > 200) {
                            btn.click();
                            return 'clicked: ' + btn.textContent.substring(0, 30);
                        }
                    }
                    return 'no_result_found';
                }
            """)
            return clicked

        def count_contact_results():
            """Count contact items in the results list (below search input)."""
            return page.evaluate("""
                () => {
                    const searchInput = document.querySelector(
                        'input[placeholder*="Search"], input[placeholder*="ابحث"], ' +
                        'div[contenteditable="true"][role="textbox"]'
                    );
                    if (!searchInput) return 0;
                    const searchRect = searchInput.getBoundingClientRect();
                    let count = 0;
                    const buttons = document.querySelectorAll('div[role="button"]');
                    for (const btn of buttons) {
                        const rect = btn.getBoundingClientRect();
                        if (rect.top > searchRect.bottom + 10 &&
                            rect.left < 600 &&
                            rect.height > 40 && rect.height < 100 &&
                            rect.width > 200) {
                            count++;
                        }
                    }
                    return count;
                }
            """)

        initial_count = count_contact_results()
        print(f"  Contact results in list: {initial_count}")

        for phone in valid_phones:
            phone_clean = phone.replace('+', '')
            variants = [phone, phone_clean, '0' + phone_clean[3:], phone_clean[3:]]

            found = False
            for vi, variant in enumerate(variants):
                try:
                    # Focus the search input
                    if not find_and_focus_search():
                        print(f"  ! Could not focus search input for {phone}")
                        break

                    time.sleep(0.3)
                    type_in_search(variant)
                    time.sleep(3)

                    if added_count == 0 and vi == 0:
                        debug_screenshot(page, '05_search')

                    after_count = count_contact_results()
                    print(f"    [{variant}] results: {after_count} (was {initial_count})")

                    if after_count > 0 and (after_count < initial_count or after_count <= 3):
                        result = click_search_result()
                        print(f"    click result: {result}")
                        if result.startswith('clicked'):
                            added_count += 1
                            print(f"  + Added: {phone}")
                            found = True
                            time.sleep(1)
                            clear_search()
                            time.sleep(1)
                            break
                    elif after_count == 0:
                        # Try "Not in your contacts" link
                        for txt in ["Not in your contacts", "ليس في جهات اتصالك"]:
                            nc = page.get_by_text(txt)
                            if nc.count() > 0:
                                nc.first.click(timeout=3000)
                                added_count += 1
                                print(f"  + Added (not in contacts): {phone}")
                                found = True
                                time.sleep(1)
                                break
                        if found:
                            clear_search()
                            time.sleep(1)
                            break

                    # Clear for next variant
                    clear_search()
                    time.sleep(0.5)
                except Exception as e:
                    if vi == 0:
                        print(f"  ! Search error for {phone}: {e}")

            if not found:
                print(f"  - Not found: {phone}")
                try:
                    clear_search()
                except Exception:
                    pass
            time.sleep(0.5)

        debug_screenshot(page, '06_after_adding')

        if added_count == 0:
            print("\nNo contacts could be added (not in phone contacts).")
            print(f"\nSave these in your phone contacts:")
            for i, ph in enumerate(valid_phones, 1):
                print(f"  Name: '{group_name} {i}'  Phone: {ph}")
            browser.close()
            return False

        print(f"\n{added_count}/{len(valid_phones)} added.")

        # ---------------------------------------------------------------
        # Step 4: Click forward arrow -> Set name -> Create
        # ---------------------------------------------------------------
        print("\nStep 4: Creating group...")

        # Debug: dump all clickable elements info
        try:
            btn_info = page.evaluate("""
                () => {
                    const results = [];
                    // Check all span[data-icon], button, div[role=button]
                    document.querySelectorAll('span[data-icon], button, div[role="button"]').forEach(el => {
                        if (el.offsetParent !== null) {
                            results.push({
                                tag: el.tagName,
                                icon: el.getAttribute('data-icon'),
                                testid: el.getAttribute('data-testid'),
                                ariaLabel: el.getAttribute('aria-label'),
                                role: el.getAttribute('role'),
                                classes: el.className.substring(0, 80),
                                text: el.textContent.substring(0, 30),
                            });
                        }
                    });
                    return results;
                }
            """)
            print(f"  Visible buttons/icons: {btn_info}")
        except Exception as e:
            print(f"  Debug failed: {e}")

        # Try multiple possible selectors for the forward/next button
        next_selectors = [
            'span[data-icon="arrow-forward"]',
            'span[data-icon="forward"]',
            'span[data-icon="arrow-forward-outline"]',
            'span[data-icon="checkmark-medium"]',
            'span[data-icon="checkmark"]',
            'span[data-icon="next"]',
            '[data-testid="arrow-forward"]',
            '[data-testid="next-btn"]',
            'button[aria-label="Next"]',
            'button[aria-label="التالي"]',
            # Green circle button - try role=button with arrow
            'div[role="button"][aria-label="Next"]',
            'div[role="button"][aria-label="التالي"]',
            # Generic: any green button at the bottom (the visible round button)
            'button:has(span[data-icon*="arrow"])',
            'div[role="button"]:has(span[data-icon*="arrow"])',
        ]
        clicked_next = False
        for sel in next_selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    print(f"  Clicking next via: {sel}")
                    loc.first.click(timeout=5000)
                    clicked_next = True
                    time.sleep(3)
                    break
            except Exception:
                continue

        # Last resort: find green circle button by evaluating DOM
        if not clicked_next:
            try:
                clicked_next = page.evaluate("""
                    () => {
                        // Look for the round green button - it typically has
                        // a specific background color and contains an SVG arrow
                        const btns = document.querySelectorAll('button, div[role="button"], span[role="button"]');
                        for (const btn of btns) {
                            const style = window.getComputedStyle(btn);
                            const bg = style.backgroundColor;
                            // Green button: rgb(0, 168, 132) or similar green
                            if (bg && (bg.includes('0, 168') || bg.includes('0, 175') ||
                                       bg.includes('00a884') || bg.includes('25, 211'))) {
                                btn.click();
                                return true;
                            }
                        }
                        // Also try: any element with border-radius 50% that's green-ish
                        const circles = document.querySelectorAll('[style*="border-radius"]');
                        for (const el of circles) {
                            if (el.offsetParent && el.offsetWidth > 40 && el.offsetWidth < 80) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if clicked_next:
                    print("  Clicked next via green button detection")
                    time.sleep(3)
            except Exception:
                pass

        if not clicked_next:
            print("  Could not find next button. Taking screenshot...")
            debug_screenshot(page, '06b_no_next_btn')
            browser.close()
            return False

        print(f"  Setting name: {group_name}")
        try:
            name_box = page.locator('div[contenteditable="true"][role="textbox"]').first
            name_box.click()
            time.sleep(0.5)
            page.keyboard.type(group_name, delay=30)
            time.sleep(1)
        except Exception as e:
            print(f"  Could not set name: {e}")

        # Debug icons on name screen
        try:
            icons2 = page.evaluate("""
                () => Array.from(document.querySelectorAll('span[data-icon]'))
                    .map(el => el.getAttribute('data-icon'))
            """)
            print(f"  Icons on name screen: {icons2}")
        except Exception:
            pass

        create_selectors = [
            'span[data-icon="checkmark-large"]',
            'span[data-icon="checkmark-medium"]',
            'span[data-icon="checkmark"]',
            '[data-testid="create-group-btn"]',
            'button[aria-label="Create group"]',
            'button[aria-label="إنشاء مجموعة"]',
        ]
        clicked_create = False
        for sel in create_selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                print(f"  Creating via: {sel}")
                loc.first.click(timeout=5000)
                clicked_create = True
                break

        try:
            if not clicked_create:
                # Last resort fallback
                page.locator(
                    'span[data-icon="checkmark-large"], '
                    '[data-testid="create-group-btn"]'
                ).first.click(timeout=5000)
            time.sleep(4)
        except Exception as e:
            print(f"  Could not create: {e}")
            browser.close()
            return False

        print(f"\nGroup '{group_name}' created with {added_count} members!")
        debug_screenshot(page, '07_done')
        time.sleep(5)
        browser.close()
        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create WhatsApp group')
    parser.add_argument('--name', required=True, help='Group name')
    parser.add_argument('--phones', required=True, help='Comma-separated phones')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()

    phones = [p.strip() for p in args.phones.split(',') if p.strip()]
    success = create_whatsapp_group(args.name, phones, headless=args.headless)
    sys.exit(0 if success else 1)
