# 🔨 GhanaHammer — Ghana's Premier Online Auction Platform

A full-featured auction marketplace built for Ghana, with real-time bidding,
mobile money integration, escrow payments, AI features, and more.

## ✨ Feature Highlights

| Feature | Status |
|---|---|
| Real-time WebSocket bidding | ✅ |
| Auto-bidding (Proxy Bidding) | ✅ |
| Bid Sniper Protection (auto-extend) | ✅ |
| Escrow Payment System | ✅ |
| Paystack (Card, MoMo, Bank Transfer) | ✅ |
| MTN MoMo / Telecel / AirtelTigo | ✅ |
| KYC Verification | ✅ |
| Two-Factor Authentication (2FA) | ✅ |
| WhatsApp Notifications | ✅ |
| AI Price Recommendations | ✅ |
| AI Description Generator | ✅ |
| Demand Forecasting | ✅ |
| Fraud Detection | ✅ |
| Seller Analytics Dashboard | ✅ |
| Subscription Plans (Free/Silver/Gold/Platinum) | ✅ |
| Bid Credits | ✅ |
| Bulk CSV/Excel Import | ✅ |
| Saved Searches & Smart Alerts | ✅ |
| VIP Early Access | ✅ |
| Featured & Sponsored Listings | ✅ |
| Reserve Price Auctions | ✅ |
| Buy Now + Auction | ✅ |
| Live Video Auctions | ✅ |
| In-App Messaging & Negotiation | ✅ |
| Multi-Vendor Marketplace | ✅ |
| Advanced Search Filters | ✅ |
| Auction Scheduling | ✅ |
| Seller Verification Badge | ✅ |
| Watchlist | ✅ |

## 🛠️ Tech Stack

- **Backend**: Django 5.1, Django REST Framework
- **Frontend**: Vue 3 (CDN), Bootstrap 5.3, Bootstrap Icons
- **Real-time**: Django Channels 4, WebSockets, Redis
- **Task Queue**: Celery + Redis
- **Database**: PostgreSQL (prod), SQLite (dev)
- **Payments**: Paystack (cards, mobile money, bank transfer)
- **Notifications**: WhatsApp Business API, Email, In-App WebSocket
- **AI**: Rule-based engine (extendable to Claude API)
- **Storage**: WhiteNoise (static), AWS S3 (media, optional)
- **Hosting**: Render.com or Namecheap

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- pip
- (Optional) Redis for Celery/Channels

```bash
# 1. Clone and setup
cd ghanahammer
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY

# 4. Run migrations
python manage.py migrate --settings=auction_platform.settings.development

# 5. Create categories and initial data
python manage.py shell --settings=auction_platform.settings.development
>>> from setup_data import create_initial_data; create_initial_data()

# 6. Create superuser
python manage.py createsuperuser --settings=auction_platform.settings.development

# 7. Run dev server
python manage.py runserver --settings=auction_platform.settings.development
```

Visit: http://localhost:8000 | Admin: http://localhost:8000/admin/

## 🌐 Deployment on Render.com

1. Push code to GitHub
2. Create new Web Service on Render → connect GitHub repo
3. Set **Build Command**:
   ```
   pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput
   ```
4. Set **Start Command**:
   ```
   gunicorn auction_platform.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
   ```
5. Add environment variables from `.env.example`
6. Add PostgreSQL database (Render managed)
7. Add Redis instance (Render managed)
8. Create separate Worker services for Celery worker and beat

## 💳 Paystack Setup

1. Register at [paystack.com](https://paystack.com)
2. Get API keys from Dashboard → Settings → API Keys
3. Register your webhook URL: `https://yourdomain.com/payments/webhook/paystack/`
4. Whitelist webhook events: `charge.success`, `transfer.success`, `refund.failed`

## 📱 WhatsApp Notifications

1. Create Meta Business Account
2. Set up WhatsApp Business API
3. Add `WHATSAPP_API_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` to `.env`

## 📁 Project Structure

```
ghanahammer/
├── auction_platform/         # Django project config
│   ├── settings/
│   │   ├── base.py          # Shared settings
│   │   ├── development.py   # Local dev overrides
│   │   └── production.py    # Production settings
│   ├── urls.py              # Root URL configuration
│   ├── asgi.py              # ASGI + WebSocket config
│   └── celery.py            # Celery configuration
│
├── apps/
│   ├── accounts/            # Users, profiles, subscriptions, 2FA
│   ├── auctions/            # Listings, categories, watchlist, bulk import
│   ├── bidding/             # Bids, auto-bidding, bid credits, fraud
│   ├── payments/            # Paystack, escrow, bank transfer, MoMo
│   ├── messaging/           # In-app chat, negotiation room
│   ├── analytics/           # Seller dashboard, market trends
│   ├── kyc/                 # Identity verification
│   ├── notifications/       # In-app, WhatsApp, email alerts
│   └── ai_engine/           # Price recommendation, descriptions, forecasting
│
├── templates/               # Django HTML templates
│   ├── base/base.html       # Master layout with navbar, footer
│   ├── auctions/            # Listing pages
│   ├── dashboard/           # Seller/buyer dashboard
│   ├── payments/            # Checkout, escrow
│   └── messaging/           # Chat interface
│
├── auction_platform/static/
│   ├── css/ghanahammer.css  # Main stylesheet
│   ├── js/ghanahammer.js    # Utility functions
│   └── js/bidding-app.js    # Vue 3 real-time bidding component
│
├── requirements.txt
├── manage.py
├── .env.example
└── deploy/
    └── render.yaml          # Render.com deployment config
```

## 🏛️ Database Models

| Model | App | Purpose |
|---|---|---|
| User | accounts | Extended user with plan, KYC, MoMo |
| SavedSearch | accounts | Smart alerts configuration |
| SubscriptionPayment | accounts | Plan payment history |
| SellerReview | accounts | Buyer→seller ratings |
| Category | auctions | Hierarchical categories |
| Auction | auctions | Core listing with all fields |
| AuctionImage | auctions | Multiple images per listing |
| Watchlist | auctions | User watching an auction |
| Bid | bidding | Individual bid records |
| AutoBid | bidding | Proxy bidding configuration |
| BidCreditPackage | bidding | Credit pack definitions |
| FraudFlag | bidding | Fraud detection alerts |
| Payment | payments | Paystack transaction records |
| EscrowAccount | payments | Escrow fund holding |
| BankTransferInstruction | payments | Manual bank transfer details |
| MessageThread | messaging | Conversation between users |
| Message | messaging | Individual messages + offers |
| Notification | notifications | In-app notification records |
| KYCDocument | kyc | Identity verification docs |
| AuctionView | analytics | View tracking |
| MarketAnalytics | analytics | Pre-computed market data |

## 🔐 Security Features

- Django Axes (brute force protection)
- TOTP Two-Factor Authentication
- Paystack webhook HMAC-SHA512 signature verification
- KYC verification for high-value transactions
- Rate limiting on bid placement API
- Fraud detection scoring on every bid
- CSRF protection on all forms
- SSL/HTTPS enforced in production

## 📄 License

Proprietary — Sikaba Systems © 2026. All rights reserved.
