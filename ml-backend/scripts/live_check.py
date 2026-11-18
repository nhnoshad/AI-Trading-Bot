import urllib.request, json

def get(path):
    with urllib.request.urlopen('http://localhost:8000' + path, timeout=5) as r:
        return json.loads(r.read())

s = get('/api/stats')
print('=== LIVE BACKEND STATUS ===')
print('Win Rate:', s.get('win_rate'), '%')
print('Total Trades:', s.get('total_trades'))
print('Wins:', s.get('wins'), '| Losses:', s.get('losses'))
print('Signals Count:', s.get('signals_count'))
print('Best Pair:', s.get('best_pair'))
print('Current Streak:', s.get('current_streak'), 'x', s.get('streak_direction'))

t = get('/api/trades?limit=5')
print()
print('Latest 5 Prediction Records:')
for tr in t.get('trades', []):
    print('  #' + str(tr['id']) + ' | ' + str(tr['pair']) + ' | ' + str(tr['direction']) + ' | ' + str(tr['result']) + ' | mode=' + str(tr['mode']))
print()
print('All pairs in DB:', t.get('all_pairs'))
