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
            """Type text into the search input using Playwright click + type."""
            # Click directly on the search input to focus it
            search_input = page.locator(
                'input[placeholder*="Search name"], '
                'input[placeholder*="ابحث عن اسم"]'
            )
            if search_input.count() > 0:
                search_input.first.click()
                time.sleep(0.2)
                # Triple-click to select all text in the input only
                search_input.first.click(click_count=3)
                time.sleep(0.1)
                page.keyboard.press('Backspace')
                time.sleep(0.2)
            # Type the search text
            page.keyboard.type(text, delay=50)

        def clear_search():
            """Clear the search input without removing contact chips."""
            search_input = page.locator(
                'input[placeholder*="Search name"], '
                'input[placeholder*="ابحث عن اسم"]'
            )
            if search_input.count() > 0:
                search_input.first.click()
                time.sleep(0.1)
                # Triple-click selects all text within the input element only
                search_input.first.click(click_count=3)
                time.sleep(0.1)
                page.keyboard.press('Backspace')
                time.sleep(0.3)

        def click_search_result(phone_query=''):
            """Click the first contact in the search results list.

            Uses JS to find the contact position, then Playwright's native
            page.mouse.click() for a real click that WhatsApp responds to.
            """
            # Get position of the best candidate via JS
            pos = page.evaluate("""
                (phoneQuery) => {
                    const searchInput = document.querySelector(
                        'input[placeholder*="Search"], input[placeholder*="ابحث"], ' +
                        'div[contenteditable="true"][role="textbox"]'
                    );
                    if (!searchInput) return {error: 'no_search_input'};

                    const searchRect = searchInput.getBoundingClientRect();

                    // Collect all candidate contact items below the search
                    const candidates = [];
                    const selectors = 'div[role="listitem"], div[role="button"], div[role="option"], div[tabindex="-1"], div[tabindex="0"]';
                    document.querySelectorAll(selectors).forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.top > searchRect.bottom + 5 &&
                            rect.left < 600 &&
                            rect.height > 40 && rect.height < 120 &&
                            rect.width > 200) {
                            candidates.push({
                                text: el.textContent.substring(0, 80),
                                x: Math.round(rect.x + rect.width / 2),
                                y: Math.round(rect.y + rect.height / 2),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height),
                                top: rect.top
                            });
                        }
                    });

                    if (candidates.length === 0) return {error: 'no_result_found'};

                    // Sort by vertical position (topmost first)
                    candidates.sort((a, b) => a.top - b.top);

                    // If phone query provided, prefer matching results
                    if (phoneQuery) {
                        const digits = phoneQuery.replace(/[^0-9]/g, '');
                        const lastDigits = digits.slice(-7);
                        for (const c of candidates) {
                            const cDigits = c.text.replace(/[^0-9]/g, '');
                            if (cDigits.includes(lastDigits) || cDigits.includes(digits)) {
                                return {x: c.x, y: c.y, text: c.text, matched: true};
                            }
                        }
                    }

                    // Return the first result
                    return {x: candidates[0].x, y: candidates[0].y,
                            text: candidates[0].text, matched: false,
                            total: candidates.length};
                }
            """, phone_query)

            if 'error' in pos:
                return pos['error']

            # Use Playwright's real mouse click at the element's center
            page.mouse.click(pos['x'], pos['y'])
            matched = 'match' if pos.get('matched') else 'first'
            return f'clicked_{matched}: {pos.get("text", "?")}'

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
                        result = click_search_result(phone)
                        print(f"    click result: {result}")
                        if result.startswith('clicked'):
                            time.sleep(1)
                            # Verify a chip was added (count chips above search)
                            chip_count = page.evaluate("""
                                () => {
                                    const input = document.querySelector(
                                        'input[placeholder*="Search"], input[placeholder*="ابحث"]'
                                    );
                                    if (!input) return -1;
                                    const inputRect = input.getBoundingClientRect();
                                    // Chips are small elements above or before the input
                                    const chips = document.querySelectorAll(
                                        'button[aria-label], span[data-icon="x"], ' +
                                        'span[data-icon="x-refreshed"]'
                                    );
                                    let count = 0;
                                    chips.forEach(c => {
                                        const r = c.getBoundingClientRect();
                                        if (r.left < 600 && r.top <= inputRect.bottom + 5
                                            && r.width > 0) {
                                            count++;
                                        }
                                    });
                                    return count;
                                }
                            """)
                            print(f"    chips visible: {chip_count}")
                            added_count += 1
                            print(f"  + Added: {phone}")
                            found = True
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

        # First verify we're still on the "Add group participants" screen
        on_add_screen = page.evaluate("""
            () => {
                const inp = document.querySelector(
                    'input[placeholder*="Search name"], input[placeholder*="ابحث عن اسم"]'
                );
                return !!inp;
            }
        """)
        print(f"  On add-participants screen: {on_add_screen}")

        if not on_add_screen:
            print("  ERROR: Not on the add-participants screen anymore.")
            debug_screenshot(page, '06b_wrong_screen')
            browser.close()
            return False

        # Debug: dump clickable elements within the left panel
        try:
            btn_info = page.evaluate("""
                () => {
                    const results = [];
                    // Find the group creation panel (contains the search input)
                    const searchInput = document.querySelector(
                        'input[placeholder*="Search name"], input[placeholder*="ابحث عن اسم"]'
                    );
                    const panel = searchInput ? searchInput.closest(
                        'div[style*="height"], div[class]'
                    ) : null;

                    document.querySelectorAll('span[data-icon], button, div[role="button"]').forEach(el => {
                        if (el.offsetParent !== null) {
                            const rect = el.getBoundingClientRect();
                            if (rect.left > 600) return; // skip right panel
                            const style = window.getComputedStyle(el);
                            results.push({
                                tag: el.tagName,
                                icon: el.getAttribute('data-icon'),
                                ariaLabel: el.getAttribute('aria-label'),
                                bg: style.backgroundColor,
                                br: style.borderRadius,
                                w: Math.round(rect.width),
                                h: Math.round(rect.height),
                                pos: [Math.round(rect.x), Math.round(rect.y)],
                                text: el.textContent.substring(0, 20),
                            });
                        }
                    });
                    return results;
                }
            """)
            print(f"  Left panel elements: {btn_info}")
        except Exception as e:
            print(f"  Debug failed: {e}")

        # Try selectors including "-refreshed" variants (WhatsApp's current naming)
        next_selectors = [
            'span[data-icon="arrow-forward"]',
            'span[data-icon="arrow-forward-refreshed"]',
            'span[data-icon="forward"]',
            'span[data-icon="forward-refreshed"]',
            'span[data-icon="arrow-forward-outline"]',
            'span[data-icon="checkmark-medium"]',
            'span[data-icon="checkmark-medium-refreshed"]',
            'span[data-icon="checkmark"]',
            'span[data-icon="checkmark-refreshed"]',
            'span[data-icon="next"]',
            'span[data-icon="next-refreshed"]',
            '[data-testid="arrow-forward"]',
            '[data-testid="next-btn"]',
            'button[aria-label="Next"]',
            'button[aria-label="التالي"]',
            'div[role="button"][aria-label="Next"]',
            'div[role="button"][aria-label="التالي"]',
            'button:has(span[data-icon*="arrow"])',
            'div[role="button"]:has(span[data-icon*="arrow"])',
            'button:has(span[data-icon*="forward"])',
            'div[role="button"]:has(span[data-icon*="forward"])',
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

        # Green button: find position via JS, click via Playwright mouse
        if not clicked_next:
            try:
                result = page.evaluate("""
                    () => {
                        const searchInput = document.querySelector(
                            'input[placeholder*="Search name"], input[placeholder*="ابحث عن اسم"]'
                        );
                        if (!searchInput) return {found: false, reason: 'no_search'};

                        // Look for ANY circular/round button in left panel
                        const candidates = [];
                        document.querySelectorAll('button, div[role="button"], span[role="button"]').forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.left > 600) return;
                            const w = rect.width;
                            const h = rect.height;
                            if (w < 35 || w > 80 || h < 35 || h > 80) return;
                            if (Math.abs(w - h) > 10) return;
                            const style = window.getComputedStyle(el);
                            const br = style.borderRadius;
                            const bg = style.backgroundColor;
                            const hasSvg = !!el.querySelector('svg');
                            const hasIcon = !!el.querySelector('span[data-icon]');
                            candidates.push({
                                bg: bg, br: br, hasSvg: hasSvg, hasIcon: hasIcon,
                                cx: Math.round(rect.x + w/2),
                                cy: Math.round(rect.y + h/2),
                                w: Math.round(w), h: Math.round(h),
                                y: rect.y,
                                icon: el.querySelector('span[data-icon]')?.getAttribute('data-icon') || ''
                            });
                        });

                        if (candidates.length === 0) return {found: false, candidates: 0};

                        // Prefer green circular buttons near bottom
                        candidates.sort((a, b) => b.y - a.y);
                        // Check for green bg
                        for (const c of candidates) {
                            const m = c.bg.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                            if (m) {
                                const r = parseInt(m[1]), g = parseInt(m[2]), bl = parseInt(m[3]);
                                if (g > 100 && g > r * 1.5) {
                                    return {found: true, cx: c.cx, cy: c.cy, bg: c.bg, icon: c.icon};
                                }
                            }
                        }
                        // Fallback: any circular button with SVG/icon near bottom
                        for (const c of candidates) {
                            if (c.hasSvg || c.hasIcon) {
                                return {found: true, cx: c.cx, cy: c.cy, bg: c.bg,
                                        icon: c.icon, fallback: true};
                            }
                        }
                        return {found: false, candidates: candidates.length,
                                all: candidates.map(c => ({bg:c.bg, icon:c.icon, cy:c.cy}))};
                    }
                """)
                print(f"  Green button result: {result}")
                if result.get('found'):
                    page.mouse.click(result['cx'], result['cy'])
                    clicked_next = True
                    time.sleep(3)
            except Exception as e:
                print(f"  Green button error: {e}")

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
            'span[data-icon="checkmark-large-refreshed"]',
            'span[data-icon="checkmark-medium"]',
            'span[data-icon="checkmark-medium-refreshed"]',
            'span[data-icon="checkmark"]',
            'span[data-icon="checkmark-refreshed"]',
            '[data-testid="create-group-btn"]',
            'button[aria-label="Create group"]',
            'button[aria-label="Create"]',
            'button[aria-label="إنشاء مجموعة"]',
            'button[aria-label="إنشاء"]',
            'div[role="button"][aria-label="Create group"]',
            'div[role="button"][aria-label="إنشاء مجموعة"]',
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
