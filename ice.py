# The MIT License (MIT)
#
# Copyright (c) 2014-2015 Susam Pal
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


"""Ice - WSGI on the rocks.

Ice is a simple and tiny WSGI microframework meant for developing small
Python web applications.
"""


__version__ = '0.0.1'
__date__ = '25 March 2014'
__author__ = 'Susam Pal <susam@susam.in>'
__credits__ = ('Marcel Hellkamp, for writing bottle, the inspiration '
               'behind ice.')


import collections
import itertools
import re
import cgi
import urllib.parse
import http.server
import os
import mimetypes


def cube():
    """Return an Ice application with a default home page.

    This function returns an object of class Ice. It creates an Ice
    object, adds a route to return the default page when a client
    requests / using HTTP GET method, adds an error handler to return
    HTTP error pages when an error occurs and returns this object. The
    returned object may be used as a WSGI application.
    """
    app = Ice()

    @app.get('/')
    def default_home_page():
        return simple_html('It works!',
                           '<h1>It works!</h1>\n'
                           '<p>This is the default ice web page.</p>')

    @app.error()
    def generic_error_page():
        return simple_html(app.response.status_line,
                           '<h1>{title}</h1>\n'
                           '<p>{description}</p>\n'
                           '<hr>\n'
                           '<address>Ice/{version}</address>'.format(
                           title=app.response.status_line,
                           description=app.response.status_detail,
                           version=__version__))

    def simple_html(title, body):
        return (
            '<!DOCTYPE html>\n'
            '<html>\n<head><title>{title}</title></head>\n'
            '<body>\n{body}\n</body>\n</html>\n'
        ).format(title=title, body=body)

    return app


