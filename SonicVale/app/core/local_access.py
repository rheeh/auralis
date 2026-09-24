"""Local browser boundary: validate Origin and fetch metadata, including WebSockets."""
import os
from urllib.parse import urlsplit

DEFAULT_ORIGINS=['http://localhost:5173','http://127.0.0.1:5173','http://localhost:5174','http://127.0.0.1:5174',
                 'http://localhost:5176','http://127.0.0.1:5176']
def allowed_origins():
    return [*DEFAULT_ORIGINS,*filter(None,os.environ.get('AURALIS_ALLOWED_ORIGINS','').split(','))]

def allows_browser(headers,query=None):
    origin=headers.get('origin')
    if origin=='null':
        import secrets
        expected=os.environ.get('AURALIS_INSTANCE_TOKEN','')
        supplied=headers.get('x-auralis-token') or (query or {}).get('instance_token','')
        return bool(expected and secrets.compare_digest(expected,supplied))
    if origin:return origin in allowed_origins()
    return headers.get('sec-fetch-site') not in {'cross-site'}
