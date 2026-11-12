# Workspace 2-Step বট — সেটআপ

`workspace_2sv_bot.py` একটা Telegram বট, যেটা আপনার Google Workspace ডোমেইনের
মেইলগুলোর 2-Step Verification (2SV) ট্র্যাক করে।

## আগে জেনে নিন

Google এমন কোনো API দেয় না যেটা দিয়ে admin বা বট অন্য ইউজারের হয়ে 2-step
**চালু** করতে পারে (Admin SDK-তে শুধু `turnOff` আছে, `turnOn` নেই)। তাই কাজটা
দুই ভাগে হয়:

1. **আপনি (admin)** Admin console থেকে একবার 2-step *enforce* করবেন — এতে সব
   মেইলে 2-step বাধ্যতামূলক হয়ে যায়।
2. **প্রতিটা ইউজার** নিজের ফোন/authenticator দিয়ে একবার enroll করবে।

বট যা করে: কে enroll করেছে আর কে করেনি তা দেখায়, নিয়মিত রিপোর্ট পাঠায়, আর
দরকার হলে ইউজারের backup code বানিয়ে দেয়।

## ধাপ ১ — Admin console-এ 2-step enforce করুন

1. <https://admin.google.com> → **Security → Authentication → 2-step verification**
2. **Allow users to turn on 2-Step Verification** টিক দিন।
3. **Enforcement → On** (অথবা একটা তারিখ দিন, যাতে সবাই সময় পায়)।
4. **New user enrollment period** দিন (যেমন ১ সপ্তাহ) — নইলে নতুন ইউজার প্রথম
   লগইনেই আটকে যাবে।
5. Save করুন।

মেনুর নাম Google মাঝে মাঝে বদলায়; না পেলে Admin console-এর সার্চে
"2-step verification" লিখুন।

## ধাপ ২ — Service account বানান

1. <https://console.cloud.google.com> → নতুন project।
2. **APIs & Services → Library → Admin SDK API → Enable**।
3. **IAM & Admin → Service Accounts → Create service account**।
4. Service account-এ ঢুকে **Keys → Add key → JSON** — একটা `.json` ফাইল নামবে।
   এই ফাইল গোপন রাখুন, GitHub-এ তুলবেন না।
5. Service account-এর **Unique ID / Client ID** কপি করুন।

## ধাপ ৩ — Domain-wide delegation দিন

Admin console → **Security → Access and data control → API controls →
Manage Domain Wide Delegation → Add new**

- **Client ID:** ধাপ ২-এর Client ID
- **OAuth scopes** (কমা দিয়ে, হুবহু এই দুটো):

```
https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/admin.directory.user.security
```

## ধাপ ৪ — Telegram বট

1. Telegram-এ [@BotFather](https://t.me/BotFather) → `/newbot` → token নিন।
2. নিজের chat ID জানতে [@userinfobot](https://t.me/userinfobot)-কে মেসেজ দিন।

## ধাপ ৫ — Environment variables

| নাম | কী দেবেন |
| --- | --- |
| `BOT_TOKEN` | BotFather-এর token |
| `ALLOWED_CHAT_IDS` | যে chat ID-গুলো বট চালাতে পারবে, কমা দিয়ে (না দিলে `CHAT_ID` ব্যবহার হয়) |
| `ADMIN_EMAIL` | আপনার ডোমেইনের একজন super admin-এর মেইল |
| `SERVICE_ACCOUNT_JSON` | JSON key ফাইলের পুরো লেখা (অথবা `SERVICE_ACCOUNT_FILE`-এ ফাইলের path) |
| `REPORT_INTERVAL_HOURS` | কত ঘণ্টা পরপর রিপোর্ট আসবে; `0` = বন্ধ (ডিফল্ট) |

## ধাপ ৬ — চালান

```bash
pip install -r requirements.txt
python workspace_2sv_bot.py
```

Docker/Railway-তে চালালে start command হিসেবে `python workspace_2sv_bot.py`
দিন (Dockerfile-এর ডিফল্ট `combined_bot.py` চালায়)।

## কমান্ড

| কমান্ড | কাজ |
| --- | --- |
| `/status` | কতজনের 2-step চালু / বন্ধ / enforce করা |
| `/pending` | যাদের 2-step এখনো বন্ধ |
| `/check email` | একটা মেইলের অবস্থা |
| `/codes email` | বর্তমান backup code |
| `/newcodes email` | নতুন ১০টা backup code (পুরনোগুলো বাতিল হয়) |
| `/export` | সব ইউজারের তালিকা CSV ফাইলে |

Backup code দিয়ে মেইলে ঢোকা যায়, তাই `ALLOWED_CHAT_IDS`-এ শুধু নিজের chat ID
রাখুন এবং কোড ব্যবহারের পর মেসেজ মুছে ফেলুন।