class Ice:

    """A single WSGI application.

    Each instance of this class is a single, distinct callable object
    that functions as WSGI application.
    """

    def __init__(self):
        """Initialize the application."""
        self.router = Router()
        self.server = None
        self._error_handlers = {}

    def run(self, host='127.0.0.1', port=8080):
        """Run the application using a simple WSGI server."""
        from wsgiref import simple_server
        self.server = simple_server.make_server(host, port, self)
        self.server.serve_forever()

    def exit(self):
        """Stop the simple WSGI server running the appliation."""
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def running(self):
        """Return true iff the simple WSGI server is running."""
        return self.server is not None

    def get(self, pattern):
        """Decorator to add route for an HTTP GET request.

        Arguments:
        pattern -- Routing pattern the path must match (type: str)
        """
        return self.route('GET', pattern)

    def post(self, pattern):
        """Decorator to add route for an HTTP POST request.

        Arguments:
        pattern -- Routing pattern the path must match (type: str)
        """
        return self.route('POST', pattern)

    def route(self, method, pattern):
        """Decorator to add route for a request with any HTTP method.

        Arguments:
        method  -- HTTP method name, e.g. GET, POST, etc. (type: str)
        pattern -- Routing pattern the path must match (type: str)

        Return: Decorator function (type: function)
        """
        def decorator(callback):
            self.router.add(method, pattern, callback)
            return callback
        return decorator

    def error(self, status=None):
        """Decorator to add a callback that generates error page.

        The status parameter specifies the HTTP response code for which
        the decorated callback should be invoked. If the status argument
        is specified as None, then the decorated callable is considered
        to be a fallback callback.

        A fallback callback, when defined, is invoked to generate the
        error page for any HTTP response representing an error when
        there is no error handler defined explicitly for the response
        code of the HTTP response.

        Arguments:
        status -- HTTP response status code, e.g. 404, 500. (type: int);
                  None to decorate a fallback error handler
        """
        def decorator(callback):
            self._error_handlers[status] = callback
            return callback
        return decorator

    def static(self, root, path, media_type=None, charset='UTF-8'):
        """Send content of a static file as response.

        The path to what is known as the document root directory should
        be specified as the root argument. This is very important to
        prevent directory traversal attack. This method guarantees that
        only files within the document root directory are served and no
        files outside this directory can be accessed by a client.

        The path to the actual file to be returned should be specified
        as the path argument. This path must be relative to the document
        directory.

        The media_type and charset arguments are used to set the
        Content-Type header of the HTTP response. If media_type argument
        is specified as None (which is the default), then media_type is
        guessed from the filename of the file to be returned.

        Arguments:
        root       -- Path to document root directory (type: str)
        path       -- Path to file relative to document root (type: str)
        media_type -- Media type of file (default: None) (type: str)
        charset    -- Character set of file (default: 'UTF-8') (type: str)

        Return: Content of file to be returned as bytes (type: bytes)
        """
        root = os.path.abspath(os.path.join(root, ''))
        path = os.path.abspath(os.path.join(root, path.lstrip('/\\')))

        # Save the filename from the path in the response state, so that
        # a following download() call can default to this filename for
        # downloadable file when filename is not explicitly specified.
        self.response.state['filename'] = os.path.basename(path)

        if not path.startswith(root):
            return 403
        elif not os.path.isfile(path):
            return 404

        if media_type is not None:
            self.response.media_type = media_type
        else:
            self.response.media_type = mimetypes.guess_type(path)[0]
        self.response.charset = charset

        with open(path, 'rb') as f:
            return f.read()

    def download(self, content, filename=None,
                 media_type=None, charset='UTF-8'):
        """Send content as attachment (downloadable file).

        The specified content is sent after setting Content-Disposition
        header such that the client prompts the user to save the content
        locally as a file. If there are directory path separators in
        filename, only the base name is used for this purpose.

        If filename is specified as None (which is the default), then
        the filename obtained from a previous static() method call made
        while handling the current request is used. If no such call was
        made in the current request, then the filename is obtained from
        the request path. If the request path contains a directory only,
        i.e. ends with a slash, then LogicError is raised.

        The media_type and charset arguments are used to set the
        Content-Type header of the HTTP response. If media_type argument
        is specified as None (which is the default), then media_type is
        guessed from the filename of the file to be returned.

        content    -- Content to be sent as file to be saved or HTTP
                      status code (type: str or int)
        filename   -- Filename to use for saving the content (type: str)
        media_type -- Media type of file (default: None) (type: str)
        charset    -- Character set of file (default: 'UTF-8') (type: str)

        Return: content, i.e. the first argument is returned (type: str)

        Raise:
        LogicError -- When filename for the download cannot be determined
        """
        if isinstance(content, int) and content != 200:
            return content
        if filename is not None:
            filename = os.path.basename(filename)
        elif 'filename' in self.response.state:
            filename = self.response.state['filename']
        else:
            filename = os.path.basename(self.request.path)

        if filename == '':
            raise LogicError('Cannot determine filename for download')

        if media_type is not None:
            self.response.media_type = media_type
        else:
            self.response.media_type = mimetypes.guess_type(filename)[0]
        self.response.charset = charset
        self.response.add_header('Content-Disposition', 'attachment; '
                                 'filename="{}"'.format(filename))
        return content

    def __call__(self, environ, start_response):
        """Respond to a request.

        Arguments:
        environ        -- Dictionary of environment variables
                          (type: dict)
        start_response -- Callable to start HTTP response
                          (type: callable)

        Return: List of one byte string (type: list)
        """
        self.request = Request(environ)
        self.response = Response(start_response)

        route = self.router.resolve(self.request.method,
                                    self.request.path)
        if route is not None:
            callback, args, kwargs = route
            value = callback(*args, **kwargs)
        elif self.router.contains_method(self.request.method):
            value = 404 # Not found
        else:
            value = 501 # Not Implemented

        if isinstance(value, str) or isinstance(value, bytes):
            self.response.body = value
        elif isinstance(value, int) and value in Response.responses:
            self.response.status = value
            if self.response.body is None:
                self.response.body = self._get_error_page_callback()()
        else:
            raise Error('Route callback for {} {} returned invalid '
                        'value: {}: {!r}'.format(self.request.method,
                        self.request.path, type(value).__name__, value))

        return self.response.response()

    def _get_error_page_callback(self):
        """Return an error page for the current response status.

        Return: Callback that returns str (type: callable)
        """
        if self.response.status in self._error_handlers:
            return self._error_handlers[self.response.status]
        elif None in self._error_handlers:
            return self._error_handlers[None]
        else:
            # Rudimentary error handler if no error handler was found
            self.response.media_type = 'text/plain'
            return lambda: self.response.status_line


