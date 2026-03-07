#!/usr/bin/env node
/**
 * WhatsApp Group Creator using whatsapp-web.js
 *
 * Usage:
 *   node wa_group_create.js --name "Group Name" --phones "+963123456789,+963987654321"
 *
 * First run shows a QR code to scan. Session is saved for subsequent runs.
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const path = require('path');

// Parse args
const args = process.argv.slice(2);
let groupName = '';
let phonesStr = '';

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--name' && args[i + 1]) groupName = args[++i];
    if (args[i] === '--phones' && args[i + 1]) phonesStr = args[++i];
}

if (!groupName || !phonesStr) {
    console.error('Usage: node wa_group_create.js --name "Group Name" --phones "+963...,+963..."');
    process.exit(1);
}

// Normalize phone numbers
const phones = phonesStr.split(',').map(p => {
    p = p.trim().replace(/[\s-]/g, '');
    if (!p) return null;
    if (p.startsWith('0')) p = '+963' + p.slice(1);
    if (!p.startsWith('+')) p = '+' + p;
    return p;
}).filter(Boolean);

if (phones.length === 0) {
    console.error('No valid phone numbers.');
    process.exit(1);
}

console.log(`Creating group "${groupName}" with ${phones.length} contacts...`);

const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: path.join(__dirname, '.wa_session_wjs')
    }),
    puppeteer: {
        executablePath: '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',
        headless: false,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled',
        ],
    },
});

client.on('qr', (qr) => {
    console.log('\nScan this QR code with WhatsApp:');
    qrcode.generate(qr, { small: true });
});

client.on('loading_screen', (percent, message) => {
    console.log(`Loading: ${percent}% - ${message}`);
});

client.on('authenticated', () => {
    console.log('Authenticated!');
});

client.on('auth_failure', (msg) => {
    console.error('Auth failed:', msg);
    process.exit(1);
});

client.on('ready', async () => {
    console.log('WhatsApp ready!\n');

    try {
        // Step 1: Verify which numbers are on WhatsApp
        console.log('Step 1: Verifying numbers...');
        const validIds = [];

        for (let i = 0; i < phones.length; i++) {
            const phone = phones[i];
            // WhatsApp ID format: countrycode+number@c.us (no + sign)
            const numberId = phone.replace('+', '') + '@c.us';
            try {
                const isRegistered = await client.isRegisteredUser(numberId);
                console.log(`  [${i + 1}/${phones.length}] ${phone}: ${isRegistered ? 'OK' : 'NOT ON WHATSAPP'}`);
                if (isRegistered) {
                    validIds.push(numberId);
                }
            } catch (err) {
                console.log(`  [${i + 1}/${phones.length}] ${phone}: ERROR - ${err.message}`);
            }
        }

        if (validIds.length === 0) {
            console.error('\nNo valid WhatsApp numbers found.');
            await client.destroy();
            process.exit(1);
        }

        console.log(`\n${validIds.length}/${phones.length} numbers verified.`);

        // Step 2: Create the group
        console.log(`\nStep 2: Creating group "${groupName}"...`);
        const result = await client.createGroup(groupName, validIds);

        if (result && result.gid) {
            console.log(`\nGroup created successfully!`);
            console.log(`  Group ID: ${result.gid._serialized || result.gid}`);
            console.log(`  Members added: ${validIds.length}`);

            // Check for any participants that failed to be added
            if (result.missingParticipants && result.missingParticipants.length > 0) {
                console.log(`  Failed to add: ${result.missingParticipants.length}`);
                for (const mp of result.missingParticipants) {
                    console.log(`    - ${JSON.stringify(mp)}`);
                }
            }
        } else {
            console.log('\nGroup creation result:', JSON.stringify(result, null, 2));
        }

        // Give WhatsApp a moment to sync
        await new Promise(r => setTimeout(r, 3000));
        console.log('\nDone!');
        await client.destroy();
        process.exit(0);

    } catch (err) {
        console.error('\nError:', err.message || err);
        await client.destroy();
        process.exit(1);
    }
});

client.on('disconnected', (reason) => {
    console.log('Disconnected:', reason);
});

console.log('Initializing WhatsApp client...');
client.initialize();
