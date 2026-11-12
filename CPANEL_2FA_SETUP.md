# cPanel মেইল 2-Step বট — সেটআপ

`cpanel_2fa_bot.py` একটা Telegram বট, যেটা আপনার cPanel-এ বানানো মেইলগুলোতে
নিজে নিজে 2-Step (Two-Factor Authentication) চালু করে দেয়। বট cPanel-এর
অফিসিয়াল API ব্যবহার করে — কোনো মেইলের পাসওয়ার্ড লাগে না, শুধু cPanel-এর একটা
API token লাগে।

প্রতিটা মেইলের জন্য বট যা করে:

1. cPanel থেকে ওই মেইলের একটা Webmail session খোলে
2. cPanel-এর কাছ থেকে একটা secret key নেয়
3. key থেকে ৬ সংখ্যার কোড বানিয়ে 2-step চালু করে
4. key আর QR কোড আপনাকে Telegram-এ পাঠায়

## শর্ত

- সার্ভারে cPanel **114 বা নতুন** ভার্সন (এর আগে Webmail-এ 2-step নেই)।
- হোস্টিং কোম্পানি 2-step চালু রেখেছে — Webmail-এর Settings-এ
  "Two-Factor Authentication" অপশন দেখা গেলে ধরে নিন চালু আছে।

## ধাপ ১ — cPanel API token বানান

1. cPanel-এ লগইন করুন → **Security → Manage API Tokens**
2. **Create** → একটা নাম দিন (যেমন `2fa-bot`) → Create
3. যে token দেখাবে সেটা কপি করুন (একবারই দেখায়)।

"Manage API Tokens" না পেলে হোস্টিং কোম্পানি ওটা বন্ধ রেখেছে; তখন token-এর বদলে
`CPANEL_PASSWORD`-এ cPanel-এর পাসওয়ার্ড দিতে পারেন।

## ধাপ ২ — Telegram বট

1. Telegram-এ [@BotFather](https://t.me/BotFather) → `/newbot` → token নিন।
2. নিজের chat ID জানতে [@userinfobot](https://t.me/userinfobot)-কে মেসেজ দিন।

## ধাপ ৩ — Environment variables

| নাম | কী দেবেন |
| --- | --- |
| `BOT_TOKEN` | BotFather-এর token |
| `ALLOWED_CHAT_IDS` | আপনার chat ID (একাধিক হলে কমা দিয়ে; না দিলে `CHAT_ID` ব্যবহার হয়) |
| `CPANEL_HOST` | cPanel যে ঠিকানায় খোলেন, `https://` আর পোর্ট ছাড়া (যেমন `server12.hostname.com`) |
| `CPANEL_USER` | cPanel-এর username |
| `CPANEL_TOKEN` | ধাপ ১-এর API token |

ঐচ্ছিক: `CPANEL_PASSWORD` (token না থাকলে), `CPANEL_PORT` (ডিফল্ট `2083`),
`WEBMAIL_PORT` (ডিফল্ট `2096`), `SECRETS_FILE` (ডিফল্ট `cpanel_2fa_secrets.json`)।

## ধাপ ৪ — চালান

```bash
pip install -r requirements.txt
python cpanel_2fa_bot.py
```

Docker/Railway-তে চালালে start command হিসেবে `python cpanel_2fa_bot.py` দিন
(Dockerfile-এর ডিফল্ট `combined_bot.py` চালায়)।

## ধাপ ৫ — ব্যবহার

**আগে একটা মেইলে পরীক্ষা করুন**, তারপর সবগুলোতে:

1. `/mails` — বট আপনার সব মেইল খুঁজে পাচ্ছে কিনা দেখুন
2. `/enable name@sub.yourdomain.com` — একটা মেইলে চালু করুন
3. Telegram-এ আসা QR কোডটা Google Authenticator-এ স্ক্যান করুন
4. Webmail-এ ওই মেইলে লগইন করে দেখুন কোড চাইছে এবং কোড কাজ করছে
5. ঠিক থাকলে `/enableall` — বাকি সবগুলোতে চালু হবে

| কমান্ড | কাজ |
| --- | --- |
| `/mails` | সব মেইলের তালিকা |
| `/status` | কোন মেইলে 2-step চালু / বন্ধ |
| `/enable email` | একটা মেইলে চালু |
| `/enableall` | যেগুলোতে বন্ধ, সবগুলোতে চালু |
| `/code email` | লগইনের জন্য এখনকার ৬ সংখ্যার কোড |
| `/disable email` | একটা মেইলের 2-step বন্ধ |
| `/export` | সব setup key CSV ফাইলে |

## জরুরি কথা

- **Setup key হারাবেন না।** প্রতিটা key authenticator অ্যাপে যোগ করুন, অথবা
  `/export`-এর ফাইলটা নিরাপদ জায়গায় রাখুন। key হারালে ওই মেইলের Webmail-এ ঢুকতে
  `/disable email` দিয়ে 2-step বন্ধ করে আবার চালু করতে হবে।
- বট key-গুলো `cpanel_2fa_secrets.json` ফাইলে রাখে। Railway-র মতো জায়গায় redeploy
  হলে এই ফাইল মুছে যায় — তখন `/code` আর `/export` কাজ করবে না, কিন্তু Telegram-এ
  পাওয়া key আর আপনার authenticator অ্যাপ ঠিকই চলবে।
- `ALLOWED_CHAT_IDS`-এ শুধু নিজের chat ID রাখুন — যে বট চালাতে পারে সে সব মেইলের
  2-step কোড পায়।
- "The security code is invalid" error এলে সাধারণত সার্ভারের ঘড়ি ভুল; আবার চেষ্টা
  করুন, না হলে হোস্টিং কোম্পানিকে জানান।