class Router:

    """Route management and resolution."""

    def __init__(self):
        """Initialize router."""
        self._literal = collections.defaultdict(dict)
        self._wildcard = collections.defaultdict(list)
        self._regex = collections.defaultdict(list)

    def add(self, method, pattern, callback):
        """Add a route.

        Arguments:
        method   -- HTTP method, e.g. GET, POST, etc. (type: str)
        pattern  -- Pattern for which the callback should be invoked
                    (type: str)
        callback -- Callback (type: callable)
        """
        pat_type, pat = self._normalize_pattern(pattern)
        if pat_type == 'literal':
            self._literal[method][pat] = callback
        elif pat_type == 'wildcard':
            self._wildcard[method].append(WildcardRoute(pat, callback))
        else:
            self._regex[method].append(RegexRoute(pat, callback))

    def resolve(self, method, path):
        """Resolve a request to a callback registered for the request.

        Arguments:
        method -- HTTP method, e.g. GET, POST, etc. (type: str)
        path   -- Path information in the request (type: str)

        Return: A tuple of three items: the callback, a list of
                positional arguments and a dictionary of keyword
                arguments (type: tuple); None if no route matches the
                request
        """
        if method in self._literal and path in self._literal[method]:
            return self._literal[method][path], [], {}
        else:
            return self._resolve_non_literal_route(method, path)

    def contains_method(self, method):
        """Determine if a method is supported by the router.

        Arguments:
        method -- HTTP method name, e.g. GET, POST, etc. (type: str)

        Return: True if there is at least one route defined for the
                method; False otherwise
        """
        return method in itertools.chain(self._literal, self._wildcard,
                                         self._regex)

    def _resolve_non_literal_route(self, method, path):
        """Resolve a request to a callback for non-literal route.

        Arguments:
        method -- HTTP method name, e.g. GET, POST, etc. (type: str)
        path   -- Path to match existing patterns against (type: str)

        Return: A tuple of three items: the callback, a list of
                positional arguments and a dictionary of keyword
                arguments (type: tuple); None if no wildcard route
                matches the request
        """
        for route_dict in (self._wildcard, self._regex):
            if method in route_dict:
                for route in reversed(route_dict[method]):
                    callback_data = route.match(path)
                    if callback_data is not None:
                        return callback_data
        return None

    @staticmethod
    def _normalize_pattern(pattern):
        """Returned a normalize form of the pattern.

        This normalizes the pattern by removing pattern type prefix if
        it exists in the pattern. It returns the pattern type and the
        pattern as a tuple of two strings.

        Arguments:
        pattern -- Request path pattern string (type: str)

        Return: A tuple of pattern type and pattern (type: tuple)
        """
        if pattern.startswith('regex:'):
            pattern_type = 'regex'
            pattern = pattern[len('regex:'):]
        elif pattern.startswith('wildcard:'):
            pattern_type = 'wildcard'
            pattern = pattern[len('wildcard:'):]
        elif pattern.startswith('literal:'):
            pattern_type = 'literal'
            pattern = pattern[len('literal:'):]
        elif RegexRoute.like(pattern):
            pattern_type = 'regex'
        elif WildcardRoute.like(pattern):
            pattern_type = 'wildcard'
        else:
            pattern_type = 'literal'
        return pattern_type, pattern


