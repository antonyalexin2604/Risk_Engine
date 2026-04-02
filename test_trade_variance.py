"""Verify that trades have different notionals and MTMs."""
from backend.data_generators.portfolio_generator import build_full_dataset
from datetime import date

ds = build_full_dataset(
    book_date=date.today(),
    n_derivative_portfolios=1,
    n_trades_min=20,
    n_trades_max=20
)

p = ds['derivative_portfolios'][0]
trades = p['trades']

print("Sample of 10 trades showing notional and MTM variance:\n")
print(f"{'Trade ID':<20} {'Type':<18} {'Notional':>15} {'MTM':>15} {'MTM %':>8}")
print("=" * 85)

for i, t in enumerate(trades[:10]):
    mtm_pct = (t.current_mtm / t.notional * 100) if t.notional != 0 else 0
    print(f"{t.trade_id:<20} {t.instrument_type:<18} {t.notional:>15,.0f} {t.current_mtm:>15,.0f} {mtm_pct:>7.2f}%")

# Statistics
notionals = [t.notional for t in trades]
mtms = [t.current_mtm for t in trades]

print(f"\n{'Statistics':<20} {'Notional':>15} {'MTM':>15}")
print("=" * 52)
print(f"{'Min':<20} {min(notionals):>15,.0f} {min(mtms):>15,.0f}")
print(f"{'Max':<20} {max(notionals):>15,.0f} {max(mtms):>15,.0f}")
print(f"{'Range':<20} {max(notionals)-min(notionals):>15,.0f} {max(mtms)-min(mtms):>15,.0f}")
print(f"{'Avg':<20} {sum(notionals)/len(notionals):>15,.0f} {sum(mtms)/len(mtms):>15,.0f}")

# Check uniqueness
unique_notionals = len(set(notionals))
unique_mtms = len(set(mtms))

print(f"\n{'Uniqueness':<20} {'Count':>15}")
print("=" * 37)
print(f"{'Total trades':<20} {len(trades):>15}")
print(f"{'Unique notionals':<20} {unique_notionals:>15}")
print(f"{'Unique MTMs':<20} {unique_mtms:>15}")
print(f"\n✓ All notionals unique: {unique_notionals == len(trades)}")
print(f"✓ All MTMs unique: {unique_mtms == len(trades)}")
