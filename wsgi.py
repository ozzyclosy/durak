# WSGI wrapper for Durak game
# PythonAnywhere expects a WSGI application

import sys
import os

# Add the app directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import the game server
from durak_server import DurakHandler, game
import http.server
import json

# Create a single server instance (reused across requests)
_server = http.server.HTTPServer(("", 0), DurakHandler)

def application(environ, start_response):
    """WSGI → HTTP adapter."""
    from io import BytesIO
    
    path = environ.get('PATH_INFO', '/')
    query = environ.get('QUERY_STRING', '')
    method = environ.get('REQUEST_METHOD', 'GET')
    
    # Build the full path with query string
    full_path = path
    if query:
        full_path += '?' + query
    
    # Create a minimal request object
    import urllib.parse
    
    class FakeRequest:
        def __init__(self):
            self.path = full_path
            self.command = method
            
    class FakeWfile:
        def __init__(self):
            self.data = BytesIO()
            self.headers_sent = False
            self.status = 200
            
    handler = DurakHandler(FakeRequest(), ('0.0.0.0', 0), _server)
    
    # Monkey-patch to capture output
    wfile = FakeWfile()
    handler.wfile = wfile
    
    # Handle the request
    if method == 'GET':
        handler.do_GET()
    elif method == 'POST':
        handler.do_POST()
    else:
        start_response('405 Method Not Allowed', [('Content-Type', 'text/plain')])
        return [b'Method not allowed']
    
    # Extract the response
    response_data = wfile.data.getvalue()
    
    # Determine content type
    content_type = 'application/json'
    if path == '/' or '.html' in path:
        content_type = 'text/html; charset=utf-8'
    
    headers = [
        ('Content-Type', content_type),
        ('Access-Control-Allow-Origin', '*'),
    ]
    
    start_response('200 OK', headers)
    return [response_data]