class WildcardRoute:

    """Route containing wildcards to match request path."""

    _wildcard_re = re.compile(r'<[^<>/]*>')
    _tokenize_re = re.compile(r'<[^<>/]*>|[^<>/]+|/|<|>')

    def __init__(self, pattern, callback):
        """Initialize wildcard route.

        Arguments:
        pattern  -- Pattern associated with the route (type: str)
        callback -- Callback associated with the route (type: callable)
        """
        self._re = []
        self._wildcards = []
        for token in WildcardRoute.tokens(pattern):
            if token and token.startswith('<') and token.endswith('>'):
                w = Wildcard(token)
                self._wildcards.append(w)
                self._re.append(w.regex())
            else:
                self._re.append(re.escape(token))
        self._re = re.compile('^' + ''.join(self._re) + '$')
        self._callback = callback

    def match(self, path):
        """Return callback with arguments if path matches this route.

        Arguments:
        path -- Request path (type: str)

        Return: A tuple of three items: the callback, a list of
                positional arguments and a dictionary of keyword
                arguments (type: tuple); None if the path does not match
                the route's request path pattern
        """
        match = self._re.search(path)
        if match is None:
            return None
        args = []
        kwargs = {}
        for i, wildcard in enumerate(self._wildcards):
            if wildcard.name == '!':
                continue
            value = wildcard.value(match.groups()[i])
            if not wildcard.name:
                args.append(value)
            else:
                kwargs[wildcard.name] = value
        return self._callback, args, kwargs

    @staticmethod
    def like(pattern):
        """Determine if a pattern looks like a wildcard based pattern.

        Arguments:
        pattern -- Request path pattern string (type: str)

        Return: True if the specified pattern looks like a wildcard
                based pattern; False otherwise (type: bool)
        """
        return WildcardRoute._wildcard_re.search(pattern) is not None

    @staticmethod
    def tokens(pattern):
        """Return tokens, that are not forward-slashes, in a pattern.

        Argument:
        pattern -- Request path pattern string (type: str)

        Return: List of token strings (type: list)
        """
        return WildcardRoute._tokenize_re.findall(pattern)


class Wildcard:

    """A single wildcard definition in a wildcard route's pattern."""

    _types_re = {
        'str': r'([^/]+)',
        'path': r'(.+)',
        'int': r'(0|[1-9][0-9]*)',
        '+int': r'([1-9][0-9]*)',
        '-int': r'(0|-?[1-9][0-9]*)',
    }
    _name_re = re.compile(r'^(?:[^\d\W]\w*|!|)$') # Identifiers, '!', ''

    def __init__(self, spec):
        """Initialize wildcard definition.

        Arguments:
        spec -- An angle-bracket delimited wildcard specification
        """
        # Split '<foo:int>' into ['foo', 'int']
        tokens = spec[1:-1].split(':', 1)
        if len(tokens) == 1: # Split '<foo>' into ['foo', '']
            tokens.append('')
        self.name, self._type = tokens
        if not self._type:
            self._type = 'str'
        if Wildcard._name_re.search(self.name) is None:
            raise RouteError('Invalid wildcard name {!r} in {!r}'
                             .format(self.name, spec))
        if self._type not in Wildcard._types_re.keys():
            raise RouteError('Invalid wildcard type {!r} in {!r}'
                             .format(self._type, spec))

    def regex(self):
        return Wildcard._types_re[self._type]

    def value(self, value):
        """Convert specified value to a value of proper type.

        This method does not check if the value matches the wildcard
        type. The caller of this method must ensure that the value
        passed to this method was obtained from a match by regular
        expression returned by the regex method of this class. Ensuring
        this guarantees that the value passed to the method matches the
        wildcard type.

        Arguments:
        value -- Value to convert (type: str)

        Return: Value converted to proper type (type: str or int)
        """
        return value if self._type in ['str', 'path'] else int(value)


class RegexRoute:

    """A regular expression pattern."""

    _group_re = re.compile(r'\(.*\)')

    def __init__(self, pattern, callback):
        """Construct a regex route.

        Arguments:
        pattern  -- Pattern associated with the route (type: str)
        callback -- Callback associated with the route (type: callback)
        """
        self._re = re.compile(pattern)
        self._callback = callback

    def match(self, path):
        """Return callback with arguments if path matches this route.

        Arguments:
        path -- Request path (type: str)

        Return: A tuple of three items: the callback, a list of
                positional arguments and a dictionary of keyword
                arguments (type: tuple); None if the path does not match
                the route's request path pattern
        """
        match = self._re.search(path)
        if match is None:
            return None
        kwargs_indexes = match.re.groupindex.values()
        args_indexes = [i for i in range(1, match.re.groups + 1)
                          if i not in kwargs_indexes]
        args = [match.group(i) for i in args_indexes]
        kwargs = {}
        for name, index in match.re.groupindex.items():
            kwargs[name] = match.group(index)
        return self._callback, args, kwargs

    @staticmethod
    def like(pattern):
        """Determine if a pattern looks like a regex based pattern.

        Arguments:
        pattern -- Routing pattern string (type: str)

        Return: True if the specified pattern looks like a regex based
                pattern; False otherwise (type: bool)
        """
        return RegexRoute._group_re.search(pattern) is not None


