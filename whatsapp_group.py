"""
WhatsApp Group Creator - delegates to whatsapp-web.js (Node.js).

Usage:
    python whatsapp_group.py --name "Group Name" --phones "+963123456789,+963987654321"

First run will ask you to scan the QR code. Session is saved for subsequent runs.
"""

import argparse
import os
import subprocess
import sys


def create_whatsapp_group(group_name, phone_numbers, headless=False):
    """Create a WhatsApp group and add members via whatsapp-web.js."""
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

    script_path = os.path.join(os.path.dirname(__file__), 'wa_group_create.js')
    if not os.path.exists(script_path):
        print(f"Error: {script_path} not found")
        return False

    cmd = ['node', script_path, '--name', group_name, '--phones', ','.join(phones)]
    print(f"Creating group '{group_name}' with {len(phones)} contacts...")
    print(f"Running: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(__file__),
        )
        # Stream output in real-time
        for line in proc.stdout:
            print(line, end='')
        proc.wait()
        return proc.returncode == 0
    except FileNotFoundError:
        print("Error: Node.js not found. Install Node.js first.")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create WhatsApp group')
    parser.add_argument('--name', required=True, help='Group name')
    parser.add_argument('--phones', required=True, help='Comma-separated phones')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()

    phones = [p.strip() for p in args.phones.split(',') if p.strip()]
    success = create_whatsapp_group(args.name, phones, headless=args.headless)
    sys.exit(0 if success else 1)
