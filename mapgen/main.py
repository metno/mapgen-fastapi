"""
main app
====================

Copyright 2022,2024 MET Norway

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import time
import logging
from multiprocessing import Process, Queue
from modules.get_quicklook import get_quicklook
from http.server import BaseHTTPRequestHandler, HTTPServer

logging_cfg = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'KeyValueFormatter': {
            'format': (
                '[%(asctime)s] [%(process)d] '
                '[%(levelname)s] %(message)s'
            )
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'KeyValueFormatter',
        }
    },
    'loggers': {
        'gunicorn.access': {
            'propagate': True,
        },
        'gunicorn.error': {
            'propagate': True,
        },
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console'],
    }
}

def start_processing(netcdf_path, query_string, netloc, scheme, q):
    try:
        start = time.time()
        response_code, response, content_type = get_quicklook(netcdf_path, query_string, netloc, scheme, products=None)
        end = time.time()
        logging.debug(f"qet_quicklook completed in: {end - start:f}seconds")
        start = end
        q.put((response_code, response, content_type))
        end = time.time()
        logging.debug(f"Put results in queue in: {end - start:f}seconds")
    except KeyboardInterrupt:
        pass

def app(environ, start_response):
    logging.config.dictConfig(logging_cfg)
    start = time.time()
    content_type = 'text/plain'
    for k in environ:
        logging.debug(f"{k}: {environ[k]}")
    q = Queue()
    if environ['PATH_INFO'].startswith('/api/get_quicklook') and environ['REQUEST_METHOD'] == 'GET':
        try:
            netcdf_path = environ['PATH_INFO'].replace('/api/get_quicklook','')
            query_string = environ['QUERY_STRING']
            url_scheme = environ.get('HTTP_X_SCHEME', environ['wsgi.url_scheme'])
            http_host = environ['HTTP_HOST']
            p = Process(target=start_processing,
                        args=(netcdf_path,
                              query_string,
                              http_host,
                              url_scheme,
                              q))
            p.start()
            end = time.time()
            logging.debug(f"Started processing in {end - start:f}seconds")
            (response_code, response, content_type) = q.get()
            response_headers = [('Content-Type', content_type)]
            p.join()
            logging.debug(f"Returning successfully from query.")
            end = time.time()
            logging.debug(f"Complete processing in {end - start:f}seconds")
        except KeyError as ke:
            logging.debug(f"Failed to parse the query: {str(ke)}")
            response_code = '404'
            response = b'Not Found\n'
        response_headers = [('Content-Type', content_type)]
    elif environ['REQUEST_METHOD'] == 'GET':
        """Need this to local images and robots.txt"""
        image_path = environ['PATH_INFO']
        logging.debug(f"image path: {image_path}")
        logging.debug(f"CWD: {os.getcwd()}")
        # if not os.path.exists(image_path) or image_path not in ['robots.txt', 'favicon.ico']:
        #     response_code = '404'
        #     response = "These aren't the droids you're looking for."
        #     content_type = 'text/plain'
        if image_path in '/robots.txt':
            response_code = '404'
            response = b"Not Found"
            content_type = 'text/plain'
            for imgp in [image_path, '.' + image_path]:
                try:
                    logging.debug(f"Try opening {imgp}")
                    with open(imgp,'rb') as ip:
                        response = ip.read()
                        response_code = '200'
                    break
                except FileNotFoundError:
                    pass
        elif image_path in '/favicon.ico':
            response_code = '404'
            response = b"Not Found"
            content_type = 'text/plain'
            for imgp in [image_path, '.' + image_path]:
                try:
                    logging.debug(f"Try opening {imgp}")
                    with open(imgp,'rb') as ip:
                        response = ip.read()
                        response_code = '200'
                        content_type = 'image/vnd.microsoft.icon'
                    break
                except FileNotFoundError:
                    pass
        else:
            response_code = '404'
            response = b"These aren't the droids you're looking for.\n"
            content_type = 'text/plain'
        response_headers = [('Content-Type', content_type)]

    elif environ['REQUEST_METHOD'] == 'OPTIONS':
        response_headers = [ ('Access-Control-Allow-Methods', 'GET, OPTIONS'), ('Access-Control-Allow-Headers', '*')]
        response_code = '200 OK'
        response = b''
        logging.debug(f"OPTIONS respond, {response_headers}")
    else:
        response_code = '400'
        response = b"Your are not welcome here!\n"
        response_headers = [('Content-Type', content_type)]
        logging.debug(f"{response_code}, {response}, {content_type}")
    response_headers.append(('Access-Control-Allow-Origin', '*'))
    start_response(response_code, response_headers)
    logging.debug(f"Queue length: {q.qsize()}")
    return [response]

class wmsServer(BaseHTTPRequestHandler):
    def do_GET(self):
        content_type = 'text/plain'
        start = time.time()
        dbg = [self.path, self.client_address, self.requestline, self.request, self.command, self.address_string()]
        for d in dbg:
            logging.debug(f"{d}")
        for h in str(self.headers).split('\n'):
            logging.debug(f"Header: {h}")

        try:
            q = Queue()
            if self.path.startswith('/api/get_quicklook'):
                try:
                    netcdf_path = self.path.replace('/api/get_quicklook','').split('?')[0]
                    try:
                        query_string = self.path.split('?')[1]
                    except IndexError:
                        query_string = ""
                    url_scheme = os.environ.get('SCHEME', 'http')  # environ.get('HTTP_X_SCHEME', environ['wsgi.url_scheme'])
                    http_host = os.environ.get('HOST_NAME', self.address_string())  # environ['HTTP_HOST']
                    p = Process(target=start_processing,
                                args=(netcdf_path,
                                    query_string,
                                    http_host,
                                    url_scheme,
                                    q))
                    p.start()
                    end = time.time()
                    logging.debug(f"Started processing in {end - start:f}seconds")
                    (response_code, response, content_type) = q.get()
                    p.join()
                    logging.debug(f"Returning successfully from query.")
                    end = time.time()
                    logging.debug(f"Complete processing in {end - start:f}seconds")
                except KeyError as ke:
                    logging.debug(f"Failed to parse the query: {str(ke)}")
                    response_code = '404'
                    response = b'Not Found\n'
            else:
                """Need this to local images and robots.txt"""
                image_path = self.path
                logging.debug(f"image path: {image_path}")
                logging.debug(f"CWD: {os.getcwd()}")
                if image_path in '/robots.txt':
                    response_code = '404'
                    response = b"Not Found"
                    content_type = 'text/plain'
                    for imgp in [image_path, '.' + image_path]:
                        try:
                            logging.debug(f"Try opening {imgp}")
                            with open(imgp,'rb') as ip:
                                response = ip.read()
                                response_code = '200'
                            break
                        except FileNotFoundError:
                            pass
                elif image_path in '/favicon.ico':
                    response_code = '404'
                    response = b"Not Found"
                    content_type = 'text/plain'
                    for imgp in [image_path, '.' + image_path]:
                        try:
                            logging.debug(f"Try opening {imgp}")
                            with open(imgp,'rb') as ip:
                                response = ip.read()
                                response_code = '200'
                                content_type = 'image/vnd.microsoft.icon'
                            break
                        except FileNotFoundError:
                            pass
                else:
                    response_code = '404'
                    response = b"These aren't the droids you're looking for.\n"
                    content_type = 'text/plain'
            response_headers = [('Content-Type', content_type)]
            response_headers.append(('Access-Control-Allow-Origin', '*'))
            self.send_response(int(response_code))
            for response_header in response_headers:
                self.send_header(response_header[0], response_header[1])
            self.end_headers()
            self.wfile.write(response)
        except BrokenPipeError:
            logging.warning("Lost connection to client.")
            pass

    def do_OPTIONS(self):
        response_headers = [ ('Access-Control-Allow-Methods', 'GET, OPTIONS'), ('Access-Control-Allow-Headers', '*')]
        response_code = '200'
        response = b''
        logging.debug(f"OPTIONS respond, {response_headers}")
        self.send_response(int(response_code))
        for response_header in response_headers:
            self.send_header(response_header[0], response_header[1])
        self.end_headers()
        self.wfile.write(response)

#import ssl
if __name__ == "__main__":        
    logging.config.dictConfig(logging_cfg)
    hostName = "0.0.0.0"
    serverPort = 8040
    webServer = HTTPServer((hostName, serverPort), wmsServer)
    webServer.timeout = 600
    # sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # sslctx.check_hostname = False # If set to True, only the hostname that matches the certificate will be accepted
    # sslctx.load_cert_chain(certfile='cert.pem', keyfile="key.pem")
    # webServer.socket = sslctx.wrap_socket(webServer.socket, server_side=True)

    print(webServer.request_queue_size)
    print("Server started http://%s:%s" % (hostName, serverPort))

    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    print("Server stopped.")