class Request:

    """Current request."""

    def __init__(self, environ):
        """Initialize the current request object.

        environ -- Dictionary of environment variables (type: dict)
        """
        self.environ = environ
        self.method = environ.get('REQUEST_METHOD', 'GET')
        self.path = environ.get('PATH_INFO', '/')
        if not self.path:
            self.path = '/'
        self.query = MultiDict()
        self.form = MultiDict()

        if 'QUERY_STRING' in environ:
            for k, v in urllib.parse.parse_qsl(environ['QUERY_STRING']):
                self.query[k] = v

        if 'wsgi.input' in environ:
            fs = cgi.FieldStorage(fp=environ['wsgi.input'],
                                  environ=environ)
            for k in fs:
                for v in fs.getlist(k):
                    self.form[k] = v

class Response:

    """Current response."""

    # Convert HTTP response status codes, phrases and detail in
    # http.server module into a dictionary of objects
    _Status = collections.namedtuple('_Status', ('phrase', 'detail'))
    responses = {}
    for k, v in http.server.BaseHTTPRequestHandler.responses.items():
        responses[k] = _Status(*v)

    def __init__(self, start_response_callable):
        """Initialize the current response object.

        start_response_callable -- Callable to start HTTP response
                                   (type: callable)
        """
        self.start = start_response_callable
        self.status = 200
        self.media_type = 'text/html'
        self.charset = 'UTF-8'
        self._headers = []
        self.body = None
        self.state = {}

    def response(self):
        """Return the HTTP response body.

        Return: HTTP response body as a sequence of bytes (type: bytes)
        """
        if isinstance(self.body, bytes):
            out = self.body
        elif isinstance(self.body, str):
            out = self.body.encode(self.charset)
        else:
            out = b''
        self.add_header('Content-Type', self.content_type)
        self.add_header('Content-Length', str(len(out)))

        self.start(self.status_line, self._headers)
        return [out]

    def add_header(self, name, value):
        """Add an HTTP header to response object.

        Arguments:
        name  -- HTTP header field name (type: str)
        value -- HTTP header field value (type: str)
        """
        if value is not None:
            self._headers.append((name, value))

    @property
    def status_line(self):
        """Return the HTTP response status line.

        Return: Status line (type: str)
        """
        return (str(self.status) + ' ' +
                Response.responses[self.status].phrase)

    @property
    def status_detail(self):
        """Return a description of the current HTTP response status.

        Return: Response status description (type: str)
        """
        return Response.responses[self.status].detail

    @property
    def content_type(self):
        """Return the value of Content-Type header field.

        Return: Value of Content-Type header field (type: str)
        """
        if (self.media_type is not None and
            self.media_type.startswith('text/') and
            self.charset is not None):
            return self.media_type + '; charset=' + self.charset
        else:
            return self.media_type


class MultiDict(collections.UserDict):

    """Dictionary with multiple values for a key.

    Setting an existing key to a new value merely adds the value to the
    list of values for the key. Getting the value of an existing key
    returns the newest value set for the key.
    """

    def __setitem__(self, key, value):
        """Adds value to the list of values for the specified key.

        Arguments:
        key   -- Key (type: object)
        value -- Value (type: object)
        """
        if key not in self.data:
            self.data[key] = [value]
        else:
            self.data[key].append(value)

    def __getitem__(self, key):
        """Return the newest value for the specified key.

        Arguments:
        key -- Key (type: object)

        Return: Newest value for the specified key
        """
        return self.data[key][-1]

    def getall(self, key, default=[]):
        """Return the list of all values for the specified key.

        Arguments:
        key -- Key (type: object)

        Keyword arguments:
        default -- Default value to return if the key does not exist

        Return: List of all values for the specified key if the key
                exists; [] otherwise (type: list)
        """
        return self.data[key] if key in self.data else default


class Error(Exception):
    """Base class for exceptions used by ice."""


class RouteError(Error):
    """Route related exception."""


class LogicError(Error):
    """Logical error due to a bug in the code that uses this module."""
