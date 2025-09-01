"""
main app
====================

Copyright 2022,2024,2025 MET Norway

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
import threading
from random import randrange
from multiprocessing import Process, Queue
from mapgen.modules.get_quicklook import get_quicklook
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

def start_processing(api, netcdf_path, query_string, netloc, scheme, q):
    try:
        start = time.time()
        response_code, response, content_type = get_quicklook(netcdf_path, query_string, netloc, scheme, products=None, api=api)
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
    if (environ['PATH_INFO'].startswith('/api/get_quicklook') or
        environ['PATH_INFO'].startswith('/klimakverna') or
        environ['PATH_INFO'].startswith('/KSS') ) and environ['REQUEST_METHOD'] == 'GET':
        try:
            netcdf_path = environ['PATH_INFO']
            if 'klimakverna' in netcdf_path:
                api = 'klimakverna'
                netcdf_path = netcdf_path.replace('/klimakverna','')
            elif 'KSS' in netcdf_path:
                api = 'KSS'
                netcdf_path = netcdf_path.replace('/KSS','')
            else:
                api = 'api/get_quicklook'
                netcdf_path = netcdf_path.replace('/api/get_quicklook','')
            query_string = environ['QUERY_STRING']
            try:
                url_scheme = environ.get('HTTP_X_FORWARDED_PROTO',
                                        environ.get('HTTP_X_SCHEME', environ['wsgi.url_scheme']))
            except Exception as ex:
                logging.debug(f"Failed to detect url scheme with Exception: {ex}")
                logging.warning(f"Failed to detect url scheme. Using http.")
                url_scheme = 'http'
            http_host = environ['HTTP_HOST']
            p = Process(target=start_processing,
                        args=(api,
                              netcdf_path,
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
            response_code = '404 Not Found'
            response = b'Not Found\n'
        except Exception as ex:
            logging.exception(f"Failed to get quicklook with Exception: {ex}")
            response_code = '500 Internal Server Error'
            response = b'Internal Server Error\n'
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
        if image_path == '/robots.txt':
            response_code = '404'
            response = b"Not Found"
            content_type = 'text/plain'
            for imgp in [image_path, '.' + image_path]:
                try:
                    logging.debug(f"Try opening {imgp}")
                    with open(imgp,'rb') as ip:
                        response = ip.read()
                        response_code = '200 OK'
                    break
                except FileNotFoundError:
                    pass
        elif image_path == '/favicon.ico':
            response_code = '404'
            response = b"Not Found"
            content_type = 'text/plain'
            for imgp in [image_path, '.' + image_path]:
                try:
                    logging.debug(f"Try opening {imgp}")
                    with open(imgp,'rb') as ip:
                        response = ip.read()
                        response_code = '200 OK'
                        content_type = 'image/vnd.microsoft.icon'
                    break
                except FileNotFoundError:
                    pass
        else:
            response_code = '404 Not Found'
            response = b"These aren't the droids you're looking for.\n"
            content_type = 'text/plain'
        response_headers = [('Content-Type', content_type)]

    elif environ['REQUEST_METHOD'] == 'OPTIONS':
        response_headers = [ ('Access-Control-Allow-Methods', 'GET, OPTIONS'), ('Access-Control-Allow-Headers', '*')]
        response_code = '200 OK'
        response = b''
        logging.debug(f"OPTIONS respond, {response_headers}")
    else:
        response_code = '400 Bad Request'
        response = b"Your are not welcome here!\n"
        response_headers = [('Content-Type', content_type)]
        logging.debug(f"{response_code}, {response}, {content_type}")
    response_headers.append(('Access-Control-Allow-Origin', '*'))
    start_response(response_code, response_headers)
    logging.debug(f"Queue length: {q.qsize()}")
    return [response]

def terminate_process(obj):
    """Terminate process"""
    logging.debug(f"{obj}")
    if obj.returncode is None:
        child_pid = obj.pid
        logging.error("This child pid is %s.", str(child_pid))
        obj.kill()
        logging.error("Process timed out and pre-maturely terminated.")
    else:
        logging.info("Process finished before time out.")
    return

class wmsServer(BaseHTTPRequestHandler):
    def send_response(self, code, message=None):
        """Add the response header to the headers buffer and log the
        response code.

        Also send two standard headers with the server software
        version and the current date.

        """
        self.log_request(code)
        self.send_response_only(code, message)
        self.send_header('Server', 'ogc-wms-from-netcdf')
        self.send_header('Date', self.date_time_string())

    def do_GET(self):
        global number_of_successfull_requests
        content_type = 'text/plain'
        start = time.time()
        dbg = [self.path, self.client_address, self.requestline, self.request, self.command, self.address_string()]
        for d in dbg:
            logging.debug(f"{d}")
        url_scheme = 'http'
        http_host = self.address_string()
        for h in str(self.headers).split('\n'):
            logging.debug(f"Header: {h}")
            if h.startswith('X-Scheme'):
                try:
                    url_scheme = h.split(" ")[1]
                except Exception:
                    pass
            if h.startswith('X-Forwarded-Host'):
                try:
                    http_host = h.split(" ")[1]
                except Exception:
                    pass
        try:
            q = Queue()
            if self.path.startswith('/api/get_quicklook'):
                try:
                    netcdf_path = self.path.replace('/api/get_quicklook','').split('?')[0]
                    try:
                        query_string = self.path.split('?')[1]
                    except IndexError:
                        query_string = ""
                    url_scheme = os.environ.get('SCHEME', url_scheme)  # environ.get('HTTP_X_SCHEME', environ['wsgi.url_scheme'])
                    http_host = os.environ.get('HOST_NAME', http_host)  # environ['HTTP_HOST']
                    p = Process(target=start_processing,
                                args=(netcdf_path,
                                    query_string,
                                    http_host,
                                    url_scheme,
                                    q))
                    p.start()
                    end = time.time()
                    logging.debug(f"Started processing in {end - start:f}seconds")
                    p.join(300)  # Timeout
                    logging.debug(f"Processing exitcode: {p.exitcode}")
                    if p.exitcode is None:
                        logging.debug(f"Processing took too long. Stopping this process. Sorry.")
                        p.terminate()
                        response_code = '500'
                        response = b'Processing took too long. Stopping this process. Sorry.\n'
                    else:
                        logging.debug(f"Returning successfully from query: {p.exitcode}")
                        (response_code, response, content_type) = q.get()
                        number_of_successfull_requests += 1
                    end = time.time()
                    logging.debug(f"Complete processing in {end - start:f}seconds")
                except KeyError as ke:
                    logging.debug(f"Failed to parse the query: {str(ke)}")
                    response_code = '404'
                    response = b'Not Found\n'
                except Exception as e:
                    logging.debug(f"Failed to parse the query: {str(e)}")
                    response_code = '500'
                    response = b'Internal Server Error\n'
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


def request_counter(web_server, request_limit):
    while 1:
        try:
            if number_of_successfull_requests > request_limit:
                logging.info("Request limit reach, shutting down...")
                web_server.shutdown()
                logging.info("Shutting down complete.")
                break
            logging.info(f"Number of requests {number_of_successfull_requests} of {request_limit}")
            time.sleep(1)
        except KeyboardInterrupt:
            break

class request_limit_shutdown(threading.Thread):

    """"""

    def __init__(self, web_server, request_limit):
        threading.Thread.__init__(self)
        self.loop = True
        self.web_server = web_server
        self.request_limit = request_limit

    def stop(self):
        """Stops the request_limit loop"""
        self.loop = False

    def run(self):
        try:
            self.loop = True
            while self.loop:
                if number_of_successfull_requests > self.request_limit:
                    logging.info("Request limit reach, shutting down...")
                    self.web_server.shutdown()
                    logging.info("Shutting down complete.")
                    self.loop = False
                logging.info(f"Number of requests {number_of_successfull_requests} of {self.request_limit}")
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutdown request_limit")

class CustomHTTPServer(HTTPServer):
    request_queue_size = 1

if __name__ == "__main__":        
    logging.config.dictConfig(logging_cfg)
    hostName = "0.0.0.0"
    serverPort = 8040
    webServer = CustomHTTPServer((hostName, serverPort), wmsServer)
    webServer.timeout = 600
    number_of_successfull_requests = 0

    logging.info(f"request queue size: {webServer.request_queue_size}")
    logging.info(f"Server started http://{hostName}:{serverPort}")

    request_limit = randrange(50,100)
    logging.debug(f"This server request_limit: {request_limit}")
    request_counter_thread = request_limit_shutdown(webServer, request_limit)
    request_counter_thread.start()
    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        request_counter_thread.stop()
        pass

    request_counter_thread.join()
    webServer.server_close()
    print("Server stopped.")
