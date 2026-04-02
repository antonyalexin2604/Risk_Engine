"""Quick test to validate asset class and exotic distribution guarantees."""
from backend.data_generators.portfolio_generator import build_full_dataset
from datetime import date

# Test with 50 trades
ds = build_full_dataset(
    book_date=date.today(),
    n_derivative_portfolios=1,
    n_trades_min=50,
    n_trades_max=50
)

p = ds['derivative_portfolios'][0]
trades = p['trades']

# Count asset classes
asset_counts = {}
for t in trades:
    asset_counts[t.asset_class] = asset_counts.get(t.asset_class, 0) + 1

# Count exotics
exotic_types = {
    'IRCap', 'IRFloor', 'Swaption', 'BermudanSwap',
    'FXOption', 'FXBarrier', 'FXAsianOption',
    'VarSwap', 'EquityBarrier', 'BasketOption',
    'CDO_Tranche', 'CommodityOption', 'SpreadOption'
}
exotic_count = sum(1 for t in trades if t.instrument_type in exotic_types)

print(f'Total trades: {len(trades)}')
print(f'Asset class distribution: {dict(sorted(asset_counts.items()))}')
print(f'All 5 asset classes present: {set(asset_counts.keys()) == {"IR", "FX", "EQ", "CR", "CMDTY"}}')
print(f'Exotic trades: {exotic_count} ({exotic_count/len(trades)*100:.1f}%)')
print(f'Minimum 10% exotics guaranteed: {exotic_count >= max(int(50 * 0.10), 5)}')

# Test with 200 trades (new default minimum)
ds2 = build_full_dataset(
    book_date=date.today(),
    n_derivative_portfolios=1,
    n_trades_min=200,
    n_trades_max=200
)

p2 = ds2['derivative_portfolios'][0]
trades2 = p2['trades']

asset_counts2 = {}
for t in trades2:
    asset_counts2[t.asset_class] = asset_counts2.get(t.asset_class, 0) + 1

exotic_count2 = sum(1 for t in trades2 if t.instrument_type in exotic_types)

print(f'\n--- With 200 trades (new default) ---')
print(f'Total trades: {len(trades2)}')
print(f'Asset class distribution: {dict(sorted(asset_counts2.items()))}')
print(f'All 5 asset classes present: {set(asset_counts2.keys()) == {"IR", "FX", "EQ", "CR", "CMDTY"}}')
print(f'Exotic trades: {exotic_count2} ({exotic_count2/len(trades2)*100:.1f}%)')
print(f'Minimum 10% exotics guaranteed: {exotic_count2 >= max(int(200 * 0.10), 5)}')
