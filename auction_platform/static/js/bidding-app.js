/**
 * GhanaHammer — Vue 3 Real-Time Bidding App
 * Mounts on the auction detail page.
 * Communicates via WebSocket for live updates.
 */

const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

const BiddingApp = createApp({
  data() {
    return {
      // Auction state (hydrated from Django template)
      auctionId: window.GH_AUCTION.id,
      lotNumber: window.GH_AUCTION.lot_number,
      title: window.GH_AUCTION.title,
      currentPrice: parseFloat(window.GH_AUCTION.current_price),
      bidCount: window.GH_AUCTION.bid_count,
      auctionStatus: window.GH_AUCTION.status,
      endTime: new Date(window.GH_AUCTION.end_time),
      minNextBid: parseFloat(window.GH_AUCTION.min_next_bid),
      buyNowPrice: window.GH_AUCTION.buy_now_price ? parseFloat(window.GH_AUCTION.buy_now_price) : null,
      reserveMet: window.GH_AUCTION.reserve_met,
      isAuthenticated: window.GH_AUCTION.is_authenticated,
      isSeller: window.GH_AUCTION.is_seller,

      // Bidding form
      bidAmount: '',
      autoBidMax: '',
      showAutoBid: false,

      // UI state
      loading: false,
      autoBidLoading: false,
      buyNowLoading: false,
      message: null,
      messageType: 'info',
      sniperExtended: false,

      // Bid history
      recentBids: window.GH_AUCTION.recent_bids || [],

      // WebSocket
      ws: null,
      wsConnected: false,
      wsRetries: 0,
    };
  },

  computed: {
    isActive() {
      return ['active', 'extended', 'closing'].includes(this.auctionStatus);
    },
    canBid() {
      return this.isAuthenticated && !this.isSeller && this.isActive;
    },
    formattedCurrentPrice() {
      return this.formatGHS(this.currentPrice);
    },
    formattedMinBid() {
      return this.formatGHS(this.minNextBid);
    },
    formattedBuyNow() {
      return this.buyNowPrice ? this.formatGHS(this.buyNowPrice) : null;
    },
    bidAmountValid() {
      const amt = parseFloat(this.bidAmount);
      return !isNaN(amt) && amt >= this.minNextBid;
    },
    autoBidAmountValid() {
      const amt = parseFloat(this.autoBidMax);
      return !isNaN(amt) && amt > this.currentPrice;
    },
    statusLabel() {
      const labels = {
        active: 'Live Auction',
        extended: '⚡ Extended (Anti-Snipe)',
        closing: '🔥 Closing Soon',
        ended: 'Auction Ended',
        sold: 'Sold',
        preview: 'VIP Preview',
        scheduled: 'Upcoming',
      };
      return labels[this.auctionStatus] || this.auctionStatus;
    },
    statusClass() {
      const map = {
        active: 'text-success',
        extended: 'text-warning',
        closing: 'text-danger',
        ended: 'text-muted',
        sold: 'text-muted',
      };
      return map[this.auctionStatus] || '';
    },
  },

  methods: {
    formatGHS(amount) {
      return 'GHS ' + parseFloat(amount).toLocaleString('en-GH', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
      });
    },

    // ── WebSocket ──────────────────────────────────────────────────
    connectWS() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/ws/auction/${this.auctionId}/`;
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.wsConnected = true;
        this.wsRetries = 0;
        console.log('[GH] Bidding WS connected');
      };

      this.ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        this.handleWSMessage(msg);
      };

      this.ws.onclose = () => {
        this.wsConnected = false;
        if (this.isActive && this.wsRetries < 10) {
          this.wsRetries++;
          const delay = Math.min(3000 * this.wsRetries, 30000);
          console.log(`[GH] WS reconnecting in ${delay}ms...`);
          setTimeout(() => this.connectWS(), delay);
        }
      };

      this.ws.onerror = (e) => {
        console.warn('[GH] WS error:', e);
      };
    },

    sendWS(data) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(data));
        return true;
      }
      return false;
    },

    handleWSMessage(msg) {
      switch (msg.type) {
        case 'auction_state':
          this.syncState(msg.data);
          break;

        case 'bid_placed':
          this.onBidPlaced(msg.data);
          break;

        case 'auction_extended':
          this.onAuctionExtended(msg.data);
          break;

        case 'auction_ended':
          this.auctionStatus = 'ended';
          this.showMessage('This auction has ended.', 'warning');
          break;

        case 'auction_sold':
          this.auctionStatus = 'sold';
          this.showMessage(`Sold for ${this.formatGHS(msg.data.amount)}!`, 'info');
          break;

        case 'bid_error':
          this.showMessage(msg.message, 'danger');
          this.loading = false;
          break;

        case 'auto_bid_set':
          this.autoBidLoading = false;
          if (msg.success) {
            this.showMessage('Auto-bid activated! We\'ll bid for you automatically.', 'success');
            this.showAutoBid = false;
            this.autoBidMax = '';
          } else {
            this.showMessage(msg.message, 'danger');
          }
          break;

        case 'pong':
          break;

        default:
          console.log('[GH] Unknown WS message:', msg.type);
      }
    },

    syncState(data) {
      this.currentPrice = parseFloat(data.current_price);
      this.bidCount = data.bid_count;
      this.auctionStatus = data.status;
      this.endTime = new Date(data.end_time);
      this.minNextBid = parseFloat(data.min_next_bid);
      this.reserveMet = data.reserve_met;
      if (data.buy_now_price) this.buyNowPrice = parseFloat(data.buy_now_price);
    },

    onBidPlaced(data) {
      this.loading = false;
      this.currentPrice = parseFloat(data.current_price);
      this.bidCount = data.bid_count;
      this.minNextBid = parseFloat(data.min_next_bid);
      this.reserveMet = data.reserve_met;
      this.bidAmount = '';

      if (data.sniper_extension) {
        this.sniperExtended = true;
        this.endTime = new Date(data.end_time);
        this.showMessage(
          `⚡ Bid received! Auction extended by ${window.GH_AUCTION.sniper_minutes || 5} minutes (anti-snipe protection).`,
          'warning'
        );
      } else {
        this.showMessage(`Bid of ${this.formatGHS(data.amount)} placed successfully!`, 'success');
      }

      // Prepend to recent bids list
      this.recentBids.unshift({
        bidder: data.bidder,
        amount: data.amount,
        placed_at: data.placed_at,
        source: 'manual',
      });
      if (this.recentBids.length > 20) this.recentBids.pop();
    },

    onAuctionExtended(data) {
      this.sniperExtended = true;
      this.endTime = new Date(data.end_time);
      this.auctionStatus = 'extended';
    },

    // ── Bid Actions ────────────────────────────────────────────────
    placeBid() {
      if (!this.canBid || !this.bidAmountValid || this.loading) return;

      this.loading = true;
      this.message = null;

      const sent = this.sendWS({
        type: 'place_bid',
        amount: parseFloat(this.bidAmount),
      });

      if (!sent) {
        // Fallback to REST API if WS disconnected
        this.placeBidHTTP(parseFloat(this.bidAmount));
      }
    },

    async placeBidHTTP(amount) {
      const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        const resp = await fetch(`/api/v1/bidding/place/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
          body: JSON.stringify({ auction_id: this.auctionId, amount }),
        });
        const data = await resp.json();
        if (data.success) {
          this.onBidPlaced(data.data);
        } else {
          this.showMessage(data.message, 'danger');
        }
      } catch (e) {
        this.showMessage('Network error. Please try again.', 'danger');
      } finally {
        this.loading = false;
      }
    },

    setAutoBid() {
      if (!this.autoBidAmountValid || this.autoBidLoading) return;
      this.autoBidLoading = true;
      this.sendWS({
        type: 'set_auto_bid',
        max_amount: parseFloat(this.autoBidMax),
      });
    },

    async buyNow() {
      if (!this.canBid || !this.buyNowPrice || this.buyNowLoading) return;
      if (!confirm(`Buy now for ${this.formattedBuyNow}? This will end the auction immediately.`)) return;

      this.buyNowLoading = true;
      this.sendWS({ type: 'buy_now' });

      // Fallback to REST
      setTimeout(async () => {
        if (this.buyNowLoading) {
          const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
          try {
            const resp = await fetch(`/api/v1/bidding/buy-now/`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
              body: JSON.stringify({ auction_id: this.auctionId }),
            });
            const data = await resp.json();
            if (data.success) {
              window.location.href = `/payments/checkout/${this.auctionId}/`;
            } else {
              this.showMessage(data.message, 'danger');
            }
          } catch (e) {
            this.showMessage('Error processing Buy Now.', 'danger');
          } finally {
            this.buyNowLoading = false;
          }
        }
      }, 3000);
    },

    // Quick-bid buttons
    quickBid(increment) {
      this.bidAmount = (this.minNextBid + increment).toFixed(2);
    },

    // ── Helpers ────────────────────────────────────────────────────
    showMessage(text, type = 'info') {
      this.message = text;
      this.messageType = type;
      if (type === 'success') {
        setTimeout(() => { if (this.message === text) this.message = null; }, 5000);
      }
    },

    formatDate(iso) {
      return new Date(iso).toLocaleString('en-GH', {
        dateStyle: 'medium', timeStyle: 'short',
      });
    },

    timeAgo(iso) {
      const diff = Date.now() - new Date(iso);
      const s = Math.floor(diff / 1000);
      if (s < 60) return `${s}s ago`;
      if (s < 3600) return `${Math.floor(s/60)}m ago`;
      return `${Math.floor(s/3600)}h ago`;
    },
  },

  mounted() {
    // Pre-fill suggested bid
    this.bidAmount = this.minNextBid.toFixed(2);

    // Connect WS only if auction is live
    if (this.isActive) {
      this.connectWS();

      // Heartbeat
      this.heartbeat = setInterval(() => {
        this.sendWS({ type: 'heartbeat' });
      }, 30000);
    }
  },

  unmounted() {
    clearInterval(this.heartbeat);
    if (this.ws) this.ws.close();
  },

  template: `
    <div class="gh-bid-panel" :class="{ 'active-auction': isActive }">

      <!-- Status -->
      <div class="d-flex align-items-center justify-content-between mb-3">
        <span class="fw-bold" :class="statusClass">
          <span v-if="auctionStatus === 'active' || auctionStatus === 'closing'" class="gh-live-dot"></span>
          {{ statusLabel }}
        </span>
        <span class="badge" :class="wsConnected ? 'bg-success' : 'bg-secondary'" style="font-size:10px">
          <i class="bi" :class="wsConnected ? 'bi-wifi' : 'bi-wifi-off'"></i>
          {{ wsConnected ? 'Live' : 'Connecting…' }}
        </span>
      </div>

      <!-- Sniper Extension Alert -->
      <div v-if="sniperExtended" class="alert alert-warning py-2 small mb-3">
        <i class="bi bi-lightning-charge-fill me-1"></i>
        <strong>Anti-snipe extended!</strong> A bid was placed near closing time. Auction extended.
      </div>

      <!-- Current Price -->
      <div class="text-center mb-3">
        <div class="gh-price-label">Current Bid</div>
        <div class="gh-current-bid-display" id="live-current-price">{{ formattedCurrentPrice }}</div>
        <div class="text-muted small mt-1">
          {{ bidCount }} bid{{ bidCount !== 1 ? 's' : '' }}
          <span v-if="reserveMet" class="text-success ms-2">
            <i class="bi bi-check-circle-fill"></i> Reserve Met
          </span>
          <span v-else-if="!reserveMet && bidCount > 0" class="text-warning ms-2">
            <i class="bi bi-exclamation-circle"></i> Reserve Not Met
          </span>
        </div>
      </div>

      <hr class="my-3">

      <!-- Message -->
      <div v-if="message" class="alert py-2 small mb-3" :class="'alert-' + messageType">
        {{ message }}
      </div>

      <!-- Not authenticated -->
      <div v-if="!isAuthenticated" class="text-center py-2">
        <p class="text-muted small mb-3">Sign in to place a bid</p>
        <a href="/accounts/login/" class="btn gh-btn-sell w-100">Sign In to Bid</a>
        <a href="/accounts/signup/" class="btn btn-outline-secondary w-100 mt-2">Create Account</a>
      </div>

      <!-- Seller cannot bid -->
      <div v-else-if="isSeller" class="alert alert-info small">
        <i class="bi bi-info-circle me-1"></i> You cannot bid on your own listing.
      </div>

      <!-- Active bidding UI -->
      <div v-else-if="isActive">
        <!-- Bid Input -->
        <div class="mb-2">
          <label class="form-label small text-muted">Your Bid (min {{ formattedMinBid }})</label>
          <div class="input-group gh-bid-input-group">
            <span class="input-group-text fw-bold">GHS</span>
            <input
              type="number"
              class="form-control"
              v-model="bidAmount"
              :min="minNextBid"
              step="1"
              placeholder="Enter bid amount"
              @keyup.enter="placeBid"
            >
            <button class="btn gh-btn-bid" @click="placeBid" :disabled="!bidAmountValid || loading">
              <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
              <i v-else class="bi bi-hammer me-1"></i>
              {{ loading ? 'Placing…' : 'Place Bid' }}
            </button>
          </div>
        </div>

        <!-- Quick bid buttons -->
        <div class="d-flex gap-2 mb-3">
          <button v-for="inc in [0, 50, 100, 500]" :key="inc"
            class="btn btn-sm btn-outline-secondary flex-fill"
            @click="quickBid(inc)"
          >
            {{ inc === 0 ? 'Min' : '+' + inc }}
          </button>
        </div>

        <!-- Buy Now -->
        <button v-if="buyNowPrice" class="btn gh-btn-buy-now mb-3" @click="buyNow" :disabled="buyNowLoading">
          <span v-if="buyNowLoading" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-bag-check me-1"></i>
          Buy Now — {{ formattedBuyNow }}
        </button>

        <!-- Auto-Bid Toggle -->
        <div class="mb-2">
          <button class="btn gh-btn-auto-bid w-100" @click="showAutoBid = !showAutoBid">
            <i class="bi bi-robot me-1"></i>
            {{ showAutoBid ? 'Cancel Auto-Bid' : 'Set Auto-Bid (Proxy)' }}
          </button>
          <div v-if="showAutoBid" class="mt-3 p-3 bg-light rounded">
            <p class="small text-muted mb-2">
              <i class="bi bi-info-circle me-1"></i>
              Set your maximum and we'll automatically bid for you up to that limit.
            </p>
            <div class="input-group mb-2">
              <span class="input-group-text">GHS</span>
              <input type="number" class="form-control" v-model="autoBidMax"
                :min="currentPrice + 1" placeholder="Your maximum bid" step="1">
            </div>
            <button class="btn gh-btn-sell w-100" @click="setAutoBid"
              :disabled="!autoBidAmountValid || autoBidLoading">
              <span v-if="autoBidLoading" class="spinner-border spinner-border-sm me-1"></span>
              {{ autoBidLoading ? 'Activating…' : 'Activate Auto-Bid' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Auction ended -->
      <div v-else-if="auctionStatus === 'ended' || auctionStatus === 'sold'" class="text-center py-2">
        <i class="bi bi-clock-history fs-2 text-muted d-block mb-2"></i>
        <p class="text-muted small">This auction has ended.</p>
      </div>

      <!-- Bid History -->
      <div class="mt-4">
        <div class="fw-semibold small text-muted text-uppercase mb-2" style="letter-spacing:.5px">
          <i class="bi bi-list-ul me-1"></i> Bid History
        </div>
        <div v-if="recentBids.length === 0" class="text-center text-muted small py-3">
          No bids yet. Be the first!
        </div>
        <div v-else>
          <div v-for="(bid, idx) in recentBids.slice(0, 8)" :key="idx" class="gh-bid-item">
            <div>
              <span class="fw-semibold small">{{ bid.bidder }}</span>
              <span v-if="bid.source === 'auto'" class="gh-bid-auto-label ms-1">Auto</span>
              <span v-if="idx === 0" class="gh-bid-winner ms-1">🏆 Winning</span>
              <div class="text-muted" style="font-size:11px">{{ timeAgo(bid.placed_at) }}</div>
            </div>
            <div class="gh-bid-amount">{{ formatGHS(bid.amount) }}</div>
          </div>
        </div>
      </div>
    </div>
  `,
});

// Mount when DOM ready
document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('gh-bidding-app');
  if (el && window.GH_AUCTION) {
    BiddingApp.mount('#gh-bidding-app');
  }
});
