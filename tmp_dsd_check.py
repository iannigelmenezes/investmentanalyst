import requests, urllib3
urllib3.disable_warnings()

# FM key: {FREQ}.{REF_AREA}.{CURRENCY}.{PROVIDER_FM}.{INSTRUMENT_FM}.{PROVIDER_FM_ID}.{DATA_TYPE_FM}
# For EUR IRS: FREQ=B, REF_AREA=U2, CURRENCY=EUR, PROVIDER_FM=4F, INSTRUMENT_FM=IS or SI
# PROVIDER_FM_ID = ?, DATA_TYPE_FM = ?

# Let's check what PROVIDER_FM_ID and DATA_TYPE_FM codelists contain
for cl in ['CL_PROVIDER_FM_ID', 'CL_DATA_TYPE_FM', 'CL_PROVIDER_FM']:
    r = requests.get(f'https://data-api.ecb.europa.eu/service/codelist/ECB/{cl}', timeout=15, verify=False)
    import re
    txt = r.text
    codes = re.findall(r'Code[^>]+id="([^"]+)"[^>]*>.*?<com:Name[^>]*>([^<]+)</com:Name>', txt, re.DOTALL)
    print(f'\n=== {cl} ===')
    for c_id, name in codes:
        if any(x in name.lower() for x in ['swap', 'irs', 'interest rate', 'mid', 'par', 'spot', '30', 'year']):
            print(f'  {c_id}: {name}')
