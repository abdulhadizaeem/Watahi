import httpx
import json

BASE = 'http://localhost:8000'

with httpx.Client(timeout=20) as c:
    r = c.post(BASE + '/api/auth/login',
               data={'username': 'admin@wahati.com', 'password': 'Admin1234!'},
               headers={'Content-Type': 'application/x-www-form-urlencoded'})
    token = r.json()['access_token']
    H = {'Authorization': f'Bearer {token}'}

    r = c.get(BASE + '/api/retell/clover/inventory', headers=H)
    items = r.json()
    print('First 5 Clover items:')
    for item in items[:5]:
        print(f"  id={item.get('id')}  name={item.get('name')}  price={item.get('price')}")

    first = items[0]
    r = c.post(BASE + '/api/retell/clover/item-map', headers=H,
               json={'item_name': first['name'], 'clover_item_id': first['id'], 'clover_item_name': first['name']})
    print(f'Map item -> {r.status_code} | {r.json()}')

    r = c.post(BASE + '/api/retell/order-confirm',
               json={'customer_name': 'Test Clover', 'customer_phone': '+1000000002',
                     'order_items': [{'item': first['name'], 'quantity': 1, 'special_instructions': 'no ice'}],
                     'order_type': 'pickup', 'total_amount': first['price'] / 100})
    print(f'Order confirm -> {r.status_code} | {r.text[:300]}')
